"""Interactions domain Pydantic V2 schemas.

All fields carry Field(description=...) for full OpenAPI documentation.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CommentStatus, ContentType, LikeTargetType, PostStatus, PostVisibility, ReportStatus, ReportTargetType, SharePlatform


# ---------------------------------------------------------------------------
# Like schemas
# ---------------------------------------------------------------------------


class LikeResponse(BaseModel):
    """Returned after a successful like action."""

    model_config = ConfigDict(from_attributes=True)

    like_id: UUID
    user_id: UUID
    target_type: LikeTargetType = Field(description="POST or COMMENT.")
    target_id: UUID = Field(description="ID of the liked post or comment.")
    created_at: datetime


class LikeCountResponse(BaseModel):
    """Like state after a like/unlike toggle."""

    target_type: LikeTargetType
    target_id: UUID
    liked: bool = Field(description="True if the current user has liked the target.")
    like_count: int = Field(description="Current denormalized like count.")


# ---------------------------------------------------------------------------
# Comment schemas
# ---------------------------------------------------------------------------


class CreateCommentRequest(BaseModel):
    """Request body for creating a comment or reply."""

    body: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Comment text (max 2,000 chars). Rate-limited: 5 per minute per user.",
    )
    parent_comment_id: UUID | None = Field(
        default=None,
        description=(
            "ID of the parent comment for replies. "
            "Nested replies are allowed at any depth."
        ),
    )


class UpdateCommentRequest(BaseModel):
    """Request body for editing a comment."""

    body: str = Field(..., min_length=1, max_length=2000, description="New comment text.")


class CommentResponse(BaseModel):
    """Full comment representation."""

    model_config = ConfigDict(from_attributes=True)

    comment_id: UUID
    post_id: UUID
    author_id: UUID = Field(description="User ID of the commenter.")
    parent_comment_id: UUID | None = Field(
        default=None, description="Set for replies; null for top-level comments."
    )
    body: str
    mentioned_usernames: list[str] = Field(
        default_factory=list,
        description=(
            "Usernames tagged in the body using @username syntax. "
            "Extracted server-side, unique and ordered by first appearance."
        ),
    )
    like_count: int
    status: CommentStatus
    created_at: datetime

    @model_validator(mode="after")
    def populate_mentions(self) -> "CommentResponse":
        seen: set[str] = set()
        mentions: list[str] = []
        for username in re.findall(r"(?<!\w)@([a-zA-Z0-9_]{1,30})", self.body):
            normalized = username.lower()
            if normalized not in seen:
                seen.add(normalized)
                mentions.append(normalized)
        self.mentioned_usernames = mentions
        return self


class CommentListResponse(BaseModel):
    """Offset-paginated list of active comments (top-level and nested)."""

    items: list[CommentResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Bookmark schemas
# ---------------------------------------------------------------------------


class BookmarkResponse(BaseModel):
    """Returned after a bookmark action."""

    model_config = ConfigDict(from_attributes=True)

    bookmark_id: UUID
    user_id: UUID
    post_id: UUID
    created_at: datetime


class BookmarkListResponse(BaseModel):
    """Offset-paginated list of a user's bookmarks."""

    items: list[BookmarkResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Repost schemas
# ---------------------------------------------------------------------------


class RepostCreate(BaseModel):
    """Request body for creating an in-app repost."""

    body: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional commentary added to the repost.",
    )
    visibility: PostVisibility = Field(
        default=PostVisibility.PUBLIC,
        description="Visibility of the repost in the sharer's feed.",
    )


class RepostResponse(BaseModel):
    """The newly created REPOST post."""

    model_config = ConfigDict(from_attributes=True)

    post_id: UUID
    author_id: UUID
    content_type: ContentType
    original_post_id: UUID = Field(description="ID of the original (root) post.")
    body: str | None
    visibility: PostVisibility
    status: PostStatus
    share_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Share (external) schemas
# ---------------------------------------------------------------------------


class CreateShareRequest(BaseModel):
    """Request body for tracking an external share (URL copy)."""

    platform: SharePlatform = Field(
        default=SharePlatform.COPY_LINK,
        description="Platform where the post was shared: APP, WHATSAPP, TWITTER, COPY_LINK.",
    )


class ShareResponse(BaseModel):
    """Returned after an external share is tracked."""

    model_config = ConfigDict(from_attributes=True)

    share_id: UUID
    user_id: UUID
    post_id: UUID
    platform: str | None = Field(description="Platform enum value as string.")
    created_at: datetime


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class CreateReportRequest(BaseModel):
    """Request body for reporting content or a user."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Description of the violation (min 5, max 255 chars).",
    )


class ReportResponse(BaseModel):
    """Returned after a report is submitted."""

    model_config = ConfigDict(from_attributes=True)

    report_id: UUID
    reporter_id: UUID
    target_type: ReportTargetType
    target_id: UUID
    reason: str
    status: ReportStatus = Field(description="Initial status is always OPEN.")
    created_at: datetime
