"""LMS router — HTTP layer only.

Defines all endpoints for course, module, lesson, enrollment, and progress management.
Delegates to controller for business logic orchestration.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user
from app.lms import controller
from app.lms.schemas import (
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CreateCourseRequest,
    CreateEnrollmentRequest,
    CreateLessonRequest,
    CreateModuleRequest,
    EnrollmentDetailResponse,
    EnrollmentResponse,
    LessonProgressResponse,
    LessonResponse,
    ModuleResponse,
    ReorderModulesRequest,
    UpdateCourseRequest,
    UpdateLessonProgressRequest,
    UpdateLessonRequest,
    UpdateModuleRequest,
    UpdateProgressRequest,
)
from app.models.enums import CourseStatus, EnrollmentStatus, PricingType
from app.pagination import OffsetPage

router = APIRouter(prefix="/lms", tags=["LMS"])


# ======================================================================
# Course endpoints
# ======================================================================


@router.post(
    "/courses",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new course",
    description="Instructor creates a new course (defaults to DRAFT status). "
    "Slug is auto-generated from title if not provided.",
)
async def create_course(
    body: CreateCourseRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> CourseResponse:
    return await controller.create_course(db, user_id, body)


@router.get(
    "/courses",
    response_model=CourseListResponse,
    summary="List / search courses (catalog)",
    description="Public course catalog with optional filters. "
    "Returns only PUBLISHED courses by default.",
)
async def list_courses(
    status_filter: CourseStatus | None = Query(None, alias="status", description="Filter by course status."),
    category: str | None = Query(None, description="Filter by category."),
    specialty_tag: str | None = Query(None, description="Filter by specialty tag."),
    pricing_type: PricingType | None = Query(None, description="FREE or PAID."),
    search: str | None = Query(None, description="Full-text search on title + description."),
    limit: int = Query(20, ge=1, le=100, description="Items per page."),
    offset: int = Query(0, ge=0, description="Number of items to skip."),
    db: AsyncSession = Depends(get_db),
) -> CourseListResponse:
    return await controller.list_courses(
        db,
        status=status_filter,
        category=category,
        specialty_tag=specialty_tag,
        pricing_type=pricing_type,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/courses/{course_id}",
    response_model=CourseResponse,
    summary="Get course by ID",
)
async def get_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    return await controller.get_course(db, course_id)


@router.get(
    "/courses/slug/{slug}",
    response_model=CourseResponse,
    summary="Get course by slug (SEO-friendly)",
)
async def get_course_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> CourseResponse:
    return await controller.get_course_by_slug(db, slug)


@router.get(
    "/courses/{course_id}/detail",
    response_model=CourseDetailResponse,
    summary="Get course detail with modules and lessons",
    description="Returns the full course structure including all modules "
    "and their lessons, ordered by sort_order.",
)
async def get_course_detail(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CourseDetailResponse:
    return await controller.get_course_detail(db, course_id)


@router.patch(
    "/courses/{course_id}",
    response_model=CourseResponse,
    summary="Update course (instructor only)",
)
async def update_course(
    course_id: UUID,
    body: UpdateCourseRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> CourseResponse:
    return await controller.update_course(db, course_id, user_id, body)


@router.post(
    "/courses/{course_id}/publish",
    response_model=CourseResponse,
    summary="Publish course (DRAFT -> PUBLISHED)",
    description="Transitions a DRAFT course to PUBLISHED. "
    "Only the course instructor can publish.",
)
async def publish_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> CourseResponse:
    return await controller.publish_course(db, course_id, user_id)


@router.post(
    "/courses/{course_id}/archive",
    response_model=CourseResponse,
    summary="Archive course (soft delete)",
    description="Archives a course. Enrolled users retain access but "
    "the course is removed from the catalog.",
)
async def archive_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> CourseResponse:
    return await controller.archive_course(db, course_id, user_id)


# ======================================================================
# Module endpoints
# ======================================================================


@router.post(
    "/courses/{course_id}/modules",
    response_model=ModuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add module to course",
)
async def create_module(
    course_id: UUID,
    body: CreateModuleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> ModuleResponse:
    return await controller.create_module(db, course_id, user_id, body)


@router.patch(
    "/modules/{module_id}",
    response_model=ModuleResponse,
    summary="Update module",
)
async def update_module(
    module_id: UUID,
    body: UpdateModuleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> ModuleResponse:
    return await controller.update_module(db, module_id, user_id, body)


@router.delete(
    "/modules/{module_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete module",
)
async def delete_module(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> None:
    await controller.delete_module(db, module_id, user_id)


@router.patch(
    "/courses/{course_id}/modules/reorder",
    response_model=list[ModuleResponse],
    summary="Reorder modules within a course",
    description="Pass an ordered array of module_ids. "
    "Modules are re-sorted to match the provided order.",
)
async def reorder_modules(
    course_id: UUID,
    body: ReorderModulesRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> list[ModuleResponse]:
    return await controller.reorder_modules(db, course_id, user_id, body.module_ids)


# ======================================================================
# Lesson endpoints
# ======================================================================


@router.post(
    "/modules/{module_id}/lessons",
    response_model=LessonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add lesson to module",
)
async def create_lesson(
    module_id: UUID,
    body: CreateLessonRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> LessonResponse:
    return await controller.create_lesson(db, module_id, user_id, body)


@router.patch(
    "/lessons/{lesson_id}",
    response_model=LessonResponse,
    summary="Update lesson",
)
async def update_lesson(
    lesson_id: UUID,
    body: UpdateLessonRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> LessonResponse:
    return await controller.update_lesson(db, lesson_id, user_id, body)


@router.delete(
    "/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete lesson",
)
async def delete_lesson(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> None:
    await controller.delete_lesson(db, lesson_id, user_id)


# ======================================================================
# Enrollment endpoints
# ======================================================================


@router.post(
    "/courses/{course_id}/enroll",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll in a free course",
    description="Creates an enrollment for a FREE course. "
    "Returns 402 if the course requires payment.",
)
async def enroll_free(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentResponse:
    return await controller.enroll_free(db, course_id, user_id)


@router.post(
    "/courses/{course_id}/enroll/paid",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll in a paid course (after payment)",
    description="Creates an enrollment for a PAID course. Requires a valid "
    "payment_id from MS-6 (Payment Service). "
    "Unique constraint on (user_id, course_id) prevents double enrollment.",
)
async def enroll_paid(
    course_id: UUID,
    body: CreateEnrollmentRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentResponse:
    return await controller.enroll_paid(db, course_id, user_id, body)


@router.get(
    "/enrollments/me",
    response_model=OffsetPage[EnrollmentResponse],
    summary="List my enrollments",
)
async def get_my_enrollments(
    enrollment_status: EnrollmentStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> dict:
    return await controller.get_my_enrollments(
        db, user_id, enrollment_status=enrollment_status, limit=limit, offset=offset,
    )


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentDetailResponse,
    summary="Get enrollment detail with per-lesson progress",
)
async def get_enrollment_detail(
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentDetailResponse:
    return await controller.get_enrollment_detail(db, enrollment_id, user_id)


@router.delete(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentResponse,
    summary="Drop course",
    description="Sets enrollment status to DROPPED. "
    "The user can re-enroll later.",
)
async def drop_enrollment(
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentResponse:
    return await controller.drop_enrollment(db, enrollment_id, user_id)


# ======================================================================
# Progress tracking endpoints
# ======================================================================


@router.post(
    "/lessons/{lesson_id}/progress",
    response_model=LessonProgressResponse,
    summary="Update lesson progress",
    description="Track video watch position or mark a lesson as completed. "
    "Automatically recalculates enrollment progress_pct. "
    "When all lessons are completed, enrollment status transitions to COMPLETED.",
)
async def update_lesson_progress(
    lesson_id: UUID,
    body: UpdateLessonProgressRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> LessonProgressResponse:
    return await controller.update_lesson_progress(
        db, lesson_id, user_id,
        watch_duration_secs=body.watch_duration_secs,
        completed=body.completed,
    )


@router.post(
    "/enrollments/{enrollment_id}/resume",
    response_model=EnrollmentResponse,
    summary="Update video resume position",
    description="Saves the last lesson and timestamp position so the user "
    "can resume playback from where they left off.",
)
async def update_resume_position(
    enrollment_id: UUID,
    body: UpdateProgressRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentResponse:
    return await controller.update_resume_position(db, enrollment_id, user_id, body)


@router.get(
    "/courses/{course_id}/progress",
    response_model=EnrollmentDetailResponse,
    summary="Get full course progress for current user",
    description="Returns the enrollment and all per-lesson progress records "
    "for the authenticated user in the specified course.",
)
async def get_course_progress(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> EnrollmentDetailResponse:
    return await controller.get_course_progress(db, course_id, user_id)
