"""Search service — pure business logic, no FastAPI imports.

Full-text search uses the GIN index on posts:
  ix_posts_fts = GIN( to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,'')) )

Tag filtering uses the GIN index:
  ix_posts_specialty_tags = GIN(specialty_tags)
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.enums import ContentType, PostStatus, PostVisibility
from app.models.post import Post

_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)


async def search_posts(
    db: AsyncSession,
    query: str | None = None,
    tags: list[str] | None = None,
    content_type: ContentType | None = None,
    channel_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int]:
    """Search published/edited posts with optional full-text, tag, type, and channel filters."""
    base = select(Post).where(
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )

    if content_type is not None:
        base = base.where(Post.content_type == content_type)

    if channel_id is not None:
        base = base.where(Post.channel_id == channel_id)

    if tags:
        # GIN containment: specialty_tags @> ARRAY['tag1', 'tag2']
        base = base.where(Post.specialty_tags.contains(tags))

    order_by_clauses = [Post.created_at.desc()]

    if query:
        ts_query = func.plainto_tsquery("english", query)
        ts_vector = func.to_tsvector(
            "english",
            func.coalesce(Post.title, "") + " " + func.coalesce(Post.body, ""),
        )
        base = base.where(ts_vector.op("@@")(ts_query))
        # Rank by relevance first, then recency
        order_by_clauses = [func.ts_rank(ts_vector, ts_query).desc(), Post.created_at.desc()]

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await db.execute(
        base.order_by(*order_by_clauses).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def search_channels(
    db: AsyncSession,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Channel], int]:
    """Search active channels by name or description (ILIKE)."""
    base = select(Channel).where(Channel.is_active.is_(True))

    if query:
        pattern = f"%{query}%"
        base = base.where(
            Channel.name.ilike(pattern) | Channel.description.ilike(pattern)
        )

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    result = await db.execute(base.order_by(Channel.name.asc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total
