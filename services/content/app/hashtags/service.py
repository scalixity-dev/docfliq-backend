"""Hashtag business logic — trending, search, posts-by-tag."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PostStatus, PostVisibility
from app.models.post import Post

logger = logging.getLogger(__name__)

_TRENDING_CACHE_KEY = "hashtag:trending"
_TRENDING_CACHE_TTL = 300  # 5 minutes
_TRENDING_WINDOW_HOURS = 24

_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)


async def get_trending_hashtags(
    db: AsyncSession,
    redis: Redis | None = None,
    limit: int = 20,
    window_hours: int = _TRENDING_WINDOW_HOURS,
) -> list[dict]:
    """Top hashtags by post count in the last N hours, Redis-cached."""
    # Try cache first
    if redis is not None:
        cached = await redis.get(_TRENDING_CACHE_KEY)
        if cached:
            items = json.loads(cached)
            return items[:limit]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # unnest the hashtags array and aggregate
    stmt = (
        select(
            func.unnest(Post.hashtags).label("tag"),
            func.count().label("cnt"),
        )
        .where(
            Post.status.in_(_LIVE_STATUSES),
            Post.visibility == PostVisibility.PUBLIC,
            Post.created_at >= cutoff,
            Post.hashtags.isnot(None),  # type: ignore[union-attr]
        )
        .group_by(text("tag"))
        .order_by(text("cnt DESC"))
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()
    items = [{"name": row.tag, "post_count": row.cnt} for row in rows]

    # Cache result
    if redis is not None and items:
        await redis.setex(_TRENDING_CACHE_KEY, _TRENDING_CACHE_TTL, json.dumps(items))

    return items


async def search_hashtags(
    q: str,
    db: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Prefix search for hashtag autocomplete."""
    prefix = q.lower().strip().lstrip("#")
    if not prefix:
        return []

    # Find distinct hashtags matching the prefix, ordered by frequency
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = (
        select(
            func.unnest(Post.hashtags).label("tag"),
            func.count().label("cnt"),
        )
        .where(
            Post.status.in_(_LIVE_STATUSES),
            Post.created_at >= cutoff,
            Post.hashtags.isnot(None),  # type: ignore[union-attr]
        )
        .group_by(text("tag"))
        .having(func.unnest(Post.hashtags).cast(type_=None).ilike(f"{prefix}%"))  # type: ignore
        .order_by(text("cnt DESC"))
        .limit(limit)
    )

    # Simpler approach: use a subquery with LIKE filter
    raw_sql = text(
        """
        SELECT tag, COUNT(*) AS cnt
        FROM posts, unnest(hashtags) AS tag
        WHERE status IN ('PUBLISHED', 'EDITED')
          AND created_at >= :cutoff
          AND lower(tag) LIKE :prefix
        GROUP BY tag
        ORDER BY cnt DESC
        LIMIT :lim
        """
    )
    rows = (
        await db.execute(
            raw_sql,
            {"cutoff": cutoff, "prefix": f"{prefix}%", "lim": limit},
        )
    ).all()

    return [{"name": row.tag, "post_count": row.cnt} for row in rows]


async def get_posts_by_hashtag(
    tag: str,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Fetch posts containing a specific hashtag."""
    normalized = tag.lower().strip().lstrip("#")

    base_filter = [
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
        Post.hashtags.contains([normalized]),  # type: ignore[union-attr]
    ]

    # Count
    count_q = select(func.count(Post.post_id)).where(*base_filter)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    posts_q = (
        select(Post)
        .where(*base_filter)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    posts = list((await db.execute(posts_q)).scalars().all())

    return posts, total
