"""
Media asset — controller layer.

Receives validated input from router, calls service functions, composes
the response. Thin glue layer between HTTP and business logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.asset import service
from app.asset.constants import TranscodeStatus
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
    """Confirm a file has been uploaded to S3. Validates file exists and size."""
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


async def transcode_callback(
    request: TranscodeCallbackRequest,
    db: AsyncSession,
) -> MessageResponse:
    """Handle callback from video transcode Lambda."""
    asset = await service.update_asset_by_job_id(
        db,
        request.mediaconvert_job_id,
        status=request.status,
        processed_url=request.processed_url,
        hls_url=request.hls_url,
        thumbnail_url=request.thumbnail_url,
        duration_secs=request.duration_secs,
        resolution=request.resolution,
        error_message=request.error_message,
    )
    if asset is None:
        logger.warning(
            "Transcode callback for unknown job: %s", request.mediaconvert_job_id
        )
    return MessageResponse(message="Callback processed.")


async def image_process_callback(
    request: ImageProcessCallbackRequest,
    db: AsyncSession,
) -> MessageResponse:
    """Handle callback from image processing Lambda."""
    asset = await service.update_transcode_status(
        db,
        request.asset_id,
        status=request.status,
        processed_url=request.processed_url,
        thumbnail_url=request.thumbnail_url,
        error_message=request.error_message,
    )
    if asset is not None and request.file_size_bytes is not None:
        asset.file_size_bytes = request.file_size_bytes
        await db.flush()

    return MessageResponse(message="Callback processed.")
