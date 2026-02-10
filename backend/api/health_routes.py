"""
Health check routes for monitoring and observability.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
import redis.asyncio as redis

from core.config import settings
from core.dependency_injection import get_redis

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str
    environment: str
    services: Dict[str, Any]


class ServiceHealth(BaseModel):
    """Individual service health status."""
    status: str
    latency_ms: float | None = None
    error: str | None = None


async def check_redis_health(redis_client: redis.Redis) -> ServiceHealth:
    """Check Redis connection health."""
    try:
        start = datetime.utcnow()
        await redis_client.ping()
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ServiceHealth(status="healthy", latency_ms=round(latency, 2))
    except Exception as e:
        return ServiceHealth(status="unhealthy", error=str(e))


async def check_postgres_health() -> ServiceHealth:
    """Check PostgreSQL connection health."""
    try:
        from db.session_manager import get_session
        async for session in get_session():
            start = datetime.utcnow()
            await session.execute("SELECT 1")
            latency = (datetime.utcnow() - start).total_seconds() * 1000
            return ServiceHealth(status="healthy", latency_ms=round(latency, 2))
    except Exception as e:
        return ServiceHealth(status="unhealthy", error=str(e))


async def check_qdrant_health() -> ServiceHealth:
    """Check Qdrant connection health."""
    try:
        from qdrant_client import QdrantClient
        start = datetime.utcnow()
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        client.get_collections()
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return ServiceHealth(status="healthy", latency_ms=round(latency, 2))
    except Exception as e:
        return ServiceHealth(status="unhealthy", error=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check(redis_client: redis.Redis = Depends(get_redis)):
    """
    Comprehensive health check endpoint.
    
    Returns status of all dependent services.
    """
    redis_health = await check_redis_health(redis_client)
    qdrant_health = await check_qdrant_health()
    
    services = {
        "redis": redis_health.model_dump(),
        "qdrant": qdrant_health.model_dump(),
    }
    
    # Determine overall status
    all_healthy = all(s.get("status") == "healthy" for s in services.values())
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0",
        environment=settings.app_env,
        services=services,
    )


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Kubernetes liveness probe - is the app running?"""
    return {"status": "alive"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(redis_client: redis.Redis = Depends(get_redis)):
    """Kubernetes readiness probe - is the app ready to serve traffic?"""
    try:
        await redis_client.ping()
        return {"status": "ready"}
    except Exception:
        return {"status": "not_ready"}, 503
