import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import CertificateType, certificate_type_enum


class Certificate(Base):
    __tablename__ = "certificates"

    certificate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollments.enrollment_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft reference — User lives in identity_db
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        nullable=False,
    )
    certificate_url: Mapped[str] = mapped_column(String(500), nullable=False)
    qr_verification_code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Module-level certificate fields (NULL = course cert)
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_modules.module_id", ondelete="SET NULL"),
        nullable=True,
    )
    certificate_type: Mapped[CertificateType] = mapped_column(
        certificate_type_enum, nullable=False, default=CertificateType.COURSE
    )
    module_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    template_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Denormalized fields — snapshot at issuance for verification display
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    course_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    instructor_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    total_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    enrollment = relationship("Enrollment", back_populates="certificates", lazy="select")
    course = relationship("Course", lazy="select")
    module = relationship("CourseModule", lazy="select")

    __table_args__ = (
        Index("ix_certificates_user_id", "user_id"),
        Index("ix_certificates_course_id", "course_id"),
    )
