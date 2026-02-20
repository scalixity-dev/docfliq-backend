"""
Verification domain — request orchestration.

Glues together: S3 presigned URLs, DB service, email background tasks.
"""
from __future__ import annotations

import uuid

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.email import send as email
from app.profile.service import get_profile
from app.s3 import (
    check_document_size,
    generate_presigned_get_url,
    generate_presigned_put_url,
)
from app.verification import service as svc
from app.verification.schemas import (
    ConfirmRequest,
    DocumentViewResponse,
    ReviewRequest,
    ReviewResponse,
    SuspendRequest,
    UploadRequest,
    UploadResponse,
    UserStatusResponse,
    VerificationQueueItem,
    VerificationQueueResponse,
    VerificationSubmittedResponse,
)


async def request_upload(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: UploadRequest,
    settings: Settings,
) -> UploadResponse:
    url, key = await generate_presigned_put_url(
        user_id, body.document_type.value, body.content_type, settings
    )
    return UploadResponse(
        upload_url=url,
        document_key=key,
        expires_in=settings.s3_presigned_expiry_seconds,
    )


async def confirm_upload(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: ConfirmRequest,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> VerificationSubmittedResponse:
    # Guard: verify the file was actually uploaded and is within the 10 MB limit.
    # check_document_size raises S3ObjectNotFound (400) if the key doesn't exist,
    # or FileTooLarge (413) + auto-deletes the S3 object if it exceeds 10 MB.
    await check_document_size(body.document_key, settings)

    doc = await svc.submit_verification(
        session, user_id, body.document_key, body.document_type.value
    )
    user = await get_profile(session, user_id)

    # Email the user confirming their submission.
    background_tasks.add_task(
        email.send_verification_submitted, user.email, user.full_name, settings
    )
    # Email the admin team so they know a new document is waiting in the queue.
    if settings.admin_notification_email:
        background_tasks.add_task(
            email.send_verification_submitted_admin,
            settings.admin_notification_email,
            user.full_name,
            user.email,
            body.document_type.value,
            settings,
        )

    return VerificationSubmittedResponse(
        verification_id=doc.id,
        status=doc.status,
        message="Document received. You will be notified once our team has reviewed it.",
    )


async def get_queue(
    session: AsyncSession,
    page: int,
    size: int,
) -> VerificationQueueResponse:
    docs, total = await svc.get_pending_queue(session, page, size)
    items = [
        VerificationQueueItem(
            id=d.id,
            user_id=d.user_id,
            user_name=d.user.full_name,
            user_email=d.user.email,
            document_type=d.document_type,
            status=d.status,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return VerificationQueueResponse(items=items, total=total, page=page, size=size)


async def view_document(
    session: AsyncSession,
    doc_id: uuid.UUID,
    settings: Settings,
) -> DocumentViewResponse:
    doc = await svc.get_doc(session, doc_id)
    view_url = await generate_presigned_get_url(doc.document_url, settings, expiry_seconds=1800)
    return DocumentViewResponse(view_url=view_url, expires_in=1800, document_type=doc.document_type)


async def review_doc(
    session: AsyncSession,
    doc_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    body: ReviewRequest,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> ReviewResponse:
    if body.action == "APPROVE":
        doc = await svc.approve(session, doc_id, reviewer_id, body.notes)
        background_tasks.add_task(
            email.send_verification_approved, doc.user.email, doc.user.full_name, settings
        )
    else:
        reason = body.notes or "Your document could not be verified."
        doc = await svc.reject(session, doc_id, reviewer_id, reason)
        background_tasks.add_task(
            email.send_verification_rejected,
            doc.user.email,
            doc.user.full_name,
            reason,
            settings,
        )
    return ReviewResponse(id=doc.id, status=doc.status, reviewed_at=doc.reviewed_at)


async def suspend_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    body: SuspendRequest,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> UserStatusResponse:
    user = await svc.suspend_user(session, user_id, body.reason)
    background_tasks.add_task(
        email.send_account_suspended, user.email, user.full_name, body.reason, settings
    )
    return UserStatusResponse(id=user.id, verification_status=user.verification_status)


async def reinstate_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> UserStatusResponse:
    user = await svc.reinstate_user(session, user_id)
    return UserStatusResponse(id=user.id, verification_status=user.verification_status)
