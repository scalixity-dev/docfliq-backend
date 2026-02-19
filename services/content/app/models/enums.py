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


# SQLAlchemy PgEnum instances (reuse across models to avoid duplicate type creation)
content_type_enum = PgEnum(ContentType, name="content_type", create_type=True)
post_visibility_enum = PgEnum(PostVisibility, name="post_visibility", create_type=True)
post_status_enum = PgEnum(PostStatus, name="post_status", create_type=True)
comment_status_enum = PgEnum(CommentStatus, name="comment_status", create_type=True)
like_target_type_enum = PgEnum(LikeTargetType, name="like_target_type", create_type=True)
report_target_type_enum = PgEnum(ReportTargetType, name="report_target_type", create_type=True)
report_status_enum = PgEnum(ReportStatus, name="report_status", create_type=True)