"""Persist and read per-query traces (audit view)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select

from src.contracts import TraceRecord
from src.core.config import settings
from src.infrastructure.database import Trace, session_scope


async def persist_trace(trace: TraceRecord) -> None:
    if not settings.persist_traces:
        return
    async with session_scope() as session:
        session.add(Trace(
            id=trace.trace_id, session_id=trace.session_id, user_id=trace.user_id, tenant_id=trace.tenant_id,
            query=trace.query, intent=trace.intent.value, confidence=trace.confidence.value,
            total_latency_ms=trace.total_latency_ms, evidence_count=trace.evidence_count,
            prompt_tokens=trace.prompt_tokens, completion_tokens=trace.completion_tokens,
            trace_json=trace.model_dump(mode="json"),
        ))


async def get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    async with session_scope() as session:
        row = await session.scalar(select(Trace).where(Trace.id == trace_id))
        return row.trace_json if row else None


async def list_traces(limit: int = 50, session_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    async with session_scope() as session:
        q = select(Trace).order_by(desc(Trace.created_at)).limit(limit)
        if session_id:
            q = q.where(Trace.session_id == session_id)
        if user_id:
            q = q.where(Trace.user_id == user_id)
        rows = (await session.execute(q)).scalars().all()
        return [{
            "trace_id": r.id, "session_id": r.session_id, "user_id": r.user_id, "query": r.query, "intent": r.intent,
            "confidence": r.confidence, "total_latency_ms": r.total_latency_ms, "evidence_count": r.evidence_count,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
