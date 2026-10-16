"""
Connector sync: list source items, detect changes, create/update/remove documents,
and enqueue ingestion with the right ACL.

ACL for a connector document = acl_for_document(owner=None, tenant, visibility, shared_groups)
plus the source principals when ``inherit_source_acl`` is on. ``visibility="source"`` uses
source principals only (fails closed to nothing visible when the source reports none).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.contracts import IngestionJob
from src.core.access import acl_for_document, column_to_groups
from src.core.config import settings
from src.core.logger import get_logger
from src.infrastructure.database import ConnectorItem, ConnectorRow, ConnectorRun, Document, session_scope

from .base import Connector, ConnectorConfig, ConnectorError, SourceItem, get_connector_class

logger = get_logger(__name__)


class SyncReport(BaseModel):
    run_id: str
    connector_id: str
    status: str = "completed"
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)
    duration_ms: float = 0.0


def config_from_row(row: ConnectorRow) -> ConnectorConfig:
    return ConnectorConfig(
        id=row.id, tenant_id=row.tenant_id, type=row.type, name=row.name, settings=dict(row.config_json or {}),
        visibility=row.visibility or "tenant", shared_groups=column_to_groups(row.shared_groups),
        inherit_source_acl=bool(row.inherit_source_acl), delete_missing=bool(row.delete_missing),
        enabled=bool(row.enabled), schedule_minutes=row.schedule_minutes, delta_cursor=row.delta_cursor,
    )


def acl_for_item(config: ConnectorConfig, item: SourceItem) -> List[str]:
    if config.visibility == "source":
        return sorted(set(item.principals)) if item.principals else ["user:nobody"]
    acl = acl_for_document(None, config.tenant_id, config.visibility, config.shared_groups)
    if config.inherit_source_acl:
        acl = sorted(set(acl) | set(item.principals))
    return acl


class ConnectorSyncService:
    def __init__(self, pipeline=None, enqueue=None):
        self._pipeline = pipeline
        self._enqueue = enqueue

    @property
    def pipeline(self):
        if self._pipeline is None:
            from src.ingestion import get_ingestion_pipeline
            self._pipeline = get_ingestion_pipeline()
        return self._pipeline

    async def enqueue(self, job: IngestionJob) -> str:
        if self._enqueue is not None:
            return await self._enqueue(job)
        from src.ingestion import enqueue_ingestion
        return await enqueue_ingestion(job)

    # ── public ─────────────────────────────────────────────────────────

    async def sync(self, connector_id: str, connector: Optional[Connector] = None, full: bool = False) -> SyncReport:
        started = datetime.now(timezone.utc)
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        async with session_scope() as db:
            row = await db.get(ConnectorRow, connector_id)
            if row is None:
                raise ConnectorError(f"Connector {connector_id} not found")
            config = config_from_row(row)
            if full:
                config.delta_cursor = None
            db.add(ConnectorRun(id=run_id, connector_id=connector_id, status="running"))
            row.last_status = "running"
        report = SyncReport(run_id=run_id, connector_id=connector_id)
        connector = connector or get_connector_class(config.type)(config)
        seen: set[str] = set()
        try:
            await self._process_items(config, connector, report, seen)
            if config.delete_missing and not config.delta_cursor:
                await self._remove_missing(config, report, seen)
            report.status = "completed" if not report.errors else "completed_with_errors"
        except Exception as exc:
            logger.exception("Connector sync failed", connector=connector_id, error=str(exc))
            report.status = "failed"
            report.errors.append(str(exc)[:500])
        finally:
            try:
                await connector.aclose()
            except Exception:
                pass
        report.duration_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1)
        async with session_scope() as db:
            run = await db.get(ConnectorRun, run_id)
            if run is not None:
                run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                run.status, run.added, run.updated, run.removed, run.skipped = report.status, report.added, report.updated, report.removed, report.skipped
                run.errors = report.errors
            row = await db.get(ConnectorRow, connector_id)
            if row is not None:
                row.last_run_at = run.finished_at if run else None
                row.last_status = report.status
                cursor = connector.new_cursor()
                if cursor and report.status != "failed":
                    row.delta_cursor = cursor
        logger.info("Connector sync finished", connector=connector_id, **report.model_dump(exclude={"errors", "connector_id", "run_id"}))
        return report

    # ── internals ──────────────────────────────────────────────────────

    async def _process_items(self, config: ConnectorConfig, connector: Connector, report: SyncReport, seen: set) -> None:
        count = 0
        async for item in connector.list_items():
            count += 1
            if count > settings.connector_max_items_per_run:
                report.errors.append("max items per run reached")
                break
            if item.metadata.get("deleted"):
                await self._remove_item(config, item.external_id, report)
                continue
            seen.add(item.external_id)
            if not item.supported():
                report.skipped += 1
                continue
            try:
                await self._upsert_item(config, connector, item, report)
            except Exception as exc:
                logger.warning("Connector item failed", connector=config.id, item=item.external_id, error=str(exc))
                report.errors.append(f"{item.external_id}: {str(exc)[:200]}")

    async def _upsert_item(self, config: ConnectorConfig, connector: Connector, item: SourceItem, report: SyncReport) -> None:
        acl = acl_for_item(config, item)
        async with session_scope() as db:
            existing = await db.scalar(select(ConnectorItem).where(ConnectorItem.connector_id == config.id,
                                                                   ConnectorItem.external_id == item.external_id))
            unchanged = existing is not None and existing.version_key == item.version_key and (existing.principals or []) == acl
            if unchanged:
                existing.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
                report.skipped += 1
                return
        content = await connector.fetch(item)
        if not content:
            report.skipped += 1
            return
        content_hash = hashlib.sha256(content).hexdigest()
        async with session_scope() as db:
            existing = await db.scalar(select(ConnectorItem).where(ConnectorItem.connector_id == config.id,
                                                                   ConnectorItem.external_id == item.external_id))
            doc: Optional[Document] = None
            if existing is not None and existing.document_id is not None:
                doc = await db.get(Document, existing.document_id)
            is_new = doc is None
            if doc is None:
                doc = Document(id=uuid.uuid4(), filename=item.title, file_type=item.file_type, file_size=len(content), status="pending")
                db.add(doc)
            else:
                await self.pipeline.delete_document(str(doc.id))
            doc.filename, doc.file_type, doc.file_size, doc.status = item.title, item.file_type, len(content), "pending"
            doc.tenant_id = config.tenant_id
            doc.visibility = "private" if config.visibility == "source" else config.visibility
            doc.shared_groups = f",{','.join(config.shared_groups)}," if config.shared_groups else ""
            doc.source_connector_id, doc.external_id, doc.source_url, doc.content_hash = config.id, item.external_id, item.url, content_hash
            doc.doc_metadata = {**(doc.doc_metadata or {}), "connector": config.name, "connector_type": config.type,
                                "url": item.url, "source_modified": item.modified.isoformat() if item.modified else None,
                                "source_principals": item.principals, **{k: v for k, v in item.metadata.items() if isinstance(v, (str, int, float, bool))}}
            if existing is None:
                existing = ConnectorItem(connector_id=config.id, external_id=item.external_id)
                db.add(existing)
            existing.document_id = doc.id
            existing.version_key = item.version_key
            existing.principals = acl
            existing.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
            doc_id = str(doc.id)
        os.makedirs(settings.upload_dir, exist_ok=True)
        path = os.path.join(settings.upload_dir, f"{doc_id}.{item.file_type}")
        with open(path, "wb") as f:
            f.write(content)
        await self.enqueue(IngestionJob(
            document_id=doc_id, file_path=path, filename=item.title, tenant_id=config.tenant_id,
            visibility=doc.visibility, acl=acl,
            metadata={"url": item.url or "", "connector": config.name, "connector_type": config.type},
        ))
        if is_new:
            report.added += 1
        else:
            report.updated += 1

    async def _remove_item(self, config: ConnectorConfig, external_id: str, report: SyncReport) -> None:
        async with session_scope() as db:
            existing = await db.scalar(select(ConnectorItem).where(ConnectorItem.connector_id == config.id,
                                                                   ConnectorItem.external_id == external_id))
            if existing is None:
                return
            doc_id = str(existing.document_id) if existing.document_id else None
            await db.delete(existing)
            if doc_id:
                doc = await db.get(Document, uuid.UUID(doc_id))
                if doc is not None:
                    await db.delete(doc)
        if doc_id:
            try:
                await self.pipeline.delete_document(doc_id)
            except Exception as exc:
                logger.warning("Vector cleanup failed", document_id=doc_id, error=str(exc))
            for ext in settings.allowed_extensions_list:
                p = os.path.join(settings.upload_dir, f"{doc_id}.{ext}")
                if os.path.exists(p):
                    os.remove(p)
        report.removed += 1

    async def _remove_missing(self, config: ConnectorConfig, report: SyncReport, seen: set) -> None:
        async with session_scope() as db:
            rows = (await db.execute(select(ConnectorItem.external_id).where(ConnectorItem.connector_id == config.id))).scalars().all()
        for external_id in rows:
            if external_id not in seen:
                await self._remove_item(config, external_id, report)


async def test_connector(config: ConnectorConfig) -> Dict[str, Any]:
    connector = get_connector_class(config.type)(config)
    try:
        return await connector.test_connection()
    finally:
        await connector.aclose()
