"""
Profile domain — request orchestration (thin glue between router and service).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import UserHiddenByBlock
from app.profile.schemas import ProfileResponse, UpdateProfileRequest
from app.profile.service import get_profile, update_profile
from app.social_graph import service as social_svc


async def get_me(session: AsyncSession, user_id: uuid.UUID) -> ProfileResponse:
    user = await get_profile(session, user_id)
    return ProfileResponse.model_validate(user)


async def get_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    viewer_id: uuid.UUID,
) -> ProfileResponse:
    # Block check: if the target user has blocked the viewer, return 404 to avoid
    # leaking block status (same response as user-not-found).
    if await social_svc.is_blocked_by(session, blocked_id=viewer_id, blocker_id=user_id):
        raise UserHiddenByBlock()
    user = await get_profile(session, user_id)
    return ProfileResponse.model_validate(user)


async def update_me(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: UpdateProfileRequest,
) -> ProfileResponse:
    fields = body.model_dump(exclude_unset=True)
    user = await update_profile(session, user_id, fields)
    return ProfileResponse.model_validate(user)
