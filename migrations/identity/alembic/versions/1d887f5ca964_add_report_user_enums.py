"""add_report_user_enums

Revision ID: 1d887f5ca964
Revises: 012
Create Date: 2026-02-25 13:08:20.711502

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1d887f5ca964'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add USER target type if missing
    op.execute("ALTER TYPE reporttargettype ADD VALUE IF NOT EXISTS 'USER';")
    # Add report status values if missing
    op.execute("ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS 'OPEN';")
    op.execute("ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS 'REVIEWED';")
    op.execute("ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS 'ACTIONED';")
    op.execute("ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS 'DISMISSED';")


def downgrade() -> None:
    # Enum values cannot be removed safely; downgrade is a no-op.
    pass
