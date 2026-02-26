"""
Media asset — Pydantic V2 request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.asset.constants import AssetType, TranscodeStatus


# ── Base ─────────────────────────────────────────────────────────────────────

class _Base(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


# ── Requests ─────────────────────────────────────────────────────────────────

class UploadRequest(_Base):
    """Request a presigned PUT URL for uploading a media file."""
    asset_type: AssetType = Field(description="Type of media: VIDEO, IMAGE, PDF, SCORM")
    content_type: str = Field(
        min_length=3,
        max_length=100,
        description="MIME type of the file (e.g. video/mp4, image/jpeg)",
    )
    original_filename: str = Field(
        min_length=1,
        max_length=255,
        description="Original filename with extension",
    )


class ConfirmUploadRequest(_Base):
    """Confirm that a file has been uploaded to the presigned URL."""
    asset_id: uuid.UUID = Field(description="Asset ID returned from the upload request")


# ── Responses ────────────────────────────────────────────────────────────────

class UploadResponse(_Base):
    """Returned when a presigned PUT URL is generated."""
    asset_id: uuid.UUID
    upload_url: str
    s3_key: str
    expires_in: int = Field(description="URL expiry in seconds")


class AssetResponse(_Base):
    """Full media asset details."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        from_attributes=True,
    )

    asset_id: uuid.UUID
    uploaded_by: uuid.UUID
    asset_type: AssetType
    original_url: str
    original_filename: str | None = None
    content_type: str | None = None
    processed_url: str | None = None
    thumbnail_url: str | None = None
    hls_url: str | None = None
    file_size_bytes: int | None = None
    duration_secs: int | None = None
    resolution: str | None = None
    transcode_status: TranscodeStatus
    mediaconvert_job_id: str | None = None
    transcode_error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AssetListResponse(_Base):
    """Paginated list of media assets."""
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


class SignedUrlResponse(_Base):
    """Returned when a signed URL is generated for content access."""
    url: str
    expires_in: int = Field(description="URL expiry in seconds")


class MessageResponse(_Base):
    message: str
