"""Database-backed chat sessions and messages."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, select

from src.infrastructure.database import ChatMessage, ChatSession, session_scope


def _uuid_or_none(value: Optional[str]) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(value) if value else None
    except (ValueError, TypeError):
        return None


class ChatMemory:
    async def ensure_session(self, session_id: str, user_id: Optional[str] = None, tenant_id: Optional[str] = None,
                             title: Optional[str] = None) -> None:
        async with session_scope() as db:
            existing = await db.get(ChatSession, session_id)
            if existing is None:
                db.add(ChatSession(id=session_id, user_id=_uuid_or_none(user_id), tenant_id=tenant_id, title=title))

    async def add_message(self, session_id: str, role: str, content: str, user_id: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> str:
        await self.ensure_session(session_id, user_id, title=content[:80] if role == "user" else None)
        message_id = uuid.uuid4()
        async with session_scope() as db:
            db.add(ChatMessage(id=message_id, session_id=session_id, role=role, content=content,
                               message_metadata=metadata or {}))
            session = await db.get(ChatSession, session_id)
            if session is not None and not session.title and role == "user":
                session.title = content[:80]
        return str(message_id)

    async def get_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with session_scope() as db:
            rows = (await db.execute(
                select(ChatMessage).where(ChatMessage.session_id == session_id)
                .order_by(desc(ChatMessage.created_at)).limit(limit)
            )).scalars().all()
        rows = list(reversed(rows))
        return [{
            "id": str(m.id), "role": m.role, "content": m.content,
            "timestamp": m.created_at.isoformat() if m.created_at else None, "metadata": m.message_metadata or {},
        } for m in rows]

    async def get_context_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        history = await self.get_history(session_id, limit=limit)
        return [{"role": m["role"], "content": m["content"]} for m in history]

    async def clear(self, session_id: str) -> None:
        async with session_scope() as db:
            await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))

    async def list_sessions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        async with session_scope() as db:
            q = select(ChatSession).order_by(desc(ChatSession.updated_at)).limit(limit)
            uid = _uuid_or_none(user_id)
            if uid is not None:
                q = q.where(ChatSession.user_id == uid)
            rows = (await db.execute(q)).scalars().all()
        return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat() if s.created_at else None,
                 "updated_at": s.updated_at.isoformat() if s.updated_at else None} for s in rows]

    def session_owner_ok(self, session: ChatSession, user_id: Optional[str]) -> bool:
        if session.user_id is None:
            return True
        return str(session.user_id) == (user_id or "")


_default: Optional[ChatMemory] = None


def get_chat_memory() -> ChatMemory:
    global _default
    if _default is None:
        _default = ChatMemory()
    return _default
