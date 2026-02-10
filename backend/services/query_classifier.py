"""
Query Classifier - 6-Type Query Classification Engine.

Classifies incoming queries into:
- Lookup: Simple fact-finding
- Comparative: Comparing entities/periods
- Temporal: Time-based analysis
- Analytical: Deep analysis requiring reasoning
- Aggregation: Summarizing across multiple sources
- Causal: Root cause / impact analysis

Uses hybrid approach: fast heuristic check + LLM fallback for ambiguous queries.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import re
import json

from core.config import settings
from core.logger import get_logger, log_timing

logger = get_logger(__name__)


class QueryType(str, Enum):
    """Supported query classification types."""
    LOOKUP = "lookup"
    COMPARATIVE = "comparative"
    TEMPORAL = "temporal"
    ANALYTICAL = "analytical"
    AGGREGATION = "aggregation"
    CAUSAL = "causal"


@dataclass
class QueryClassification:
    """Result of query classification."""
    query_type: QueryType
    confidence: float
    needs_planning: bool
    entities: List[str]
    time_references: List[str]
    reasoning: str
    suggested_content_types: List[str]  # text, table, chart
    suggested_synthesis: str  # summary, comparison_table, timeline, bullet_analysis

    def to_dict(self) -> Dict:
        return {
            "query_type": self.query_type.value,
            "confidence": self.confidence,
            "needs_planning": self.needs_planning,
            "entities": self.entities,
            "time_references": self.time_references,
            "reasoning": self.reasoning,
            "suggested_content_types": self.suggested_content_types,
            "suggested_synthesis": self.suggested_synthesis,
        }


# ── Classification Patterns ──────────────────────────────────

COMPARATIVE_PATTERNS = [
    r"\b(?:compare|comparison|versus|vs\.?|against|differ(?:ence|ent)?|between)\b",
    r"\b(?:better|worse|higher|lower|more|less|greater|smaller)\s+than\b",
    r"\b(?:outperform|underperform|exceed|surpass|lag behind)\b",
    r"\b(?:relative to|in contrast|as opposed to|compared with)\b",
]

TEMPORAL_PATTERNS = [
    r"\b(?:trend|over time|historically|year[- ]?on[- ]?year|yoy|growth|decline)\b",
    r"\b(?:quarter[- ]?on[- ]?quarter|qoq|month[- ]?on[- ]?month|mom)\b",
    r"\b(?:last year|previous year|next year|this quarter|last quarter)\b",
    r"\b(?:FY\s*\d{2,4}|Q[1-4]\s*(?:FY)?\s*\d{2,4}|H[12]\s*\d{2,4})\b",
    r"\b(?:from\s+\d{4}\s+to\s+\d{4}|between\s+\d{4}\s+and\s+\d{4})\b",
    r"\b(?:trajectory|progression|evolution|movement)\b",
]

ANALYTICAL_PATTERNS = [
    r"\b(?:analyze|analysis|assess|evaluate|examine|investigate|deep dive)\b",
    r"\b(?:implication|significance|insight|interpretation|perspective)\b",
    r"\b(?:strategic|critical|key drivers|contributing factors)\b",
    r"\b(?:opportunity|risk|challenge|strength|weakness|swot)\b",
    r"\b(?:performance|effectiveness|efficiency|productivity)\b",
]

AGGREGATION_PATTERNS = [
    r"\b(?:summarize|summary|overview|outline|recap|highlight)\b",
    r"\b(?:total|aggregate|overall|combined|consolidated|cumulative)\b",
    r"\b(?:all|entire|comprehensive|complete|full|across all)\b",
    r"\b(?:breakdown|segmentation|distribution|allocation)\b",
]

CAUSAL_PATTERNS = [
    r"\b(?:why|cause|reason|because|due to|result of|led to|resulted in)\b",
    r"\b(?:impact|effect|consequence|outcome|influence|drove|driven by)\b",
    r"\b(?:attribution|explain why|root cause|contributing|factor)\b",
    r"\b(?:relationship|correlation|causation|connection|linked to)\b",
]

LOOKUP_PATTERNS = [
    r"\b(?:what is|what are|what was|what were|how much|how many)\b",
    r"\b(?:tell me|show me|find|locate|give me|provide|list)\b",
    r"\b(?:define|meaning|description|explain\s+(?:what|the))\b",
]

# Time detection for entity extraction
TIME_DETECTION = re.compile(
    r"(?:FY\s*\d{2,4}(?:-\d{2,4})?|Q[1-4]\s*(?:FY)?\s*\d{2,4}|"
    r"H[12]\s*(?:FY)?\s*\d{2,4}|\b20[0-3]\d(?:-\d{2,4})?\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|"
    r"\b(?:first|second|third|fourth)\s+(?:quarter|half)\b)",
    re.IGNORECASE,
)

# Known financial entity patterns
ENTITY_PATTERNS = re.compile(
    r"\b(?:revenue|profit|margin|ebitda|ebit|eps|dps|roe|roa|roce|"
    r"capex|opex|debt|equity|asset|liability|cash flow|dividend|"
    r"sales|income|cost|expense|growth|market share|npat|pat|pbt)\b",
    re.IGNORECASE,
)


class QueryClassifier:
    """
    Hybrid query classifier: heuristic-first with LLM fallback.
    
    Flow:
    1. Pattern matching for high-confidence classification
    2. LLM-based classification for ambiguous queries
    3. Entity and time reference extraction
    4. Synthesis strategy recommendation
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service
        self._patterns = {
            QueryType.COMPARATIVE: [re.compile(p, re.IGNORECASE) for p in COMPARATIVE_PATTERNS],
            QueryType.TEMPORAL: [re.compile(p, re.IGNORECASE) for p in TEMPORAL_PATTERNS],
            QueryType.ANALYTICAL: [re.compile(p, re.IGNORECASE) for p in ANALYTICAL_PATTERNS],
            QueryType.AGGREGATION: [re.compile(p, re.IGNORECASE) for p in AGGREGATION_PATTERNS],
            QueryType.CAUSAL: [re.compile(p, re.IGNORECASE) for p in CAUSAL_PATTERNS],
            QueryType.LOOKUP: [re.compile(p, re.IGNORECASE) for p in LOOKUP_PATTERNS],
        }

    @log_timing("query_classify")
    async def classify(self, query: str) -> QueryClassification:
        """
        Classify a query into one of 6 types.
        
        Args:
            query: The user's input query
            
        Returns:
            QueryClassification with type, confidence, and metadata
        """
        # Step 1: Fast heuristic classification
        heuristic_result = self._heuristic_classify(query)

        # Step 2: If confidence is high, use heuristic result
        if heuristic_result.confidence >= 0.8:
            logger.info(
                "Query classified (heuristic)",
                query_type=heuristic_result.query_type.value,
                confidence=heuristic_result.confidence,
            )
            return heuristic_result

        # Step 3: LLM fallback for ambiguous queries
        if self.llm and heuristic_result.confidence < 0.6:
            try:
                llm_result = await self._llm_classify(query, heuristic_result)
                logger.info(
                    "Query classified (LLM)",
                    query_type=llm_result.query_type.value,
                    confidence=llm_result.confidence,
                )
                return llm_result
            except Exception as e:
                logger.warning("LLM classification failed, using heuristic", error=str(e))

        return heuristic_result

    def _heuristic_classify(self, query: str) -> QueryClassification:
        """Pattern-based classification with scoring."""
        scores: Dict[QueryType, float] = {}

        for query_type, patterns in self._patterns.items():
            score = 0.0
            for pattern in patterns:
                matches = pattern.findall(query)
                score += len(matches) * 0.2
            scores[query_type] = min(score, 1.0)

        # Boost based on query complexity
        word_count = len(query.split())
        if word_count > 20:
            for qt in [QueryType.ANALYTICAL, QueryType.COMPARATIVE, QueryType.CAUSAL]:
                scores[qt] = scores.get(qt, 0) + 0.15

        # Multiple time references boost temporal
        time_refs = TIME_DETECTION.findall(query)
        if len(time_refs) >= 2:
            scores[QueryType.TEMPORAL] = scores.get(QueryType.TEMPORAL, 0) + 0.3
            scores[QueryType.COMPARATIVE] = scores.get(QueryType.COMPARATIVE, 0) + 0.15

        # Extract entities
        entities = list(set(ENTITY_PATTERNS.findall(query)))

        # Determine winner
        if not any(v > 0 for v in scores.values()):
            best_type = QueryType.LOOKUP
            confidence = 0.5
        else:
            best_type = max(scores, key=lambda k: scores[k])
            confidence = min(scores[best_type], 0.95)

            # If scores are close, reduce confidence
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2 and sorted_scores[0] - sorted_scores[1] < 0.1:
                confidence *= 0.7

        # Determine if planning is needed
        needs_planning = best_type in {
            QueryType.COMPARATIVE,
            QueryType.TEMPORAL,
            QueryType.ANALYTICAL,
            QueryType.AGGREGATION,
            QueryType.CAUSAL,
        }

        # Suggest content types
        content_types = self._suggest_content_types(best_type, query)
        synthesis = self._suggest_synthesis(best_type)

        return QueryClassification(
            query_type=best_type,
            confidence=round(confidence, 2),
            needs_planning=needs_planning,
            entities=entities,
            time_references=time_refs,
            reasoning=f"Heuristic classification: {best_type.value} (scores: {', '.join(f'{k.value}={v:.2f}' for k, v in sorted(scores.items(), key=lambda x: -x[1])[:3])})",
            suggested_content_types=content_types,
            suggested_synthesis=synthesis,
        )

    async def _llm_classify(
        self, query: str, heuristic_hint: QueryClassification
    ) -> QueryClassification:
        """LLM-based classification for ambiguous queries."""
        prompt = f"""Classify this query into exactly ONE type. Respond with JSON only.

Query: "{query}"

Types:
- lookup: Simple fact-finding (e.g., "What is the revenue?")
- comparative: Comparing entities or periods (e.g., "How does Q1 compare to Q2?")
- temporal: Time-based analysis (e.g., "What was the revenue trend over 3 years?")
- analytical: Deep analysis requiring reasoning (e.g., "What are the key growth drivers?")
- aggregation: Summarizing across sources (e.g., "Summarize all risk factors")
- causal: Root cause / impact (e.g., "Why did profits decline?")

Heuristic hint: {heuristic_hint.query_type.value} (confidence: {heuristic_hint.confidence})

Respond ONLY with JSON:
{{"query_type": "", "confidence": 0.0, "reasoning": "", "entities": [], "content_types": ["text"]}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="You are a query classification engine. Respond only with valid JSON.",
            temperature=0.1,
            max_tokens=300,
        )

        # Parse response
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            data = json.loads(json_str)
            qt = QueryType(data.get("query_type", "lookup"))
            conf = float(data.get("confidence", 0.7))

            time_refs = TIME_DETECTION.findall(query)
            entities = data.get("entities", []) or list(set(ENTITY_PATTERNS.findall(query)))

            needs_planning = qt in {
                QueryType.COMPARATIVE, QueryType.TEMPORAL,
                QueryType.ANALYTICAL, QueryType.AGGREGATION, QueryType.CAUSAL,
            }

            return QueryClassification(
                query_type=qt,
                confidence=round(conf, 2),
                needs_planning=needs_planning,
                entities=entities,
                time_references=time_refs,
                reasoning=data.get("reasoning", "LLM classification"),
                suggested_content_types=data.get("content_types", ["text"]),
                suggested_synthesis=self._suggest_synthesis(qt),
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Failed to parse LLM classification", error=str(e))
            return heuristic_hint

    def _suggest_content_types(self, query_type: QueryType, query: str) -> List[str]:
        """Suggest which content types to prioritize in retrieval."""
        query_lower = query.lower()

        # Financial/numeric queries prefer tables
        financial_terms = ["revenue", "profit", "cost", "price", "margin", "ebitda",
                          "sales", "income", "eps", "dividend", "growth rate"]
        has_financial = any(t in query_lower for t in financial_terms)

        if query_type == QueryType.COMPARATIVE and has_financial:
            return ["table", "text"]
        elif query_type == QueryType.TEMPORAL:
            return ["table", "chart", "text"]
        elif query_type == QueryType.AGGREGATION:
            return ["text", "table"]
        elif has_financial:
            return ["table", "text"]
        elif query_type in (QueryType.ANALYTICAL, QueryType.CAUSAL):
            return ["text", "table", "chart"]
        else:
            return ["text"]

    @staticmethod
    def _suggest_synthesis(query_type: QueryType) -> str:
        """Suggest synthesis strategy based on query type."""
        mapping = {
            QueryType.LOOKUP: "summary",
            QueryType.COMPARATIVE: "comparison_table",
            QueryType.TEMPORAL: "timeline",
            QueryType.ANALYTICAL: "bullet_analysis",
            QueryType.AGGREGATION: "summary",
            QueryType.CAUSAL: "bullet_analysis",
        }
        return mapping.get(query_type, "summary")
