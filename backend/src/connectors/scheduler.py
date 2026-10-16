"""Periodic connector syncs inside the API process (single replica; use an external scheduler at scale)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from src.core.config import settings
from src.core.logger import get_logger
from src.infrastructure.database import ConnectorRow, session_scope

from .sync import ConnectorSyncService

logger = get_logger(__name__)

_task: Optional[asyncio.Task] = None
_running: set = set()


async def run_due_syncs(service: Optional[ConnectorSyncService] = None) -> int:
    service = service or ConnectorSyncService()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = []
    async with session_scope() as db:
        rows = (await db.execute(select(ConnectorRow).where(ConnectorRow.enabled.is_(True), ConnectorRow.schedule_minutes.isnot(None)))).scalars().all()
        for row in rows:
            if row.id in _running or row.last_status == "running":
                continue
            if row.last_run_at is None or row.last_run_at + timedelta(minutes=row.schedule_minutes or 0) <= now:
                due.append(row.id)
    for connector_id in due:
        _running.add(connector_id)
        try:
            await service.sync(connector_id)
        except Exception as exc:
            logger.warning("Scheduled sync failed", connector=connector_id, error=str(exc))
        finally:
            _running.discard(connector_id)
    return len(due)


async def _loop() -> None:
    while True:
        try:
            await run_due_syncs()
        except Exception as exc:  # pragma: no cover
            logger.warning("Scheduler tick failed", error=str(exc))
        await asyncio.sleep(settings.connector_scheduler_tick_seconds)


def start_scheduler() -> None:
    global _task
    if _task is None and settings.connector_scheduler_enabled:
        _task = asyncio.create_task(_loop())
        logger.info("Connector scheduler started", tick_seconds=settings.connector_scheduler_tick_seconds)


async def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
