import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import LessonType, lesson_type_enum


class Lesson(Base):
    __tablename__ = "lessons"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_modules.module_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    lesson_type: Mapped[LessonType] = mapped_column(lesson_type_enum, nullable=False)
    content_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # HLS manifest S3 key (e.g. "courses/{id}/lessons/{id}/hls/master.m3u8")
    hls_manifest_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # SCORM fields
    scorm_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scorm_entry_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    module = relationship("CourseModule", back_populates="lessons", lazy="select")
    quiz = relationship("Quiz", back_populates="lesson", uselist=False, lazy="noload")

    __table_args__ = (
        Index("ix_lessons_module_id", "module_id"),
    )
