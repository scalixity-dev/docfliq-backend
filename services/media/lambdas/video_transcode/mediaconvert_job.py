"""
AWS MediaConvert job creation — produces HLS (720p + 1080p + 4K) + MP4 download.

HLS output structure:
  processed/video/{user_id}/{timestamp}/hls/
    ├── master.m3u8       (master playlist)
    ├── 720p/stream.m3u8  (variant playlist)
    ├── 1080p/stream.m3u8
    └── 4k/stream.m3u8

MP4 output:
  processed/video/{user_id}/{timestamp}/mp4/download.mp4

Thumbnail:
  processed/video/{user_id}/{timestamp}/thumb/thumb.0000000.jpg
"""
from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger(__name__)

MEDIACONVERT_ENDPOINT = os.environ.get("MEDIACONVERT_ENDPOINT", "")
MEDIACONVERT_ROLE_ARN = os.environ.get("MEDIACONVERT_ROLE_ARN", "")
MEDIACONVERT_QUEUE_ARN = os.environ.get("MEDIACONVERT_QUEUE_ARN", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


def _get_client():
    """Get MediaConvert client using the account-specific endpoint."""
    if MEDIACONVERT_ENDPOINT:
        return boto3.client(
            "mediaconvert",
            region_name=AWS_REGION,
            endpoint_url=MEDIACONVERT_ENDPOINT,
        )
    # Auto-discover endpoint
    mc = boto3.client("mediaconvert", region_name=AWS_REGION)
    endpoints = mc.describe_endpoints()
    endpoint_url = endpoints["Endpoints"][0]["Url"]
    return boto3.client(
        "mediaconvert",
        region_name=AWS_REGION,
        endpoint_url=endpoint_url,
    )


def create_transcode_job(
    *,
    input_bucket: str,
    input_key: str,
    output_bucket: str,
    output_prefix: str,
) -> str:
    """Submit an AWS MediaConvert job. Returns the job ID."""
    client = _get_client()
    input_uri = f"s3://{input_bucket}/{input_key}"
    output_base = f"s3://{output_bucket}/{output_prefix}"

    job_settings = {
        "Role": MEDIACONVERT_ROLE_ARN,
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
                # HLS output group
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
                # MP4 download
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
                # Thumbnail
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

    if MEDIACONVERT_QUEUE_ARN:
        job_settings["Queue"] = MEDIACONVERT_QUEUE_ARN

    response = client.create_job(**job_settings)
    job_id = response["Job"]["Id"]
    logger.info("MediaConvert job created: %s", job_id)
    return job_id


def _hls_output(
    name: str,
    width: int,
    height: int,
    bitrate: int,
) -> dict:
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
