import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quizzes.quiz_id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollments.enrollment_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft reference to identity_db
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # User answers: list of int (MCQ) or list[int] (MSQ) per question
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correct_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    total_questions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_taken_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    quiz = relationship("Quiz", lazy="select")
    enrollment = relationship("Enrollment", lazy="select")

    __table_args__ = (
        UniqueConstraint(
            "quiz_id", "enrollment_id", "attempt_number",
            name="uq_quiz_attempt_number",
        ),
        Index("ix_quiz_attempts_quiz_enrollment", "quiz_id", "enrollment_id"),
        Index("ix_quiz_attempts_user_id", "user_id"),
    )
