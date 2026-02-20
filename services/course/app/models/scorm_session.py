import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import ScormSessionStatus, scorm_session_status_enum


class ScormSession(Base):
    __tablename__ = "scorm_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
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
    status: Mapped[ScormSessionStatus] = mapped_column(
        scorm_session_status_enum,
        nullable=False,
        default=ScormSessionStatus.INITIALIZED,
    )
    # SCORM cmi.* data model stored as JSONB
    tracking_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    score_raw: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_max: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    total_time_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    enrollment = relationship("Enrollment", lazy="select")
    lesson = relationship("Lesson", lazy="select")

    __table_args__ = (
        Index("ix_scorm_sessions_enrollment_lesson", "enrollment_id", "lesson_id"),
    )
