"""Assessment service — quiz CRUD, attempt scoring, and grading.

Supports MCQ (single answer) and MSQ (multiple answers).
Time-limited quizzes, randomized question order, and answer review policies.

Pure business logic, no FastAPI imports.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    LessonNotFoundError,
    MaxAttemptsReachedError,
    NotCourseOwnerError,
    NotEnrolledError,
    QuizAlreadyExistsError,
    QuizNotFoundError,
    QuizTimeLimitExceededError,
)
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import LessonProgressStatus, QuestionType, ShowAnswersPolicy
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.player.cache import get_quiz_start_time, start_quiz_timer


# ---------------------------------------------------------------------------
# Quiz CRUD
# ---------------------------------------------------------------------------


async def create_quiz(
    db: AsyncSession,
    lesson_id: UUID,
    instructor_id: UUID,
    *,
    questions: list[dict],
    passing_score: int,
    max_attempts: int | None,
    time_limit_secs: int | None = None,
    randomize_order: bool = False,
    show_answers: ShowAnswersPolicy = ShowAnswersPolicy.NEVER,
) -> Quiz:
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFoundError(str(lesson_id))

    module = await db.get(CourseModule, lesson.module_id)
    course = await db.get(Course, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    existing = await db.scalar(
        select(Quiz.quiz_id).where(Quiz.lesson_id == lesson_id),
    )
    if existing is not None:
        raise QuizAlreadyExistsError()

    quiz = Quiz(
        lesson_id=lesson_id,
        questions=questions,
        passing_score=passing_score,
        max_attempts=max_attempts,
        time_limit_secs=time_limit_secs,
        randomize_order=randomize_order,
        show_answers=show_answers,
    )
    db.add(quiz)
    await db.flush()
    await db.refresh(quiz)
    return quiz


async def get_quiz_by_id(db: AsyncSession, quiz_id: UUID) -> Quiz:
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise QuizNotFoundError(str(quiz_id))
    return quiz


async def get_quiz_for_lesson(db: AsyncSession, lesson_id: UUID) -> Quiz:
    stmt = select(Quiz).where(Quiz.lesson_id == lesson_id)
    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()
    if quiz is None:
        raise QuizNotFoundError(f"lesson={lesson_id}")
    return quiz


async def update_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    instructor_id: UUID,
    **fields: object,
) -> Quiz:
    quiz = await get_quiz_by_id(db, quiz_id)
    lesson = await db.get(Lesson, quiz.lesson_id)
    module = await db.get(CourseModule, lesson.module_id)
    course = await db.get(Course, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    for key, value in fields.items():
        if value is not None:
            setattr(quiz, key, value)
    await db.flush()
    await db.refresh(quiz)
    return quiz


async def delete_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    instructor_id: UUID,
) -> None:
    quiz = await get_quiz_by_id(db, quiz_id)
    lesson = await db.get(Lesson, quiz.lesson_id)
    module = await db.get(CourseModule, lesson.module_id)
    course = await db.get(Course, module.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    await db.delete(quiz)
    await db.flush()


# ---------------------------------------------------------------------------
# Start quiz (timed + randomized)
# ---------------------------------------------------------------------------

_TIMER_GRACE_SECS = 30


async def start_quiz(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
    *,
    redis: Redis | None = None,
) -> dict:
    """Start a quiz attempt: optionally start timer, randomize questions.

    Returns student-safe questions (no correct answers) + quiz metadata.
    """
    quiz = await get_quiz_by_id(db, quiz_id)
    lesson = await db.get(Lesson, quiz.lesson_id)
    module = await db.get(CourseModule, lesson.module_id)

    # Verify enrollment
    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    # Check max attempts
    attempt_count = await _count_attempts(db, quiz_id, enrollment.enrollment_id)
    if quiz.max_attempts is not None and attempt_count >= quiz.max_attempts:
        raise MaxAttemptsReachedError()

    # Start timer in Redis if time-limited
    if quiz.time_limit_secs and redis is not None:
        try:
            await start_quiz_timer(
                quiz_id, enrollment.enrollment_id,
                quiz.time_limit_secs, redis,
            )
        except Exception:
            pass  # best-effort

    questions = quiz.questions if isinstance(quiz.questions, list) else []

    # Randomize order if configured
    if quiz.randomize_order:
        questions = list(questions)
        random.shuffle(questions)

    # Strip correct answers for student view
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

    return {
        "quiz_id": quiz.quiz_id,
        "lesson_id": quiz.lesson_id,
        "questions": stripped,
        "passing_score": quiz.passing_score,
        "max_attempts": quiz.max_attempts,
        "time_limit_secs": quiz.time_limit_secs,
        "show_answers": quiz.show_answers,
    }


# ---------------------------------------------------------------------------
# Quiz Attempts
# ---------------------------------------------------------------------------


async def submit_attempt(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
    *,
    answers: list[int | list[int] | str],
    time_taken_secs: int | None = None,
    redis: Redis | None = None,
) -> dict:
    """Score a quiz attempt (MCQ, MSQ, TRUE_FALSE, SHORT_ANSWER).

    Returns dict with quiz_id, score, passed, correct_count, total_questions,
    attempt_number, time_taken_secs, answers_review.
    """
    quiz = await get_quiz_by_id(db, quiz_id)
    lesson = await db.get(Lesson, quiz.lesson_id)
    module = await db.get(CourseModule, lesson.module_id)

    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    # Check time limit
    if quiz.time_limit_secs and redis is not None:
        try:
            start_ts = await get_quiz_start_time(
                quiz_id, enrollment.enrollment_id, redis,
            )
            if start_ts is not None:
                elapsed = int(time.time()) - start_ts
                if elapsed > quiz.time_limit_secs + _TIMER_GRACE_SECS:
                    raise QuizTimeLimitExceededError()
        except QuizTimeLimitExceededError:
            raise
        except Exception:
            pass  # Redis failure — allow submission

    # Check max attempts
    attempt_count = await _count_attempts(db, quiz_id, enrollment.enrollment_id)
    if quiz.max_attempts is not None and attempt_count >= quiz.max_attempts:
        raise MaxAttemptsReachedError()

    # Score
    questions = quiz.questions if isinstance(quiz.questions, list) else []
    total_questions = len(questions)
    correct_count = 0

    for i, q in enumerate(questions):
        if i >= len(answers):
            continue
        q_type = q.get("question_type", "MCQ")
        if q_type == QuestionType.MSQ.value:
            # MSQ: all-or-nothing — exact set match
            correct_set = set(q.get("correct_indices", []))
            user_answer = answers[i]
            user_set = set(user_answer) if isinstance(user_answer, list) else {user_answer}
            if user_set == correct_set:
                correct_count += 1
        elif q_type == QuestionType.TRUE_FALSE.value:
            correct_idx = q.get("correct_index")
            user_answer = answers[i]
            if isinstance(user_answer, list):
                user_answer = user_answer[0] if user_answer else None
            if user_answer == correct_idx:
                correct_count += 1
        elif q_type == QuestionType.SHORT_ANSWER.value:
            correct_text = (q.get("correct_text") or "").strip().lower()
            user_answer = str(answers[i]).strip().lower() if answers[i] is not None else ""
            if user_answer == correct_text:
                correct_count += 1
        else:
            # MCQ: single index match
            correct_idx = q.get("correct_index")
            user_answer = answers[i]
            if isinstance(user_answer, list):
                user_answer = user_answer[0] if user_answer else None
            if user_answer == correct_idx:
                correct_count += 1

    score = round(correct_count / total_questions * 100) if total_questions > 0 else 0
    passed = score >= quiz.passing_score

    # Store QuizAttempt record
    attempt_number = attempt_count + 1
    attempt = QuizAttempt(
        quiz_id=quiz_id,
        enrollment_id=enrollment.enrollment_id,
        user_id=user_id,
        attempt_number=attempt_number,
        answers=answers,
        score=score,
        passed=passed,
        correct_count=correct_count,
        total_questions=total_questions,
        time_taken_secs=time_taken_secs,
    )
    db.add(attempt)

    # Update lesson progress
    progress = await _upsert_progress(db, enrollment.enrollment_id, quiz.lesson_id)
    progress.quiz_score = score
    progress.quiz_attempts = attempt_number
    if passed:
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)

    await db.flush()

    # Recalculate weighted course progress
    course = await db.get(Course, module.course_id)
    from app.player.service import _recalculate_weighted_progress
    await _recalculate_weighted_progress(db, enrollment, course)

    # Build answers review if policy permits
    answers_review = _build_answers_review(quiz, answers, passed)

    return {
        "quiz_id": quiz.quiz_id,
        "score": score,
        "passed": passed,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "attempt_number": attempt_number,
        "time_taken_secs": time_taken_secs,
        "answers_review": answers_review,
    }


async def get_my_attempts(
    db: AsyncSession,
    quiz_id: UUID,
    user_id: UUID,
) -> dict:
    """Return attempt history for the current user on a quiz."""
    quiz = await get_quiz_by_id(db, quiz_id)
    lesson = await db.get(Lesson, quiz.lesson_id)
    module = await db.get(CourseModule, lesson.module_id)

    enrollment = await _get_enrollment(db, user_id, module.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    attempt_stmt = (
        select(QuizAttempt)
        .where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.enrollment_id == enrollment.enrollment_id,
        )
        .order_by(QuizAttempt.attempt_number)
    )
    result = await db.execute(attempt_stmt)
    attempts = list(result.scalars().all())

    best_score = max((a.score for a in attempts), default=None)

    return {
        "quiz_id": quiz.quiz_id,
        "total_attempts": len(attempts),
        "max_attempts": quiz.max_attempts,
        "best_score": best_score,
        "passed": any(a.passed for a in attempts),
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "score": a.score,
                "passed": a.passed,
                "correct_count": a.correct_count,
                "total_questions": a.total_questions,
                "time_taken_secs": a.time_taken_secs,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            }
            for a in attempts
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_answers_review(
    quiz: Quiz,
    user_answers: list[int | list[int] | str],
    passed: bool,
) -> list[dict] | None:
    """Build per-question review based on show_answers policy."""
    if quiz.show_answers == ShowAnswersPolicy.NEVER:
        return None
    if quiz.show_answers == ShowAnswersPolicy.AFTER_PASS and not passed:
        return None

    questions = quiz.questions if isinstance(quiz.questions, list) else []
    review = []
    for i, q in enumerate(questions):
        q_type = q.get("question_type", "MCQ")
        item = {
            "question_index": i,
            "question": q.get("question", ""),
            "user_answer": user_answers[i] if i < len(user_answers) else None,
        }
        if q_type == QuestionType.MSQ.value:
            item["correct_indices"] = q.get("correct_indices", [])
        elif q_type == QuestionType.SHORT_ANSWER.value:
            item["correct_text"] = q.get("correct_text")
        elif q_type == QuestionType.TRUE_FALSE.value:
            item["correct_index"] = q.get("correct_index")
        else:
            item["correct_index"] = q.get("correct_index")
        item["explanation"] = q.get("explanation")
        review.append(item)
    return review


async def _get_enrollment(
    db: AsyncSession, user_id: UUID, course_id: UUID,
) -> Enrollment | None:
    stmt = select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _count_attempts(
    db: AsyncSession, quiz_id: UUID, enrollment_id: UUID,
) -> int:
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(QuizAttempt)
        .where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.enrollment_id == enrollment_id,
        )
    )
    return await db.scalar(stmt) or 0


async def _upsert_progress(
    db: AsyncSession, enrollment_id: UUID, lesson_id: UUID,
) -> LessonProgress:
    stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment_id,
        LessonProgress.lesson_id == lesson_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if progress is not None:
        return progress

    progress = LessonProgress(
        enrollment_id=enrollment_id,
        lesson_id=lesson_id,
        status=LessonProgressStatus.IN_PROGRESS,
        quiz_attempts=0,
    )
    db.add(progress)
    await db.flush()
    return progress
