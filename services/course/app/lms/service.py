"""LMS service — pure business logic, no FastAPI imports.

Handles course CRUD, module/lesson management, enrollment flows,
and progress tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import CourseStatus, EnrollmentStatus, PricingType
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def _slugify(title: str) -> str:
    import re
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    counter = 1
    while True:
        exists = await db.scalar(select(func.count()).where(Course.slug == slug))
        if not exists:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


# ---------------------------------------------------------------------------
# Course CRUD
# ---------------------------------------------------------------------------


async def create_course(
    db: AsyncSession,
    instructor_id: UUID,
    *,
    title: str,
    slug: str | None,
    description: str | None,
    instructor_name: str,
    instructor_bio: str | None,
    institution_id: UUID | None,
    category: str,
    specialty_tags: list[str] | None,
    pricing_type: PricingType,
    price: Decimal | None,
    currency: str,
    preview_video_url: str | None,
    thumbnail_url: str | None,
    syllabus: str | None,
    completion_logic: dict,
    visibility: str,
    scorm_package_url: str | None,
) -> Course:
    resolved_slug = slug or _slugify(title)
    resolved_slug = await _unique_slug(db, resolved_slug)

    course = Course(
        title=title,
        slug=resolved_slug,
        description=description,
        instructor_id=instructor_id,
        instructor_name=instructor_name,
        instructor_bio=instructor_bio,
        institution_id=institution_id,
        category=category,
        specialty_tags=specialty_tags,
        pricing_type=pricing_type,
        price=price,
        currency=currency,
        preview_video_url=preview_video_url,
        thumbnail_url=thumbnail_url,
        syllabus=syllabus,
        completion_logic=completion_logic,
        visibility=visibility,
        scorm_package_url=scorm_package_url,
    )
    db.add(course)
    await db.flush()
    await db.refresh(course)
    return course


async def get_course_by_id(db: AsyncSession, course_id: UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise CourseNotFoundError(str(course_id))
    return course


async def get_course_by_slug(db: AsyncSession, slug: str) -> Course:
    stmt = select(Course).where(Course.slug == slug)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if course is None:
        raise CourseNotFoundError(slug)
    return course


async def get_course_detail(db: AsyncSession, course_id: UUID) -> tuple[Course, list[CourseModule]]:
    course = await get_course_by_id(db, course_id)
    stmt = (
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .options(selectinload(CourseModule.lessons))
        .order_by(CourseModule.sort_order)
    )
    result = await db.execute(stmt)
    modules = list(result.scalars().all())
    return course, modules


async def list_courses(
    db: AsyncSession,
    *,
    status: CourseStatus | None = None,
    category: str | None = None,
    specialty_tag: str | None = None,
    pricing_type: PricingType | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Course], int]:
    base = select(Course)
    count_base = select(func.count()).select_from(Course)

    filters = []
    if status is not None:
        filters.append(Course.status == status)
    else:
        filters.append(Course.status.in_([CourseStatus.PUBLISHED]))
    if category is not None:
        filters.append(Course.category == category)
    if specialty_tag is not None:
        filters.append(Course.specialty_tags.any(specialty_tag))
    if pricing_type is not None:
        filters.append(Course.pricing_type == pricing_type)
    if search is not None:
        filters.append(
            func.to_tsvector("english", func.coalesce(Course.title, "") + " " + func.coalesce(Course.description, ""))
            .match(search)
        )

    for f in filters:
        base = base.where(f)
        count_base = count_base.where(f)

    total = await db.scalar(count_base) or 0
    stmt = base.order_by(Course.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    courses = list(result.scalars().all())
    return courses, total


async def update_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    **fields: object,
) -> Course:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    for key, value in fields.items():
        if value is not None:
            setattr(course, key, value)
    await db.flush()
    await db.refresh(course)
    return course


async def publish_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> Course:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    if course.status != CourseStatus.DRAFT:
        raise InvalidStatusTransitionError(course.status.value, CourseStatus.PUBLISHED.value)
    course.status = CourseStatus.PUBLISHED
    await db.flush()
    await db.refresh(course)
    return course


async def archive_course(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> Course:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    if course.status not in (CourseStatus.PUBLISHED, CourseStatus.DRAFT):
        raise InvalidStatusTransitionError(course.status.value, CourseStatus.ARCHIVED.value)
    course.status = CourseStatus.ARCHIVED
    await db.flush()
    await db.refresh(course)
    return course


# ---------------------------------------------------------------------------
# Module CRUD
# ---------------------------------------------------------------------------


async def create_module(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    *,
    title: str,
    sort_order: int,
) -> CourseModule:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    module = CourseModule(
        course_id=course_id,
        title=title,
        sort_order=sort_order,
    )
    db.add(module)
    course.total_modules = course.total_modules + 1
    await db.flush()
    await db.refresh(module)
    return module


async def get_module_by_id(db: AsyncSession, module_id: UUID) -> CourseModule:
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise ModuleNotFoundError(str(module_id))
    return module


async def update_module(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
    **fields: object,
) -> CourseModule:
    module = await get_module_by_id(db, module_id)
    course = await get_course_by_id(db, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    for key, value in fields.items():
        if value is not None:
            setattr(module, key, value)
    await db.flush()
    await db.refresh(module)
    return module


async def delete_module(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
) -> None:
    module = await get_module_by_id(db, module_id)
    course = await get_course_by_id(db, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    course.total_modules = max(0, course.total_modules - 1)
    await db.delete(module)
    await db.flush()


async def reorder_modules(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    *,
    module_ids: list[UUID],
) -> list[CourseModule]:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    stmt = (
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .order_by(CourseModule.sort_order)
    )
    result = await db.execute(stmt)
    modules = {m.module_id: m for m in result.scalars().all()}

    for idx, mid in enumerate(module_ids):
        if mid in modules:
            modules[mid].sort_order = idx

    await db.flush()
    return sorted(modules.values(), key=lambda m: m.sort_order)


# ---------------------------------------------------------------------------
# Lesson CRUD
# ---------------------------------------------------------------------------


async def create_lesson(
    db: AsyncSession,
    module_id: UUID,
    instructor_id: UUID,
    *,
    title: str,
    lesson_type: str,
    content_url: str | None,
    content_body: str | None,
    duration_mins: int | None,
    sort_order: int,
    is_preview: bool,
) -> Lesson:
    module = await get_module_by_id(db, module_id)
    course = await get_course_by_id(db, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    lesson = Lesson(
        module_id=module_id,
        title=title,
        lesson_type=lesson_type,
        content_url=content_url,
        content_body=content_body,
        duration_mins=duration_mins,
        sort_order=sort_order,
        is_preview=is_preview,
    )
    db.add(lesson)
    # Update course total_duration_mins
    if duration_mins:
        course.total_duration_mins = (course.total_duration_mins or 0) + duration_mins
    await db.flush()
    await db.refresh(lesson)
    return lesson


async def get_lesson_by_id(db: AsyncSession, lesson_id: UUID) -> Lesson:
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError(str(lesson_id))
    return lesson


async def update_lesson(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
    **fields: object,
) -> Lesson:
    lesson = await get_lesson_by_id(db, lesson_id)
    module = await get_module_by_id(db, lesson.module_id)
    course = await get_course_by_id(db, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    for key, value in fields.items():
        if value is not None:
            setattr(lesson, key, value)
    await db.flush()
    await db.refresh(lesson)
    return lesson


async def delete_lesson(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
) -> None:
    lesson = await get_lesson_by_id(db, lesson_id)
    module = await get_module_by_id(db, lesson.module_id)
    course = await get_course_by_id(db, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    if lesson.duration_mins:
        course.total_duration_mins = max(0, (course.total_duration_mins or 0) - lesson.duration_mins)
    await db.delete(lesson)
    await db.flush()


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


async def enroll_free(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> Enrollment:
    course = await get_course_by_id(db, course_id)
    if course.status != CourseStatus.PUBLISHED:
        raise CourseNotPublishedError()
    if course.pricing_type != PricingType.FREE:
        raise PaymentRequiredError()

    existing = await _get_enrollment(db, user_id, course_id)
    if existing is not None:
        raise AlreadyEnrolledError()

    enrollment = Enrollment(
        user_id=user_id,
        course_id=course_id,
        progress_pct=Decimal("0.00"),
        status=EnrollmentStatus.IN_PROGRESS,
    )
    db.add(enrollment)
    course.enrollment_count += 1
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def enroll_paid(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
    payment_id: UUID,
) -> Enrollment:
    course = await get_course_by_id(db, course_id)
    if course.status != CourseStatus.PUBLISHED:
        raise CourseNotPublishedError()

    existing = await _get_enrollment(db, user_id, course_id)
    if existing is not None:
        raise AlreadyEnrolledError()

    enrollment = Enrollment(
        user_id=user_id,
        course_id=course_id,
        payment_id=payment_id,
        progress_pct=Decimal("0.00"),
        status=EnrollmentStatus.IN_PROGRESS,
    )
    db.add(enrollment)
    course.enrollment_count += 1
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def _get_enrollment(
    db: AsyncSession,
    user_id: UUID,
    course_id: UUID,
) -> Enrollment | None:
    stmt = select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_enrollment_by_id(db: AsyncSession, enrollment_id: UUID) -> Enrollment:
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise EnrollmentNotFoundError(str(enrollment_id))
    return enrollment


async def get_my_enrollments(
    db: AsyncSession,
    user_id: UUID,
    *,
    status: EnrollmentStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Enrollment], int]:
    base = select(Enrollment).where(Enrollment.user_id == user_id)
    count_base = select(func.count()).select_from(Enrollment).where(Enrollment.user_id == user_id)

    if status is not None:
        base = base.where(Enrollment.status == status)
        count_base = count_base.where(Enrollment.status == status)

    total = await db.scalar(count_base) or 0
    stmt = base.order_by(Enrollment.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    enrollments = list(result.scalars().all())
    return enrollments, total


async def get_enrollment_detail(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
) -> tuple[Enrollment, list[LessonProgress]]:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if enrollment.user_id != user_id:
        raise EnrollmentNotFoundError(str(enrollment_id))

    stmt = (
        select(LessonProgress)
        .where(LessonProgress.enrollment_id == enrollment_id)
        .order_by(LessonProgress.progress_id)
    )
    result = await db.execute(stmt)
    progress = list(result.scalars().all())
    return enrollment, progress


async def drop_enrollment(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
) -> Enrollment:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if enrollment.user_id != user_id:
        raise EnrollmentNotFoundError(str(enrollment_id))
    enrollment.status = EnrollmentStatus.DROPPED
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def check_refund_eligibility(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
) -> bool:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if enrollment.user_id != user_id:
        raise EnrollmentNotFoundError(str(enrollment_id))
    if enrollment.progress_pct >= 20:
        return False
    days_since = (datetime.now(timezone.utc) - enrollment.created_at).days
    if days_since > 7:
        return False
    return True


# ---------------------------------------------------------------------------
# Progress Tracking
# ---------------------------------------------------------------------------


async def update_lesson_progress(
    db: AsyncSession,
    lesson_id: UUID,
    user_id: UUID,
    *,
    watch_duration_secs: int | None = None,
    completed: bool = False,
) -> LessonProgress:
    lesson = await get_lesson_by_id(db, lesson_id)
    module = await get_module_by_id(db, lesson.module_id)

    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    # Upsert lesson progress
    stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment.enrollment_id,
        LessonProgress.lesson_id == lesson_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()

    from app.models.enums import LessonProgressStatus

    if progress is None:
        progress = LessonProgress(
            enrollment_id=enrollment.enrollment_id,
            lesson_id=lesson_id,
            status=LessonProgressStatus.IN_PROGRESS,
        )
        db.add(progress)

    if watch_duration_secs is not None:
        progress.watch_duration_secs = watch_duration_secs
        if progress.status == LessonProgressStatus.NOT_STARTED:
            progress.status = LessonProgressStatus.IN_PROGRESS

    if completed:
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(progress)

    # Recalculate weighted enrollment progress_pct
    course = await db.get(Course, module.course_id)
    from app.player.service import _recalculate_weighted_progress
    await _recalculate_weighted_progress(db, enrollment, course)

    return progress


async def update_resume_position(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
    *,
    last_lesson_id: UUID,
    last_position_secs: int,
) -> Enrollment:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if enrollment.user_id != user_id:
        raise EnrollmentNotFoundError(str(enrollment_id))
    enrollment.last_lesson_id = last_lesson_id
    enrollment.last_position_secs = last_position_secs
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def get_course_progress(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
) -> tuple[Enrollment, list[LessonProgress]]:
    enrollment = await _get_enrollment(db, user_id, course_id)
    if enrollment is None:
        raise NotEnrolledError()

    stmt = (
        select(LessonProgress)
        .where(LessonProgress.enrollment_id == enrollment.enrollment_id)
        .order_by(LessonProgress.progress_id)
    )
    result = await db.execute(stmt)
    progress = list(result.scalars().all())
    return enrollment, progress


async def _recalculate_progress(db: AsyncSession, enrollment: Enrollment) -> None:
    """Delegate to the weighted progress algorithm in player.service."""
    course = await db.get(Course, enrollment.course_id)
    from app.player.service import _recalculate_weighted_progress
    await _recalculate_weighted_progress(db, enrollment, course)
