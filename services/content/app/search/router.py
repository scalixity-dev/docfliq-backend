"""Search router — all /api/v1/search endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import ContentType
from app.search import controller
from app.search.schemas import ChannelSearchResponse, SearchResponse

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "/posts",
    response_model=SearchResponse,
    summary="Search posts",
    description=(
        "Full-text search over published and edited posts. "
        "Supports optional `q` (full-text), `tags` (specialty tags containment), "
        "`type` (content type filter), and `channel_id` filters. "
        "Results are ranked by relevance when `q` is provided."
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
        description="Filter by content type (TEXT, IMAGE, VIDEO, LINK, etc.).",
    ),
    channel_id: UUID | None = Query(
        default=None,
        description="Filter posts belonging to a specific channel.",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    return await controller.search_posts(
        db=db,
        query=q,
        tags=tags,
        content_type=type,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/channels",
    response_model=ChannelSearchResponse,
    summary="Search channels",
    description=(
        "Search active channels by name or description (case-insensitive substring match). "
        "Returns all active channels when `q` is omitted."
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
