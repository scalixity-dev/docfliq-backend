"""Add username column to users table.

VARCHAR(50), unique, nullable, indexed.
Backfill existing users with slugified full_name (append row number if needed).

Revision ID: 012
Revises: 011
Create Date: 2026-02-24
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", name.lower())
    return slug or "user"


def upgrade() -> None:
    # 1. Add nullable column first (no default needed)
    op.add_column(
        "users",
        sa.Column("username", sa.String(50), nullable=True),
    )

    # 2. Backfill existing users with a deterministic unique username.
    #    Uses a window function (row_number) to handle duplicate names:
    #    first occurrence gets the clean slug, subsequent ones get slug + row_number.
    op.execute(
        """
        WITH slugs AS (
            SELECT
                id,
                LOWER(REGEXP_REPLACE(full_name, '[^a-zA-Z0-9]', '', 'g')) AS base_slug,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(REGEXP_REPLACE(full_name, '[^a-zA-Z0-9]', '', 'g'))
                    ORDER BY created_at
                ) AS rn
            FROM users
        )
        UPDATE users
        SET username = CASE
            WHEN slugs.rn = 1 THEN LEFT(slugs.base_slug, 50)
            ELSE LEFT(slugs.base_slug, 46) || slugs.rn::text
        END
        FROM slugs
        WHERE users.id = slugs.id
        """
    )

    # Handle any NULL base_slug (empty names) — set to 'user' + id prefix
    op.execute(
        """
        UPDATE users
        SET username = 'user' || LEFT(id::text, 8)
        WHERE username IS NULL OR username = ''
        """
    )

    # 3. Create unique index
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
