"""
Planner: turn a routed question into a bounded ``QueryPlan`` of tool steps.

Simple lookups get a single ``knowledge.retrieve`` step plus (optionally) a
few alternate phrasings for multi-query fusion. Complex questions are
decomposed by the fast model into atomic sub-questions. Backends that plan
for themselves (Foundry IQ at low/medium effort) receive the original
question only.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from src.contracts import Intent, PlanStep, QueryPlan
from src.core.config import settings
from src.core.logger import get_logger
from src.services.llm.nvidia_llm_service import LLMUsage, NvidiaLLMService, get_llm_service

from .router import RouteDecision

logger = get_logger(__name__)

PLANNER_SYSTEM = """You decompose questions about a document collection into a small retrieval plan.
Return ONLY JSON:
{
  "sub_questions": ["atomic question 1", "atomic question 2"],   // 1-{max_steps} items, each independently searchable
  "alternate_phrasings": ["another way to phrase the original question"],  // 0-2 items, same meaning as the original
  "synthesis_strategy": "summary" | "comparison_table" | "timeline" | "bullet_analysis",
  "needs_clarification": false,
  "clarification_question": null,
  "reasoning": "one sentence"
}
Rules: keep every specific term (numbers, names, years, product codes). Split comparisons into one question per side,
multi-period questions into one per period, "why" questions into "what happened" + "what were the causes".
Do not invent sub-questions the user did not ask."""


class QueryPlanner:
    def __init__(self, llm: Optional[NvidiaLLMService] = None, cache: Optional[Dict[str, Dict[str, Any]]] = None):
        self._llm = llm
        self._cache: Dict[str, Dict[str, Any]] = cache if cache is not None else {}

    @property
    def llm(self) -> NvidiaLLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    @staticmethod
    def _cache_key(query: str) -> str:
        return hashlib.sha1(" ".join(query.lower().split()).encode()).hexdigest()

    def simple_plan(self, query: str, decision: RouteDecision) -> QueryPlan:
        intent = decision.intent if decision.intent in (Intent.KNOWLEDGE, Intent.HYBRID, Intent.DATA) else Intent.KNOWLEDGE
        return QueryPlan(
            intent=intent,
            query_type=decision.query_type,  # type: ignore[arg-type]
            steps=[PlanStep(id="s1", tool="knowledge.retrieve", goal=query, keywords=decision.keywords)],
            synthesis_strategy="summary",
            max_tool_calls=settings.max_tool_calls,
            reasoning="direct retrieval",
        )

    async def plan(
        self,
        query: str,
        decision: RouteDecision,
        backend_plans_itself: bool = False,
        usage: Optional[LLMUsage] = None,
        use_llm: bool = True,
    ) -> QueryPlan:
        if decision.intent == Intent.CHAT:
            return QueryPlan(intent=Intent.CHAT, query_type="chat", steps=[PlanStep(id="s1", tool="chat.respond", goal=query)],
                             synthesis_strategy="direct", reasoning="conversational")
        if decision.intent in (Intent.ACTION, Intent.CLARIFICATION):
            return QueryPlan(intent=decision.intent, query_type=decision.query_type, steps=[],  # type: ignore[arg-type]
                             needs_clarification=decision.intent == Intent.CLARIFICATION,
                             clarification_question="Could you add a bit more detail about what you are looking for?"
                             if decision.intent == Intent.CLARIFICATION else None, reasoning=decision.reason)

        if not decision.complex or backend_plans_itself or not use_llm:
            return self.simple_plan(query, decision)

        key = self._cache_key(query)
        if key in self._cache:
            plan = QueryPlan(**self._cache[key])
            plan.cached = True
            return plan

        max_steps = min(settings.max_sub_queries, settings.max_tool_calls)
        try:
            data = await self.llm.generate_json(
                f"Question: {query}",
                system_prompt=PLANNER_SYSTEM.replace("{max_steps}", str(max_steps)),
                max_tokens=600, fast=True, usage=usage,
            )
            subs: List[str] = [s.strip() for s in data.get("sub_questions", []) if isinstance(s, str) and s.strip()]
            alts: List[str] = [s.strip() for s in data.get("alternate_phrasings", []) if isinstance(s, str) and s.strip()]
            if not subs:
                subs = [query]
            subs = subs[:max_steps]
            steps = [PlanStep(id=f"s{i + 1}", tool="knowledge.retrieve", goal=sq, keywords=decision.keywords) for i, sq in enumerate(subs)]
            # Alternate phrasings of the original question are fused into the first step (multi-query).
            if alts and settings.multi_query_enabled:
                steps[0].alternate_queries = alts[:2]
            strategy = data.get("synthesis_strategy") or "summary"
            if strategy not in ("summary", "comparison_table", "timeline", "bullet_analysis"):
                strategy = "summary"
            plan = QueryPlan(
                intent=Intent.KNOWLEDGE,
                query_type=decision.query_type,  # type: ignore[arg-type]
                steps=steps,
                synthesis_strategy=strategy,  # type: ignore[arg-type]
                max_tool_calls=settings.max_tool_calls,
                needs_clarification=bool(data.get("needs_clarification", False)),
                clarification_question=data.get("clarification_question"),
                reasoning=str(data.get("reasoning", ""))[:300],
            )
            self._cache[key] = plan.model_dump()
            return plan
        except Exception as exc:
            logger.warning("Planner failed; using direct retrieval", error=str(exc))
            return self.simple_plan(query, decision)

