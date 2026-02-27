from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.notifications import controller
from app.notifications.schemas import NotificationsPageResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationsPageResponse,
    summary="List my notifications",
    description="Returns notifications for the authenticated user, newest first.",
)
async def list_notifications(
    limit: int = Query(20, ge=1, le=50, description="Page size."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    only_unread: bool = Query(
        default=False,
        description="When true, return only unread notifications.",
    ),
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsPageResponse:
    return await controller.get_notifications(
        user_id=user_id,
        db=db,
        limit=limit,
        offset=offset,
        only_unread=only_unread,
    )


@router.post(
    "/mark-all-read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all my notifications as read",
)
async def mark_all_read(
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.mark_all_read(user_id=user_id, db=db)


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a single notification as read",
)
async def mark_read(
    notification_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.mark_read(user_id=user_id, notification_id=notification_id, db=db)

