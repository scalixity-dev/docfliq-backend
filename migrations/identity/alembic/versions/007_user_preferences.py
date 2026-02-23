"""Add user preference columns: purposes, event_schedule, languages

Revision ID: 007
Revises: 006
Create Date: 2026-02-21

Changes:
  - users.purposes         TEXT[] NULL — Step 1: why are you here (Attend live events, etc.)
  - users.event_schedule   TEXT[] NULL — Step 3: live events on weekdays/weekends
  - users.languages        TEXT[] NULL — Step 3: course language preferences
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("purposes", postgresql.ARRAY(sa.String(100)), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "event_schedule",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "languages")
    op.drop_column("users", "event_schedule")
    op.drop_column("users", "purposes")
