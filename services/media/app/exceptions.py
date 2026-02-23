"""
Media service — domain-specific HTTP exceptions.

All exceptions use preset status codes and detail messages so that callers
never need to specify these at the call site.  The global error_envelope_middleware
in shared catches these and wraps them in the standard error envelope.
"""
from fastapi import HTTPException, status


# ── Asset ────────────────────────────────────────────────────────────────────

class AssetNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media asset not found.",
        )


class AssetAlreadyProcessing(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This asset is already being processed.",
        )


class UnsupportedAssetType(HTTPException):
    def __init__(self, asset_type: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported asset type: {asset_type}.",
        )


class UnsupportedContentType(HTTPException):
    def __init__(self, content_type: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported content type: {content_type}.",
        )


# ── Upload ───────────────────────────────────────────────────────────────────

class UploadFileTooLarge(HTTPException):
    def __init__(self, max_mb: int) -> None:
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the maximum allowed size of {max_mb} MB.",
        )


# ── S3 / CloudFront ─────────────────────────────────────────────────────────

class S3PresignError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate upload URL. Please try again.",
        )


class S3ObjectNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file does not exist in storage. Please upload first.",
        )


class CloudFrontSignError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate secure content URL. Please try again.",
        )


# ── Transcoding ──────────────────────────────────────────────────────────────

class TranscodeJobFailed(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Video transcoding failed. Please re-upload in MP4 format.",
        )


class TranscodeJobNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcoding job not found.",
        )
