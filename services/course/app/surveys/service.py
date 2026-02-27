"""Survey service — CRUD, response submission, and results aggregation.

Pure business logic, no FastAPI imports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    CourseNotFoundError,
    LessonNotFoundError,
    NotCourseOwnerError,
    NotEnrolledError,
    SurveyAlreadyRespondedError,
    SurveyNotFoundError,
)
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus, LessonProgressStatus
from app.models.lesson import Lesson
from app.models.lesson_progress import LessonProgress
from app.models.survey import Survey
from app.models.survey_response import SurveyResponse


# ---------------------------------------------------------------------------
# Survey CRUD
# ---------------------------------------------------------------------------


async def create_survey(
    db: AsyncSession,
    course_id: UUID,
    instructor_id: UUID,
    *,
    title: str,
    placement: str,
    is_required: bool = False,
    questions: list[dict],
    lesson_id: UUID | None = None,
    module_id: UUID | None = None,
    sort_order: int = 0,
) -> Survey:
    course = await db.get(Course, course_id)
    if course is None:
        raise CourseNotFoundError(str(course_id))
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    if lesson_id is not None:
        lesson = await db.get(Lesson, lesson_id)
        if lesson is None:
            raise LessonNotFoundError(str(lesson_id))

    survey = Survey(
        course_id=course_id,
        lesson_id=lesson_id,
        module_id=module_id,
        title=title,
        placement=placement,
        is_required=is_required,
        questions=questions,
        sort_order=sort_order,
    )
    db.add(survey)
    await db.flush()
    await db.refresh(survey)
    return survey


async def get_survey(db: AsyncSession, survey_id: UUID) -> Survey:
    survey = await db.get(Survey, survey_id)
    if survey is None:
        raise SurveyNotFoundError(str(survey_id))
    return survey


async def list_surveys_for_course(
    db: AsyncSession,
    course_id: UUID,
) -> list[Survey]:
    stmt = (
        select(Survey)
        .where(Survey.course_id == course_id)
        .order_by(Survey.sort_order, Survey.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_survey(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
    **fields: object,
) -> Survey:
    survey = await get_survey(db, survey_id)
    course = await db.get(Course, survey.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    for key, value in fields.items():
        if value is not None:
            setattr(survey, key, value)
    await db.flush()
    await db.refresh(survey)
    return survey


async def delete_survey(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
) -> None:
    survey = await get_survey(db, survey_id)
    course = await db.get(Course, survey.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()
    await db.delete(survey)
    await db.flush()


# ---------------------------------------------------------------------------
# Survey response submission
# ---------------------------------------------------------------------------


async def submit_survey_response(
    db: AsyncSession,
    survey_id: UUID,
    user_id: UUID,
    *,
    answers: list[dict],
) -> SurveyResponse:
    survey = await get_survey(db, survey_id)
    course = await db.get(Course, survey.course_id)

    enrollment = await _get_enrollment(db, user_id, course.course_id)
    if enrollment is None:
        raise NotEnrolledError()

    # Check for duplicate submission
    existing = await db.scalar(
        select(SurveyResponse.response_id).where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.enrollment_id == enrollment.enrollment_id,
        ),
    )
    if existing is not None:
        raise SurveyAlreadyRespondedError()

    response = SurveyResponse(
        survey_id=survey_id,
        enrollment_id=enrollment.enrollment_id,
        user_id=user_id,
        answers=answers,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(response)

    # If the survey is tied to a lesson, mark that lesson as completed
    if survey.lesson_id is not None:
        progress = await _upsert_lesson_progress(
            db, enrollment.enrollment_id, survey.lesson_id,
        )
        progress.status = LessonProgressStatus.COMPLETED
        progress.completed_at = datetime.now(timezone.utc)

        from app.player.service import _recalculate_weighted_progress

        await _recalculate_weighted_progress(db, enrollment, course)

    await db.flush()
    await db.refresh(response)
    return response


# ---------------------------------------------------------------------------
# Survey results aggregation (instructor view)
# ---------------------------------------------------------------------------


async def get_survey_results(
    db: AsyncSession,
    survey_id: UUID,
    instructor_id: UUID,
) -> dict:
    survey = await get_survey(db, survey_id)
    course = await db.get(Course, survey.course_id)
    if course.instructor_id != instructor_id:
        raise NotCourseOwnerError()

    count_stmt = (
        select(func.count())
        .select_from(SurveyResponse)
        .where(SurveyResponse.survey_id == survey_id)
    )
    total_responses = await db.scalar(count_stmt) or 0

    responses_stmt = select(SurveyResponse).where(
        SurveyResponse.survey_id == survey_id,
    )
    result = await db.execute(responses_stmt)
    responses = list(result.scalars().all())

    # Aggregate answers per question
    questions = survey.questions if isinstance(survey.questions, list) else []
    aggregated = []
    for qi, q in enumerate(questions):
        q_id = q.get("question_id", str(qi))
        q_type = q.get("question_type", "FREE_TEXT")
        agg: dict = {
            "question_id": q_id,
            "question_text": q.get("question_text", ""),
            "question_type": q_type,
            "response_count": 0,
        }

        values = []
        for resp in responses:
            ans_list = resp.answers if isinstance(resp.answers, list) else []
            for ans in ans_list:
                if ans.get("question_id") == q_id:
                    values.append(ans.get("answer_value"))
                    break

        agg["response_count"] = len(values)

        if q_type in ("RATING", "LIKERT"):
            numeric = [v for v in values if isinstance(v, (int, float))]
            agg["average"] = round(sum(numeric) / len(numeric), 2) if numeric else None
            agg["distribution"] = {}
            for v in numeric:
                key = str(int(v))
                agg["distribution"][key] = agg["distribution"].get(key, 0) + 1
        elif q_type == "MCQ":
            agg["distribution"] = {}
            for v in values:
                key = str(v)
                agg["distribution"][key] = agg["distribution"].get(key, 0) + 1
        elif q_type in ("FREE_TEXT",):
            agg["sample_answers"] = values[:20]

        aggregated.append(agg)

    return {
        "survey_id": survey.survey_id,
        "title": survey.title,
        "total_responses": total_responses,
        "questions": aggregated,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_enrollment(
    db: AsyncSession, user_id: UUID, course_id: UUID,
) -> Enrollment | None:
    stmt = select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
        Enrollment.status.in_([
            EnrollmentStatus.IN_PROGRESS,
            EnrollmentStatus.COMPLETED,
        ]),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _upsert_lesson_progress(
    db: AsyncSession, enrollment_id: UUID, lesson_id: UUID,
) -> LessonProgress:
    stmt = select(LessonProgress).where(
        LessonProgress.enrollment_id == enrollment_id,
        LessonProgress.lesson_id == lesson_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = LessonProgress(
            enrollment_id=enrollment_id,
            lesson_id=lesson_id,
            status=LessonProgressStatus.NOT_STARTED,
        )
        db.add(progress)
        await db.flush()
    return progress
