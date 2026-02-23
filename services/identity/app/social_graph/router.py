"""
Social graph domain — user-facing routes.

All routes prefixed /api/v1/users (same prefix as profile router — different
sub-paths; no conflict because path patterns don't overlap).

Routes:
  POST   /{user_id}/follow         Follow a user  (50/hour rate limit)
  DELETE /{user_id}/follow         Unfollow
  POST   /{user_id}/block          Block (auto-removes follow edges both ways)
  DELETE /{user_id}/block          Unblock
  POST   /{user_id}/mute           Mute
  DELETE /{user_id}/mute           Unmute
  POST   /{user_id}/report         Report a user/content
  GET    /me/suggestions           Suggested users to follow
  GET    /me/following             Who I follow (paginated)
  GET    /me/followers             Who follows me (paginated)
  GET    /me/blocked               My block list (paginated)
  GET    /me/muted                 My mute list (paginated)
  GET    /{user_id}/following      View user's following (404 if they blocked me)
  GET    /{user_id}/followers      View user's followers (404 if they blocked me)

Note: /me/... routes must be registered before /{user_id}/... routes of the same
shape so Starlette's literal-path matching takes precedence.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.rate_limit import limiter
from app.social_graph import controller as ctrl
from app.social_graph.schemas import (
    FollowListResponse,
    ReportRequest,
    ReportResponse,
    SocialRelationListResponse,
    SuggestionListResponse,
)
from shared.models.user import CurrentUser

router = APIRouter(prefix="/users", tags=["social-graph"])


# ── Follow ─────────────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/follow",
    status_code=status.HTTP_200_OK,
    summary="Follow a user",
    description="Rate-limited to 50 follow actions per hour.",
)
@limiter.limit("50/hour")
async def follow_user(
    request: Request,
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await ctrl.follow_user(session, current_user.id, user_id)


@router.delete(
    "/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unfollow a user",
)
async def unfollow_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await ctrl.unfollow_user(session, current_user.id, user_id)


# ── Block ──────────────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/block",
    status_code=status.HTTP_200_OK,
    summary="Block a user",
    description="Automatically removes follow edges in both directions.",
)
async def block_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await ctrl.block_user(session, current_user.id, user_id)


@router.delete(
    "/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock a user",
)
async def unblock_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await ctrl.unblock_user(session, current_user.id, user_id)


# ── Mute ───────────────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/mute",
    status_code=status.HTTP_200_OK,
    summary="Mute a user",
    description="Muted user's content is hidden from your feed. Independent of follow/block.",
)
async def mute_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await ctrl.mute_user(session, current_user.id, user_id)


@router.delete(
    "/{user_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unmute a user",
)
async def unmute_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await ctrl.unmute_user(session, current_user.id, user_id)


# ── Report ─────────────────────────────────────────────────────────────────────

@router.post(
    "/{user_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a user or their content",
    description=(
        "The path user_id provides context (whose content is being reported). "
        "The body carries the exact target (target_type + target_id) and reason."
    ),
)
async def report_user(
    user_id: uuid.UUID,  # noqa: ARG001 — kept for URL semantics / future audit
    body: ReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReportResponse:
    return await ctrl.report_user(session, current_user.id, body)


# ── My lists (must be registered before /{user_id}/... to avoid mis-routing) ──

@router.get(
    "/me/suggestions",
    response_model=SuggestionListResponse,
    summary="Suggest users to follow",
    description="Returns users the current user does not follow (excludes blocked users and self).",
)
async def my_suggestions(
    size: int = Query(10, ge=1, le=50, description="Number of suggestions"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SuggestionListResponse:
    return await ctrl.list_suggestions(session, current_user.id, size=size)


@router.get(
    "/me/following",
    response_model=FollowListResponse,
    summary="List users I follow",
)
async def my_following(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FollowListResponse:
    return await ctrl.list_following(
        session, current_user.id, viewer_id=current_user.id, page=page, size=size
    )


@router.get(
    "/me/followers",
    response_model=FollowListResponse,
    summary="List users who follow me",
)
async def my_followers(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FollowListResponse:
    return await ctrl.list_followers(
        session, current_user.id, viewer_id=current_user.id, page=page, size=size
    )


@router.get(
    "/me/blocked",
    response_model=SocialRelationListResponse,
    summary="List users I have blocked",
)
async def my_blocked(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SocialRelationListResponse:
    return await ctrl.list_blocked(session, current_user.id, page=page, size=size)


@router.get(
    "/me/muted",
    response_model=SocialRelationListResponse,
    summary="List users I have muted",
)
async def my_muted(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SocialRelationListResponse:
    return await ctrl.list_muted(session, current_user.id, page=page, size=size)


# ── Another user's lists ───────────────────────────────────────────────────────

@router.get(
    "/{user_id}/following",
    response_model=FollowListResponse,
    summary="View another user's following list",
    description="Returns 404 if the target user has blocked you.",
)
async def user_following(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FollowListResponse:
    return await ctrl.view_user_following(
        session, user_id, viewer_id=current_user.id, page=page, size=size
    )


@router.get(
    "/{user_id}/followers",
    response_model=FollowListResponse,
    summary="View another user's followers list",
    description="Returns 404 if the target user has blocked you.",
)
async def user_followers(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FollowListResponse:
    return await ctrl.view_user_followers(
        session, user_id, viewer_id=current_user.id, page=page, size=size
    )
