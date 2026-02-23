"""
Admin domain — user management routes.

Routes:
  POST  /api/v1/admin/users/create              Create an admin account (SUPER_ADMIN only)
  GET   /api/v1/admin/users                      List all users (ADMIN+)
  GET   /api/v1/admin/users/{user_id}            Get single user detail (ADMIN+)
  PATCH /api/v1/admin/users/{user_id}/ban        Ban a user (ADMIN+)
  PATCH /api/v1/admin/users/{user_id}/unban      Unban a user (ADMIN+)
  PATCH /api/v1/admin/users/{user_id}/verify     Manually verify a user (ADMIN+)

Zero business logic. Zero DB queries.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import controller as ctrl
from app.admin.schemas import (
    AdminBanUserRequest,
    AdminCreateUserRequest,
    AdminUserListResponse,
    AdminUserResponse,
)
from app.auth.constants import UserRole, VerificationStatus
from app.auth.dependencies import require_admin, require_super_admin
from app.database import get_db
from shared.models.user import CurrentUser

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.post(
    "/create",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Super Admin] Create a new admin account",
    description=(
        "Creates a user with the admin role. "
        "Requires SUPER_ADMIN privileges. "
        "The account is created with email_verified=True."
    ),
)
async def create_admin_user(
    body: AdminCreateUserRequest,
    admin: CurrentUser = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    return await ctrl.create_admin_user(session, body)


@router.get(
    "",
    response_model=AdminUserListResponse,
    summary="[Admin] List all users with filters and pagination",
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: UserRole | None = Query(None, description="Filter by professional role"),
    verification_status: VerificationStatus | None = Query(
        None, description="Filter by verification status"
    ),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, max_length=200, description="Search by name or email"),
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    return await ctrl.list_users(
        session,
        page=page,
        size=size,
        role=role,
        verification_status=verification_status,
        is_active=is_active,
        search=search,
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserResponse,
    summary="[Admin] Get a single user's full details",
)
async def get_user_detail(
    user_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    return await ctrl.get_user_detail(session, user_id)


@router.patch(
    "/{user_id}/ban",
    response_model=AdminUserResponse,
    summary="[Admin] Ban a user — revokes access and invalidates sessions",
    description=(
        "Sets is_banned=True and is_active=False. "
        "All active sessions are deleted immediately."
    ),
)
async def ban_user(
    user_id: uuid.UUID,
    body: AdminBanUserRequest,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    return await ctrl.ban_user(session, user_id, body)


@router.patch(
    "/{user_id}/unban",
    response_model=AdminUserResponse,
    summary="[Admin] Unban a user — restores access",
    description="Sets is_banned=False and is_active=True. Clears the ban reason.",
)
async def unban_user(
    user_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    return await ctrl.unban_user(session, user_id)


@router.patch(
    "/{user_id}/verify",
    response_model=AdminUserResponse,
    summary="[Admin] Manually verify a user without a document",
    description=(
        "Sets verification_status=VERIFIED and content_creation_mode=True. "
        "Raises 409 if the user is already verified."
    ),
)
async def manual_verify_user(
    user_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    return await ctrl.manual_verify_user(session, user_id)
