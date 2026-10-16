from __future__ import annotations

from typing import Optional

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

_client = None
_checked = False
_available = False


def get_redis_client():
    """Return a shared redis.asyncio client, or None when Redis is disabled."""
    global _client
    if not settings.redis_enabled:
        return None
    if _client is None:
        import redis.asyncio as redis
        _client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True,
                                 socket_connect_timeout=2, socket_timeout=5)
    return _client


async def redis_available() -> bool:
    """Ping once and cache the answer for the process lifetime."""
    global _checked, _available
    if _checked:
        return _available
    client = get_redis_client()
    if client is None:
        _checked, _available = True, False
        return False
    try:
        await client.ping()
        _available = True
    except Exception as exc:
        logger.warning("Redis unavailable; falling back to in-process mode", error=str(exc))
        _available = False
    _checked = True
    return _available


async def close_redis_client() -> None:
    global _client, _checked
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
    _client = None
    _checked = False
