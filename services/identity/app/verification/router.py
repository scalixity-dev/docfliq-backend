"""
Verification domain — user-facing routes.

Routes:
  POST /api/v1/users/me/verify/upload    Request presigned S3 PUT URL
  POST /api/v1/users/me/verify/confirm   Confirm upload → submit for admin review

Requires: valid Bearer token (any role).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import Settings
from app.database import get_db
from app.verification import controller as ctrl
from app.verification.schemas import (
    ConfirmRequest,
    UploadRequest,
    UploadResponse,
    VerificationSubmittedResponse,
)
from shared.models.user import CurrentUser

router = APIRouter(prefix="/users/me/verify", tags=["verification"])


def _get_settings() -> Settings:
    return Settings()


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Get a presigned S3 URL to upload a verification document",
    description=(
        "Returns a presigned PUT URL (15-min expiry). "
        "Upload the file directly to that URL, then call /confirm with the document_key."
    ),
)
async def upload(
    body: UploadRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> UploadResponse:
    return await ctrl.request_upload(session, current_user.id, body, settings)


@router.post(
    "/confirm",
    response_model=VerificationSubmittedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm the S3 upload and submit the document for admin review",
    description=(
        "Creates a PENDING verification record. "
        "User status advances to PENDING. Confirmation email sent via Brevo."
    ),
)
async def confirm(
    body: ConfirmRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> VerificationSubmittedResponse:
    return await ctrl.confirm_upload(session, current_user.id, body, settings, background_tasks)
