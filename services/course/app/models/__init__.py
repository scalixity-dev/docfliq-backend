# Import all models so Alembic can discover them via Base.metadata
from .certificate import Certificate
from .course import Course
from .course_instructor import CourseInstructor
from .course_module import CourseModule
from .enrollment import Enrollment
from .lesson import Lesson
from .lesson_progress import LessonProgress
from .promo_code import PromoCode
from .quiz import Quiz
from .quiz_attempt import QuizAttempt
from .scorm_api_log import ScormApiLog
from .scorm_session import ScormSession
from .survey import Survey
from .survey_response import SurveyResponse

__all__ = [
    "Certificate",
    "Course",
    "CourseInstructor",
    "CourseModule",
    "Enrollment",
    "Lesson",
    "LessonProgress",
    "PromoCode",
    "Quiz",
    "QuizAttempt",
    "ScormApiLog",
    "ScormSession",
    "Survey",
    "SurveyResponse",
]
