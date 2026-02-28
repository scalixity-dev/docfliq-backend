"""
Media asset — static constants and enum types.
"""
import enum


class AssetType(str, enum.Enum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    PDF = "PDF"
    SCORM = "SCORM"


class TranscodeStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ImageSize(str, enum.Enum):
    """Standard image resize presets."""
    THUMBNAIL = "thumbnail"    # 150x150
    MEDIUM = "medium"          # 600x600
    LARGE = "large"            # 1200x1200
    AVATAR_SMALL = "avatar_s"  # 48x48
    AVATAR_MEDIUM = "avatar_m"  # 120x120
    AVATAR_LARGE = "avatar_l"  # 300x300
    COURSE_THUMB = "course_thumb"  # 400x225 (16:9)


# Image size dimensions: (width, height)
IMAGE_DIMENSIONS: dict[str, tuple[int, int]] = {
    ImageSize.THUMBNAIL: (150, 150),
    ImageSize.MEDIUM: (600, 600),
    ImageSize.LARGE: (1200, 1200),
    ImageSize.AVATAR_SMALL: (48, 48),
    ImageSize.AVATAR_MEDIUM: (120, 120),
    ImageSize.AVATAR_LARGE: (300, 300),
    ImageSize.COURSE_THUMB: (400, 225),
}

# Video transcoding output presets
VIDEO_PRESETS = {
    "720p": {"width": 1280, "height": 720, "bitrate": 3_500_000},
    "1080p": {"width": 1920, "height": 1080, "bitrate": 6_000_000},
    "4k": {"width": 3840, "height": 2160, "bitrate": 15_000_000},
}

# CloudFront signed URL expiry (seconds) per content type
SIGNED_URL_EXPIRY: dict[str, int] = {
    "paid_course_video": 4 * 3600,     # 4 hours
    "paid_course_pdf": 2 * 3600,       # 2 hours
    "webinar_vod": 8 * 3600,           # 8 hours
    "user_upload": 15 * 60,            # 15 minutes
    "verification_doc": 30 * 60,       # 30 minutes
    "default": 1 * 3600,               # 1 hour fallback
}
