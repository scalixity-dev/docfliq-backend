"""drop_follows_blocks_move_to_identity

Revision ID: 2937ecd08870
Revises: 31ff7a88983d
Create Date: 2026-02-19 14:24:00.663701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2937ecd08870'
down_revision: Union[str, None] = '31ff7a88983d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Follow and Block tables moved to identity service (identity_db).
    op.drop_index(op.f('ix_follows_follower_id'), table_name='follows')
    op.drop_index(op.f('ix_follows_following_id'), table_name='follows')
    op.drop_table('follows')
    op.drop_index(op.f('ix_blocks_blocked_id'), table_name='blocks')
    op.drop_index(op.f('ix_blocks_blocker_id'), table_name='blocks')
    op.drop_table('blocks')


def downgrade() -> None:
    op.create_table('blocks',
    sa.Column('block_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('blocker_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('blocked_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('block_id', name=op.f('blocks_pkey')),
    sa.UniqueConstraint('blocker_id', 'blocked_id', name=op.f('uq_blocks_pair'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_blocks_blocker_id'), 'blocks', ['blocker_id'], unique=False)
    op.create_index(op.f('ix_blocks_blocked_id'), 'blocks', ['blocked_id'], unique=False)
    op.create_table('follows',
    sa.Column('follow_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('follower_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('following_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('follow_id', name=op.f('follows_pkey')),
    sa.UniqueConstraint('follower_id', 'following_id', name=op.f('uq_follows_pair'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_follows_following_id'), 'follows', ['following_id'], unique=False)
    op.create_index(op.f('ix_follows_follower_id'), 'follows', ['follower_id'], unique=False)
    # ### end Alembic commands ###
