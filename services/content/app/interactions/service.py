"""Interactions service — pure business logic, no FastAPI imports.

Redis is used for:
  - Like / comment counter caching (immediate update, async DB sync)
  - Comment rate limiting: 5 comments/minute per user
    key: content:rate:comment:{user_id}  type: counter, TTL=60s

Redis calls are best-effort — counter drift is acceptable short-term.
The DB like_count / comment_count columns are the authoritative values
and should be reconciled via a background job if needed.
"""

from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.enums import (
    CommentStatus,
    ContentType,
    LikeTargetType,
    PostStatus,
    PostVisibility,
    ReportStatus,
    ReportTargetType,
)
from app.models.interaction import Bookmark, Like, Share
from app.models.post import Post
from app.models.social import Report
from app.interactions.exceptions import (
    AlreadyBookmarkedError,
    AlreadyLikedError,
    CommentAccessDeniedError,
    CommentDepthExceededError,
    CommentNotFoundError,
    CommentRateLimitError,
    NotBookmarkedError,
    NotLikedError,
    PostNotFoundError,
    SelfReportError,
)
from app.interactions.schemas import (
    CreateCommentRequest,
    CreateReportRequest,
    CreateShareRequest,
    RepostCreate,
    UpdateCommentRequest,
)

_COMMENT_RATE_LIMIT = 5  # max comments per window
_COMMENT_RATE_WINDOW = 60  # seconds
_AUTO_HIDE_THRESHOLD = 5  # reports before auto-hide

# Statuses visible to the general public
_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)


# ---------------------------------------------------------------------------
# Like operations
# ---------------------------------------------------------------------------


async def like_target(
    user_id: UUID,
    target_type: LikeTargetType,
    target_id: UUID,
    db: AsyncSession,
    redis: aioredis.Redis | None = None,
) -> Like:
    """Like a post or comment. Raises AlreadyLikedError if already liked."""
    existing = await db.execute(
        select(Like).where(
            Like.user_id == user_id,
            Like.target_type == target_type,
            Like.target_id == target_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AlreadyLikedError()

    like = Like(user_id=user_id, target_type=target_type, target_id=target_id)
    db.add(like)

    # Increment denormalized counter in DB
    if target_type == LikeTargetType.POST:
        post = await db.get(Post, target_id)
        if post:
            post.like_count += 1
    else:
        comment = await db.get(Comment, target_id)
        if comment:
            comment.like_count += 1

    await db.flush()
    await db.refresh(like)
    return like


async def unlike_target(
    user_id: UUID,
    target_type: LikeTargetType,
    target_id: UUID,
    db: AsyncSession,
    redis: aioredis.Redis | None = None,
) -> None:
    """Remove a like. Raises NotLikedError if not previously liked."""
    result = await db.execute(
        select(Like).where(
            Like.user_id == user_id,
            Like.target_type == target_type,
            Like.target_id == target_id,
        )
    )
    like = result.scalar_one_or_none()
    if like is None:
        raise NotLikedError()

    await db.delete(like)

    if target_type == LikeTargetType.POST:
        post = await db.get(Post, target_id)
        if post and post.like_count > 0:
            post.like_count -= 1
    else:
        comment = await db.get(Comment, target_id)
        if comment and comment.like_count > 0:
            comment.like_count -= 1

    await db.flush()


# ---------------------------------------------------------------------------
# Comment operations
# ---------------------------------------------------------------------------


async def get_comment_by_id(comment_id: UUID, db: AsyncSession) -> Comment:
    result = await db.execute(select(Comment).where(Comment.comment_id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise CommentNotFoundError(comment_id)
    return comment


async def list_comments(
    post_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Comment], int]:
    """Return active top-level comments for a post (parent_comment_id IS NULL)."""
    base = select(Comment).where(
        Comment.post_id == post_id,
        Comment.parent_comment_id.is_(None),
        Comment.status == CommentStatus.ACTIVE,
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Comment.created_at.asc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def create_comment(
    post_id: UUID,
    payload: CreateCommentRequest,
    author_id: UUID,
    db: AsyncSession,
    redis: aioredis.Redis | None = None,
) -> Comment:
    """Create a comment or reply.

    Enforces:
    - Max depth 2 (no replies to replies)
    - Rate limit: 5 comments/minute per user (Redis-backed)
    - Max 2,000 chars (Pydantic schema)
    """
    # Rate limiting — best effort (skip if Redis is unavailable)
    if redis is not None:
        rate_key = f"content:rate:comment:{author_id}"
        count = await redis.incr(rate_key)
        if count == 1:
            await redis.expire(rate_key, _COMMENT_RATE_WINDOW)
        if count > _COMMENT_RATE_LIMIT:
            raise CommentRateLimitError()

    # Validate parent comment depth
    if payload.parent_comment_id is not None:
        parent = await get_comment_by_id(payload.parent_comment_id, db)
        if parent.parent_comment_id is not None:
            raise CommentDepthExceededError()

    comment = Comment(
        post_id=post_id,
        author_id=author_id,
        parent_comment_id=payload.parent_comment_id,
        body=payload.body,
    )
    db.add(comment)

    # Increment post comment counter
    post = await db.get(Post, post_id)
    if post:
        post.comment_count += 1

    await db.flush()
    await db.refresh(comment)
    return comment


async def update_comment(
    comment_id: UUID,
    payload: UpdateCommentRequest,
    author_id: UUID,
    db: AsyncSession,
) -> Comment:
    comment = await get_comment_by_id(comment_id, db)
    if comment.author_id != author_id:
        raise CommentAccessDeniedError()
    comment.body = payload.body
    await db.flush()
    await db.refresh(comment)
    return comment


async def delete_comment(
    comment_id: UUID,
    author_id: UUID,
    db: AsyncSession,
) -> None:
    comment = await get_comment_by_id(comment_id, db)
    if comment.author_id != author_id:
        raise CommentAccessDeniedError()
    comment.status = CommentStatus.DELETED

    post = await db.get(Post, comment.post_id)
    if post and post.comment_count > 0:
        post.comment_count -= 1

    await db.flush()


# ---------------------------------------------------------------------------
# Bookmark operations
# ---------------------------------------------------------------------------


async def bookmark_post(post_id: UUID, user_id: UUID, db: AsyncSession) -> Bookmark:
    existing = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == user_id,
            Bookmark.post_id == post_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AlreadyBookmarkedError()

    bookmark = Bookmark(user_id=user_id, post_id=post_id)
    db.add(bookmark)

    post = await db.get(Post, post_id)
    if post:
        post.bookmark_count += 1

    await db.flush()
    await db.refresh(bookmark)
    return bookmark


async def remove_bookmark(post_id: UUID, user_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == user_id,
            Bookmark.post_id == post_id,
        )
    )
    bookmark = result.scalar_one_or_none()
    if bookmark is None:
        raise NotBookmarkedError()

    await db.delete(bookmark)

    post = await db.get(Post, post_id)
    if post and post.bookmark_count > 0:
        post.bookmark_count -= 1

    await db.flush()


async def list_bookmarks(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Bookmark], int]:
    base = select(Bookmark).where(Bookmark.user_id == user_id)
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(
        base.order_by(Bookmark.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# Repost (internal share) operations
# ---------------------------------------------------------------------------


async def repost(
    original_post_id: UUID,
    author_id: UUID,
    payload: RepostCreate,
    db: AsyncSession,
) -> Post:
    """Create an internal repost of a post.

    If the original is itself a REPOST, the chain collapses to the root post.
    Increments share_count on the root post.
    """
    original = await db.get(Post, original_post_id)
    if original is None or original.status not in _LIVE_STATUSES:
        raise PostNotFoundError(original_post_id)

    # Collapse repost chains — always point to the root
    root_id = (
        original.original_post_id
        if original.content_type == ContentType.REPOST and original.original_post_id
        else original_post_id
    )

    repost_post = Post(
        author_id=author_id,
        content_type=ContentType.REPOST,
        original_post_id=root_id,
        body=payload.body,
        visibility=payload.visibility,
        status=PostStatus.PUBLISHED,
    )
    db.add(repost_post)

    # Increment share_count on the root original
    root_post = await db.get(Post, root_id)
    if root_post:
        root_post.share_count += 1

    await db.flush()
    await db.refresh(repost_post)
    return repost_post


# ---------------------------------------------------------------------------
# External share (URL tracking)
# ---------------------------------------------------------------------------


async def share_post(
    post_id: UUID,
    user_id: UUID,
    payload: CreateShareRequest,
    db: AsyncSession,
) -> Share:
    """Track an external share (URL copy, WhatsApp, Twitter, etc.)."""
    post = await db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError(post_id)

    share = Share(user_id=user_id, post_id=post_id, platform=payload.platform.value)
    db.add(share)

    post.share_count += 1

    await db.flush()
    await db.refresh(share)
    return share


# ---------------------------------------------------------------------------
# Report operations
# ---------------------------------------------------------------------------


async def report_target(
    reporter_id: UUID,
    target_type: ReportTargetType,
    target_id: UUID,
    payload: CreateReportRequest,
    db: AsyncSession,
) -> Report:
    """Submit a report. Enforces self-report prevention and auto-hide at 5 reports."""
    # Self-report: reject when reporting a USER and the target is the reporter
    if target_type == ReportTargetType.USER and target_id == reporter_id:
        raise SelfReportError()

    report = Report(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id,
        reason=payload.reason,
        status=ReportStatus.OPEN,
    )
    db.add(report)
    await db.flush()

    # Auto-hide: if 5+ OPEN reports exist for a post/comment, hide it
    if target_type in (ReportTargetType.POST, ReportTargetType.COMMENT):
        count_result = await db.execute(
            select(func.count()).where(
                Report.target_type == target_type,
                Report.target_id == target_id,
                Report.status == ReportStatus.OPEN,
            )
        )
        report_count = count_result.scalar_one()
        if report_count >= _AUTO_HIDE_THRESHOLD:
            if target_type == ReportTargetType.POST:
                post = await db.get(Post, target_id)
                if post and post.status in (PostStatus.PUBLISHED, PostStatus.EDITED):
                    post.status = PostStatus.HIDDEN_BY_ADMIN
            else:
                comment = await db.get(Comment, target_id)
                if comment and comment.status == CommentStatus.ACTIVE:
                    comment.status = CommentStatus.HIDDEN

    await db.refresh(report)
    return report
