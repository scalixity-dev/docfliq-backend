"""Pydantic V2 schemas for the experiments domain.

Input schemas:  CohortCreate, CohortUpdate, ExperimentCreate, ExperimentUpdate,
                ExperimentEventIngest, WeightConfigIn
Output schemas: CohortResponse, ExperimentResponse, WeightConfigResponse,
                ExperimentResultsResponse, ExperimentEventResponse
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ExperimentEventType, ExperimentStatus


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------


class VariantSpec(BaseModel):
    """Single variant definition inside an experiment.

    Example:
      {"name": "control",   "traffic_pct": 50, "algorithm_config": {"recency": 0.40, ...}}
      {"name": "treatment", "traffic_pct": 50, "algorithm_config": {"recency": 0.20, ...}}
    """

    name: str = Field(..., min_length=1, max_length=100, description="Variant identifier (e.g. 'control', 'treatment').")
    traffic_pct: int = Field(..., ge=1, le=99, description="Percentage of cohort traffic routed to this variant.")
    algorithm_config: dict[str, Any] = Field(
        ...,
        description=(
            "Feed weight overrides for this variant. "
            "Keys: recency, specialty, affinity, cold_start_threshold, affinity_ceiling."
        ),
    )


class WeightConfigResponse(BaseModel):
    """Resolved feed scoring weights for a user (from cohort/experiment or defaults)."""

    model_config = ConfigDict(from_attributes=True)

    recency: float = Field(0.40, description="Recency decay weight.")
    specialty: float = Field(0.30, description="Specialty tag overlap weight.")
    affinity: float = Field(0.30, description="Author affinity weight.")
    cold_start_threshold: int = Field(10, description="Min interactions before leaving cold-start.")
    affinity_ceiling: float = Field(50.0, description="Raw affinity pts that map to score=1.0.")
    source: str = Field("default", description="Weight source: 'default', 'cohort', or 'experiment:{name}'.")


# ---------------------------------------------------------------------------
# Cohort schemas
# ---------------------------------------------------------------------------


class CohortCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150, description="Unique cohort name.")
    description: str | None = Field(None, description="Admin-facing description.")
    rules: dict[str, Any] | None = Field(
        None,
        description=(
            "Membership rule spec for display (geo, specialty, behavioral). "
            "Actual membership is resolved externally (gateway / client)."
        ),
    )
    feed_algorithm: dict[str, Any] = Field(
        ...,
        description="Feed ranking weights: {recency, specialty, affinity, cold_start_threshold, affinity_ceiling}.",
    )
    priority: int = Field(0, ge=0, le=32767, description="Higher priority wins on cohort overlap.")
    is_active: bool = Field(True, description="Whether this cohort is active.")


class CohortUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    rules: dict[str, Any] | None = None
    feed_algorithm: dict[str, Any] | None = None
    priority: int | None = Field(None, ge=0, le=32767)
    is_active: bool | None = None


class CohortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cohort_id: uuid.UUID
    name: str
    description: str | None
    rules: dict[str, Any] | None
    feed_algorithm: dict[str, Any]
    priority: int
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Experiment schemas
# ---------------------------------------------------------------------------


class ExperimentCreate(BaseModel):
    cohort_id: uuid.UUID | None = Field(None, description="Target cohort (optional).")
    name: str = Field(..., min_length=1, max_length=200, description="Unique experiment name.")
    description: str | None = None
    variants: list[VariantSpec] = Field(
        ...,
        min_length=2,
        description="Experiment variants. traffic_pct values must sum to 100.",
    )
    end_date: datetime | None = Field(None, description="Planned end date (min 7 days after start).")

    @model_validator(mode="after")
    def check_traffic_sum(self) -> "ExperimentCreate":
        total = sum(v.traffic_pct for v in self.variants)
        if total != 100:
            raise ValueError(f"variants[].traffic_pct must sum to 100, got {total}.")
        return self


class ExperimentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    variants: list[VariantSpec] | None = None
    end_date: datetime | None = None

    @model_validator(mode="after")
    def check_traffic_sum(self) -> "ExperimentUpdate":
        if self.variants is not None:
            total = sum(v.traffic_pct for v in self.variants)
            if total != 100:
                raise ValueError(f"variants[].traffic_pct must sum to 100, got {total}.")
        return self


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    experiment_id: uuid.UUID
    cohort_id: uuid.UUID | None
    name: str
    description: str | None
    status: ExperimentStatus
    variants: list[dict[str, Any]]
    start_date: datetime | None
    end_date: datetime | None
    results: dict[str, Any] | None
    created_by: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Results schemas
# ---------------------------------------------------------------------------


class VariantMetrics(BaseModel):
    """Computed metrics for a single variant."""

    impressions: int = Field(0, description="Total impression events.")
    clicks: int = Field(0, description="Total click events.")
    ctr: float = Field(0.0, description="Click-through rate = clicks / impressions.")
    ctr_ci_lower: float = Field(0.0, description="95% Wilson CI lower bound for CTR.")
    ctr_ci_upper: float = Field(0.0, description="95% Wilson CI upper bound for CTR.")
    session_starts: int = Field(0, description="Total session start events.")
    likes: int = Field(0, description="Total like events.")
    likes_per_session: float = Field(0.0, description="likes / session_starts.")
    avg_session_duration_s: float | None = Field(None, description="Mean session duration (seconds).")


class ExperimentResultsResponse(BaseModel):
    """Results for all variants of an experiment with statistical significance."""

    experiment_id: uuid.UUID
    experiment_name: str
    status: ExperimentStatus
    variants: dict[str, VariantMetrics] = Field(
        description="Keyed by variant name (e.g. 'control', 'treatment')."
    )
    is_significant: bool = Field(
        False,
        description=(
            "True when the treatment CTR confidence interval lower bound "
            "is above the control CTR confidence interval upper bound."
        ),
    )
    computed_at: datetime


# ---------------------------------------------------------------------------
# Event ingestion schemas
# ---------------------------------------------------------------------------


class ExperimentEventIngest(BaseModel):
    experiment_id: uuid.UUID
    variant_name: str = Field(..., min_length=1, max_length=100, description="Variant the user is assigned to.")
    event_type: ExperimentEventType
    post_id: uuid.UUID | None = Field(None, description="Relevant post (not required for session events).")
    session_duration_s: int | None = Field(None, ge=0, description="Only for SESSION_END events.")


class ExperimentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    experiment_id: uuid.UUID
    user_id: uuid.UUID
    variant_name: str
    event_type: ExperimentEventType
    post_id: uuid.UUID | None
    session_duration_s: int | None
    occurred_at: datetime
