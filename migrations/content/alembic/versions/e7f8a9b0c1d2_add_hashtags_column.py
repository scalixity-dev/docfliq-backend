"""Add hashtags ARRAY column to posts table.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-02-27 12:00:00.000000

Changes:
  1. Add hashtags ARRAY(String) column to posts table
  2. Create GIN index for fast array overlap/containment queries
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e7f8a9b0c1d2"
down_revision = "2479fedf9df9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("hashtags", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.create_index(
        "ix_posts_hashtags",
        "posts",
        ["hashtags"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_posts_hashtags", table_name="posts")
    op.drop_column("posts", "hashtags")
