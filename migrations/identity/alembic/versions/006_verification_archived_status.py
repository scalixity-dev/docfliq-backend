"""Add 'archived' value to verificationdocstatus enum

Revision ID: 006
Revises: 005
Create Date: 2026-02-19

Changes:
  - ALTER TYPE verificationdocstatus ADD VALUE 'archived'
    Used to mark old rejected documents that have been superseded by a re-upload.

Note: PostgreSQL does not support removing enum values. Downgrade is a no-op
      (the value remains in the type but is no longer used by application code).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE IF NOT EXISTS is safe to run multiple times (idempotent).
    # Available in PostgreSQL 9.3+.
    op.execute("ALTER TYPE verificationdocstatus ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    # PostgreSQL does not support removing individual enum values without
    # dropping and recreating the entire type — which would require migrating
    # all existing rows.  Since 'archived' rows would need to be handled
    # anyway, we leave the value in place on downgrade.
    pass
