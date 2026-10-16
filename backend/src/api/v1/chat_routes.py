"""
Chat endpoints.

POST /chat            – SSE stream (default) or JSON answer
GET  /chat/sessions   – list sessions
GET  /chat/history/{session_id}
DELETE /chat/history/{session_id}
POST /chat/feedback
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.contracts import Answer, ErrorEvent, RetrievalFilters, StreamEvent
from src.core.config import settings
from src.core.dependency_injection import ChatUser, RateLimited
from src.core.logger import get_logger
from src.infrastructure.database import Feedback, session_scope
from src.orchestrator import get_engine
from src.services.chat_memory import get_chat_memory

router = APIRouter()
logger = get_logger(__name__)


class ChatMessageIn(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    chat_history: Optional[List[ChatMessageIn]] = Field(default=None, description="Overrides stored history when given")
    stream: bool = True
    use_rag: bool = True
    document_ids: Optional[List[str]] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    reasoning_effort: str = Field(default="low", pattern="^(minimal|low|medium)$")
    backend: Optional[str] = Field(default=None, description="Override KNOWLEDGE_BACKEND for this request")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    sources: List[dict] = []
    evidence: List[dict] = []
    citations: List[dict] = []
    usage: dict = {}
    route: str = "rag_pipeline"
    intent: str = "KNOWLEDGE"
    confidence: str = "medium"
    answer_id: Optional[str] = None
    trace_id: Optional[str] = None
    latency_ms: float = 0.0
    warnings: List[str] = []


class FeedbackRequest(BaseModel):
    trace_id: Optional[str] = None
    message_id: Optional[str] = None
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = Field(default=None, max_length=2000)


_engines: Dict[str, Any] = {}


def _engine_for(backend: Optional[str]):
    """Engine bound to a non-default backend (cached per backend name)."""
    if backend and backend != settings.knowledge_backend:
        if backend not in _engines:
            from src.knowledge import get_knowledge_adapter
            from src.orchestrator.engine import RetrievalEngine
            from src.services.traces import persist_trace
            _engines[backend] = RetrievalEngine(adapter=get_knowledge_adapter(backend), trace_sink=persist_trace)
        return _engines[backend]
    return get_engine()


def reset_engine_cache() -> None:
    _engines.clear()


async def _has_documents() -> bool:
    if settings.knowledge_backend != "local":
        return True
    try:
        from src.infrastructure.vector_store import get_qdrant_store
        return (await get_qdrant_store().count()) > 0
    except Exception:
        return True


async def _run(request: ChatRequest, user, session_id: str) -> AsyncGenerator[StreamEvent, None]:
    memory = get_chat_memory()
    user_id = user.user_id if user else None
    history: List[Dict[str, str]]
    if request.chat_history is not None:
        history = [{"role": m.role, "content": m.content} for m in request.chat_history]
    else:
        history = await memory.get_context_messages(session_id, limit=10)
    await memory.add_message(session_id, "user", request.query, user_id)

    filters = RetrievalFilters(document_ids=request.document_ids or None)
    engine = _engine_for(request.backend)
    engine.last_answer = None
    yield StreamEvent(event="start", data=session_id)
    async for event in engine.answer_stream(
        request.query, session_id=session_id, user_id=user_id, chat_history=history, filters=filters,
        use_rag=request.use_rag, top_k=request.top_k, reasoning_effort=request.reasoning_effort,
        has_documents=await _has_documents(),
    ):
        yield event
    answer: Optional[Answer] = getattr(engine, "last_answer", None)
    if answer is not None:
        message_id = await memory.add_message(
            session_id, "assistant", answer.text, user_id,
            metadata={"sources": [e.to_legacy_source() for e in answer.evidence], "trace_id": answer.trace_id,
                      "intent": answer.intent.value, "confidence": answer.confidence.value,
                      "citations": [c.model_dump() for c in answer.citations], "answer_id": answer.answer_id},
        )
        yield StreamEvent(event="metadata", data={"message_id": message_id, "session_id": session_id,
                                                  "route": answer.route, "trace_id": answer.trace_id,
                                                  "intent": answer.intent.value, "confidence": answer.confidence.value})


async def _sse(request: ChatRequest, user, session_id: str) -> AsyncGenerator[str, None]:
    try:
        async for event in _run(request, user, session_id):
            yield event.to_sse()
    except Exception as exc:
        logger.exception("Streaming failure", error=str(exc))
        yield ErrorEvent(message=str(exc)).to_stream().to_sse()


@router.post("")
async def chat(request: ChatRequest, http_request: Request, user: ChatUser, _: RateLimited = None):
    session_id = request.session_id or f"session_{uuid.uuid4().hex[:16]}"
    logger.info("Chat request", session_id=session_id, stream=request.stream, use_rag=request.use_rag,
                user_id=user.user_id if user else "anonymous", query_len=len(request.query))
    if request.stream:
        return StreamingResponse(
            _sse(request, user, session_id), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
                     "X-Session-ID": session_id},
        )
    final: Optional[Answer] = None
    error: Optional[str] = None
    engine = _engine_for(request.backend)
    async for event in _run(request, user, session_id):
        if event.event == "error":
            error = str(event.data)
    final = getattr(engine, "last_answer", None)
    if final is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, error or "No answer produced")
    return ChatResponse(
        response=final.text, session_id=session_id, sources=[e.to_legacy_source() for e in final.evidence],
        evidence=[e.model_dump() for e in final.evidence], citations=[c.model_dump() for c in final.citations],
        usage=final.usage, route=final.route, intent=final.intent.value, confidence=final.confidence.value,
        answer_id=final.answer_id, trace_id=final.trace_id, latency_ms=final.latency_ms, warnings=final.warnings,
    )


@router.get("/sessions")
async def list_sessions(user: ChatUser, limit: int = 50):
    return {"sessions": await get_chat_memory().list_sessions(user.user_id if user else None, limit=limit)}


@router.get("/history/{session_id}")
async def get_history(session_id: str, user: ChatUser, limit: int = 100):
    return {"session_id": session_id, "messages": await get_chat_memory().get_history(session_id, limit=limit)}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str, user: ChatUser):
    await get_chat_memory().clear(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def feedback(request: FeedbackRequest, user: ChatUser):
    async with session_scope() as db:
        row = Feedback(trace_id=request.trace_id, message_id=request.message_id,
                       user_id=user.user_id if user else None, rating=request.rating, comment=request.comment)
        db.add(row)
        await db.flush()
        fid = str(row.id)
    return {"status": "recorded", "feedback_id": fid}
