"""
Profile domain — request orchestration (thin glue between router and service).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.profile.schemas import ProfileResponse, UpdateProfileRequest
from app.profile.service import get_profile, get_profile_for_viewer, update_profile


async def get_me(session: AsyncSession, user_id: uuid.UUID) -> ProfileResponse:
    user = await get_profile(session, user_id)
    return ProfileResponse.model_validate(user)


async def get_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    viewer_id: uuid.UUID,
) -> ProfileResponse:
    # Single query: load user + block check (raises 404 if blocked or not found)
    user = await get_profile_for_viewer(session, user_id, viewer_id)
    return ProfileResponse.model_validate(user)


async def update_me(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: UpdateProfileRequest,
) -> ProfileResponse:
    fields = body.model_dump(exclude_unset=True)
    user = await update_profile(session, user_id, fields)
    return ProfileResponse.model_validate(user)
