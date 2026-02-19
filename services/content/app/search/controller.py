"""Search controller — orchestration layer between router and service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.search import service
from app.search.schemas import (
    ChannelSearchResponse,
    ChannelSearchResult,
    PostSearchResult,
    SearchResponse,
)


async def search_posts(
    db: AsyncSession,
    query: str | None = None,
    tags: list[str] | None = None,
    content_type: ContentType | None = None,
    channel_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    posts, total = await service.search_posts(
        db=db,
        query=query,
        tags=tags,
        content_type=content_type,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )
    return SearchResponse(
        items=[PostSearchResult.model_validate(p) for p in posts],
        total=total,
        query=query,
        limit=limit,
        offset=offset,
    )


async def search_channels(
    db: AsyncSession,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ChannelSearchResponse:
    channels, total = await service.search_channels(db, query=query, limit=limit, offset=offset)
    return ChannelSearchResponse(
        items=[ChannelSearchResult.model_validate(c) for c in channels],
        total=total,
        query=query,
        limit=limit,
        offset=offset,
    )
