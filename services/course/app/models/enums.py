import enum

from sqlalchemy.dialects.postgresql import ENUM as PgEnum


class PricingType(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"


class CourseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class CourseVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    VERIFIED_ONLY = "VERIFIED_ONLY"


class LessonType(str, enum.Enum):
    VIDEO = "VIDEO"
    PDF = "PDF"
    TEXT = "TEXT"
    QUIZ = "QUIZ"
    SCORM = "SCORM"


class EnrollmentStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"


class LessonProgressStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class QuestionType(str, enum.Enum):
    MCQ = "MCQ"
    MSQ = "MSQ"


class ShowAnswersPolicy(str, enum.Enum):
    NEVER = "NEVER"
    AFTER_SUBMIT = "AFTER_SUBMIT"
    AFTER_PASS = "AFTER_PASS"


class ScormSessionStatus(str, enum.Enum):
    INITIALIZED = "INITIALIZED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# SQLAlchemy PgEnum instances (reuse across models to avoid duplicate type creation)
pricing_type_enum = PgEnum(PricingType, name="pricing_type", create_type=True)
course_status_enum = PgEnum(CourseStatus, name="course_status", create_type=True)
course_visibility_enum = PgEnum(CourseVisibility, name="course_visibility", create_type=True)
lesson_type_enum = PgEnum(LessonType, name="lesson_type", create_type=True)
enrollment_status_enum = PgEnum(EnrollmentStatus, name="enrollment_status", create_type=True)
lesson_progress_status_enum = PgEnum(
    LessonProgressStatus, name="lesson_progress_status", create_type=True
)
show_answers_policy_enum = PgEnum(
    ShowAnswersPolicy, name="show_answers_policy", create_type=True
)
scorm_session_status_enum = PgEnum(
    ScormSessionStatus, name="scorm_session_status", create_type=True
)
