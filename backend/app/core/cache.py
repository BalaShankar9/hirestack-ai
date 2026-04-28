"""HireStack AI — Cache module.

Lazy-initialised Redis client with TTL-based caching for read-heavy endpoints.
Falls back to a bounded in-memory LRU when Redis is unavailable.

Public surface (re-exported from app.core.database for back-compat):
  - get_redis()
  - cache_get(key)
  - cache_set(key, value, ttl=None)
  - cache_invalidate(*keys)
  - cache_invalidate_prefix(prefix)
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from collections import OrderedDict
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("hirestack.cache")


_redis_client = None
_redis_init_attempted = False


def get_redis():
    """Lazy-init Redis connection. Returns None if Redis unavailable."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True
    redis_url = settings.redis_url
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        logger.info("Redis cache connected", extra={"url": redis_url.split("@")[-1]})
    except Exception as exc:
        logger.warning(
            "Redis unavailable, using in-memory fallback",
            extra={"error": str(exc)[:200]},
        )
        _redis_client = None
    return _redis_client


# In-memory fallback cache (bounded LRU).
_MEM_CACHE: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
_MEM_CACHE_MAX = 512


def _mem_cache_get(key: str) -> Optional[str]:
    entry = _MEM_CACHE.get(key)
    if entry is None:
        return None
    val, expires = entry
    if _time.time() >= expires:
        _MEM_CACHE.pop(key, None)
        return None
    _MEM_CACHE.move_to_end(key)
    return val


def _mem_cache_set(key: str, val: str, ttl: int) -> None:
    _MEM_CACHE[key] = (val, _time.time() + ttl)
    _MEM_CACHE.move_to_end(key)
    while len(_MEM_CACHE) > _MEM_CACHE_MAX:
        _MEM_CACHE.popitem(last=False)


async def cache_get(key: str) -> Optional[Any]:
    """Read from Redis cache (or in-memory fallback)."""
    r = get_redis()
    if r is not None:
        try:
            val = await asyncio.to_thread(r.get, key)
            return _json.loads(val) if val else None
        except Exception:
            pass
    val = _mem_cache_get(key)
    return _json.loads(val) if val else None


async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Write to Redis cache (or in-memory fallback)."""
    if ttl is None:
        ttl = settings.cache_ttl_seconds
    serialized = _json.dumps(value, default=str)
    r = get_redis()
    if r is not None:
        try:
            await asyncio.to_thread(r.setex, key, ttl, serialized)
            return
        except Exception:
            pass
    _mem_cache_set(key, serialized, ttl)


async def cache_invalidate(*keys: str) -> None:
    """Delete one or more cache keys."""
    r = get_redis()
    if r is not None:
        try:
            await asyncio.to_thread(r.delete, *keys)
        except Exception:
            pass
    for k in keys:
        _MEM_CACHE.pop(k, None)


async def cache_invalidate_prefix(prefix: str) -> None:
    """Invalidate all cache keys matching a prefix (Redis SCAN + in-memory)."""
    r = get_redis()
    if r is not None:
        try:

            def _scan_and_delete():
                cursor = 0
                while True:
                    cursor, keys = r.scan(cursor, match=f"{prefix}*", count=100)
                    if keys:
                        r.delete(*keys)
                    if cursor == 0:
                        break

            await asyncio.to_thread(_scan_and_delete)
        except Exception:
            pass
    to_remove = [k for k in _MEM_CACHE if k.startswith(prefix)]
    for k in to_remove:
        _MEM_CACHE.pop(k, None)


__all__ = [
    "get_redis",
    "cache_get",
    "cache_set",
    "cache_invalidate",
    "cache_invalidate_prefix",
]
