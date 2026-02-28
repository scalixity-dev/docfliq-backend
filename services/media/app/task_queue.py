"""
ARQ task queue — API-side job enqueuing.

The FastAPI API process uses this to push jobs into Redis.
Worker processes (app.worker) consume them independently.
"""
from __future__ import annotations

import logging
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None


def _redis_settings_from_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into ARQ RedisSettings."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


async def init_pool(redis_url: str) -> None:
    """Initialize the ARQ Redis connection pool. Called once at API startup."""
    global _pool
    settings = _redis_settings_from_url(redis_url)
    _pool = await create_pool(settings, default_queue_name="media:tasks")
    logger.info("ARQ task queue pool initialized")


async def close_pool() -> None:
    """Close the ARQ Redis pool. Called at API shutdown."""
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
        logger.info("ARQ task queue pool closed")


async def enqueue(function_name: str, *args: Any, **kwargs: Any) -> str | None:
    """
    Enqueue a job for the media worker.

    Returns the job ID or None if enqueue failed.
    Enqueuing is near-instant (just a Redis LPUSH).
    """
    if _pool is None:
        logger.error("ARQ pool not initialized — cannot enqueue %s", function_name)
        return None
    try:
        job = await _pool.enqueue_job(function_name, *args, **kwargs)
        if job:
            logger.info("Enqueued %s → job %s", function_name, job.job_id)
            return job.job_id
        return None
    except Exception:
        logger.exception("Failed to enqueue %s", function_name)
        return None
