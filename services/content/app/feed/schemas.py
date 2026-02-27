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
    hashtags: list[str] | None = None
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


# ---------------------------------------------------------------------------
# For You feed (ranked, offset-based within a 7-day candidate window)
# ---------------------------------------------------------------------------


class ForYouFeedResponse(BaseModel):
    """Ranked personalised feed response.

    Scoring: 40% recency decay (half-life 24 h) + 30% specialty tag overlap
    + 30% author affinity from past interactions.

    is_cold_start=True when the user has fewer than 10 interactions; the feed
    is then composed of editor picks (20%), trending posts (40%), and
    specialty-matched posts (40%) from onboarding interests.
    """

    items: list[PostSummary]
    total: int = Field(description="Total scored candidates in the 7-day window.")
    limit: int
    offset: int
    is_cold_start: bool = Field(
        default=False,
        description="True when cold-start logic was used instead of personalised ranking.",
    )


# ---------------------------------------------------------------------------
# Following tab (cursor-based, strictly reverse-chronological)
# ---------------------------------------------------------------------------


class FollowingFeedResponse(BaseModel):
    """Cursor-paginated feed of posts from followed accounts.

    Hard cap: 500 posts per feed session. When is_exhausted=True the client
    should show 'You are all caught up'.
    """

    items: list[PostSummary]
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Opaque cursor for the next page. Pass as the `cursor` query param. "
            "Null when there are no more posts or the 500-post hard cap is reached."
        ),
    )
    has_more: bool
    is_exhausted: bool = Field(
        default=False,
        description="True when the 500-post session hard cap has been reached.",
    )


# ---------------------------------------------------------------------------
# Trending feed
# ---------------------------------------------------------------------------


class TrendingFeedResponse(BaseModel):
    """Top-engagement posts in the last 48 hours, cached for 5 minutes."""

    items: list[PostSummary]
    cached: bool = Field(
        default=False,
        description="True when the response was served from the Redis cache.",
    )


# ---------------------------------------------------------------------------
# Editor Picks
# ---------------------------------------------------------------------------


class EditorPickCreate(BaseModel):
    """Request body for adding a post to the editor-picks list."""

    post_id: UUID
    priority: int = Field(
        default=0,
        ge=0,
        description="Display priority — lower integer shown first (0 = highest).",
    )


class EditorPickResponse(BaseModel):
    """Response for a single editor pick record."""

    model_config = ConfigDict(from_attributes=True)

    pick_id: UUID
    post_id: UUID
    added_by: UUID
    priority: int
    is_active: bool
    created_at: datetime
