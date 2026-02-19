import enum

from sqlalchemy.dialects.postgresql import ENUM as PgEnum


class ContentType(str, enum.Enum):
    TEXT = "TEXT"
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    LINK = "LINK"
    WEBINAR_CARD = "WEBINAR_CARD"
    COURSE_CARD = "COURSE_CARD"
    REPOST = "REPOST"


class PostVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    VERIFIED_ONLY = "VERIFIED_ONLY"
    FOLLOWERS_ONLY = "FOLLOWERS_ONLY"


class PostStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    EDITED = "EDITED"          # Published post that has been modified; shows 'edited' indicator
    SOFT_DELETED = "SOFT_DELETED"      # Hidden, data retained 30 days; author can restore
    HIDDEN_BY_ADMIN = "HIDDEN_BY_ADMIN"  # Admin action; author sees 'hidden' status, can appeal


class CommentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    HIDDEN = "HIDDEN"
    DELETED = "DELETED"


class LikeTargetType(str, enum.Enum):
    POST = "POST"
    COMMENT = "COMMENT"


class ReportTargetType(str, enum.Enum):
    USER = "USER"
    POST = "POST"
    COMMENT = "COMMENT"
    WEBINAR = "WEBINAR"


class ReportStatus(str, enum.Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    ACTIONED = "ACTIONED"
    DISMISSED = "DISMISSED"


class SharePlatform(str, enum.Enum):
    APP = "APP"
    WHATSAPP = "WHATSAPP"
    TWITTER = "TWITTER"
    COPY_LINK = "COPY_LINK"


class ExperimentStatus(str, enum.Enum):
    DRAFT = "DRAFT"          # Created but not yet running
    RUNNING = "RUNNING"      # Active, traffic is being split
    PAUSED = "PAUSED"        # Temporarily halted
    COMPLETED = "COMPLETED"  # Concluded (manually or by end date)


class ExperimentEventType(str, enum.Enum):
    IMPRESSION = "IMPRESSION"        # Post shown in feed
    CLICK = "CLICK"                  # User tapped on post
    LIKE = "LIKE"                    # Liked a post in this session
    COMMENT = "COMMENT"              # Commented on a post in this session
    SHARE = "SHARE"                  # Shared a post in this session
    SESSION_START = "SESSION_START"  # User opened feed tab
    SESSION_END = "SESSION_END"      # User left feed tab (carries session_duration_s)


# SQLAlchemy PgEnum instances (reuse across models to avoid duplicate type creation)
content_type_enum = PgEnum(ContentType, name="content_type", create_type=True)
post_visibility_enum = PgEnum(PostVisibility, name="post_visibility", create_type=True)
post_status_enum = PgEnum(PostStatus, name="post_status", create_type=True)
comment_status_enum = PgEnum(CommentStatus, name="comment_status", create_type=True)
like_target_type_enum = PgEnum(LikeTargetType, name="like_target_type", create_type=True)
report_target_type_enum = PgEnum(ReportTargetType, name="report_target_type", create_type=True)
report_status_enum = PgEnum(ReportStatus, name="report_status", create_type=True)
experiment_status_enum = PgEnum(ExperimentStatus, name="experiment_status", create_type=True)
experiment_event_type_enum = PgEnum(
    ExperimentEventType, name="experiment_event_type", create_type=True
)