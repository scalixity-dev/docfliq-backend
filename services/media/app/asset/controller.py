"""
Media asset — controller layer.

Receives validated input from router, calls service functions, composes
the response. Thin glue layer between HTTP and business logic.
"""
from __future__ import annotations

import asyncio
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
    download_object,
    generate_presigned_get_url,
    generate_presigned_put_url,
    get_object_metadata,
    upload_object,
)

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
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
    background_tasks: BackgroundTasks,
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

    # Schedule background image processing (images only)
    if asset.asset_type == AssetType.IMAGE:
        background_tasks.add_task(
            _process_image_background, asset.asset_id, s3_key, settings,
        )

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


async def _process_image_background(
    asset_id: uuid.UUID,
    s3_key: str,
    settings: Settings,
) -> None:
    """
    Background task: download image from S3, process with Pillow, upload
    processed variants, and update DB status.

    Uses its own DB session (request session is closed by the time this runs).
    """
    from app.database import get_session_factory

    try:
        # 1. Download original image
        image_data = await download_object(s3_key, settings)

        # 2. Process with Pillow (CPU-bound → offload to thread)
        loop = asyncio.get_running_loop()
        variants = await loop.run_in_executor(
            None, lambda: service.process_image_sync(image_data),
        )

        # 3. Upload each processed variant to S3
        processed_url = None
        thumbnail_url = None
        for size_name, webp_bytes in variants.items():
            out_key = service.build_processed_key(s3_key, size_name)
            s3_url = await upload_object(out_key, webp_bytes, "image/webp", settings)
            if size_name == "large":
                processed_url = s3_url
            elif size_name == "thumbnail":
                thumbnail_url = s3_url

        # 4. Update DB status
        factory = get_session_factory()
        async with factory() as session:
            await service.update_transcode_status(
                session,
                asset_id,
                status=TranscodeStatus.COMPLETED,
                processed_url=processed_url,
                thumbnail_url=thumbnail_url,
            )
            await session.commit()

        logger.info("Image processing completed for asset %s", asset_id)

    except Exception:
        logger.exception("Image processing failed for asset %s", asset_id)
        try:
            factory = get_session_factory()
            async with factory() as session:
                await service.update_transcode_status(
                    session,
                    asset_id,
                    status=TranscodeStatus.FAILED,
                    error_message="In-service image processing failed",
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to update error status for asset %s", asset_id)
