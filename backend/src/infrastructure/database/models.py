"""
SQLAlchemy models.

Portable across PostgreSQL and SQLite: UUIDs use the generic ``Uuid`` type and
JSON columns use the generic ``JSON`` type.
"""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid, Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), default="user")
    groups = Column(String(1024), default="")           # comma separated, e.g. ",finance,legal,"
    external_id = Column(String(128), nullable=True, index=True)   # Entra object id
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(128), primary_key=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    session_metadata = Column(JSON, default=dict)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(128), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    token_count = Column(Integer, nullable=True)
    message_metadata = Column(JSON, default=dict)   # sources, trace_id, intent, confidence ...

    session = relationship("ChatSession", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    status = Column(String(50), default="pending", index=True)  # pending | processing | completed | failed
    visibility = Column(String(16), default="tenant", index=True)   # private | tenant | public
    shared_groups = Column(String(1024), default="")                # comma separated with leading/trailing commas
    chunks_count = Column(Integer, nullable=True)
    total_pages = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    processed_at = Column(DateTime, nullable=True)
    doc_metadata = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Uuid(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    vector_id = Column(String(255), nullable=True)
    page = Column(Integer, nullable=True)
    content_type = Column(String(32), default="text")
    chunk_level = Column(String(32), default="paragraph")
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    chunk_metadata = Column(JSON, default=dict)

    document = relationship("Document", back_populates="chunks")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("chat_messages.id"), nullable=False, unique=True)
    session_id = Column(String(128), nullable=False, index=True)
    faithfulness = Column(Float, nullable=True)
    relevance = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)


class Trace(Base):
    """Per-query trace: intent, plan, tool calls, latency, cost. Powers the audit view."""
    __tablename__ = "traces"

    id = Column(String(64), primary_key=True)         # trace_id
    session_id = Column(String(128), nullable=True, index=True)
    user_id = Column(String(64), nullable=True, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    query = Column(Text, nullable=False)
    intent = Column(String(32), nullable=False)
    confidence = Column(String(16), nullable=True)
    total_latency_ms = Column(Float, default=0.0)
    evidence_count = Column(Integer, default=0)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    trace_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, index=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(String(64), nullable=True, index=True)
    message_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)
    rating = Column(Integer, nullable=True)     # -1 | 0 | 1
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)


Index("ix_document_chunks_doc_idx", DocumentChunk.document_id, DocumentChunk.chunk_index)
