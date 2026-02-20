"""enhance player assessment progress

Revision ID: a1b2c3d4e5f6
Revises: 856d8eddef4e
Create Date: 2026-02-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '856d8eddef4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New enum types
show_answers_policy = postgresql.ENUM(
    'NEVER', 'AFTER_SUBMIT', 'AFTER_PASS',
    name='show_answers_policy', create_type=False,
)
scorm_session_status = postgresql.ENUM(
    'INITIALIZED', 'IN_PROGRESS', 'COMPLETED', 'FAILED',
    name='scorm_session_status', create_type=False,
)


def upgrade() -> None:
    # --- Create new enum types ---
    op.execute("CREATE TYPE show_answers_policy AS ENUM ('NEVER', 'AFTER_SUBMIT', 'AFTER_PASS')")
    op.execute("CREATE TYPE scorm_session_status AS ENUM ('INITIALIZED', 'IN_PROGRESS', 'COMPLETED', 'FAILED')")

    # --- ALTER TABLE quizzes: add assessment config columns ---
    op.add_column('quizzes', sa.Column('time_limit_secs', sa.Integer(), nullable=True))
    op.add_column('quizzes', sa.Column('randomize_order', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('quizzes', sa.Column(
        'show_answers', show_answers_policy, nullable=False, server_default='NEVER',
    ))

    # --- ALTER TABLE lessons: add player columns ---
    op.add_column('lessons', sa.Column('duration_secs', sa.Integer(), nullable=True))
    op.add_column('lessons', sa.Column('total_pages', sa.SmallInteger(), nullable=True))
    op.add_column('lessons', sa.Column('hls_manifest_key', sa.String(length=500), nullable=True))
    op.add_column('lessons', sa.Column('scorm_version', sa.String(length=20), nullable=True))
    op.add_column('lessons', sa.Column('scorm_entry_url', sa.String(length=500), nullable=True))

    # --- ALTER TABLE lesson_progress: add granular tracking columns ---
    op.add_column('lesson_progress', sa.Column(
        'watched_intervals', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
    ))
    op.add_column('lesson_progress', sa.Column(
        'watched_pct', sa.Numeric(precision=5, scale=2), nullable=True,
    ))
    op.add_column('lesson_progress', sa.Column(
        'pages_viewed', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
    ))
    op.add_column('lesson_progress', sa.Column(
        'pages_pct', sa.Numeric(precision=5, scale=2), nullable=True,
    ))
    op.add_column('lesson_progress', sa.Column('scorm_score', sa.SmallInteger(), nullable=True))

    # --- CREATE TABLE scorm_sessions ---
    op.create_table('scorm_sessions',
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('enrollment_id', sa.UUID(), nullable=False),
        sa.Column('lesson_id', sa.UUID(), nullable=False),
        sa.Column('status', scorm_session_status, nullable=False, server_default='INITIALIZED'),
        sa.Column('tracking_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('score_raw', sa.SmallInteger(), nullable=True),
        sa.Column('score_max', sa.SmallInteger(), nullable=True),
        sa.Column('score_min', sa.SmallInteger(), nullable=True),
        sa.Column('total_time_secs', sa.Integer(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['enrollment_id'], ['enrollments.enrollment_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.lesson_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_id'),
    )
    op.create_index(
        'ix_scorm_sessions_enrollment_lesson', 'scorm_sessions',
        ['enrollment_id', 'lesson_id'], unique=False,
    )

    # --- CREATE TABLE quiz_attempts ---
    op.create_table('quiz_attempts',
        sa.Column('attempt_id', sa.UUID(), nullable=False),
        sa.Column('quiz_id', sa.UUID(), nullable=False),
        sa.Column('enrollment_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('attempt_number', sa.SmallInteger(), nullable=False),
        sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('score', sa.SmallInteger(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('correct_count', sa.SmallInteger(), nullable=False),
        sa.Column('total_questions', sa.SmallInteger(), nullable=False),
        sa.Column('time_taken_secs', sa.Integer(), nullable=True),
        sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.quiz_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['enrollment_id'], ['enrollments.enrollment_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('attempt_id'),
        sa.UniqueConstraint('quiz_id', 'enrollment_id', 'attempt_number', name='uq_quiz_attempt_number'),
    )
    op.create_index('ix_quiz_attempts_quiz_enrollment', 'quiz_attempts', ['quiz_id', 'enrollment_id'], unique=False)
    op.create_index('ix_quiz_attempts_user_id', 'quiz_attempts', ['user_id'], unique=False)


def downgrade() -> None:
    # --- Drop new tables ---
    op.drop_index('ix_quiz_attempts_user_id', table_name='quiz_attempts')
    op.drop_index('ix_quiz_attempts_quiz_enrollment', table_name='quiz_attempts')
    op.drop_table('quiz_attempts')

    op.drop_index('ix_scorm_sessions_enrollment_lesson', table_name='scorm_sessions')
    op.drop_table('scorm_sessions')

    # --- Drop new columns from lesson_progress ---
    op.drop_column('lesson_progress', 'scorm_score')
    op.drop_column('lesson_progress', 'pages_pct')
    op.drop_column('lesson_progress', 'pages_viewed')
    op.drop_column('lesson_progress', 'watched_pct')
    op.drop_column('lesson_progress', 'watched_intervals')

    # --- Drop new columns from lessons ---
    op.drop_column('lessons', 'scorm_entry_url')
    op.drop_column('lessons', 'scorm_version')
    op.drop_column('lessons', 'hls_manifest_key')
    op.drop_column('lessons', 'total_pages')
    op.drop_column('lessons', 'duration_secs')

    # --- Drop new columns from quizzes ---
    op.drop_column('quizzes', 'show_answers')
    op.drop_column('quizzes', 'randomize_order')
    op.drop_column('quizzes', 'time_limit_secs')

    # --- Drop enum types ---
    op.execute("DROP TYPE IF EXISTS scorm_session_status")
    op.execute("DROP TYPE IF EXISTS show_answers_policy")
