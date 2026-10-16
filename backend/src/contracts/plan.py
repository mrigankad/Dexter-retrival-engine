"""Planner contract: route + bounded tool steps."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .common import Intent


ToolName = Literal["knowledge.retrieve", "data.query", "chat.respond"]


class PlanStep(BaseModel):
    id: str
    tool: ToolName = "knowledge.retrieve"
    goal: str                                  # the sub-question to answer
    keywords: List[str] = Field(default_factory=list)
    content_type: Optional[str] = None         # text | table | chart
    alternate_queries: List[str] = Field(default_factory=list)   # extra phrasings fused with the goal
    depends_on: List[str] = Field(default_factory=list)


class QueryPlan(BaseModel):
    intent: Intent = Intent.KNOWLEDGE
    query_type: Literal["lookup", "comparative", "temporal", "analytical", "aggregation", "causal", "chat"] = "lookup"
    steps: List[PlanStep] = Field(default_factory=list)
    synthesis_strategy: Literal["summary", "comparison_table", "timeline", "bullet_analysis", "direct"] = "summary"
    max_tool_calls: int = 4
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    reasoning: str = ""
    cached: bool = False

    @property
    def is_multi_hop(self) -> bool:
        return len(self.steps) > 1
