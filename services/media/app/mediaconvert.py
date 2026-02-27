"""
AWS MediaConvert — async job submission and polling.

Adapted from lambdas/video_transcode/mediaconvert_job.py to use aioboto3.
Produces HLS (720p + 1080p + 4K) + MP4 download + thumbnail.

Output structure in S3:
  processed/video/{user_id}/{timestamp}/hls/master.m3u8   (HLS master playlist)
  processed/video/{user_id}/{timestamp}/mp4/download.mp4  (MP4 download)
  processed/video/{user_id}/{timestamp}/thumb/thumb.0000000.jpg  (thumbnail)
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

# Poll interval and timeout for job completion
_POLL_INTERVAL_SECS = 15
_POLL_TIMEOUT_SECS = 40 * 60  # 40 minutes max


def _build_output_prefix(input_key: str) -> str:
    """Derive the output prefix from the input S3 key.

    Input:  uploads/video/{user_id}/20260226_abc12345.mp4
    Output: processed/video/{user_id}/20260226_abc12345
    """
    prefix = input_key.replace("uploads/video/", "processed/video/")
    if "." in prefix:
        prefix = prefix.rsplit(".", 1)[0]
    return prefix


def _hls_output(name: str, width: int, height: int, bitrate: int) -> dict:
    """Build an HLS output configuration for a specific resolution."""
    return {
        "ContainerSettings": {
            "Container": "M3U8",
            "M3u8Settings": {},
        },
        "VideoDescription": {
            "Width": width,
            "Height": height,
            "CodecSettings": {
                "Codec": "H_264",
                "H264Settings": {
                    "RateControlMode": "CBR",
                    "Bitrate": bitrate,
                    "GopSize": 2,
                    "GopSizeUnits": "SECONDS",
                },
            },
        },
        "AudioDescriptions": [
            {
                "CodecSettings": {
                    "Codec": "AAC",
                    "AacSettings": {
                        "Bitrate": 128000,
                        "CodingMode": "CODING_MODE_2_0",
                        "SampleRate": 48000,
                    },
                },
            }
        ],
        "NameModifier": name,
    }


def _build_job_settings(
    *,
    input_uri: str,
    output_base: str,
    role_arn: str,
    queue_arn: str,
) -> dict:
    """Build the full MediaConvert job settings JSON."""
    settings: dict = {
        "Role": role_arn,
        "Settings": {
            "TimecodeConfig": {"Source": "ZEROBASED"},
            "Inputs": [
                {
                    "FileInput": input_uri,
                    "AudioSelectors": {
                        "Audio Selector 1": {"DefaultSelection": "DEFAULT"},
                    },
                    "VideoSelector": {},
                    "TimecodeSource": "ZEROBASED",
                }
            ],
            "OutputGroups": [
                # HLS output group (720p + 1080p + 4K)
                {
                    "Name": "HLS",
                    "OutputGroupSettings": {
                        "Type": "HLS_GROUP_SETTINGS",
                        "HlsGroupSettings": {
                            "Destination": f"{output_base}/hls/",
                            "SegmentLength": 6,
                            "MinSegmentLength": 0,
                        },
                    },
                    "Outputs": [
                        _hls_output("720p", 1280, 720, 3_500_000),
                        _hls_output("1080p", 1920, 1080, 6_000_000),
                        _hls_output("4k", 3840, 2160, 15_000_000),
                    ],
                },
                # MP4 download copy
                {
                    "Name": "MP4",
                    "OutputGroupSettings": {
                        "Type": "FILE_GROUP_SETTINGS",
                        "FileGroupSettings": {
                            "Destination": f"{output_base}/mp4/",
                        },
                    },
                    "Outputs": [
                        {
                            "ContainerSettings": {
                                "Container": "MP4",
                                "Mp4Settings": {},
                            },
                            "VideoDescription": {
                                "CodecSettings": {
                                    "Codec": "H_264",
                                    "H264Settings": {
                                        "RateControlMode": "QVBR",
                                        "QvbrSettings": {"QvbrQualityLevel": 7},
                                        "MaxBitrate": 6_000_000,
                                    },
                                },
                            },
                            "AudioDescriptions": [
                                {
                                    "CodecSettings": {
                                        "Codec": "AAC",
                                        "AacSettings": {
                                            "Bitrate": 128000,
                                            "CodingMode": "CODING_MODE_2_0",
                                            "SampleRate": 48000,
                                        },
                                    },
                                }
                            ],
                            "NameModifier": "download",
                        }
                    ],
                },
                # Thumbnail (single frame capture)
                {
                    "Name": "Thumbnails",
                    "OutputGroupSettings": {
                        "Type": "FILE_GROUP_SETTINGS",
                        "FileGroupSettings": {
                            "Destination": f"{output_base}/thumb/",
                        },
                    },
                    "Outputs": [
                        {
                            "ContainerSettings": {"Container": "RAW"},
                            "VideoDescription": {
                                "CodecSettings": {
                                    "Codec": "FRAME_CAPTURE",
                                    "FrameCaptureSettings": {
                                        "FramerateNumerator": 1,
                                        "FramerateDenominator": 5,
                                        "MaxCaptures": 1,
                                        "Quality": 80,
                                    },
                                },
                                "Width": 640,
                                "Height": 360,
                            },
                            "NameModifier": "thumb",
                        }
                    ],
                },
            ],
        },
    }
    if queue_arn:
        settings["Queue"] = queue_arn
    return settings


def _mc_session(settings: Settings) -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


async def submit_transcode_job(input_key: str, settings: Settings) -> str:
    """Submit a MediaConvert transcoding job. Returns the job ID."""
    bucket = settings.s3_bucket_media
    output_bucket = settings.mediaconvert_output_bucket or bucket
    output_prefix = _build_output_prefix(input_key)

    input_uri = f"s3://{bucket}/{input_key}"
    output_base = f"s3://{output_bucket}/{output_prefix}"

    job_params = _build_job_settings(
        input_uri=input_uri,
        output_base=output_base,
        role_arn=settings.mediaconvert_role_arn,
        queue_arn=settings.mediaconvert_queue_arn,
    )

    endpoint_url = settings.mediaconvert_endpoint or None
    session = _mc_session(settings)

    async with session.client("mediaconvert", endpoint_url=endpoint_url) as mc:
        if not endpoint_url:
            # Auto-discover the account-specific endpoint
            resp = await mc.describe_endpoints()
            endpoint_url = resp["Endpoints"][0]["Url"]
            # Re-create client with the discovered endpoint
            async with session.client("mediaconvert", endpoint_url=endpoint_url) as mc2:
                response = await mc2.create_job(**job_params)
        else:
            response = await mc.create_job(**job_params)

    job_id = response["Job"]["Id"]
    logger.info("MediaConvert job submitted: %s for key %s", job_id, input_key)
    return job_id


async def poll_job_until_done(job_id: str, settings: Settings) -> dict:
    """Poll a MediaConvert job until it completes or fails.

    Returns a dict with: status, hls_url, processed_url, thumbnail_url,
    duration_secs, resolution, error_message.
    """
    endpoint_url = settings.mediaconvert_endpoint or None
    session = _mc_session(settings)
    elapsed = 0

    async with session.client("mediaconvert", endpoint_url=endpoint_url) as mc:
        if not endpoint_url:
            resp = await mc.describe_endpoints()
            endpoint_url = resp["Endpoints"][0]["Url"]

    # Poll loop with the correct endpoint
    while elapsed < _POLL_TIMEOUT_SECS:
        await asyncio.sleep(_POLL_INTERVAL_SECS)
        elapsed += _POLL_INTERVAL_SECS

        try:
            async with session.client("mediaconvert", endpoint_url=endpoint_url) as mc:
                resp = await mc.get_job(Id=job_id)
            job = resp["Job"]
            status = job["Status"]

            if status == "COMPLETE":
                return _extract_completed_result(job, settings)
            if status == "ERROR":
                error_msg = job.get("ErrorMessage", "Unknown transcoding error")
                logger.error("MediaConvert job %s failed: %s", job_id, error_msg)
                return {"status": "FAILED", "error_message": error_msg}

            logger.debug("Job %s status: %s (%ds elapsed)", job_id, status, elapsed)

        except (BotoCoreError, ClientError) as exc:
            logger.warning("Error polling job %s: %s", job_id, exc)

    # Timed out
    return {
        "status": "FAILED",
        "error_message": f"Transcoding timed out after {_POLL_TIMEOUT_SECS}s",
    }


def _extract_completed_result(job: dict, settings: Settings) -> dict:
    """Extract output URLs, duration, and resolution from a completed job."""
    bucket = settings.mediaconvert_output_bucket or settings.s3_bucket_media
    result: dict = {"status": "COMPLETED"}

    # Extract output group details
    output_groups = job.get("Settings", {}).get("OutputGroups", [])
    for group in output_groups:
        group_name = group.get("Name", "")
        group_settings = group.get("OutputGroupSettings", {})

        if group_name == "HLS":
            dest = group_settings.get("HlsGroupSettings", {}).get("Destination", "")
            if dest:
                result["hls_url"] = f"{dest}master.m3u8"

        elif group_name == "MP4":
            dest = group_settings.get("FileGroupSettings", {}).get("Destination", "")
            if dest:
                result["processed_url"] = f"{dest}download.mp4"

        elif group_name == "Thumbnails":
            dest = group_settings.get("FileGroupSettings", {}).get("Destination", "")
            if dest:
                result["thumbnail_url"] = f"{dest}thumb.0000000.jpg"

    # Duration from input details
    try:
        timing = job.get("Timing", {})
        # MediaConvert doesn't directly give duration in job response;
        # we can estimate from output details if available
        output_details = job.get("OutputGroupDetails", [])
        for group in output_details:
            for output in group.get("outputDetails", []):
                duration_ms = output.get("durationInMs", 0)
                if duration_ms:
                    result["duration_secs"] = int(duration_ms / 1000)
                    break
            if "duration_secs" in result:
                break
    except (TypeError, KeyError):
        pass

    # Resolution — check the highest output
    for group in output_groups:
        for output in group.get("Outputs", []):
            video = output.get("VideoDescription", {})
            height = video.get("Height", 0)
            if height >= 2160:
                result["resolution"] = "4K"
            elif height >= 1080 and result.get("resolution") != "4K":
                result["resolution"] = "1080p"
            elif height >= 720 and "resolution" not in result:
                result["resolution"] = "720p"

    # Default resolution to the highest we requested
    if "resolution" not in result:
        result["resolution"] = "4K"

    return result
