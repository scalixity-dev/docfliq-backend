"""
Admin domain — pure business logic (zero FastAPI imports).
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole, VerificationStatus
from app.auth.models import User
from app.auth.service import get_user_by_email, invalidate_all_user_sessions
from app.auth.utils import hash_password
from app.exceptions import UserAlreadyExists, UserNotFound
from shared.constants import Role


async def create_admin_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
) -> User:
    """
    Create a user with admin role.

    Guards: email uniqueness. Happy path last.
    """
    if await get_user_by_email(session, email) is not None:
        raise UserAlreadyExists()

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.ADMIN,
        roles=[Role.ADMIN.value],
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


async def list_users(
    session: AsyncSession,
    *,
    page: int,
    size: int,
    role: UserRole | None = None,
    verification_status: VerificationStatus | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> tuple[list[User], int]:
    """
    Paginated user listing with optional filters.

    Returns (users, total_count).
    """
    base = sa.select(User)
    count_base = sa.select(sa.func.count()).select_from(User)

    filters = []
    if role is not None:
        filters.append(User.role == role)
    if verification_status is not None:
        filters.append(User.verification_status == verification_status)
    if is_active is not None:
        filters.append(User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        filters.append(
            sa.or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    for f in filters:
        base = base.where(f)
        count_base = count_base.where(f)

    total_result = await session.execute(count_base)
    total = total_result.scalar_one()

    offset = (page - 1) * size
    query = base.order_by(User.created_at.desc()).offset(offset).limit(size)
    result = await session.execute(query)
    users = list(result.scalars().all())

    return users, total


async def get_user_detail(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    """Load a single user by PK for admin viewing."""
    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFound()
    return user


async def ban_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    reason: str,
) -> User:
    """Ban a user: set is_banned=True and wipe all active sessions."""
    user = await get_user_detail(session, user_id)
    if user.is_banned:
        from app.exceptions import UserBanned

        raise UserBanned()
    user.is_banned = True
    user.ban_reason = reason
    user.is_active = False
    await session.flush()
    await invalidate_all_user_sessions(session, user_id)
    return user


async def unban_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    """Unban a user: set is_banned=False and restore active status."""
    user = await get_user_detail(session, user_id)
    if not user.is_banned:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is not currently banned.",
        )
    user.is_banned = False
    user.ban_reason = None
    user.is_active = True
    await session.flush()
    return user


async def manual_verify_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    """Manually set a user's verification status to VERIFIED."""
    user = await get_user_detail(session, user_id)
    if user.verification_status == VerificationStatus.VERIFIED:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already verified.",
        )
    user.verification_status = VerificationStatus.VERIFIED
    user.content_creation_mode = True
    await session.flush()
    return user
