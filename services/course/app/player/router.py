"""Player router — content delivery, heartbeat, SCORM, progress.

HTTP layer only. Delegates to controller for business logic.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.dependencies import get_current_user, get_redis, get_settings
from app.player import controller
from app.player.schemas import (
    CourseProgressDetailResponse,
    DocumentHeartbeatRequest,
    DocumentHeartbeatResponse,
    HeartbeatRequest,
    LessonContentResponse,
    ScormCommitRequest,
    ScormSessionResponse,
    VideoHeartbeatResponse,
)

router = APIRouter(prefix="/player", tags=["Player"])


@router.get(
    "/lessons/{lesson_id}/content",
    response_model=LessonContentResponse,
    summary="Get lesson content with signed URLs",
    description="Returns lesson content with CloudFront signed URLs for secure playback. "
    "Includes resume position. For VIDEO: HLS manifest + signed cookies. "
    "For PDF: signed download URL. For SCORM: signed launch URL + session ID. "
    "Preview lessons accessible without enrollment.",
)
async def get_lesson_content(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> LessonContentResponse:
    return await controller.get_lesson_content(db, lesson_id, user_id, settings, redis)


@router.post(
    "/lessons/{lesson_id}/heartbeat",
    response_model=VideoHeartbeatResponse,
    summary="Video playback heartbeat (every 10s)",
    description="Client sends this every 10 seconds during video playback. "
    "Tracks watch position and watched intervals for anti-cheat progress. "
    "Seeking forward does NOT count as watched. "
    "Returns current watched percentage and completion status.",
)
async def video_heartbeat(
    lesson_id: UUID,
    body: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> VideoHeartbeatResponse:
    return await controller.video_heartbeat(db, lesson_id, user_id, body, redis)


@router.post(
    "/lessons/{lesson_id}/heartbeat/document",
    response_model=DocumentHeartbeatResponse,
    summary="Document reading heartbeat",
    description="Client sends on PDF/document scroll events. "
    "Tracks pages viewed vs total pages. "
    "Returns pages progress percentage.",
)
async def document_heartbeat(
    lesson_id: UUID,
    body: DocumentHeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> DocumentHeartbeatResponse:
    return await controller.document_heartbeat(db, lesson_id, user_id, body, redis)


@router.post(
    "/scorm/sessions/{session_id}/commit",
    response_model=ScormSessionResponse,
    summary="SCORM runtime data commit",
    description="SCORM JS runtime API calls LMSCommit, which posts "
    "the cmi.* tracking data to this endpoint. "
    "Handles both SCORM 1.2 and 2004 data models via JSONB.",
)
async def scorm_commit(
    session_id: UUID,
    body: ScormCommitRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> ScormSessionResponse:
    return await controller.scorm_commit(db, session_id, user_id, body, redis)


@router.get(
    "/courses/{course_id}/progress/detail",
    response_model=CourseProgressDetailResponse,
    summary="Get detailed course progress with per-module breakdown",
    description="Returns weighted progress at course, module, and lesson level. "
    "Includes watched_pct for videos, pages_pct for documents, "
    "quiz scores, and SCORM completion status.",
)
async def get_detailed_progress(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> CourseProgressDetailResponse:
    return await controller.get_detailed_progress(db, course_id, user_id)
