"""
Async Redis client — shared across email verification and login lockout.

Uses a module-level singleton so a single connection pool is reused per
process.  The pool is created lazily on first call to get_redis_client().
"""
from __future__ import annotations

import redis.asyncio as aioredis

_client: aioredis.Redis | None = None


def get_redis_client(redis_url: str) -> aioredis.Redis:
    """Return (and lazily create) the module-level async Redis client."""
    global _client
    if _client is None:
        _client = aioredis.from_url(redis_url, decode_responses=True)
    return _client
