"""Cohort, ABExperiment ORM models.

Cohorts group users by shared characteristics (geo, specialty, behavioral rules) and
map to custom feed algorithm weights stored in `feed_algorithm` JSONB.

ABExperiments run multi-variant tests within a cohort. The `variants` JSONB field
holds an array of ``{name, traffic_pct, algorithm_config}`` objects — two variants
covers control/treatment; more are supported.

ExperimentEvent captures per-user telemetry sent from clients for computing
per-variant metrics (CTR, session time, likes/session, etc.).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import (
    ExperimentEventType,
    ExperimentStatus,
    experiment_event_type_enum,
    experiment_status_enum,
)
from shared.database.postgres import Base


class Cohort(Base):
    """Admin-defined user segment with custom feed scoring weights.

    `rules` stores the membership rule spec as JSON for display purposes.
    Actual cohort membership is resolved by the API gateway or client and
    passed via the `cohort_ids` query parameter on feed endpoints.

    `feed_algorithm` overrides the default feed scoring weights for this cohort:
      {recency, specialty, affinity, cold_start_threshold, affinity_ceiling}

    Higher `priority` wins when a user belongs to multiple active cohorts.
    """

    __tablename__ = "cohorts"

    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Membership rule spec for UI display (geo, specialty, behavioral rules, etc.)
    # Actual membership resolution is external — client passes cohort_ids to feed.
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Feed ranking weights: {recency, specialty, affinity, cold_start_threshold, affinity_ceiling}
    feed_algorithm: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Higher priority wins on cohort overlap (SMALLINT matches spec)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    experiments: Mapped[list[ABExperiment]] = relationship(
        "ABExperiment", back_populates="cohort", lazy="noload"
    )

    __table_args__ = (
        Index("ix_cohorts_priority", "priority"),
        Index("ix_cohorts_is_active", "is_active"),
    )


class ABExperiment(Base):
    """Multi-variant A/B experiment targeting a cohort.

    Variant assignment is deterministic:
      bucket = SHA-256(user_id + experiment_id) % 100
      Cumulative traffic_pct across variants determines which variant is assigned.

    `variants` JSON schema:
      [
        {"name": "control",   "traffic_pct": 50, "algorithm_config": {...}},
        {"name": "treatment", "traffic_pct": 50, "algorithm_config": {...}}
      ]
    traffic_pct values must sum to 100 (validated at application layer).

    `results` is written back after on-demand or scheduled metric computation:
      {"control": {"ctr": 0.12, "ctr_ci": [0.10, 0.14], ...}, "treatment": {...}, ...}

    Min 7-day duration is enforced at the application layer when `start` is called.
    """

    __tablename__ = "ab_experiments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.cohort_id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        experiment_status_enum, nullable=False, default=ExperimentStatus.DRAFT
    )
    # Array of {name, traffic_pct, algorithm_config} — supports 2+ variants.
    variants: Mapped[list] = mapped_column(JSONB, nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Computed results per variant (written by results endpoint or background job).
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    cohort: Mapped[Cohort | None] = relationship(
        "Cohort", back_populates="experiments", lazy="select"
    )
    events: Mapped[list[ExperimentEvent]] = relationship(
        "ExperimentEvent", back_populates="experiment", lazy="noload"
    )

    __table_args__ = (
        Index("ix_ab_experiments_cohort_id", "cohort_id"),
        Index("ix_ab_experiments_status", "status"),
    )


class ExperimentEvent(Base):
    """Per-user telemetry event for computing experiment metrics.

    Events are sent by the client and ingested via POST /experiments/events.
    `variant_name` matches one of the names in ABExperiment.variants[].name.

    Metrics derived from these events:
      CTR            = clicks / impressions (per variant)
      likes/session  = likes / session_starts (per variant)
      avg_session_s  = mean(session_duration_s WHERE event_type=SESSION_END)
    """

    __tablename__ = "experiment_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ab_experiments.experiment_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Matches one of ABExperiment.variants[].name (e.g. "control", "treatment")
    variant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[ExperimentEventType] = mapped_column(
        experiment_event_type_enum, nullable=False
    )
    # Nullable: not all events are associated with a post (e.g. SESSION_START/END).
    post_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Populated on SESSION_END — seconds the user spent in the feed.
    session_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    experiment: Mapped[ABExperiment] = relationship(
        "ABExperiment", back_populates="events", lazy="select"
    )

    __table_args__ = (
        # Optimised for results queries (GROUP BY experiment_id, variant_name, event_type)
        Index(
            "ix_experiment_events_result_query",
            "experiment_id",
            "variant_name",
            "event_type",
        ),
        Index("ix_experiment_events_occurred_at", "experiment_id", "occurred_at"),
        Index("ix_experiment_events_user_id", "user_id"),
    )
