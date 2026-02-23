"""
Social graph domain — Pydantic V2 request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.constants import UserRole, VerificationStatus
from app.social_graph.constants import ReportStatus, ReportTargetType


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── Embedded user reference (used inside list items) ───────────────────────────

class SocialUserRef(BaseModel):
    """Minimal user profile embedded in follow/block/mute list items."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    role: UserRole
    specialty: str | None
    profile_image_url: str | None
    verification_status: VerificationStatus


# ── Follow ─────────────────────────────────────────────────────────────────────

class FollowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID           # follow_id
    user: SocialUserRef     # the other party (following or follower depending on context)
    created_at: datetime
    is_followed_by_me: bool  # does the current authed user follow this person?


class FollowListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[FollowListItem]
    total: int
    page: int
    size: int


# ── Block / Mute ───────────────────────────────────────────────────────────────

class SocialRelationItem(BaseModel):
    """Generic item for blocked / muted lists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user: SocialUserRef
    created_at: datetime


class SocialRelationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SocialRelationItem]
    total: int
    page: int
    size: int


# ── Suggestions ───────────────────────────────────────────────────────────────

class SuggestionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SocialUserRef]


# ── Report ─────────────────────────────────────────────────────────────────────

class ReportRequest(_Base):
    target_type: ReportTargetType
    target_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=255)


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ReportStatus
    created_at: datetime


# ── Admin report schemas ───────────────────────────────────────────────────────

class AdminReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter_id: uuid.UUID
    target_type: ReportTargetType
    target_id: uuid.UUID
    reason: str
    status: ReportStatus
    reviewed_by: uuid.UUID | None
    action_taken: str | None
    created_at: datetime


class AdminReportListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[AdminReportItem]
    total: int
    page: int
    size: int


class AdminReportReviewRequest(_Base):
    status: Literal["reviewed", "actioned", "dismissed"]
    action_taken: str | None = Field(None, max_length=100)
