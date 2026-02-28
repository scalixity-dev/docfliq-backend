"""Hashtag discovery endpoints — trending, autocomplete, posts-by-tag."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_redis
from app.feed.schemas import FeedResponse, PostSummary
from app.hashtags.schemas import (
    HashtagItem,
    HashtagSuggestResponse,
    TrendingHashtagsResponse,
)
from app.hashtags.service import (
    get_posts_by_hashtag,
    get_trending_hashtags,
    search_hashtags,
)

router = APIRouter(prefix="/hashtags", tags=["Hashtags"])


@router.get(
    "/trending",
    response_model=TrendingHashtagsResponse,
    summary="Trending hashtags",
    description="Top hashtags by post count in the last 24 hours. Redis-cached for 5 minutes.",
)
async def trending_hashtags(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TrendingHashtagsResponse:
    items = await get_trending_hashtags(db, redis, limit=limit)
    return TrendingHashtagsResponse(
        items=[HashtagItem(**i) for i in items],
        window_hours=24,
    )


@router.get(
    "/search",
    response_model=HashtagSuggestResponse,
    summary="Hashtag autocomplete",
    description="Prefix search for the editor hashtag suggestion dropdown.",
)
async def suggest_hashtags(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> HashtagSuggestResponse:
    items = await search_hashtags(q, db, limit=limit)
    return HashtagSuggestResponse(
        suggestions=[HashtagItem(**i) for i in items],
    )


@router.get(
    "/{tag}/posts",
    response_model=FeedResponse,
    summary="Posts by hashtag",
    description="Fetch published posts containing a specific hashtag, sorted by recency.",
)
async def posts_by_hashtag(
    tag: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    posts, total = await get_posts_by_hashtag(tag, db, limit=limit, offset=offset)
    return FeedResponse(
        items=[PostSummary.model_validate(p) for p in posts],
        total=total,
        limit=limit,
        offset=offset,
    )
