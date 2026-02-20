"""LMS controller — maps service results to HTTP responses, catches domain exceptions."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    AlreadyEnrolledError,
    CourseNotFoundError,
    CourseNotPublishedError,
    EnrollmentNotFoundError,
    InvalidStatusTransitionError,
    LessonNotFoundError,
    ModuleNotFoundError,
    NotCourseOwnerError,
    NotEnrolledError,
    PaymentRequiredError,
    RefundNotEligibleError,
)
from app.lms import service
from app.lms.schemas import (
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseSummary,
    CreateCourseRequest,
    CreateEnrollmentRequest,
    CreateLessonRequest,
    CreateModuleRequest,
    EnrollmentDetailResponse,
    EnrollmentResponse,
    LessonProgressResponse,
    LessonResponse,
    ModuleResponse,
    ModuleWithLessonsResponse,
    UpdateCourseRequest,
    UpdateLessonRequest,
    UpdateModuleRequest,
    UpdateProgressRequest,
)
from app.models.enums import CourseStatus, EnrollmentStatus, PricingType


def _handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (CourseNotFoundError, ModuleNotFoundError, LessonNotFoundError, EnrollmentNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NotCourseOwnerError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the course instructor.")
    if isinstance(exc, AlreadyEnrolledError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already enrolled in this course.")
    if isinstance(exc, CourseNotPublishedError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course is not published.")
    if isinstance(exc, PaymentRequiredError):
        return HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Payment required for this course.")
    if isinstance(exc, NotEnrolledError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course.")
    if isinstance(exc, InvalidStatusTransitionError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, RefundNotEligibleError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund not eligible.")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error.")


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


async def create_course(
    db: AsyncSession,
    instructor_id: UUID,
    body: CreateCourseRequest,
) -> CourseResponse:
    try:
        course = await service.create_course(
            db, instructor_id, **body.model_dump(),
        )
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_course(db: AsyncSession, course_id: UUID) -> CourseResponse:
    try:
        course = await service.get_course_by_id(db, course_id)
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_course_by_slug(db: AsyncSession, slug: str) -> CourseResponse:
    try:
        course = await service.get_course_by_slug(db, slug)
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_course_detail(db: AsyncSession, course_id: UUID) -> CourseDetailResponse:
    try:
        course, modules = await service.get_course_detail(db, course_id)
        module_responses = []
        for m in modules:
            lessons = sorted(m.lessons, key=lambda l: l.sort_order) if m.lessons else []
            module_responses.append(
                ModuleWithLessonsResponse(
                    module_id=m.module_id,
                    course_id=m.course_id,
                    title=m.title,
                    sort_order=m.sort_order,
                    lessons=[LessonResponse.model_validate(l) for l in lessons],
                    created_at=m.created_at,
                )
            )
        return CourseDetailResponse(
            course=CourseResponse.model_validate(course),
            modules=module_responses,
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def list_courses(
    db: AsyncSession,
    *,
    status: CourseStatus | None,
    category: str | None,
    specialty_tag: str | None,
    pricing_type: PricingType | None,
    search: str | None,
    limit: int,
    offset: int,
) -> CourseListResponse:
    courses, total = await service.list_courses(
        db,
        status=status,
        category=category,
        specialty_tag=specialty_tag,
        pricing_type=pricing_type,
        search=search,
        limit=limit,
        offset=offset,
    )
    return CourseListResponse(
        items=[CourseSummary.model_validate(c) for c in courses],
        total=total,
        limit=limit,
        offset=offset,
    )


async def update_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    body: UpdateCourseRequest,
) -> CourseResponse:
    try:
        course = await service.update_course(
            db, course_id, instructor_id,
            **body.model_dump(exclude_unset=True),
        )
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def publish_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> CourseResponse:
    try:
        course = await service.publish_course(db, course_id, instructor_id)
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def archive_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> CourseResponse:
    try:
        course = await service.archive_course(db, course_id, instructor_id)
        return CourseResponse.model_validate(course)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


async def create_module(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    body: CreateModuleRequest,
) -> ModuleResponse:
    try:
        module = await service.create_module(
            db, course_id, instructor_id,
            title=body.title,
            sort_order=body.sort_order,
        )
        return ModuleResponse.model_validate(module)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def update_module(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
    body: UpdateModuleRequest,
) -> ModuleResponse:
    try:
        module = await service.update_module(
            db, module_id, instructor_id,
            **body.model_dump(exclude_unset=True),
        )
        return ModuleResponse.model_validate(module)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def delete_module(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
) -> None:
    try:
        await service.delete_module(db, module_id, instructor_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def reorder_modules(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    module_ids: list[UUID],
) -> list[ModuleResponse]:
    try:
        modules = await service.reorder_modules(
            db, course_id, instructor_id, module_ids=module_ids,
        )
        return [ModuleResponse.model_validate(m) for m in modules]
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Lesson
# ---------------------------------------------------------------------------


async def create_lesson(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
    body: CreateLessonRequest,
) -> LessonResponse:
    try:
        lesson = await service.create_lesson(
            db, module_id, instructor_id, **body.model_dump(),
        )
        return LessonResponse.model_validate(lesson)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def update_lesson(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
    body: UpdateLessonRequest,
) -> LessonResponse:
    try:
        lesson = await service.update_lesson(
            db, lesson_id, instructor_id,
            **body.model_dump(exclude_unset=True),
        )
        return LessonResponse.model_validate(lesson)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def delete_lesson(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
) -> None:
    try:
        await service.delete_lesson(db, lesson_id, instructor_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


async def enroll_free(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> EnrollmentResponse:
    try:
        enrollment = await service.enroll_free(db, course_id, user_id)
        return EnrollmentResponse.model_validate(enrollment)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def enroll_paid(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
    body: CreateEnrollmentRequest,
) -> EnrollmentResponse:
    try:
        if body.payment_id is None:
            raise PaymentRequiredError()
        enrollment = await service.enroll_paid(
            db, course_id, user_id, body.payment_id,
        )
        return EnrollmentResponse.model_validate(enrollment)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_my_enrollments(
    db: AsyncSession,
    user_id: UUID,
    *,
    enrollment_status: EnrollmentStatus | None,
    limit: int,
    offset: int,
) -> dict:
    enrollments, total = await service.get_my_enrollments(
        db, user_id, status=enrollment_status, limit=limit, offset=offset,
    )
    return {
        "items": [EnrollmentResponse.model_validate(e) for e in enrollments],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def get_enrollment_detail(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
) -> EnrollmentDetailResponse:
    try:
        enrollment, progress = await service.get_enrollment_detail(
            db, enrollment_id, user_id,
        )
        return EnrollmentDetailResponse(
            enrollment=EnrollmentResponse.model_validate(enrollment),
            lesson_progress=[LessonProgressResponse.model_validate(p) for p in progress],
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def drop_enrollment(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
) -> EnrollmentResponse:
    try:
        enrollment = await service.drop_enrollment(db, enrollment_id, user_id)
        return EnrollmentResponse.model_validate(enrollment)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


async def update_lesson_progress(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    *,
    watch_duration_secs: int | None,
    completed: bool,
) -> LessonProgressResponse:
    try:
        progress = await service.update_lesson_progress(
            db, lesson_id, user_id,
            watch_duration_secs=watch_duration_secs,
            completed=completed,
        )
        return LessonProgressResponse.model_validate(progress)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def update_resume_position(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
    body: UpdateProgressRequest,
) -> EnrollmentResponse:
    try:
        enrollment = await service.update_resume_position(
            db, enrollment_id, user_id,
            last_lesson_id=body.last_lesson_id,
            last_position_secs=body.last_position_secs,
        )
        return EnrollmentResponse.model_validate(enrollment)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_course_progress(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> EnrollmentDetailResponse:
    try:
        enrollment, progress = await service.get_course_progress(
            db, course_id, user_id,
        )
        return EnrollmentDetailResponse(
            enrollment=EnrollmentResponse.model_validate(enrollment),
            lesson_progress=[LessonProgressResponse.model_validate(p) for p in progress],
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc
