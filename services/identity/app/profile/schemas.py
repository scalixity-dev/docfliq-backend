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
    UserRole.DOCTOR_SPECIALIST: ["specialty", "hospital_name", "medical_license_number"],
    UserRole.DOCTOR_GP: ["specialty", "hospital_name", "medical_license_number"],
    UserRole.NURSE: ["specialty", "hospital_name", "certification"],
    UserRole.STUDENT: ["university", "graduation_year", "student_id"],
    UserRole.PHARMACIST: ["pharmacist_license_number", "pharmacy_name"],
    UserRole.ADMIN: [],
}


# ── Request ───────────────────────────────────────────────────────────────────

class UpdateProfileRequest(_Base):
    """PATCH /users/me — all fields optional; only provided fields are written."""

    full_name: str | None = Field(None, min_length=1, max_length=150)
    specialty: str | None = Field(None, max_length=100)
    sub_specialty: str | None = Field(None, max_length=100)
    years_of_experience: int | None = Field(None, ge=0, le=80)
    location_city: str | None = Field(None, max_length=100)
    location_state: str | None = Field(None, max_length=100)
    location_country: str | None = Field(None, max_length=50)
    bio: str | None = None
    interests: list[str] | None = None
    # Doctor (Specialist / GP) + Nurse
    medical_license_number: str | None = Field(None, max_length=100)
    hospital_name: str | None = Field(None, max_length=200)
    # Nurse
    certification: str | None = Field(None, max_length=200)
    # Student
    university: str | None = Field(None, max_length=200)
    graduation_year: int | None = Field(None, ge=1980, le=2060)
    student_id: str | None = Field(None, max_length=100)
    # Pharmacist
    pharmacist_license_number: str | None = Field(None, max_length=100)
    pharmacy_name: str | None = Field(None, max_length=200)


# ── Response ──────────────────────────────────────────────────────────────────

class CapabilitiesResponse(BaseModel):
    """Role + verification-based capability flags.

    Informational for the frontend and for downstream services that read the JWT.
    Actual enforcement happens in the content/webinar/course service (MS-2+).
    """

    model_config = ConfigDict(extra="forbid")

    can_create_courses: bool
    """Doctor Specialist only, after verification."""

    can_be_speaker: bool
    """Doctor Specialist and Doctor GP only, after verification."""

    can_post_community: bool
    """All verified non-student roles (Doctor, Nurse, Pharmacist)."""

    has_full_content_access: bool
    """True for all verified non-student roles. Students always False."""

    student_restricted: bool
    """True only for Student role — free courses + public content only."""


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
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
    verification_status: VerificationStatus
    content_creation_mode: bool
    email_verified: bool
    # Doctor (Specialist / GP) + Nurse
    medical_license_number: str | None
    hospital_name: str | None
    # Nurse
    certification: str | None
    # Student
    university: str | None
    graduation_year: int | None
    student_id: str | None
    # Pharmacist
    pharmacist_license_number: str | None
    pharmacy_name: str | None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def capabilities(self) -> CapabilitiesResponse:
        """Compute role-based capabilities from current role + verification status."""
        is_verified = self.verification_status == VerificationStatus.VERIFIED
        role = self.role
        return CapabilitiesResponse(
            can_create_courses=is_verified and role == UserRole.DOCTOR_SPECIALIST,
            can_be_speaker=is_verified and role in {
                UserRole.DOCTOR_SPECIALIST,
                UserRole.DOCTOR_GP,
            },
            can_post_community=is_verified and role in {
                UserRole.DOCTOR_SPECIALIST,
                UserRole.DOCTOR_GP,
                UserRole.NURSE,
                UserRole.PHARMACIST,
            },
            has_full_content_access=is_verified and role != UserRole.STUDENT,
            student_restricted=role == UserRole.STUDENT,
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
