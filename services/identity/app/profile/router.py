"""
Profile domain — router.

Routes:
  GET    /api/v1/users/me          Get own full profile
  PATCH  /api/v1/users/me          Update own profile (partial)
  GET    /api/v1/users/{user_id}   Get any user's public profile

All routes require a valid Bearer token.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.profile import controller as ctrl
from app.profile.schemas import ProfileResponse, UpdateProfileRequest
from shared.models.user import CurrentUser

router = APIRouter(prefix="/users", tags=["profile"])


@router.get("/me", response_model=ProfileResponse, summary="Get own profile")
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    return await ctrl.get_me(session, current_user.id)


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update own profile (partial — only provided fields are written)",
)
async def update_me(
    body: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    return await ctrl.update_me(session, current_user.id, body)


@router.get(
    "/{user_id}",
    response_model=ProfileResponse,
    summary="Get any user's public profile",
)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    return await ctrl.get_user(session, user_id, viewer_id=current_user.id)
