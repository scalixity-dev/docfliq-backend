"""CMS controller — orchestration layer between router and service.

Maps HTTP requests to service calls, translates domain exceptions to HTTPException,
and composes Pydantic response models.
"""

from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms import service
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
    AdminChannelListResponse,
    AdminPostListResponse,
    ChannelResponse,
    CreateChannelRequest,
    CreatePostRequest,
    PostListResponse,
    PostResponse,
    PostRestoreRequest,
    PostVersionResponse,
    UpdateChannelRequest,
    UpdatePostRequest,
)
from app.pagination import decode_cursor, encode_cursor


# ---------------------------------------------------------------------------
# Post controllers
# ---------------------------------------------------------------------------


async def create_post(
    payload: CreatePostRequest,
    author_id: UUID,
    db: AsyncSession,
    redis: Redis | None = None,
) -> PostResponse:
    """Create a new post and return the full representation."""
    try:
        post = await service.create_post(payload, author_id, db, redis=redis)
    except DuplicateContentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PostResponse.model_validate(post)


async def get_post(
    post_id: UUID,
    viewer_id: UUID | None,
    db: AsyncSession,
) -> PostResponse:
    """Return a post if visible to the viewer.

    Drafts are only visible to the author. PUBLISHED/EDITED posts are public.
    SOFT_DELETED and HIDDEN_BY_ADMIN posts are only visible to the author.
    """
    try:
        post = await service.get_post_for_viewer(post_id, viewer_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    return PostResponse.model_validate(post)


async def update_post(
    post_id: UUID,
    payload: UpdatePostRequest,
    author_id: UUID,
    db: AsyncSession,
) -> PostResponse:
    try:
        post = await service.update_post(post_id, payload, author_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this post",
        )
    return PostResponse.model_validate(post)


async def publish_post(post_id: UUID, author_id: UUID, db: AsyncSession) -> PostResponse:
    try:
        post = await service.publish_post(post_id, author_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can publish this post",
        )
    except PostNotPublishableError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.reason,
        )
    return PostResponse.model_validate(post)


async def delete_post(post_id: UUID, author_id: UUID, db: AsyncSession) -> None:
    try:
        await service.soft_delete_post(post_id, author_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this post",
        )


async def hide_post(post_id: UUID, db: AsyncSession) -> PostResponse:
    """Admin: transition post to HIDDEN_BY_ADMIN status."""
    try:
        post = await service.hide_post(post_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    return PostResponse.model_validate(post)


async def get_my_posts(
    author_id: UUID,
    db: AsyncSession,
    cursor: str | None = None,
    limit: int = 20,
) -> PostListResponse:
    """Return cursor-paginated list of all posts by the authenticated user."""
    cursor_dt = cursor_uid = None
    if cursor:
        try:
            cursor_dt, cursor_uid = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid pagination cursor.",
            )

    posts = await service.get_my_posts(
        author_id=author_id,
        db=db,
        limit=limit,
        cursor_created_at=cursor_dt,
        cursor_post_id=cursor_uid,
    )
    has_more = len(posts) > limit
    page = posts[:limit]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].post_id) if has_more and page else None
    )
    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in page],
        next_cursor=next_cursor,
        has_more=has_more,
    )


async def get_post_versions(
    post_id: UUID,
    author_id: UUID,
    db: AsyncSession,
) -> list[PostVersionResponse]:
    """Return all edit history snapshots for a post. Author-only."""
    try:
        versions = await service.get_post_versions(post_id, author_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can view edit history",
        )
    return [PostVersionResponse.model_validate(v) for v in versions]


async def restore_post_version(
    post_id: UUID,
    payload: PostRestoreRequest,
    author_id: UUID,
    db: AsyncSession,
) -> PostResponse:
    """Restore a historical version. Author-only."""
    try:
        post = await service.restore_post_version(post_id, payload, author_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can restore a version",
        )
    except PostNotRestorableError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {e.version_number} not found for this post",
        )
    return PostResponse.model_validate(post)


# ---------------------------------------------------------------------------
# Channel controllers
# ---------------------------------------------------------------------------


async def list_channels(
    db: AsyncSession, limit: int = 20, offset: int = 0
) -> list[ChannelResponse]:
    channels = await service.list_channels(db, limit=limit, offset=offset)
    return [ChannelResponse.model_validate(c) for c in channels]


async def create_channel(
    payload: CreateChannelRequest,
    owner_id: UUID,
    db: AsyncSession,
) -> ChannelResponse:
    try:
        channel = await service.create_channel(payload, owner_id, db)
    except ChannelSlugTakenError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel slug '{e.slug}' is already taken.",
        )
    return ChannelResponse.model_validate(channel)


async def get_channel(channel_id: UUID, db: AsyncSession) -> ChannelResponse:
    try:
        channel = await service.get_channel_by_id(channel_id, db)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    return ChannelResponse.model_validate(channel)


async def update_channel(
    channel_id: UUID,
    payload: UpdateChannelRequest,
    owner_id: UUID,
    db: AsyncSession,
) -> ChannelResponse:
    try:
        channel = await service.update_channel(channel_id, payload, owner_id, db)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
    except ChannelAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the channel owner can perform this action",
        )
    return ChannelResponse.model_validate(channel)


# ---------------------------------------------------------------------------
# Admin controllers
# ---------------------------------------------------------------------------


async def admin_list_posts(
    db: AsyncSession,
    status_filter: str | None = None,
    content_type: str | None = None,
    page: int = 1,
    size: int = 25,
) -> AdminPostListResponse:
    posts, total = await service.admin_list_posts(
        db, status=status_filter, content_type=content_type, page=page, size=size
    )
    return AdminPostListResponse(
        items=[PostResponse.model_validate(p) for p in posts],
        total=total,
        page=page,
        size=size,
    )


async def admin_list_channels(
    db: AsyncSession,
    page: int = 1,
    size: int = 25,
) -> AdminChannelListResponse:
    channels, total = await service.admin_list_channels(db, page=page, size=size)
    return AdminChannelListResponse(
        items=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
        page=page,
        size=size,
    )


async def restore_post(post_id: UUID, db: AsyncSession) -> PostResponse:
    """Admin: restore a hidden/deleted post back to PUBLISHED."""
    try:
        post = await service.restore_post(post_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )
    except PostNotRestorableError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only HIDDEN_BY_ADMIN or SOFT_DELETED posts can be restored",
        )
    return PostResponse.model_validate(post)
