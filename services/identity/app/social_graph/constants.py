"""
Social graph domain — enums and limits.
"""
from __future__ import annotations

import enum

# Hard limit on the number of users one account can follow (MS-1 spec §2.6.3)
FOLLOW_LIMIT: int = 5_000


class ReportTargetType(str, enum.Enum):
    USER = "user"
    POST = "post"
    COMMENT = "comment"
    WEBINAR = "webinar"


class ReportStatus(str, enum.Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    ACTIONED = "actioned"
    DISMISSED = "dismissed"
