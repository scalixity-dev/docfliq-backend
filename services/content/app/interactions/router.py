"""Interactions router — all /api/v1/interactions endpoints.

Handles likes, comments, bookmarks, reposts, external shares, and reports.
Zero business logic — delegates entirely to controller.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.dependencies import get_access_token, get_current_user, get_optional_user, get_settings
from app.interactions import controller
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

router = APIRouter(prefix="/interactions", tags=["Interactions"])

_404 = {"description": "Not found"}
_403 = {"description": "Forbidden"}
_409 = {"description": "Conflict — already liked / bookmarked"}
_422 = {"description": "Validation error"}
_429 = {"description": "Rate limit exceeded"}


# ---------------------------------------------------------------------------
# Like endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/like",
    response_model=LikeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Like a post",
    description=(
        "Like a post. Returns 409 if already liked. "
        "Counter updates immediately in the database."
    ),
    responses={409: _409},
)
async def like_post(
    post_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LikeResponse:
    return await controller.like_post(post_id, user_id, db)


@router.delete(
    "/posts/{post_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlike a post",
    description="Remove a like from a post. Returns 409 if not previously liked.",
    responses={409: _409},
)
async def unlike_post(
    post_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.unlike_post(post_id, user_id, db)


@router.post(
    "/comments/{comment_id}/like",
    response_model=LikeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Like a comment",
    responses={409: _409},
)
async def like_comment(
    comment_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LikeResponse:
    return await controller.like_comment(comment_id, user_id, db)


@router.delete(
    "/comments/{comment_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlike a comment",
    responses={409: _409},
)
async def unlike_comment(
    comment_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.unlike_comment(comment_id, user_id, db)


# ---------------------------------------------------------------------------
# Comment endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/posts/{post_id}/comments",
    response_model=CommentListResponse,
    summary="List comments on a post (threaded)",
    description=(
        "Returns active comments (top-level + nested replies) ordered by creation time. "
        "Auth is optional — unauthenticated requests see all public comments."
    ),
)
async def list_comments(
    post_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: UUID | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> CommentListResponse:
    return await controller.list_comments(post_id, db, limit=limit, offset=offset)


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a post",
    description=(
        "Create a top-level comment or a nested reply (set `parent_comment_id`). "
        "Mentions are supported in comment text using @username syntax. "
        "Max length: 2,000 chars. "
        "Rate limit: 5 comments per minute per user."
    ),
    responses={404: _404, 422: _422, 429: _429},
)
async def create_comment(
    post_id: UUID,
    payload: CreateCommentRequest,
    author_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    return await controller.create_comment(post_id, payload, author_id, db)


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Edit a comment",
    description="Author-only. Updates the comment body.",
    responses={404: _404, 403: _403},
)
async def update_comment(
    comment_id: UUID,
    payload: UpdateCommentRequest,
    author_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    return await controller.update_comment(comment_id, payload, author_id, db)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    description="Soft-deletes the comment (status → DELETED). Author-only.",
    responses={404: _404, 403: _403},
)
async def delete_comment(
    comment_id: UUID,
    author_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.delete_comment(comment_id, author_id, db)


# ---------------------------------------------------------------------------
# Bookmark endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/bookmark",
    response_model=BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bookmark a post",
    description="Bookmark is private to the user. Returns 409 if already bookmarked.",
    responses={409: _409},
)
async def bookmark_post(
    post_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkResponse:
    return await controller.bookmark_post(post_id, user_id, db)


@router.delete(
    "/posts/{post_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a bookmark",
    description="Returns 409 if the post was not bookmarked.",
    responses={409: _409},
)
async def remove_bookmark(
    post_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await controller.remove_bookmark(post_id, user_id, db)


@router.get(
    "/bookmarks",
    response_model=BookmarkListResponse,
    summary="List my bookmarks",
    description="Returns the authenticated user's bookmarked posts, newest first.",
)
async def list_bookmarks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkListResponse:
    return await controller.list_bookmarks(user_id, db, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Repost (internal share) endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/repost",
    response_model=RepostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Repost a post",
    description=(
        "Create an internal repost. A new REPOST post is created in the sharer's feed "
        "and `share_count` is incremented on the original post. "
        "Repost chains collapse to the original root post."
    ),
    responses={404: _404},
)
async def repost_post(
    post_id: UUID,
    payload: RepostCreate,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepostResponse:
    return await controller.repost_post(post_id, user_id, payload, db)


# ---------------------------------------------------------------------------
# External share endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/share",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Track an external share",
    description=(
        "Record an external share event (URL copy, WhatsApp, Twitter, etc.). "
        "Increments `share_count` on the post. "
        "No server-side URL generation — client constructs the share URL."
    ),
    responses={404: _404},
)
async def share_post(
    post_id: UUID,
    payload: CreateShareRequest,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareResponse:
    return await controller.share_post(post_id, user_id, payload, db)


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/posts/{post_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a post",
    description=(
        "Submit a moderation report for a post. "
        "If 5 or more open reports exist for the post, it is automatically hidden "
        "pending admin review (HIDDEN_BY_ADMIN). "
        "Self-reports are rejected."
    ),
    responses={422: _422},
)
async def report_post(
    post_id: UUID,
    payload: CreateReportRequest,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    return await controller.report_post(post_id, user_id, payload, db)


@router.post(
    "/comments/{comment_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a comment",
    description=(
        "Submit a moderation report for a comment. "
        "If 5 or more open reports exist, the comment is automatically hidden."
    ),
    responses={422: _422},
)
async def report_comment(
    comment_id: UUID,
    payload: CreateReportRequest,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    return await controller.report_comment(comment_id, user_id, payload, db)


# ---------------------------------------------------------------------------
# User moderation endpoints (delegated to identity service)
# ---------------------------------------------------------------------------


@router.post(
    "/users/{user_id}/block",
    response_model=SocialActionResponse,
    summary="Block a user",
    description=(
        "Block a user through the identity social graph. "
        "This removes follow edges in both directions."
    ),
    responses={409: _409, 422: _422},
)
async def block_user(
    user_id: UUID,
    _: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> SocialActionResponse:
    return await controller.block_user(user_id, access_token, settings.identity_service_url)


@router.delete(
    "/users/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock a user",
    responses={404: _404},
)
async def unblock_user(
    user_id: UUID,
    _: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> None:
    await controller.unblock_user(user_id, access_token, settings.identity_service_url)


@router.post(
    "/users/{user_id}/mute",
    response_model=SocialActionResponse,
    summary="Mute a user",
    description="Mute a user through the identity social graph.",
    responses={409: _409, 422: _422},
)
async def mute_user(
    user_id: UUID,
    _: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> SocialActionResponse:
    return await controller.mute_user(user_id, access_token, settings.identity_service_url)


@router.delete(
    "/users/{user_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unmute a user",
    responses={404: _404},
)
async def unmute_user(
    user_id: UUID,
    _: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> None:
    await controller.unmute_user(user_id, access_token, settings.identity_service_url)


@router.post(
    "/users/{user_id}/report",
    response_model=UserReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a user",
    description=(
        "Submit a moderation report against a user via identity social graph."
    ),
    responses={422: _422},
)
async def report_user(
    user_id: UUID,
    payload: CreateReportRequest,
    _: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> UserReportResponse:
    return await controller.report_user(
        user_id,
        payload,
        access_token,
        settings.identity_service_url,
    )
