import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import ShowAnswersPolicy, show_answers_policy_enum


class Quiz(Base):
    __tablename__ = "quizzes"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.lesson_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Array of {question_type, question, question_html, image_url, options: [{text, html, image_url}],
    #           correct_index (MCQ), correct_indices (MSQ), explanation}
    questions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    passing_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=70)
    max_attempts: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    time_limit_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    randomize_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_answers: Mapped[ShowAnswersPolicy] = mapped_column(
        show_answers_policy_enum, nullable=False, default=ShowAnswersPolicy.NEVER
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    lesson = relationship("Lesson", back_populates="quiz", lazy="select")

    __table_args__ = (
        Index("ix_quizzes_lesson_id", "lesson_id"),
    )
