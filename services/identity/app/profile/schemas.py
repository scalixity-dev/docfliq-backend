"""
Profile domain — Pydantic V2 request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.auth.constants import UserRole, VerificationStatus


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── Role-specific required fields (used for profile_complete computation) ──────

_REQUIRED_FIELDS: dict[UserRole, list[str]] = {
    UserRole.PHYSICIAN: ["specialty"],
    UserRole.ASSOCIATION: [],
    UserRole.NON_PHYSICIAN: [],
    UserRole.ADMIN: [],
}


# ── Request ───────────────────────────────────────────────────────────────────

class UpdateProfileRequest(_Base):
    """PATCH /users/me — all fields optional; only provided fields are written."""

    full_name: str | None = Field(None, min_length=1, max_length=150)
    role: UserRole | None = None
    specialty: str | None = Field(None, max_length=100)
    sub_specialty: str | None = Field(None, max_length=100)
    years_of_experience: int | None = Field(None, ge=0, le=80)
    location_city: str | None = Field(None, max_length=100)
    location_state: str | None = Field(None, max_length=100)
    location_country: str | None = Field(None, max_length=50)
    bio: str | None = None
    interests: list[str] | None = None
    purposes: list[str] | None = None
    event_schedule: list[str] | None = None
    languages: list[str] | None = None
    # Physician-specific
    medical_license_number: str | None = Field(None, max_length=100)
    hospital_name: str | None = Field(None, max_length=200)
    # Legacy fields (kept for backwards compatibility)
    certification: str | None = Field(None, max_length=200)
    university: str | None = Field(None, max_length=200)
    graduation_year: int | None = Field(None, ge=1980, le=2060)
    student_id: str | None = Field(None, max_length=100)
    pharmacist_license_number: str | None = Field(None, max_length=100)
    pharmacy_name: str | None = Field(None, max_length=200)
    # Phone number (E.164 format, e.g. "+919876543210")
    phone_number: str | None = Field(None, max_length=20)
    # Notification preferences — JSONB dict of channel toggles
    notification_preferences: dict | None = None
    # Set to False when user completes onboarding
    is_new_user: bool | None = None


# ── Response ──────────────────────────────────────────────────────────────────

class CapabilitiesResponse(BaseModel):
    """Role + verification-based capability flags.

    Informational for the frontend and for downstream services that read the JWT.
    Actual enforcement happens in the content/webinar/course service (MS-2+).
    """

    model_config = ConfigDict(extra="forbid")

    can_create_courses: bool
    """Physician only, after verification."""

    can_be_speaker: bool
    """Physician only, after verification."""

    can_post_community: bool
    """Physician only, after verification."""

    has_full_content_access: bool
    """True for verified Physicians."""

    consumer_only: bool
    """True for NON_PHYSICIAN role — can consume content but not create it."""


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    phone_number: str | None
    full_name: str
    username: str | None
    role: UserRole
    specialty: str | None
    sub_specialty: str | None
    years_of_experience: int | None
    location_city: str | None
    location_state: str | None
    location_country: str | None
    profile_image_url: str | None
    bio: str | None
    interests: list[str] | None
    purposes: list[str] | None
    event_schedule: list[str] | None
    languages: list[str] | None
    verification_status: VerificationStatus
    content_creation_mode: bool
    email_verified: bool
    # Physician-specific
    medical_license_number: str | None
    hospital_name: str | None
    # Legacy fields (kept for backwards compatibility)
    certification: str | None
    university: str | None
    graduation_year: int | None
    student_id: str | None
    pharmacist_license_number: str | None
    pharmacy_name: str | None
    # Notification preferences
    notification_preferences: dict | None
    is_new_user: bool
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def capabilities(self) -> CapabilitiesResponse:
        """Compute role-based capabilities from current role + verification status."""
        is_verified = self.verification_status == VerificationStatus.VERIFIED
        is_physician_verified = is_verified and self.role == UserRole.PHYSICIAN
        return CapabilitiesResponse(
            can_create_courses=is_physician_verified,
            can_be_speaker=is_physician_verified,
            can_post_community=is_physician_verified,
            has_full_content_access=is_physician_verified,
            consumer_only=self.role == UserRole.NON_PHYSICIAN,
        )

    @computed_field  # type: ignore[misc]
    @property
    def profile_complete(self) -> bool:
        """True when all role-required fields are filled."""
        return len(self.missing_required_fields) == 0

    @computed_field  # type: ignore[misc]
    @property
    def missing_required_fields(self) -> list[str]:
        """Field names required for this role that are not yet set."""
        required = _REQUIRED_FIELDS.get(self.role, [])
        return [f for f in required if getattr(self, f, None) in (None, "")]
