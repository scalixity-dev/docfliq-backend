from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user, get_redis
from app.feed import controller
from app.feed.schemas import (
    ChannelFeedResponse,
    EditorPickCreate,
    EditorPickResponse,
    FeedResponse,
    FollowingFeedResponse,
    ForYouFeedResponse,
    PostSummary,
    TrendingFeedResponse,
)

router = APIRouter(prefix="/feed", tags=["Feed"])


# ===========================================================================
# Public / channel / user feeds (existing)
# ===========================================================================


@router.get(
    "",
    response_model=FeedResponse,
    summary="Public home feed",
    description=(
        "Returns public, live (PUBLISHED or EDITED) posts ordered by recency. "
        "No auth required."
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
    summary="Channel feed",
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
    summary="User profile feed",
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


# ===========================================================================
# For You feed (ranked personalised)
# ===========================================================================


@router.get(
    "/for-you",
    response_model=ForYouFeedResponse,
    summary="For You ranked feed",
    description=(
        "Personalised ranked feed. "
        "Scoring: 40% recency decay (half-life 24 h) + 30% specialty tag overlap "
        "+ 30% author affinity (like=1pt, comment=3pt, share=5pt). "
        "Users with fewer than 10 interactions receive a cold-start feed: "
        "20% editor picks + 40% trending + 40% specialty. "
        "Pass the user's declared specialty interests via `interests` (repeated param). "
        "Requires authentication."
    ),
)
async def get_for_you_feed(
    interests: list[str] = Query(
        default=[],
        description="User's declared specialty interests (e.g. cardiology, oncology).",
    ),
    cohort_ids: list[UUID] = Query(
        default=[],
        description=(
            "Cohort IDs the user belongs to (resolved by client/gateway). "
            "Used to apply per-cohort feed algorithm weights and A/B experiment variants. "
            "Pass repeatedly: ?cohort_ids=id1&cohort_ids=id2."
        ),
    ),
    limit: int = Query(20, ge=1, le=100, description="Page size."),
    offset: int = Query(0, ge=0, le=480, description="Pagination offset (max 480 to respect 500-item cap)."),
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ForYouFeedResponse:
    return await controller.get_for_you_feed(
        user_id=user_id,
        user_interests=interests,
        cohort_ids=cohort_ids,
        db=db,
        redis=redis,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# Following tab (cursor-based, strictly reverse-chronological)
# ===========================================================================


@router.get(
    "/following",
    response_model=FollowingFeedResponse,
    summary="Following tab feed",
    description=(
        "Strictly reverse-chronological feed from accounts the user follows. "
        "Pass the list of followed user IDs via `following_ids` (repeated param). "
        "Cursor-based pagination via `cursor`. "
        "Hard cap: 500 posts per session — tracked via `depth` (total posts already loaded). "
        "When `is_exhausted=true`, show 'You are all caught up'. "
        "Requires authentication."
    ),
)
async def get_following_feed(
    following_ids: list[UUID] = Query(
        default=[],
        description="UUIDs of accounts the user follows (pass repeatedly: ?following_ids=id1&following_ids=id2).",
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque pagination cursor returned by the previous page.",
    ),
    depth: int = Query(
        default=0,
        ge=0,
        description="Total posts already loaded this session. Used to enforce 500-post hard cap.",
    ),
    limit: int = Query(20, ge=1, le=100),
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FollowingFeedResponse:
    return await controller.get_following_feed(
        following_ids=following_ids,
        db=db,
        limit=limit,
        depth=depth,
        cursor=cursor,
    )


# ===========================================================================
# Trending
# ===========================================================================


@router.get(
    "/trending",
    response_model=TrendingFeedResponse,
    summary="Trending posts (last 48 h)",
    description=(
        "Returns posts with the highest engagement score in the last 48 hours. "
        "Engagement = like_count + comment_count×2 + share_count×3. "
        "Results are Redis-cached for 5 minutes. "
        "No auth required."
    ),
)
async def get_trending(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TrendingFeedResponse:
    return await controller.get_trending_feed(db=db, redis=redis, limit=limit)


# ===========================================================================
# Editor Picks (admin-managed curated list)
# ===========================================================================


@router.get(
    "/editor-picks",
    response_model=list[EditorPickResponse],
    summary="List all editor picks (admin)",
    description=(
        "Returns all editor pick records (active and inactive). "
        "In production, gate this endpoint at the API gateway with an admin role check. "
        "Requires authentication."
    ),
)
async def list_editor_picks(
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EditorPickResponse]:
    return await controller.list_editor_picks(db)


@router.post(
    "/editor-picks",
    response_model=EditorPickResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a post to editor picks (admin)",
    description=(
        "Adds a post to the curated editor picks list. "
        "Returns 409 if the post is already picked. "
        "In production, gate this endpoint with an admin role at the API gateway. "
        "Requires authentication."
    ),
)
async def add_editor_pick(
    body: EditorPickCreate,
    added_by: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EditorPickResponse:
    return await controller.add_editor_pick(
        post_id=body.post_id,
        added_by=added_by,
        priority=body.priority,
        db=db,
    )


@router.delete(
    "/editor-picks/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a post from editor picks (admin)",
    description=(
        "Deactivates the editor pick for the given post (soft remove). "
        "Returns 404 if the post was not in editor picks. "
        "In production, gate this endpoint with an admin role at the API gateway. "
        "Requires authentication."
    ),
)
async def remove_editor_pick(
    post_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.remove_editor_pick(post_id=post_id, db=db)
