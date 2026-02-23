"""
Admin domain — Pydantic V2 request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.constants import UserRole, VerificationStatus


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        str_min_length=0,
    )


# ── Requests ─────────────────────────────────────────────────────────────────

class AdminCreateUserRequest(_Base):
    """Body for POST /admin/users/create — create an admin account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)


class AdminBanUserRequest(_Base):
    """Body for PATCH /admin/users/{user_id}/ban."""

    reason: str = Field(
        min_length=1,
        max_length=500,
        description="Reason for banning — stored on the user record.",
    )


# ── Responses ────────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    """Single user record returned to admin panel."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    roles: list[str]
    phone_number: str | None
    specialty: str | None
    medical_license_number: str | None
    hospital_name: str | None
    verification_status: VerificationStatus
    email_verified: bool
    is_active: bool
    is_banned: bool
    ban_reason: str | None
    content_creation_mode: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUserListResponse(BaseModel):
    """Paginated list of users."""

    model_config = ConfigDict(extra="forbid")

    items: list[AdminUserResponse]
    total: int
    page: int
    size: int
