from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import service
from app.notifications.schemas import NotificationSummary, NotificationsPageResponse


async def get_notifications(
    user_id: UUID,
    db: AsyncSession,
    limit: int,
    offset: int,
    only_unread: bool,
) -> NotificationsPageResponse:
    items, total = await service.list_notifications(
        user_id=user_id,
        db=db,
        limit=limit,
        offset=offset,
        only_unread=only_unread,
    )

    summaries: list[NotificationSummary] = []
    for n in items:
        context = n.context or {}
        link_url = context.get("link_url") or "/home"
        snippet = context.get("snippet")
        actor_name = context.get("actor_name")
        actor_username = context.get("actor_username")
        actor_is_verified = context.get("actor_is_verified")

        summaries.append(
            NotificationSummary(
                id=n.notification_id,
                type=context.get("type", n.type),
                actor_id=n.actor_id,
                actor_name=actor_name,
                actor_username=actor_username,
                actor_is_verified=actor_is_verified,
                post_id=n.post_id,
                snippet=snippet,
                link_url=link_url,
                created_at=n.created_at,
                is_read=n.is_read,
            )
        )

    return NotificationsPageResponse(
        items=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


async def mark_all_read(user_id: UUID, db: AsyncSession) -> None:
    await service.mark_all_read(user_id=user_id, db=db)


async def mark_read(user_id: UUID, notification_id: UUID, db: AsyncSession) -> None:
    await service.mark_read(user_id=user_id, notification_id=notification_id, db=db)

