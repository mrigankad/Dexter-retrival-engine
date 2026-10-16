"""Server-Sent Event contracts for the streaming chat endpoint."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StreamEvent(BaseModel):
    event: str
    data: Any

    def to_sse(self) -> str:
        payload = self.data if isinstance(self.data, str) else json.dumps(self.data, default=str)
        # SSE data must not contain bare newlines; split into multiple data: lines.
        lines = "".join(f"data: {line}\n" for line in payload.split("\n"))
        return f"event: {self.event}\n{lines}\n"


class ProgressEvent(BaseModel):
    stage: Literal[
        "understanding", "routing", "planning", "retrieving", "reranking",
        "found_sources", "synthesizing", "verifying", "finalizing",
    ]
    label: str
    detail: Optional[Dict[str, Any]] = None

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="progress", data=self.model_dump(exclude_none=True))


class EvidenceEvent(BaseModel):
    evidence: List[Dict[str, Any]]

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="evidence", data=self.evidence)


class AnswerDeltaEvent(BaseModel):
    text: str

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="answer_delta", data={"text": self.text})


class DoneEvent(BaseModel):
    answer_id: str
    confidence: str
    latency_ms: float
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="done", data=self.model_dump())


class WarningEvent(BaseModel):
    message: str

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="warning", data={"message": self.message})


class ErrorEvent(BaseModel):
    message: str
    code: str = "internal_error"

    def to_stream(self) -> StreamEvent:
        return StreamEvent(event="error", data=self.message)
