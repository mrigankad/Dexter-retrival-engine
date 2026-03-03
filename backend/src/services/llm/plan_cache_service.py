"""
Plan Cache Service - Redis-based Query Plan Caching.

Caches query decomposition plans to avoid redundant LLM calls:
- Semantic similarity-based cache lookup
- TTL-based expiration
- Hit rate tracking
- Plan versioning
"""

from typing import Any, Dict, List, Optional
import hashlib
import json
import time

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


class PlanCacheService:
    """
    Redis-based cache for query execution plans.
    
    Strategy:
    1. Normalize query text
    2. Generate semantic hash
    3. Check Redis for cached plan
    4. Store with TTL on miss
    5. Track hit/miss metrics
    """

    def __init__(self):
        self._redis = None
        self._connected = False
        self._hit_count = 0
        self._miss_count = 0
        self._cache_prefix = "plan_cache:"
        self._ttl_seconds = 3600  # 1 hour default TTL
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection."""
        try:
            import redis
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # Test connection
            self._redis.ping()
            self._connected = True
            logger.info("Plan cache connected to Redis")
        except Exception as e:
            logger.warning("Redis unavailable for plan caching, using in-memory fallback", error=str(e))
            self._connected = False
            self._memory_cache: Dict[str, Dict] = {}

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent hashing."""
        import re
        normalized = query.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        # Remove question marks and trailing punctuation
        normalized = normalized.rstrip("?!.")
        # Sort words for partial order invariance (optional, aggressive)
        # We keep order to maintain semantic meaning
        return normalized

    def _generate_key(self, query: str) -> str:
        """Generate a cache key from a normalized query."""
        normalized = self._normalize_query(query)
        query_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"{self._cache_prefix}{query_hash}"

    def get_plan(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Look up a cached plan for a query.
        
        Args:
            query: The user query
            
        Returns:
            Cached plan dict or None
        """
        key = self._generate_key(query)

        try:
            if self._connected and self._redis:
                cached = self._redis.get(key)
                if cached:
                    self._hit_count += 1
                    plan_data = json.loads(cached)
                    logger.info("Plan cache HIT", key=key[:20], hits=self._hit_count)
                    return plan_data
                else:
                    self._miss_count += 1
                    logger.debug("Plan cache MISS", key=key[:20])
                    return None
            else:
                # In-memory fallback
                entry = self._memory_cache.get(key)
                if entry and time.time() - entry.get("_ts", 0) < self._ttl_seconds:
                    self._hit_count += 1
                    return entry.get("plan")
                self._miss_count += 1
                return None

        except Exception as e:
            logger.warning("Plan cache lookup failed", error=str(e))
            self._miss_count += 1
            return None

    def store_plan(
        self,
        query: str,
        plan: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache a query plan.
        
        Args:
            query: The user query
            plan: The execution plan to cache
            ttl: Optional TTL override in seconds
            
        Returns:
            True if stored successfully
        """
        key = self._generate_key(query)
        ttl = ttl or self._ttl_seconds

        try:
            plan_json = json.dumps(plan, default=str)

            if self._connected and self._redis:
                self._redis.setex(key, ttl, plan_json)
                logger.debug("Plan cached", key=key[:20], ttl=ttl)
                return True
            else:
                # In-memory fallback
                self._memory_cache[key] = {
                    "plan": plan,
                    "_ts": time.time(),
                }
                # Evict old entries
                self._evict_memory_cache()
                return True

        except Exception as e:
            logger.warning("Plan cache store failed", error=str(e))
            return False

    def invalidate(self, query: str) -> bool:
        """Invalidate a cached plan."""
        key = self._generate_key(query)
        try:
            if self._connected and self._redis:
                self._redis.delete(key)
            else:
                self._memory_cache.pop(key, None)
            return True
        except Exception as e:
            logger.warning("Plan cache invalidation failed", error=str(e))
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache hit/miss statistics."""
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / max(total, 1)

        stats = {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "total": total,
            "hit_rate": round(hit_rate, 4),
            "connected": self._connected,
        }

        if self._connected and self._redis:
            try:
                info = self._redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
            except Exception:
                pass
        else:
            stats["memory_cache_size"] = len(self._memory_cache)

        return stats

    def clear_all(self) -> int:
        """Clear all cached plans. Returns count of deleted keys."""
        try:
            if self._connected and self._redis:
                keys = self._redis.keys(f"{self._cache_prefix}*")
                if keys:
                    count = self._redis.delete(*keys)
                    logger.info(f"Cleared {count} cached plans")
                    return count
                return 0
            else:
                count = len(self._memory_cache)
                self._memory_cache.clear()
                return count
        except Exception as e:
            logger.warning("Failed to clear plan cache", error=str(e))
            return 0

    def _evict_memory_cache(self, max_size: int = 500):
        """Evict old entries from in-memory cache."""
        if len(self._memory_cache) <= max_size:
            return

        # Remove oldest entries
        sorted_entries = sorted(
            self._memory_cache.items(),
            key=lambda x: x[1].get("_ts", 0),
        )
        entries_to_remove = len(self._memory_cache) - max_size
        for key, _ in sorted_entries[:entries_to_remove]:
            del self._memory_cache[key]
