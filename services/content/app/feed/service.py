"""Feed service — pure business logic, no FastAPI imports.

All feed queries include both PUBLISHED and EDITED posts — the EDITED status
means a live post that has been modified at least once.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PostStatus, PostVisibility
from app.models.post import Post

# Both statuses are publicly visible
_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)


async def get_public_feed(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return public, live posts ordered by recency."""
    base = select(Post).where(
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def get_post_for_feed(post_id: UUID, db: AsyncSession) -> Post | None:
    """Fetch a single live post by ID; returns None if not found or not visible."""
    result = await db.execute(
        select(Post).where(
            Post.post_id == post_id,
            Post.status.in_(_LIVE_STATUSES),
        )
    )
    return result.scalar_one_or_none()


async def get_channel_feed(
    channel_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return live posts for a channel, newest first."""
    base = select(Post).where(
        Post.channel_id == channel_id,
        Post.status.in_(_LIVE_STATUSES),
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def get_user_posts(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Return public, live posts by a specific user, newest first."""
    base = select(Post).where(
        Post.author_id == user_id,
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Post.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total
