"""Certificate controller — maps service results to HTTP responses."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates import service
from app.certificates.schemas import (
    CertificateResponse,
    CertificateVerifyResponse,
    GenerateCertificateRequest,
)
from app.config import Settings
from app.exceptions import (
    CertificateAlreadyIssuedError,
    CertificateNotFoundError,
    CourseNotCompletedError,
    EnrollmentNotFoundError,
)


def _handle_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (CertificateNotFoundError, EnrollmentNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CourseNotCompletedError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Course not yet completed. Complete all lessons first.",
        )
    if isinstance(exc, CertificateAlreadyIssuedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate already issued for this enrollment.",
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error.")


async def generate_certificate(
    db: AsyncSession,
    enrollment_id: UUID,
    user_id: UUID,
    body: GenerateCertificateRequest,
    settings: Settings,
) -> CertificateResponse:
    try:
        cert = await service.generate_certificate(
            db, enrollment_id, user_id,
            recipient_name=body.recipient_name,
            settings=settings,
        )
        resp = CertificateResponse.model_validate(cert)
        resp.verification_url = f"{settings.certificate_base_url}/{cert.qr_verification_code}"
        return resp
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_certificate(
    db: AsyncSession,
    certificate_id: UUID,
    settings: Settings,
) -> CertificateResponse:
    try:
        cert = await service.get_certificate_by_id(db, certificate_id)
        resp = CertificateResponse.model_validate(cert)
        resp.verification_url = f"{settings.certificate_base_url}/{cert.qr_verification_code}"
        return resp
    except Exception as exc:
        raise _handle_domain_error(exc) from exc


async def get_my_certificates(
    db: AsyncSession,
    user_id: UUID,
    settings: Settings,
) -> list[CertificateResponse]:
    certs = await service.get_my_certificates(db, user_id)
    results = []
    for c in certs:
        resp = CertificateResponse.model_validate(c)
        resp.verification_url = f"{settings.certificate_base_url}/{c.qr_verification_code}"
        results.append(resp)
    return results


async def verify_certificate(
    db: AsyncSession,
    qr_code: str,
) -> CertificateVerifyResponse:
    result = await service.verify_certificate(db, qr_code)
    return CertificateVerifyResponse(**result)
