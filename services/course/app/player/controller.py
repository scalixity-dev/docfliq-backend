"""Player controller — maps service results to HTTP responses."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import (
    CloudFrontSigningError,
    ContentNotAccessibleError,
    LessonGatedError,
    LessonNotFoundError,
    ModuleLockedError,
    NotEnrolledError,
    ScormSessionAlreadyCompletedError,
    ScormSessionNotFoundError,
)
from app.player import service
from app.player.schemas import (
    CourseProgressDetailResponse,
    DocumentHeartbeatRequest,
    DocumentHeartbeatResponse,
    HeartbeatRequest,
    LessonContentResponse,
    PresentationHeartbeatRequest,
    PresentationHeartbeatResponse,
    ScormApiLogRequest,
    ScormCommitRequest,
    ScormRuntimeDataResponse,
    ScormSessionResponse,
    VideoHeartbeatResponse,
)


def _handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ContentNotAccessibleError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Content not accessible. Enrollment required.",
        )
    if isinstance(exc, NotEnrolledError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled in this course.",
        )
    if isinstance(exc, ScormSessionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ScormSessionAlreadyCompletedError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SCORM session already completed.",
        )
    if isinstance(exc, LessonGatedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    if isinstance(exc, ModuleLockedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    if isinstance(exc, CloudFrontSigningError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Content delivery error.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error.",
    )


async def get_lesson_content(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    settings: Settings,
    redis: Redis | None = None,
) -> LessonContentResponse:
    try:
        result = await service.get_lesson_content(
            db, lesson_id, user_id, settings, redis,
        )
        return LessonContentResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def video_heartbeat(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    body: HeartbeatRequest,
    redis: Redis | None = None,
) -> VideoHeartbeatResponse:
    try:
        result = await service.process_video_heartbeat(
            db,
            lesson_id,
            user_id,
            position_secs=body.position_secs,
            watched_intervals=body.watched_intervals,
            playback_rate=body.playback_rate,
            redis=redis,
        )
        return VideoHeartbeatResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def document_heartbeat(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    body: DocumentHeartbeatRequest,
    redis: Redis | None = None,
) -> DocumentHeartbeatResponse:
    try:
        result = await service.process_document_heartbeat(
            db,
            lesson_id,
            user_id,
            current_page=body.current_page,
            pages_viewed=body.pages_viewed,
            redis=redis,
        )
        return DocumentHeartbeatResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def scorm_commit(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
    body: ScormCommitRequest,
    redis: Redis | None = None,
) -> ScormSessionResponse:
    try:
        session = await service.commit_scorm_data(
            db, session_id, user_id, **body.model_dump(), redis=redis,
        )
        return ScormSessionResponse.model_validate(session)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_detailed_progress(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> CourseProgressDetailResponse:
    try:
        result = await service.get_detailed_course_progress(db, course_id, user_id)
        return CourseProgressDetailResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Presentation heartbeat
# ---------------------------------------------------------------------------


async def presentation_heartbeat(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    body: PresentationHeartbeatRequest,
    redis: Redis | None = None,
) -> PresentationHeartbeatResponse:
    try:
        result = await service.process_presentation_heartbeat(
            db,
            lesson_id,
            user_id,
            current_slide=body.current_slide,
            slides_viewed=body.slides_viewed,
            redis=redis,
        )
        return PresentationHeartbeatResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# SCORM runtime data & API logging
# ---------------------------------------------------------------------------


async def get_scorm_runtime_data(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
) -> ScormRuntimeDataResponse:
    try:
        session = await service.get_scorm_runtime_data(db, session_id, user_id)
        api_logs = []
        if hasattr(session, "api_logs") and session.api_logs:
            api_logs = [
                {
                    "api_call": log.api_call,
                    "parameter": log.parameter,
                    "value": log.value,
                    "error_code": log.error_code,
                    "timestamp": log.timestamp,
                }
                for log in session.api_logs
            ]
        return ScormRuntimeDataResponse(
            session_id=session.session_id,
            tracking_data=session.tracking_data,
            suspend_data=session.suspend_data,
            api_logs=api_logs,
            status=session.status.value if hasattr(session.status, "value") else session.status,
            score_raw=session.score_raw,
            total_time_secs=session.total_time_secs,
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def log_scorm_api_call(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
    body: ScormApiLogRequest,
) -> dict:
    try:
        log = await service.log_scorm_api_call(
            db, session_id, user_id, **body.model_dump(),
        )
        return {"log_id": log.log_id, "timestamp": log.timestamp}
    except Exception as exc:
        raise _handle_domain_error(exc) from exc
