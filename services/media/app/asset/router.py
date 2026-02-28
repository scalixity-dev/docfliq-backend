"""
Media asset — HTTP routes.

All user-facing endpoints require JWT auth (Bearer token from MS-1).
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.asset import controller
from app.asset.dependencies import get_current_user_required
from app.asset.schemas import (
    AssetListResponse,
    AssetResponse,
    ConfirmUploadRequest,
    MessageResponse,
    PlaybackInfoResponse,
    SignedUrlResponse,
    UploadRequest,
    UploadResponse,
)
from app.config import Settings
from app.database import get_db
from app.s3 import download_object, generate_presigned_get_url
from shared.models.user import CurrentUser

router = APIRouter(prefix="/media", tags=["media"])


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


# ── Public file serving (no auth — used by <img> tags) ─────────────────────

@router.get(
    "/serve/{s3_key:path}",
    summary="Serve a file via presigned redirect",
    description=(
        "Public endpoint (no auth). Generates a short-lived presigned GET URL "
        "for the given S3 key and redirects to it. Used as a permanent URL "
        "for profile images, banners, thumbnails, etc."
    ),
    tags=["media"],
    response_class=RedirectResponse,
)
async def serve_file(
    s3_key: str,
    settings: Settings = Depends(_get_settings),
) -> RedirectResponse:
    url = await generate_presigned_get_url(s3_key, settings, expiry_seconds=3600)
    return RedirectResponse(url=url, status_code=302)


# ── HLS stream proxy (no auth — used by video player) ────────────────────

_STREAM_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/MP2T",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
}


@router.get(
    "/stream/{s3_key:path}",
    summary="Stream a file via proxy (no redirect)",
    description=(
        "Public endpoint (no auth). Downloads the S3 object and returns "
        "the content directly. Required for HLS playback because .m3u8 "
        "playlists reference segments by relative paths."
    ),
    tags=["media"],
)
async def stream_file(
    s3_key: str,
    settings: Settings = Depends(_get_settings),
) -> Response:
    data = await download_object(s3_key, settings)

    # Determine content type from extension
    ext = ""
    if "." in s3_key:
        ext = "." + s3_key.rsplit(".", 1)[1].lower()
    content_type = _STREAM_CONTENT_TYPES.get(ext, "application/octet-stream")

    # Manifests: no-cache (may update). Segments: cache aggressively (immutable).
    cache = "no-cache" if ext == ".m3u8" else "public, max-age=3600"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=content_type,
        headers={"Cache-Control": cache},
    )


# ── Public playback info (no auth — used by video player) ────────────────

@router.get(
    "/playback/{asset_id}",
    response_model=PlaybackInfoResponse,
    summary="Get video playback info (public, no auth)",
    description=(
        "Returns current HLS URL, thumbnail URL, and transcode status. "
        "Used by the video player to check if adaptive streaming is available."
    ),
    tags=["media"],
)
async def get_playback_info(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> PlaybackInfoResponse:
    return await controller.get_playback_info(asset_id, db, settings)
