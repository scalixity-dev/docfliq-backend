"""Feed domain Pydantic V2 schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContentType, PostStatus, PostVisibility


class PostSummary(BaseModel):
    """Lightweight post card for feed listings.

    For the full post (with edit history, viewer-contextual flags), use GET /cms/posts/{id}.
    """

    model_config = ConfigDict(from_attributes=True)

    post_id: UUID
    author_id: UUID = Field(description="User ID of the author (identity_db reference).")
    content_type: ContentType
    title: str | None
    body: str | None
    media_urls: list[dict] | None = Field(
        default=None, description="Array of {url, type, thumbnail}."
    )
    link_preview: dict | None = Field(
        default=None, description="{url, og_title, og_image, og_description}."
    )
    visibility: PostVisibility
    status: PostStatus = Field(description="PUBLISHED or EDITED for feed items.")
    specialty_tags: list[str] | None
    like_count: int
    comment_count: int
    share_count: int
    bookmark_count: int
    channel_id: UUID | None
    original_post_id: UUID | None = Field(
        default=None, description="For REPOST type: ID of the original post."
    )
    created_at: datetime
    updated_at: datetime


class FeedResponse(BaseModel):
    """Offset-paginated feed response."""

    items: list[PostSummary]
    total: int = Field(description="Total matching posts.")
    limit: int = Field(description="Requested page size.")
    offset: int = Field(description="Requested offset.")


class ChannelFeedResponse(BaseModel):
    """Feed response scoped to a specific channel."""

    items: list[PostSummary]
    total: int
    limit: int
    offset: int
    channel_id: UUID = Field(description="Channel these posts belong to.")
