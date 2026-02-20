import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import EnrollmentStatus, enrollment_status_enum


class Enrollment(Base):
    __tablename__ = "enrollments"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Soft reference — User lives in identity_db
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft reference — Payment lives in payment_db
    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    progress_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enrollment_status_enum, nullable=False, default=EnrollmentStatus.IN_PROGRESS
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Resume pointer: which lesson the user was last on
    last_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.lesson_id", ondelete="SET NULL"),
        nullable=True,
    )
    last_position_secs: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    course = relationship("Course", back_populates="enrollments", lazy="select")
    last_lesson = relationship("Lesson", lazy="select")
    progress_records = relationship("LessonProgress", back_populates="enrollment", lazy="noload")
    certificate = relationship(
        "Certificate", back_populates="enrollment", uselist=False, lazy="noload"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollments_user_course"),
        Index("ix_enrollments_user_id", "user_id"),
        Index("ix_enrollments_course_id", "course_id"),
        Index("ix_enrollments_status", "status"),
        Index("ix_enrollments_created_at", "created_at"),
    )
