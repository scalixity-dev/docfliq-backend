import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import LessonProgressStatus, lesson_progress_status_enum


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    progress_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollments.enrollment_id", ondelete="CASCADE"),
        nullable=False,
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.lesson_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[LessonProgressStatus] = mapped_column(
        lesson_progress_status_enum,
        nullable=False,
        default=LessonProgressStatus.NOT_STARTED,
    )
    watch_duration_secs: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    # Merged watched intervals: [[0,120],[180,300]] — anti-cheat tracking
    watched_intervals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Calculated from intervals/duration * 100
    watched_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Document progress: {"viewed": [1,2,3], "total": 10}
    pages_viewed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pages_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quiz_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    quiz_attempts: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=0)
    scorm_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    enrollment = relationship("Enrollment", back_populates="progress_records", lazy="select")
    lesson = relationship("Lesson", lazy="select")

    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "lesson_id", name="uq_lesson_progress_enrollment_lesson"
        ),
        Index("ix_lesson_progress_enrollment_id", "enrollment_id"),
        Index("ix_lesson_progress_lesson_id", "lesson_id"),
    )
