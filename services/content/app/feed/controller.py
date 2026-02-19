"""Feed controller — orchestration layer between router and service."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.feed import service
from app.feed.schemas import (
    ChannelFeedResponse,
    FeedResponse,
    PostSummary,
)


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
