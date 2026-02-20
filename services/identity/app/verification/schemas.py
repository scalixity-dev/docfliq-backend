"""
Verification domain — Pydantic V2 request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth.constants import DocumentType, VerificationDocStatus, VerificationStatus


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── User-facing ───────────────────────────────────────────────────────────────

class UploadRequest(_Base):
    """Request a presigned S3 PUT URL for a verification document."""

    document_type: DocumentType
    content_type: Literal["image/jpeg", "image/png", "application/pdf"] = "application/pdf"


class UploadResponse(BaseModel):
    upload_url: str                  # Presigned S3 PUT URL (15-min expiry)
    document_key: str                # S3 key — pass this to /confirm
    expires_in: int                  # Seconds until upload_url expires


class ConfirmRequest(_Base):
    """Confirm that the S3 upload completed and submit for admin review."""

    document_key: str = Field(min_length=1)
    document_type: DocumentType


class VerificationSubmittedResponse(BaseModel):
    verification_id: uuid.UUID
    status: VerificationDocStatus
    message: str


# ── Admin-facing ──────────────────────────────────────────────────────────────

class VerificationQueueItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    document_type: DocumentType
    status: VerificationDocStatus
    created_at: datetime


class VerificationQueueResponse(BaseModel):
    items: list[VerificationQueueItem]
    total: int
    page: int
    size: int


class DocumentViewResponse(BaseModel):
    view_url: str        # Presigned S3 GET URL (30-min expiry)
    expires_in: int      # Seconds until view_url expires
    document_type: DocumentType


class ReviewRequest(_Base):
    action: Literal["APPROVE", "REJECT"]
    notes: str | None = Field(
        None,
        max_length=1000,
        description="Required when action=REJECT (rejection reason shown to the user). Optional when action=APPROVE.",
    )

    @model_validator(mode="after")
    def notes_required_for_rejection(self) -> "ReviewRequest":
        if self.action == "REJECT" and not (self.notes or "").strip():
            raise ValueError(
                "A rejection reason is required when action is REJECT. "
                "Provide a clear explanation so the user knows what to fix."
            )
        return self


class ReviewResponse(BaseModel):
    id: uuid.UUID
    status: VerificationDocStatus
    reviewed_at: datetime | None


class SuspendRequest(_Base):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Reason for suspension — communicated to the user via email.",
    )


class UserStatusResponse(BaseModel):
    id: uuid.UUID
    verification_status: VerificationStatus
