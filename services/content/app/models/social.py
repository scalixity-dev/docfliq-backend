# Follow and Block are owned by the Identity service (identity_db).
# They are user-to-user graph relationships, not content relationships.

import uuid
from datetime import datetime, timezone

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.postgres import Base

from .enums import ReportStatus, ReportTargetType, report_status_enum, report_target_type_enum


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Soft reference — User lives in identity_db
    reporter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[ReportTargetType] = mapped_column(report_target_type_enum, nullable=False)
    # Polymorphic target: could be a post_id, comment_id, user_id, or webinar_id
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        report_status_enum, nullable=False, default=ReportStatus.OPEN
    )
    # Soft reference — admin User lives in identity_db
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_reports_reporter_id", "reporter_id"),
        Index("ix_reports_target", "target_type", "target_id"),
        Index("ix_reports_status", "status"),
    )