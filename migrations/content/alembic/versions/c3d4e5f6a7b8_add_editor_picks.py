"""Add editor_picks table for feed cold-start and curation.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-02-19 18:00:00.000000

Changes:
  1. Create editor_picks table with columns:
       pick_id (UUID PK), post_id (FK → posts, CASCADE), added_by (UUID),
       priority (INT), is_active (BOOL), created_at (TIMESTAMPTZ)
  2. Unique constraint: uq_editor_picks_post_id (post_id)
  3. Indexes: ix_editor_picks_priority, ix_editor_picks_is_active
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "c3d4e5f6a7b8"
down_revision: str = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_picks",
        sa.Column("pick_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("posts.post_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("added_by", UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("post_id", name="uq_editor_picks_post_id"),
    )
    op.create_index("ix_editor_picks_priority", "editor_picks", ["priority"])
    op.create_index("ix_editor_picks_is_active", "editor_picks", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_editor_picks_is_active", table_name="editor_picks")
    op.drop_index("ix_editor_picks_priority", table_name="editor_picks")
    op.drop_table("editor_picks")
