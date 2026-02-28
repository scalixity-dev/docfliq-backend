"""
AWS S3 utilities — async presigned URL generation for verification documents.

PUT URL:  user uploads directly to S3 (15-min expiry, bypasses backend).
GET URL:  admin views the document inline (30-min expiry).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.exceptions import FileTooLarge, S3ObjectNotFound, S3PresignError

logger = logging.getLogger(__name__)

# Maximum allowed verification document size: 10 MB
MAX_DOCUMENT_SIZE_BYTES: int = 10 * 1024 * 1024  # 10,485,760 bytes


def _doc_key(user_id: uuid.UUID, document_type: str) -> str:
    """Build a unique, human-readable S3 key for a verification document."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"verification/{user_id}/{ts}_{uid}_{document_type}"


def _s3_session(settings: Settings) -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


async def generate_presigned_put_url(
    user_id: uuid.UUID,
    document_type: str,
    content_type: str,
    settings: Settings,
) -> tuple[str, str]:
    """Return (presigned_put_url, s3_key).  Store s3_key as document_url in DB."""
    if not settings.aws_access_key_id:
        raise S3PresignError()
    key = _doc_key(user_id, document_type)
    try:
        async with _s3_session(settings).client("s3") as s3:
            url: str = await s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=settings.s3_presigned_expiry_seconds,
            )
    except (BotoCoreError, ClientError):
        raise S3PresignError()
    return url, key


async def generate_presigned_get_url(
    s3_key: str,
    settings: Settings,
    expiry_seconds: int = 1800,
) -> str:
    """Return a presigned GET URL so admins can view the uploaded document."""
    if not settings.aws_access_key_id:
        raise S3PresignError()
    try:
        async with _s3_session(settings).client("s3") as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket, "Key": s3_key},
                ExpiresIn=expiry_seconds,
            )
    except (BotoCoreError, ClientError):
        raise S3PresignError()
    return url


async def get_object_size(s3_key: str, settings: Settings) -> int:
    """Return the size in bytes of an S3 object via HeadObject.

    Raises:
        S3ObjectNotFound: key does not exist in the bucket (user hasn't uploaded yet).
        S3PresignError:   any other S3/network failure.
    """
    if not settings.aws_access_key_id:
        raise S3PresignError()
    try:
        async with _s3_session(settings).client("s3") as s3:
            response = await s3.head_object(Bucket=settings.s3_bucket, Key=s3_key)
            return int(response["ContentLength"])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            raise S3ObjectNotFound()
        raise S3PresignError()
    except BotoCoreError:
        raise S3PresignError()


async def delete_object(s3_key: str, settings: Settings) -> None:
    """Delete an S3 object. Best-effort — logs on failure but never raises.

    Called after a file-size or format rejection to clean up the orphaned upload.
    """
    if not settings.aws_access_key_id:
        return
    try:
        async with _s3_session(settings).client("s3") as s3:
            await s3.delete_object(Bucket=settings.s3_bucket, Key=s3_key)
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 delete_object failed for key %s: %s", s3_key, exc)


async def check_document_size(s3_key: str, settings: Settings) -> None:
    """Check the uploaded document size. Raises FileTooLarge if > MAX_DOCUMENT_SIZE_BYTES.

    Also cleans up the oversized file from S3 before raising.
    """
    size = await get_object_size(s3_key, settings)
    if size > MAX_DOCUMENT_SIZE_BYTES:
        await delete_object(s3_key, settings)
        raise FileTooLarge()
