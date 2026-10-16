"""Final answer + trace records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import Confidence, Intent
from .evidence import Citation, Evidence
from .plan import QueryPlan


class AnswerBlock(BaseModel):
    type: Literal["markdown", "kpi", "table", "chart"] = "markdown"
    data: Dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool: str
    step_id: Optional[str] = None
    backend: Optional[str] = None
    latency_ms: float = 0.0
    status: Literal["ok", "error", "empty"] = "ok"
    input_summary: str = ""
    result_count: int = 0
    error: Optional[str] = None


class TraceRecord(BaseModel):
    trace_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    query: str
    intent: Intent
    plan: Optional[QueryPlan] = None
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    evidence_count: int = 0
    total_latency_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    confidence: Confidence = Confidence.MEDIUM
    model: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra: Dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    answer_id: str
    session_id: Optional[str] = None
    text: str
    intent: Intent
    confidence: Confidence = Confidence.MEDIUM
    blocks: List[AnswerBlock] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    latency_ms: float = 0.0
    trace_id: Optional[str] = None
    route: str = "rag_pipeline"
    usage: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
