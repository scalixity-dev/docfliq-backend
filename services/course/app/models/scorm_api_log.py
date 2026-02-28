import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class ScormApiLog(Base):
    __tablename__ = "scorm_api_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scorm_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    api_call: Mapped[str] = mapped_column(String(100), nullable=False)
    parameter: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("ScormSession", back_populates="api_logs", lazy="select")

    __table_args__ = (
        Index("ix_scorm_api_logs_session_id", "session_id"),
        Index("ix_scorm_api_logs_timestamp", "timestamp"),
    )
