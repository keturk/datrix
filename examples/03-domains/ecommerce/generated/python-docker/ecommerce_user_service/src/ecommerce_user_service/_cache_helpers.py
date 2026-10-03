"""Cache helper functions for generated Python code.

Uses redis.asyncio for async Redis operations. The Redis client is lazily
initialized from AppSettings.redis_url (assembled at lifespan startup).
No environment variables are read at any point.
"""

from __future__ import annotations

import json
import time
from typing import Callable, Optional

import redis.asyncio as aioredis

from ecommerce_user_service.config.settings import get_settings

_redis_client: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    """Get or create the Redis client from assembled AppSettings."""
    global _redis_client
    if _redis_client is None:
        url = get_settings().redis_url
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


async def _cache_get_or_set(
    key: str,
    factory: Callable[..., object],
    ttl: Optional[int] = None,
) -> object:
    """Get cached value or compute and cache using factory."""
    r = _get_redis()
    value = await r.get(key)
    if value is not None:
        return value
    result = factory()
    value = await result if hasattr(result, "__await__") else result
    if ttl is not None:
        await r.set(key, value, ex=ttl)
    else:
        await r.set(key, value)
    return value


async def _cache_set_many(
    entries: dict[str, object],
    ttl: Optional[int] = None,
) -> None:
    """Set multiple key-value pairs with optional TTL using pipeline."""
    r = _get_redis()
    async with r.pipeline(transaction=True) as pipe:
        for key, value in entries.items():
            if ttl is not None:
                pipe.set(key, value, ex=ttl)
            else:
                pipe.set(key, value)
        await pipe.execute()


async def _cache_get_many(keys: list[str]) -> dict[str, object]:
    """Get multiple values by keys."""
    r = _get_redis()
    values = await r.mget(keys)
    return dict(zip(keys, values))


async def _cache_delete_many(keys: list[str]) -> int:
    """Delete multiple keys, returns count."""
    r = _get_redis()
    if not keys:
        return 0
    return await r.delete(*keys)


async def _redis_flat_clear_hash_prefix(r: aioredis.Redis, prefix: str) -> None:
    """Delete all Redis keys under a flat hash entry (``prefix:*``).

    Used when DSL calls ``entry.clear()`` with no arguments on a hash-typed cache.
    """
    pattern = f"{prefix}:*"
    async for key in r.scan_iter(match=pattern):
        await r.delete(key)


async def _redis_flat_hash_keys(r: aioredis.Redis, prefix: str) -> list[str]:
    """Return logical row keys for a flat hash entry (Redis keys ``prefix:*``)."""
    prefix_with_colon = f"{prefix}:"
    out: list[str] = []
    async for full in r.scan_iter(match=f"{prefix}:*"):
        key_str = full.decode() if isinstance(full, bytes) else str(full)
        if key_str.startswith(prefix_with_colon):
            out.append(key_str[len(prefix_with_colon) :])
    return out


async def _cache_lock(key: str, ttl: Optional[int] = None) -> bool:
    """Acquire distributed lock using SET NX."""
    r = _get_redis()
    if ttl is not None:
        return bool(await r.set(key, "1", nx=True, ex=ttl))
    return bool(await r.set(key, "1", nx=True))


async def _cache_check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window rate limit using Redis; mirrors TS ``_cacheCheckRateLimit``."""
    r = _get_redis()
    now = int(time.time())
    raw = await r.get(key)
    if raw:
        bucket = json.loads(raw)
    else:
        bucket = {"count": 0, "windowStart": now}
    if now - int(bucket["windowStart"]) >= window_seconds:
        bucket["windowStart"] = now
        bucket["count"] = 0
    bucket["count"] = int(bucket["count"]) + 1
    await r.set(key, json.dumps(bucket))
    return int(bucket["count"]) <= limit
