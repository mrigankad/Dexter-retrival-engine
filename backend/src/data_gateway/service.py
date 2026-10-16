"""DataQueryService: the `data.query` tool. Every path goes through SqlPolicy before execution."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from src.contracts import Evidence, EvidenceLocator
from src.core.config import settings
from src.core.logger import get_logger
from src.services.llm.nvidia_llm_service import LLMUsage

from .charts import rows_to_markdown, suggest_chart, validate_chart_spec
from .connections import DataConnectionManager, get_connection_manager
from .generator import SqlGenerator
from .models import DataConnection, QueryResult, SemanticModel
from .policy import SqlPolicy, SqlPolicyError
from .semantic import example_context, match_verified, rank_tables, schema_context

logger = get_logger(__name__)


class DataQueryError(RuntimeError):
    def __init__(self, message: str, clarification: Optional[str] = None, violations: Optional[List[str]] = None):
        super().__init__(message)
        self.clarification = clarification
        self.violations = violations or []


class SemanticStore:
    """In-memory semantic models keyed by connection (persisted through the admin API / DB)."""

    def __init__(self) -> None:
        self._models: Dict[str, SemanticModel] = {}

    def get(self, connection_id: str) -> Optional[SemanticModel]:
        return self._models.get(connection_id)

    def set(self, model: SemanticModel) -> None:
        self._models[model.connection_id] = model

    def clear(self) -> None:
        self._models.clear()


class DataQueryService:
    def __init__(self, manager: Optional[DataConnectionManager] = None, generator: Optional[SqlGenerator] = None,
                 semantic: Optional[SemanticStore] = None):
        self._manager = manager
        self.generator = generator or SqlGenerator()
        self.semantic = semantic or SemanticStore()
        self.max_attempts = 2

    @property
    def manager(self) -> DataConnectionManager:
        if self._manager is None:
            self._manager = get_connection_manager()
        return self._manager

    @property
    def available(self) -> bool:
        return settings.data_gateway_enabled and any(c.enabled for c in self.manager.list())

    def policy_for(self, conn: DataConnection, catalog_tables: Optional[List[str]] = None) -> SqlPolicy:
        allowed = conn.allowed_tables or (catalog_tables or [])
        return SqlPolicy(dialect=conn.dialect, allowed_tables=allowed, denied_columns=conn.denied_columns,
                         default_limit=conn.default_row_limit, hard_limit=conn.hard_row_limit)

    # ── raw SQL (admins / analysts): still policed ─────────────────────

    async def run_sql(self, sql: str, connection_id: Optional[str] = None, limit: Optional[int] = None,
                      question: Optional[str] = None, source: str = "raw") -> QueryResult:
        conn = self.manager.get(connection_id)
        catalog = await self.manager.discover(conn.id)
        policy = self.policy_for(conn, [t.qualified for t in catalog.tables])
        checked = policy.enforce(sql, limit=limit)
        columns, rows, truncated, latency = await self.manager.execute(conn.id, checked.exec_sql or checked.sql, max_rows=checked.limit)
        return QueryResult(
            query_id=f"q_{uuid.uuid4().hex[:10]}", connection_id=conn.id, connection_name=conn.name, question=question,
            sql=checked.sql, columns=columns, rows=rows, row_count=len(rows), truncated=truncated, latency_ms=latency,
            source=source, tables=checked.tables,
        )

    # ── natural language ───────────────────────────────────────────────

    async def query(self, question: str, connection_id: Optional[str] = None, usage: Optional[LLMUsage] = None,
                    limit: Optional[int] = None) -> QueryResult:
        if not settings.data_gateway_enabled:
            raise DataQueryError("Data gateway is disabled")
        conn = self.manager.get(connection_id)
        model = self.semantic.get(conn.id)
        verified = match_verified(model, question)
        if verified is not None:
            result = await self.run_sql(verified.sql, conn.id, limit=limit, question=question, source="verified")
            result.explanation = verified.description or "Verified query template"
            return result

        catalog = await self.manager.discover(conn.id)
        ranked = rank_tables(catalog, model, question)
        tables = [t for t, _ in ranked] or catalog.tables[:5]
        schema = schema_context(tables, model)
        examples = example_context(model, question)
        policy = self.policy_for(conn, [t.qualified for t in catalog.tables])
        feedback = ""
        last_error: Optional[str] = None
        for attempt in range(self.max_attempts):
            gen = await self.generator.generate(question, schema, conn.dialect, policy.default_limit, examples=examples,
                                                feedback=feedback, today=date.today().isoformat(), usage=usage)
            if gen["needs_clarification"]:
                raise DataQueryError("clarification needed", clarification=gen.get("clarification") or "Which metric do you mean?")
            if not gen["sql"]:
                feedback = "no SQL was returned"
                continue
            checked = policy.validate(gen["sql"], limit=limit)
            if not checked.ok:
                last_error = "; ".join(checked.violations)
                feedback = last_error
                logger.info("Generated SQL rejected by policy", attempt=attempt + 1, violations=checked.violations)
                continue
            try:
                columns, rows, truncated, latency = await self.manager.execute(conn.id, checked.exec_sql or checked.sql, max_rows=checked.limit)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                feedback = f"the query failed to execute: {last_error}"
                continue
            result = QueryResult(
                query_id=f"q_{uuid.uuid4().hex[:10]}", connection_id=conn.id, connection_name=conn.name, question=question,
                sql=checked.sql, columns=columns, rows=rows, row_count=len(rows), truncated=truncated, latency_ms=latency,
                source="generated", explanation=gen["explanation"], tables=checked.tables,
            )
            chart = None
            if gen.get("chart"):
                try:
                    chart = validate_chart_spec(gen["chart"], columns)
                except ValueError:
                    chart = None
            result_chart = chart or suggest_chart(columns, rows, title=question[:80])
            result.explanation = result.explanation or ""
            setattr(result, "_chart", result_chart)
            return result
        raise DataQueryError(f"Could not produce a valid query: {last_error or 'unknown error'}",
                             violations=[last_error] if last_error else [])

    # ── evidence helpers ───────────────────────────────────────────────

    @staticmethod
    def chart_for(result: QueryResult) -> Optional[Dict[str, Any]]:
        return getattr(result, "_chart", None) or suggest_chart(result.columns, result.rows, title=result.question or "")

    @staticmethod
    def to_evidence(result: QueryResult, index: int) -> Evidence:
        preview = rows_to_markdown(result.columns, result.rows, max_rows=20)
        return Evidence(
            id=f"ev_{index}", type="sql", source_name=f"{result.connection_name} (SQL)", title=result.question,
            locator=EvidenceLocator(query_id=result.query_id), snippet=preview[:1500], score=1.0, backend="data_gateway",
            content_type="table",
            metadata={"sql": result.sql, "columns": result.columns, "row_count": result.row_count, "truncated": result.truncated,
                      "rows": result.rows[:50], "latency_ms": result.latency_ms, "source": result.source,
                      "explanation": result.explanation, "tables": result.tables},
        )

    @staticmethod
    def to_context(result: QueryResult) -> str:
        table = rows_to_markdown(result.columns, result.rows, max_rows=50)
        note = " (truncated)" if result.truncated else ""
        return (f"Query results from {result.connection_name} ({result.row_count} rows{note}). SQL: {result.sql}\n"
                f"{table}")


_service: Optional[DataQueryService] = None


def get_data_query_service() -> DataQueryService:
    global _service
    if _service is None:
        _service = DataQueryService()
    return _service


def set_data_query_service(service: Optional[DataQueryService]) -> None:
    global _service
    _service = service
