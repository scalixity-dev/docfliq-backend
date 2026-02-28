"""
AWS Lambda handler — MediaConvert Job Status Change callback.

Triggered by CloudWatch Events / EventBridge rule:
  source: "aws.mediaconvert"
  detail-type: "MediaConvert Job State Change"

When MediaConvert finishes (COMPLETE or ERROR), this Lambda:
  1. Extracts the job ID and status.
  2. Gathers output URLs (HLS manifest, MP4, thumbnail).
  3. Calls the media service callback endpoint.
"""
from __future__ import annotations

import logging
import os

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CALLBACK_URL = os.environ.get(
    "CALLBACK_URL",
    "http://localhost:8005/api/v1/internal/media/callback/transcode",
)
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "docfliq-user-content-dev")
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN", "")


def handler(event: dict, context: object) -> dict:
    """Process MediaConvert job completion event."""
    detail = event.get("detail", {})
    job_id = detail.get("jobId", "")
    mc_status = detail.get("status", "")

    logger.info("MediaConvert event: job=%s status=%s", job_id, mc_status)

    if mc_status == "COMPLETE":
        output_group_details = detail.get("outputGroupDetails", [])
        urls = _extract_output_urls(output_group_details)
        duration = _get_duration(detail)
        resolution = _get_resolution(detail)

        _send_callback(
            job_id=job_id,
            status="COMPLETED",
            processed_url=urls.get("mp4"),
            hls_url=urls.get("hls"),
            thumbnail_url=urls.get("thumbnail"),
            duration_secs=duration,
            resolution=resolution,
        )

    elif mc_status == "ERROR":
        error_msg = detail.get("errorMessage", "Unknown transcoding error")
        _send_callback(
            job_id=job_id,
            status="FAILED",
            error_message=error_msg,
        )

    return {"statusCode": 200, "jobId": job_id, "status": mc_status}


def _extract_output_urls(output_group_details: list) -> dict:
    """Extract HLS, MP4, and thumbnail URLs from MediaConvert output."""
    urls: dict[str, str] = {}

    for group in output_group_details:
        group_type = group.get("type", "")
        output_details = group.get("outputDetails", [])

        for detail in output_details:
            output_path = detail.get("outputFilePaths", [""])[0]
            if not output_path:
                continue

            # Convert S3 path to CloudFront URL if domain is configured
            url = _to_cdn_url(output_path) if CLOUDFRONT_DOMAIN else output_path

            if group_type == "HLS_GROUP" and "hls" not in urls:
                # The first HLS output path; derive the master manifest URL
                # MediaConvert puts the master manifest at the group destination
                hls_base = output_path.rsplit("/", 1)[0]
                urls["hls"] = _to_cdn_url(hls_base + "/master.m3u8")
            elif group_type == "FILE_GROUP":
                if "mp4" in output_path.lower() or "download" in output_path.lower():
                    urls["mp4"] = url
                elif "thumb" in output_path.lower():
                    urls["thumbnail"] = url

    return urls


def _to_cdn_url(s3_path: str) -> str:
    """Convert s3://bucket/key to https://cdn.domain/key."""
    if not CLOUDFRONT_DOMAIN:
        return s3_path
    # Remove s3://bucket/ prefix
    parts = s3_path.replace("s3://", "").split("/", 1)
    if len(parts) < 2:
        return s3_path
    key = parts[1]
    return f"https://{CLOUDFRONT_DOMAIN}/{key}"


def _get_duration(detail: dict) -> int | None:
    """Extract video duration in seconds from job detail."""
    try:
        input_details = detail.get("inputDetails", [{}])
        duration_ms = input_details[0].get("durationInMs", 0)
        return int(duration_ms / 1000) if duration_ms else None
    except (IndexError, TypeError):
        return None


def _get_resolution(detail: dict) -> str | None:
    """Detect the highest resolution output."""
    try:
        output_groups = detail.get("outputGroupDetails", [])
        for group in output_groups:
            for output in group.get("outputDetails", []):
                video = output.get("videoDetails", {})
                height = video.get("heightInPx", 0)
                if height >= 2160:
                    return "4K"
                if height >= 1080:
                    return "1080p"
                if height >= 720:
                    return "720p"
        return None
    except (TypeError, KeyError):
        return None


def _send_callback(**kwargs) -> None:
    """Send processing result to media service."""
    try:
        resp = requests.post(CALLBACK_URL, json=kwargs, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Callback failed: %s", exc)
