import enum

from sqlalchemy.dialects.postgresql import ENUM as PgEnum


class PricingType(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"
    FREE_PLUS_CERTIFICATE = "FREE_PLUS_CERTIFICATE"


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
    PRESENTATION = "PRESENTATION"
    SURVEY = "SURVEY"
    ASSESSMENT = "ASSESSMENT"


class EnrollmentStatus(str, enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
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
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    RATING = "RATING"
    LIKERT = "LIKERT"
    FREE_TEXT = "FREE_TEXT"


class ShowAnswersPolicy(str, enum.Enum):
    NEVER = "NEVER"
    AFTER_SUBMIT = "AFTER_SUBMIT"
    AFTER_PASS = "AFTER_PASS"


class ScormSessionStatus(str, enum.Enum):
    INITIALIZED = "INITIALIZED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SurveyPlacement(str, enum.Enum):
    INLINE = "INLINE"
    END_OF_MODULE = "END_OF_MODULE"
    END_OF_COURSE = "END_OF_COURSE"


class ScormImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CompletionMode(str, enum.Enum):
    DEFAULT = "DEFAULT"
    CUSTOM = "CUSTOM"


class ModuleUnlockMode(str, enum.Enum):
    ALL_UNLOCKED = "ALL_UNLOCKED"
    SEQUENTIAL = "SEQUENTIAL"
    CUSTOM = "CUSTOM"


class CertificationMode(str, enum.Enum):
    COURSE = "COURSE"
    MODULE = "MODULE"
    BOTH = "BOTH"
    NONE = "NONE"


class CertificateType(str, enum.Enum):
    COURSE = "COURSE"
    MODULE = "MODULE"


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
survey_placement_enum = PgEnum(SurveyPlacement, name="survey_placement", create_type=True)
scorm_import_status_enum = PgEnum(ScormImportStatus, name="scorm_import_status", create_type=True)
completion_mode_enum = PgEnum(CompletionMode, name="completion_mode", create_type=True)
module_unlock_mode_enum = PgEnum(ModuleUnlockMode, name="module_unlock_mode", create_type=True)
certification_mode_enum = PgEnum(CertificationMode, name="certification_mode", create_type=True)
certificate_type_enum = PgEnum(CertificateType, name="certificate_type", create_type=True)
