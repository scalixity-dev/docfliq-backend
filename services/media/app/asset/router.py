"""
Media asset — HTTP routes.

All user-facing endpoints require JWT auth (Bearer token from MS-1).
Lambda callback endpoints use an internal API key for authentication.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.asset import controller
from app.asset.dependencies import get_current_user_required
from app.asset.schemas import (
    AssetListResponse,
    AssetResponse,
    ConfirmUploadRequest,
    ImageProcessCallbackRequest,
    MessageResponse,
    SignedUrlResponse,
    TranscodeCallbackRequest,
    UploadRequest,
    UploadResponse,
)
from app.config import Settings
from app.database import get_db
from shared.models.user import CurrentUser

router = APIRouter(prefix="/media", tags=["media"])
callback_router = APIRouter(prefix="/internal/media", tags=["internal"])


def _get_settings() -> Settings:
    return Settings()


# ── Upload flow ──────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a presigned upload URL",
    description=(
        "Generates a presigned S3 PUT URL for direct file upload. "
        "Creates a pending MediaAsset record. After uploading the file "
        "to the returned URL, call POST /media/upload/confirm."
    ),
)
async def request_upload(
    request: UploadRequest,
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> UploadResponse:
    return await controller.request_upload(request, user, db, settings)


@router.post(
    "/upload/confirm",
    response_model=AssetResponse,
    summary="Confirm file upload",
    description=(
        "Confirms that the file has been uploaded to S3. Validates existence "
        "and size, then marks the asset for processing."
    ),
)
async def confirm_upload(
    request: ConfirmUploadRequest,
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> AssetResponse:
    return await controller.confirm_upload(request, user, db, settings)


# ── Asset CRUD ───────────────────────────────────────────────────────────────

@router.get(
    "/assets",
    response_model=AssetListResponse,
    summary="List my assets",
    description="Returns paginated list of the authenticated user's media assets.",
)
async def list_assets(
    asset_type: str | None = Query(
        default=None, description="Filter by type: VIDEO, IMAGE, PDF, SCORM",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    return await controller.list_assets(
        user, db, asset_type=asset_type, page=page, page_size=page_size,
    )


@router.get(
    "/assets/{asset_id}",
    response_model=AssetResponse,
    summary="Get asset details",
)
async def get_asset(
    asset_id: str,
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    return await controller.get_asset(asset_id, user, db)


@router.delete(
    "/assets/{asset_id}",
    response_model=MessageResponse,
    summary="Delete an asset",
)
async def delete_asset(
    asset_id: str,
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await controller.delete_asset(asset_id, user, db)


# ── Signed URL ───────────────────────────────────────────────────────────────

@router.get(
    "/assets/{asset_id}/url",
    response_model=SignedUrlResponse,
    summary="Get signed download URL",
    description="Returns a time-limited presigned URL for accessing the asset.",
)
async def get_signed_url(
    asset_id: str,
    expiry: int = Query(default=3600, ge=300, le=28800, description="URL expiry in seconds"),
    user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> SignedUrlResponse:
    return await controller.get_signed_url(
        asset_id, user, db, settings, expiry_seconds=expiry,
    )


# ── Lambda callbacks (internal) ─────────────────────────────────────────────

@callback_router.post(
    "/callback/transcode",
    response_model=MessageResponse,
    summary="Video transcode callback",
    description="Called by the video transcode Lambda when a job completes or fails.",
)
async def transcode_callback(
    request: TranscodeCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await controller.transcode_callback(request, db)


@callback_router.post(
    "/callback/image",
    response_model=MessageResponse,
    summary="Image processing callback",
    description="Called by the image processing Lambda when processing completes.",
)
async def image_process_callback(
    request: ImageProcessCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    return await controller.image_process_callback(request, db)
