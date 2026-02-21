"""
AWS S3 utilities — presigned URL generation for media uploads and downloads.

Upload flow:
  1. Client requests a presigned PUT URL from the API.
  2. Client uploads the file directly to S3 using the presigned URL.
  3. S3 PutObject event triggers the appropriate Lambda for processing.
  4. Lambda updates the MediaAsset record via the callback endpoint.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.exceptions import S3PresignError, S3ObjectNotFound

logger = logging.getLogger(__name__)

# S3 key prefixes by asset type
_KEY_PREFIXES = {
    "VIDEO": "uploads/video",
    "IMAGE": "uploads/image",
    "PDF": "uploads/pdf",
    "SCORM": "uploads/scorm",
}

# Allowed MIME types per asset type
ALLOWED_CONTENT_TYPES: dict[str, set[str]] = {
    "VIDEO": {
        "video/mp4", "video/quicktime", "video/x-msvideo",
        "video/webm", "video/x-matroska",
    },
    "IMAGE": {
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "image/svg+xml",
    },
    "PDF": {"application/pdf"},
    "SCORM": {"application/zip", "application/x-zip-compressed"},
}

# Max file sizes per asset type (bytes)
MAX_FILE_SIZES: dict[str, int] = {
    "VIDEO": 2 * 1024 * 1024 * 1024,  # 2 GB
    "IMAGE": 20 * 1024 * 1024,         # 20 MB
    "PDF": 100 * 1024 * 1024,          # 100 MB
    "SCORM": 500 * 1024 * 1024,        # 500 MB
}


def _media_key(asset_type: str, user_id: uuid.UUID, original_filename: str) -> str:
    """Build a unique S3 key for a media upload."""
    prefix = _KEY_PREFIXES.get(asset_type, "uploads/other")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    # Sanitize filename: keep extension
    ext = ""
    if "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()
    return f"{prefix}/{user_id}/{ts}_{uid}{ext}"


def _s3_session(settings: Settings) -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


async def generate_presigned_put_url(
    user_id: uuid.UUID,
    asset_type: str,
    content_type: str,
    original_filename: str,
    settings: Settings,
) -> tuple[str, str]:
    """Return (presigned_put_url, s3_key)."""
    if not settings.aws_access_key_id:
        raise S3PresignError()

    key = _media_key(asset_type, user_id, original_filename)
    try:
        async with _s3_session(settings).client("s3") as s3:
            url: str = await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.s3_bucket_media,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=settings.s3_upload_expiry_seconds,
            )
    except (BotoCoreError, ClientError):
        raise S3PresignError()
    return url, key


async def generate_presigned_get_url(
    s3_key: str,
    settings: Settings,
    expiry_seconds: int = 3600,
) -> str:
    """Return a presigned GET URL for direct S3 access."""
    if not settings.aws_access_key_id:
        raise S3PresignError()
    try:
        async with _s3_session(settings).client("s3") as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket_media, "Key": s3_key},
                ExpiresIn=expiry_seconds,
            )
    except (BotoCoreError, ClientError):
        raise S3PresignError()
    return url


async def get_object_metadata(s3_key: str, settings: Settings) -> dict:
    """Return S3 object metadata (ContentLength, ContentType, etc.)."""
    if not settings.aws_access_key_id:
        raise S3PresignError()
    try:
        async with _s3_session(settings).client("s3") as s3:
            response = await s3.head_object(
                Bucket=settings.s3_bucket_media, Key=s3_key,
            )
            return {
                "content_length": int(response["ContentLength"]),
                "content_type": response.get("ContentType", ""),
                "last_modified": response.get("LastModified"),
            }
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            raise S3ObjectNotFound()
        raise S3PresignError()
    except BotoCoreError:
        raise S3PresignError()


async def delete_object(s3_key: str, settings: Settings) -> None:
    """Delete an S3 object. Best-effort — logs on failure but never raises."""
    if not settings.aws_access_key_id:
        return
    try:
        async with _s3_session(settings).client("s3") as s3:
            await s3.delete_object(Bucket=settings.s3_bucket_media, Key=s3_key)
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 delete_object failed for key %s: %s", s3_key, exc)
