"""Survey domain Pydantic V2 schemas.

Covers Survey CRUD, survey question types (rating, text, likert, MCQ),
and survey response submission.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SurveyPlacement


# ---------------------------------------------------------------------------
# Survey question schema
# ---------------------------------------------------------------------------


class SurveyQuestionSchema(BaseModel):
    """A single question within a survey."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: str = Field(description="Unique ID within the survey (client-generated).")
    question_type: str = Field(
        description="RATING, LIKERT, FREE_TEXT, or MCQ.",
    )
    question_text: str = Field(min_length=1)
    options: list[str] | None = Field(
        default=None,
        description="Answer choices for MCQ/LIKERT. Not used for RATING/FREE_TEXT.",
    )
    required: bool = False
    scale_min: int | None = Field(default=None, ge=1, description="Min value for RATING scale.")
    scale_max: int | None = Field(default=None, le=10, description="Max value for RATING scale.")
    scale_labels: dict[str, str] | None = Field(
        default=None,
        description="Labels for scale points, e.g. {'1': 'Strongly Disagree', '5': 'Strongly Agree'}.",
    )


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateSurveyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    placement: SurveyPlacement
    is_required: bool = False
    questions: list[SurveyQuestionSchema] = Field(min_length=1)
    module_id: UUID | None = Field(
        default=None,
        description="Required for END_OF_MODULE placement.",
    )
    sort_order: int = Field(default=0, ge=0)


class UpdateSurveyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    is_required: bool | None = None
    questions: list[SurveyQuestionSchema] | None = Field(default=None, min_length=1)
    sort_order: int | None = Field(default=None, ge=0)


class SubmitSurveyResponseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    answers: list[dict] = Field(
        description="Array of {question_id, answer_value}.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SurveyResponseSchema(BaseModel):
    """Survey detail."""

    model_config = ConfigDict(from_attributes=True)

    survey_id: UUID
    lesson_id: UUID | None = None
    course_id: UUID
    module_id: UUID | None = None
    title: str
    placement: SurveyPlacement
    is_required: bool
    questions: list[dict]
    sort_order: int
    created_at: datetime
    updated_at: datetime


class SurveySubmissionResponse(BaseModel):
    response_id: UUID
    survey_id: UUID
    submitted_at: datetime
