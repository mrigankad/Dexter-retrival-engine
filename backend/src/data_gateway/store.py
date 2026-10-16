"""Persistence for data connections and semantic models; loads them into the in-memory manager."""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select

from src.core.logger import get_logger
from src.infrastructure.database import DataConnectionRow, DataQueryLog, SemanticModelRow, session_scope

from .connections import get_connection_manager
from .models import DataConnection, QueryResult, SemanticModel
from .service import get_data_query_service

logger = get_logger(__name__)


async def load_from_db() -> int:
    """Register every enabled stored connection and its semantic model."""
    manager = get_connection_manager()
    service = get_data_query_service()
    count = 0
    async with session_scope() as db:
        rows = (await db.execute(select(DataConnectionRow))).scalars().all()
        for row in rows:
            try:
                conn = DataConnection(**row.config_json)
                conn.enabled = bool(row.enabled)
                manager.register(conn)
                count += 1
            except Exception as exc:
                logger.warning("Invalid stored data connection", id=row.id, error=str(exc))
        models = (await db.execute(select(SemanticModelRow))).scalars().all()
        for m in models:
            try:
                service.semantic.set(SemanticModel(**m.model_json))
            except Exception as exc:
                logger.warning("Invalid stored semantic model", connection=m.connection_id, error=str(exc))
    return count


async def save_connection(conn: DataConnection, user_id: Optional[str]) -> None:
    async with session_scope() as db:
        row = await db.get(DataConnectionRow, conn.id)
        if row is None:
            row = DataConnectionRow(id=conn.id, created_by=user_id)
            db.add(row)
        row.tenant_id = conn.tenant_id
        row.config_json = conn.model_dump()
        row.enabled = conn.enabled
    get_connection_manager().register(conn)


async def delete_connection(connection_id: str) -> bool:
    async with session_scope() as db:
        row = await db.get(DataConnectionRow, connection_id)
        if row is None:
            return False
        await db.delete(row)
        model = await db.get(SemanticModelRow, connection_id)
        if model is not None:
            await db.delete(model)
    get_connection_manager().remove(connection_id)
    return True


async def save_semantic_model(model: SemanticModel, user_id: Optional[str]) -> None:
    async with session_scope() as db:
        row = await db.get(SemanticModelRow, model.connection_id)
        if row is None:
            row = SemanticModelRow(connection_id=model.connection_id)
            db.add(row)
        row.model_json = model.model_dump()
        row.updated_by = user_id
    get_data_query_service().semantic.set(model)


async def log_query(result: Optional[QueryResult], question: str, user_id: Optional[str], connection_id: Optional[str],
                    error: Optional[str] = None) -> None:
    try:
        async with session_scope() as db:
            db.add(DataQueryLog(
                id=result.query_id if result else f"q_{uuid.uuid4().hex[:10]}", connection_id=result.connection_id if result else connection_id,
                user_id=user_id, question=question, sql=result.sql if result else None, status="ok" if result else "error",
                row_count=result.row_count if result else 0, latency_ms=result.latency_ms if result else 0.0,
                source=result.source if result else "generated", error=error,
            ))
    except Exception as exc:  # never break answering because of logging
        logger.debug("Query log failed", error=str(exc))


async def recent_queries(limit: int = 50, user_id: Optional[str] = None) -> List[dict]:
    from sqlalchemy import desc
    async with session_scope() as db:
        q = select(DataQueryLog).order_by(desc(DataQueryLog.created_at)).limit(limit)
        if user_id:
            q = q.where(DataQueryLog.user_id == user_id)
        rows = (await db.execute(q)).scalars().all()
    return [{"query_id": r.id, "connection_id": r.connection_id, "user_id": r.user_id, "question": r.question, "sql": r.sql,
             "status": r.status, "row_count": r.row_count, "latency_ms": r.latency_ms, "source": r.source, "error": r.error,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
