"""Feed controller — orchestration layer between router and service."""

from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.experiments import service as experiments_service
from app.feed import service
from app.feed.schemas import (
    ChannelFeedResponse,
    EditorPickResponse,
    FeedResponse,
    FollowingFeedResponse,
    ForYouFeedResponse,
    PostSummary,
    TrendingFeedResponse,
)
from app.pagination import decode_cursor, encode_cursor


# ===========================================================================
# Existing feeds
# ===========================================================================


async def get_public_feed(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> FeedResponse:
    posts, total = await service.get_public_feed(db, limit=limit, offset=offset)
    return FeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_post(post_id: UUID, db: AsyncSession) -> PostSummary:
    post = await service.get_post_for_feed(post_id, db)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    return PostSummary.model_validate(post)


async def get_channel_feed(
    channel_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> ChannelFeedResponse:
    posts, total = await service.get_channel_feed(channel_id, db, limit=limit, offset=offset)
    return ChannelFeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        total=total,
        limit=limit,
        offset=offset,
        channel_id=channel_id,
    )


async def get_user_posts(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> FeedResponse:
    posts, total = await service.get_user_posts(user_id, db, limit=limit, offset=offset)
    return FeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        total=total,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# For You feed
# ===========================================================================


async def get_for_you_feed(
    user_id: UUID,
    user_interests: list[str],
    db: AsyncSession,
    redis: Redis,
    limit: int = 20,
    offset: int = 0,
    cohort_ids: list[UUID] | None = None,
    exclude_author_ids: list[UUID] | None = None,
) -> ForYouFeedResponse:
    weight_config, _ = await experiments_service.get_effective_weights(
        user_id=user_id,
        cohort_ids=cohort_ids or [],
        db=db,
        redis=redis,
    )
    posts, total, is_cold_start = await service.get_for_you_feed(
        user_id=user_id,
        user_interests=user_interests,
        db=db,
        redis=redis,
        limit=limit,
        offset=offset,
        weight_config=weight_config,
        exclude_author_ids=exclude_author_ids,
    )
    return ForYouFeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        total=total,
        limit=limit,
        offset=offset,
        is_cold_start=is_cold_start,
    )


# ===========================================================================
# Following tab
# ===========================================================================


async def get_following_feed(
    following_ids: list[UUID],
    db: AsyncSession,
    limit: int = 20,
    depth: int = 0,
    cursor: str | None = None,
    exclude_author_ids: list[UUID] | None = None,
) -> FollowingFeedResponse:
    cursor_created_at = None
    cursor_post_id = None
    if cursor:
        try:
            cursor_created_at, cursor_post_id = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor.",
            )

    posts, is_exhausted = await service.get_following_feed(
        following_ids=following_ids,
        db=db,
        limit=limit,
        depth=depth,
        cursor_created_at=cursor_created_at,
        cursor_post_id=cursor_post_id,
        exclude_author_ids=exclude_author_ids,
    )

    next_cursor: str | None = None
    has_more = not is_exhausted and bool(posts)
    if has_more:
        last = posts[-1]
        next_cursor = encode_cursor(last.created_at, last.post_id)

    return FollowingFeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        next_cursor=next_cursor,
        has_more=has_more,
        is_exhausted=is_exhausted,
    )


# ===========================================================================
# Trending
# ===========================================================================


async def get_trending_feed(
    db: AsyncSession, redis: Redis, limit: int = 20
) -> TrendingFeedResponse:
    posts, was_cached = await service.get_trending_posts(db=db, redis=redis, limit=limit)
    return TrendingFeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        cached=was_cached,
    )


# ===========================================================================
# Editor Picks
# ===========================================================================


async def list_editor_picks(db: AsyncSession) -> list[EditorPickResponse]:
    picks = await service.list_editor_picks(db)
    return [EditorPickResponse.model_validate(p) for p in picks]


async def add_editor_pick(
    post_id: UUID, added_by: UUID, priority: int, db: AsyncSession
) -> EditorPickResponse:
    try:
        pick = await service.add_editor_pick(
            post_id=post_id, added_by=added_by, priority=priority, db=db
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return EditorPickResponse.model_validate(pick)


async def remove_editor_pick(post_id: UUID, db: AsyncSession) -> None:
    try:
        await service.remove_editor_pick(post_id=post_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
