"""Redis cache helpers for the feed domain.

Key schema
----------
feed:{user_id}:affinity:{author_id}   float str  TTL 1 h   per-author affinity score
feed:trending                          JSON list   TTL 5 min list of post_id strings
content:fingerprint:{hash}:{author_id} "1"         TTL 60 s  duplicate-content guard
"""

import json
from uuid import UUID

from redis.asyncio import Redis

_AFFINITY_TTL_S: int = 3600      # 1 hour
_TRENDING_TTL_S: int = 300       # 5 minutes
_FINGERPRINT_TTL_S: int = 60     # 60 seconds


# ---------------------------------------------------------------------------
# Affinity
# ---------------------------------------------------------------------------


def _affinity_key(user_id: UUID, author_id: UUID) -> str:
    return f"feed:{user_id}:affinity:{author_id}"


async def get_affinity(user_id: UUID, author_id: UUID, redis: Redis) -> float | None:
    """Return cached affinity score or None if not cached."""
    val = await redis.get(_affinity_key(user_id, author_id))
    return float(val) if val is not None else None


async def set_affinity(
    user_id: UUID, author_id: UUID, score: float, redis: Redis
) -> None:
    await redis.setex(_affinity_key(user_id, author_id), _AFFINITY_TTL_S, str(score))


async def get_affinities_batch(
    user_id: UUID, author_ids: list[UUID], redis: Redis
) -> dict[UUID, float | None]:
    """Fetch affinity scores for multiple authors in one pipeline round-trip."""
    if not author_ids:
        return {}
    keys = [_affinity_key(user_id, aid) for aid in author_ids]
    pipeline = redis.pipeline()
    for k in keys:
        pipeline.get(k)
    values = await pipeline.execute()
    return {
        aid: (float(v) if v is not None else None)
        for aid, v in zip(author_ids, values)
    }


async def set_affinities_batch(
    user_id: UUID, scores: dict[UUID, float], redis: Redis
) -> None:
    """Write multiple affinity scores in one pipeline round-trip."""
    if not scores:
        return
    pipeline = redis.pipeline()
    for author_id, score in scores.items():
        pipeline.setex(_affinity_key(user_id, author_id), _AFFINITY_TTL_S, str(score))
    await pipeline.execute()


# ---------------------------------------------------------------------------
# Trending
# ---------------------------------------------------------------------------

_TRENDING_KEY = "feed:trending"


async def get_trending_post_ids(redis: Redis) -> list[str] | None:
    """Return cached list of trending post_id strings, or None if cache miss."""
    val = await redis.get(_TRENDING_KEY)
    return json.loads(val) if val is not None else None


async def set_trending_post_ids(post_ids: list[str], redis: Redis) -> None:
    await redis.setex(_TRENDING_KEY, _TRENDING_TTL_S, json.dumps(post_ids))


# ---------------------------------------------------------------------------
# Content fingerprint (duplicate spam guard)
# ---------------------------------------------------------------------------


def _fingerprint_key(fingerprint: str, author_id: UUID) -> str:
    return f"content:fingerprint:{fingerprint}:{author_id}"


async def is_duplicate_content(
    fingerprint: str, author_id: UUID, redis: Redis
) -> bool:
    """Return True if this (fingerprint, author) pair was seen within the last 60 s.

    Uses SETNX so the check and set are atomic: the first call sets the key and
    returns False (not duplicate). Subsequent calls within the TTL return True.
    """
    key = _fingerprint_key(fingerprint, author_id)
    was_set = await redis.setnx(key, "1")
    if was_set:
        await redis.expire(key, _FINGERPRINT_TTL_S)
        return False  # first occurrence — not a duplicate
    return True  # key already existed — duplicate
