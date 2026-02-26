"""Surveys router — HTTP layer for survey CRUD, responses, and results.

Delegates to controller for business logic orchestration.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.surveys import controller
from app.surveys.schemas import (
    CreateSurveyRequest,
    SubmitSurveyResponseRequest,
    SurveyResponseSchema,
    SurveySubmissionResponse,
    UpdateSurveyRequest,
)

router = APIRouter(prefix="/surveys", tags=["Surveys"])


@router.post(
    "/courses/{course_id}",
    response_model=SurveyResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a survey for a course",
    description="Instructor creates a survey attached to a course. "
    "Can be inline (attached to a lesson), end-of-module, or end-of-course.",
)
async def create_survey(
    course_id: UUID,
    body: CreateSurveyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> SurveyResponseSchema:
    return await controller.create_survey(db, course_id, user_id, body)


@router.get(
    "/{survey_id}",
    response_model=SurveyResponseSchema,
    summary="Get survey by ID",
)
async def get_survey(
    survey_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SurveyResponseSchema:
    return await controller.get_survey(db, survey_id)


@router.get(
    "/courses/{course_id}",
    response_model=list[SurveyResponseSchema],
    summary="List all surveys for a course",
)
async def list_surveys(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SurveyResponseSchema]:
    return await controller.list_surveys(db, course_id)


@router.patch(
    "/{survey_id}",
    response_model=SurveyResponseSchema,
    summary="Update a survey",
)
async def update_survey(
    survey_id: UUID,
    body: UpdateSurveyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> SurveyResponseSchema:
    return await controller.update_survey(db, survey_id, user_id, body)


@router.delete(
    "/{survey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a survey",
)
async def delete_survey(
    survey_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> None:
    await controller.delete_survey(db, survey_id, user_id)


@router.post(
    "/{survey_id}/respond",
    response_model=SurveySubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit survey response",
    description="Student submits answers for a survey. One response per enrollment.",
)
async def submit_response(
    survey_id: UUID,
    body: SubmitSurveyResponseRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> SurveySubmissionResponse:
    return await controller.submit_response(db, survey_id, user_id, body)


@router.get(
    "/{survey_id}/results",
    summary="Get aggregated survey results (instructor only)",
    description="Returns aggregated response data per question: "
    "averages for rating/likert, distribution for MCQ, sample answers for free text.",
)
async def get_survey_results(
    survey_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> dict:
    return await controller.get_survey_results(db, survey_id, user_id)
