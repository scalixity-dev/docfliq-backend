"""
Profile domain — request orchestration (thin glue between router and service).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import UserHiddenByBlock
from app.profile.schemas import ProfileResponse, UpdateProfileRequest, UserSearchItem, UserSearchResponse
from app.profile.service import get_profile, search_users, update_profile
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


async def search(
    session: AsyncSession,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> UserSearchResponse:
    users, total = await search_users(session, query, limit=limit, offset=offset)
    return UserSearchResponse(
        items=[UserSearchItem.model_validate(u) for u in users],
        total=total,
        query=query,
        limit=limit,
        offset=offset,
    )


async def update_me(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: UpdateProfileRequest,
) -> ProfileResponse:
    fields = body.model_dump(exclude_unset=True)
    user = await update_profile(session, user_id, fields)
    return ProfileResponse.model_validate(user)
