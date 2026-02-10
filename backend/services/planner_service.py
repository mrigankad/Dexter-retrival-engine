from typing import List, Dict, Any, Optional
import json
import re
from pydantic import BaseModel, Field

from core.config import settings
from core.logger import get_logger, log_timing
from services.nvidia_llm_service import NvidiaLLMService

logger = get_logger(__name__)

class SubQueryFilter(BaseModel):
    section_hint: Optional[str] = None
    content_type: str = "all"
    time_range: Optional[str] = None
    keywords: List[str] = []

class SubQuery(BaseModel):
    """Atomic sub-query for the execution engine."""
    id: str
    question: str
    filters: SubQueryFilter
    expected_output: str = "facts"

class QueryPlan(BaseModel):
    """Execution plan for complex queries - Production Grade Schema."""
    query_type: str = Field(description="lookup | analytical | comparative | temporal | aggregation | causal")
    entities: List[str] = []
    time_ranges: List[str] = []
    sub_queries: List[SubQuery] = []
    synthesis_strategy: str = Field(description="summary | comparison_table | timeline | bullet_analysis")
    reasoning: str = Field(description="Brief explanation of the plan")

PLANNER_SYSTEM_PROMPT = """You are the "Architect" for an Enterprise Financial RAG system. Your role is to decompose complex inquiries into a high-fidelity execution plan.

CONTEXT:
You are analyzing corporate reports (text, tables, figures). The reports contain audited financials, ESG metrics, risk management sections, and operational KPIs.

RULES:
1. DECOMPOSE: Break analytical, comparative, or causal questions into atomic blocks.
2. HYBRID FOCUS: Identify keywords (e.g., "EBITDA", "FY25", "Scope 1") for keyword filtering.
3. CONTENT TARGETING: Specify if a sub-query needs a TABLE (for numbers) or TEXT (for context).
4. TIME SENSITIVITY: Explicitly separate multi-year or multi-quarter requests into separate hops.
5. NO HALLUCINATION: If a metric is unknown, request a broad search for its definition first.

OUTPUT SCHEMA (JSON ONLY):
{
  "query_type": "lookup | analytical | comparative | temporal | aggregation | causal",
  "entities": ["list of company names, specific funds, or people"],
  "time_ranges": ["e.g., FY 2023-24", "Q3 FY25"],
  "sub_queries": [
    {
      "id": "sq_1",
      "question": "Specific atomic question",
      "filters": {
        "section_hint": "e.g., Financial Highlights",
        "content_type": "text | table | image",
        "time_range": "Target period",
        "keywords": ["key", "words"]
      },
      "expected_output": "facts | numbers | explanation"
    }
  ],
  "synthesis_strategy": "summary | comparison_table | timeline | bullet_analysis",
  "reasoning": "..."
}
"""

class PlannerService:
    """Production Grade Planner Service."""
    
    def __init__(self, llm_service: Optional[NvidiaLLMService] = None):
        self.llm = llm_service or NvidiaLLMService()
        
    def is_complex(self, query: str) -> bool:
        """Heuristic to check if query needs planning."""
        query_lower = query.lower()
        complex_keywords = [
            'compare', 'trend', 'across', 'impact', 'drivers', 'change', 'why', 
            'root cause', 'versus', 'vs', 'difference', 'increase', 'decrease', 
            'growth', 'decline', 'metrics', 'kpi', 'analyze', 'relationship', 
            'explain', 'correlation', 'breakdown'
        ]
        if any(keyword in query_lower for keyword in complex_keywords):
            return True
        if len(query.split()) > 15:
            return True
        return False

    @log_timing("plan_query")
    async def plan_query(self, query: str) -> QueryPlan:
        """Decompose query into a QueryPlan using LLM."""
        if not self.is_complex(query):
            return QueryPlan(
                query_type="lookup",
                sub_queries=[SubQuery(
                    id="sq1", 
                    question=query, 
                    filters=SubQueryFilter(content_type="all"),
                    expected_output="facts"
                )],
                synthesis_strategy="summary",
                reasoning="Direct lookup query."
            )
            
        prompt = f"Analyze and decompose: {query}\n\nResponse format: JSON."
        
        try:
            response_text = await self.llm.generate(
                prompt=prompt,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1500
            )
            
            # Extract JSON
            json_str = response_text
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            
            plan_dict = json.loads(json_str)
            return QueryPlan(**plan_dict)
            
        except Exception as e:
            logger.error("Planner failed", error=str(e))
            return QueryPlan(
                query_type="lookup",
                sub_queries=[SubQuery(
                    id="sq1", 
                    question=query, 
                    filters=SubQueryFilter(content_type="all")
                )],
                synthesis_strategy="summary",
                reasoning="Fallback due to planner error."
            )
