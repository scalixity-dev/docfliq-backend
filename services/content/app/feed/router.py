from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_optional_user
from app.feed import controller
from app.feed.schemas import ChannelFeedResponse, FeedResponse, PostSummary

router = APIRouter(prefix="/feed", tags=["Feed"])


@router.get(
    "",
    response_model=FeedResponse,
    summary="Get public home feed",
    description=(
        "Returns public, live (PUBLISHED or EDITED) posts ordered by recency. "
        "No auth required. Future: will be personalised based on follow graph."
    ),
)
async def get_feed(
    limit: int = Query(20, ge=1, le=100, description="Page size."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    _: UUID | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    return await controller.get_public_feed(db, limit=limit, offset=offset)


@router.get(
    "/posts/{post_id}",
    response_model=PostSummary,
    summary="Get a single published or edited post",
    description="Returns a live post by ID. Returns 404 if the post is a draft, deleted, or hidden.",
)
async def get_post(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PostSummary:
    return await controller.get_post(post_id, db)


@router.get(
    "/channels/{channel_id}/posts",
    response_model=ChannelFeedResponse,
    summary="Get posts in a channel",
    description="Returns live posts belonging to the specified channel, newest first.",
)
async def get_channel_feed(
    channel_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ChannelFeedResponse:
    return await controller.get_channel_feed(channel_id, db, limit=limit, offset=offset)


@router.get(
    "/users/{user_id}/posts",
    response_model=FeedResponse,
    summary="Get public posts by a user",
    description=(
        "Returns public, live posts by the specified user, newest first. "
        "Does not include DRAFT, SOFT_DELETED, or HIDDEN_BY_ADMIN posts."
    ),
)
async def get_user_posts(
    user_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    return await controller.get_user_posts(user_id, db, limit=limit, offset=offset)
