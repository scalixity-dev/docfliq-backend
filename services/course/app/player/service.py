"""Player service — video delivery, heartbeat, SCORM, progress.

Pure business logic, no FastAPI imports.
Redis is passed as ``Redis | None`` and all Redis ops are best-effort.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.exceptions import (
    ContentNotAccessibleError,
    LessonNotFoundError,
    NotEnrolledError,
    ScormSessionAlreadyCompletedError,
    ScormSessionNotFoundError,
)
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import (
    EnrollmentStatus,
    LessonProgressStatus,
    LessonType,
    ScormSessionStatus,
)
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.scorm_session import ScormSession
from app.player import cache as player_cache
from app.player.cloudfront import generate_signed_cookies, generate_signed_url


# ---------------------------------------------------------------------------
# Content delivery with CloudFront signing
# ---------------------------------------------------------------------------


async def get_lesson_content(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    settings: Settings,
    redis: Redis | None = None,
) -> dict:
    """Load lesson content with signed URLs and resume position."""
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError(str(lesson_id))

    module = await db.get(CourseModule, lesson.module_id)
    course = await db.get(Course, module.course_id)

    enrollment = await _get_enrollment(db, user_id, course.course_id)
    is_paid = course.pricing_type.value == "PAID"

    if enrollment is None and not lesson.is_preview:
        raise ContentNotAccessibleError()

    if enrollment is not None and enrollment.status == EnrollmentStatus.DROPPED:
        raise NotEnrolledError()

    result: dict = {
        "lesson_id": lesson.lesson_id,
        "lesson_type": lesson.lesson_type,
        "title": lesson.title,
        "duration_secs": lesson.duration_secs,
        "total_pages": lesson.total_pages,
        "signed_content_url": None,
        "hls_manifest_url": None,
        "signed_cookies": None,
        "scorm_launch_url": None,
        "scorm_session_id": None,
        "content_body": None,
        "resume": None,
    }

    expiry = (
        settings.cloudfront_signed_url_expiry_secs
        if is_paid
        else settings.cloudfront_preview_expiry_secs
    )

    if lesson.lesson_type == LessonType.VIDEO and lesson.hls_manifest_key:
        manifest_url = f"https://{settings.cloudfront_domain}/{lesson.hls_manifest_key}"
        result["hls_manifest_url"] = generate_signed_url(
            manifest_url,
            settings.cloudfront_key_pair_id,
            settings.cloudfront_private_key_path,
            expiry,
        )
        hls_dir = "/".join(lesson.hls_manifest_key.split("/")[:-1]) + "/*"
        pattern = f"https://{settings.cloudfront_domain}/{hls_dir}"
        result["signed_cookies"] = generate_signed_cookies(
            pattern,
            settings.cloudfront_key_pair_id,
            settings.cloudfront_private_key_path,
            expiry,
        )
    elif lesson.lesson_type == LessonType.VIDEO and lesson.content_url:
        result["signed_content_url"] = generate_signed_url(
            f"https://{settings.cloudfront_domain}/{lesson.content_url}",
            settings.cloudfront_key_pair_id,
            settings.cloudfront_private_key_path,
            expiry,
        )
    elif lesson.lesson_type == LessonType.PDF and lesson.content_url:
        result["signed_content_url"] = generate_signed_url(
            f"https://{settings.cloudfront_domain}/{lesson.content_url}",
            settings.cloudfront_key_pair_id,
            settings.cloudfront_private_key_path,
            expiry,
        )
    elif lesson.lesson_type == LessonType.TEXT:
        result["content_body"] = lesson.content_body
    elif lesson.lesson_type == LessonType.SCORM and enrollment is not None:
        session = await _get_or_create_scorm_session(db, enrollment.enrollment_id, lesson)
        result["scorm_session_id"] = session.session_id
        if lesson.scorm_entry_url:
            result["scorm_launch_url"] = generate_signed_url(
                f"https://{settings.cloudfront_domain}/{lesson.scorm_entry_url}",
                settings.cloudfront_key_pair_id,
                settings.cloudfront_private_key_path,
                expiry,
            )

    # Resume position
    if enrollment is not None:
        result["resume"] = await _get_resume(db, user_id, lesson, enrollment, redis)
        enrollment.last_lesson_id = lesson.lesson_id
        await db.flush()

    return result


# ---------------------------------------------------------------------------
# Video heartbeat (anti-cheat interval tracking)
# ---------------------------------------------------------------------------


async def process_video_heartbeat(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    *,
    position_secs: int,
    watched_intervals: list[list[int]],
    playback_rate: float,
    redis: Redis | None = None,
) -> dict:
    """Process a client heartbeat for video lessons.

    Anti-cheat: only the union of watched intervals / lesson duration
    counts toward ``watched_pct``.  Seeking forward creates gaps that
    are NOT counted.
    """
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError(str(lesson_id))
    if lesson.lesson_type != LessonType.VIDEO:
        raise ContentNotAccessibleError()

    module = await db.get(CourseModule, lesson.module_id)
    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    merged = _merge_intervals(watched_intervals)
    total_watched_secs = sum(end - start for start, end in merged)
    duration = lesson.duration_secs or (lesson.duration_mins * 60 if lesson.duration_mins else 0)
    watched_pct = (
        Decimal(str(round(min(total_watched_secs / duration * 100, 100), 2)))
        if duration > 0
        else Decimal("0")
    )

    # Redis fast path
    if redis is not None:
        try:
            await player_cache.store_heartbeat(
                user_id, lesson_id, position_secs, json.dumps(merged), redis,
            )
            await player_cache.set_resume_position(
                user_id, lesson_id, position_secs, LessonType.VIDEO.value, redis,
            )
        except Exception:
            pass  # best-effort

    # Postgres write
    progress = await _upsert_lesson_progress(db, enrollment.enrollment_id, lesson_id)
    progress.watch_duration_secs = total_watched_secs
    progress.watched_intervals = merged
    progress.watched_pct = watched_pct

    enrollment.last_lesson_id = lesson_id
    enrollment.last_position_secs = position_secs

    course = await db.get(Course, enrollment.course_id)
    threshold = _get_video_completion_threshold(course.completion_logic)
    if watched_pct >= threshold and progress.status != LessonProgressStatus.COMPLETED:
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)
    elif progress.status == LessonProgressStatus.NOT_STARTED:
        progress.status = LessonProgressStatus.IN_PROGRESS

    await db.flush()
    await _recalculate_weighted_progress(db, enrollment, course)

    return {
        "position_secs": position_secs,
        "watched_pct": float(watched_pct),
        "total_watched_secs": total_watched_secs,
        "is_completed": progress.status == LessonProgressStatus.COMPLETED,
    }


# ---------------------------------------------------------------------------
# Document heartbeat (PDF / text)
# ---------------------------------------------------------------------------


async def process_document_heartbeat(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    *,
    current_page: int,
    pages_viewed: list[int],
    redis: Redis | None = None,
) -> dict:
    """Track document reading progress."""
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError(str(lesson_id))

    module = await db.get(CourseModule, lesson.module_id)
    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    total_pages = lesson.total_pages or 1
    unique_viewed = sorted(set(pages_viewed))
    pages_pct = Decimal(str(round(min(len(unique_viewed) / total_pages * 100, 100), 2)))

    if redis is not None:
        try:
            await player_cache.set_resume_position(
                user_id, lesson_id, current_page, lesson.lesson_type.value, redis,
            )
        except Exception:
            pass

    progress = await _upsert_lesson_progress(db, enrollment.enrollment_id, lesson_id)
    progress.pages_viewed = {"viewed": unique_viewed, "total": total_pages}
    progress.pages_pct = pages_pct

    course = await db.get(Course, enrollment.course_id)
    doc_threshold = _get_doc_completion_threshold(course.completion_logic)
    if pages_pct >= doc_threshold and progress.status != LessonProgressStatus.COMPLETED:
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)
    elif progress.status == LessonProgressStatus.NOT_STARTED:
        progress.status = LessonProgressStatus.IN_PROGRESS

    await db.flush()
    await _recalculate_weighted_progress(db, enrollment, course)

    return {
        "pages_viewed": unique_viewed,
        "pages_pct": float(pages_pct),
        "is_completed": progress.status == LessonProgressStatus.COMPLETED,
    }


# ---------------------------------------------------------------------------
# SCORM session management
# ---------------------------------------------------------------------------


async def _get_or_create_scorm_session(
    db: AsyncSession, enrollment_id: UUID, lesson: Lesson,
) -> ScormSession:
    stmt = select(ScormSession).where(
        ScormSession.enrollment_id == enrollment_id,
        ScormSession.lesson_id == lesson.lesson_id,
        ScormSession.status.in_([
            ScormSessionStatus.INITIALIZED,
            ScormSessionStatus.IN_PROGRESS,
        ]),
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is not None:
        return session

    session = ScormSession(
        enrollment_id=enrollment_id,
        lesson_id=lesson.lesson_id,
        status=ScormSessionStatus.INITIALIZED,
        tracking_data={},
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def commit_scorm_data(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
    *,
    tracking_data: dict,
    score_raw: int | None,
    score_max: int | None,
    score_min: int | None,
    completion_status: str | None,
    success_status: str | None,
    total_time_secs: int | None,
    redis: Redis | None = None,
) -> ScormSession:
    """Receive SCORM runtime API commit (LMSCommit / Commit)."""
    session = await db.get(ScormSession, session_id)
    if session is None:
        raise ScormSessionNotFoundError(str(session_id))
    if session.status == ScormSessionStatus.COMPLETED:
        raise ScormSessionAlreadyCompletedError()

    merged = {**session.tracking_data, **tracking_data}
    session.tracking_data = merged
    if score_raw is not None:
        session.score_raw = score_raw
    if score_max is not None:
        session.score_max = score_max
    if score_min is not None:
        session.score_min = score_min
    if total_time_secs is not None:
        session.total_time_secs = total_time_secs

    if completion_status == "completed":
        session.status = ScormSessionStatus.COMPLETED
    elif session.status == ScormSessionStatus.INITIALIZED:
        session.status = ScormSessionStatus.IN_PROGRESS

    if success_status == "failed":
        session.status = ScormSessionStatus.FAILED

    await db.flush()
    await db.refresh(session)

    # Update lesson progress on SCORM completion
    if session.status == ScormSessionStatus.COMPLETED:
        progress = await _upsert_lesson_progress(
            db, session.enrollment_id, session.lesson_id,
        )
        progress.scorm_score = session.score_raw
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)
        await db.flush()

        enrollment = await db.get(Enrollment, session.enrollment_id)
        course = await db.get(Course, enrollment.course_id)
        await _recalculate_weighted_progress(db, enrollment, course)

    return session


# ---------------------------------------------------------------------------
# Weighted progress calculation (consumes completion_logic)
# ---------------------------------------------------------------------------


def _get_video_completion_threshold(completion_logic: dict) -> Decimal:
    return Decimal(str(completion_logic.get("video_watch_pct", 90)))


def _get_doc_completion_threshold(completion_logic: dict) -> Decimal:
    return Decimal(str(completion_logic.get("doc_read_pct", 90)))


async def _recalculate_weighted_progress(
    db: AsyncSession,
    enrollment: Enrollment,
    course: Course,
) -> None:
    """Weighted progress: VIDEO=watch%, PDF=pages%, QUIZ=pass, TEXT/SCORM=complete.

    ``completion_logic`` schema::

        {
            "video_watch_pct": 90,
            "doc_read_pct": 90,
            "score_threshold": 70,
            "pct_required": 100,
            "weights": {"VIDEO": 1.0, "PDF": 1.0, "TEXT": 0.5, "QUIZ": 1.5, "SCORM": 1.0}
        }
    """
    lesson_stmt = (
        select(Lesson)
        .join(CourseModule, Lesson.module_id == CourseModule.module_id)
        .where(CourseModule.course_id == course.course_id)
    )
    lesson_result = await db.execute(lesson_stmt)
    lessons = list(lesson_result.scalars().all())
    if not lessons:
        return

    progress_stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment.enrollment_id,
    )
    progress_result = await db.execute(progress_stmt)
    progress_map = {p.lesson_id: p for p in progress_result.scalars().all()}

    cl = course.completion_logic or {}
    video_threshold = Decimal(str(cl.get("video_watch_pct", 90)))
    doc_threshold = Decimal(str(cl.get("doc_read_pct", 90)))
    quiz_threshold = cl.get("score_threshold", None)
    pct_required = Decimal(str(cl.get("pct_required", 100)))
    custom_weights = cl.get("weights", {})

    default_weight = Decimal("1.0")
    total_weight = Decimal("0")
    earned_weight = Decimal("0")

    for lesson in lessons:
        lt = lesson.lesson_type.value if hasattr(lesson.lesson_type, "value") else lesson.lesson_type
        weight = Decimal(str(custom_weights.get(lt, default_weight)))
        total_weight += weight

        progress = progress_map.get(lesson.lesson_id)
        if progress is None:
            continue

        lesson_score = Decimal("0")

        if lt == "VIDEO":
            wp = progress.watched_pct or Decimal("0")
            lesson_score = min(wp / video_threshold, Decimal("1")) if video_threshold > 0 else Decimal("0")
        elif lt == "PDF":
            pp = progress.pages_pct or Decimal("0")
            lesson_score = min(pp / doc_threshold, Decimal("1")) if doc_threshold > 0 else Decimal("0")
        elif lt == "TEXT":
            lesson_score = Decimal("1") if progress.status == LessonProgressStatus.COMPLETED else Decimal("0")
        elif lt == "QUIZ":
            if progress.quiz_score is not None:
                threshold = quiz_threshold if quiz_threshold is not None else 70
                lesson_score = Decimal("1") if progress.quiz_score >= threshold else Decimal("0")
        elif lt == "SCORM":
            lesson_score = Decimal("1") if progress.status == LessonProgressStatus.COMPLETED else Decimal("0")

        earned_weight += weight * lesson_score

    if total_weight > 0:
        new_pct = (earned_weight / total_weight * 100).quantize(Decimal("0.01"))
    else:
        new_pct = Decimal("0.00")

    enrollment.progress_pct = new_pct

    if new_pct >= pct_required and enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)

    await db.flush()


# ---------------------------------------------------------------------------
# Detailed progress report
# ---------------------------------------------------------------------------


async def get_detailed_course_progress(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> dict:
    """Return per-module, per-lesson granular progress."""
    enrollment = await _get_enrollment(db, user_id, course_id)
    if enrollment is None:
        raise NotEnrolledError()

    course = await db.get(Course, course_id)

    module_stmt = (
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .options(selectinload(CourseModule.lessons))
        .order_by(CourseModule.sort_order)
    )
    module_result = await db.execute(module_stmt)
    modules = list(module_result.scalars().all())

    progress_stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment.enrollment_id,
    )
    progress_result = await db.execute(progress_stmt)
    progress_map = {p.lesson_id: p for p in progress_result.scalars().all()}

    cl = course.completion_logic or {}
    quiz_threshold = cl.get("score_threshold", 70)

    module_responses = []
    for module in modules:
        lessons = sorted(module.lessons, key=lambda l: l.sort_order) if module.lessons else []
        lesson_details = []
        module_earned = Decimal("0")
        module_total = Decimal("0")

        for lesson in lessons:
            p = progress_map.get(lesson.lesson_id)
            detail = {
                "lesson_id": lesson.lesson_id,
                "lesson_type": lesson.lesson_type,
                "title": lesson.title,
                "status": p.status.value if p else "NOT_STARTED",
                "watched_pct": p.watched_pct if p and p.watched_pct else None,
                "pages_pct": p.pages_pct if p and p.pages_pct else None,
                "quiz_score": p.quiz_score if p else None,
                "quiz_passed": (
                    p.quiz_score >= quiz_threshold
                    if p and p.quiz_score is not None
                    else None
                ),
                "scorm_score": p.scorm_score if p else None,
                "completed_at": p.completed_at if p else None,
            }
            lesson_details.append(detail)

            module_total += Decimal("1")
            if p and p.status == LessonProgressStatus.COMPLETED:
                module_earned += Decimal("1")

        module_pct = (
            (module_earned / module_total * 100).quantize(Decimal("0.01"))
            if module_total > 0
            else Decimal("0")
        )
        module_responses.append({
            "module_id": module.module_id,
            "title": module.title,
            "progress_pct": module_pct,
            "lessons": lesson_details,
        })

    return {
        "enrollment_id": enrollment.enrollment_id,
        "course_id": course_id,
        "overall_progress_pct": enrollment.progress_pct,
        "status": enrollment.status.value,
        "modules": module_responses,
        "completion_logic": course.completion_logic or {},
    }


# ---------------------------------------------------------------------------
# Anti-cheat interval merging
# ---------------------------------------------------------------------------


def _merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """Merge overlapping / adjacent intervals.

    Seeking forward creates a gap that is NOT counted.
    Only the union of actually watched segments counts.
    """
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged: list[list[int]] = [sorted_iv[0][:]]
    for start, end in sorted_iv[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_enrollment(
    db: AsyncSession, user_id: UUID, course_id: UUID,
) -> Enrollment | None:
    stmt = select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _upsert_lesson_progress(
    db: AsyncSession, enrollment_id: UUID, lesson_id: UUID,
) -> LessonProgress:
    stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment_id,
        LessonProgress.lesson_id == lesson_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = LessonProgress(
            enrollment_id=enrollment_id,
            lesson_id=lesson_id,
            status=LessonProgressStatus.NOT_STARTED,
        )
        db.add(progress)
        await db.flush()
    return progress


async def _get_resume(
    db: AsyncSession,
    user_id: UUID,
    lesson: Lesson,
    enrollment: Enrollment,
    redis: Redis | None,
) -> dict:
    """Get resume data. Redis first, DB fallback."""
    if redis is not None:
        try:
            cached = await player_cache.get_resume_position(
                user_id, lesson.lesson_id, redis,
            )
            if cached:
                return {
                    "lesson_id": lesson.lesson_id,
                    "lesson_type": lesson.lesson_type,
                    "position_secs": int(cached.get("position_secs", 0)),
                    "watched_intervals": None,
                    "pages_viewed": None,
                }
        except Exception:
            pass

    progress_stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment.enrollment_id,
        LessonProgress.lesson_id == lesson.lesson_id,
    )
    result = await db.execute(progress_stmt)
    progress = result.scalar_one_or_none()

    position = (
        enrollment.last_position_secs or 0
        if enrollment.last_lesson_id == lesson.lesson_id
        else 0
    )

    return {
        "lesson_id": lesson.lesson_id,
        "lesson_type": lesson.lesson_type,
        "position_secs": position,
        "watched_intervals": progress.watched_intervals if progress else None,
        "pages_viewed": (
            (progress.pages_viewed or {}).get("viewed") if progress else None
        ),
    }
