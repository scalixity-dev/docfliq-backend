import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class CourseInstructor(Base):
    __tablename__ = "course_instructors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        nullable=False,
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    instructor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    instructor_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="co_instructor")
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    course = relationship("Course", back_populates="instructors", lazy="select")

    __table_args__ = (
        UniqueConstraint("course_id", "instructor_id", name="uq_course_instructor"),
        Index("ix_course_instructors_course_id", "course_id"),
        Index("ix_course_instructors_instructor_id", "instructor_id"),
    )
