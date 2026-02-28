import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class CourseModule(Base):
    __tablename__ = "course_modules"

    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # ── Completion & certification ─────────────────────────────────────
    prerequisite_module_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cert_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cert_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cert_custom_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    course = relationship("Course", back_populates="modules", lazy="select")
    lessons = relationship("Lesson", back_populates="module", lazy="noload")

    __table_args__ = (
        Index("ix_course_modules_course_id", "course_id"),
    )
