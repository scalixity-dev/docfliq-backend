import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    response_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("surveys.survey_id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollments.enrollment_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    answers: Mapped[list] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    survey = relationship("Survey", back_populates="responses", lazy="select")
    enrollment = relationship("Enrollment", lazy="select")

    __table_args__ = (
        UniqueConstraint("survey_id", "enrollment_id", name="uq_survey_response_enrollment"),
        Index("ix_survey_responses_survey_id", "survey_id"),
        Index("ix_survey_responses_user_id", "user_id"),
    )
