"""Search domain Pydantic V2 schemas.

Sections:
  - Post / Channel search (Postgres GIN + OpenSearch dual-path)
  - Unified search (LinkedIn-style, all indexes, top-N per section)
  - Suggest / autocomplete
  - People, Courses, Webinars (stub schemas — populated once those services exist)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentType, PostStatus, PostVisibility


# ---------------------------------------------------------------------------
# Facet schemas
# ---------------------------------------------------------------------------


class FacetBucket(BaseModel):
    value: str
    count: int


class SearchFacets(BaseModel):
    content_type: list[FacetBucket] = Field(default_factory=list)
    specialty_tags: list[FacetBucket] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Post search
# ---------------------------------------------------------------------------


class PostSearchResult(BaseModel):
    """Lightweight post result for search listings."""

    model_config = ConfigDict(from_attributes=True)

    post_id: UUID
    author_id: UUID = Field(description="User ID of the post author.")
    content_type: ContentType
    title: str | None
    body: str | None
    visibility: PostVisibility
    status: PostStatus
    specialty_tags: list[str] | None
    like_count: int
    comment_count: int
    channel_id: UUID | None
    created_at: datetime


class SearchResponse(BaseModel):
    """Offset-paginated post search results with optional facets."""

    items: list[PostSearchResult]
    total: int = Field(description="Total matching posts.")
    query: str | None = Field(description="The full-text query string (if provided).")
    limit: int
    offset: int
    facets: SearchFacets | None = Field(None, description="Aggregated facet counts (OpenSearch only).")


# ---------------------------------------------------------------------------
# Channel search
# ---------------------------------------------------------------------------


class ChannelSearchResult(BaseModel):
    """Channel result for channel search listings."""

    model_config = ConfigDict(from_attributes=True)

    channel_id: UUID
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    owner_id: UUID
    is_active: bool
    created_at: datetime


class ChannelSearchResponse(BaseModel):
    """Offset-paginated channel search results."""

    items: list[ChannelSearchResult]
    total: int
    query: str | None
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# People search (stub — identity service not yet built)
# ---------------------------------------------------------------------------


class PeopleSearchResult(BaseModel):
    """User profile search result from user_index (OpenSearch)."""

    user_id: UUID | None = None
    full_name: str = ""
    specialty: str | None = None
    role: str | None = None
    verification_status: str | None = None


class PeopleSearchResponse(BaseModel):
    items: list[PeopleSearchResult] = Field(default_factory=list)
    total: int = 0
    query: str | None = None
    limit: int = 20
    offset: int = 0


# ---------------------------------------------------------------------------
# Course search (stub — course service not yet built)
# ---------------------------------------------------------------------------


class CourseSearchResult(BaseModel):
    """Course search result from content_index (OpenSearch, content_type=COURSE)."""

    content_id: str = ""
    title: str = ""
    body_snippet: str = ""
    specialty_tags: list[str] = Field(default_factory=list)
    pricing_type: str | None = None
    duration_mins: int | None = None
    popularity_score: float = 0.0
    created_at: str | None = None


class CourseSearchResponse(BaseModel):
    items: list[CourseSearchResult] = Field(default_factory=list)
    total: int = 0
    query: str | None = None
    limit: int = 20
    offset: int = 0


# ---------------------------------------------------------------------------
# Webinar search (stub — webinar service not yet built)
# ---------------------------------------------------------------------------


class WebinarSearchResult(BaseModel):
    """Webinar search result from content_index (OpenSearch, content_type=WEBINAR)."""

    content_id: str = ""
    title: str = ""
    body_snippet: str = ""
    specialty_tags: list[str] = Field(default_factory=list)
    pricing_type: str | None = None
    duration_mins: int | None = None
    popularity_score: float = 0.0
    created_at: str | None = None


class WebinarSearchResponse(BaseModel):
    items: list[WebinarSearchResult] = Field(default_factory=list)
    total: int = 0
    query: str | None = None
    limit: int = 20
    offset: int = 0


# ---------------------------------------------------------------------------
# Suggest / autocomplete
# ---------------------------------------------------------------------------


class SuggestItem(BaseModel):
    content_id: str
    content_type: str
    title: str
    specialty_tags: list[str] = Field(default_factory=list)


class SuggestResponse(BaseModel):
    suggestions: list[SuggestItem] = Field(default_factory=list)
    query: str


# ---------------------------------------------------------------------------
# Unified search (LinkedIn-style — top N per section)
# ---------------------------------------------------------------------------


class UnifiedSearchResponse(BaseModel):
    """LinkedIn-style unified search: top results per section."""

    query: str
    posts: list[PostSearchResult] = Field(default_factory=list, description="Top post results.")
    channels: list[ChannelSearchResult] = Field(default_factory=list, description="Top channel results.")
    people: list[PeopleSearchResult] = Field(default_factory=list, description="Top people results (stub).")
    courses: list[CourseSearchResult] = Field(default_factory=list, description="Top course results (stub).")
    webinars: list[WebinarSearchResult] = Field(default_factory=list, description="Top webinar results (stub).")
    facets: SearchFacets | None = None
