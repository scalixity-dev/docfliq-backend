"""Add composite indexes for frequently queried column combinations.

- otp_requests(phone_number, purpose): speeds up active OTP lookups
- password_reset_tokens(email, is_used): speeds up active reset token lookups
- auth_sessions(user_id, created_at): speeds up oldest-session eviction query

Revision ID: 014
Revises: 013
Create Date: 2026-02-25
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_otp_requests_phone_purpose",
        "otp_requests",
        ["phone_number", "purpose"],
    )
    op.create_index(
        "ix_password_reset_tokens_email_used",
        "password_reset_tokens",
        ["email", "is_used"],
    )
    op.create_index(
        "ix_auth_sessions_user_created",
        "auth_sessions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_created", table_name="auth_sessions")
    op.drop_index("ix_password_reset_tokens_email_used", table_name="password_reset_tokens")
    op.drop_index("ix_otp_requests_phone_purpose", table_name="otp_requests")
