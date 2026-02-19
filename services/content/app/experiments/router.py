"""Experiments router — cohort management, A/B experiments, weight resolution, event ingestion."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_redis
from app.experiments import controller
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
    WeightConfigResponse,
)

router = APIRouter(prefix="/experiments", tags=["Experiments"])


# ===========================================================================
# Cohorts (admin-only in production — gate at API gateway)
# ===========================================================================


@router.post(
    "/cohorts",
    response_model=CohortResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cohort (admin)",
    description=(
        "Define a user segment with custom feed algorithm weights. "
        "Cohort membership is resolved externally (client / API gateway) and passed as "
        "`cohort_ids` query params to feed endpoints. "
        "Returns 409 if name is already taken. "
        "Requires authentication (admin role enforced at API gateway in production)."
    ),
)
async def create_cohort(
    body: CohortCreate,
    created_by: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CohortResponse:
    return await controller.create_cohort(body, created_by, db)


@router.get(
    "/cohorts",
    response_model=list[CohortResponse],
    summary="List all cohorts (admin)",
    description="Returns all cohorts ordered by priority descending. Requires authentication.",
)
async def list_cohorts(
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CohortResponse]:
    return await controller.list_cohorts(db)


@router.get(
    "/cohorts/{cohort_id}",
    response_model=CohortResponse,
    summary="Get a cohort by ID",
    description="Returns the cohort or 404 if not found. Requires authentication.",
)
async def get_cohort(
    cohort_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CohortResponse:
    return await controller.get_cohort(cohort_id, db)


@router.patch(
    "/cohorts/{cohort_id}",
    response_model=CohortResponse,
    summary="Update a cohort (admin)",
    description="Partial update (PATCH semantics). Returns 404 if not found. Requires authentication.",
)
async def update_cohort(
    cohort_id: UUID,
    body: CohortUpdate,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CohortResponse:
    return await controller.update_cohort(cohort_id, body, db)


@router.delete(
    "/cohorts/{cohort_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a cohort (admin)",
    description="Hard delete. Running experiments become cohort-less (FK SET NULL). Requires authentication.",
)
async def delete_cohort(
    cohort_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.delete_cohort(cohort_id, db)


# ===========================================================================
# Experiments (admin-only in production)
# ===========================================================================


@router.post(
    "",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an experiment (admin)",
    description=(
        "Define a multi-variant A/B experiment. "
        "`variants[].traffic_pct` must sum to 100. "
        "Status starts as DRAFT. Call `/start` to activate. "
        "Returns 409 if name is already taken. Requires authentication."
    ),
)
async def create_experiment(
    body: ExperimentCreate,
    created_by: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.create_experiment(body, created_by, db)


@router.get(
    "",
    response_model=list[ExperimentResponse],
    summary="List all experiments (admin)",
    description="Returns all experiments, newest first. Requires authentication.",
)
async def list_experiments(
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExperimentResponse]:
    return await controller.list_experiments(db)


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get an experiment by ID",
    description="Returns the experiment or 404. Requires authentication.",
)
async def get_experiment(
    experiment_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.get_experiment(experiment_id, db)


@router.patch(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Update an experiment (admin)",
    description=(
        "Partial update. Only allowed for DRAFT or PAUSED experiments. "
        "Returns 422 if in RUNNING or COMPLETED state. Requires authentication."
    ),
)
async def update_experiment(
    experiment_id: UUID,
    body: ExperimentUpdate,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.update_experiment(experiment_id, body, db)


@router.post(
    "/{experiment_id}/start",
    response_model=ExperimentResponse,
    summary="Start an experiment (admin)",
    description=(
        "Transitions DRAFT or PAUSED → RUNNING. Sets start_date to now. "
        "If end_date is set, it must be at least 7 days from now (statistical significance). "
        "Returns 422 on invalid transition or duration violation. Requires authentication."
    ),
)
async def start_experiment(
    experiment_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.start_experiment(experiment_id, db)


@router.post(
    "/{experiment_id}/pause",
    response_model=ExperimentResponse,
    summary="Pause a running experiment (admin)",
    description="Transitions RUNNING → PAUSED. Returns 422 if not RUNNING. Requires authentication.",
)
async def pause_experiment(
    experiment_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.pause_experiment(experiment_id, db)


@router.post(
    "/{experiment_id}/complete",
    response_model=ExperimentResponse,
    summary="Complete an experiment (admin)",
    description=(
        "Transitions RUNNING or PAUSED → COMPLETED. "
        "Returns 422 if in DRAFT state. Requires authentication."
    ),
)
async def complete_experiment(
    experiment_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    return await controller.complete_experiment(experiment_id, db)


# ===========================================================================
# Results
# ===========================================================================


@router.get(
    "/{experiment_id}/results",
    response_model=ExperimentResultsResponse,
    summary="Get experiment results with confidence intervals",
    description=(
        "Computes CTR, likes/session, and avg session duration per variant. "
        "Includes 95% Wilson CI for CTR. "
        "`is_significant=true` when treatment CTR CI lower bound > control CTR CI upper bound. "
        "Results are also written back to experiment.results for caching. "
        "Requires authentication."
    ),
)
async def get_results(
    experiment_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResultsResponse:
    return await controller.get_results(experiment_id, db)


# ===========================================================================
# Weight resolution (used by feed + client)
# ===========================================================================


@router.get(
    "/weights",
    response_model=WeightConfigResponse,
    summary="Resolve effective feed weights for the current user",
    description=(
        "Resolves the effective WeightConfig for the calling user based on their cohort membership. "
        "Pass `cohort_ids` (repeated param) as determined by the client/gateway. "
        "Returns the highest-priority cohort's algorithm, overridden by any RUNNING experiment variant "
        "(assignment is deterministic and stateless). "
        "Result is Redis-cached for 60 seconds. "
        "Requires authentication."
    ),
)
async def get_weights(
    cohort_ids: list[UUID] = Query(
        default=[],
        description="Cohort IDs the user belongs to (pass repeatedly: ?cohort_ids=id1&cohort_ids=id2).",
    ),
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> WeightConfigResponse:
    return await controller.get_weights(user_id, cohort_ids, db, redis)


# ===========================================================================
# Event ingestion (client telemetry)
# ===========================================================================


@router.post(
    "/events",
    response_model=ExperimentEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest an experiment telemetry event",
    description=(
        "Record a client-side event (impression, click, like, session start/end) "
        "for an experiment variant. "
        "Events are used to compute per-variant metrics (CTR, likes/session, avg session duration). "
        "Requires authentication."
    ),
)
async def ingest_event(
    body: ExperimentEventIngest,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentEventResponse:
    return await controller.ingest_event(body, user_id, db)
