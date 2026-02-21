"""
AWS Lambda handler — Video Transcoding

Triggered by:
  1. S3 PutObject event (user uploads a video)
  2. SQS message (webinar.recording_raw event)

Flow:
  1. Receives S3 event with bucket/key of uploaded video.
  2. Submits an AWS MediaConvert job for HLS transcoding (720p + 1080p + 4K).
  3. Calls the media service callback endpoint when the job completes.

Environment variables:
  MEDIACONVERT_ENDPOINT   — MediaConvert API endpoint for the region
  MEDIACONVERT_ROLE_ARN   — IAM role ARN for MediaConvert to access S3
  MEDIACONVERT_QUEUE_ARN  — MediaConvert queue ARN
  OUTPUT_BUCKET           — S3 bucket for transcoded output
  CALLBACK_URL            — Media service internal callback URL
  AWS_REGION              — AWS region (set by Lambda runtime)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse

import boto3
import requests

from mediaconvert_job import create_transcode_job

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CALLBACK_URL = os.environ.get("CALLBACK_URL", "http://localhost:8005/api/v1/internal/media/callback/transcode")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "docfliq-user-content-dev")


def handler(event: dict, context: object) -> dict:
    """Lambda entry point — processes S3 or SQS events."""
    records = event.get("Records", [])
    results = []

    for record in records:
        # SQS wrapper: unwrap the S3 event from the SQS message body
        if record.get("eventSource") == "aws:sqs":
            body = json.loads(record.get("body", "{}"))
            s3_records = body.get("Records", [])
        else:
            s3_records = [record]

        for s3_record in s3_records:
            result = _process_s3_record(s3_record)
            results.append(result)

    return {"statusCode": 200, "results": results}


def _process_s3_record(record: dict) -> dict:
    """Process a single S3 PutObject event record."""
    try:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = urllib.parse.unquote_plus(
            s3_info.get("object", {}).get("key", "")
        )

        if not bucket or not key:
            logger.error("Missing bucket or key in S3 event: %s", record)
            return {"status": "error", "message": "Missing bucket or key"}

        # Only process video files
        if not _is_video_key(key):
            logger.info("Skipping non-video file: %s", key)
            return {"status": "skipped", "key": key, "reason": "not a video"}

        logger.info("Processing video: s3://%s/%s", bucket, key)

        # Derive output path
        output_prefix = key.replace("uploads/video/", "processed/video/")
        if "." in output_prefix:
            output_prefix = output_prefix.rsplit(".", 1)[0]

        # Submit MediaConvert job
        job_id = create_transcode_job(
            input_bucket=bucket,
            input_key=key,
            output_bucket=OUTPUT_BUCKET,
            output_prefix=output_prefix,
        )

        logger.info("MediaConvert job submitted: %s", job_id)

        # Notify the media service about the job
        _send_callback(
            job_id=job_id,
            status="PROCESSING",
        )

        return {"status": "submitted", "key": key, "job_id": job_id}

    except Exception as exc:
        logger.exception("Error processing S3 record: %s", exc)
        return {"status": "error", "message": str(exc)}


def _is_video_key(key: str) -> bool:
    """Check if the S3 key looks like a video file."""
    video_extensions = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"}
    lower = key.lower()
    return any(lower.endswith(ext) for ext in video_extensions)


def _send_callback(
    *,
    job_id: str,
    status: str,
    processed_url: str | None = None,
    hls_url: str | None = None,
    thumbnail_url: str | None = None,
    duration_secs: int | None = None,
    resolution: str | None = None,
    error_message: str | None = None,
) -> None:
    """Send a callback to the media service API."""
    payload = {
        "mediaconvert_job_id": job_id,
        "status": status,
    }
    if processed_url:
        payload["processed_url"] = processed_url
    if hls_url:
        payload["hls_url"] = hls_url
    if thumbnail_url:
        payload["thumbnail_url"] = thumbnail_url
    if duration_secs is not None:
        payload["duration_secs"] = duration_secs
    if resolution:
        payload["resolution"] = resolution
    if error_message:
        payload["error_message"] = error_message

    try:
        resp = requests.post(CALLBACK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Callback sent successfully for job %s", job_id)
    except Exception as exc:
        logger.error("Failed to send callback for job %s: %s", job_id, exc)
