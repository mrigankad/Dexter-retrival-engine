"""Execute plan steps against knowledge adapters in parallel, within tool-call budgets."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts import (
    Evidence, QueryPlan, RetrievalFilters, RetrievalRequest, RetrievalResult, RetrievedChunk, ToolCallRecord,
)
from src.core.config import settings
from src.core.logger import get_logger
from src.knowledge import KnowledgeAdapter, get_knowledge_adapter
from src.retrieval import ContextBuilder, reciprocal_rank_fusion

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    chunks: List[RetrievedChunk] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    context: str = ""
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    per_step: Dict[str, RetrievalResult] = field(default_factory=dict)
    backend: str = "local"
    warnings: List[str] = field(default_factory=list)
    data_results: List[Any] = field(default_factory=list)      # QueryResult objects from data.query steps
    blocks: List[Dict[str, Any]] = field(default_factory=list)  # table / chart blocks for the UI
    clarification: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.chunks and not self.data_results


class PlanExecutor:
    def __init__(self, adapter: Optional[KnowledgeAdapter] = None, fallback: Optional[KnowledgeAdapter] = None,
                 data_service=None):
        self._adapter = adapter
        self._fallback = fallback
        self._data_service = data_service
        self.context_builder = ContextBuilder()

    @property
    def data_service(self):
        if self._data_service is None:
            from src.data_gateway import get_data_query_service
            self._data_service = get_data_query_service()
        return self._data_service

    async def _run_data_step(self, step_id: str, goal: str, usage=None) -> tuple[Optional[Any], ToolCallRecord, Optional[str]]:
        from src.data_gateway import DataQueryError
        started = time.perf_counter()
        record = ToolCallRecord(tool="data.query", step_id=step_id, backend="data_gateway", input_summary=goal[:120])
        clarification = None
        result = None
        try:
            result = await self.data_service.query(goal, usage=usage)
            record.result_count = result.row_count
            record.status = "ok" if result.row_count else "empty"
        except DataQueryError as exc:
            record.status, record.error = "error", str(exc)
            clarification = exc.clarification
        except Exception as exc:
            record.status, record.error = "error", f"{type(exc).__name__}: {exc}"
        record.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return result, record, clarification

    @property
    def adapter(self) -> KnowledgeAdapter:
        if self._adapter is None:
            self._adapter = get_knowledge_adapter()
        return self._adapter

    @property
    def fallback(self) -> Optional[KnowledgeAdapter]:
        if self._fallback is None and settings.knowledge_fallback_backend:
            try:
                self._fallback = get_knowledge_adapter(settings.knowledge_fallback_backend)
            except Exception as exc:  # pragma: no cover
                logger.warning("Fallback backend unavailable", error=str(exc))
        return self._fallback

    async def _run_step(self, step_id: str, request: RetrievalRequest) -> tuple[Optional[RetrievalResult], ToolCallRecord]:
        started = time.perf_counter()
        record = ToolCallRecord(tool="knowledge.retrieve", step_id=step_id, backend=self.adapter.name,
                                input_summary=request.query[:120])
        try:
            result = await self.adapter.retrieve(request)
            if result.is_empty and self.fallback is not None:
                logger.info("Primary backend returned nothing; trying fallback", step=step_id)
                result = await self.fallback.retrieve(request)
                record.backend = f"{self.adapter.name}->{self.fallback.name}"
            record.result_count = len(result.chunks)
            record.status = "ok" if result.chunks else "empty"
        except Exception as exc:
            logger.warning("Retrieval step failed", step=step_id, error=str(exc))
            result = None
            if self.fallback is not None:
                try:
                    result = await self.fallback.retrieve(request)
                    record.backend = f"{self.adapter.name}!->{self.fallback.name}"
                    record.result_count = len(result.chunks)
                    record.status = "ok" if result.chunks else "empty"
                except Exception as exc2:
                    record.status, record.error = "error", f"{exc}; fallback: {exc2}"
            else:
                record.status, record.error = "error", str(exc)
        record.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return result, record

    async def execute(
        self,
        plan: QueryPlan,
        filters: Optional[RetrievalFilters] = None,
        top_k: Optional[int] = None,
        reasoning_effort: str = "low",
        max_context_tokens: Optional[int] = None,
        usage=None,
    ) -> ExecutionResult:
        result = ExecutionResult(backend=self.adapter.name)
        data_steps = [s for s in plan.steps if s.tool == "data.query"][: settings.data_max_sql_calls]
        steps = [s for s in plan.steps if s.tool == "knowledge.retrieve"][: max(0, plan.max_tool_calls - len(data_steps))]

        data_outcomes = await asyncio.gather(*(self._run_data_step(s.id, s.goal, usage=usage) for s in data_steps)) if data_steps else []
        data_context_parts: List[str] = []
        for (step, (qres, record, clarification)) in zip(data_steps, data_outcomes):
            result.tool_calls.append(record)
            if clarification and result.clarification is None:
                result.clarification = clarification
            if qres is None:
                result.warnings.append(f"Data query failed for step {step.id}: {record.error}")
                continue
            result.data_results.append(qres)
            result.blocks.append({"type": "table", "data": {"query_id": qres.query_id, "title": qres.question, "columns": qres.columns,
                                                            "rows": qres.rows[:200], "row_count": qres.row_count, "sql": qres.sql,
                                                            "connection": qres.connection_name}})
            chart = self.data_service.chart_for(qres)
            if chart and chart.get("type") not in (None, "table"):
                result.blocks.append({"type": "chart", "data": {**chart, "query_id": qres.query_id}})

        if not steps:
            self._finish_with_data(result, data_context_parts)
            return result
        top_k = top_k or settings.rerank_top_k
        per_step_k = top_k if len(steps) == 1 else max(3, (top_k * 2) // len(steps) + 1)

        requests = []
        for i, step in enumerate(steps):
            requests.append((step.id, RetrievalRequest(
                query=step.goal, top_k=per_step_k, filters=filters or RetrievalFilters(),
                rerank=True, reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
                alternate_queries=list(step.alternate_queries) if settings.multi_query_enabled else [],
                max_context_chars=(max_context_tokens or settings.max_context_tokens) * 4,
            )))
        outcomes = await asyncio.gather(*(self._run_step(sid, req) for sid, req in requests))

        ranked_lists: List[List[RetrievedChunk]] = []
        for (sid, _), (res, record) in zip(requests, outcomes):
            result.tool_calls.append(record)
            if res is None:
                result.warnings.append(f"Retrieval failed for step {sid}: {record.error}")
                continue
            result.per_step[sid] = res
            if res.chunks:
                for c in res.chunks:
                    c.metadata.setdefault("step_id", sid)
                ranked_lists.append(res.chunks)

        if not ranked_lists:
            self._finish_with_data(result, data_context_parts)
            return result
        if len(ranked_lists) == 1:
            fused = ranked_lists[0]
        else:
            # Interleave sub-query results so every sub-question keeps representation.
            fused = reciprocal_rank_fusion(ranked_lists, k=settings.rrf_k)
        built = self.context_builder.build(fused, max_tokens=max_context_tokens)
        result.chunks = built.chunks
        result.evidence = built.evidence
        result.context = built.text
        if built.truncated:
            result.warnings.append("Context truncated to fit the token budget")
        self._finish_with_data(result, data_context_parts)
        return result

    def _finish_with_data(self, result: ExecutionResult, data_context_parts: List[str]) -> None:
        """Append SQL results as numbered evidence after the document evidence."""
        if not result.data_results:
            return
        parts = [result.context] if result.context else []
        for qres in result.data_results:
            n = len(result.evidence) + 1
            result.evidence.append(self.data_service.to_evidence(qres, n))
            parts.append(f"[{n}] {qres.connection_name} query {qres.query_id} [sql]\n{self.data_service.to_context(qres)}")
        result.context = "\n\n---\n\n".join(parts)
