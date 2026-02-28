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
    InvalidAccessCodeError,
    InvalidDependencyGraphError,
    InvalidPromoCodeError,
    InvalidStatusTransitionError,
    LessonNotFoundError,
    ModuleNotFoundError,
    NotCourseOwnerError,
    NotEnrolledError,
    PaymentRequiredError,
    PromoCodeNotFoundError,
    RefundNotEligibleError,
    SelfRegistrationDisabledError,
)
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.course_instructor import CourseInstructor
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import (
    CompletionMode,
    CourseStatus,
    EnrollmentStatus,
    ModuleUnlockMode,
    PricingType,
    ScormImportStatus,
)
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.promo_code import PromoCode


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


def _default_completion_logic() -> dict:
    """Default completion rules: 100% content consumed + 70% avg score."""
    return {
        "video_watch_pct": 90,
        "doc_read_pct": 90,
        "score_threshold": 70,
        "pct_required": 100,
        "weights": {
            "VIDEO": 1.0, "PDF": 1.0, "TEXT": 1.0, "QUIZ": 1.0,
            "SCORM": 1.0, "PRESENTATION": 1.0, "SURVEY": 1.0, "ASSESSMENT": 1.0,
        },
    }


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
    # V2 setup fields
    custom_metadata: list[dict] | None = None,
    self_registration_enabled: bool = True,
    approval_required: bool = False,
    access_code: str | None = None,
    discount_pct: Decimal | None = None,
    certificate_price: Decimal | None = None,
    registration_questions: list[dict] | None = None,
    eligibility_rules: dict | None = None,
    # Completion & certification
    completion_mode: str = "DEFAULT",
    module_unlock_mode: str = "ALL_UNLOCKED",
    certification_mode: str = "COURSE",
    cert_template: str | None = None,
    cert_custom_title: str | None = None,
) -> Course:
    resolved_slug = slug or _slugify(title)
    resolved_slug = await _unique_slug(db, resolved_slug)

    # Auto-fill completion_logic when mode is DEFAULT and no custom rules given
    if completion_mode == CompletionMode.DEFAULT and not completion_logic:
        completion_logic = _default_completion_logic()

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
        custom_metadata=custom_metadata or [],
        self_registration_enabled=self_registration_enabled,
        approval_required=approval_required,
        access_code=access_code,
        discount_pct=discount_pct,
        certificate_price=certificate_price,
        registration_questions=registration_questions or [],
        eligibility_rules=eligibility_rules or {},
        completion_mode=completion_mode,
        module_unlock_mode=module_unlock_mode,
        certification_mode=certification_mode,
        cert_template=cert_template,
        cert_custom_title=cert_custom_title,
    )
    # If SCORM package provided, mark for import
    if scorm_package_url:
        course.scorm_import_status = ScormImportStatus.PENDING

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
    prerequisite_module_ids: list[UUID] | None = None,
    is_required: bool = True,
    cert_enabled: bool = False,
    cert_template: str | None = None,
    cert_custom_title: str | None = None,
) -> CourseModule:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    module = CourseModule(
        course_id=course_id,
        title=title,
        sort_order=sort_order,
        prerequisite_module_ids=prerequisite_module_ids,
        is_required=is_required,
        cert_enabled=cert_enabled,
        cert_template=cert_template,
        cert_custom_title=cert_custom_title,
    )
    db.add(module)
    course.total_modules = course.total_modules + 1
    await db.flush()
    await db.refresh(module)

    # Validate dependency graph when CUSTOM unlock mode
    if prerequisite_module_ids and course.module_unlock_mode == ModuleUnlockMode.CUSTOM:
        modules = await _get_course_modules(db, course_id)
        validate_module_dependencies(modules)

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

    # Re-validate dependency graph if prerequisites changed
    if "prerequisite_module_ids" in fields and course.module_unlock_mode == ModuleUnlockMode.CUSTOM:
        modules = await _get_course_modules(db, module.course_id)
        validate_module_dependencies(modules)

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
    # V2 build fields
    slide_count: int | None = None,
    is_required: bool = False,
    is_gated: bool = False,
    gate_passing_score: int | None = None,
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
        slide_count=slide_count,
        is_required=is_required,
        is_gated=is_gated,
        gate_passing_score=gate_passing_score,
    )
    db.add(lesson)
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


async def enroll(
    db: AsyncSession,
    course_id: UUID,
    user_id: UUID,
    *,
    payment_id: UUID | None = None,
    access_code: str | None = None,
    promo_code: str | None = None,
    registration_answers: list[dict] | None = None,
) -> Enrollment:
    """Unified enrollment handling FREE, PAID, and FREE_PLUS_CERTIFICATE courses."""
    course = await get_course_by_id(db, course_id)
    if course.status != CourseStatus.PUBLISHED:
        raise CourseNotPublishedError()

    # Self-registration check
    if not course.self_registration_enabled:
        raise SelfRegistrationDisabledError()

    # Access code validation
    if course.access_code:
        if access_code != course.access_code:
            raise InvalidAccessCodeError()

    # Duplicate check
    existing = await _get_enrollment(db, user_id, course_id)
    if existing is not None:
        raise AlreadyEnrolledError()

    # Promo code validation & price calculation
    promo: PromoCode | None = None
    discount_applied = Decimal("0")
    final_price = course.price or Decimal("0")
    if promo_code:
        promo = await _validate_promo_code(db, course_id, promo_code)
        discount_applied = promo.discount_pct
        final_price = final_price * (1 - discount_applied / 100)
    elif course.discount_pct:
        discount_applied = course.discount_pct
        final_price = final_price * (1 - discount_applied / 100)

    # Payment validation
    if course.pricing_type == PricingType.PAID and final_price > 0:
        if payment_id is None:
            raise PaymentRequiredError()

    # Determine initial status
    initial_status = EnrollmentStatus.IN_PROGRESS
    if course.approval_required:
        initial_status = EnrollmentStatus.PENDING_APPROVAL

    enrollment = Enrollment(
        user_id=user_id,
        course_id=course_id,
        payment_id=payment_id,
        progress_pct=Decimal("0.00"),
        status=initial_status,
        access_code_used=access_code if course.access_code else None,
        promo_code_id=promo.promo_code_id if promo else None,
        discount_applied_pct=discount_applied if discount_applied > 0 else None,
        final_price=final_price,
        registration_answers=registration_answers,
    )
    db.add(enrollment)

    if promo:
        promo.current_uses += 1

    if initial_status != EnrollmentStatus.PENDING_APPROVAL:
        course.enrollment_count += 1

    await db.flush()
    await db.refresh(enrollment)
    return enrollment


# Keep legacy aliases for backward compatibility
async def enroll_free(db: AsyncSession, course_id: UUID, user_id: UUID) -> Enrollment:
    return await enroll(db, course_id, user_id)


async def enroll_paid(db: AsyncSession, course_id: UUID, user_id: UUID, payment_id: UUID) -> Enrollment:
    return await enroll(db, course_id, user_id, payment_id=payment_id)


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


# ---------------------------------------------------------------------------
# Multi-instructor management (Feature 3)
# ---------------------------------------------------------------------------


async def add_instructor(
    db: AsyncSession,
    course_id: UUID,
    requester_id: UUID,
    *,
    instructor_id: UUID,
    instructor_name: str,
    instructor_bio: str | None = None,
    role: str = "co_instructor",
) -> CourseInstructor:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != requester_id:
        raise NotCourseOwnerError()

    # Get next sort_order
    stmt = select(func.count()).select_from(CourseInstructor).where(
        CourseInstructor.course_id == course_id
    )
    count = await db.scalar(stmt) or 0

    ci = CourseInstructor(
        course_id=course_id,
        instructor_id=instructor_id,
        instructor_name=instructor_name,
        instructor_bio=instructor_bio,
        role=role,
        sort_order=count,
    )
    db.add(ci)
    await db.flush()
    await db.refresh(ci)
    return ci


async def remove_instructor(
    db: AsyncSession,
    course_id: UUID,
    requester_id: UUID,
    *,
    target_instructor_id: UUID,
) -> None:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != requester_id:
        raise NotCourseOwnerError()

    stmt = select(CourseInstructor).where(
        CourseInstructor.course_id == course_id,
        CourseInstructor.instructor_id == target_instructor_id,
    )
    result = await db.execute(stmt)
    ci = result.scalar_one_or_none()
    if ci is None:
        raise LessonNotFoundError(str(target_instructor_id))  # reuse for now
    await db.delete(ci)
    await db.flush()


async def list_instructors(db: AsyncSession, course_id: UUID) -> list[CourseInstructor]:
    stmt = (
        select(CourseInstructor)
        .where(CourseInstructor.course_id == course_id)
        .order_by(CourseInstructor.sort_order)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Enrollment approval (Feature 5)
# ---------------------------------------------------------------------------


async def approve_enrollment(
    db: AsyncSession,
    enrollment_id: UUID,
    instructor_id: UUID,
) -> Enrollment:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    course = await get_course_by_id(db, enrollment.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    if enrollment.status != EnrollmentStatus.PENDING_APPROVAL:
        raise InvalidStatusTransitionError(enrollment.status.value, "IN_PROGRESS")

    enrollment.status = EnrollmentStatus.IN_PROGRESS
    enrollment.approved_by = instructor_id
    enrollment.approved_at = datetime.now(timezone.utc)
    course.enrollment_count += 1
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def reject_enrollment(
    db: AsyncSession,
    enrollment_id: UUID,
    instructor_id: UUID,
) -> Enrollment:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    course = await get_course_by_id(db, enrollment.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    if enrollment.status != EnrollmentStatus.PENDING_APPROVAL:
        raise InvalidStatusTransitionError(enrollment.status.value, "DROPPED")

    enrollment.status = EnrollmentStatus.DROPPED
    await db.flush()
    await db.refresh(enrollment)
    return enrollment


async def list_pending_enrollments(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> list[Enrollment]:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    stmt = (
        select(Enrollment)
        .where(
            Enrollment.course_id == course_id,
            Enrollment.status == EnrollmentStatus.PENDING_APPROVAL,
        )
        .order_by(Enrollment.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Promo codes (Feature 7)
# ---------------------------------------------------------------------------


async def create_promo_code(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    *,
    code: str,
    discount_pct: Decimal,
    max_uses: int | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> PromoCode:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    promo = PromoCode(
        course_id=course_id,
        code=code.upper(),
        discount_pct=discount_pct,
        max_uses=max_uses,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.add(promo)
    await db.flush()
    await db.refresh(promo)
    return promo


async def list_promo_codes(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
) -> list[PromoCode]:
    course = await get_course_by_id(db, course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    stmt = (
        select(PromoCode)
        .where(PromoCode.course_id == course_id)
        .order_by(PromoCode.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def deactivate_promo_code(
    db: AsyncSession,
    promo_code_id: UUID,
    instructor_id: UUID,
) -> PromoCode:
    promo = await db.get(PromoCode, promo_code_id)
    if promo is None:
        raise PromoCodeNotFoundError(str(promo_code_id))

    course = await get_course_by_id(db, promo.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    promo.is_active = False
    await db.flush()
    await db.refresh(promo)
    return promo


async def _validate_promo_code(
    db: AsyncSession,
    course_id: UUID,
    code: str,
) -> PromoCode:
    stmt = select(PromoCode).where(
        PromoCode.course_id == course_id,
        PromoCode.code == code.upper(),
        PromoCode.is_active == True,
    )
    result = await db.execute(stmt)
    promo = result.scalar_one_or_none()
    if promo is None:
        raise InvalidPromoCodeError()

    now = datetime.now(timezone.utc)
    if promo.valid_from and now < promo.valid_from:
        raise InvalidPromoCodeError()
    if promo.valid_until and now > promo.valid_until:
        raise InvalidPromoCodeError()
    if promo.max_uses is not None and promo.current_uses >= promo.max_uses:
        raise InvalidPromoCodeError()

    return promo


# ---------------------------------------------------------------------------
# Course timeline (Feature 18)
# ---------------------------------------------------------------------------


async def get_course_timeline(
    db: AsyncSession,
    course_id: UUID,
) -> list[dict]:
    """Return a flat ordered list of all lessons across all modules."""
    course = await get_course_by_id(db, course_id)

    stmt = (
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .options(selectinload(CourseModule.lessons))
        .order_by(CourseModule.sort_order)
    )
    result = await db.execute(stmt)
    modules = list(result.scalars().all())

    timeline = []
    global_index = 0
    for module in modules:
        lessons = sorted(module.lessons, key=lambda l: l.sort_order) if module.lessons else []
        for lesson in lessons:
            timeline.append({
                "global_index": global_index,
                "module_id": module.module_id,
                "module_title": module.title,
                "module_sort_order": module.sort_order,
                "lesson_id": lesson.lesson_id,
                "lesson_title": lesson.title,
                "lesson_type": lesson.lesson_type,
                "lesson_sort_order": lesson.sort_order,
                "duration_mins": lesson.duration_mins,
                "is_preview": lesson.is_preview,
                "is_gated": lesson.is_gated,
                "is_required": lesson.is_required,
            })
            global_index += 1

    return timeline


# ---------------------------------------------------------------------------
# Module dependency graph & validation
# ---------------------------------------------------------------------------


async def _get_course_modules(db: AsyncSession, course_id: UUID) -> list[CourseModule]:
    stmt = (
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .order_by(CourseModule.sort_order)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def validate_module_dependencies(modules: list[CourseModule]) -> None:
    """Topological sort (Kahn's algorithm) to detect cycles in prerequisites."""
    module_ids = {m.module_id for m in modules}
    in_degree: dict[UUID, int] = {m.module_id: 0 for m in modules}
    adjacency: dict[UUID, list[UUID]] = {m.module_id: [] for m in modules}

    for m in modules:
        prereqs = m.prerequisite_module_ids or []
        for prereq_id in prereqs:
            if prereq_id not in module_ids:
                raise InvalidDependencyGraphError(
                    f"Prerequisite {prereq_id} not found in course modules."
                )
            adjacency[prereq_id].append(m.module_id)
            in_degree[m.module_id] += 1

    queue = [mid for mid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(modules):
        raise InvalidDependencyGraphError("Cycle detected in module prerequisites.")


async def get_module_dependency_graph(
    db: AsyncSession,
    course_id: UUID,
) -> tuple[Course, list[CourseModule]]:
    """Return course and modules for the controller to build dependency graph."""
    course = await get_course_by_id(db, course_id)
    modules = await _get_course_modules(db, course_id)
    return course, modules
