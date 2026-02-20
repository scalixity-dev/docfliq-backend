"""Assessment controller — maps service results to HTTP responses."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service
from app.assessment.schemas import (
    CreateQuizRequest,
    QuizAttemptRequest,
    QuizAttemptResponse,
    QuizResponse,
    QuizStudentResponse,
    UpdateQuizRequest,
)
from app.exceptions import (
    LessonNotFoundError,
    MaxAttemptsReachedError,
    NotCourseOwnerError,
    NotEnrolledError,
    QuizAlreadyExistsError,
    QuizNotFoundError,
    QuizTimeLimitExceededError,
)


def _handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (QuizNotFoundError, LessonNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NotCourseOwnerError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the course instructor.")
    if isinstance(exc, QuizAlreadyExistsError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quiz already exists for this lesson.")
    if isinstance(exc, NotEnrolledError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course.")
    if isinstance(exc, MaxAttemptsReachedError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum quiz attempts reached.")
    if isinstance(exc, QuizTimeLimitExceededError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz time limit exceeded.")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error.")


async def create_quiz(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
    body: CreateQuizRequest,
) -> QuizResponse:
    try:
        questions = [q.model_dump() for q in body.questions]
        quiz = await service.create_quiz(
            db, lesson_id, instructor_id,
            questions=questions,
            passing_score=body.passing_score,
            max_attempts=body.max_attempts,
            time_limit_secs=body.time_limit_secs,
            randomize_order=body.randomize_order,
            show_answers=body.show_answers,
        )
        return QuizResponse.model_validate(quiz)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_quiz_for_student(
    db: AsyncSession,
    lesson_id: UUID,
) -> QuizStudentResponse:
    """Return quiz without correct answers (student view)."""
    try:
        quiz = await service.get_quiz_for_lesson(db, lesson_id)
        questions = quiz.questions if isinstance(quiz.questions, list) else []
        stripped = []
        for q in questions:
            student_q = {
                "question": q.get("question", ""),
                "question_type": q.get("question_type", "MCQ"),
                "question_html": q.get("question_html"),
                "image_url": q.get("image_url"),
                "options": q.get("options", []),
            }
            stripped.append(student_q)
        return QuizStudentResponse(
            quiz_id=quiz.quiz_id,
            lesson_id=quiz.lesson_id,
            questions=stripped,
            passing_score=quiz.passing_score,
            max_attempts=quiz.max_attempts,
            time_limit_secs=quiz.time_limit_secs,
            show_answers=quiz.show_answers,
        )
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_quiz_instructor(
    db: AsyncSession,
    quiz_id: UUID,
) -> QuizResponse:
    """Return quiz with correct answers (instructor view)."""
    try:
        quiz = await service.get_quiz_by_id(db, quiz_id)
        return QuizResponse.model_validate(quiz)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def update_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    instructor_id: UUID,
    body: UpdateQuizRequest,
) -> QuizResponse:
    try:
        fields = body.model_dump(exclude_unset=True)
        if "questions" in fields and fields["questions"] is not None:
            fields["questions"] = [
                q.model_dump() if hasattr(q, "model_dump") else q
                for q in body.questions
            ]
        quiz = await service.update_quiz(db, quiz_id, instructor_id, **fields)
        return QuizResponse.model_validate(quiz)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def delete_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    instructor_id: UUID,
) -> None:
    try:
        await service.delete_quiz(db, quiz_id, instructor_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def start_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
    redis: Redis | None = None,
) -> QuizStudentResponse:
    """Start a timed quiz — returns randomized questions with answers stripped."""
    try:
        result = await service.start_quiz(db, quiz_id, user_id, redis=redis)
        return QuizStudentResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def submit_attempt(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
    body: QuizAttemptRequest,
    redis: Redis | None = None,
) -> QuizAttemptResponse:
    try:
        result = await service.submit_attempt(
            db, quiz_id, user_id,
            answers=body.answers,
            time_taken_secs=body.time_taken_secs,
            redis=redis,
        )
        return QuizAttemptResponse(**result)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_my_attempts(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
) -> dict:
    try:
        return await service.get_my_attempts(db, quiz_id, user_id)
    except Exception as exc:
        raise _handle_domain_error(exc) from exc
