"""add_notifications_table

Revision ID: 2479fedf9df9
Revises: d5e6f7a8b9c0
Create Date: 2026-02-25 13:08:20.220133

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '2479fedf9df9'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("post_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_notifications_user_created_at",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_is_read",
        "notifications",
        ["user_id", "is_read"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_created_at", table_name="notifications")
    op.drop_table("notifications")
