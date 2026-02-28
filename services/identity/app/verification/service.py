"""
Verification domain — pure business logic (zero FastAPI imports).

State machine enforced here:
  UNVERIFIED  → PENDING    submit_verification()
  REJECTED    → PENDING    submit_verification()
  PENDING     → APPROVED   approve()
  PENDING     → REJECTED   reject()
  VERIFIED    → SUSPENDED  suspend_user()
  SUSPENDED   → VERIFIED   reinstate_user()
  VERIFIED    → (blocked)  CannotResubmitVerification

Transaction contract: these functions only flush() — they do NOT commit().
The commit is the caller's responsibility (get_db dependency commits at request
end, which gives us full unit-of-work atomicity: if anything fails after a
service call, the whole transaction is rolled back together).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.auth.constants import UserRole, VerificationDocStatus, VerificationStatus
from app.auth.models import User
from app.auth.service import invalidate_all_user_sessions
from app.exceptions import (
    CannotResubmitVerification,
    UserAlreadySuspended,
    UserNotFound,
    UserNotSuspended,
    VerificationAlreadyApproved,
    VerificationDocNotFound,
    VerificationDocNotPending,
)
from app.verification.models import UserVerification


async def _get_doc_or_404(session: AsyncSession, doc_id: uuid.UUID) -> UserVerification:
    """Load a UserVerification with its user eagerly loaded; raise 404 if absent."""
    result = await session.execute(
        sa.select(UserVerification)
        .options(selectinload(UserVerification.user))
        .where(UserVerification.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise VerificationDocNotFound()
    return doc


async def _get_user_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFound()
    return user


async def submit_verification(
    session: AsyncSession,
    user_id: uuid.UUID,
    document_key: str,
    document_type: str,
) -> UserVerification:
    """Create a PENDING doc record and advance user.verification_status to PENDING.

    If the user previously had REJECTED documents, those are set to ARCHIVED so
    that only the new submission is considered active in the review queue.
    """
    user = await _get_user_or_404(session, user_id)
    if user.verification_status == VerificationStatus.VERIFIED:
        raise CannotResubmitVerification()

    # Archive any prior REJECTED documents for this user before creating the new one.
    # This keeps the admin queue clean — only the latest submission is PENDING.
    if user.verification_status == VerificationStatus.REJECTED:
        await session.execute(
            sa.update(UserVerification)
            .where(
                UserVerification.user_id == user_id,
                UserVerification.status == VerificationDocStatus.REJECTED,
            )
            .values(status=VerificationDocStatus.ARCHIVED)
        )

    doc = UserVerification(
        user_id=user_id,
        document_url=document_key,
        document_type=document_type,
        status=VerificationDocStatus.PENDING,
    )
    session.add(doc)
    user.verification_status = VerificationStatus.PENDING
    # flush: executes INSERT within the open transaction so doc.id is populated
    # and constraints are enforced, without committing (get_db handles the commit)
    await session.flush()
    return doc


async def get_pending_queue(
    session: AsyncSession,
    page: int,
    size: int,
) -> tuple[list[UserVerification], int]:
    """Return (docs, total) for PENDING verifications ordered by role priority then FIFO.

    Priority order (lower number = reviewed first):
      1 → Physician
      2 → Association
      3 → everything else (Non-Physician, Admin, unknown)

    Within the same priority group, documents are ordered oldest-first (FIFO).
    """
    total_r = await session.execute(
        sa.select(sa.func.count())
        .select_from(UserVerification)
        .where(UserVerification.status == VerificationDocStatus.PENDING)
    )
    total = total_r.scalar_one()

    role_priority = sa.case(
        (User.role == UserRole.PHYSICIAN, 1),
        (User.role == UserRole.ASSOCIATION, 2),
        else_=3,
    )

    docs_r = await session.execute(
        sa.select(UserVerification)
        .join(User, UserVerification.user_id == User.id)
        .options(contains_eager(UserVerification.user))
        .where(UserVerification.status == VerificationDocStatus.PENDING)
        .order_by(role_priority, UserVerification.created_at.asc())
        .limit(size)
        .offset((page - 1) * size)
    )
    return list(docs_r.scalars()), total


async def get_doc(session: AsyncSession, doc_id: uuid.UUID) -> UserVerification:
    return await _get_doc_or_404(session, doc_id)


async def approve(
    session: AsyncSession,
    doc_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    notes: str | None,
) -> UserVerification:
    """Approve a document: VERIFIED + content_creation_mode=True. Idempotent guard."""
    doc = await _get_doc_or_404(session, doc_id)
    if doc.status == VerificationDocStatus.APPROVED:
        raise VerificationAlreadyApproved()
    if doc.status != VerificationDocStatus.PENDING:
        raise VerificationDocNotPending()
    now = datetime.now(timezone.utc)
    doc.status = VerificationDocStatus.APPROVED
    doc.reviewed_by = reviewer_id
    doc.review_notes = notes
    doc.reviewed_at = now
    doc.user.verification_status = VerificationStatus.VERIFIED
    doc.user.content_creation_mode = True
    await session.flush()
    return doc


async def reject(
    session: AsyncSession,
    doc_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    reason: str,
) -> UserVerification:
    """Reject a document: user status → REJECTED so they can re-upload."""
    doc = await _get_doc_or_404(session, doc_id)
    if doc.status == VerificationDocStatus.APPROVED:
        raise VerificationAlreadyApproved()
    if doc.status != VerificationDocStatus.PENDING:
        raise VerificationDocNotPending()
    now = datetime.now(timezone.utc)
    doc.status = VerificationDocStatus.REJECTED
    doc.reviewed_by = reviewer_id
    doc.review_notes = reason
    doc.reviewed_at = now
    doc.user.verification_status = VerificationStatus.REJECTED
    await session.flush()
    return doc


async def suspend_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    reason: str,
) -> User:
    """Suspend a user: set verification_status=SUSPENDED and wipe all active sessions.

    Can be applied regardless of current status (VERIFIED, PENDING, etc.).
    Raises UserAlreadySuspended if already suspended.
    """
    user = await _get_user_or_404(session, user_id)
    if user.verification_status == VerificationStatus.SUSPENDED:
        raise UserAlreadySuspended()
    user.verification_status = VerificationStatus.SUSPENDED
    # Store the reason on ban_reason so it's persisted (cleared on reinstate)
    user.ban_reason = reason
    await session.flush()
    # Wipe all refresh-token sessions so the user cannot continue any active login
    await invalidate_all_user_sessions(session, user_id)
    return user


async def reinstate_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    """Reinstate a suspended user: SUSPENDED → VERIFIED.

    Raises UserNotSuspended if the user is not currently suspended.
    """
    user = await _get_user_or_404(session, user_id)
    if user.verification_status != VerificationStatus.SUSPENDED:
        raise UserNotSuspended()
    user.verification_status = VerificationStatus.VERIFIED
    user.ban_reason = None  # clear the stored suspension reason
    await session.flush()
    return user
