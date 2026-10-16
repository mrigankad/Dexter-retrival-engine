"""Async SQLAlchemy engine / session management with lazy initialisation."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = settings.effective_database_url
        kwargs = {"echo": settings.db_echo}
        if url.startswith("sqlite"):
            path = url.split("///")[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["poolclass"] = NullPool
        _engine = create_async_engine(url, **kwargs)
        logger.info("Database engine created", backend=url.split(":")[0])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False, autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for background code."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(seed_admin: bool = True) -> None:
    """Create tables and seed the default admin user."""
    from .models import Base, User
    from sqlalchemy import select

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)
    logger.info("Database tables ready")

    if seed_admin:
        from src.core.security import hash_password
        async with session_scope() as session:
            existing = await session.scalar(select(User).where(User.username == settings.default_admin_username))
            if existing is None:
                session.add(User(
                    username=settings.default_admin_username,
                    email=f"{settings.default_admin_username}@example.com",
                    password_hash=hash_password(settings.default_admin_password),
                    role="admin",
                    tenant_id=settings.default_tenant_id,
                    groups="",
                ))
                logger.info("Seeded default admin user", username=settings.default_admin_username)


def _ensure_columns(conn) -> None:
    """Lightweight forward migration: add columns introduced after a table was first created."""
    from sqlalchemy import inspect, text
    from .models import Base

    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl_type = column.type.compile(dialect=conn.dialect)
            default = ""
            if column.default is not None and getattr(column.default, "arg", None) is not None and not callable(column.default.arg):
                arg = column.default.arg
                default = f" DEFAULT {repr(arg) if isinstance(arg, str) else arg}"
            conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}{default}'))
            logger.info("Added missing column", table=table.name, column=column.name)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


async def reset_db_for_tests() -> None:
    """Drop + recreate everything (tests only)."""
    from .models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
