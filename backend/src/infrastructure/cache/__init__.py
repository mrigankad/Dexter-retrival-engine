"""Optional Redis access (queue, caches, rate limiting). Everything degrades gracefully without it."""

from .redis_client import get_redis_client, close_redis_client, redis_available

__all__ = ["get_redis_client", "close_redis_client", "redis_available"]
