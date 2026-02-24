"""
Social graph domain — request orchestration.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import UserHiddenByBlock
from app.social_graph import service as svc
from app.social_graph.constants import ReportStatus
from app.social_graph.schemas import (
    AdminReportItem,
    AdminReportListResponse,
    AdminReportReviewRequest,
    FollowListItem,
    FollowListResponse,
    ReportRequest,
    ReportResponse,
    SocialRelationItem,
    SocialRelationListResponse,
    SocialUserRef,
    SuggestionListResponse,
)


def _user_ref(user) -> SocialUserRef:
    return SocialUserRef(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        role=user.role,
        specialty=user.specialty,
        profile_image_url=user.profile_image_url,
        verification_status=user.verification_status,
    )


async def follow_user(
    session: AsyncSession,
    follower_id: uuid.UUID,
    following_id: uuid.UUID,
) -> dict:
    await svc.follow(session, follower_id, following_id)
    return {"message": "Followed successfully."}


async def unfollow_user(
    session: AsyncSession,
    follower_id: uuid.UUID,
    following_id: uuid.UUID,
) -> None:
    await svc.unfollow(session, follower_id, following_id)


async def block_user(
    session: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> dict:
    await svc.block(session, blocker_id, blocked_id)
    return {"message": "User blocked."}


async def unblock_user(
    session: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> None:
    await svc.unblock(session, blocker_id, blocked_id)


async def mute_user(
    session: AsyncSession,
    muter_id: uuid.UUID,
    muted_id: uuid.UUID,
) -> dict:
    await svc.mute(session, muter_id, muted_id)
    return {"message": "User muted."}


async def unmute_user(
    session: AsyncSession,
    muter_id: uuid.UUID,
    muted_id: uuid.UUID,
) -> None:
    await svc.unmute(session, muter_id, muted_id)


async def list_following(
    session: AsyncSession,
    user_id: uuid.UUID,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> FollowListResponse:
    rows, total = await svc.get_following(
        session, user_id, viewer_id=viewer_id, page=page, size=size
    )
    items = [
        FollowListItem(
            id=f.follow_id,
            user=_user_ref(u),
            created_at=f.created_at,
            is_followed_by_me=is_followed,
        )
        for f, u, is_followed in rows
    ]
    return FollowListResponse(items=items, total=total, page=page, size=size)


async def list_followers(
    session: AsyncSession,
    user_id: uuid.UUID,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> FollowListResponse:
    rows, total = await svc.get_followers(
        session, user_id, viewer_id=viewer_id, page=page, size=size
    )
    items = [
        FollowListItem(
            id=f.follow_id,
            user=_user_ref(u),
            created_at=f.created_at,
            is_followed_by_me=is_followed,
        )
        for f, u, is_followed in rows
    ]
    return FollowListResponse(items=items, total=total, page=page, size=size)


async def view_user_following(
    session: AsyncSession,
    user_id: uuid.UUID,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> FollowListResponse:
    """List another user's following — raises 404 if that user has blocked the viewer."""
    if await svc.is_blocked_by(session, blocked_id=viewer_id, blocker_id=user_id):
        raise UserHiddenByBlock()
    return await list_following(session, user_id, viewer_id=viewer_id, page=page, size=size)


async def view_user_followers(
    session: AsyncSession,
    user_id: uuid.UUID,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> FollowListResponse:
    """List another user's followers — raises 404 if that user has blocked the viewer."""
    if await svc.is_blocked_by(session, blocked_id=viewer_id, blocker_id=user_id):
        raise UserHiddenByBlock()
    return await list_followers(session, user_id, viewer_id=viewer_id, page=page, size=size)


async def list_blocked(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    size: int,
) -> SocialRelationListResponse:
    rows, total = await svc.get_blocked(session, user_id, page=page, size=size)
    items = [SocialRelationItem(id=b.block_id, user=_user_ref(u), created_at=b.created_at) for b, u in rows]
    return SocialRelationListResponse(items=items, total=total, page=page, size=size)


async def list_muted(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    size: int,
) -> SocialRelationListResponse:
    rows, total = await svc.get_muted(session, user_id, page=page, size=size)
    items = [SocialRelationItem(id=m.mute_id, user=_user_ref(u), created_at=m.created_at) for m, u in rows]
    return SocialRelationListResponse(items=items, total=total, page=page, size=size)


async def list_suggestions(
    session: AsyncSession,
    user_id: uuid.UUID,
    size: int,
) -> SuggestionListResponse:
    users = await svc.get_suggestions(session, user_id, size=size)
    items = [_user_ref(u) for u in users]
    return SuggestionListResponse(items=items)


async def report_user(
    session: AsyncSession,
    reporter_id: uuid.UUID,
    body: ReportRequest,
) -> ReportResponse:
    report = await svc.create_report(
        session, reporter_id, body.target_type, body.target_id, body.reason
    )
    return ReportResponse(id=report.report_id, status=report.status, created_at=report.created_at)


async def admin_list_reports(
    session: AsyncSession,
    status_filter: ReportStatus | None,
    page: int,
    size: int,
) -> AdminReportListResponse:
    reports, total = await svc.get_reports(
        session, status_filter=status_filter, page=page, size=size
    )
    items = [
        AdminReportItem(
            id=r.report_id,
            reporter_id=r.reporter_id,
            target_type=r.target_type,
            target_id=r.target_id,
            reason=r.reason,
            status=r.status,
            reviewed_by=r.reviewed_by,
            action_taken=r.action_taken,
            created_at=r.created_at,
        )
        for r in reports
    ]
    return AdminReportListResponse(items=items, total=total, page=page, size=size)


async def admin_review_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    body: AdminReportReviewRequest,
) -> AdminReportItem:
    report = await svc.review_report(
        session,
        report_id,
        reviewer_id,
        ReportStatus(body.status),
        body.action_taken,
    )
    return AdminReportItem(
        id=report.report_id,
        reporter_id=report.reporter_id,
        target_type=report.target_type,
        target_id=report.target_id,
        reason=report.reason,
        status=report.status,
        reviewed_by=report.reviewed_by,
        action_taken=report.action_taken,
        created_at=report.created_at,
    )
