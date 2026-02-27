"""Certificate router — generation, retrieval, and public QR verification."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates import controller
from app.certificates.schemas import (
    CertificateResponse,
    CertificateVerifyResponse,
    GenerateCertificateRequest,
    GenerateModuleCertificateRequest,
)
from app.config import Settings
from app.database import get_db
from app.dependencies import get_current_user, get_settings

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.post(
    "/enrollments/{enrollment_id}/generate",
    response_model=CertificateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate certificate for completed course",
    description="Generates a branded PDF certificate with QR verification code. "
    "Uploaded to S3. Requires enrollment status = COMPLETED. "
    "Returns 409 if already issued. "
    "Recipient name is provided in the request body.",
)
async def generate_certificate(
    enrollment_id: UUID,
    body: GenerateCertificateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CertificateResponse:
    return await controller.generate_certificate(db, enrollment_id, user_id, body, settings)


@router.get(
    "/me",
    response_model=list[CertificateResponse],
    summary="List my certificates",
    description="Returns all certificates earned by the authenticated user, "
    "ordered by issue date (newest first).",
)
async def get_my_certificates(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> list[CertificateResponse]:
    return await controller.get_my_certificates(db, user_id, settings)


@router.get(
    "/verify/{qr_code}",
    response_model=CertificateVerifyResponse,
    summary="Verify certificate via QR code (public)",
    description="Public endpoint — no authentication required. "
    "QR codes on certificates encode the verification URL. "
    "Returns certificate validity, recipient, course, and issue details.",
)
async def verify_certificate(
    qr_code: str,
    db: AsyncSession = Depends(get_db),
) -> CertificateVerifyResponse:
    return await controller.verify_certificate(db, qr_code)


@router.get(
    "/{certificate_id}",
    response_model=CertificateResponse,
    summary="Get certificate by ID",
)
async def get_certificate(
    certificate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CertificateResponse:
    return await controller.get_certificate(db, certificate_id, settings)


@router.post(
    "/enrollments/{enrollment_id}/modules/{module_id}/generate",
    response_model=CertificateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate module certificate",
    description="Generates a certificate for completing a specific module. "
    "Requires all lessons in the module to be completed. "
    "Course certification_mode must be MODULE or BOTH, and module cert_enabled must be true.",
)
async def generate_module_certificate(
    enrollment_id: UUID,
    module_id: UUID,
    body: GenerateModuleCertificateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CertificateResponse:
    return await controller.generate_module_certificate(
        db, enrollment_id, module_id, user_id, body, settings,
    )
