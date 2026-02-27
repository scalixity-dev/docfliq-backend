"""Feed service — pure business logic, no FastAPI imports.

All feed queries include both PUBLISHED and EDITED posts — the EDITED status
means a live post that has been modified at least once.

Feed strategies implemented
---------------------------
- Public feed        : reverse-chronological, offset-based (unauthenticated)
- Channel feed       : reverse-chronological, offset-based
- User posts         : reverse-chronological, offset-based (profile view)
- For You feed       : composite-scored (recency + specialty + affinity), offset-based
- Following tab      : reverse-chronological, cursor-based, 500-post hard cap
- Trending           : highest engagement in last 48 h, Redis-cached (5 min)
- Cold start         : editor picks 20% + trending 40% + specialty 40%
- Editor picks CRUD  : admin-managed curated post list
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.feed import cache as feed_cache
from app.feed.scoring import (
    AFFINITY_POINTS,
    DEFAULT_WEIGHT_CONFIG,
    WeightConfig,
    normalise_affinity,
    score_composite,
    score_recency,
    score_specialty,
)
from app.models.comment import Comment
from app.models.editor_pick import EditorPick
from app.models.enums import LikeTargetType, PostStatus, PostVisibility
from app.models.interaction import Like, Share
from app.models.post import Post
from redis.asyncio import Redis

# Statuses visible to any viewer (used across all feed queries)
_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)

# Candidate window for the For You feed scoring
_FOR_YOU_WINDOW_DAYS: int = 7

# Trending engagement window (48 h as per spec 3.4.2)
_TRENDING_WINDOW_HOURS: int = 48

# Following feed: 500-post session hard cap (spec 3.4.5)
_FOLLOWING_HARD_CAP: int = 500


# ===========================================================================
# Existing feeds (public / channel / user posts)
# ===========================================================================


async def get_public_feed(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return public, live posts ordered by recency."""
    base = select(Post).where(
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def get_post_for_feed(post_id: UUID, db: AsyncSession) -> Post | None:
    """Fetch a single live post by ID; returns None if not found or not visible."""
    result = await db.execute(
        select(Post).where(
            Post.post_id == post_id,
            Post.status.in_(_LIVE_STATUSES),
        )
    )
    return result.scalar_one_or_none()


async def get_channel_feed(
    channel_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return live posts for a channel, newest first."""
    base = select(Post).where(
        Post.channel_id == channel_id,
        Post.status.in_(_LIVE_STATUSES),
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def get_user_posts(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return public, live posts by a specific user, newest first."""
    base = select(Post).where(
        Post.author_id == user_id,
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


# ===========================================================================
# Affinity helpers (private)
# ===========================================================================


async def _compute_raw_affinity(
    user_id: UUID, author_ids: list[UUID], db: AsyncSession
) -> dict[UUID, float]:
    """Compute raw affinity points per author via three GROUP BY queries.

    like=1pt, comment=3pt, share=5pt (spec 3.4.2).
    No profile-visit signal — that data lives in identity_db.
    """
    result: dict[UUID, float] = {aid: 0.0 for aid in author_ids}

    # Likes on posts authored by target authors
    likes_q = (
        select(Post.author_id, func.count(Like.like_id).label("cnt"))
        .join(
            Like,
            and_(Like.target_id == Post.post_id, Like.target_type == LikeTargetType.POST),
        )
        .where(Like.user_id == user_id, Post.author_id.in_(author_ids))
        .group_by(Post.author_id)
    )
    for row in (await db.execute(likes_q)).all():
        result[row.author_id] += row.cnt * AFFINITY_POINTS["like"]

    # Comments on posts authored by target authors
    comments_q = (
        select(Post.author_id, func.count(Comment.comment_id).label("cnt"))
        .join(Comment, Comment.post_id == Post.post_id)
        .where(Comment.author_id == user_id, Post.author_id.in_(author_ids))
        .group_by(Post.author_id)
    )
    for row in (await db.execute(comments_q)).all():
        result[row.author_id] += row.cnt * AFFINITY_POINTS["comment"]

    # Shares of posts authored by target authors
    shares_q = (
        select(Post.author_id, func.count(Share.share_id).label("cnt"))
        .join(Share, Share.post_id == Post.post_id)
        .where(Share.user_id == user_id, Post.author_id.in_(author_ids))
        .group_by(Post.author_id)
    )
    for row in (await db.execute(shares_q)).all():
        result[row.author_id] += row.cnt * AFFINITY_POINTS["share"]

    return result


async def _get_affinities(
    user_id: UUID, author_ids: list[UUID], db: AsyncSession, redis: Redis
) -> dict[UUID, float]:
    """Return normalised affinity [0,1] for each author (Redis L1 cache + DB fallback)."""
    cached = await feed_cache.get_affinities_batch(user_id, author_ids, redis)
    uncached = [aid for aid, v in cached.items() if v is None]

    affinities: dict[UUID, float] = {aid: v for aid, v in cached.items() if v is not None}

    if uncached:
        raw = await _compute_raw_affinity(user_id, uncached, db)
        computed = {aid: normalise_affinity(pts, DEFAULT_WEIGHT_CONFIG) for aid, pts in raw.items()}
        await feed_cache.set_affinities_batch(user_id, computed, redis)
        affinities.update(computed)

    return affinities


# ===========================================================================
# Cold-start detection
# ===========================================================================


async def count_user_interactions(user_id: UUID, db: AsyncSession) -> int:
    """Total likes + comments + shares by this user (cold-start threshold check)."""
    likes = (
        await db.execute(select(func.count(Like.like_id)).where(Like.user_id == user_id))
    ).scalar_one()
    comments = (
        await db.execute(
            select(func.count(Comment.comment_id)).where(Comment.author_id == user_id)
        )
    ).scalar_one()
    shares = (
        await db.execute(select(func.count(Share.share_id)).where(Share.user_id == user_id))
    ).scalar_one()
    return likes + comments + shares


# ===========================================================================
# Trending
# ===========================================================================


async def get_trending_posts(
    db: AsyncSession, redis: Redis, limit: int = 20
) -> tuple[list[Post], bool]:
    """Top-engagement posts in the last 48 h, Redis-cached for 5 minutes.

    Engagement score = like_count + comment_count×2 + share_count×3.
    Returns (posts, was_cached).
    """
    cached_ids = await feed_cache.get_trending_post_ids(redis)
    if cached_ids is not None:
        id_list = [UUID(i) for i in cached_ids[:limit]]
        if not id_list:
            return [], True
        rows = await db.execute(select(Post).where(Post.post_id.in_(id_list)))
        by_id = {p.post_id: p for p in rows.scalars().all()}
        # Preserve original ranking order from cache
        return [by_id[i] for i in id_list if i in by_id], True

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_TRENDING_WINDOW_HOURS)
    engagement = (Post.like_count + Post.comment_count * 2 + Post.share_count * 3).label(
        "engagement"
    )
    q = (
        select(Post)
        .where(
            Post.created_at >= cutoff,
            Post.status.in_(_LIVE_STATUSES),
            Post.visibility == PostVisibility.PUBLIC,
        )
        .order_by(engagement.desc())
        .limit(limit)
    )
    posts = list((await db.execute(q)).scalars().all())
    await feed_cache.set_trending_post_ids([str(p.post_id) for p in posts], redis)
    return posts, False


# ===========================================================================
# Editor Picks
# ===========================================================================


async def get_editor_picks(db: AsyncSession, limit: int = 20) -> list[Post]:
    """Active editor picks ordered by priority (ascending), joined to live posts."""
    q = (
        select(Post)
        .join(EditorPick, EditorPick.post_id == Post.post_id)
        .where(EditorPick.is_active.is_(True), Post.status.in_(_LIVE_STATUSES))
        .order_by(EditorPick.priority.asc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


async def list_editor_picks(db: AsyncSession) -> list[EditorPick]:
    """All editor pick records for admin management."""
    return list(
        (await db.execute(select(EditorPick).order_by(EditorPick.priority.asc()))).scalars().all()
    )


async def add_editor_pick(
    post_id: UUID, added_by: UUID, priority: int, db: AsyncSession
) -> EditorPick:
    """Add a post to editor picks. Raises ValueError if already added."""
    pick = EditorPick(post_id=post_id, added_by=added_by, priority=priority, is_active=True)
    db.add(pick)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"Post {post_id} is already in editor picks.")
    await db.refresh(pick)
    return pick


async def remove_editor_pick(post_id: UUID, db: AsyncSession) -> None:
    """Deactivate an editor pick (soft remove — row is kept for audit trail)."""
    result = await db.execute(
        select(EditorPick).where(EditorPick.post_id == post_id)
    )
    pick = result.scalar_one_or_none()
    if pick is None:
        raise ValueError(f"Post {post_id} is not in editor picks.")
    pick.is_active = False
    await db.flush()


# ===========================================================================
# Cold-start feed
# ===========================================================================


async def get_cold_start_feed(
    user_interests: list[str],
    db: AsyncSession,
    redis: Redis,
    limit: int = 20,
) -> list[Post]:
    """Compose a cold-start feed: 20% editor picks + 40% trending + 40% specialty.

    Deduplicates across segments so each post appears at most once.
    """
    editor_count = max(1, round(limit * 0.20))
    trending_count = max(1, round(limit * 0.40))
    specialty_count = max(1, limit - editor_count - trending_count)

    editor_posts = await get_editor_picks(db, limit=editor_count)
    trending_posts, _ = await get_trending_posts(db, redis, limit=trending_count + editor_count)

    specialty_posts: list[Post] = []
    if user_interests:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_FOR_YOU_WINDOW_DAYS)
        specialty_posts = list(
            (
                await db.execute(
                    select(Post)
                    .where(
                        Post.status.in_(_LIVE_STATUSES),
                        Post.visibility == PostVisibility.PUBLIC,
                        Post.specialty_tags.overlap(user_interests),  # type: ignore[attr-defined]
                        Post.created_at >= cutoff,
                    )
                    .order_by(Post.created_at.desc())
                    .limit(specialty_count + editor_count + trending_count)
                )
            )
            .scalars()
            .all()
        )

    seen: set[UUID] = set()
    merged: list[Post] = []
    for post in editor_posts + trending_posts + specialty_posts:
        if post.post_id not in seen:
            seen.add(post.post_id)
            merged.append(post)
        if len(merged) >= limit:
            break

    return merged


# ===========================================================================
# For You feed (personalised ranked)
# ===========================================================================


async def get_for_you_feed(
    user_id: UUID,
    user_interests: list[str],
    db: AsyncSession,
    redis: Redis,
    limit: int = 20,
    offset: int = 0,
    weight_config: WeightConfig | None = None,
    exclude_author_ids: list[UUID] | None = None,
) -> tuple[list[Post], int, bool]:
    """Ranked personalised feed with composite scoring.

    Algorithm:
    1. Cold-start check (< threshold interactions) → delegate to get_cold_start_feed.
    2. Fetch up to 500 candidate posts from the last 7 days (excluding own posts).
    3. Batch-resolve author affinity (Redis L1 + DB fallback).
    4. Score each post using the provided weight_config (defaults to 40/30/30).
    5. Sort descending and apply offset pagination.

    Returns (page_posts, total_candidates, is_cold_start).
    """
    config = weight_config or DEFAULT_WEIGHT_CONFIG
    interaction_count = await count_user_interactions(user_id, db)
    if interaction_count < config.cold_start_threshold:
        cold_posts = await get_cold_start_feed(user_interests, db, redis, limit=limit)
        return cold_posts, len(cold_posts), True

    cutoff = datetime.now(timezone.utc) - timedelta(days=_FOR_YOU_WINDOW_DAYS)
    filters = [
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
        Post.created_at >= cutoff,
        Post.author_id != user_id,
    ]
    if exclude_author_ids:
        filters.append(Post.author_id.notin_(exclude_author_ids))
    candidates_q = (
        select(Post)
        .where(*filters)
        .order_by(Post.created_at.desc())
        .limit(500)
    )
    candidates = list((await db.execute(candidates_q)).scalars().all())

    if not candidates:
        return [], 0, False

    unique_authors = list({p.author_id for p in candidates})
    affinities = await _get_affinities(user_id, unique_authors, db, redis)

    scored: list[tuple[float, Post]] = [
        (
            score_composite(
                score_recency(p.created_at),
                score_specialty(p.specialty_tags, user_interests),
                affinities.get(p.author_id, 0.0),
                config,
            ),
            p,
        )
        for p in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    total = len(scored)
    page_posts = [p for _, p in scored[offset: offset + limit]]
    return page_posts, total, False


# ===========================================================================
# Following tab
# ===========================================================================


async def get_following_feed(
    following_ids: list[UUID],
    db: AsyncSession,
    limit: int = 20,
    depth: int = 0,
    cursor_created_at: datetime | None = None,
    cursor_post_id: UUID | None = None,
    exclude_author_ids: list[UUID] | None = None,
) -> tuple[list[Post], bool]:
    """Strictly reverse-chronological feed from followed accounts.

    Hard cap: 500 posts per feed session.
    depth = total posts the client has already loaded this session.
    Returns (posts, is_exhausted).
    """
    if not following_ids:
        return [], False

    remaining = _FOLLOWING_HARD_CAP - depth
    if remaining <= 0:
        return [], True

    page_limit = min(limit, remaining)

    filters = [
        Post.author_id.in_(following_ids),
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    ]
    if exclude_author_ids:
        filters.append(Post.author_id.notin_(exclude_author_ids))
    q = select(Post).where(*filters)

    if cursor_created_at is not None and cursor_post_id is not None:
        q = q.where(
            or_(
                Post.created_at < cursor_created_at,
                and_(
                    Post.created_at == cursor_created_at,
                    Post.post_id < cursor_post_id,
                ),
            )
        )

    q = q.order_by(Post.created_at.desc(), Post.post_id.desc()).limit(page_limit + 1)
    posts = list((await db.execute(q)).scalars().all())

    has_extra = len(posts) > page_limit
    if has_extra:
        posts = posts[:page_limit]

    new_depth = depth + len(posts)
    is_exhausted = new_depth >= _FOLLOWING_HARD_CAP or not has_extra

    return posts, is_exhausted
