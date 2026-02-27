"""Add is_new_user boolean flag to users table.

True by default for new users. Set to False when user completes onboarding.
Existing users are backfilled to False (they already completed onboarding).

Revision ID: 013
Revises: 012
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column with server_default=true (new users start as new)
    op.add_column(
        "users",
        sa.Column(
            "is_new_user",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Backfill: mark ALL existing users as NOT new (they already onboarded)
    op.execute("UPDATE users SET is_new_user = false")


def downgrade() -> None:
    op.drop_column("users", "is_new_user")
