"""Certificate service — generation, PDF creation, S3 upload, and QR verification.

Pure business logic, no FastAPI imports.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates.pdf_generator import CertificatePDFData, generate_certificate_pdf
from app.certificates.s3 import upload_certificate_pdf
from app.config import Settings
from app.exceptions import (
    CertificateAlreadyIssuedError,
    CertificateNotFoundError,
    CourseNotCompletedError,
    EnrollmentNotFoundError,
)
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus
from app.models.lesson import Lesson

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tamper-proof verification code
# ---------------------------------------------------------------------------


def _generate_verification_code(
    user_id: UUID,
    course_id: UUID,
    timestamp: datetime,
    secret: str,
) -> str:
    """HMAC-SHA256(userId:courseId:timestamp, secret) → 16-char alphanumeric code."""
    message = f"{user_id}:{course_id}:{timestamp.isoformat()}"
    digest = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256,
    ).hexdigest()
    # Convert to alphanumeric-friendly: take first 16 hex chars → uppercase
    return digest[:16].upper()


# ---------------------------------------------------------------------------
# Total hours calculation
# ---------------------------------------------------------------------------


async def _calculate_total_hours(
    db: AsyncSession,
    course_id: UUID,
) -> Decimal | None:
    """Sum duration_secs from all lessons in the course and convert to hours."""
    stmt = (
        select(func.sum(Lesson.duration_secs))
        .join(CourseModule, Lesson.module_id == CourseModule.module_id)
        .where(CourseModule.course_id == course_id)
    )
    total_secs = await db.scalar(stmt)
    if total_secs is None or total_secs == 0:
        return None
    return Decimal(str(round(total_secs / 3600, 1)))


# ---------------------------------------------------------------------------
# Certificate generation
# ---------------------------------------------------------------------------


async def generate_certificate(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
    recipient_name: str,
    settings: Settings,
) -> Certificate:
    """Generate PDF certificate, upload to S3, and store the record."""
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.user_id != user_id:
        raise EnrollmentNotFoundError(str(enrollment_id))

    if enrollment.status != EnrollmentStatus.COMPLETED:
        raise CourseNotCompletedError()

    # Check if certificate already issued
    existing = await db.scalar(
        select(Certificate.certificate_id)
        .where(Certificate.enrollment_id == enrollment_id),
    )
    if existing is not None:
        raise CertificateAlreadyIssuedError()

    # Snapshot course data
    course = await db.get(Course, enrollment.course_id)
    course_title = course.title if course else "Unknown Course"
    instructor_name = course.instructor_name if course else ""

    # Calculate total hours and score
    total_hours = await _calculate_total_hours(db, enrollment.course_id)
    score = int(enrollment.progress_pct) if enrollment.progress_pct else None

    # Generate tamper-proof verification code
    issued_at = datetime.now(timezone.utc)
    verification_code = _generate_verification_code(
        user_id, enrollment.course_id, issued_at, settings.certificate_signing_secret,
    )
    verification_url = f"{settings.certificate_base_url}/{verification_code}"

    # Generate PDF
    pdf_data = CertificatePDFData(
        recipient_name=recipient_name,
        course_title=course_title,
        instructor_name=instructor_name,
        issued_date=issued_at,
        total_hours=float(total_hours) if total_hours else None,
        score=score,
        verification_code=verification_code,
        verification_url=verification_url,
    )
    pdf_bytes = generate_certificate_pdf(pdf_data)

    # Upload to S3
    s3_key = f"{settings.s3_certificate_prefix}{verification_code}.pdf"
    certificate_url = upload_certificate_pdf(pdf_bytes, s3_key, settings)

    # Store certificate record
    cert = Certificate(
        enrollment_id=enrollment_id,
        user_id=user_id,
        course_id=enrollment.course_id,
        certificate_url=certificate_url,
        qr_verification_code=verification_code,
        issued_at=issued_at,
        recipient_name=recipient_name,
        course_title=course_title,
        instructor_name=instructor_name,
        total_hours=total_hours,
        score=score,
    )
    db.add(cert)
    await db.flush()
    await db.refresh(cert)
    return cert


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def get_certificate_by_id(
    db: AsyncSession,
    certificate_id: UUID,
) -> Certificate:
    cert = await db.get(Certificate, certificate_id)
    if cert is None:
        raise CertificateNotFoundError(str(certificate_id))
    return cert


async def get_my_certificates(
    db: AsyncSession,
    user_id: UUID,
) -> list[Certificate]:
    stmt = (
        select(Certificate)
        .where(Certificate.user_id == user_id)
        .order_by(Certificate.issued_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Public verification
# ---------------------------------------------------------------------------


async def verify_certificate(
    db: AsyncSession,
    qr_code: str,
) -> dict:
    """Public verification — no auth required.

    Returns certificate validity and snapshot data from the certificate row.
    """
    stmt = select(Certificate).where(Certificate.qr_verification_code == qr_code)
    result = await db.execute(stmt)
    cert = result.scalar_one_or_none()

    if cert is None:
        return {
            "is_valid": False,
            "certificate_id": None,
            "recipient_name": None,
            "user_id": None,
            "course_id": None,
            "course_title": None,
            "instructor_name": None,
            "total_hours": None,
            "score": None,
            "issued_at": None,
        }

    return {
        "is_valid": True,
        "certificate_id": cert.certificate_id,
        "recipient_name": cert.recipient_name,
        "user_id": cert.user_id,
        "course_id": cert.course_id,
        "course_title": cert.course_title,
        "instructor_name": cert.instructor_name,
        "total_hours": cert.total_hours,
        "score": cert.score,
        "issued_at": cert.issued_at,
    }
