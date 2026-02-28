"""Redis cache helpers for the player domain.

Key schema
----------
user:{user_id}:lesson:{lesson_id}                 Hash   TTL 90d    resume position
heartbeat:{user_id}:{lesson_id}                    Hash   TTL 5min   latest heartbeat
quiz:started:{quiz_id}:{enrollment_id}             String TTL=limit  quiz start ts

All functions are best-effort — callers catch exceptions.
"""

from __future__ import annotations

import time
from uuid import UUID

from redis.asyncio import Redis

_RESUME_TTL = 90 * 24 * 3600  # 90 days
_HEARTBEAT_TTL = 300  # 5 minutes


# -- Resume position --

def _resume_key(user_id: UUID, lesson_id: UUID) -> str:
    return f"user:{user_id}:lesson:{lesson_id}"


async def get_resume_position(
    user_id: UUID, lesson_id: UUID, redis: Redis,
) -> dict | None:
    data = await redis.hgetall(_resume_key(user_id, lesson_id))
    return data if data else None


async def set_resume_position(
    user_id: UUID,
    lesson_id: UUID,
    position_secs: int,
    lesson_type: str,
    redis: Redis,
) -> None:
    key = _resume_key(user_id, lesson_id)
    await redis.hset(key, mapping={
        "position_secs": str(position_secs),
        "lesson_type": lesson_type,
        "updated_at": str(int(time.time())),
    })
    await redis.expire(key, _RESUME_TTL)


# -- Heartbeat --

def _heartbeat_key(user_id: UUID, lesson_id: UUID) -> str:
    return f"heartbeat:{user_id}:{lesson_id}"


async def store_heartbeat(
    user_id: UUID,
    lesson_id: UUID,
    position_secs: int,
    intervals_json: str,
    redis: Redis,
) -> None:
    key = _heartbeat_key(user_id, lesson_id)
    await redis.hset(key, mapping={
        "position_secs": str(position_secs),
        "intervals": intervals_json,
        "timestamp": str(int(time.time())),
    })
    await redis.expire(key, _HEARTBEAT_TTL)


async def get_heartbeat(
    user_id: UUID, lesson_id: UUID, redis: Redis,
) -> dict | None:
    data = await redis.hgetall(_heartbeat_key(user_id, lesson_id))
    return data if data else None


# -- Quiz timer --

def _quiz_timer_key(quiz_id: UUID, enrollment_id: UUID) -> str:
    return f"quiz:started:{quiz_id}:{enrollment_id}"


async def start_quiz_timer(
    quiz_id: UUID, enrollment_id: UUID, time_limit_secs: int, redis: Redis,
) -> None:
    key = _quiz_timer_key(quiz_id, enrollment_id)
    await redis.set(key, str(int(time.time())), ex=time_limit_secs + 60)


async def get_quiz_start_time(
    quiz_id: UUID, enrollment_id: UUID, redis: Redis,
) -> int | None:
    val = await redis.get(_quiz_timer_key(quiz_id, enrollment_id))
    return int(val) if val else None
