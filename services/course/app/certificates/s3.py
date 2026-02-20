"""S3 upload helper for certificate PDFs.

Thin wrapper around boto3. Graceful fallback in dev when AWS is not configured.
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def upload_certificate_pdf(
    pdf_bytes: bytes,
    key: str,
    settings: Settings,
) -> str:
    """Upload PDF bytes to S3 and return the public URL.

    Parameters
    ----------
    pdf_bytes : raw PDF content
    key : S3 object key (e.g. ``certificates/abc123.pdf``)
    settings : application settings with S3 config

    Returns
    -------
    str : URL of the uploaded PDF. Falls back to a placeholder in dev.
    """
    try:
        import boto3

        s3 = boto3.client("s3", region_name=settings.s3_region)
        bucket = settings.s3_bucket

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            ContentDisposition="inline",
        )

        # Use CloudFront domain if configured, otherwise direct S3 URL
        if settings.cloudfront_domain:
            return f"https://{settings.cloudfront_domain}/{key}"
        return f"https://{bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"

    except Exception:
        logger.warning("S3 upload failed — returning placeholder URL", exc_info=True)
        return f"/static/{key}"
