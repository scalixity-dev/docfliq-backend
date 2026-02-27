from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


NotificationType = Literal[
    "like",
    "comment",
    "follow",
    "mention",
    "system_webinar",
    "system_certificate",
]


class NotificationSummary(BaseModel):
    """Single notification item for the notifications feed."""

    id: UUID
    type: NotificationType
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_username: str | None = None
    actor_is_verified: bool | None = None
    post_id: UUID | None = None
    snippet: str | None = None
    link_url: str
    created_at: datetime
    is_read: bool


class NotificationsPageResponse(BaseModel):
    """Offset-paginated notifications list for the current user."""

    items: list[NotificationSummary]
    total: int = Field(description="Total notifications for this user.")
    limit: int = Field(description="Requested page size.")
    offset: int = Field(description="Requested offset.")

