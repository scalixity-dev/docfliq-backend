"""CMS service — pure business logic, no FastAPI imports."""

import hashlib
import re
import uuid
from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.feed.cache import is_duplicate_content
from app.models.channel import Channel
from app.models.enums import PostStatus
from app.models.post import Post
from app.models.post_version import PostVersion
from app.cms.exceptions import (
    ChannelAccessDeniedError,
    ChannelNotFoundError,
    ChannelSlugTakenError,
    DuplicateContentError,
    PostAccessDeniedError,
    PostNotFoundError,
    PostNotPublishableError,
    PostNotRestorableError,
)
from app.cms.schemas import (
    CreateChannelRequest,
    CreatePostRequest,
    PostRestoreRequest,
    UpdateChannelRequest,
    UpdatePostRequest,
)

# Statuses that allow the author to edit
_EDITABLE_STATUSES = (PostStatus.DRAFT, PostStatus.PUBLISHED, PostStatus.EDITED)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert arbitrary text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or str(uuid.uuid4())[:8]


async def _snapshot_version(post: Post, edited_by: UUID, db: AsyncSession) -> None:
    """Persist a PostVersion snapshot of current post content before overwriting."""
    snapshot = PostVersion(
        post_id=post.post_id,
        version_number=post.version,
        title=post.title,
        body=post.body,
        media_urls=post.media_urls,
        link_preview=post.link_preview,
        edited_by=edited_by,
    )
    db.add(snapshot)


# ---------------------------------------------------------------------------
# Post operations
# ---------------------------------------------------------------------------


async def get_post_by_id(post_id: UUID, db: AsyncSession) -> Post:
    result = await db.execute(select(Post).where(Post.post_id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise PostNotFoundError(post_id)
    return post


async def get_post_for_viewer(
    post_id: UUID,
    viewer_id: UUID | None,
    db: AsyncSession,
) -> Post:
    """Return a post if visible to the given viewer.

    - DRAFT: author only.
    - PUBLISHED / EDITED: any viewer (no auth needed).
    - SOFT_DELETED / HIDDEN_BY_ADMIN: author only (sees their own status).
    """
    post = await get_post_by_id(post_id, db)

    if post.status == PostStatus.DRAFT:
        if viewer_id is None or post.author_id != viewer_id:
            raise PostNotFoundError(post_id)

    if post.status in (PostStatus.SOFT_DELETED, PostStatus.HIDDEN_BY_ADMIN):
        if viewer_id is None or post.author_id != viewer_id:
            raise PostNotFoundError(post_id)

    return post


def _compute_fingerprint(title: str | None, body: str | None) -> str:
    """SHA-256 fingerprint of normalised post content for duplicate detection."""
    raw = ((title or "") + " " + (body or "")).lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_post(
    payload: CreatePostRequest,
    author_id: UUID,
    db: AsyncSession,
    redis: Redis | None = None,
) -> Post:
    # Duplicate-content guard: same author, same content, within 60 seconds
    if redis is not None:
        fingerprint = _compute_fingerprint(payload.title, payload.body)
        if await is_duplicate_content(fingerprint, author_id, redis):
            raise DuplicateContentError(
                "Duplicate post detected. The same content was submitted within the last 60 seconds."
            )

    media = (
        [item.model_dump() for item in payload.media_urls]
        if payload.media_urls
        else None
    )
    link_prev = payload.link_preview.model_dump() if payload.link_preview else None

    from app.cms.hashtags import extract_hashtags

    extracted_hashtags = extract_hashtags(payload.body)

    post = Post(
        author_id=author_id,
        content_type=payload.content_type,
        title=payload.title,
        body=payload.body,
        media_urls=media,
        link_preview=link_prev,
        visibility=payload.visibility,
        status=payload.status,
        specialty_tags=payload.specialty_tags,
        hashtags=extracted_hashtags or None,
        channel_id=payload.channel_id,
    )
    db.add(post)
    await db.flush()
    await db.refresh(post)
    return post


async def update_post(
    post_id: UUID,
    payload: UpdatePostRequest,
    author_id: UUID,
    db: AsyncSession,
) -> Post:
    post = await get_post_by_id(post_id, db)
    if post.author_id != author_id:
        raise PostAccessDeniedError()
    if post.status not in _EDITABLE_STATUSES:
        raise PostAccessDeniedError()

    # Snapshot before overwriting
    await _snapshot_version(post, author_id, db)

    update_data = payload.model_dump(exclude_none=True)
    # Serialize nested Pydantic objects to plain dicts for JSONB storage
    if "media_urls" in update_data and payload.media_urls is not None:
        update_data["media_urls"] = [item.model_dump() for item in payload.media_urls]
    if "link_preview" in update_data and payload.link_preview is not None:
        update_data["link_preview"] = payload.link_preview.model_dump()

    for field, value in update_data.items():
        setattr(post, field, value)

    # Re-extract hashtags when body changes
    if "body" in update_data:
        from app.cms.hashtags import extract_hashtags
        post.hashtags = extract_hashtags(post.body) or None

    post.version += 1
    if post.status == PostStatus.PUBLISHED:
        post.status = PostStatus.EDITED

    await db.flush()
    await db.refresh(post)
    return post


async def publish_post(post_id: UUID, author_id: UUID, db: AsyncSession) -> Post:
    post = await get_post_by_id(post_id, db)
    if post.author_id != author_id:
        raise PostAccessDeniedError()
    if post.status != PostStatus.DRAFT:
        raise PostNotPublishableError(
            f"Cannot publish a post with status '{post.status.value}'. "
            "Only DRAFT posts can be published."
        )
    post.status = PostStatus.PUBLISHED
    await db.flush()
    await db.refresh(post)
    return post


async def soft_delete_post(post_id: UUID, author_id: UUID, db: AsyncSession) -> None:
    post = await get_post_by_id(post_id, db)
    if post.author_id != author_id:
        raise PostAccessDeniedError()
    if post.status == PostStatus.SOFT_DELETED:
        return  # idempotent — already deleted
    post.status = PostStatus.SOFT_DELETED
    post.deleted_at = datetime.now(timezone.utc)
    await db.flush()


async def hide_post(post_id: UUID, db: AsyncSession) -> Post:
    """Admin action: hide a post from public feed (HIDDEN_BY_ADMIN)."""
    post = await get_post_by_id(post_id, db)
    post.status = PostStatus.HIDDEN_BY_ADMIN
    await db.flush()
    await db.refresh(post)
    return post


async def get_my_posts(
    author_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    cursor_created_at: datetime | None = None,
    cursor_post_id: UUID | None = None,
) -> list[Post]:
    """All posts by the authenticated author (any status), newest first."""
    q = select(Post).where(Post.author_id == author_id)
    if cursor_created_at is not None and cursor_post_id is not None:
        q = q.where(
            (Post.created_at < cursor_created_at)
            | (
                (Post.created_at == cursor_created_at)
                & (Post.post_id < cursor_post_id)
            )
        )
    q = q.order_by(Post.created_at.desc(), Post.post_id.desc()).limit(limit + 1)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_post_versions(
    post_id: UUID,
    author_id: UUID,
    db: AsyncSession,
) -> list[PostVersion]:
    """Return all version snapshots for a post. Author-only."""
    post = await get_post_by_id(post_id, db)
    if post.author_id != author_id:
        raise PostAccessDeniedError()
    result = await db.execute(
        select(PostVersion)
        .where(PostVersion.post_id == post_id)
        .order_by(PostVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def restore_post_version(
    post_id: UUID,
    payload: PostRestoreRequest,
    author_id: UUID,
    db: AsyncSession,
) -> Post:
    """Restore a historical version.

    Takes a snapshot of the current state first, then overwrites with the target version.
    """
    post = await get_post_by_id(post_id, db)
    if post.author_id != author_id:
        raise PostAccessDeniedError()

    result = await db.execute(
        select(PostVersion).where(
            PostVersion.post_id == post_id,
            PostVersion.version_number == payload.version_number,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise PostNotRestorableError(payload.version_number)

    await _snapshot_version(post, author_id, db)

    post.title = target.title
    post.body = target.body
    post.media_urls = target.media_urls
    post.link_preview = target.link_preview
    post.version += 1
    if post.status == PostStatus.PUBLISHED:
        post.status = PostStatus.EDITED

    await db.flush()
    await db.refresh(post)
    return post


# ---------------------------------------------------------------------------
# Channel operations
# ---------------------------------------------------------------------------


async def get_channel_by_id(channel_id: UUID, db: AsyncSession) -> Channel:
    result = await db.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise ChannelNotFoundError(channel_id)
    return channel


async def list_channels(db: AsyncSession, limit: int = 20, offset: int = 0) -> list[Channel]:
    result = await db.execute(
        select(Channel).where(Channel.is_active.is_(True)).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


async def create_channel(
    payload: CreateChannelRequest,
    owner_id: UUID,
    db: AsyncSession,
) -> Channel:
    slug = payload.slug or _slugify(payload.name)
    channel = Channel(
        name=payload.name,
        slug=slug,
        description=payload.description,
        logo_url=payload.logo_url,
        owner_id=owner_id,
    )
    db.add(channel)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ChannelSlugTakenError(slug)
    await db.refresh(channel)
    return channel


async def admin_list_posts(
    db: AsyncSession,
    status: str | None = None,
    content_type: str | None = None,
    page: int = 1,
    size: int = 25,
) -> tuple[list[Post], int]:
    """List all posts (any status) with optional filters. Returns (posts, total)."""
    q = select(Post)
    count_q = select(func.count()).select_from(Post)

    if status:
        q = q.where(Post.status == status)
        count_q = count_q.where(Post.status == status)
    if content_type:
        q = q.where(Post.content_type == content_type)
        count_q = count_q.where(Post.content_type == content_type)

    total = (await db.execute(count_q)).scalar() or 0
    q = q.order_by(Post.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def admin_list_channels(
    db: AsyncSession,
    page: int = 1,
    size: int = 25,
) -> tuple[list[Channel], int]:
    """List all channels (including inactive). Returns (channels, total)."""
    total = (await db.execute(select(func.count()).select_from(Channel))).scalar() or 0
    result = await db.execute(
        select(Channel).order_by(Channel.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    return list(result.scalars().all()), total


async def restore_post(post_id: UUID, db: AsyncSession) -> Post:
    """Admin action: restore a HIDDEN_BY_ADMIN or SOFT_DELETED post back to PUBLISHED."""
    post = await get_post_by_id(post_id, db)
    if post.status not in (PostStatus.HIDDEN_BY_ADMIN, PostStatus.SOFT_DELETED):
        raise PostNotRestorableError(0)
    post.status = PostStatus.PUBLISHED
    post.deleted_at = None
    await db.flush()
    await db.refresh(post)
    return post


async def update_channel(
    channel_id: UUID,
    payload: UpdateChannelRequest,
    owner_id: UUID,
    db: AsyncSession,
) -> Channel:
    channel = await get_channel_by_id(channel_id, db)
    if channel.owner_id != owner_id:
        raise ChannelAccessDeniedError()

    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(channel, field, value)

    await db.flush()
    await db.refresh(channel)
    return channel
