"""
Profile domain — pure business logic (zero FastAPI imports).
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.exceptions import UserHiddenByBlock, UserNotFound


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Load a user by PK; raise 404 if not found."""
    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFound()
    return user


async def get_profile_for_viewer(
    session: AsyncSession,
    user_id: uuid.UUID,
    viewer_id: uuid.UUID,
) -> User:
    """Load a user by PK and verify they haven't blocked the viewer.

    Single query instead of separate block-check + profile-load.
    Raises UserNotFound (404) or UserHiddenByBlock (404).
    """
    from app.social_graph.models import Block

    blocked_sq = sa.exists(
        sa.select(Block.id).where(
            Block.blocker_id == user_id,
            Block.blocked_id == viewer_id,
        )
    )
    result = await session.execute(
        sa.select(User, blocked_sq).where(User.id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise UserNotFound()
    user, is_blocked = row.tuple()
    if is_blocked:
        raise UserHiddenByBlock()
    return user


async def search_users(
    session: AsyncSession,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[User], int]:
    """Search active users by full_name or username using ILIKE."""
    pattern = f"%{query}%"
    base = (
        sa.select(User)
        .where(
            User.is_active.is_(True),
            User.is_banned.is_(False),
            sa.or_(
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
            ),
        )
    )
    total_result = await session.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )
    total = total_result.scalar_one()
    result = await session.execute(
        base.order_by(User.full_name.asc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_profile(
    session: AsyncSession,
    user_id: uuid.UUID,
    fields: dict,
) -> User:
    """Patch the provided fields onto the user row and persist."""
    user = await get_profile(session, user_id)
    for key, value in fields.items():
        setattr(user, key, value)
    # flush: writes changes within the open transaction; get_db commits at request end.
    # session.refresh() is not needed — expire_on_commit=False keeps the object current.
    await session.flush()
    return user
