"""
Admin domain — request orchestration layer.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    AdminBanUserRequest,
    AdminCreateUserRequest,
    AdminUserListResponse,
    AdminUserResponse,
)
from app.admin.service import (
    ban_user as ban_user_svc,
    create_admin_user as create_admin_user_svc,
    get_user_detail as get_user_detail_svc,
    list_users as list_users_svc,
    manual_verify_user as manual_verify_user_svc,
    unban_user as unban_user_svc,
)
from app.auth.constants import UserRole, VerificationStatus


async def create_admin_user(
    session: AsyncSession,
    body: AdminCreateUserRequest,
) -> AdminUserResponse:
    user = await create_admin_user_svc(
        session,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return AdminUserResponse.model_validate(user)


async def list_users(
    session: AsyncSession,
    *,
    page: int,
    size: int,
    role: UserRole | None = None,
    verification_status: VerificationStatus | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> AdminUserListResponse:
    users, total = await list_users_svc(
        session,
        page=page,
        size=size,
        role=role,
        verification_status=verification_status,
        is_active=is_active,
        search=search,
    )
    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        size=size,
    )


async def get_user_detail(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> AdminUserResponse:
    user = await get_user_detail_svc(session, user_id)
    return AdminUserResponse.model_validate(user)


async def ban_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: AdminBanUserRequest,
) -> AdminUserResponse:
    user = await ban_user_svc(session, user_id, body.reason)
    return AdminUserResponse.model_validate(user)


async def unban_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> AdminUserResponse:
    user = await unban_user_svc(session, user_id)
    return AdminUserResponse.model_validate(user)


async def manual_verify_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> AdminUserResponse:
    user = await manual_verify_user_svc(session, user_id)
    return AdminUserResponse.model_validate(user)
