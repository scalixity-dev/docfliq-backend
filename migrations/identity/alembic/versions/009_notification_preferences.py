"""Add notification_preferences JSONB column to users table.

Stores per-channel notification toggles, e.g.:
  {"email": true, "push": true, "course": true, "webinar": true, "marketing": false}

Revision ID: 009
Revises: 008
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notification_preferences", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "notification_preferences")
