"""
Verification domain — admin-facing routes.

Routes:
  GET   /api/v1/admin/verification/queue                     FIFO list of PENDING docs
  GET   /api/v1/admin/verification/{doc_id}/document         Presigned GET URL (30 min)
  PATCH /api/v1/admin/verification/{doc_id}/review           Approve or reject
  PATCH /api/v1/admin/verification/users/{user_id}/suspend   Suspend a user
  PATCH /api/v1/admin/verification/users/{user_id}/reinstate Reinstate a suspended user

Requires: ADMIN or SUPER_ADMIN role.
"""
from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.config import Settings
from app.database import get_db
from app.verification import controller as ctrl
from app.verification.schemas import (
    DocumentViewResponse,
    ReviewRequest,
    ReviewResponse,
    SuspendRequest,
    UserStatusResponse,
    VerificationQueueResponse,
)
from shared.models.user import CurrentUser

router = APIRouter(prefix="/admin/verification", tags=["admin-verification"])


@lru_cache
def _get_settings() -> Settings:
    return Settings()


@router.get(
    "/queue",
    response_model=VerificationQueueResponse,
    summary="[Admin] List PENDING verification documents (FIFO order)",
)
async def get_queue(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> VerificationQueueResponse:
    return await ctrl.get_queue(session, page, size)


@router.get(
    "/{doc_id}/document",
    response_model=DocumentViewResponse,
    summary="[Admin] Get a 30-min presigned URL to view the uploaded document",
)
async def view_document(
    doc_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> DocumentViewResponse:
    return await ctrl.view_document(session, doc_id, settings)


@router.patch(
    "/{doc_id}/review",
    response_model=ReviewResponse,
    summary="[Admin] Approve or reject a verification document",
    description=(
        "action=APPROVE: user status → VERIFIED, content_creation_mode=True. "
        "action=REJECT: user status → REJECTED, can re-upload. "
        "Approval is idempotent (no-op if already APPROVED)."
    ),
)
async def review(
    doc_id: uuid.UUID,
    body: ReviewRequest,
    background_tasks: BackgroundTasks,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> ReviewResponse:
    return await ctrl.review_doc(session, doc_id, admin.id, body, settings, background_tasks)


@router.patch(
    "/users/{user_id}/suspend",
    response_model=UserStatusResponse,
    summary="[Admin] Suspend a user — revokes all access and invalidates active sessions",
    description=(
        "Sets verification_status=SUSPENDED and immediately deletes all active "
        "refresh-token sessions so the user cannot continue any existing login. "
        "The user is notified by email. Raises 409 if already suspended."
    ),
)
async def suspend_user(
    user_id: uuid.UUID,
    body: SuspendRequest,
    background_tasks: BackgroundTasks,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> UserStatusResponse:
    return await ctrl.suspend_user(session, user_id, body, settings, background_tasks)


@router.patch(
    "/users/{user_id}/reinstate",
    response_model=UserStatusResponse,
    summary="[Admin] Reinstate a suspended user back to VERIFIED",
    description=(
        "Sets verification_status=VERIFIED for a currently SUSPENDED user. "
        "Clears the stored suspension reason. Raises 409 if the user is not suspended."
    ),
)
async def reinstate_user(
    user_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> UserStatusResponse:
    return await ctrl.reinstate_user(session, user_id)
