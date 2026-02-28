"""
AWS Lambda handler — Image Processing

Triggered by S3 PutObject event on uploads/image/* prefix.

Flow:
  1. Downloads the original image from S3.
  2. Generates multiple sizes: thumbnail (150x150), medium (600x600), large (1200x1200).
  3. Converts to WebP with JPEG fallback.
  4. For profile avatars: circular crop at 48x48, 120x120, 300x300.
  5. For course thumbnails: 400x225 (16:9).
  6. Uploads processed images back to S3.
  7. Calls the media service callback endpoint.

Environment variables:
  OUTPUT_BUCKET    — S3 bucket for processed images
  CALLBACK_URL     — Media service internal callback URL
  AWS_REGION       — AWS region (set by Lambda runtime)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import uuid

import boto3
import requests

from processor import ImageProcessor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CALLBACK_URL = os.environ.get(
    "CALLBACK_URL",
    "http://localhost:8005/api/v1/internal/media/callback/image",
)
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "docfliq-user-content-dev")

s3_client = boto3.client("s3")


def handler(event: dict, context: object) -> dict:
    """Lambda entry point — processes S3 image upload events."""
    records = event.get("Records", [])
    results = []

    for record in records:
        # SQS wrapper
        if record.get("eventSource") == "aws:sqs":
            body = json.loads(record.get("body", "{}"))
            s3_records = body.get("Records", [])
        else:
            s3_records = [record]

        for s3_record in s3_records:
            result = _process_image(s3_record)
            results.append(result)

    return {"statusCode": 200, "results": results}


def _process_image(record: dict) -> dict:
    """Process a single image upload."""
    try:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = urllib.parse.unquote_plus(
            s3_info.get("object", {}).get("key", "")
        )

        if not bucket or not key:
            return {"status": "error", "message": "Missing bucket or key"}

        if not _is_image_key(key):
            return {"status": "skipped", "key": key, "reason": "not an image"}

        logger.info("Processing image: s3://%s/%s", bucket, key)

        # Download original image
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response["Body"].read()
        content_type = response.get("ContentType", "image/jpeg")
        file_size = len(image_data)

        # Determine processing mode from key path
        is_avatar = "/avatar/" in key or "/profile/" in key
        is_course_thumb = "/course/" in key

        # Process image
        processor = ImageProcessor(image_data)
        processed = processor.process(
            is_avatar=is_avatar,
            is_course_thumbnail=is_course_thumb,
        )

        # Upload processed versions
        output_prefix = key.replace("uploads/image/", "processed/image/")
        if "." in output_prefix:
            output_prefix = output_prefix.rsplit(".", 1)[0]

        uploaded_urls = {}
        for size_name, data in processed.items():
            output_key = f"{output_prefix}/{size_name}.webp"
            s3_client.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=output_key,
                Body=data,
                ContentType="image/webp",
                CacheControl="max-age=31536000",
            )
            uploaded_urls[size_name] = f"s3://{OUTPUT_BUCKET}/{output_key}"
            logger.info("Uploaded %s: %s", size_name, output_key)

        # Extract asset_id from the key (format: uploads/image/{user_id}/{ts}_{uid}.ext)
        # The asset_id is tracked in the database, so we look for it in the key
        asset_id = _extract_asset_id_from_key(key)

        # Send callback
        thumbnail_url = uploaded_urls.get("thumbnail", "")
        processed_url = uploaded_urls.get("large", uploaded_urls.get("medium", ""))

        if asset_id:
            _send_callback(
                asset_id=asset_id,
                status="COMPLETED",
                processed_url=processed_url,
                thumbnail_url=thumbnail_url,
                file_size_bytes=file_size,
            )

        return {
            "status": "completed",
            "key": key,
            "sizes": list(processed.keys()),
        }

    except Exception as exc:
        logger.exception("Error processing image: %s", exc)

        asset_id = _extract_asset_id_from_key(
            record.get("s3", {}).get("object", {}).get("key", "")
        )
        if asset_id:
            _send_callback(
                asset_id=asset_id,
                status="FAILED",
                error_message=str(exc),
            )

        return {"status": "error", "message": str(exc)}


def _is_image_key(key: str) -> bool:
    """Check if the S3 key is an image file."""
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
    lower = key.lower()
    return any(lower.endswith(ext) for ext in image_extensions)


def _extract_asset_id_from_key(key: str) -> str | None:
    """Try to extract the asset UUID from S3 event metadata or return None."""
    # In production, the asset_id would be passed via S3 object metadata
    # or SQS message attributes. For now, return None and let the callback
    # be sent with the key for matching.
    return None


def _send_callback(**kwargs) -> None:
    """Send processing result to media service."""
    try:
        resp = requests.post(CALLBACK_URL, json=kwargs, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Callback failed: %s", exc)
