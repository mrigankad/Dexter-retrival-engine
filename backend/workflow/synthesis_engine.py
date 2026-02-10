"""
Synthesis Engine - Final Traceable Answer Synthesis.

Generates the final response from multi-hop evidence with:
- Strategy-aware synthesis (comparison_table, timeline, bullet_analysis, summary)
- Citation enforcement
- Missing evidence declaration
- Confidence scoring
- Structured output formatting
"""

from typing import Any, Dict, List, Optional
import re
import json

from core.config import settings
from core.logger import get_logger, log_timing

logger = get_logger(__name__)


# ── Synthesis Strategy Templates ──────────────────────────────

SYNTHESIS_BASE_PROMPT = """ROLE: Principal Financial Analyst & Document Expert.
GOAL: Synthesize a final, deep-reasoning answer for the query based on provided evidence.

UNIVERSAL RULES:
1. EVERY fact must include a [Page X] citation.
2. If evidence is contradictory, state BOTH positions with their citations.
3. If evidence is MISSING for any part, explicitly state: "⚠️ Data not found in documents for: [topic]"
4. Never fabricate data. Only use what is in the evidence.
5. Be precise with numbers, units, dates, and percentages.
"""

STRATEGY_PROMPTS = {
    "summary": """SYNTHESIS STRATEGY: Comprehensive Summary
FORMAT:
- Lead with a 2-3 sentence executive summary
- Follow with detailed findings organized by topic
- End with key conclusions
- Cite [Page X] for every data point""",

    "comparison_table": """SYNTHESIS STRATEGY: Structured Comparison
FORMAT:
- Create a comparison table or side-by-side analysis
- Identify dimensions of comparison
- For each dimension, provide values for all entities
- Highlight significant differences
- End with comparative insights
- Cite [Page X] for every data point""",

    "timeline": """SYNTHESIS STRATEGY: Temporal Analysis
FORMAT:
- Organize findings chronologically
- For each time period, list key metrics/events
- Identify trends (upward/downward/stable)
- Calculate period-over-period changes where possible
- Highlight turning points
- Cite [Page X] for every data point""",

    "bullet_analysis": """SYNTHESIS STRATEGY: Deep Analytical Breakdown
FORMAT:
- Structure as numbered analytical points
- Each point should contain: Finding → Evidence → Implication
- Prioritize by significance/impact
- Include quantitative backing where available
- End with actionable insights
- Cite [Page X] for every data point""",
}


class SynthesisEngine:
    """
    Final answer synthesis engine with strategy routing.
    
    Pipeline:
    1. Select synthesis strategy based on query classification
    2. Build strategy-specific prompt
    3. Generate synthesis via LLM
    4. Post-process for citation completeness
    5. Score confidence
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service
        self._citation_pattern = re.compile(r"\[Page\s+\d+(?:/\d+)?\]", re.IGNORECASE)

    @log_timing("synthesis")
    async def synthesize(
        self,
        query: str,
        evidence_context: str,
        synthesis_strategy: str = "summary",
        plan_reasoning: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        """
        Generate a final traceable answer.
        
        Args:
            query: Original user query
            evidence_context: Assembled evidence from multi-hop executor
            synthesis_strategy: Strategy type (summary/comparison_table/timeline/bullet_analysis)
            plan_reasoning: Reasoning from the query planner
            max_tokens: Maximum response tokens
            temperature: LLM temperature
            
        Returns:
            Dict with response, citations, confidence, and metadata
        """
        if not self.llm:
            logger.error("LLM service not available for synthesis")
            return {"response": "Synthesis engine unavailable.", "confidence": 0.0}

        if not evidence_context or evidence_context.strip() == "":
            return {
                "response": "⚠️ No relevant evidence was found in the documents for this query.",
                "confidence": 0.0,
                "citations": [],
                "missing_info": [query],
            }

        # Step 1: Build strategy-aware prompt
        strategy_prompt = STRATEGY_PROMPTS.get(synthesis_strategy, STRATEGY_PROMPTS["summary"])
        system_prompt = f"{SYNTHESIS_BASE_PROMPT}\n\n{strategy_prompt}"

        user_prompt = self._build_user_prompt(
            query, evidence_context, plan_reasoning, synthesis_strategy
        )

        # Step 2: Generate synthesis
        response = await self.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Step 3: Post-process
        response = response.strip()
        citations = self._extract_citations(response)
        missing_info = self._detect_missing_info(response)
        confidence = self._score_confidence(response, evidence_context, citations)

        # Step 4: Validate citation density
        if len(citations) == 0 and "Page" not in response:
            # Response lacks citations; append a note
            response += "\n\n*Note: Source documents were used but specific page citations could not be verified.*"
            confidence *= 0.7

        result = {
            "response": response,
            "confidence": round(confidence, 2),
            "citations": citations,
            "missing_info": missing_info,
            "synthesis_strategy": synthesis_strategy,
        }

        logger.info(
            "Synthesis complete",
            strategy=synthesis_strategy,
            citations_count=len(citations),
            missing_items=len(missing_info),
            confidence=result["confidence"],
        )

        return result

    async def synthesize_stream(
        self,
        query: str,
        evidence_context: str,
        synthesis_strategy: str = "summary",
        plan_reasoning: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.4,
    ):
        """
        Streaming synthesis - yields tokens as generated.
        
        Yields:
            str tokens as they are generated
        """
        if not self.llm:
            yield "Synthesis engine unavailable."
            return

        if not evidence_context:
            yield "⚠️ No relevant evidence was found in the documents for this query."
            return

        strategy_prompt = STRATEGY_PROMPTS.get(synthesis_strategy, STRATEGY_PROMPTS["summary"])
        system_prompt = f"{SYNTHESIS_BASE_PROMPT}\n\n{strategy_prompt}"

        user_prompt = self._build_user_prompt(
            query, evidence_context, plan_reasoning, synthesis_strategy
        )

        async for token in self.llm.generate_stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield token

    # ── Internal Methods ───────────────────────────────────────

    def _build_user_prompt(
        self,
        query: str,
        evidence: str,
        reasoning: str,
        strategy: str,
    ) -> str:
        """Build the complete user prompt for synthesis."""
        parts = []

        if reasoning:
            parts.append(f"EXECUTION PLAN: {reasoning}")
        parts.append(f"SYNTHESIS STRATEGY: {strategy}")
        parts.append(f"\nAGGREGATED EVIDENCE:\n{evidence}")
        parts.append(f"\nFINAL QUESTION: {query}")
        parts.append(
            "\nREMINDER: Cite [Page X] for every fact. "
            "State explicitly if data is missing for any part of the question."
        )

        return "\n\n".join(parts)

    def _extract_citations(self, text: str) -> List[str]:
        """Extract all page citations from the response."""
        citations = self._citation_pattern.findall(text)
        return list(set(citations))

    def _detect_missing_info(self, text: str) -> List[str]:
        """Detect explicit mentions of missing information."""
        missing = []
        patterns = [
            r"(?:data not found|not found in|no (?:data|information|evidence))\s+(?:for|about|regarding)\s+(.+?)(?:\.|$)",
            r"⚠️\s*(.+?)(?:\.|$)",
            r"(?:missing|unavailable|not available)\s+(?:for|:)\s*(.+?)(?:\.|$)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            missing.extend(m.strip() for m in matches if m.strip())
        return missing

    def _score_confidence(
        self, response: str, evidence: str, citations: List[str]
    ) -> float:
        """Score synthesis confidence based on evidence quality."""
        score = 0.5  # Base score

        # Boost for citations
        if citations:
            score += min(len(citations) * 0.05, 0.25)

        # Boost for evidence density
        evidence_tokens = len(evidence) // 4
        if evidence_tokens > 500:
            score += 0.1
        if evidence_tokens > 1000:
            score += 0.05

        # Penalty for missing info
        missing_count = len(self._detect_missing_info(response))
        score -= missing_count * 0.1

        # Penalty for short response
        response_tokens = len(response) // 4
        if response_tokens < 50:
            score -= 0.15

        # Boost for numerical data (precision indicator)
        numbers = re.findall(r"\d[\d,]*(?:\.\d+)?%?", response)
        if len(numbers) > 5:
            score += 0.1

        return max(0.0, min(1.0, score))
