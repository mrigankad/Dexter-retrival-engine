"""Execute plan steps against knowledge adapters in parallel, within tool-call budgets."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    @property
    def is_empty(self) -> bool:
        return not self.chunks


class PlanExecutor:
    def __init__(self, adapter: Optional[KnowledgeAdapter] = None, fallback: Optional[KnowledgeAdapter] = None):
        self._adapter = adapter
        self._fallback = fallback
        self.context_builder = ContextBuilder()

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
    ) -> ExecutionResult:
        steps = [s for s in plan.steps if s.tool == "knowledge.retrieve"][: plan.max_tool_calls]
        result = ExecutionResult(backend=self.adapter.name)
        if not steps:
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
        return result
