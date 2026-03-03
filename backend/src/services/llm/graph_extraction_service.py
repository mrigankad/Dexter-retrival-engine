"""
Graph Extraction Service - Extracts entities and relationships using LLM.
"""

import json
import re
from typing import List, Dict, Any, Tuple
from src.core.logger import get_logger

logger = get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an expert Knowledge Graph architect.
Your task is to extract high-quality knowledge triplets (Subject, Relationship, Object) from the provided text.

RULES:
1. Extract ALL unique entities (Companies, Dates, Targets, Metrics, Locations, Technologies).
2. Relationships should be concise (e.g., "OPERATES_IN", "TARGETS", "REPORTS", "REDUCED_BY").
3. Return ONLY a JSON list of triplets: [{"subject": "...", "relation": "...", "object": "..."}]
4. Do not include any preamble or explanation.
5. Focus on facts, especially financial and sustainability metrics.

Example:
Input: "JSW Steel targets 42% CO2 reduction by 2030."
Output: [{"subject": "JSW Steel", "relation": "TARGETS", "object": "42% CO2 reduction"}, {"subject": "JSW Steel", "relation": "HAS_DEADLINE", "object": "2030"}]
"""

class GraphExtractionService:
    """Service to extract triplets from text using LLM."""

    def __init__(self, llm_service):
        self.llm = llm_service

    async def extract_triplets(self, text: str) -> List[Dict[str, str]]:
        """Extract triplets from a text chunk."""
        if not text or len(text) < 50:
            return []

        try:
            response = await self.llm.generate(
                prompt=f"Extract knowledge triplets from the following text:\n\n{text}",
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                max_tokens=1024,
                temperature=0.1  # Low temperature for consistency
            )

            # Cleanup response to find JSON list
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                triplets = json.loads(json_match.group(0))
                return triplets
            else:
                logger.warning("No JSON triplets found in LLM response")
                return []
        except Exception as e:
            logger.error("Error extracting triplets with LLM", error=str(e))
            return []
