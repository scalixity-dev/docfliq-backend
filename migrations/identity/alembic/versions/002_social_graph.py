"""Social graph: follows, blocks, mutes, reports

Revision ID: 002
Revises: 001
Create Date: 2026-02-19

Tables created:
  - follows   Unidirectional follow edges (follower → following)
  - blocks    Block edges (blocker blocks blocked); CASCADE removes on user delete
  - mutes     Mute edges (muter mutes muted)
  - reports   User/content reports submitted for admin review

PostgreSQL ENUM types created:
  - reporttargettype   user / post / comment / webinar
  - reportstatus       open / reviewed / actioned / dismissed
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ─────────────────────────────────────────────────────────────────────────────
#  UPGRADE
# ─────────────────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ── 1. New PostgreSQL ENUM types ──────────────────────────────────────────
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE reporttargettype AS ENUM (
                'user',
                'post',
                'comment',
                'webinar'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE reportstatus AS ENUM (
                'open',
                'reviewed',
                'actioned',
                'dismissed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # ── 2. follows ────────────────────────────────────────────────────────────
    op.create_table(
        "follows",
        sa.Column(
            "follow_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("follower_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("following_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("follow_id", name="pk_follows"),
        sa.ForeignKeyConstraint(
            ["follower_id"],
            ["users.id"],
            name="fk_follows_follower_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["following_id"],
            ["users.id"],
            name="fk_follows_following_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("follower_id", "following_id", name="uq_follows_pair"),
        sa.CheckConstraint("follower_id != following_id", name="ck_follows_no_self"),
    )
    op.create_index("idx_follows_follower_id", "follows", ["follower_id"])
    op.create_index("idx_follows_following_id", "follows", ["following_id"])

    # ── 3. blocks ─────────────────────────────────────────────────────────────
    op.create_table(
        "blocks",
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("blocker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blocked_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("block_id", name="pk_blocks"),
        sa.ForeignKeyConstraint(
            ["blocker_id"],
            ["users.id"],
            name="fk_blocks_blocker_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["blocked_id"],
            ["users.id"],
            name="fk_blocks_blocked_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocks_pair"),
        sa.CheckConstraint("blocker_id != blocked_id", name="ck_blocks_no_self"),
    )
    op.create_index("idx_blocks_blocker_id", "blocks", ["blocker_id"])
    op.create_index("idx_blocks_blocked_id", "blocks", ["blocked_id"])

    # ── 4. mutes ──────────────────────────────────────────────────────────────
    op.create_table(
        "mutes",
        sa.Column(
            "mute_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("muter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("muted_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("mute_id", name="pk_mutes"),
        sa.ForeignKeyConstraint(
            ["muter_id"],
            ["users.id"],
            name="fk_mutes_muter_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["muted_id"],
            ["users.id"],
            name="fk_mutes_muted_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("muter_id", "muted_id", name="uq_mutes_pair"),
        sa.CheckConstraint("muter_id != muted_id", name="ck_mutes_no_self"),
    )
    op.create_index("idx_mutes_muter_id", "mutes", ["muter_id"])
    op.create_index("idx_mutes_muted_id", "mutes", ["muted_id"])

    # ── 5. reports ────────────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "target_type",
            postgresql.ENUM(name="reporttargettype", create_type=False),
            nullable=False,
        ),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="reportstatus", create_type=False),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        # Nullable — set when an admin reviews the report
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_taken", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("report_id", name="pk_reports"),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name="fk_reports_reporter_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_reports_reviewed_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("idx_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("idx_reports_status", "reports", ["status"])
    op.create_index("idx_reports_target", "reports", ["target_type", "target_id"])


# ─────────────────────────────────────────────────────────────────────────────
#  DOWNGRADE
# ─────────────────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Drop tables in reverse FK dependency order
    op.drop_table("reports")
    op.drop_table("mutes")
    op.drop_table("blocks")
    op.drop_table("follows")

    # Drop ENUM types (must happen after tables are gone)
    op.execute("DROP TYPE IF EXISTS reportstatus")
    op.execute("DROP TYPE IF EXISTS reporttargettype")
