"""Assessment domain Pydantic V2 schemas.

Covers Quiz CRUD, quiz attempt submission, and quiz review.
Supports MCQ (single answer) and MSQ (multiple answers).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import QuestionType, ShowAnswersPolicy


# ---------------------------------------------------------------------------
# Sub-objects
# ---------------------------------------------------------------------------


class QuestionOption(BaseModel):
    """Single option within a question. Supports rich text + images."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, description="Plain text option.")
    html: str | None = Field(default=None, description="Rich text HTML version.")
    image_url: str | None = Field(default=None, max_length=500)


class QuizQuestion(BaseModel):
    """Question supporting MCQ (single answer) and MSQ (multiple answers)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question_type: QuestionType = Field(
        default=QuestionType.MCQ,
        description="MCQ (single correct) or MSQ (multiple correct).",
    )
    question: str = Field(min_length=1, description="Plain text question.")
    question_html: str | None = Field(
        default=None, description="Rich text HTML version of the question.",
    )
    image_url: str | None = Field(
        default=None, max_length=500, description="Question image URL.",
    )
    options: list[QuestionOption] = Field(
        min_length=2, max_length=10, description="Answer choices (2-10).",
    )
    correct_index: int | None = Field(
        default=None, ge=0, description="0-based index of the correct option (MCQ).",
    )
    correct_indices: list[int] | None = Field(
        default=None, description="0-based indices of correct options (MSQ).",
    )
    explanation: str | None = Field(
        default=None, description="Explanation shown after answering.",
    )

    @model_validator(mode="after")
    def _validate_correct_answer(self) -> QuizQuestion:
        if self.question_type == QuestionType.MCQ:
            if self.correct_index is None:
                raise ValueError("MCQ requires correct_index.")
            if self.correct_index >= len(self.options):
                raise ValueError("correct_index out of range.")
        elif self.question_type == QuestionType.MSQ:
            if not self.correct_indices:
                raise ValueError("MSQ requires correct_indices.")
            if any(i >= len(self.options) for i in self.correct_indices):
                raise ValueError("correct_indices contain out-of-range index.")
        return self


# ---------------------------------------------------------------------------
# Quiz request schemas
# ---------------------------------------------------------------------------


class CreateQuizRequest(BaseModel):
    """Request body for creating a quiz attached to a lesson."""

    model_config = ConfigDict(str_strip_whitespace=True)

    questions: list[QuizQuestion] = Field(
        min_length=1, description="Array of MCQ/MSQ questions.",
    )
    passing_score: int = Field(
        default=70, ge=0, le=100, description="Minimum percentage to pass.",
    )
    max_attempts: int | None = Field(
        default=None, ge=1, description="Max retry attempts. Null = unlimited.",
    )
    time_limit_secs: int | None = Field(
        default=None,
        ge=30,
        description="Time limit per attempt in seconds. Null = untimed.",
    )
    randomize_order: bool = Field(
        default=False, description="Randomize question order for each attempt.",
    )
    show_answers: ShowAnswersPolicy = Field(
        default=ShowAnswersPolicy.NEVER,
        description="When to reveal correct answers: NEVER, AFTER_SUBMIT, AFTER_PASS.",
    )


class UpdateQuizRequest(BaseModel):
    """PATCH body for updating a quiz."""

    model_config = ConfigDict(str_strip_whitespace=True)

    questions: list[QuizQuestion] | None = Field(default=None, min_length=1)
    passing_score: int | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=1)
    time_limit_secs: int | None = Field(default=None, ge=30)
    randomize_order: bool | None = Field(default=None)
    show_answers: ShowAnswersPolicy | None = Field(default=None)


# ---------------------------------------------------------------------------
# Quiz attempt schemas
# ---------------------------------------------------------------------------


class QuizAttemptRequest(BaseModel):
    """Request body for submitting a quiz attempt.

    ``answers`` is a list matching question order. For MCQ: a single int.
    For MSQ: a list of ints.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    answers: list[int | list[int]] = Field(
        description="Per question: int for MCQ, list[int] for MSQ.",
    )
    time_taken_secs: int | None = Field(
        default=None, ge=0, description="Client-reported time taken in seconds.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class QuizResponse(BaseModel):
    """Quiz representation (questions included for instructor view)."""

    model_config = ConfigDict(from_attributes=True)

    quiz_id: UUID
    lesson_id: UUID
    questions: list[dict] = Field(description="Array of question objects.")
    passing_score: int
    max_attempts: int | None
    time_limit_secs: int | None
    randomize_order: bool
    show_answers: ShowAnswersPolicy
    created_at: datetime


class QuizStudentResponse(BaseModel):
    """Quiz as seen by a student (correct answers stripped).

    Returned by the ``/start`` endpoint.
    """

    quiz_id: UUID
    lesson_id: UUID
    questions: list[dict] = Field(
        description="Questions with options but without correct_index or explanation.",
    )
    passing_score: int
    max_attempts: int | None
    time_limit_secs: int | None
    show_answers: ShowAnswersPolicy


class QuizAttemptResponse(BaseModel):
    """Result of a quiz submission."""

    quiz_id: UUID
    score: int = Field(description="Score as a percentage (0-100).")
    passed: bool = Field(description="Whether the score meets passing_score.")
    correct_count: int
    total_questions: int
    attempt_number: int = Field(description="Which attempt this was (1-based).")
    time_taken_secs: int | None = None
    answers_review: list[dict] | None = Field(
        default=None,
        description="Present only if show_answers policy permits. "
        "Contains correct answers and explanations per question.",
    )
