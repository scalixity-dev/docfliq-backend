from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.notifications import service
from app.notifications.schemas import NotificationType


class CreateNotificationRequestBody(BaseModel):
    user_id: UUID
    actor_id: UUID | None = None
    type: NotificationType
    post_id: UUID | None = None
    link_url: str | None = None
    snippet: str | None = None


router = APIRouter(prefix="/notifications/internal", tags=["Notifications"])


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Internal: create a notification (service-to-service).",
)
async def create_notification_internal(
    body: CreateNotificationRequestBody,
    db: AsyncSession = Depends(get_db),
) -> None:
    context: dict[str, str] = {}
    if body.link_url is not None:
        context["link_url"] = body.link_url
    if body.snippet is not None:
        context["snippet"] = body.snippet

    await service.create_notification(
        user_id=body.user_id,
        actor_id=body.actor_id,
        type_=body.type,
        post_id=body.post_id,
        context=context or None,
        db=db,
    )

