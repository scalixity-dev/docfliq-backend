"""Search router — all /api/v1/search endpoints.

Endpoints:
  GET /search                  Unified LinkedIn-style search (top N per section)
  GET /search/posts            Post search with facets (Postgres GIN + OpenSearch)
  GET /search/channels         Channel search (Postgres ILIKE)
  GET /search/suggest          Autocomplete (OpenSearch phrase_prefix)
  GET /search/people           People search (OpenSearch user_index stub)
  GET /search/courses          Course search (OpenSearch content_index, type=COURSE stub)
  GET /search/webinars         Webinar search (OpenSearch content_index, type=WEBINAR stub)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.dependencies import get_opensearch, get_settings
from app.models.enums import ContentType
from app.search import controller
from app.search.schemas import (
    ChannelSearchResponse,
    CourseSearchResponse,
    PeopleSearchResponse,
    SearchResponse,
    SuggestResponse,
    UnifiedSearchResponse,
    WebinarSearchResponse,
)

router = APIRouter(prefix="/search", tags=["Search"])


def _index_prefix(settings: Settings) -> str:
    return settings.opensearch_index_prefix


# ===========================================================================
# Unified search (LinkedIn-style)
# ===========================================================================


@router.get(
    "",
    response_model=UnifiedSearchResponse,
    summary="Unified search (LinkedIn-style)",
    description=(
        "Fans out to all search indexes and returns the top `limit` results per section: "
        "posts, channels, people, courses, and webinars. "
        "People/courses/webinars return empty lists until those services populate the indexes. "
        "Uses OpenSearch when enabled, falls back to Postgres for posts/channels. "
        "No auth required."
    ),
)
async def unified_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query."),
    limit: int = Query(5, ge=1, le=20, description="Max results per section."),
    db: AsyncSession = Depends(get_db),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> UnifiedSearchResponse:
    return await controller.unified_search(
        db=db,
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        query=q,
        limit=limit,
    )


# ===========================================================================
# Post search (existing, enhanced with facets + OpenSearch)
# ===========================================================================


@router.get(
    "/posts",
    response_model=SearchResponse,
    summary="Search posts",
    description=(
        "Full-text search over published and edited posts. "
        "Uses OpenSearch (BM25, typo-tolerance, facets) when enabled; "
        "falls back to PostgreSQL GIN when OpenSearch is off. "
        "Supports optional `q`, `tags` (specialty tags), `type` (content type), "
        "and `channel_id` filters. "
        "Facets are populated only when OpenSearch is active. "
        "No auth required."
    ),
)
async def search_posts(
    q: str | None = Query(
        default=None,
        min_length=2,
        max_length=200,
        description="Full-text search query (min 2 chars).",
    ),
    tags: list[str] | None = Query(
        default=None,
        description="Filter by specialty tags (all provided tags must match).",
    ),
    type: ContentType | None = Query(
        default=None,
        alias="type",
        description="Filter by content type.",
    ),
    channel_id: UUID | None = Query(
        default=None,
        description="Filter posts belonging to a specific channel.",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    db: AsyncSession = Depends(get_db),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    return await controller.search_posts(
        db=db,
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        query=q,
        tags=tags,
        content_type=type,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# Channel search (existing)
# ===========================================================================


@router.get(
    "/channels",
    response_model=ChannelSearchResponse,
    summary="Search channels",
    description=(
        "Search active channels by name or description (case-insensitive substring match). "
        "Returns all active channels when `q` is omitted. "
        "No auth required."
    ),
)
async def search_channels(
    q: str | None = Query(
        default=None,
        min_length=2,
        max_length=200,
        description="Search query matched against channel name and description.",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ChannelSearchResponse:
    return await controller.search_channels(db=db, query=q, limit=limit, offset=offset)


# ===========================================================================
# Autocomplete suggest
# ===========================================================================


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    summary="Autocomplete suggestions",
    description=(
        "Returns autocomplete suggestions from the content index "
        "using phrase_prefix matching on title and specialty_tags. "
        "Returns empty suggestions when OpenSearch is disabled. "
        "No auth required."
    ),
)
async def suggest(
    q: str = Query(..., min_length=1, max_length=100, description="Partial search query."),
    limit: int = Query(default=10, ge=1, le=20, description="Max suggestions."),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> SuggestResponse:
    return await controller.suggest(
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        partial=q,
        limit=limit,
    )


# ===========================================================================
# People search (user_index stub)
# ===========================================================================


@router.get(
    "/people",
    response_model=PeopleSearchResponse,
    summary="Search people (user profiles)",
    description=(
        "Search user profiles from the OpenSearch user_index. "
        "Returns empty results until the identity service populates the index. "
        "Supports `q` (name search) and `specialty` filter. "
        "No auth required."
    ),
)
async def search_people(
    q: str | None = Query(default=None, min_length=1, max_length=200, description="Name search query."),
    specialty: str | None = Query(default=None, description="Filter by specialty."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> PeopleSearchResponse:
    return await controller.search_people(
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        query=q,
        specialty=specialty,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# Course search (content_index stub)
# ===========================================================================


@router.get(
    "/courses",
    response_model=CourseSearchResponse,
    summary="Search courses",
    description=(
        "Search courses from the OpenSearch content_index (content_type=COURSE). "
        "Returns empty results until the course service indexes data. "
        "Supports `q`, `specialty_tags`, and `pricing_type` (FREE/PAID) filters. "
        "No auth required."
    ),
)
async def search_courses(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    specialty_tags: list[str] | None = Query(default=None, description="Filter by specialty tags."),
    pricing_type: str | None = Query(default=None, description="FREE or PAID."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> CourseSearchResponse:
    return await controller.search_courses(
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        query=q,
        specialty_tags=specialty_tags,
        pricing_type=pricing_type,
        limit=limit,
        offset=offset,
    )


# ===========================================================================
# Webinar search (content_index stub)
# ===========================================================================


@router.get(
    "/webinars",
    response_model=WebinarSearchResponse,
    summary="Search webinars",
    description=(
        "Search webinars from the OpenSearch content_index (content_type=WEBINAR). "
        "Returns empty results until the webinar service indexes data. "
        "Supports `q`, `specialty_tags`, and `pricing_type` (FREE/PAID) filters. "
        "No auth required."
    ),
)
async def search_webinars(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    specialty_tags: list[str] | None = Query(default=None, description="Filter by specialty tags."),
    pricing_type: str | None = Query(default=None, description="FREE or PAID."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    os_client=Depends(get_opensearch),
    settings: Settings = Depends(get_settings),
) -> WebinarSearchResponse:
    return await controller.search_webinars(
        os_client=os_client,
        index_prefix=_index_prefix(settings),
        query=q,
        specialty_tags=specialty_tags,
        pricing_type=pricing_type,
        limit=limit,
        offset=offset,
    )
