import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Index, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID  # JSONB still used for completion_logic
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import (
    CourseStatus,
    CourseVisibility,
    PricingType,
    course_status_enum,
    course_visibility_enum,
    pricing_type_enum,
)


class Course(Base):
    __tablename__ = "courses"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Soft reference — User lives in identity_db, FK not enforceable cross-DB
    instructor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Denormalized from identity_db so course cards render without cross-service calls
    instructor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    instructor_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Soft reference — Institution lives in identity_db (pending client confirmation)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    specialty_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    pricing_type: Mapped[PricingType] = mapped_column(pricing_type_enum, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    preview_video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Rich-text / markdown syllabus written by the instructor
    syllabus: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Custom completion rules: {score_threshold, pct_required, ...}
    completion_logic: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    total_modules: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_duration_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrollment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    status: Mapped[CourseStatus] = mapped_column(
        course_status_enum, nullable=False, default=CourseStatus.DRAFT
    )
    visibility: Mapped[CourseVisibility] = mapped_column(
        course_visibility_enum, nullable=False, default=CourseVisibility.PUBLIC
    )
    scorm_package_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    modules = relationship("CourseModule", back_populates="course", lazy="noload")
    enrollments = relationship("Enrollment", back_populates="course", lazy="noload")

    __table_args__ = (
        Index("ix_courses_instructor_id", "instructor_id"),
        Index("ix_courses_status", "status"),
        Index("ix_courses_category", "category"),
        Index("ix_courses_created_at", "created_at"),
        # GIN index for array containment queries on specialty_tags
        Index("ix_courses_specialty_tags", "specialty_tags", postgresql_using="gin"),
        # Functional GIN index for full-text search on title + description
        Index(
            "ix_courses_fts",
            text(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))"
            ),
            postgresql_using="gin",
        ),
    )
