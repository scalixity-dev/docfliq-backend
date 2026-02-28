"""
Media asset — controller layer.

Receives validated input from router, calls service functions, composes
the response. Thin glue layer between HTTP and business logic.

Media processing (image resize, video transcode) is offloaded to ARQ
worker processes via Redis queue — the API never blocks on heavy work.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.asset import service
from app.asset.constants import AssetType, TranscodeStatus
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
from app.exceptions import (
    AssetNotFound,
    S3ObjectNotFound,
    UnsupportedContentType,
    UploadFileTooLarge,
)
from app.s3 import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZES,
    generate_presigned_get_url,
    generate_presigned_put_url,
    get_object_metadata,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from shared.models.user import CurrentUser

logger = logging.getLogger(__name__)


async def request_upload(
    request: UploadRequest,
    user: CurrentUser,
    db: AsyncSession,
    settings: Settings,
) -> UploadResponse:
    """Generate a presigned PUT URL and create a pending MediaAsset record."""
    asset_type = request.asset_type.value

    # Validate content type
    allowed = ALLOWED_CONTENT_TYPES.get(asset_type, set())
    if request.content_type not in allowed:
        raise UnsupportedContentType(request.content_type)

    # Generate presigned PUT URL
    upload_url, s3_key = await generate_presigned_put_url(
        user_id=user.id,
        asset_type=asset_type,
        content_type=request.content_type,
        original_filename=request.original_filename,
        settings=settings,
    )

    # Create pending asset record
    full_s3_url = f"s3://{settings.s3_bucket_media}/{s3_key}"
    asset = await service.create_asset(
        db,
        uploaded_by=user.id,
        asset_type=request.asset_type,
        original_url=full_s3_url,
        original_filename=request.original_filename,
        content_type=request.content_type,
    )

    return UploadResponse(
        asset_id=asset.asset_id,
        upload_url=upload_url,
        s3_key=s3_key,
        expires_in=settings.s3_upload_expiry_seconds,
    )


async def confirm_upload(
    request: ConfirmUploadRequest,
    user: CurrentUser,
    db: AsyncSession,
    settings: Settings,
) -> AssetResponse:
    """Confirm a file has been uploaded to S3. Validates file exists and size.

    Enqueues processing to the ARQ worker queue (Redis). The API returns
    immediately — workers handle image/video processing independently.
    """
    from app import task_queue

    asset = await service.get_asset_by_id(db, request.asset_id)
    if asset is None or asset.uploaded_by != user.id:
        raise AssetNotFound()

    # Extract S3 key from the stored URL
    s3_key = asset.original_url.replace(f"s3://{settings.s3_bucket_media}/", "")

    # Verify the file exists in S3 and get its size
    try:
        metadata = await get_object_metadata(s3_key, settings)
    except S3ObjectNotFound:
        raise S3ObjectNotFound()

    file_size = metadata["content_length"]
    max_size = MAX_FILE_SIZES.get(asset.asset_type.value, 100 * 1024 * 1024)
    if file_size > max_size:
        raise UploadFileTooLarge(max_size // (1024 * 1024))

    # Update asset with file size and mark upload confirmed
    asset = await service.confirm_upload(db, asset.asset_id, file_size)
    if asset is None:
        raise AssetNotFound()

    # Enqueue processing to worker queue (near-instant Redis LPUSH)
    asset_id_str = str(asset.asset_id)
    if asset.asset_type == AssetType.IMAGE:
        await task_queue.enqueue("process_image", asset_id_str, s3_key)
    elif asset.asset_type == AssetType.VIDEO:
        await task_queue.enqueue("process_video", asset_id_str, s3_key)

    return AssetResponse.model_validate(asset)


async def get_asset(
    asset_id: str,
    user: CurrentUser,
    db: AsyncSession,
) -> AssetResponse:
    """Get a single asset by ID. Only the owner can view it."""
    import uuid
    uid = uuid.UUID(asset_id)
    asset = await service.get_asset_by_id(db, uid)
    if asset is None or asset.uploaded_by != user.id:
        raise AssetNotFound()
    return AssetResponse.model_validate(asset)


async def list_assets(
    user: CurrentUser,
    db: AsyncSession,
    *,
    asset_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> AssetListResponse:
    """List assets for the authenticated user with pagination."""
    from app.asset.constants import AssetType

    at = AssetType(asset_type) if asset_type else None
    items, total = await service.get_assets_by_user(
        db, user.id, asset_type=at, page=page, page_size=page_size,
    )
    return AssetListResponse(
        items=[AssetResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_signed_url(
    asset_id: str,
    user: CurrentUser,
    db: AsyncSession,
    settings: Settings,
    *,
    expiry_seconds: int = 3600,
) -> SignedUrlResponse:
    """Generate a presigned GET URL for an asset."""
    import uuid
    uid = uuid.UUID(asset_id)
    asset = await service.get_asset_by_id(db, uid)
    if asset is None or asset.uploaded_by != user.id:
        raise AssetNotFound()

    s3_key = asset.original_url.replace(f"s3://{settings.s3_bucket_media}/", "")
    url = await generate_presigned_get_url(s3_key, settings, expiry_seconds)
    return SignedUrlResponse(url=url, expires_in=expiry_seconds)


async def delete_asset(
    asset_id: str,
    user: CurrentUser,
    db: AsyncSession,
) -> MessageResponse:
    """Delete an asset. Only the owner can delete."""
    import uuid
    uid = uuid.UUID(asset_id)
    deleted = await service.delete_asset(db, uid, user.id)
    if not deleted:
        raise AssetNotFound()
    return MessageResponse(message="Asset deleted successfully.")


async def get_playback_info(
    asset_id: str,
    db: AsyncSession,
    settings: Settings,
) -> PlaybackInfoResponse:
    """Get video playback metadata (public, no auth).

    Converts internal s3:// URLs to public stream-proxy / serve URLs.
    """
    uid = uuid.UUID(asset_id)
    asset = await service.get_asset_by_id(db, uid)
    if asset is None:
        raise AssetNotFound()

    bucket_prefix = f"s3://{settings.s3_bucket_media}/"

    hls_url = None
    if asset.hls_url and asset.transcode_status == TranscodeStatus.COMPLETED:
        hls_s3_key = asset.hls_url.replace(bucket_prefix, "")
        hls_url = f"/media/stream/{hls_s3_key}"

    thumbnail_url = None
    if asset.thumbnail_url:
        thumb_key = asset.thumbnail_url.replace(bucket_prefix, "")
        thumbnail_url = f"/media/serve/{thumb_key}"

    original_url = None
    if asset.original_url:
        orig_key = asset.original_url.replace(bucket_prefix, "")
        original_url = f"/media/serve/{orig_key}"

    return PlaybackInfoResponse(
        asset_id=asset.asset_id,
        transcode_status=asset.transcode_status,
        hls_url=hls_url,
        thumbnail_url=thumbnail_url,
        original_url=original_url,
        duration_secs=getattr(asset, "duration_secs", None),
        resolution=getattr(asset, "resolution", None),
    )


