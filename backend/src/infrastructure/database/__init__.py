"""Relational persistence (PostgreSQL in production, SQLite for dev/tests)."""

from .models import (
    Base,
    User,
    ChatSession,
    ChatMessage,
    Document,
    DocumentChunk,
    Evaluation,
    Trace,
    Feedback,
)
from .session_manager import (
    get_engine,
    get_session_factory,
    get_session,
    session_scope,
    init_db,
    close_db,
)

__all__ = [
    "Base", "User", "ChatSession", "ChatMessage", "Document", "DocumentChunk", "Evaluation", "Trace", "Feedback",
    "get_engine", "get_session_factory", "get_session", "session_scope", "init_db", "close_db",
]
