"""
Profile domain — pure business logic (zero FastAPI imports).
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.exceptions import UserNotFound


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Load a user by PK; raise 404 if not found."""
    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFound()
    return user


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
