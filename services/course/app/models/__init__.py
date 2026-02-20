# Import all models so Alembic can discover them via Base.metadata
from .certificate import Certificate
from .course import Course
from .course_module import CourseModule
from .enrollment import Enrollment
from .lesson import Lesson
from .lesson_progress import LessonProgress
from .quiz import Quiz
from .quiz_attempt import QuizAttempt
from .scorm_session import ScormSession

__all__ = [
    "Certificate",
    "Course",
    "CourseModule",
    "Enrollment",
    "Lesson",
    "LessonProgress",
    "Quiz",
    "QuizAttempt",
    "ScormSession",
]
