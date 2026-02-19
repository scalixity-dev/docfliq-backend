"""Search domain Pydantic V2 schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentType, PostStatus, PostVisibility


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
    """Offset-paginated post search results."""

    items: list[PostSearchResult]
    total: int = Field(description="Total matching posts.")
    query: str | None = Field(description="The full-text query string (if provided).")
    limit: int
    offset: int


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
