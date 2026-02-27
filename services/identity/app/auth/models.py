"""
Identity service — SQLAlchemy ORM models for the auth domain.

Tables owned by this module:
  - users                  Core user accounts, profile data, and RBAC roles
  - auth_sessions          Persistent JWT refresh-token sessions (one per device)
  - otp_requests           One-time password records keyed by phone number
  - password_reset_tokens  Email-keyed OTP records for password reset flow
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.database.postgres import Base

from app.auth.constants import OTPPurpose, UserRole, VerificationStatus


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # GIN index for fast array containment queries on interests
        sa.Index("ix_users_interests", "interests", postgresql_using="gin"),
        sa.CheckConstraint(
            "years_of_experience >= 0",
            name="ck_users_years_of_experience_non_negative",
        ),
    )

    # ── Primary key ──────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Authentication identifiers ────────────────────────────────────────────
    # email is the primary login credential for email/password flow
    email: Mapped[str] = mapped_column(
        sa.String(255), unique=True, nullable=False, index=True
    )
    # phone_number is the primary identifier for OTP flow (nullable for email-only users)
    phone_number: Mapped[str | None] = mapped_column(
        sa.String(20), unique=True, nullable=True, index=True
    )
    # nullable: OTP-only and SSO users have no password
    password_hash: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )

    # ── Profile fields ────────────────────────────────────────────────────────
    full_name: Mapped[str] = mapped_column(
        sa.String(150), nullable=False, index=True
    )
    # Unique handle displayed as @username — auto-generated from full_name on creation
    username: Mapped[str | None] = mapped_column(
        sa.String(50), unique=True, nullable=True, index=True
    )
    # Professional role — drives content access and profile field requirements
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(
            UserRole,
            name="userrole",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )
    specialty: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True, index=True
    )
    sub_specialty: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    years_of_experience: Mapped[int | None] = mapped_column(
        sa.SmallInteger(), nullable=True
    )
    location_city: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True, index=True
    )
    location_state: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    location_country: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True, server_default=sa.text("'India'")
    )
    profile_image_url: Mapped[str | None] = mapped_column(
        sa.String(500), nullable=True
    )
    banner_url: Mapped[str | None] = mapped_column(
        sa.String(500), nullable=True
    )
    bio: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)

    # ── Verification state machine ────────────────────────────────────────────
    verification_status: Mapped[VerificationStatus] = mapped_column(
        sa.Enum(
            VerificationStatus,
            name="verificationstatus",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=sa.text("'unverified'"),
        index=True,
    )

    # ── Email verification ────────────────────────────────────────────────────
    # Flipped to True when the user clicks the verification link in their email.
    # OTP-registered users get a placeholder email so this starts False for them too
    # (they can optionally add a real email via profile update in a future phase).
    email_verified: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )

    # ── Onboarding flag ────────────────────────────────────────────────────────
    # True until the user completes sign-up questions (role, location, etc.)
    is_new_user: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )

    # ── Account flags ─────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=True,
        server_default=sa.text("true"),
        index=True,
    )
    is_banned: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        index=True,
    )
    ban_reason: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    # ── Discovery / recommendation ────────────────────────────────────────────
    # Array of topic tag strings for cold-start recommendation engine (GIN indexed)
    interests: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.String(100)), nullable=True
    )
    # Onboarding preferences (Step 1: purposes, Step 3: event schedule, languages)
    purposes: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.String(100)), nullable=True
    )
    event_schedule: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.String(100)), nullable=True
    )
    languages: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.String(100)), nullable=True
    )

    # ── Content creation gate ─────────────────────────────────────────────────
    # Set to True when user becomes VERIFIED and is eligible to create content
    content_creation_mode: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        index=True,
    )

    # ── OAuth provider identifiers ─────────────────────────────────────────────
    google_id: Mapped[str | None] = mapped_column(
        sa.String(255), unique=True, nullable=True, index=True
    )
    microsoft_id: Mapped[str | None] = mapped_column(
        sa.String(255), unique=True, nullable=True, index=True
    )

    # ── Doctor-specific ───────────────────────────────────────────────────────
    medical_license_number: Mapped[str | None] = mapped_column(
        sa.String(100), unique=True, nullable=True, index=True
    )

    # ── Role-specific profile fields (migration 005) ───────────────────────────
    # Doctor Specialist / Doctor GP / Nurse
    hospital_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    # Nurse — certification or specialty area credential
    certification: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    # Student
    university: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(sa.SmallInteger(), nullable=True)
    student_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    # Pharmacist — separate from medical_license_number
    pharmacist_license_number: Mapped[str | None] = mapped_column(
        sa.String(100), unique=True, nullable=True
    )
    pharmacy_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)

    # ── Notification preferences ──────────────────────────────────────────────
    # JSONB dict storing per-channel toggles — all ON by default for new users
    notification_preferences: Mapped[dict | None] = mapped_column(
        JSONB(),
        nullable=True,
        server_default=sa.text(
            "'{\"email\": true, \"push\": true, \"course\": true, \"webinar\": true, \"marketing\": true}'::jsonb"
        ),
    )

    # ── JWT authorization roles (USER / CREATOR / ADMIN / SUPER_ADMIN) ────────
    # Separate from `role` — these drive permission checks across all services.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(sa.String()),
        nullable=False,
        default=list,
        server_default=sa.text("ARRAY[]::varchar[]"),
    )

    # ── Audit timestamps ──────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    sessions: Mapped[list[AuthSession]] = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
        # Order newest first so eviction of oldest is trivial
        order_by="AuthSession.created_at.desc()",
    )


class AuthSession(Base):
    """
    Persistent refresh-token session record.

    One row per active device session. Soft-limited to MAX_SESSIONS_PER_USER
    (5) per user — oldest session is evicted when the 6th is created.
    Token rotation: on every /auth/refresh the old refresh_token is deleted
    and a new row is inserted (rotation prevents replay attacks).
    """

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_auth_sessions_user_id"),
        nullable=False,
        index=True,
    )
    # Opaque random token stored as the session secret (not a JWT)
    refresh_token: Mapped[str] = mapped_column(
        sa.String(512), unique=True, nullable=False, index=True
    )
    # Client device fingerprint for session labelling and eviction ordering
    device_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # OAuth provider sub-identifiers (unique per active session)
    google_id: Mapped[str | None] = mapped_column(
        sa.String(255), unique=True, nullable=True, index=True
    )
    microsoft_id: Mapped[str | None] = mapped_column(
        sa.String(255), unique=True, nullable=True, index=True
    )
    # Arbitrary device/browser metadata as JSONB (e.g. user-agent, OS)
    device_info: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET(), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")


class OTPRequest(Base):
    """
    One-time password record keyed by phone number.

    No FK to users because OTPs can be requested before an account exists
    (first-time mobile registration creates the user on successful verify).
    Single-use: is_used is set to True immediately on first successful verify.
    Max 5 verify attempts before the OTP is invalidated entirely.
    """

    __tablename__ = "otp_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, index=True
    )
    # Hashed OTP code — never store plaintext
    otp_code: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    purpose: Mapped[OTPPurpose] = mapped_column(
        sa.Enum(
            OTPPurpose,
            name="otppurpose",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    # Remaining verification attempts before OTP is invalidated
    attempts_remaining: Mapped[int] = mapped_column(
        sa.SmallInteger(),
        nullable=False,
        default=5,
        server_default=sa.text("5"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PasswordResetToken(Base):
    """
    Email-keyed OTP record for the password reset flow.

    No FK to users — the email may be submitted for a non-existent account;
    we return the same 200 either way to prevent enumeration.
    Single-use: is_used set True on successful confirm.
    Max 5 verify attempts before the token is invalidated.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        sa.String(255), nullable=False, index=True
    )
    # Hashed OTP code — never store plaintext
    token_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_used: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    attempts_remaining: Mapped[int] = mapped_column(
        sa.SmallInteger(),
        nullable=False,
        default=5,
        server_default=sa.text("5"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
