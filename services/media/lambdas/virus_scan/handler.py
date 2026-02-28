"""
AWS Lambda handler — Virus Scanning (ClamAV)

Triggered by S3 PutObject events on all upload prefixes.
Runs BEFORE processing Lambdas via S3 event ordering or Step Functions.

Flow:
  1. Downloads the uploaded file from S3.
  2. Scans with ClamAV (using clamd socket or subprocess).
  3. If INFECTED: delete the file, tag the object, log the event.
  4. If CLEAN: tag the object as scanned, allow processing to proceed.

Environment variables:
  CLAM_AV_PATH        — Path to clamscan binary (default: /opt/bin/clamscan)
  CLAM_AV_DB_PATH     — Path to ClamAV database (default: /opt/share/clamav)
  MAX_SCAN_SIZE_MB     — Maximum file size to scan (default: 500)
  QUARANTINE_BUCKET    — Bucket for quarantined infected files (optional)

Deployment note:
  ClamAV binaries must be packaged as a Lambda Layer. Use the
  `clamav-lambda-layer` open-source project or build from source.
  Database definitions should be bundled or fetched from S3 on cold start.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import urllib.parse

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

CLAM_AV_PATH = os.environ.get("CLAM_AV_PATH", "/opt/bin/clamscan")
CLAM_AV_DB_PATH = os.environ.get("CLAM_AV_DB_PATH", "/opt/share/clamav")
MAX_SCAN_SIZE_MB = int(os.environ.get("MAX_SCAN_SIZE_MB", "500"))
QUARANTINE_BUCKET = os.environ.get("QUARANTINE_BUCKET", "")


def handler(event: dict, context: object) -> dict:
    """Lambda entry point — scans uploaded files for malware."""
    records = event.get("Records", [])
    results = []

    for record in records:
        if record.get("eventSource") == "aws:sqs":
            body = json.loads(record.get("body", "{}"))
            s3_records = body.get("Records", [])
        else:
            s3_records = [record]

        for s3_record in s3_records:
            result = _scan_file(s3_record)
            results.append(result)

    return {"statusCode": 200, "results": results}


def _scan_file(record: dict) -> dict:
    """Download and scan a single file."""
    try:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = urllib.parse.unquote_plus(
            s3_info.get("object", {}).get("key", "")
        )
        file_size = s3_info.get("object", {}).get("size", 0)

        if not bucket or not key:
            return {"status": "error", "message": "Missing bucket or key"}

        # Skip files that are too large for scanning
        max_size = MAX_SCAN_SIZE_MB * 1024 * 1024
        if file_size > max_size:
            logger.warning(
                "File too large for scanning (%d bytes): %s", file_size, key
            )
            _tag_object(bucket, key, "SKIPPED_TOO_LARGE")
            return {"status": "skipped", "key": key, "reason": "too large"}

        # Skip already-processed files
        if key.startswith("processed/"):
            return {"status": "skipped", "key": key, "reason": "processed file"}

        logger.info("Scanning: s3://%s/%s (%d bytes)", bucket, key, file_size)

        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=True, suffix="_scan") as tmp:
            s3_client.download_file(bucket, key, tmp.name)

            # Run ClamAV scan
            is_infected, scan_output = _run_clamscan(tmp.name)

        if is_infected:
            logger.warning("INFECTED: s3://%s/%s — %s", bucket, key, scan_output)
            _handle_infected(bucket, key)
            return {"status": "infected", "key": key, "details": scan_output}

        logger.info("CLEAN: s3://%s/%s", bucket, key)
        _tag_object(bucket, key, "CLEAN")
        return {"status": "clean", "key": key}

    except FileNotFoundError:
        logger.error("ClamAV binary not found at %s", CLAM_AV_PATH)
        return {"status": "error", "message": "ClamAV not available"}
    except Exception as exc:
        logger.exception("Scan error: %s", exc)
        return {"status": "error", "message": str(exc)}


def _run_clamscan(file_path: str) -> tuple[bool, str]:
    """Run ClamAV scan on a file. Returns (is_infected, output)."""
    try:
        result = subprocess.run(
            [
                CLAM_AV_PATH,
                f"--database={CLAM_AV_DB_PATH}",
                "--no-summary",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        # ClamAV exit codes: 0=clean, 1=infected, 2=error
        is_infected = result.returncode == 1
        output = result.stdout.strip() or result.stderr.strip()
        return is_infected, output
    except subprocess.TimeoutExpired:
        return False, "Scan timed out"


def _handle_infected(bucket: str, key: str) -> None:
    """Handle an infected file: quarantine or delete."""
    if QUARANTINE_BUCKET:
        # Move to quarantine bucket
        try:
            s3_client.copy_object(
                Bucket=QUARANTINE_BUCKET,
                Key=f"quarantine/{key}",
                CopySource={"Bucket": bucket, "Key": key},
            )
            logger.info("Quarantined: %s → %s", key, QUARANTINE_BUCKET)
        except Exception as exc:
            logger.error("Quarantine copy failed: %s", exc)

    # Delete the infected file from the upload bucket
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        logger.info("Deleted infected file: s3://%s/%s", bucket, key)
    except Exception as exc:
        logger.error("Failed to delete infected file: %s", exc)


def _tag_object(bucket: str, key: str, scan_result: str) -> None:
    """Tag the S3 object with its scan result."""
    try:
        s3_client.put_object_tagging(
            Bucket=bucket,
            Key=key,
            Tagging={
                "TagSet": [
                    {"Key": "av-scan", "Value": scan_result},
                ]
            },
        )
    except Exception as exc:
        logger.error("Failed to tag object %s: %s", key, exc)
