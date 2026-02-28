"""Experiments service — pure business logic, no FastAPI imports.

Key responsibilities:
- Cohort CRUD
- ABExperiment CRUD + lifecycle transitions (start / pause / complete)
- Deterministic variant assignment (SHA-256 hash, no DB storage)
- Weight resolution: cohort feed_algorithm → WeightConfig (Redis-cached, TTL=60s)
- Results computation: Wilson CI for CTR, normal approximation for continuous metrics
- Event ingestion
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.experiments.exceptions import (
    CohortNotFound,
    ExperimentDurationError,
    ExperimentNotFound,
    ExperimentTransitionError,
    VariantTrafficError,
)
from app.feed.scoring import DEFAULT_WEIGHT_CONFIG, WeightConfig
from app.models.cohort import ABExperiment, Cohort, ExperimentEvent
from app.models.enums import ExperimentEventType, ExperimentStatus
from redis.asyncio import Redis

# Minimum experiment duration before it can be started with an end_date set.
_MIN_DURATION_DAYS: int = 7

# Redis cache key pattern for resolved weight config (TTL 60s).
_WEIGHTS_CACHE_TTL: int = 60
_WEIGHTS_CACHE_KEY = "experiments:weights:{user_id}:{cohort_hash}"

# Valid transitions for start/pause/complete
_START_FROM = {ExperimentStatus.DRAFT, ExperimentStatus.PAUSED}
_PAUSE_FROM = {ExperimentStatus.RUNNING}
_COMPLETE_FROM = {ExperimentStatus.RUNNING, ExperimentStatus.PAUSED}


# ===========================================================================
# Cohort CRUD
# ===========================================================================


async def create_cohort(
    name: str,
    feed_algorithm: dict,
    created_by: UUID,
    db: AsyncSession,
    description: str | None = None,
    rules: dict | None = None,
    priority: int = 0,
    is_active: bool = True,
) -> Cohort:
    cohort = Cohort(
        name=name,
        description=description,
        rules=rules,
        feed_algorithm=feed_algorithm,
        priority=priority,
        is_active=is_active,
        created_by=created_by,
    )
    db.add(cohort)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"Cohort with name '{name}' already exists.")
    await db.refresh(cohort)
    return cohort


async def list_cohorts(db: AsyncSession) -> list[Cohort]:
    result = await db.execute(select(Cohort).order_by(Cohort.priority.desc(), Cohort.created_at.asc()))
    return list(result.scalars().all())


async def get_cohort(cohort_id: UUID, db: AsyncSession) -> Cohort:
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise CohortNotFound(cohort_id)
    return cohort


async def update_cohort(cohort_id: UUID, updates: dict, db: AsyncSession) -> Cohort:
    cohort = await get_cohort(cohort_id, db)
    for key, value in updates.items():
        if value is not None:
            setattr(cohort, key, value)
    await db.flush()
    await db.refresh(cohort)
    return cohort


async def delete_cohort(cohort_id: UUID, db: AsyncSession) -> None:
    cohort = await get_cohort(cohort_id, db)
    await db.delete(cohort)
    await db.flush()


# ===========================================================================
# ABExperiment CRUD
# ===========================================================================


def _validate_variants(variants: list[dict]) -> None:
    total = sum(v.get("traffic_pct", 0) for v in variants)
    if total != 100:
        raise VariantTrafficError(f"variants[].traffic_pct must sum to 100, got {total}.")


async def create_experiment(
    name: str,
    variants: list[dict],
    created_by: UUID,
    db: AsyncSession,
    cohort_id: UUID | None = None,
    description: str | None = None,
    end_date: datetime | None = None,
) -> ABExperiment:
    _validate_variants(variants)
    experiment = ABExperiment(
        cohort_id=cohort_id,
        name=name,
        description=description,
        status=ExperimentStatus.DRAFT,
        variants=variants,
        end_date=end_date,
        created_by=created_by,
    )
    db.add(experiment)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"Experiment with name '{name}' already exists.")
    await db.refresh(experiment)
    return experiment


async def list_experiments(db: AsyncSession) -> list[ABExperiment]:
    result = await db.execute(select(ABExperiment).order_by(ABExperiment.created_at.desc()))
    return list(result.scalars().all())


async def get_experiment(experiment_id: UUID, db: AsyncSession) -> ABExperiment:
    experiment = await db.get(ABExperiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFound(experiment_id)
    return experiment


async def update_experiment(experiment_id: UUID, updates: dict, db: AsyncSession) -> ABExperiment:
    experiment = await get_experiment(experiment_id, db)
    if experiment.status not in (ExperimentStatus.DRAFT, ExperimentStatus.PAUSED):
        raise ExperimentTransitionError("Only DRAFT or PAUSED experiments can be updated.")
    if "variants" in updates and updates["variants"] is not None:
        _validate_variants(updates["variants"])
    for key, value in updates.items():
        if value is not None:
            setattr(experiment, key, value)
    await db.flush()
    await db.refresh(experiment)
    return experiment


# ===========================================================================
# Experiment lifecycle
# ===========================================================================


async def start_experiment(experiment_id: UUID, db: AsyncSession) -> ABExperiment:
    experiment = await get_experiment(experiment_id, db)
    if experiment.status not in _START_FROM:
        raise ExperimentTransitionError(
            f"Cannot start experiment in status '{experiment.status.value}'. "
            "Allowed: DRAFT, PAUSED."
        )
    now = datetime.now(timezone.utc)
    if experiment.end_date is not None:
        end = experiment.end_date
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end < now + timedelta(days=_MIN_DURATION_DAYS):
            raise ExperimentDurationError(
                f"end_date must be at least {_MIN_DURATION_DAYS} days from now."
            )
    experiment.status = ExperimentStatus.RUNNING
    experiment.start_date = now
    await db.flush()
    await db.refresh(experiment)
    return experiment


async def pause_experiment(experiment_id: UUID, db: AsyncSession) -> ABExperiment:
    experiment = await get_experiment(experiment_id, db)
    if experiment.status not in _PAUSE_FROM:
        raise ExperimentTransitionError(
            f"Cannot pause experiment in status '{experiment.status.value}'. Allowed: RUNNING."
        )
    experiment.status = ExperimentStatus.PAUSED
    await db.flush()
    await db.refresh(experiment)
    return experiment


async def complete_experiment(experiment_id: UUID, db: AsyncSession) -> ABExperiment:
    experiment = await get_experiment(experiment_id, db)
    if experiment.status not in _COMPLETE_FROM:
        raise ExperimentTransitionError(
            f"Cannot complete experiment in status '{experiment.status.value}'. "
            "Allowed: RUNNING, PAUSED."
        )
    experiment.status = ExperimentStatus.COMPLETED
    await db.flush()
    await db.refresh(experiment)
    return experiment


# ===========================================================================
# Variant assignment (deterministic, no DB storage)
# ===========================================================================


def assign_variant(user_id: UUID, experiment: ABExperiment) -> str:
    """Deterministically assign a variant name using SHA-256.

    bucket = int(SHA-256(f"{user_id}:{experiment_id}").hexdigest(), 16) % 100
    Cumulative traffic_pct across variants determines the assigned variant.
    """
    key = f"{user_id}:{experiment.experiment_id}"
    bucket = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100
    cumulative = 0
    for variant in experiment.variants:
        cumulative += variant["traffic_pct"]
        if bucket < cumulative:
            return variant["name"]
    # Fallback (should not reach here if traffic_pct sums to 100)
    return experiment.variants[-1]["name"]


# ===========================================================================
# Weight resolution
# ===========================================================================


def _weights_from_algorithm_config(config_dict: dict, source: str) -> WeightConfig:
    """Build a WeightConfig from a stored algorithm_config dict."""
    return WeightConfig(
        recency=float(config_dict.get("recency", DEFAULT_WEIGHT_CONFIG.recency)),
        specialty=float(config_dict.get("specialty", DEFAULT_WEIGHT_CONFIG.specialty)),
        affinity=float(config_dict.get("affinity", DEFAULT_WEIGHT_CONFIG.affinity)),
        cold_start_threshold=int(
            config_dict.get("cold_start_threshold", DEFAULT_WEIGHT_CONFIG.cold_start_threshold)
        ),
        affinity_ceiling=float(
            config_dict.get("affinity_ceiling", DEFAULT_WEIGHT_CONFIG.affinity_ceiling)
        ),
    ), source


async def get_effective_weights(
    user_id: UUID,
    cohort_ids: list[UUID],
    db: AsyncSession,
    redis: Redis,
) -> tuple[WeightConfig, str]:
    """Resolve the effective WeightConfig for a user.

    Resolution order:
    1. Empty cohort_ids → DEFAULT_WEIGHT_CONFIG ("default")
    2. Check Redis cache (TTL=60s)
    3. Highest-priority active cohort → check for RUNNING experiment
       a. Assign variant → return experiment variant's algorithm_config ("experiment:{name}")
       b. No running experiment → return cohort's feed_algorithm ("cohort")
    4. Write result to Redis cache and return

    Returns (WeightConfig, source_label).
    """
    if not cohort_ids:
        return DEFAULT_WEIGHT_CONFIG, "default"

    cohort_hash = hashlib.sha256(
        json.dumps(sorted(str(c) for c in cohort_ids)).encode()
    ).hexdigest()[:16]
    cache_key = _WEIGHTS_CACHE_KEY.format(user_id=user_id, cohort_hash=cohort_hash)

    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return (
            WeightConfig(
                recency=data["recency"],
                specialty=data["specialty"],
                affinity=data["affinity"],
                cold_start_threshold=data["cold_start_threshold"],
                affinity_ceiling=data["affinity_ceiling"],
            ),
            data["source"],
        )

    # Fetch highest-priority active cohort
    q = (
        select(Cohort)
        .where(
            Cohort.cohort_id.in_(cohort_ids),
            Cohort.is_active.is_(True),
        )
        .order_by(Cohort.priority.desc())
        .limit(1)
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        return DEFAULT_WEIGHT_CONFIG, "default"

    cohort: Cohort = row

    # Check for a RUNNING experiment on this cohort
    now = datetime.now(timezone.utc)
    exp_q = select(ABExperiment).where(
        ABExperiment.cohort_id == cohort.cohort_id,
        ABExperiment.status == ExperimentStatus.RUNNING,
        and_(
            ABExperiment.start_date.isnot(None),
            ABExperiment.start_date <= now,
        ),
    )
    experiment = (await db.execute(exp_q)).scalar_one_or_none()

    if experiment is not None:
        variant_name = assign_variant(user_id, experiment)
        variant_config = next(
            (v["algorithm_config"] for v in experiment.variants if v["name"] == variant_name),
            {},
        )
        config, source = _weights_from_algorithm_config(
            variant_config, f"experiment:{experiment.name}:{variant_name}"
        )
    else:
        config, source = _weights_from_algorithm_config(
            cohort.feed_algorithm, "cohort"
        )

    # Cache the result
    payload = json.dumps({
        "recency": config.recency,
        "specialty": config.specialty,
        "affinity": config.affinity,
        "cold_start_threshold": config.cold_start_threshold,
        "affinity_ceiling": config.affinity_ceiling,
        "source": source,
    })
    await redis.setex(cache_key, _WEIGHTS_CACHE_TTL, payload)
    return config, source


# ===========================================================================
# Event ingestion
# ===========================================================================


async def ingest_event(
    experiment_id: UUID,
    user_id: UUID,
    variant_name: str,
    event_type: ExperimentEventType,
    db: AsyncSession,
    post_id: UUID | None = None,
    session_duration_s: int | None = None,
) -> ExperimentEvent:
    # Validate experiment exists
    await get_experiment(experiment_id, db)
    event = ExperimentEvent(
        experiment_id=experiment_id,
        user_id=user_id,
        variant_name=variant_name,
        event_type=event_type,
        post_id=post_id,
        session_duration_s=session_duration_s,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


# ===========================================================================
# Results computation (Wilson CI for CTR)
# ===========================================================================


def _wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if trials == 0:
        return 0.0, 0.0
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    margin = (z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


async def compute_results(experiment_id: UUID, db: AsyncSession) -> dict:
    """Aggregate experiment_events by variant_name + event_type and compute metrics.

    Returns a dict keyed by variant_name, each with VariantMetrics-compatible fields.
    Writes the computed results back to ABExperiment.results.
    """
    experiment = await get_experiment(experiment_id, db)

    # GROUP BY variant_name, event_type
    agg_q = (
        select(
            ExperimentEvent.variant_name,
            ExperimentEvent.event_type,
            func.count(ExperimentEvent.event_id).label("cnt"),
            func.avg(ExperimentEvent.session_duration_s).label("avg_dur"),
        )
        .where(ExperimentEvent.experiment_id == experiment_id)
        .group_by(ExperimentEvent.variant_name, ExperimentEvent.event_type)
    )
    rows = (await db.execute(agg_q)).all()

    # Collect raw counts per variant
    counts: dict[str, dict[str, int | float]] = {}
    for row in rows:
        v = row.variant_name
        if v not in counts:
            counts[v] = {
                "impressions": 0,
                "clicks": 0,
                "likes": 0,
                "session_starts": 0,
                "avg_session_duration_s": None,
            }
        et = row.event_type
        if et == ExperimentEventType.IMPRESSION:
            counts[v]["impressions"] = row.cnt
        elif et == ExperimentEventType.CLICK:
            counts[v]["clicks"] = row.cnt
        elif et == ExperimentEventType.LIKE:
            counts[v]["likes"] = row.cnt
        elif et == ExperimentEventType.SESSION_START:
            counts[v]["session_starts"] = row.cnt
        elif et == ExperimentEventType.SESSION_END and row.avg_dur is not None:
            counts[v]["avg_session_duration_s"] = float(row.avg_dur)

    # Compute metrics per variant
    metrics: dict[str, dict] = {}
    for variant_name, c in counts.items():
        impressions = int(c["impressions"])
        clicks = int(c["clicks"])
        likes = int(c["likes"])
        session_starts = int(c["session_starts"])
        ctr = clicks / impressions if impressions > 0 else 0.0
        ci_lo, ci_hi = _wilson_ci(clicks, impressions)
        metrics[variant_name] = {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(ctr, 6),
            "ctr_ci_lower": round(ci_lo, 6),
            "ctr_ci_upper": round(ci_hi, 6),
            "session_starts": session_starts,
            "likes": likes,
            "likes_per_session": round(likes / session_starts, 6) if session_starts > 0 else 0.0,
            "avg_session_duration_s": c.get("avg_session_duration_s"),
        }

    # Statistical significance: treatment CI lower > control CI upper
    is_significant = False
    if "control" in metrics and "treatment" in metrics:
        ctrl = metrics["control"]
        treat = metrics["treatment"]
        is_significant = treat["ctr_ci_lower"] > ctrl["ctr_ci_upper"]

    result_payload = {
        "variants": metrics,
        "is_significant": is_significant,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Persist back to experiment.results
    experiment.results = result_payload
    await db.flush()
    await db.refresh(experiment)
    return result_payload
