"""Interactions controller — orchestration layer between router and service."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LikeTargetType, ReportTargetType
from app.interactions import service
from app.interactions.exceptions import (
    AlreadyBookmarkedError,
    AlreadyLikedError,
    CommentAccessDeniedError,
    CommentNotFoundError,
    CommentRateLimitError,
    IdentityServiceError,
    NotBookmarkedError,
    NotLikedError,
    PostNotFoundError,
    SelfReportError,
)
from app.interactions.schemas import (
    BookmarkListResponse,
    BookmarkResponse,
    CommentListResponse,
    CommentResponse,
    CreateCommentRequest,
    CreateReportRequest,
    CreateShareRequest,
    LikeResponse,
    ReportResponse,
    RepostCreate,
    RepostResponse,
    ShareResponse,
    SocialActionResponse,
    UpdateCommentRequest,
    UserReportResponse,
)
from app.models.post import Post
from app.notifications import service as notifications_service


# ---------------------------------------------------------------------------
# Like controllers
# ---------------------------------------------------------------------------


async def like_post(post_id: UUID, user_id: UUID, db: AsyncSession) -> LikeResponse:
    try:
        like = await service.like_target(user_id, LikeTargetType.POST, post_id, db)
    except AlreadyLikedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already liked this post.",
        )
    # Best-effort notification for post author
    try:
        post = await db.get(Post, post_id)
        if post and post.author_id != user_id:
            snippet = (post.body or "")[:160] or None
            context = {
                "snippet": snippet,
                "link_url": f"/home?post={post.post_id}",
            }
            await notifications_service.create_notification(
                user_id=post.author_id,
                actor_id=user_id,
                type_="like",
                post_id=post.post_id,
                context=context,
                db=db,
            )
    except Exception:  # noqa: BLE001
        pass
    return LikeResponse.model_validate(like)


async def unlike_post(post_id: UUID, user_id: UUID, db: AsyncSession) -> None:
    try:
        await service.unlike_target(user_id, LikeTargetType.POST, post_id, db)
    except NotLikedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have not liked this post.",
        )


async def like_comment(comment_id: UUID, user_id: UUID, db: AsyncSession) -> LikeResponse:
    try:
        like = await service.like_target(user_id, LikeTargetType.COMMENT, comment_id, db)
    except AlreadyLikedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already liked this comment.",
        )
    return LikeResponse.model_validate(like)


async def unlike_comment(comment_id: UUID, user_id: UUID, db: AsyncSession) -> None:
    try:
        await service.unlike_target(user_id, LikeTargetType.COMMENT, comment_id, db)
    except NotLikedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have not liked this comment.",
        )


# ---------------------------------------------------------------------------
# Comment controllers
# ---------------------------------------------------------------------------


async def list_comments(
    post_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> CommentListResponse:
    comments, total = await service.list_comments(post_id, db, limit=limit, offset=offset)
    return CommentListResponse(
        items=[CommentResponse.model_validate(c) for c in comments],
        total=total,
        limit=limit,
        offset=offset,
    )


async def create_comment(
    post_id: UUID,
    payload: CreateCommentRequest,
    author_id: UUID,
    db: AsyncSession,
) -> CommentResponse:
    try:
        comment = await service.create_comment(post_id, payload, author_id, db)
    except CommentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent comment not found.",
        )
    except CommentRateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many comments. Limit is 5 per minute.",
        )
    # Best-effort notification for post author
    try:
        post = await db.get(Post, post_id)
        if post and post.author_id != author_id:
            snippet = (payload.body or "")[:160] or None
            context = {
                "snippet": snippet,
                "link_url": f"/home?post={post.post_id}",
            }
            await notifications_service.create_notification(
                user_id=post.author_id,
                actor_id=author_id,
                type_="comment",
                post_id=post.post_id,
                context=context,
                db=db,
            )
    except Exception:  # noqa: BLE001
        pass
    return CommentResponse.model_validate(comment)


async def update_comment(
    comment_id: UUID,
    payload: UpdateCommentRequest,
    author_id: UUID,
    db: AsyncSession,
) -> CommentResponse:
    try:
        comment = await service.update_comment(comment_id, payload, author_id, db)
    except CommentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment {comment_id} not found.",
        )
    except CommentAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this comment.",
        )
    return CommentResponse.model_validate(comment)


async def delete_comment(
    comment_id: UUID,
    author_id: UUID,
    db: AsyncSession,
) -> None:
    try:
        await service.delete_comment(comment_id, author_id, db)
    except CommentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment {comment_id} not found.",
        )
    except CommentAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this comment.",
        )


# ---------------------------------------------------------------------------
# Bookmark controllers
# ---------------------------------------------------------------------------


async def bookmark_post(post_id: UUID, user_id: UUID, db: AsyncSession) -> BookmarkResponse:
    try:
        bookmark = await service.bookmark_post(post_id, user_id, db)
    except AlreadyBookmarkedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already bookmarked this post.",
        )
    return BookmarkResponse.model_validate(bookmark)


async def remove_bookmark(post_id: UUID, user_id: UUID, db: AsyncSession) -> None:
    try:
        await service.remove_bookmark(post_id, user_id, db)
    except NotBookmarkedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have not bookmarked this post.",
        )


async def list_bookmarks(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> BookmarkListResponse:
    bookmarks, total = await service.list_bookmarks(user_id, db, limit=limit, offset=offset)
    return BookmarkListResponse(
        items=[BookmarkResponse.model_validate(b) for b in bookmarks],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Repost controller
# ---------------------------------------------------------------------------


async def repost_post(
    post_id: UUID,
    user_id: UUID,
    payload: RepostCreate,
    db: AsyncSession,
) -> RepostResponse:
    """Create an internal repost of a post."""
    try:
        repost = await service.repost(post_id, user_id, payload, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found or not publicly available.",
        )
    return RepostResponse.model_validate(repost)


# ---------------------------------------------------------------------------
# Share controllers
# ---------------------------------------------------------------------------


async def share_post(
    post_id: UUID,
    user_id: UUID,
    payload: CreateShareRequest,
    db: AsyncSession,
) -> ShareResponse:
    try:
        share = await service.share_post(post_id, user_id, payload, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found.",
        )
    return ShareResponse.model_validate(share)


# ---------------------------------------------------------------------------
# Report controllers
# ---------------------------------------------------------------------------


async def report_post(
    post_id: UUID,
    user_id: UUID,
    payload: CreateReportRequest,
    db: AsyncSession,
) -> ReportResponse:
    try:
        report = await service.report_target(
            reporter_id=user_id,
            target_type=ReportTargetType.POST,
            target_id=post_id,
            payload=payload,
            db=db,
        )
    except SelfReportError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot report yourself.",
        )
    return ReportResponse.model_validate(report)


async def report_comment(
    comment_id: UUID,
    user_id: UUID,
    payload: CreateReportRequest,
    db: AsyncSession,
) -> ReportResponse:
    report = await service.report_target(
        reporter_id=user_id,
        target_type=ReportTargetType.COMMENT,
        target_id=comment_id,
        payload=payload,
        db=db,
    )
    return ReportResponse.model_validate(report)


# ---------------------------------------------------------------------------
# User moderation controllers (proxied via identity service)
# ---------------------------------------------------------------------------


async def block_user(
    user_id: UUID,
    access_token: str,
    identity_base_url: str,
) -> SocialActionResponse:
    try:
        data = await service.block_user(user_id, access_token, identity_base_url)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return SocialActionResponse.model_validate(data)


async def unblock_user(
    user_id: UUID,
    access_token: str,
    identity_base_url: str,
) -> None:
    try:
        await service.unblock_user(user_id, access_token, identity_base_url)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def mute_user(
    user_id: UUID,
    access_token: str,
    identity_base_url: str,
) -> SocialActionResponse:
    try:
        data = await service.mute_user(user_id, access_token, identity_base_url)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return SocialActionResponse.model_validate(data)


async def unmute_user(
    user_id: UUID,
    access_token: str,
    identity_base_url: str,
) -> None:
    try:
        await service.unmute_user(user_id, access_token, identity_base_url)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def report_user(
    user_id: UUID,
    payload: CreateReportRequest,
    access_token: str,
    identity_base_url: str,
) -> UserReportResponse:
    try:
        data = await service.report_user(
            user_id,
            payload,
            access_token,
            identity_base_url,
        )
    except IdentityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return UserReportResponse.model_validate(data)
