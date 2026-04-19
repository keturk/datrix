"""Cache helper functions for generated Python code.

Uses redis.asyncio for async Redis operations. The Redis client is lazily
initialized from the REDIS_URL environment variable.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

import redis.asyncio as aioredis

_redis_client: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    """Get or create the Redis client."""
    global _redis_client
    if _redis_client is None:
        url = os.environ["REDIS_URL"]
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


async def _cache_get_or_set(
    key: str,
    factory: Callable[..., Any],
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


async def _cache_lock(key: str, ttl: Optional[int] = None) -> bool:
    """Acquire distributed lock using SET NX."""
    r = _get_redis()
    if ttl is not None:
        return bool(await r.set(key, "1", nx=True, ex=ttl))
    return bool(await r.set(key, "1", nx=True))
