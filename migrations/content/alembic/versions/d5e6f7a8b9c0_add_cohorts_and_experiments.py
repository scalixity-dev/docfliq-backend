"""Add cohorts, ab_experiments, and experiment_events tables for A/B testing.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-02-19 19:00:00.000000

Changes:
  1. Create PgEnum types: experiment_status, experiment_event_type
  2. Create cohorts table (admin-defined user segments with feed algorithm overrides)
  3. Create ab_experiments table (multi-variant A/B test linked to a cohort)
  4. Create experiment_events table (per-user telemetry for computing metrics)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "d5e6f7a8b9c0"
down_revision: str = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enum types — create via raw SQL, then reference with create_type=False
    #    to prevent SQLAlchemy's _on_table_create from issuing a duplicate CREATE TYPE.
    op.execute("CREATE TYPE experiment_status AS ENUM ('DRAFT', 'RUNNING', 'PAUSED', 'COMPLETED')")
    op.execute(
        "CREATE TYPE experiment_event_type AS ENUM "
        "('IMPRESSION', 'CLICK', 'LIKE', 'COMMENT', 'SHARE', 'SESSION_START', 'SESSION_END')"
    )
    experiment_status = PgEnum(
        "DRAFT", "RUNNING", "PAUSED", "COMPLETED",
        name="experiment_status", create_type=False,
    )
    experiment_event_type = PgEnum(
        "IMPRESSION", "CLICK", "LIKE", "COMMENT", "SHARE",
        "SESSION_START", "SESSION_END",
        name="experiment_event_type", create_type=False,
    )

    # 2. cohorts
    op.create_table(
        "cohorts",
        sa.Column("cohort_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Membership rule spec for UI display (geo, specialty, behavioral rules)
        sa.Column("rules", JSONB, nullable=True),
        # Feed ranking weights: {recency, specialty, affinity, cold_start_threshold, affinity_ceiling}
        sa.Column("feed_algorithm", JSONB, nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_cohorts_name"),
    )
    op.create_index("ix_cohorts_priority", "cohorts", ["priority"])
    op.create_index("ix_cohorts_is_active", "cohorts", ["is_active"])

    # 3. ab_experiments
    op.create_table(
        "ab_experiments",
        sa.Column("experiment_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "cohort_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cohorts.cohort_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            experiment_status,
            nullable=False,
            server_default="DRAFT",
        ),
        # Array of {name, traffic_pct, algorithm_config} — supports 2+ variants.
        # traffic_pct values must sum to 100.
        sa.Column("variants", JSONB, nullable=False),
        sa.Column("start_date", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_date", TIMESTAMP(timezone=True), nullable=True),
        # Computed results per variant; written by results endpoint or background job.
        sa.Column("results", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_ab_experiments_name"),
    )
    op.create_index("ix_ab_experiments_cohort_id", "ab_experiments", ["cohort_id"])
    op.create_index("ix_ab_experiments_status", "ab_experiments", ["status"])

    # 4. experiment_events
    op.create_table(
        "experiment_events",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "experiment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ab_experiments.experiment_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        # Matches one of ABExperiment.variants[].name (e.g. "control", "treatment")
        sa.Column("variant_name", sa.String(100), nullable=False),
        sa.Column("event_type", experiment_event_type, nullable=False),
        sa.Column("post_id", UUID(as_uuid=True), nullable=True),
        sa.Column("session_duration_s", sa.Integer(), nullable=True),
        sa.Column(
            "occurred_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Composite index optimised for results GROUP BY queries
    op.create_index(
        "ix_experiment_events_result_query",
        "experiment_events",
        ["experiment_id", "variant_name", "event_type"],
    )
    op.create_index(
        "ix_experiment_events_occurred_at",
        "experiment_events",
        ["experiment_id", "occurred_at"],
    )
    op.create_index("ix_experiment_events_user_id", "experiment_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_events_user_id", table_name="experiment_events")
    op.drop_index("ix_experiment_events_occurred_at", table_name="experiment_events")
    op.drop_index("ix_experiment_events_result_query", table_name="experiment_events")
    op.drop_table("experiment_events")

    op.drop_index("ix_ab_experiments_status", table_name="ab_experiments")
    op.drop_index("ix_ab_experiments_cohort_id", table_name="ab_experiments")
    op.drop_table("ab_experiments")

    op.drop_index("ix_cohorts_is_active", table_name="cohorts")
    op.drop_index("ix_cohorts_priority", table_name="cohorts")
    op.drop_table("cohorts")

    sa.Enum(name="experiment_event_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="experiment_status").drop(op.get_bind(), checkfirst=True)
