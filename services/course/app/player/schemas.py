"""Player domain Pydantic V2 schemas.

Covers content delivery, heartbeat, SCORM tracking, and progress detail.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LessonType


# ---------------------------------------------------------------------------
# Heartbeat requests
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    """Client sends this every 10 seconds during video playback."""

    model_config = ConfigDict(str_strip_whitespace=True)

    position_secs: int = Field(ge=0, description="Current playback position in seconds.")
    watched_intervals: list[list[int]] = Field(
        description="Array of [start_sec, end_sec] intervals the user actually watched. "
        "Client tracks this locally and sends cumulative intervals.",
    )
    playback_rate: float = Field(
        default=1.0, ge=0.25, le=3.0, description="Playback speed.",
    )


class DocumentHeartbeatRequest(BaseModel):
    """Client sends this on scroll for PDF/document lessons."""

    model_config = ConfigDict(str_strip_whitespace=True)

    current_page: int = Field(ge=1, description="Page currently visible.")
    pages_viewed: list[int] = Field(
        description="Array of page numbers the user has scrolled to (1-based).",
    )


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class ResumePositionResponse(BaseModel):
    lesson_id: UUID
    lesson_type: LessonType
    position_secs: int
    watched_intervals: list[list[int]] | None = None
    pages_viewed: list[int] | None = None


# ---------------------------------------------------------------------------
# Content delivery
# ---------------------------------------------------------------------------


class LessonContentResponse(BaseModel):
    """Lesson content with signed URLs for authorised playback."""

    lesson_id: UUID
    lesson_type: LessonType
    title: str
    duration_secs: int | None = None
    total_pages: int | None = None

    signed_content_url: str | None = Field(
        default=None,
        description="CloudFront signed URL for direct content (PDF, single video file).",
    )
    hls_manifest_url: str | None = Field(
        default=None,
        description="CloudFront signed URL for HLS adaptive bitrate manifest.",
    )
    signed_cookies: dict[str, str] | None = Field(
        default=None,
        description="CloudFront signed cookies for HLS segment authorisation.",
    )
    scorm_launch_url: str | None = Field(
        default=None,
        description="Signed URL to SCORM launch page.",
    )
    scorm_session_id: UUID | None = Field(
        default=None,
        description="Active SCORM session ID for tracking API calls.",
    )
    content_body: str | None = None
    resume: ResumePositionResponse | None = None


# ---------------------------------------------------------------------------
# SCORM
# ---------------------------------------------------------------------------


class ScormCommitRequest(BaseModel):
    """SCORM runtime API data commit (cmi.* data model)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    tracking_data: dict = Field(description="SCORM cmi.* data model as JSONB.")
    score_raw: int | None = Field(default=None, ge=0, le=100)
    score_max: int | None = Field(default=None, ge=0)
    score_min: int | None = Field(default=None, ge=0)
    completion_status: str | None = Field(
        default=None,
        description="SCORM completion status: 'completed', 'incomplete', 'not attempted'.",
    )
    success_status: str | None = Field(
        default=None,
        description="SCORM success status: 'passed', 'failed', 'unknown'.",
    )
    total_time_secs: int | None = Field(default=None, ge=0)


class ScormSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    enrollment_id: UUID
    lesson_id: UUID
    status: str
    tracking_data: dict
    score_raw: int | None
    total_time_secs: int | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Heartbeat responses
# ---------------------------------------------------------------------------


class VideoHeartbeatResponse(BaseModel):
    position_secs: int
    watched_pct: float
    total_watched_secs: int
    is_completed: bool


class DocumentHeartbeatResponse(BaseModel):
    pages_viewed: list[int]
    pages_pct: float
    is_completed: bool


# ---------------------------------------------------------------------------
# Progress detail
# ---------------------------------------------------------------------------


class LessonProgressDetail(BaseModel):
    lesson_id: UUID
    lesson_type: LessonType
    title: str
    status: str
    watched_pct: Decimal | None = None
    pages_pct: Decimal | None = None
    quiz_score: int | None = None
    quiz_passed: bool | None = None
    scorm_score: int | None = None
    completed_at: datetime | None = None


class ModuleProgressResponse(BaseModel):
    module_id: UUID
    title: str
    progress_pct: Decimal
    lessons: list[LessonProgressDetail]


class CourseProgressDetailResponse(BaseModel):
    enrollment_id: UUID
    course_id: UUID
    overall_progress_pct: Decimal
    status: str
    modules: list[ModuleProgressResponse]
    completion_logic: dict
