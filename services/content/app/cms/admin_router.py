"""CMS admin router — admin-only endpoints for post and channel management.

RBAC is enforced at the API gateway level. These endpoints require authentication
but do not check roles internally.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.cms import controller
from app.cms.schemas import (
    AdminChannelListResponse,
    AdminPostListResponse,
    PostResponse,
)

router = APIRouter(prefix="/cms/admin", tags=["CMS"])


@router.get(
    "/posts",
    response_model=AdminPostListResponse,
    summary="List all posts (admin)",
    description=(
        "Returns offset-paginated posts across all statuses. "
        "Supports optional status and content_type filters. "
        "Admin RBAC is enforced at the API gateway level."
    ),
)
async def admin_list_posts(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by PostStatus value."),
    content_type: str | None = Query(default=None, description="Filter by ContentType value."),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=100),
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminPostListResponse:
    return await controller.admin_list_posts(
        db, status_filter=status_filter, content_type=content_type, page=page, size=size
    )


@router.get(
    "/channels",
    response_model=AdminChannelListResponse,
    summary="List all channels (admin)",
    description=(
        "Returns offset-paginated channels including inactive ones. "
        "Admin RBAC is enforced at the API gateway level."
    ),
)
async def admin_list_channels(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=100),
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminChannelListResponse:
    return await controller.admin_list_channels(db, page=page, size=size)


@router.post(
    "/posts/{post_id}/restore",
    response_model=PostResponse,
    summary="Restore a hidden or soft-deleted post (admin)",
    description=(
        "Transitions a HIDDEN_BY_ADMIN or SOFT_DELETED post back to PUBLISHED. "
        "Returns 422 if the post is not in a restorable state. "
        "Admin RBAC is enforced at the API gateway level."
    ),
    responses={404: {"description": "Not found"}, 422: {"description": "Not restorable"}},
)
async def restore_post(
    post_id: UUID,
    _: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    return await controller.restore_post(post_id, db)
