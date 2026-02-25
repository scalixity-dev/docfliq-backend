from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def list_notifications(
    user_id: UUID,
    db: AsyncSession,
    limit: int,
    offset: int,
    only_unread: bool,
) -> tuple[list[Notification], int]:
    base = select(Notification).where(Notification.user_id == user_id)
    if only_unread:
        base = base.where(Notification.is_read.is_(False))

    count_query = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_query)).scalar_one()

    rows = await db.execute(
        base.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(rows.scalars().all())
    return items, total


async def mark_all_read(user_id: UUID, db: AsyncSession) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )


async def mark_read(user_id: UUID, notification_id: UUID, db: AsyncSession) -> None:
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.notification_id == notification_id,
        )
        .values(is_read=True)
    )


async def create_notification(
    user_id: UUID,
    actor_id: UUID | None,
    type_: str,
    post_id: UUID | None,
    context: dict[str, Any] | None,
    db: AsyncSession,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type_,
        post_id=post_id,
        context=context,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return notification

