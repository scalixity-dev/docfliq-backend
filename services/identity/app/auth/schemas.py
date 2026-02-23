"""
Identity service — Pydantic V2 request/response schemas for the auth domain.

Separation of concerns:
  - *Request  models:  input from the client (strict extra="forbid")
  - *Response models:  output to the client (no write-only fields exposed)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.constants import UserRole, VerificationStatus


# ── Shared base ───────────────────────────────────────────────────────────────

class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        str_min_length=0,
    )


# ── Email + Password flow ─────────────────────────────────────────────────────

class RegisterRequest(_Base):
    """Body for POST /auth/register (email + password flow)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    role: UserRole
    # Common optional at signup (can be completed via PATCH /users/me later)
    phone_number: str | None = Field(
        default=None,
        pattern=r"^\+?[1-9]\d{9,14}$",
        description="E.164 format, e.g. +919876543210",
    )
    specialty: str | None = Field(default=None, max_length=100)
    sub_specialty: str | None = Field(default=None, max_length=100)
    years_of_experience: int | None = Field(default=None, ge=0, le=80)
    # Doctor (Specialist / GP) + Nurse
    medical_license_number: str | None = Field(default=None, max_length=100)
    hospital_name: str | None = Field(default=None, max_length=200)
    # Nurse
    certification: str | None = Field(default=None, max_length=200)
    # Student
    university: str | None = Field(default=None, max_length=200)
    graduation_year: int | None = Field(default=None, ge=1980, le=2060)
    student_id: str | None = Field(default=None, max_length=100)
    # Pharmacist
    pharmacist_license_number: str | None = Field(default=None, max_length=100)
    pharmacy_name: str | None = Field(default=None, max_length=200)


class LoginRequest(_Base):
    """Body for POST /auth/login."""

    email: EmailStr
    password: str


# ── OTP flow ──────────────────────────────────────────────────────────────────

class OTPRequestSchema(_Base):
    """Body for POST /auth/otp/request — sends a 6-digit code via SMS."""

    phone_number: str = Field(
        pattern=r"^\+?[1-9]\d{9,14}$",
        description="E.164 format, e.g. +919876543210",
    )


class OTPVerifyRequest(_Base):
    """
    Body for POST /auth/otp/verify.

    For first-time registrations, full_name and role are required because
    the user account is created on this call.  For returning users these
    fields are ignored.
    """

    phone_number: str = Field(pattern=r"^\+?[1-9]\d{9,14}$")
    otp_code: str = Field(min_length=6, max_length=6)
    # Required only for first-time registration via OTP
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    role: UserRole | None = None


# ── Token management ──────────────────────────────────────────────────────────

class RefreshRequest(_Base):
    """Body for POST /auth/refresh."""

    refresh_token: str


class LogoutRequest(_Base):
    """Body for POST /auth/logout — invalidates a single session."""

    refresh_token: str


# ── Response models ───────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """
    Returned on successful register / login / refresh.

    refresh_token is returned in the body; callers should store it in an
    httpOnly cookie or secure storage — never in localStorage.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime in seconds


class UserResponse(BaseModel):
    """Public user profile returned after registration / login."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    phone_number: str | None
    specialty: str | None
    verification_status: VerificationStatus
    content_creation_mode: bool
    is_active: bool
    created_at: datetime


class RegisterResponse(BaseModel):
    """Combined response for POST /auth/register."""

    model_config = ConfigDict(extra="forbid")

    user: UserResponse
    tokens: TokenResponse


class MessageResponse(BaseModel):
    """Generic single-message response for informational 200/201 endpoints."""

    model_config = ConfigDict(extra="forbid")

    message: str


# ── Password reset ─────────────────────────────────────────────────────────────

class PasswordResetRequestSchema(_Base):
    """Body for POST /auth/password-reset/request."""

    email: EmailStr


class PasswordResetConfirmSchema(_Base):
    """Body for POST /auth/password-reset/confirm."""

    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6, description="6-digit code sent to email")
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetLinkConfirmSchema(_Base):
    """Body for POST /auth/password-reset/confirm-link (link-based flow)."""

    token: str = Field(description="URL-safe token from the reset link in the email")
    new_password: str = Field(min_length=8, max_length=128)


# ── Email OTP (6-digit verification code sent via email) ─────────────────────

class EmailOTPRequestSchema(_Base):
    """Body for POST /auth/email-otp/request — sends a 6-digit code via email."""

    email: EmailStr


class EmailOTPVerifyRequest(_Base):
    """Body for POST /auth/email-otp/verify — verifies the 6-digit email code."""

    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6, description="6-digit code sent to email")
