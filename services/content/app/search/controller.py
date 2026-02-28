"""Search controller — orchestration layer between router and service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.search import service
from app.search.schemas import (
    ChannelSearchResponse,
    ChannelSearchResult,
    CourseSearchResponse,
    PeopleSearchResponse,
    PostSearchResult,
    SearchResponse,
    SuggestResponse,
    UnifiedSearchResponse,
    WebinarSearchResponse,
)


async def search_posts(
    db: AsyncSession,
    os_client,
    index_prefix: str,
    query: str | None = None,
    tags: list[str] | None = None,
    content_type: ContentType | None = None,
    channel_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    posts, total, facets = await service.search_posts(
        db=db,
        os_client=os_client,
        index_prefix=index_prefix,
        query=query,
        tags=tags,
        content_type=content_type,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )
    # OpenSearch returns raw dicts; Postgres returns ORM objects
    items = [
        PostSearchResult.model_validate(p) if hasattr(p, "__table__")
        else PostSearchResult(
            post_id=p["content_id"],
            author_id=p["author_id"],
            content_type=p["content_type"],
            title=p.get("title"),
            body=p.get("body_snippet"),
            visibility="PUBLIC",
            status="PUBLISHED",
            specialty_tags=p.get("specialty_tags"),
            like_count=0,
            comment_count=0,
            channel_id=None,
            created_at=p.get("created_at"),
        )
        for p in posts
    ]
    return SearchResponse(
        items=items,
        total=total,
        query=query,
        limit=limit,
        offset=offset,
        facets=facets,
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


async def search_people(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PeopleSearchResponse:
    results, total = await service.search_people(
        os_client, index_prefix, query=query, specialty=specialty, limit=limit, offset=offset
    )
    return PeopleSearchResponse(items=results, total=total, query=query, limit=limit, offset=offset)


async def search_courses(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty_tags: list[str] | None = None,
    pricing_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> CourseSearchResponse:
    results, total = await service.search_courses(
        os_client, index_prefix, query=query, specialty_tags=specialty_tags,
        pricing_type=pricing_type, limit=limit, offset=offset
    )
    return CourseSearchResponse(items=results, total=total, query=query, limit=limit, offset=offset)


async def search_webinars(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty_tags: list[str] | None = None,
    pricing_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> WebinarSearchResponse:
    results, total = await service.search_webinars(
        os_client, index_prefix, query=query, specialty_tags=specialty_tags,
        pricing_type=pricing_type, limit=limit, offset=offset
    )
    return WebinarSearchResponse(items=results, total=total, query=query, limit=limit, offset=offset)


async def suggest(
    os_client,
    index_prefix: str,
    partial: str,
    limit: int = 10,
) -> SuggestResponse:
    items = await service.suggest(os_client, index_prefix, partial, limit)
    return SuggestResponse(suggestions=items, query=partial)


async def unified_search(
    db: AsyncSession,
    os_client,
    index_prefix: str,
    query: str,
    limit: int = 5,
) -> UnifiedSearchResponse:
    """Fan out to all indexes and return top-N per section."""
    # Posts (dual-path)
    posts, _, facets = await service.search_posts(
        db=db, os_client=os_client, index_prefix=index_prefix,
        query=query, limit=limit, offset=0,
    )
    post_items = [
        PostSearchResult.model_validate(p) if hasattr(p, "__table__")
        else PostSearchResult(
            post_id=p["content_id"],
            author_id=p["author_id"],
            content_type=p["content_type"],
            title=p.get("title"),
            body=p.get("body_snippet"),
            visibility="PUBLIC",
            status="PUBLISHED",
            specialty_tags=p.get("specialty_tags"),
            like_count=0,
            comment_count=0,
            channel_id=None,
            created_at=p.get("created_at"),
        )
        for p in posts
    ]

    # Channels (Postgres)
    channels, _ = await service.search_channels(db, query=query, limit=limit, offset=0)
    channel_items = [ChannelSearchResult.model_validate(c) for c in channels]

    # People (OpenSearch stub)
    people_items, _ = await service.search_people(
        os_client, index_prefix, query=query, limit=limit
    )

    # Courses (OpenSearch stub)
    course_items, _ = await service.search_courses(
        os_client, index_prefix, query=query, limit=limit
    )

    # Webinars (OpenSearch stub)
    webinar_items, _ = await service.search_webinars(
        os_client, index_prefix, query=query, limit=limit
    )

    return UnifiedSearchResponse(
        query=query,
        posts=post_items,
        channels=channel_items,
        people=people_items,
        courses=course_items,
        webinars=webinar_items,
        facets=facets,
    )
