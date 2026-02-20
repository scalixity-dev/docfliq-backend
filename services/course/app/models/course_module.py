import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
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
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    course = relationship("Course", back_populates="modules", lazy="select")
    lessons = relationship("Lesson", back_populates="module", lazy="noload")

    __table_args__ = (
        Index("ix_course_modules_course_id", "course_id"),
    )
