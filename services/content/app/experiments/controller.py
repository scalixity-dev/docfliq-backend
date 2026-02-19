"""Experiments controller — converts service results to Pydantic responses,
catches domain exceptions and maps them to HTTPExceptions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.experiments import service
from app.experiments.exceptions import (
    CohortNotFound,
    ExperimentDurationError,
    ExperimentNotFound,
    ExperimentTransitionError,
    VariantTrafficError,
)
from app.experiments.schemas import (
    CohortCreate,
    CohortResponse,
    CohortUpdate,
    ExperimentCreate,
    ExperimentEventIngest,
    ExperimentEventResponse,
    ExperimentResponse,
    ExperimentResultsResponse,
    ExperimentUpdate,
    VariantMetrics,
    WeightConfigResponse,
)


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------


async def create_cohort(body: CohortCreate, created_by: UUID, db: AsyncSession) -> CohortResponse:
    try:
        cohort = await service.create_cohort(
            name=body.name,
            feed_algorithm=body.feed_algorithm,
            created_by=created_by,
            db=db,
            description=body.description,
            rules=body.rules,
            priority=body.priority,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CohortResponse.model_validate(cohort)


async def list_cohorts(db: AsyncSession) -> list[CohortResponse]:
    cohorts = await service.list_cohorts(db)
    return [CohortResponse.model_validate(c) for c in cohorts]


async def get_cohort(cohort_id: UUID, db: AsyncSession) -> CohortResponse:
    try:
        cohort = await service.get_cohort(cohort_id, db)
    except CohortNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CohortResponse.model_validate(cohort)


async def update_cohort(cohort_id: UUID, body: CohortUpdate, db: AsyncSession) -> CohortResponse:
    updates = body.model_dump(exclude_none=True)
    try:
        cohort = await service.update_cohort(cohort_id, updates, db)
    except CohortNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CohortResponse.model_validate(cohort)


async def delete_cohort(cohort_id: UUID, db: AsyncSession) -> None:
    try:
        await service.delete_cohort(cohort_id, db)
    except CohortNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


async def create_experiment(
    body: ExperimentCreate, created_by: UUID, db: AsyncSession
) -> ExperimentResponse:
    try:
        experiment = await service.create_experiment(
            name=body.name,
            variants=[v.model_dump() for v in body.variants],
            created_by=created_by,
            db=db,
            cohort_id=body.cohort_id,
            description=body.description,
            end_date=body.end_date,
        )
    except (ValueError, VariantTrafficError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


async def list_experiments(db: AsyncSession) -> list[ExperimentResponse]:
    experiments = await service.list_experiments(db)
    return [ExperimentResponse.model_validate(e) for e in experiments]


async def get_experiment(experiment_id: UUID, db: AsyncSession) -> ExperimentResponse:
    try:
        experiment = await service.get_experiment(experiment_id, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


async def update_experiment(
    experiment_id: UUID, body: ExperimentUpdate, db: AsyncSession
) -> ExperimentResponse:
    updates = body.model_dump(exclude_none=True)
    # Re-serialize variants as plain dicts if present
    if "variants" in updates:
        updates["variants"] = [v.model_dump() if hasattr(v, "model_dump") else v for v in updates["variants"]]
    try:
        experiment = await service.update_experiment(experiment_id, updates, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (ExperimentTransitionError, VariantTrafficError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


async def start_experiment(experiment_id: UUID, db: AsyncSession) -> ExperimentResponse:
    try:
        experiment = await service.start_experiment(experiment_id, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ExperimentTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ExperimentDurationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


async def pause_experiment(experiment_id: UUID, db: AsyncSession) -> ExperimentResponse:
    try:
        experiment = await service.pause_experiment(experiment_id, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ExperimentTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


async def complete_experiment(experiment_id: UUID, db: AsyncSession) -> ExperimentResponse:
    try:
        experiment = await service.complete_experiment(experiment_id, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ExperimentTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ExperimentResponse.model_validate(experiment)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


async def get_results(experiment_id: UUID, db: AsyncSession) -> ExperimentResultsResponse:
    try:
        experiment = await service.get_experiment(experiment_id, db)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    result_data = await service.compute_results(experiment_id, db)

    variants_metrics = {
        name: VariantMetrics(**m) for name, m in result_data["variants"].items()
    }
    return ExperimentResultsResponse(
        experiment_id=experiment.experiment_id,
        experiment_name=experiment.name,
        status=experiment.status,
        variants=variants_metrics,
        is_significant=result_data["is_significant"],
        computed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Weight resolution
# ---------------------------------------------------------------------------


async def get_weights(
    user_id: UUID,
    cohort_ids: list[UUID],
    db: AsyncSession,
    redis: Redis,
) -> WeightConfigResponse:
    config, source = await service.get_effective_weights(user_id, cohort_ids, db, redis)
    return WeightConfigResponse(
        recency=config.recency,
        specialty=config.specialty,
        affinity=config.affinity,
        cold_start_threshold=config.cold_start_threshold,
        affinity_ceiling=config.affinity_ceiling,
        source=source,
    )


# ---------------------------------------------------------------------------
# Event ingestion
# ---------------------------------------------------------------------------


async def ingest_event(
    body: ExperimentEventIngest,
    user_id: UUID,
    db: AsyncSession,
) -> ExperimentEventResponse:
    try:
        event = await service.ingest_event(
            experiment_id=body.experiment_id,
            user_id=user_id,
            variant_name=body.variant_name,
            event_type=body.event_type,
            db=db,
            post_id=body.post_id,
            session_duration_s=body.session_duration_s,
        )
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ExperimentEventResponse.model_validate(event)
