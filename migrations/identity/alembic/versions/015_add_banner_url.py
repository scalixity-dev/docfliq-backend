"""Add banner_url column to users table for profile banners.

Revision ID: 015
Revises: 014
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015"
down_revision: tuple[str, ...] = ("014", "1d887f5ca964")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("banner_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "banner_url")
