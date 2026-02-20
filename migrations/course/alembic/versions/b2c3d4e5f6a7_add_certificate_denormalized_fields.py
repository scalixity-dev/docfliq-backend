"""add certificate denormalized fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('certificates', sa.Column('recipient_name', sa.String(length=200), nullable=False, server_default=''))
    op.add_column('certificates', sa.Column('course_title', sa.String(length=300), nullable=False, server_default=''))
    op.add_column('certificates', sa.Column('instructor_name', sa.String(length=200), nullable=False, server_default=''))
    op.add_column('certificates', sa.Column('total_hours', sa.Numeric(precision=5, scale=1), nullable=True))
    op.add_column('certificates', sa.Column('score', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('certificates', 'score')
    op.drop_column('certificates', 'total_hours')
    op.drop_column('certificates', 'instructor_name')
    op.drop_column('certificates', 'course_title')
    op.drop_column('certificates', 'recipient_name')
