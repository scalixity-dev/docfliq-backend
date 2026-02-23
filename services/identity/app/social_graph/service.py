"""
Social graph domain — pure business logic (zero FastAPI imports).

State rules:
  follow:   cannot follow self, cannot follow if blocked, max 5000 following
  block:    cannot block self; auto-removes follow edges both directions
  mute:     cannot mute self; independent of follow/block
  report:   any user can report any target type
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    AlreadyBlocked,
    AlreadyFollowing,
    AlreadyMuted,
    CannotBlockSelf,
    CannotFollowSelf,
    CannotMuteSelf,
    FollowLimitExceeded,
    NotBlocked,
    NotFollowing,
    NotMuted,
    ReportNotFound,
)
from app.social_graph.constants import FOLLOW_LIMIT, ReportStatus, ReportTargetType
from app.social_graph.models import Block, Follow, Mute, Report
from app.auth.models import User


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _follow_exists(
    session: AsyncSession, follower_id: uuid.UUID, following_id: uuid.UUID
) -> bool:
    result = await session.execute(
        sa.select(sa.exists().where(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        ))
    )
    return result.scalar_one()


async def _block_exists(
    session: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID
) -> bool:
    result = await session.execute(
        sa.select(sa.exists().where(
            Block.blocker_id == blocker_id,
            Block.blocked_id == blocked_id,
        ))
    )
    return result.scalar_one()


async def _mute_exists(
    session: AsyncSession, muter_id: uuid.UUID, muted_id: uuid.UUID
) -> bool:
    result = await session.execute(
        sa.select(sa.exists().where(
            Mute.muter_id == muter_id,
            Mute.muted_id == muted_id,
        ))
    )
    return result.scalar_one()


async def _count_following(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        sa.select(sa.func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    return result.scalar_one()


# ── Follow ─────────────────────────────────────────────────────────────────────

async def follow(
    session: AsyncSession,
    follower_id: uuid.UUID,
    following_id: uuid.UUID,
) -> Follow:
    if follower_id == following_id:
        raise CannotFollowSelf()
    if await _block_exists(session, blocker_id=follower_id, blocked_id=following_id):
        raise AlreadyBlocked()
    if await _count_following(session, follower_id) >= FOLLOW_LIMIT:
        raise FollowLimitExceeded()
    if await _follow_exists(session, follower_id, following_id):
        raise AlreadyFollowing()
    edge = Follow(follower_id=follower_id, following_id=following_id)
    session.add(edge)
    await session.flush()
    # TODO: emit user.followed event (SNS/SQS not wired yet)
    return edge


async def unfollow(
    session: AsyncSession,
    follower_id: uuid.UUID,
    following_id: uuid.UUID,
) -> None:
    if not await _follow_exists(session, follower_id, following_id):
        raise NotFollowing()
    await session.execute(
        sa.delete(Follow).where(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        )
    )


# ── Block ──────────────────────────────────────────────────────────────────────

async def block(
    session: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> Block:
    if blocker_id == blocked_id:
        raise CannotBlockSelf()
    if await _block_exists(session, blocker_id, blocked_id):
        raise AlreadyBlocked()
    edge = Block(blocker_id=blocker_id, blocked_id=blocked_id)
    session.add(edge)
    # Remove follow edges in both directions
    await session.execute(
        sa.delete(Follow).where(
            sa.or_(
                sa.and_(Follow.follower_id == blocker_id, Follow.following_id == blocked_id),
                sa.and_(Follow.follower_id == blocked_id, Follow.following_id == blocker_id),
            )
        )
    )
    await session.flush()
    return edge


async def unblock(
    session: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> None:
    if not await _block_exists(session, blocker_id, blocked_id):
        raise NotBlocked()
    await session.execute(
        sa.delete(Block).where(
            Block.blocker_id == blocker_id,
            Block.blocked_id == blocked_id,
        )
    )


# ── Mute ───────────────────────────────────────────────────────────────────────

async def mute(
    session: AsyncSession,
    muter_id: uuid.UUID,
    muted_id: uuid.UUID,
) -> Mute:
    if muter_id == muted_id:
        raise CannotMuteSelf()
    if await _mute_exists(session, muter_id, muted_id):
        raise AlreadyMuted()
    edge = Mute(muter_id=muter_id, muted_id=muted_id)
    session.add(edge)
    await session.flush()
    return edge


async def unmute(
    session: AsyncSession,
    muter_id: uuid.UUID,
    muted_id: uuid.UUID,
) -> None:
    if not await _mute_exists(session, muter_id, muted_id):
        raise NotMuted()
    await session.execute(
        sa.delete(Mute).where(
            Mute.muter_id == muter_id,
            Mute.muted_id == muted_id,
        )
    )


# ── Block visibility check ─────────────────────────────────────────────────────

async def is_blocked_by(
    session: AsyncSession,
    *,
    blocked_id: uuid.UUID,
    blocker_id: uuid.UUID,
) -> bool:
    """Return True if blocker_id has blocked blocked_id."""
    return await _block_exists(session, blocker_id=blocker_id, blocked_id=blocked_id)


# ── Following / Followers lists ────────────────────────────────────────────────

async def get_following(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> tuple[list[tuple[Follow, User, bool]], int]:
    """
    Return (rows, total) where each row is (Follow, User[following], is_followed_by_viewer).

    viewer_id is the currently authenticated user — used to compute is_followed_by_me.
    """
    total_r = await session.execute(
        sa.select(sa.func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    total = total_r.scalar_one()

    rows_r = await session.execute(
        sa.select(Follow, User)
        .join(User, User.id == Follow.following_id)
        .where(Follow.follower_id == user_id)
        .order_by(Follow.created_at.desc())
        .limit(size)
        .offset((page - 1) * size)
    )
    rows = rows_r.all()  # list of (Follow, User)

    # Batch check which of these users the viewer follows
    target_ids = [u.id for _, u in rows]
    followed_set = await _batch_followed_by(session, viewer_id, target_ids)

    return [(f, u, u.id in followed_set) for f, u in rows], total


async def get_followers(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    viewer_id: uuid.UUID,
    page: int,
    size: int,
) -> tuple[list[tuple[Follow, User, bool]], int]:
    """
    Return (rows, total) where each row is (Follow, User[follower], is_followed_by_viewer).
    """
    total_r = await session.execute(
        sa.select(sa.func.count()).select_from(Follow).where(Follow.following_id == user_id)
    )
    total = total_r.scalar_one()

    rows_r = await session.execute(
        sa.select(Follow, User)
        .join(User, User.id == Follow.follower_id)
        .where(Follow.following_id == user_id)
        .order_by(Follow.created_at.desc())
        .limit(size)
        .offset((page - 1) * size)
    )
    rows = rows_r.all()

    target_ids = [u.id for _, u in rows]
    followed_set = await _batch_followed_by(session, viewer_id, target_ids)

    return [(f, u, u.id in followed_set) for f, u in rows], total


async def _batch_followed_by(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    target_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    """Return the subset of target_ids that viewer_id follows."""
    if not target_ids:
        return set()
    result = await session.execute(
        sa.select(Follow.following_id).where(
            Follow.follower_id == viewer_id,
            Follow.following_id.in_(target_ids),
        )
    )
    return {row[0] for row in result.all()}


# ── Blocked / Muted lists ──────────────────────────────────────────────────────

async def get_blocked(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    size: int,
) -> tuple[list[tuple[Block, User]], int]:
    total_r = await session.execute(
        sa.select(sa.func.count()).select_from(Block).where(Block.blocker_id == user_id)
    )
    total = total_r.scalar_one()
    rows_r = await session.execute(
        sa.select(Block, User)
        .join(User, User.id == Block.blocked_id)
        .where(Block.blocker_id == user_id)
        .order_by(Block.created_at.desc())
        .limit(size)
        .offset((page - 1) * size)
    )
    return rows_r.all(), total


async def get_muted(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    size: int,
) -> tuple[list[tuple[Mute, User]], int]:
    total_r = await session.execute(
        sa.select(sa.func.count()).select_from(Mute).where(Mute.muter_id == user_id)
    )
    total = total_r.scalar_one()
    rows_r = await session.execute(
        sa.select(Mute, User)
        .join(User, User.id == Mute.muted_id)
        .where(Mute.muter_id == user_id)
        .order_by(Mute.created_at.desc())
        .limit(size)
        .offset((page - 1) * size)
    )
    return rows_r.all(), total


# ── Suggestions ───────────────────────────────────────────────────────────────

async def get_suggestions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    size: int,
) -> list[User]:
    """
    Return up to `size` users that the current user does NOT follow,
    has NOT blocked, and is NOT blocked by.  Excludes self.
    Ordered by newest accounts first.
    """
    # Sub-queries for exclusion
    following_ids = sa.select(Follow.following_id).where(Follow.follower_id == user_id)
    blocked_ids = sa.select(Block.blocked_id).where(Block.blocker_id == user_id)
    blocked_by_ids = sa.select(Block.blocker_id).where(Block.blocked_id == user_id)

    stmt = (
        sa.select(User)
        .where(
            User.id != user_id,
            User.is_active == True,  # noqa: E712
            User.id.notin_(following_ids),
            User.id.notin_(blocked_ids),
            User.id.notin_(blocked_by_ids),
        )
        .order_by(User.created_at.desc())
        .limit(size)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Report ─────────────────────────────────────────────────────────────────────

async def create_report(
    session: AsyncSession,
    reporter_id: uuid.UUID,
    target_type: ReportTargetType,
    target_id: uuid.UUID,
    reason: str,
) -> Report:
    report = Report(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
    )
    session.add(report)
    await session.flush()
    return report


async def get_reports(
    session: AsyncSession,
    *,
    status_filter: ReportStatus | None,
    page: int,
    size: int,
) -> tuple[list[Report], int]:
    base = sa.select(Report)
    count_base = sa.select(sa.func.count()).select_from(Report)
    if status_filter is not None:
        base = base.where(Report.status == status_filter)
        count_base = count_base.where(Report.status == status_filter)
    total = (await session.execute(count_base)).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Report.created_at.asc()).limit(size).offset((page - 1) * size)
        )
    ).scalars().all()
    return list(rows), total


async def review_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    new_status: ReportStatus,
    action_taken: str | None,
) -> Report:
    result = await session.execute(
        sa.select(Report).where(Report.report_id == report_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise ReportNotFound()
    report.status = new_status
    report.reviewed_by = reviewer_id
    report.action_taken = action_taken
    await session.flush()
    return report
