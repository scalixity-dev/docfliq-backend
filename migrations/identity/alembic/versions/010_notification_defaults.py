"""Set server_default for notification_preferences (all ON) and backfill NULLs.

Revision ID: 010
Revises: 009
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_DEFAULT = '{"email": true, "push": true, "course": true, "webinar": true, "marketing": true}'


def upgrade() -> None:
    # Set server default for new rows
    op.alter_column(
        "users",
        "notification_preferences",
        server_default=sa.text(f"'{_DEFAULT}'::jsonb"),
    )
    # Backfill existing rows that have NULL
    op.execute(
        f"UPDATE users SET notification_preferences = '{_DEFAULT}'::jsonb "
        "WHERE notification_preferences IS NULL"
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "notification_preferences",
        server_default=None,
    )
