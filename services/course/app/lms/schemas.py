"""LMS domain Pydantic V2 schemas.

Covers Course, CourseModule, Lesson, and Enrollment.
Follows RORO: separate request models from response models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    CertificationMode,
    CompletionMode,
    CourseStatus,
    CourseVisibility,
    EnrollmentStatus,
    LessonProgressStatus,
    LessonType,
    ModuleUnlockMode,
    PricingType,
    ScormImportStatus,
)


# ---------------------------------------------------------------------------
# Course request schemas
# ---------------------------------------------------------------------------


class CreateCourseRequest(BaseModel):
    """Request body for creating a new course.

    Can be created by admins or verified HCPs (physicians).
    instructor_name is required — stored on the course so cards render
    without cross-service calls to the identity service.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300, description="Course title.")
    slug: str | None = Field(
        default=None,
        max_length=300,
        description="SEO-friendly URL slug. Auto-generated from title if omitted.",
    )
    description: str | None = Field(
        default=None,
        description="Course description / landing page body.",
    )
    instructor_name: str = Field(
        min_length=1,
        max_length=200,
        description="Display name of the instructor (e.g. 'Dr. Priya Sharma').",
    )
    instructor_bio: str | None = Field(
        default=None,
        description="Short bio of the instructor. Markdown supported.",
    )
    institution_id: UUID | None = Field(
        default=None,
        description="Hospital/Society offering the course (identity_db reference). Optional — pending confirmation.",
    )
    category: str = Field(
        min_length=1,
        max_length=100,
        description="Category (e.g. Featured, Trending, By Specialty).",
    )
    specialty_tags: list[str] | None = Field(
        default=None,
        description="Specialty tags for search and filtering.",
    )
    pricing_type: PricingType = Field(description="FREE or PAID.")
    price: Decimal | None = Field(
        default=None,
        ge=0,
        description="Price in INR. Must be > 0 for PAID courses, 0 or null for FREE.",
    )
    currency: str = Field(
        default="INR",
        max_length=3,
        description="ISO 4217 currency code.",
    )
    preview_video_url: str | None = Field(
        default=None,
        max_length=500,
        description="Preview video CloudFront URL.",
    )
    thumbnail_url: str | None = Field(
        default=None,
        max_length=500,
        description="Course thumbnail image URL.",
    )
    syllabus: str | None = Field(
        default=None,
        description="Course syllabus in markdown / rich text format.",
    )
    completion_logic: dict = Field(
        default_factory=dict,
        description="Custom completion rules: score thresholds, percentage required, etc.",
    )
    visibility: CourseVisibility = Field(
        default=CourseVisibility.PUBLIC,
        description="PUBLIC or VERIFIED_ONLY.",
    )
    scorm_package_url: str | None = Field(
        default=None,
        max_length=500,
        description="S3 URL for SCORM 1.2/2004 package.",
    )
    # V2 setup features
    custom_metadata: list[dict] | None = Field(
        default=None,
        description="Custom metadata fields: [{field_name, field_type, label, options, required, value}].",
    )
    self_registration_enabled: bool = Field(default=True)
    approval_required: bool = Field(default=False)
    access_code: str | None = Field(default=None, max_length=50, description="Institutional passcode.")
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100, description="Direct discount %.")
    certificate_price: Decimal | None = Field(
        default=None, ge=0,
        description="Certificate price for FREE_PLUS_CERTIFICATE courses.",
    )
    registration_questions: list[dict] | None = Field(
        default=None,
        description="Custom registration questions: [{question_id, question_text, question_type, options, required}].",
    )
    eligibility_rules: dict | None = Field(
        default=None,
        description="Eligibility rules: {min_experience_years, required_specialties, required_role, custom_rules}.",
    )
    # Completion & certification
    completion_mode: CompletionMode = Field(
        default=CompletionMode.DEFAULT,
        description="DEFAULT auto-fills completion_logic; CUSTOM uses the provided values.",
    )
    module_unlock_mode: ModuleUnlockMode = Field(
        default=ModuleUnlockMode.ALL_UNLOCKED,
        description="How modules become accessible to students.",
    )
    certification_mode: CertificationMode = Field(
        default=CertificationMode.COURSE,
        description="What certificates are generated on completion.",
    )
    cert_template: str | None = Field(default=None, max_length=100, description="Certificate template name.")
    cert_custom_title: str | None = Field(default=None, max_length=300, description="Custom certificate title.")

    @field_validator("price")
    @classmethod
    def _validate_price_for_paid(cls, v: Decimal | None, info) -> Decimal | None:
        pricing_type = info.data.get("pricing_type")
        if pricing_type == PricingType.PAID and (v is None or v <= 0):
            raise ValueError("PAID courses must have a price greater than 0.")
        return v

    @field_validator("certificate_price")
    @classmethod
    def _validate_certificate_price(cls, v: Decimal | None, info) -> Decimal | None:
        pricing_type = info.data.get("pricing_type")
        if pricing_type == PricingType.FREE_PLUS_CERTIFICATE and (v is None or v <= 0):
            raise ValueError("FREE_PLUS_CERTIFICATE courses must have a certificate_price > 0.")
        return v


class UpdateCourseRequest(BaseModel):
    """PATCH body for updating a course. All fields optional."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None)
    instructor_name: str | None = Field(default=None, max_length=200)
    instructor_bio: str | None = Field(default=None)
    category: str | None = Field(default=None, max_length=100)
    specialty_tags: list[str] | None = Field(default=None)
    pricing_type: PricingType | None = Field(default=None)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    preview_video_url: str | None = Field(default=None, max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    syllabus: str | None = Field(default=None, description="Markdown / rich text syllabus.")
    completion_logic: dict | None = Field(default=None)
    status: CourseStatus | None = Field(default=None)
    visibility: CourseVisibility | None = Field(default=None)
    scorm_package_url: str | None = Field(default=None, max_length=500)
    # V2 setup features (all optional for update)
    custom_metadata: list[dict] | None = Field(default=None)
    self_registration_enabled: bool | None = Field(default=None)
    approval_required: bool | None = Field(default=None)
    access_code: str | None = Field(default=None, max_length=50)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    certificate_price: Decimal | None = Field(default=None, ge=0)
    registration_questions: list[dict] | None = Field(default=None)
    eligibility_rules: dict | None = Field(default=None)
    # Completion & certification
    completion_mode: CompletionMode | None = Field(default=None)
    module_unlock_mode: ModuleUnlockMode | None = Field(default=None)
    certification_mode: CertificationMode | None = Field(default=None)
    cert_template: str | None = Field(default=None, max_length=100)
    cert_custom_title: str | None = Field(default=None, max_length=300)


# ---------------------------------------------------------------------------
# CourseModule request schemas
# ---------------------------------------------------------------------------


class CreateModuleRequest(BaseModel):
    """Request body for adding a module to a course."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300, description="Module title.")
    sort_order: int = Field(ge=0, description="Display order within the course.")
    prerequisite_module_ids: list[UUID] | None = Field(
        default=None, description="Module IDs that must be completed before this module unlocks (CUSTOM mode).",
    )
    is_required: bool = Field(default=True, description="Whether module counts toward course completion.")
    cert_enabled: bool = Field(default=False, description="Whether module completion issues a certificate.")
    cert_template: str | None = Field(default=None, max_length=100)
    cert_custom_title: str | None = Field(default=None, max_length=300)


class UpdateModuleRequest(BaseModel):
    """PATCH body for updating a module."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    sort_order: int | None = Field(default=None, ge=0)
    prerequisite_module_ids: list[UUID] | None = Field(default=None)
    is_required: bool | None = Field(default=None)
    cert_enabled: bool | None = Field(default=None)
    cert_template: str | None = Field(default=None, max_length=100)
    cert_custom_title: str | None = Field(default=None, max_length=300)


# ---------------------------------------------------------------------------
# Lesson request schemas
# ---------------------------------------------------------------------------


class CreateLessonRequest(BaseModel):
    """Request body for adding a lesson to a module."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300, description="Lesson title.")
    lesson_type: LessonType = Field(
        description="VIDEO, PDF, TEXT, QUIZ, SCORM, PRESENTATION, SURVEY, or ASSESSMENT.",
    )
    content_url: str | None = Field(
        default=None,
        max_length=500,
        description="S3 signed URL for video/PDF content.",
    )
    content_body: str | None = Field(
        default=None,
        description="Rich text content for TEXT type lessons.",
    )
    duration_mins: int | None = Field(
        default=None,
        ge=0,
        description="Lesson duration in minutes.",
    )
    sort_order: int = Field(ge=0, description="Order within the module.")
    is_preview: bool = Field(
        default=False,
        description="Whether this lesson is available as a free preview.",
    )
    # V2 build features
    slide_count: int | None = Field(default=None, ge=1, description="Number of slides for PRESENTATION type.")
    is_required: bool = Field(default=False, description="Whether this lesson must be completed to proceed.")
    is_gated: bool = Field(default=False, description="Whether previous lessons must be completed first.")
    gate_passing_score: int | None = Field(default=None, ge=0, le=100, description="Min score to unlock next.")


class UpdateLessonRequest(BaseModel):
    """PATCH body for updating a lesson."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    lesson_type: LessonType | None = Field(default=None)
    content_url: str | None = Field(default=None, max_length=500)
    content_body: str | None = Field(default=None)
    duration_mins: int | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None, ge=0)
    is_preview: bool | None = Field(default=None)
    slide_count: int | None = Field(default=None, ge=1)
    is_required: bool | None = Field(default=None)
    is_gated: bool | None = Field(default=None)
    gate_passing_score: int | None = Field(default=None, ge=0, le=100)


# ---------------------------------------------------------------------------
# Enrollment request schemas
# ---------------------------------------------------------------------------


class CreateEnrollmentRequest(BaseModel):
    """Request body for enrolling in a course."""

    model_config = ConfigDict(str_strip_whitespace=True)

    payment_id: UUID | None = Field(
        default=None,
        description="Payment record ID. Required for PAID courses, null for FREE.",
    )
    access_code: str | None = Field(default=None, max_length=50, description="Institutional access code.")
    promo_code: str | None = Field(default=None, max_length=50, description="Promo code for discount.")
    registration_answers: list[dict] | None = Field(
        default=None, description="Answers to custom registration questions.",
    )


class UpdateProgressRequest(BaseModel):
    """Request body for updating lesson resume position."""

    model_config = ConfigDict(str_strip_whitespace=True)

    last_lesson_id: UUID = Field(description="Lesson the user is currently on.")
    last_position_secs: int = Field(
        default=0,
        ge=0,
        description="Video resume position in seconds.",
    )


class UpdateLessonProgressRequest(BaseModel):
    """Request body for tracking lesson progress (video watch, completion)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    watch_duration_secs: int | None = Field(
        default=None,
        ge=0,
        description="Current video watch position in seconds.",
    )
    completed: bool = Field(
        default=False,
        description="Whether the lesson is completed.",
    )


class ReorderModulesRequest(BaseModel):
    """Request body for reordering modules within a course."""

    model_config = ConfigDict(str_strip_whitespace=True)

    module_ids: list[UUID] = Field(
        description="Ordered array of module UUIDs. Modules are re-sorted to match.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CourseResponse(BaseModel):
    """Full course representation."""

    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    title: str
    slug: str = Field(description="SEO-friendly URL slug.")
    description: str | None
    instructor_id: UUID = Field(description="Primary instructor (identity_db reference).")
    instructor_name: str = Field(description="Display name of the instructor.")
    instructor_bio: str | None = Field(description="Instructor bio (markdown).")
    institution_id: UUID | None
    category: str
    specialty_tags: list[str] | None
    pricing_type: PricingType
    price: Decimal | None
    currency: str
    preview_video_url: str | None
    thumbnail_url: str | None
    syllabus: str | None = Field(description="Course syllabus (markdown / rich text).")
    completion_logic: dict
    total_modules: int
    total_duration_mins: int | None
    enrollment_count: int
    rating_avg: Decimal | None
    status: CourseStatus
    visibility: CourseVisibility
    scorm_package_url: str | None
    custom_metadata: list[dict] | None = None
    self_registration_enabled: bool = True
    approval_required: bool = False
    access_code: str | None = None
    discount_pct: Decimal | None = None
    certificate_price: Decimal | None = None
    registration_questions: list[dict] | None = None
    eligibility_rules: dict | None = None
    scorm_import_status: ScormImportStatus | None = None
    scorm_import_error: str | None = None
    completion_mode: CompletionMode = CompletionMode.DEFAULT
    module_unlock_mode: ModuleUnlockMode = ModuleUnlockMode.ALL_UNLOCKED
    certification_mode: CertificationMode = CertificationMode.COURSE
    cert_template: str | None = None
    cert_custom_title: str | None = None
    created_at: datetime
    updated_at: datetime


class CourseSummary(BaseModel):
    """Lightweight course card for list/feed views."""

    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    title: str
    slug: str
    thumbnail_url: str | None
    instructor_id: UUID
    instructor_name: str
    category: str
    specialty_tags: list[str] | None
    pricing_type: PricingType
    price: Decimal | None
    currency: str
    total_modules: int
    total_duration_mins: int | None
    enrollment_count: int
    rating_avg: Decimal | None
    status: CourseStatus
    created_at: datetime


class CourseListResponse(BaseModel):
    """Paginated list of courses."""

    items: list[CourseSummary]
    total: int
    limit: int
    offset: int


class ModuleResponse(BaseModel):
    """Module within a course."""

    model_config = ConfigDict(from_attributes=True)

    module_id: UUID
    course_id: UUID
    title: str
    sort_order: int
    prerequisite_module_ids: list[UUID] | None = None
    is_required: bool = True
    cert_enabled: bool = False
    cert_template: str | None = None
    cert_custom_title: str | None = None
    created_at: datetime


class LessonResponse(BaseModel):
    """Lesson within a module."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: UUID
    module_id: UUID
    title: str
    lesson_type: LessonType
    content_url: str | None
    content_body: str | None
    duration_mins: int | None
    sort_order: int
    is_preview: bool
    slide_count: int | None = None
    is_required: bool = False
    is_gated: bool = False
    gate_passing_score: int | None = None
    created_at: datetime


class ModuleWithLessonsResponse(BaseModel):
    """Module with its lessons expanded (for course detail view)."""

    model_config = ConfigDict(from_attributes=True)

    module_id: UUID
    course_id: UUID
    title: str
    sort_order: int
    prerequisite_module_ids: list[UUID] | None = None
    is_required: bool = True
    cert_enabled: bool = False
    cert_template: str | None = None
    cert_custom_title: str | None = None
    lessons: list[LessonResponse] = Field(default_factory=list)
    created_at: datetime


class CourseDetailResponse(BaseModel):
    """Full course with modules and lessons for the course detail page."""

    course: CourseResponse
    modules: list[ModuleWithLessonsResponse] = Field(default_factory=list)


class EnrollmentResponse(BaseModel):
    """Enrollment record."""

    model_config = ConfigDict(from_attributes=True)

    enrollment_id: UUID
    user_id: UUID
    course_id: UUID
    payment_id: UUID | None
    progress_pct: Decimal
    status: EnrollmentStatus
    completed_at: datetime | None
    last_lesson_id: UUID | None
    last_position_secs: int | None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    access_code_used: str | None = None
    promo_code_id: UUID | None = None
    discount_applied_pct: Decimal | None = None
    final_price: Decimal | None = None
    registration_answers: list[dict] | None = None
    created_at: datetime


class LessonProgressResponse(BaseModel):
    """Per-lesson progress record."""

    model_config = ConfigDict(from_attributes=True)

    progress_id: UUID
    enrollment_id: UUID
    lesson_id: UUID
    status: LessonProgressStatus
    watch_duration_secs: int | None
    quiz_score: int | None
    quiz_attempts: int | None
    completed_at: datetime | None


class EnrollmentDetailResponse(BaseModel):
    """Enrollment with per-lesson progress breakdown."""

    enrollment: EnrollmentResponse
    lesson_progress: list[LessonProgressResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# V2 Feature schemas: Instructor, Promo codes, Timeline
# ---------------------------------------------------------------------------


class CourseInstructorRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    instructor_id: UUID
    instructor_name: str = Field(min_length=1, max_length=200)
    instructor_bio: str | None = None
    role: str = Field(default="co_instructor", max_length=50)


class CourseInstructorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    instructor_id: UUID
    instructor_name: str
    instructor_bio: str | None
    role: str
    sort_order: int
    added_at: datetime


class CreatePromoCodeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=50)
    discount_pct: Decimal = Field(ge=1, le=100)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class PromoCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    promo_code_id: UUID
    course_id: UUID
    code: str
    discount_pct: Decimal
    max_uses: int | None
    current_uses: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    created_at: datetime


class CourseTimelineItem(BaseModel):
    global_index: int
    module_id: UUID
    module_title: str
    module_sort_order: int
    lesson_id: UUID
    lesson_title: str
    lesson_type: LessonType
    lesson_sort_order: int
    duration_mins: int | None
    is_preview: bool
    is_gated: bool
    is_required: bool


class CourseTimelineResponse(BaseModel):
    course_id: UUID
    total_items: int
    timeline: list[CourseTimelineItem]


# ---------------------------------------------------------------------------
# Module dependency graph
# ---------------------------------------------------------------------------


class ModuleDependencyNode(BaseModel):
    module_id: UUID
    title: str
    sort_order: int
    is_required: bool


class ModuleDependencyEdge(BaseModel):
    from_module_id: UUID
    to_module_id: UUID


class ModuleDependencyGraphResponse(BaseModel):
    course_id: UUID
    module_unlock_mode: ModuleUnlockMode
    nodes: list[ModuleDependencyNode]
    edges: list[ModuleDependencyEdge]
