"""Admin API for connectors: define sources, test them, sync, inspect runs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from src.connectors import ConnectorConfig, ConnectorError, ConnectorSyncService, list_connector_types
from src.connectors.sync import config_from_row, test_connector
from src.core.access import column_to_groups, groups_to_column
from src.core.config import settings
from src.core.dependency_injection import AdminUser, DbSession
from src.core.logger import get_logger
from src.infrastructure.database import ConnectorItem, ConnectorRow, ConnectorRun

router = APIRouter()
logger = get_logger(__name__)
_background: set = set()


class ConnectorIn(BaseModel):
    type: str
    name: str = Field(..., min_length=1, max_length=255)
    settings: Dict[str, Any] = Field(default_factory=dict, description="Connector settings; secrets as env:VAR references")
    visibility: str = Field(default="tenant", pattern="^(private|tenant|public|source)$")
    shared_groups: List[str] = Field(default_factory=list)
    inherit_source_acl: bool = True
    delete_missing: bool = True
    enabled: bool = True
    schedule_minutes: Optional[int] = Field(default=None, ge=1)
    tenant_id: Optional[str] = None


class ConnectorOut(BaseModel):
    id: str
    tenant_id: Optional[str]
    type: str
    name: str
    settings: Dict[str, Any]
    visibility: str
    shared_groups: List[str]
    inherit_source_acl: bool
    delete_missing: bool
    enabled: bool
    schedule_minutes: Optional[int]
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    items: int = 0


SECRET_KEYS = {"client_secret", "access_token", "api_token", "secret_access_key", "password"}


def _mask(settings_: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in settings_.items():
        if k in SECRET_KEYS and isinstance(v, str) and not v.startswith("env:"):
            out[k] = "***"
        else:
            out[k] = v
    return out


async def _out(db, row: ConnectorRow) -> ConnectorOut:
    from sqlalchemy import func
    items = await db.scalar(select(func.count(ConnectorItem.id)).where(ConnectorItem.connector_id == row.id)) or 0
    return ConnectorOut(
        id=row.id, tenant_id=row.tenant_id, type=row.type, name=row.name, settings=_mask(row.config_json or {}),
        visibility=row.visibility or "tenant", shared_groups=column_to_groups(row.shared_groups),
        inherit_source_acl=bool(row.inherit_source_acl), delete_missing=bool(row.delete_missing), enabled=bool(row.enabled),
        schedule_minutes=row.schedule_minutes, last_run_at=row.last_run_at, last_status=row.last_status, items=int(items),
    )


@router.get("/types")
async def connector_types(admin: AdminUser):
    return {"types": list_connector_types()}


@router.get("")
async def list_connectors(admin: AdminUser, db: DbSession):
    rows = (await db.execute(select(ConnectorRow).order_by(ConnectorRow.created_at))).scalars().all()
    return {"connectors": [await _out(db, r) for r in rows]}


@router.post("", response_model=ConnectorOut, status_code=status.HTTP_201_CREATED)
async def create_connector(body: ConnectorIn, admin: AdminUser, db: DbSession):
    config = ConnectorConfig(**body.model_dump())
    try:
        from src.connectors import get_connector_class
        get_connector_class(config.type)(config)   # validates settings
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    row = ConnectorRow(
        id=f"con_{uuid.uuid4().hex[:12]}", tenant_id=body.tenant_id or admin.tenant_id or settings.default_tenant_id,
        type=body.type, name=body.name, config_json=body.settings, visibility=body.visibility,
        shared_groups=groups_to_column(body.shared_groups), inherit_source_acl=body.inherit_source_acl,
        delete_missing=body.delete_missing, enabled=body.enabled, schedule_minutes=body.schedule_minutes, created_by=admin.user_id,
    )
    db.add(row)
    await db.flush()
    return await _out(db, row)


async def _row(db, connector_id: str) -> ConnectorRow:
    row = await db.get(ConnectorRow, connector_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector not found")
    return row


@router.get("/{connector_id}", response_model=ConnectorOut)
async def get_connector(connector_id: str, admin: AdminUser, db: DbSession):
    return await _out(db, await _row(db, connector_id))


@router.put("/{connector_id}", response_model=ConnectorOut)
async def update_connector(connector_id: str, body: ConnectorIn, admin: AdminUser, db: DbSession):
    row = await _row(db, connector_id)
    row.type, row.name, row.config_json, row.visibility = body.type, body.name, body.settings, body.visibility
    row.shared_groups, row.inherit_source_acl, row.delete_missing = groups_to_column(body.shared_groups), body.inherit_source_acl, body.delete_missing
    row.enabled, row.schedule_minutes = body.enabled, body.schedule_minutes
    if body.tenant_id:
        row.tenant_id = body.tenant_id
    await db.flush()
    return await _out(db, row)


@router.delete("/{connector_id}")
async def delete_connector(connector_id: str, admin: AdminUser, db: DbSession, remove_documents: bool = True):
    row = await _row(db, connector_id)
    removed = 0
    if remove_documents:
        from src.connectors.sync import ConnectorSyncService, SyncReport
        service = ConnectorSyncService()
        report = SyncReport(run_id="delete", connector_id=connector_id)
        items = (await db.execute(select(ConnectorItem.external_id).where(ConnectorItem.connector_id == connector_id))).scalars().all()
        await db.commit()
        config = config_from_row(row)
        for ext_id in items:
            await service._remove_item(config, ext_id, report)
        removed = report.removed
        row = await _row(db, connector_id)
    await db.delete(row)
    return {"status": "deleted", "connector_id": connector_id, "documents_removed": removed}


@router.post("/{connector_id}/test")
async def test_connection(connector_id: str, admin: AdminUser, db: DbSession):
    row = await _row(db, connector_id)
    try:
        return await test_connector(config_from_row(row))
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{type(exc).__name__}: {exc}")


@router.post("/test")
async def test_unsaved(body: ConnectorIn, admin: AdminUser):
    try:
        return await test_connector(ConnectorConfig(**body.model_dump()))
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{type(exc).__name__}: {exc}")


@router.post("/{connector_id}/sync")
async def sync_connector(connector_id: str, admin: AdminUser, db: DbSession, wait: bool = True, full: bool = False):
    await _row(db, connector_id)
    await db.commit()
    service = ConnectorSyncService()
    if wait:
        report = await service.sync(connector_id, full=full)
        return report.model_dump()
    task = asyncio.create_task(service.sync(connector_id, full=full))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"status": "started", "connector_id": connector_id}


@router.get("/{connector_id}/runs")
async def runs(connector_id: str, admin: AdminUser, db: DbSession, limit: int = 20):
    await _row(db, connector_id)
    rows = (await db.execute(select(ConnectorRun).where(ConnectorRun.connector_id == connector_id)
                             .order_by(desc(ConnectorRun.started_at)).limit(limit))).scalars().all()
    return {"runs": [{
        "run_id": r.id, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
        "added": r.added, "updated": r.updated, "removed": r.removed, "skipped": r.skipped, "errors": r.errors or [],
    } for r in rows]}


@router.get("/{connector_id}/items")
async def items(connector_id: str, admin: AdminUser, db: DbSession, limit: int = 200):
    await _row(db, connector_id)
    rows = (await db.execute(select(ConnectorItem).where(ConnectorItem.connector_id == connector_id)
                             .order_by(desc(ConnectorItem.last_seen_at)).limit(limit))).scalars().all()
    return {"items": [{"external_id": r.external_id, "document_id": str(r.document_id) if r.document_id else None,
                       "version_key": r.version_key, "principals": r.principals or [], "last_seen_at": r.last_seen_at} for r in rows]}
