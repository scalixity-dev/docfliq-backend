"""Add google_id and microsoft_id to users table for OAuth SSO.

Revision ID: 008
Revises: 007
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("microsoft_id", sa.String(255), nullable=True))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.create_index("ix_users_microsoft_id", "users", ["microsoft_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_microsoft_id", table_name="users")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "microsoft_id")
    op.drop_column("users", "google_id")
