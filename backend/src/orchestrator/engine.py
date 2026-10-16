"""
RetrievalEngine: the one entry point the API uses.

    route → plan → execute (parallel retrieval) → evidence → synthesize once → trace

``answer_stream`` yields ``StreamEvent`` objects (progress / evidence / answer_delta / done / error)
and ``answer`` collects the same into an ``Answer``.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional

from src.contracts import (
    Answer, AnswerDeltaEvent, Confidence, DoneEvent, ErrorEvent, EvidenceEvent, Intent, ProgressEvent,
    QueryPlan, RetrievalFilters, StreamEvent, TraceRecord, WarningEvent,
)
from src.core.config import settings
from src.core.logger import get_logger
from src.knowledge import KnowledgeAdapter, get_knowledge_adapter
from src.services.llm.nvidia_llm_service import LLMUsage, NvidiaLLMService, get_llm_service

from .executor import ExecutionResult, PlanExecutor
from .planner import QueryPlanner
from .router import QueryRouter, RouteDecision
from .synthesizer import Synthesizer, assess_confidence, resolve_citations

logger = get_logger(__name__)


class RetrievalEngine:
    def __init__(
        self,
        llm: Optional[NvidiaLLMService] = None,
        adapter: Optional[KnowledgeAdapter] = None,
        router: Optional[QueryRouter] = None,
        planner: Optional[QueryPlanner] = None,
        executor: Optional[PlanExecutor] = None,
        synthesizer: Optional[Synthesizer] = None,
        trace_sink=None,
    ):
        self._llm = llm
        self._adapter = adapter
        self.router = router or QueryRouter(llm=llm)
        self.planner = planner or QueryPlanner(llm=llm)
        self.executor = executor or PlanExecutor(adapter=adapter)
        self.synthesizer = synthesizer or Synthesizer(llm=llm)
        self.trace_sink = trace_sink   # async callable(TraceRecord) → None
        self._guardrails = None

    @property
    def llm(self) -> NvidiaLLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    @property
    def adapter(self) -> KnowledgeAdapter:
        if self._adapter is None:
            self._adapter = get_knowledge_adapter()
        return self._adapter

    # ── guardrails ─────────────────────────────────────────────────────

    async def _check_input(self, query: str) -> Optional[str]:
        if not settings.guardrails_enabled or not settings.input_guardrails:
            return None
        try:
            if self._guardrails is None:
                from src.services.llm.guardrails_service import GuardrailsService
                self._guardrails = GuardrailsService()
            result = await self._guardrails.check_input(query)
            if getattr(result, "result", None) and str(result.result).lower().endswith("blocked"):
                return getattr(result, "message", None) or "Request blocked by input guardrails"
        except Exception as exc:  # guardrails must never break answering
            logger.debug("Guardrail check skipped", error=str(exc))
        return None

    # ── main streaming flow ────────────────────────────────────────────

    async def answer_stream(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        filters: Optional[RetrievalFilters] = None,
        use_rag: bool = True,
        top_k: Optional[int] = None,
        reasoning_effort: str = "low",
        has_documents: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        started = time.perf_counter()
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        answer_id = f"a_{uuid.uuid4().hex[:12]}"
        usage = LLMUsage()
        filters = filters or RetrievalFilters()
        if tenant_id and not filters.tenant_id:
            filters.tenant_id = tenant_id
        text_parts: List[str] = []
        execution: Optional[ExecutionResult] = None
        plan: Optional[QueryPlan] = None
        decision: Optional[RouteDecision] = None
        intent = Intent.KNOWLEDGE
        confidence = Confidence.LOW
        warnings: List[str] = []
        citations = []

        try:
            yield ProgressEvent(stage="understanding", label="Understanding question").to_stream()
            blocked = await self._check_input(query)
            if blocked:
                yield ErrorEvent(message=blocked, code="guardrail_blocked").to_stream()
                return

            # 1. Route
            if use_rag:
                decision = await self.router.route(query, has_documents=has_documents, usage=usage)
            else:
                decision = RouteDecision(Intent.CHAT, 1.0, "RAG disabled by request", "chat")
            intent = decision.intent
            yield ProgressEvent(stage="routing", label=f"Route: {intent.value.lower()}",
                                detail={"confidence": decision.confidence, "reason": decision.reason}).to_stream()

            if intent == Intent.ACTION:
                msg = "I can't perform actions such as sending, deleting or scheduling. I can answer questions from your documents."
                text_parts.append(msg)
                yield AnswerDeltaEvent(text=msg).to_stream()
                confidence = Confidence.HIGH
            elif intent == Intent.CLARIFICATION:
                plan = await self.planner.plan(query, decision, usage=usage)
                msg = plan.clarification_question or "Could you give me a bit more detail?"
                text_parts.append(msg)
                yield AnswerDeltaEvent(text=msg).to_stream()
                confidence = Confidence.MEDIUM
            elif intent == Intent.CHAT:
                plan = QueryPlan(intent=Intent.CHAT, query_type="chat", synthesis_strategy="direct", reasoning=decision.reason)
                yield ProgressEvent(stage="synthesizing", label="Replying").to_stream()
                async for token in self.synthesizer.chat_stream(query, chat_history, usage=usage):
                    text_parts.append(token)
                    yield AnswerDeltaEvent(text=token).to_stream()
                confidence = Confidence.HIGH
            elif not has_documents and self.adapter.name == "local":
                msg = ("No documents have been indexed yet, so I can't answer this from your knowledge base. "
                       "Upload a document first (Documents page) and ask again once it shows as completed.")
                text_parts.append(msg)
                yield AnswerDeltaEvent(text=msg).to_stream()
                confidence = Confidence.LOW
            else:
                # 2. Plan
                caps = self.adapter.capabilities()
                plan = await self.planner.plan(query, decision, backend_plans_itself=caps.query_planning, usage=usage)
                if plan.needs_clarification and plan.clarification_question:
                    text_parts.append(plan.clarification_question)
                    yield AnswerDeltaEvent(text=plan.clarification_question).to_stream()
                    confidence = Confidence.MEDIUM
                else:
                    if plan.is_multi_hop:
                        yield ProgressEvent(stage="planning", label=f"Breaking the question into {len(plan.steps)} parts",
                                            detail={"sub_questions": [s.goal for s in plan.steps]}).to_stream()
                    # 3. Execute
                    yield ProgressEvent(stage="retrieving", label=f"Searching {self.adapter.name} knowledge").to_stream()
                    execution = await self.executor.execute(
                        plan, filters=filters, top_k=top_k, reasoning_effort=reasoning_effort,
                    )
                    warnings.extend(execution.warnings)
                    for w in execution.warnings:
                        yield WarningEvent(message=w).to_stream()

                    if execution.is_empty:
                        yield ProgressEvent(stage="found_sources", label="No relevant sources found").to_stream()
                        msg = ("I couldn't find anything in the indexed documents that answers this. "
                               "Try rephrasing, or check that the relevant document has been uploaded and processed.")
                        text_parts.append(msg)
                        yield AnswerDeltaEvent(text=msg).to_stream()
                        confidence = Confidence.LOW
                    else:
                        yield ProgressEvent(stage="found_sources", label=f"Found {len(execution.evidence)} relevant passages",
                                            detail={"count": len(execution.evidence)}).to_stream()
                        yield EvidenceEvent(evidence=[e.model_dump() for e in execution.evidence]).to_stream()
                        # legacy event for the existing UI
                        yield StreamEvent(event="sources", data=[e.to_legacy_source() for e in execution.evidence])

                        # 4. Synthesize once
                        yield ProgressEvent(stage="synthesizing", label="Writing answer").to_stream()
                        async for token in self.synthesizer.stream(query, execution.context, plan.synthesis_strategy,
                                                                   chat_history, usage=usage):
                            text_parts.append(token)
                            yield AnswerDeltaEvent(text=token).to_stream()
                        raw = "".join(text_parts)
                        cleaned, citations = resolve_citations(raw, execution.evidence)
                        confidence = assess_confidence(execution.evidence, citations, cleaned)
                        if cleaned != raw:
                            text_parts = [cleaned]
                            warnings.append("Removed citations that did not match any evidence")

            final_text = "".join(text_parts)
            latency = round((time.perf_counter() - started) * 1000, 1)
            trace = TraceRecord(
                trace_id=trace_id, session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=query,
                intent=intent, plan=plan, tool_calls=execution.tool_calls if execution else [],
                evidence_count=len(execution.evidence) if execution else 0, total_latency_ms=latency,
                prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens, confidence=confidence,
                model=self.llm.model, extra={"route_method": decision.method if decision else None,
                                             "backend": self.adapter.name, "warnings": warnings, "answer_id": answer_id,
                                             "citations": [c.model_dump() for c in citations]},
            )
            await self._emit_trace(trace)
            self.last_answer = Answer(
                answer_id=answer_id, session_id=session_id, text=final_text, intent=intent, confidence=confidence,
                evidence=execution.evidence if execution else [], citations=citations, latency_ms=latency,
                trace_id=trace_id, route="rag_pipeline" if execution else intent.value.lower(), usage=usage.to_dict(),
                warnings=warnings,
            )
            yield DoneEvent(answer_id=answer_id, confidence=confidence.value, latency_ms=latency, trace_id=trace_id,
                            session_id=session_id, citations=[c.model_dump() for c in citations],
                            usage=usage.to_dict()).to_stream()
        except Exception as exc:
            logger.exception("Engine failure", error=str(exc), trace_id=trace_id)
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}").to_stream()

    async def answer(self, query: str, **kwargs) -> Answer:
        """Non-streaming convenience wrapper."""
        error: Optional[str] = None
        self.last_answer = None
        async for event in self.answer_stream(query, **kwargs):
            if event.event == "error":
                error = str(event.data)
        if self.last_answer is None:
            return Answer(answer_id=f"a_{uuid.uuid4().hex[:12]}", text=error or "", intent=Intent.KNOWLEDGE,
                          confidence=Confidence.LOW, route="error", warnings=[error] if error else [])
        return self.last_answer

    async def _emit_trace(self, trace: TraceRecord) -> None:
        if self.trace_sink is None:
            return
        try:
            await self.trace_sink(trace)
        except Exception as exc:
            logger.warning("Trace persistence failed", error=str(exc))


_default: Optional[RetrievalEngine] = None


def get_engine() -> RetrievalEngine:
    global _default
    if _default is None:
        from src.services.traces import persist_trace
        _default = RetrievalEngine(trace_sink=persist_trace)
    return _default


def set_engine(engine: Optional[RetrievalEngine]) -> None:
    global _default
    _default = engine
