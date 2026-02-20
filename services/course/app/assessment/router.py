"""Assessment router — quiz CRUD, quiz attempts, and grading.

Endpoints for instructors (quiz management) and students (taking quizzes).
Supports MCQ + MSQ, timed quizzes, randomized order, and answer review.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import controller
from app.assessment.schemas import (
    CreateQuizRequest,
    QuizAttemptRequest,
    QuizAttemptResponse,
    QuizResponse,
    QuizStudentResponse,
    UpdateQuizRequest,
)
from app.database import get_db
from app.dependencies import get_current_user, get_redis

router = APIRouter(prefix="/assessment", tags=["Assessment"])


# ======================================================================
# Quiz CRUD (instructor)
# ======================================================================


@router.post(
    "/lessons/{lesson_id}/quiz",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create quiz for a lesson (instructor)",
    description="Attach an MCQ/MSQ quiz to a lesson. Supports time limits, "
    "randomized order, and answer reveal policies. One quiz per lesson.",
)
async def create_quiz(
    lesson_id: UUID,
    body: CreateQuizRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> QuizResponse:
    return await controller.create_quiz(db, lesson_id, user_id, body)


@router.get(
    "/lessons/{lesson_id}/quiz",
    response_model=QuizStudentResponse,
    summary="Get quiz for a lesson (student view)",
    description="Returns the quiz questions without correct answers. "
    "Suitable for student-facing quiz UI.",
)
async def get_quiz_student(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> QuizStudentResponse:
    return await controller.get_quiz_for_student(db, lesson_id)


@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizResponse,
    summary="Get quiz (instructor view with answers)",
    description="Returns the full quiz including correct_index/correct_indices "
    "and explanations. For instructor review.",
)
async def get_quiz_instructor(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> QuizResponse:
    return await controller.get_quiz_instructor(db, quiz_id)


@router.patch(
    "/quizzes/{quiz_id}",
    response_model=QuizResponse,
    summary="Update quiz (instructor)",
)
async def update_quiz(
    quiz_id: UUID,
    body: UpdateQuizRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> QuizResponse:
    return await controller.update_quiz(db, quiz_id, user_id, body)


@router.delete(
    "/quizzes/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete quiz (instructor)",
)
async def delete_quiz(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> None:
    await controller.delete_quiz(db, quiz_id, user_id)


# ======================================================================
# Quiz start + attempts (student)
# ======================================================================


@router.post(
    "/quizzes/{quiz_id}/start",
    response_model=QuizStudentResponse,
    summary="Start a quiz attempt",
    description="Start a quiz attempt. If the quiz has a time limit, starts "
    "the countdown timer. Returns randomized questions (if configured) "
    "with correct answers stripped.",
)
async def start_quiz(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> QuizStudentResponse:
    return await controller.start_quiz(db, quiz_id, user_id, redis=redis)


@router.post(
    "/quizzes/{quiz_id}/attempt",
    response_model=QuizAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit quiz attempt",
    description="Submit answers to a quiz. For MCQ: int index. "
    "For MSQ: list of int indices. "
    "Returns score, pass/fail, and (optionally) answer review.",
)
async def submit_attempt(
    quiz_id: UUID,
    body: QuizAttemptRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> QuizAttemptResponse:
    return await controller.submit_attempt(db, quiz_id, user_id, body, redis=redis)


@router.get(
    "/quizzes/{quiz_id}/attempts",
    summary="Get my quiz attempt history",
    description="Returns the user's attempts with per-attempt details, "
    "best score, and whether they have passed the quiz.",
)
async def get_my_attempts(
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
) -> dict:
    return await controller.get_my_attempts(db, quiz_id, user_id)
