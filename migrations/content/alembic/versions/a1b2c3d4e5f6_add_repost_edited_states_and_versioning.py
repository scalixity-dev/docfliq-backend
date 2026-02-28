"""Add REPOST content type, EDITED/SOFT_DELETED/HIDDEN_BY_ADMIN post statuses, and post_versions table.

Revision ID: a1b2c3d4e5f6
Revises: 2937ecd08870
Create Date: 2026-02-19 16:00:00.000000

Changes:
  1. Add REPOST to content_type enum
  2. Add EDITED, SOFT_DELETED, HIDDEN_BY_ADMIN to post_status enum
     (Note: old HIDDEN and DELETED values are kept for backwards compatibility
      during data migration — they are migrated to new values then effectively unused)
  3. Migrate existing data: HIDDEN -> HIDDEN_BY_ADMIN, DELETED -> SOFT_DELETED
  4. Add original_post_id column to posts (FK to posts, SET NULL)
  5. Add deleted_at column to posts (nullable TIMESTAMP WITH TIME ZONE)
  6. Add SharePlatform enum
  7. Create post_versions table
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "2937ecd08870"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add REPOST to content_type enum
    # ------------------------------------------------------------------
    op.execute("ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'REPOST'")

    # ------------------------------------------------------------------
    # 2. Add new post_status enum values
    #    PostgreSQL requires committing the enum addition before using them.
    # ------------------------------------------------------------------
    op.execute("ALTER TYPE post_status ADD VALUE IF NOT EXISTS 'EDITED'")
    op.execute("ALTER TYPE post_status ADD VALUE IF NOT EXISTS 'SOFT_DELETED'")
    op.execute("ALTER TYPE post_status ADD VALUE IF NOT EXISTS 'HIDDEN_BY_ADMIN'")

    # Commit so the new enum labels are visible for the data migration below
    op.execute("COMMIT")
    op.execute("BEGIN")

    # ------------------------------------------------------------------
    # 3. Migrate existing data to new enum values
    # ------------------------------------------------------------------
    op.execute(
        "UPDATE posts SET status = 'HIDDEN_BY_ADMIN' WHERE status = 'HIDDEN'"
    )
    op.execute(
        "UPDATE posts SET status = 'SOFT_DELETED' WHERE status = 'DELETED'"
    )

    # ------------------------------------------------------------------
    # 4. Add original_post_id to posts (self-referential FK, nullable)
    # ------------------------------------------------------------------
    op.add_column(
        "posts",
        sa.Column(
            "original_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.post_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_posts_original_post_id", "posts", ["original_post_id"])

    # ------------------------------------------------------------------
    # 5. Add deleted_at to posts (nullable timestamp)
    # ------------------------------------------------------------------
    op.add_column(
        "posts",
        sa.Column(
            "deleted_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 6. Create post_versions table
    # ------------------------------------------------------------------
    op.create_table(
        "post_versions",
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.post_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("media_urls", postgresql.JSONB, nullable=True),
        sa.Column("link_preview", postgresql.JSONB, nullable=True),
        sa.Column(
            "edited_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_post_versions_post_id", "post_versions", ["post_id"])
    op.create_index(
        "ix_post_versions_post_version",
        "post_versions",
        ["post_id", "version_number"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop post_versions table
    # ------------------------------------------------------------------
    op.drop_index("ix_post_versions_post_version", table_name="post_versions")
    op.drop_index("ix_post_versions_post_id", table_name="post_versions")
    op.drop_table("post_versions")

    # ------------------------------------------------------------------
    # Remove columns from posts
    # ------------------------------------------------------------------
    op.drop_column("posts", "deleted_at")
    op.drop_index("ix_posts_original_post_id", table_name="posts")
    op.drop_column("posts", "original_post_id")

    # ------------------------------------------------------------------
    # Migrate data back (best-effort — HIDDEN_BY_ADMIN -> HIDDEN, etc.)
    # ------------------------------------------------------------------
    op.execute(
        "UPDATE posts SET status = 'HIDDEN' WHERE status = 'HIDDEN_BY_ADMIN'"
    )
    op.execute(
        "UPDATE posts SET status = 'DELETED' WHERE status = 'SOFT_DELETED'"
    )
    op.execute(
        "UPDATE posts SET status = 'PUBLISHED' WHERE status = 'EDITED'"
    )

    # Note: PostgreSQL does not support DROP VALUE on enums.
    # The REPOST, EDITED, SOFT_DELETED, HIDDEN_BY_ADMIN labels will remain
    # in the enum type but will no longer be used in data.
    # To fully remove them requires recreating the enum type.
