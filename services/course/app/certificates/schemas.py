"""Certificate domain Pydantic V2 schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CertificateType


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class GenerateCertificateRequest(BaseModel):
    """Request body for certificate generation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recipient_name: str = Field(
        min_length=1,
        max_length=200,
        description="Full name of the certificate recipient (as it should appear on the PDF).",
    )


class GenerateModuleCertificateRequest(BaseModel):
    """Request body for module-level certificate generation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recipient_name: str = Field(
        min_length=1,
        max_length=200,
        description="Full name of the certificate recipient.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CertificateResponse(BaseModel):
    """Certificate record returned after generation or retrieval."""

    model_config = ConfigDict(from_attributes=True)

    certificate_id: UUID
    enrollment_id: UUID
    user_id: UUID
    course_id: UUID
    certificate_url: str = Field(description="S3 URL of the generated PDF certificate.")
    qr_verification_code: str = Field(description="Unique tamper-proof verification code.")
    issued_at: datetime
    recipient_name: str
    course_title: str
    instructor_name: str
    total_hours: Decimal | None = None
    score: int | None = None
    module_id: UUID | None = None
    certificate_type: CertificateType = CertificateType.COURSE
    module_title: str | None = None
    template_used: str | None = None
    verification_url: str | None = Field(
        default=None,
        description="Full URL for QR-based verification.",
    )


class CertificateVerifyResponse(BaseModel):
    """Public verification result (accessed via QR code scan)."""

    is_valid: bool
    certificate_id: UUID | None = None
    recipient_name: str | None = None
    user_id: UUID | None = None
    course_id: UUID | None = None
    course_title: str | None = None
    instructor_name: str | None = None
    total_hours: Decimal | None = None
    score: int | None = None
    issued_at: datetime | None = None
    module_id: UUID | None = None
    certificate_type: CertificateType | None = None
    module_title: str | None = None


class CertificatePreviewResponse(BaseModel):
    """Preview URL for a certificate template."""

    preview_url: str
    cert_template: str | None = None
    cert_title: str | None = None
