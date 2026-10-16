"""
Intent router: deterministic rules first, cheap LLM only for the ambiguous middle.

Routes: CHAT (no retrieval), KNOWLEDGE (documents), DATA/HYBRID (reserved for a
structured-data gateway; today they resolve to KNOWLEDGE with a warning),
ACTION (blocked), CLARIFICATION.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts import Intent
from src.core.logger import get_logger
from src.services.llm.nvidia_llm_service import LLMUsage, NvidiaLLMService, get_llm_service

logger = get_logger(__name__)


@dataclass
class RouteDecision:
    intent: Intent
    confidence: float
    reason: str
    query_type: str = "lookup"          # lookup | comparative | temporal | analytical | aggregation | causal | chat
    complex: bool = False               # worth planning / decomposition
    keywords: List[str] = field(default_factory=list)
    method: str = "rules"


_GREETING = re.compile(r"^\s*(hi|hello|hey|thanks?|thank you|good (morning|afternoon|evening)|ok|okay|bye)\b(\s+(there|bodham|again|you|a lot|very much|so much))?[\s!.?]*$", re.I)
_SMALLTALK = re.compile(r"\b(who are you|what can you do|your name|how are you|help me|what is this)\b", re.I)
_ACTION = re.compile(r"^\s*(please\s+)?(send|email|forward|schedule|book|delete|remove|update|edit|create a ticket|approve|pay|purchase|order|post|publish)\b", re.I)
_DATA = re.compile(r"\b(revenue|sales|orders?|customers?|invoices?|kpis?|units sold|headcount|churn|margin|"
                   r"last (month|quarter|week|year)|this (month|quarter|year|week)|yesterday|year to date|ytd|"
                   r"sum of|count of|total of|average|top \d+|how many|how much|by (region|month|quarter|customer|product|plant))\b", re.I)
_PLOT = re.compile(r"\b(plot|chart|graph|visuali[sz]e|trend of)\b", re.I)
_EXPLAIN = re.compile(r"\b(why|explain|reason|cause|what drove|drivers?)\b", re.I)
_DOC_HINT = re.compile(r"\b(document|file|report|policy|contract|pdf|section|page|according to|uploaded|manual|guideline|spec)\b", re.I)

_COMPARATIVE = re.compile(r"\b(compare|comparison|versus|vs\.?|differ|difference|better|worse|against)\b", re.I)
_TEMPORAL = re.compile(r"\b(trend|over time|year[- ]on[- ]year|yoy|quarter|growth|decline|history|timeline|change[sd]? (since|from|over))\b", re.I)
_CAUSAL = re.compile(r"\b(why|cause|reason|because|impact|effect|driver|led to|result of)\b", re.I)
_AGGREGATION = re.compile(r"\b(summar|overview|all|list (all|every)|total|across|breakdown|key points|main points)\b", re.I)
_ANALYTICAL = re.compile(r"\b(analy[sz]e|assess|evaluate|implication|risk|opportunit|recommend|strateg)\b", re.I)

_STOP = set("""a an and are as at be by for from has have how in is it its of on or that the to was what when where which who why will with
about into than then this these those can could should would do does did me my our your their please tell show give find explain""".split())


def extract_keywords(query: str, limit: int = 12) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-\.']{1,}|\d+(?:[.,]\d+)*%?", query)
    out: List[str] = []
    for w in words:
        lw = w.lower().strip(".,'")
        if lw in _STOP or len(lw) < 2 or lw in out:
            continue
        out.append(lw)
    return out[:limit]


def classify_query_type(query: str) -> str:
    q = query.strip()
    if _COMPARATIVE.search(q):
        return "comparative"
    if _CAUSAL.search(q):
        return "causal"
    if _TEMPORAL.search(q):
        return "temporal"
    if _ANALYTICAL.search(q):
        return "analytical"
    if _AGGREGATION.search(q):
        return "aggregation"
    return "lookup"


ROUTER_PROMPT = """Classify the user's message for a retrieval assistant that answers from uploaded documents.
Return ONLY JSON: {"intent": "CHAT" | "KNOWLEDGE" | "DATA" | "HYBRID" | "ACTION" | "CLARIFICATION", "confidence": 0-1, "reason": "..."}

- CHAT: greetings, small talk, questions about the assistant itself, or general knowledge that needs no documents.
- KNOWLEDGE: anything that should be answered from the user's documents or knowledge base (default when unsure).
- DATA: a measurable business question answered from the live database (sums, counts, trends, top-N).
- HYBRID: needs both live numbers and document explanation.
- ACTION: asks to perform a side effect (send, delete, schedule, buy).
- CLARIFICATION: too ambiguous to search (e.g. a single word with no context).

Message: {query}"""


class QueryRouter:
    def __init__(self, llm: Optional[NvidiaLLMService] = None, use_llm: bool = True):
        self._llm = llm
        self.use_llm = use_llm

    @property
    def llm(self) -> NvidiaLLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    def route_rules(self, query: str, has_documents: bool = True, data_available: bool = False) -> Optional[RouteDecision]:
        q = query.strip()
        qt = classify_query_type(q)
        keywords = extract_keywords(q)
        word_count = len(q.split())
        if not q:
            return RouteDecision(Intent.CLARIFICATION, 1.0, "empty query", "chat")
        if _GREETING.match(q) or (_SMALLTALK.search(q) and word_count <= 8):
            return RouteDecision(Intent.CHAT, 0.95, "greeting / small talk", "chat", keywords=keywords)
        if _ACTION.match(q):
            return RouteDecision(Intent.ACTION, 0.8, "imperative request for a side effect", qt, keywords=keywords)
        if word_count == 1 and not _DOC_HINT.search(q) and len(q) < 4:
            return RouteDecision(Intent.CLARIFICATION, 0.7, "single short token", "lookup", keywords=keywords)
        complex_ = qt != "lookup" or word_count > 18 or _AGGREGATION.search(q) is not None
        if data_available and _DATA.search(q):
            doc_like = _DOC_HINT.search(q) is not None
            explain = _EXPLAIN.search(q) is not None
            if doc_like or explain:
                return RouteDecision(Intent.HYBRID, 0.75, "numbers from data plus explanation from documents", qt, True, keywords)
            return RouteDecision(Intent.DATA, 0.8, "measurable business question", "aggregation" if _AGGREGATION.search(q) else qt,
                                 _PLOT.search(q) is not None, keywords)
        if _DOC_HINT.search(q) or q.endswith("?") or word_count >= 4:
            return RouteDecision(Intent.KNOWLEDGE, 0.85 if _DOC_HINT.search(q) else 0.7, "document-style question", qt, complex_, keywords)
        return None  # ambiguous → LLM

    async def route(self, query: str, has_documents: bool = True, usage: Optional[LLMUsage] = None,
                    data_available: bool = False) -> RouteDecision:
        decision = self.route_rules(query, has_documents, data_available)
        if decision is not None and (decision.confidence >= 0.7 or not self.use_llm):
            return decision
        if not self.use_llm:
            return decision or RouteDecision(Intent.KNOWLEDGE, 0.5, "default", classify_query_type(query), keywords=extract_keywords(query))
        try:
            data = await self.llm.generate_json(ROUTER_PROMPT.format(query=query), max_tokens=120, fast=True, usage=usage)
            intent = Intent(str(data.get("intent", "KNOWLEDGE")).upper())
            qt = classify_query_type(query)
            return RouteDecision(intent, float(data.get("confidence", 0.6)), str(data.get("reason", "")), qt,
                                 complex=qt != "lookup", keywords=extract_keywords(query), method="llm")
        except Exception as exc:
            logger.warning("LLM routing failed; defaulting to KNOWLEDGE", error=str(exc))
            return decision or RouteDecision(Intent.KNOWLEDGE, 0.5, "router fallback", classify_query_type(query),
                                             keywords=extract_keywords(query), method="fallback")
