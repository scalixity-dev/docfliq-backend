"""features v2: setup, build, surveys, SCORM import

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-02-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum additions ───────────────────────────────────────────────────
    op.execute("ALTER TYPE pricing_type ADD VALUE IF NOT EXISTS 'FREE_PLUS_CERTIFICATE'")
    op.execute("ALTER TYPE enrollment_status ADD VALUE IF NOT EXISTS 'PENDING_APPROVAL'")
    op.execute("ALTER TYPE lesson_type ADD VALUE IF NOT EXISTS 'PRESENTATION'")
    op.execute("ALTER TYPE lesson_type ADD VALUE IF NOT EXISTS 'SURVEY'")
    op.execute("ALTER TYPE lesson_type ADD VALUE IF NOT EXISTS 'ASSESSMENT'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'TRUE_FALSE'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'SHORT_ANSWER'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'RATING'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'LIKERT'")
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'FREE_TEXT'")

    # New enums
    survey_placement = postgresql.ENUM(
        "INLINE", "END_OF_MODULE", "END_OF_COURSE",
        name="survey_placement", create_type=False,
    )
    op.execute("CREATE TYPE survey_placement AS ENUM ('INLINE', 'END_OF_MODULE', 'END_OF_COURSE')")

    scorm_import_status = postgresql.ENUM(
        "PENDING", "PROCESSING", "COMPLETED", "FAILED",
        name="scorm_import_status", create_type=False,
    )
    op.execute("CREATE TYPE scorm_import_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')")

    # ── ALTER TABLE courses ──────────────────────────────────────────────
    op.add_column("courses", sa.Column(
        "custom_metadata", postgresql.JSONB(astext_type=sa.Text()),
        nullable=True, server_default="[]",
    ))
    op.add_column("courses", sa.Column(
        "self_registration_enabled", sa.Boolean(), nullable=False, server_default="true",
    ))
    op.add_column("courses", sa.Column(
        "approval_required", sa.Boolean(), nullable=False, server_default="false",
    ))
    op.add_column("courses", sa.Column(
        "access_code", sa.String(length=50), nullable=True,
    ))
    op.add_column("courses", sa.Column(
        "discount_pct", sa.Numeric(precision=5, scale=2), nullable=True,
    ))
    op.add_column("courses", sa.Column(
        "registration_questions", postgresql.JSONB(astext_type=sa.Text()),
        nullable=True, server_default="[]",
    ))
    op.add_column("courses", sa.Column(
        "eligibility_rules", postgresql.JSONB(astext_type=sa.Text()),
        nullable=True, server_default="{}",
    ))
    op.add_column("courses", sa.Column(
        "scorm_import_status", scorm_import_status, nullable=True,
    ))
    op.add_column("courses", sa.Column(
        "scorm_import_error", sa.Text(), nullable=True,
    ))
    op.add_column("courses", sa.Column(
        "certificate_price", sa.Numeric(precision=10, scale=2), nullable=True,
    ))

    # ── New table: course_instructors ────────────────────────────────────
    op.create_table(
        "course_instructors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("instructor_id", sa.UUID(), nullable=False),
        sa.Column("instructor_name", sa.String(length=200), nullable=False),
        sa.Column("instructor_bio", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="co_instructor"),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("added_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "instructor_id", name="uq_course_instructor"),
    )
    op.create_index("ix_course_instructors_course_id", "course_instructors", ["course_id"])
    op.create_index("ix_course_instructors_instructor_id", "course_instructors", ["instructor_id"])

    # ── New table: promo_codes ───────────────────────────────────────────
    op.create_table(
        "promo_codes",
        sa.Column("promo_code_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("current_uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_until", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("promo_code_id"),
        sa.UniqueConstraint("course_id", "code", name="uq_promo_code_course"),
    )
    op.create_index("ix_promo_codes_course_id", "promo_codes", ["course_id"])
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    # ── ALTER TABLE enrollments ──────────────────────────────────────────
    op.add_column("enrollments", sa.Column("approved_by", sa.UUID(), nullable=True))
    op.add_column("enrollments", sa.Column(
        "approved_at", postgresql.TIMESTAMP(timezone=True), nullable=True,
    ))
    op.add_column("enrollments", sa.Column(
        "access_code_used", sa.String(length=50), nullable=True,
    ))
    op.add_column("enrollments", sa.Column("promo_code_id", sa.UUID(), nullable=True))
    op.add_column("enrollments", sa.Column(
        "discount_applied_pct", sa.Numeric(precision=5, scale=2), nullable=True,
    ))
    op.add_column("enrollments", sa.Column(
        "final_price", sa.Numeric(precision=10, scale=2), nullable=True,
    ))
    op.add_column("enrollments", sa.Column(
        "registration_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
    ))

    # ── ALTER TABLE lessons ──────────────────────────────────────────────
    op.add_column("lessons", sa.Column("slide_count", sa.SmallInteger(), nullable=True))
    op.add_column("lessons", sa.Column(
        "is_required", sa.Boolean(), nullable=False, server_default="false",
    ))
    op.add_column("lessons", sa.Column(
        "is_gated", sa.Boolean(), nullable=False, server_default="false",
    ))
    op.add_column("lessons", sa.Column("gate_passing_score", sa.SmallInteger(), nullable=True))

    # ── New table: surveys ───────────────────────────────────────────────
    op.create_table(
        "surveys",
        sa.Column("survey_id", sa.UUID(), nullable=False),
        sa.Column("lesson_id", sa.UUID(), nullable=True),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("module_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("placement", survey_placement, nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.lesson_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["course_modules.module_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("survey_id"),
    )
    op.create_index("ix_surveys_course_id", "surveys", ["course_id"])
    op.create_index("ix_surveys_lesson_id", "surveys", ["lesson_id"])
    op.create_index("ix_surveys_module_id", "surveys", ["module_id"])

    # ── New table: survey_responses ──────────────────────────────────────
    op.create_table(
        "survey_responses",
        sa.Column("response_id", sa.UUID(), nullable=False),
        sa.Column("survey_id", sa.UUID(), nullable=False),
        sa.Column("enrollment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("submitted_at", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["survey_id"], ["surveys.survey_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.enrollment_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("response_id"),
        sa.UniqueConstraint("survey_id", "enrollment_id", name="uq_survey_response_enrollment"),
    )
    op.create_index("ix_survey_responses_survey_id", "survey_responses", ["survey_id"])
    op.create_index("ix_survey_responses_user_id", "survey_responses", ["user_id"])

    # ── New table: scorm_api_logs ────────────────────────────────────────
    op.create_table(
        "scorm_api_logs",
        sa.Column("log_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("api_call", sa.String(length=100), nullable=False),
        sa.Column("parameter", sa.String(length=200), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=10), nullable=True),
        sa.Column("timestamp", postgresql.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["scorm_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index("ix_scorm_api_logs_session_id", "scorm_api_logs", ["session_id"])
    op.create_index("ix_scorm_api_logs_timestamp", "scorm_api_logs", ["timestamp"])

    # ── ALTER TABLE scorm_sessions ───────────────────────────────────────
    op.add_column("scorm_sessions", sa.Column("suspend_data", sa.Text(), nullable=True))


def downgrade() -> None:
    # scorm_sessions
    op.drop_column("scorm_sessions", "suspend_data")

    # scorm_api_logs
    op.drop_index("ix_scorm_api_logs_timestamp", table_name="scorm_api_logs")
    op.drop_index("ix_scorm_api_logs_session_id", table_name="scorm_api_logs")
    op.drop_table("scorm_api_logs")

    # survey_responses
    op.drop_index("ix_survey_responses_user_id", table_name="survey_responses")
    op.drop_index("ix_survey_responses_survey_id", table_name="survey_responses")
    op.drop_table("survey_responses")

    # surveys
    op.drop_index("ix_surveys_module_id", table_name="surveys")
    op.drop_index("ix_surveys_lesson_id", table_name="surveys")
    op.drop_index("ix_surveys_course_id", table_name="surveys")
    op.drop_table("surveys")

    # lessons
    op.drop_column("lessons", "gate_passing_score")
    op.drop_column("lessons", "is_gated")
    op.drop_column("lessons", "is_required")
    op.drop_column("lessons", "slide_count")

    # enrollments
    op.drop_column("enrollments", "registration_answers")
    op.drop_column("enrollments", "final_price")
    op.drop_column("enrollments", "discount_applied_pct")
    op.drop_column("enrollments", "promo_code_id")
    op.drop_column("enrollments", "access_code_used")
    op.drop_column("enrollments", "approved_at")
    op.drop_column("enrollments", "approved_by")

    # promo_codes
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_index("ix_promo_codes_course_id", table_name="promo_codes")
    op.drop_table("promo_codes")

    # course_instructors
    op.drop_index("ix_course_instructors_instructor_id", table_name="course_instructors")
    op.drop_index("ix_course_instructors_course_id", table_name="course_instructors")
    op.drop_table("course_instructors")

    # courses
    op.drop_column("courses", "certificate_price")
    op.drop_column("courses", "scorm_import_error")
    op.drop_column("courses", "scorm_import_status")
    op.drop_column("courses", "eligibility_rules")
    op.drop_column("courses", "registration_questions")
    op.drop_column("courses", "discount_pct")
    op.drop_column("courses", "access_code")
    op.drop_column("courses", "approval_required")
    op.drop_column("courses", "self_registration_enabled")
    op.drop_column("courses", "custom_metadata")

    # Drop new enums
    op.execute("DROP TYPE IF EXISTS scorm_import_status")
    op.execute("DROP TYPE IF EXISTS survey_placement")

    # Note: Cannot remove values from existing enums in PostgreSQL without recreating them.
    # The added enum values (FREE_PLUS_CERTIFICATE, PENDING_APPROVAL, PRESENTATION, SURVEY,
    # ASSESSMENT, TRUE_FALSE, SHORT_ANSWER, RATING, LIKERT, FREE_TEXT) will persist.
