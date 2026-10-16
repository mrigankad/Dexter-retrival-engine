"""Structured-data API: connections (admin), semantic model (admin), natural-language and raw SQL queries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.core.dependency_injection import AdminUser, CurrentUser
from src.core.logger import get_logger
from src.data_gateway import DataConnection, DataQueryError, SemanticModel, SqlPolicyError, get_connection_manager, get_data_query_service
from src.data_gateway import store
from src.data_gateway.semantic import rank_tables, schema_context

router = APIRouter()
logger = get_logger(__name__)


class ConnectionIn(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_\-]{2,64}$")
    name: str
    dialect: str = "postgres"
    url: str = Field(..., description="SQLAlchemy URL or env:VAR reference")
    tenant_id: Optional[str] = None
    allowed_schemas: List[str] = Field(default_factory=list)
    allowed_tables: List[str] = Field(default_factory=list)
    denied_columns: List[str] = Field(default_factory=list)
    default_row_limit: int = Field(default=500, ge=1, le=100000)
    hard_row_limit: int = Field(default=5000, ge=1, le=1000000)
    timeout_seconds: int = Field(default=15, ge=1, le=300)
    enabled: bool = True
    description: str = ""


class NLQueryIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    connection_id: Optional[str] = None
    limit: Optional[int] = Field(default=None, ge=1, le=100000)


class SqlIn(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)
    connection_id: Optional[str] = None
    limit: Optional[int] = Field(default=None, ge=1, le=100000)


def _mask(conn: DataConnection) -> Dict[str, Any]:
    d = conn.model_dump()
    if not d["url"].startswith("env:"):
        d["url"] = "***"
    return d


@router.get("/connections")
async def list_connections(user: CurrentUser):
    return {"connections": [_mask(c) for c in get_connection_manager().list()]}


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(body: ConnectionIn, admin: AdminUser):
    conn = DataConnection(**body.model_dump())
    conn.tenant_id = conn.tenant_id or admin.tenant_id
    await store.save_connection(conn, admin.user_id)
    return _mask(conn)


@router.delete("/connections/{connection_id}")
async def delete_connection(connection_id: str, admin: AdminUser):
    if not await store.delete_connection(connection_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    return {"status": "deleted", "connection_id": connection_id}


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: str, admin: AdminUser):
    try:
        return await get_connection_manager().test(connection_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{type(exc).__name__}: {exc}")


@router.post("/connections/{connection_id}/discover")
async def discover(connection_id: str, admin: AdminUser, refresh: bool = True):
    try:
        catalog = await get_connection_manager().discover(connection_id, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return catalog.model_dump()


@router.get("/connections/{connection_id}/semantic")
async def get_semantic(connection_id: str, user: CurrentUser):
    model = get_data_query_service().semantic.get(connection_id)
    return (model or SemanticModel(connection_id=connection_id)).model_dump()


@router.put("/connections/{connection_id}/semantic")
async def put_semantic(connection_id: str, model: SemanticModel, admin: AdminUser):
    if model.connection_id != connection_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "connection_id mismatch")
    for vq in model.verified_queries:
        vq.approved_by = vq.approved_by or admin.username
    await store.save_semantic_model(model, admin.user_id)
    return model.model_dump()


@router.post("/connections/{connection_id}/semantic/suggest")
async def suggest_semantic(connection_id: str, admin: AdminUser):
    """AI-free first draft of entities from the schema (admin reviews and approves)."""
    try:
        catalog = await get_connection_manager().discover(connection_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    from src.data_gateway.models import SemanticEntity
    entities = []
    for t in catalog.tables:
        numeric = [c.name for c in t.columns if any(k in c.type.upper() for k in ("INT", "NUM", "DEC", "FLOAT", "REAL", "DOUBLE", "MONEY"))
                   and not c.primary_key and not c.foreign_key]
        dims = {c.name: c.name for c in t.columns if c.name not in numeric and not c.primary_key}
        metrics = {f"total_{c}": f"SUM({c})" for c in numeric[:5]}
        rels = {c.foreign_key.split(".")[0]: f"{t.name}.{c.name} = {c.foreign_key}" for c in t.columns if c.foreign_key}
        entities.append(SemanticEntity(name="".join(w.capitalize() for w in t.name.split("_")), source=t.qualified,
                                       description=f"Rows of {t.name}", dimensions=dims, metrics=metrics, relationships=rels, status="suggested"))
    return SemanticModel(connection_id=connection_id, entities=entities).model_dump()


@router.post("/query")
async def nl_query(body: NLQueryIn, user: CurrentUser):
    service = get_data_query_service()
    try:
        result = await service.query(body.question, connection_id=body.connection_id, limit=body.limit)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except DataQueryError as exc:
        await store.log_query(None, body.question, user.user_id, body.connection_id, error=str(exc))
        if exc.clarification:
            return {"status": "clarification", "clarification": exc.clarification}
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    await store.log_query(result, body.question, user.user_id, result.connection_id)
    return {"status": "ok", **result.model_dump(), "chart": service.chart_for(result)}


@router.post("/sql")
async def raw_sql(body: SqlIn, admin: AdminUser):
    """Run SQL through the policy engine (admins/analysts). Read-only, row-capped."""
    service = get_data_query_service()
    try:
        result = await service.run_sql(body.sql, connection_id=body.connection_id, limit=body.limit)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except SqlPolicyError as exc:
        await store.log_query(None, body.sql, admin.user_id, body.connection_id, error=str(exc))
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"SQL rejected by policy: {exc}")
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{type(exc).__name__}: {exc}")
    await store.log_query(result, body.sql, admin.user_id, result.connection_id)
    return {"status": "ok", **result.model_dump(), "chart": service.chart_for(result)}


@router.post("/validate")
async def validate_sql(body: SqlIn, user: CurrentUser):
    service = get_data_query_service()
    try:
        conn = get_connection_manager().get(body.connection_id)
        catalog = await get_connection_manager().discover(conn.id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return service.policy_for(conn, [t.qualified for t in catalog.tables]).validate(body.sql, limit=body.limit).model_dump()


@router.get("/queries")
async def query_log(user: CurrentUser, limit: int = 50):
    is_admin = (user.role or "").lower() == "admin"
    return {"queries": await store.recent_queries(limit=limit, user_id=None if is_admin else user.user_id)}


@router.get("/connections/{connection_id}/context")
async def preview_context(connection_id: str, question: str, admin: AdminUser):
    """Debug: which tables and semantics the generator would see for a question."""
    manager = get_connection_manager()
    catalog = await manager.discover(connection_id)
    model = get_data_query_service().semantic.get(connection_id)
    ranked = rank_tables(catalog, model, question)
    return {"tables": [{"table": t.qualified, "score": s} for t, s in ranked], "schema_context": schema_context([t for t, _ in ranked], model)}
