"""Surveys controller — maps service results to HTTP responses."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    CourseNotFoundError,
    LessonNotFoundError,
    NotCourseOwnerError,
    NotEnrolledError,
    SurveyAlreadyRespondedError,
    SurveyNotFoundError,
)
from app.surveys import service
from app.surveys.schemas import (
    CreateSurveyRequest,
    SubmitSurveyResponseRequest,
    SurveyResponseSchema,
    SurveySubmissionResponse,
    UpdateSurveyRequest,
)


def _handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (SurveyNotFoundError, CourseNotFoundError, LessonNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NotCourseOwnerError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the course instructor.")
    if isinstance(exc, NotEnrolledError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course.")
    if isinstance(exc, SurveyAlreadyRespondedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Survey already submitted.")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error.")


async def create_survey(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    body: CreateSurveyRequest,
) -> SurveyResponseSchema:
    try:
        survey = await service.create_survey(
            db, course_id, instructor_id, **body.model_dump(),
        )
        return SurveyResponseSchema.model_validate(survey)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_survey(
    db: AsyncSession,
    survey_id: UUID,
) -> SurveyResponseSchema:
    try:
        survey = await service.get_survey(db, survey_id)
        return SurveyResponseSchema.model_validate(survey)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def list_surveys(
    db: AsyncSession,
    course_id: UUID,
) -> list[SurveyResponseSchema]:
    try:
        surveys = await service.list_surveys_for_course(db, course_id)
        return [SurveyResponseSchema.model_validate(s) for s in surveys]
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def update_survey(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
    body: UpdateSurveyRequest,
) -> SurveyResponseSchema:
    try:
        survey = await service.update_survey(
            db, survey_id, instructor_id,
            **body.model_dump(exclude_unset=True),
        )
        return SurveyResponseSchema.model_validate(survey)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def delete_survey(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
) -> None:
    try:
        await service.delete_survey(db, survey_id, instructor_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def submit_response(
    db: AsyncSession,
    survey_id: UUID,
    user_id: UUID,
    body: SubmitSurveyResponseRequest,
) -> SurveySubmissionResponse:
    try:
        response = await service.submit_survey_response(
            db, survey_id, user_id, answers=body.answers,
        )
        return SurveySubmissionResponse(
            response_id=response.response_id,
            survey_id=response.survey_id,
            submitted_at=response.submitted_at,
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_survey_results(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
) -> dict:
    try:
        return await service.get_survey_results(db, survey_id, instructor_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc
