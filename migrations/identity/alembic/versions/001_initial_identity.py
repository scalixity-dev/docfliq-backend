"""Full identity schema: users, auth_sessions, otp_requests, user_verifications

Revision ID: 001
Revises:
Create Date: 2026-02-19

Tables created:
  - users                 Core accounts, profile data, RBAC roles
  - auth_sessions         Persistent refresh-token sessions (one per device)
  - otp_requests          OTP records keyed by phone number (no user FK)
  - user_verifications    Document uploads + admin review records

PostgreSQL-native ENUM types created:
  - userrole              Doctor / Nurse / Student / Pharmacist / Admin
  - verificationstatus    Unverified / Pending / Verified / Rejected / Suspended
  - documenttype          Medical license / ID card / Degree
  - verificationdocstatus Pending / Approved / Rejected
  - otppurpose            Login / 2FA / Password reset

Downgrade: drops all tables and ENUM types in reverse dependency order.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ─────────────────────────────────────────────────────────────────────────────
#  UPGRADE
# ─────────────────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ── 1. PostgreSQL ENUM types ──────────────────────────────────────────────
    # Created before tables so columns can reference them with create_type=False.
    # PostgreSQL has no CREATE TYPE IF NOT EXISTS, so we use a DO/EXCEPTION block.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM (
                'doctor_specialist',
                'doctor_gp',
                'nurse',
                'student',
                'pharmacist',
                'admin'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE verificationstatus AS ENUM (
                'unverified',
                'pending',
                'verified',
                'rejected',
                'suspended'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE documenttype AS ENUM (
                'medical_license',
                'id_card',
                'degree'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE verificationdocstatus AS ENUM (
                'pending',
                'approved',
                'rejected'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE otppurpose AS ENUM (
                'login',
                '2fa',
                'password_reset'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # ── 2. users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        # PK
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Auth identifiers
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        # Profile
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="userrole", create_type=False),
            nullable=False,
        ),
        sa.Column("specialty", sa.String(100), nullable=True),
        sa.Column("sub_specialty", sa.String(100), nullable=True),
        sa.Column("years_of_experience", sa.SmallInteger(), nullable=True),
        sa.Column("location_city", sa.String(100), nullable=True),
        sa.Column("location_state", sa.String(100), nullable=True),
        sa.Column(
            "location_country",
            sa.String(50),
            nullable=True,
            server_default=sa.text("'India'"),
        ),
        sa.Column("profile_image_url", sa.String(500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        # Verification state
        sa.Column(
            "verification_status",
            postgresql.ENUM(name="verificationstatus", create_type=False),
            nullable=False,
            server_default=sa.text("'unverified'"),
        ),
        # Account flags
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_banned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("ban_reason", sa.Text(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        # Discovery
        sa.Column(
            "interests",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
        ),
        # Content creation gate
        sa.Column(
            "content_creation_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Doctor-specific
        sa.Column("medical_license_number", sa.String(100), nullable=True),
        # JWT authorization roles array
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        # Audit timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("phone_number", name="uq_users_phone_number"),
        sa.UniqueConstraint(
            "medical_license_number", name="uq_users_medical_license_number"
        ),
        sa.CheckConstraint(
            "years_of_experience >= 0",
            name="ck_users_years_of_experience_non_negative",
        ),
    )

    # Regular B-tree indexes on users
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone_number", "users", ["phone_number"])
    op.create_index("ix_users_full_name", "users", ["full_name"])
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_specialty", "users", ["specialty"])
    op.create_index("ix_users_location_city", "users", ["location_city"])
    op.create_index(
        "ix_users_verification_status", "users", ["verification_status"]
    )
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_is_banned", "users", ["is_banned"])
    op.create_index(
        "ix_users_content_creation_mode", "users", ["content_creation_mode"]
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_medical_license_number", "users", ["medical_license_number"])

    # GIN index for array containment queries on interests
    op.create_index(
        "ix_users_interests",
        "users",
        ["interests"],
        postgresql_using="gin",
    )

    # ── 3. auth_sessions ──────────────────────────────────────────────────────
    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token", sa.String(512), nullable=False),
        sa.Column("device_id", sa.String(255), nullable=True),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("microsoft_id", sa.String(255), nullable=True),
        sa.Column(
            "device_info",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("refresh_token", name="uq_auth_sessions_refresh_token"),
        sa.UniqueConstraint("google_id", name="uq_auth_sessions_google_id"),
        sa.UniqueConstraint("microsoft_id", name="uq_auth_sessions_microsoft_id"),
    )

    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_refresh_token",
        "auth_sessions",
        ["refresh_token"],
        unique=True,
    )
    op.create_index("ix_auth_sessions_google_id", "auth_sessions", ["google_id"])
    op.create_index(
        "ix_auth_sessions_microsoft_id", "auth_sessions", ["microsoft_id"]
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    # ── 4. otp_requests ───────────────────────────────────────────────────────
    # No FK to users — OTPs are requested before an account may exist
    op.create_table(
        "otp_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        # Hashed OTP code — never stored as plain text
        sa.Column("otp_code", sa.String(255), nullable=False),
        sa.Column(
            "purpose",
            postgresql.ENUM(name="otppurpose", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "is_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "attempts_remaining",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("5"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_otp_requests"),
    )

    op.create_index("ix_otp_requests_phone_number", "otp_requests", ["phone_number"])
    op.create_index("ix_otp_requests_expires_at", "otp_requests", ["expires_at"])

    # ── 5. user_verifications ─────────────────────────────────────────────────
    op.create_table(
        "user_verifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_type",
            postgresql.ENUM(name="documenttype", create_type=False),
            nullable=False,
        ),
        sa.Column("document_url", sa.String(500), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="verificationdocstatus", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # Nullable — set when an admin reviews the document
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_user_verifications"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_verifications_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_user_verifications_reviewed_by",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_user_verifications_user_id", "user_verifications", ["user_id"]
    )
    op.create_index(
        "ix_user_verifications_status", "user_verifications", ["status"]
    )
    op.create_index(
        "ix_user_verifications_created_at", "user_verifications", ["created_at"]
    )

    # ── 6. updated_at trigger (auto-stamp on every row update) ────────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


# ─────────────────────────────────────────────────────────────────────────────
#  DOWNGRADE
# ─────────────────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")

    # Drop tables in reverse FK dependency order
    op.drop_table("user_verifications")
    op.drop_table("otp_requests")
    op.drop_table("auth_sessions")
    op.drop_table("users")

    # Drop ENUM types (must happen after tables are gone)
    op.execute("DROP TYPE IF EXISTS otppurpose")
    op.execute("DROP TYPE IF EXISTS verificationdocstatus")
    op.execute("DROP TYPE IF EXISTS documenttype")
    op.execute("DROP TYPE IF EXISTS verificationstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
