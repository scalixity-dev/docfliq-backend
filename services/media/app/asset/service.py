"""
Media asset — pure business logic.

Zero FastAPI imports. Receives data objects and session via parameters.
Fully testable in isolation.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.asset.constants import AssetType, TranscodeStatus
from app.asset.models import MediaAsset


async def create_asset(
    db: AsyncSession,
    *,
    uploaded_by: uuid.UUID,
    asset_type: AssetType,
    original_url: str,
    original_filename: str | None = None,
    content_type: str | None = None,
    file_size_bytes: int | None = None,
) -> MediaAsset:
    """Create a new media asset record in PENDING state."""
    asset = MediaAsset(
        uploaded_by=uploaded_by,
        asset_type=asset_type,
        original_url=original_url,
        original_filename=original_filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        transcode_status=TranscodeStatus.PENDING,
    )
    db.add(asset)
    await db.flush()
    return asset


async def get_asset_by_id(
    db: AsyncSession,
    asset_id: uuid.UUID,
) -> MediaAsset | None:
    """Fetch a single asset by its primary key."""
    result = await db.execute(
        select(MediaAsset).where(MediaAsset.asset_id == asset_id)
    )
    return result.scalar_one_or_none()


async def get_assets_by_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    asset_type: AssetType | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MediaAsset], int]:
    """Fetch paginated assets for a user, optionally filtered by type."""
    base = select(MediaAsset).where(MediaAsset.uploaded_by == user_id)
    count_base = select(func.count()).select_from(MediaAsset).where(
        MediaAsset.uploaded_by == user_id
    )

    if asset_type is not None:
        base = base.where(MediaAsset.asset_type == asset_type)
        count_base = count_base.where(MediaAsset.asset_type == asset_type)

    # Total count
    total = (await db.execute(count_base)).scalar() or 0

    # Paginated results
    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(MediaAsset.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return items, total


async def update_transcode_status(
    db: AsyncSession,
    asset_id: uuid.UUID,
    *,
    status: TranscodeStatus,
    mediaconvert_job_id: str | None = None,
    processed_url: str | None = None,
    hls_url: str | None = None,
    thumbnail_url: str | None = None,
    duration_secs: int | None = None,
    resolution: str | None = None,
    error_message: str | None = None,
) -> MediaAsset | None:
    """Update transcoding status and processed output URLs."""
    asset = await get_asset_by_id(db, asset_id)
    if asset is None:
        return None

    asset.transcode_status = status
    if mediaconvert_job_id is not None:
        asset.mediaconvert_job_id = mediaconvert_job_id
    if processed_url is not None:
        asset.processed_url = processed_url
    if hls_url is not None:
        asset.hls_url = hls_url
    if thumbnail_url is not None:
        asset.thumbnail_url = thumbnail_url
    if duration_secs is not None:
        asset.duration_secs = duration_secs
    if resolution is not None:
        asset.resolution = resolution
    if error_message is not None:
        asset.transcode_error = error_message

    await db.flush()
    return asset


async def update_asset_by_job_id(
    db: AsyncSession,
    mediaconvert_job_id: str,
    *,
    status: TranscodeStatus,
    processed_url: str | None = None,
    hls_url: str | None = None,
    thumbnail_url: str | None = None,
    duration_secs: int | None = None,
    resolution: str | None = None,
    error_message: str | None = None,
) -> MediaAsset | None:
    """Update asset by MediaConvert job ID (used by Lambda callbacks)."""
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.mediaconvert_job_id == mediaconvert_job_id
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        return None

    asset.transcode_status = status
    if processed_url is not None:
        asset.processed_url = processed_url
    if hls_url is not None:
        asset.hls_url = hls_url
    if thumbnail_url is not None:
        asset.thumbnail_url = thumbnail_url
    if duration_secs is not None:
        asset.duration_secs = duration_secs
    if resolution is not None:
        asset.resolution = resolution
    if error_message is not None:
        asset.transcode_error = error_message

    await db.flush()
    return asset


async def confirm_upload(
    db: AsyncSession,
    asset_id: uuid.UUID,
    file_size_bytes: int,
) -> MediaAsset | None:
    """Mark an asset's upload as confirmed and set file size."""
    asset = await get_asset_by_id(db, asset_id)
    if asset is None:
        return None

    asset.file_size_bytes = file_size_bytes
    # For images, processing is fast — mark as PROCESSING
    # For videos, Lambda will pick it up and set PROCESSING
    if asset.asset_type == AssetType.IMAGE:
        asset.transcode_status = TranscodeStatus.PROCESSING
    elif asset.asset_type in (AssetType.PDF, AssetType.SCORM):
        # PDFs and SCORM packages don't need transcoding
        asset.transcode_status = TranscodeStatus.COMPLETED

    await db.flush()
    return asset


async def delete_asset(
    db: AsyncSession,
    asset_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Delete an asset owned by the user. Returns True if deleted."""
    asset = await get_asset_by_id(db, asset_id)
    if asset is None or asset.uploaded_by != user_id:
        return False
    await db.delete(asset)
    await db.flush()
    return True
