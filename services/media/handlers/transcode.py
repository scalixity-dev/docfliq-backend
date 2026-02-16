"""Lambda handler for media transcoding. Stub: accepts S3-style event, returns status dict."""


def handler(event: dict, context: object) -> dict:
    """Process transcoding event (e.g. S3 object created). Stub implementation."""
    bucket = event.get("bucket") or event.get("Records", [{}])[0].get("s3", {}).get("bucket", {}).get("name", "")
    key = event.get("key") or event.get("Records", [{}])[0].get("s3", {}).get("object", {}).get("key", "")
    return {
        "status": "ok",
        "service": "media",
        "handler": "transcode",
        "bucket": bucket,
        "key": key,
    }
