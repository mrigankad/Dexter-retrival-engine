from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter
from sqlalchemy import text

from src.core.config import settings

router = APIRouter()


async def _check_db() -> Dict[str, Any]:
    from src.infrastructure.database import session_scope
    start = datetime.now(timezone.utc)
    try:
        async with session_scope() as s:
            await s.execute(text("SELECT 1"))
        return {"status": "healthy", "latency_ms": round((datetime.now(timezone.utc) - start).total_seconds() * 1000, 2), "error": None}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)[:200]}


async def _check_redis() -> Dict[str, Any]:
    from src.infrastructure.cache import get_redis_client
    if not settings.redis_enabled:
        return {"status": "disabled", "latency_ms": None, "error": None}
    start = datetime.now(timezone.utc)
    try:
        client = get_redis_client()
        await client.ping()
        return {"status": "healthy", "latency_ms": round((datetime.now(timezone.utc) - start).total_seconds() * 1000, 2), "error": None}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)[:200]}


async def _check_knowledge() -> Dict[str, Any]:
    from src.knowledge import get_knowledge_adapter
    start = datetime.now(timezone.utc)
    try:
        info = await get_knowledge_adapter().healthcheck()
        info["latency_ms"] = round((datetime.now(timezone.utc) - start).total_seconds() * 1000, 2)
        info.setdefault("error", None)
        return info
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)[:200]}


@router.get("/health")
async def health_check():
    services = {"database": await _check_db(), "redis": await _check_redis(), "knowledge": await _check_knowledge()}
    # qdrant alias for the existing UI
    services["qdrant"] = services["knowledge"] if settings.knowledge_backend == "local" else {"status": "n/a", "latency_ms": None, "error": None}
    required = [services["database"], services["knowledge"]]
    overall = "healthy" if all(s.get("status") == "healthy" for s in required) else "degraded"
    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "environment": settings.app_env,
        "knowledge_backend": settings.knowledge_backend,
        "llm_configured": settings.has_nvidia_key,
        "services": services,
    }


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    db = await _check_db()
    return {"status": "ready" if db["status"] == "healthy" else "not_ready", "database": db}
