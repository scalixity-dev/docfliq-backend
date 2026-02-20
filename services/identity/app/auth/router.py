"""
Identity service — auth router.

Only HTTP concerns live here:
  - Route declarations, HTTP methods, status codes, response_model
  - Dependency injection (session, settings, current user)
  - Forwarding to the controller

Zero business logic. Zero DB queries.
"""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.rate_limit import limiter
from app.auth.controller import (
    email_otp_request as email_otp_request_controller,
    email_otp_verify as email_otp_verify_controller,
    login as login_controller,
    logout as logout_controller,
    otp_request as otp_request_controller,
    otp_verify as otp_verify_controller,
    password_reset_confirm as password_reset_confirm_controller,
    password_reset_confirm_link as password_reset_confirm_link_controller,
    password_reset_request as password_reset_request_controller,
    refresh_token as refresh_token_controller,
    register as register_controller,
    resend_verification as resend_verification_controller,
    verify_email as verify_email_controller,
)
from app.auth.schemas import (
    EmailOTPRequestSchema,
    EmailOTPVerifyRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    OTPRequestSchema,
    OTPVerifyRequest,
    PasswordResetConfirmSchema,
    PasswordResetLinkConfirmSchema,
    PasswordResetRequestSchema,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.auth.dependencies import get_current_user
from app.config import Settings
from app.database import get_db
from app.redis_client import get_redis_client
from shared.models.user import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@lru_cache
def _get_settings() -> Settings:
    return Settings()


def _get_redis(settings: Settings = Depends(_get_settings)) -> aioredis.Redis:
    return get_redis_client(settings.redis_url)


def _client_ip(request: Request) -> str | None:
    """Extract client IP from the request, honouring X-Forwarded-For."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Email + Password ──────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account (email + password)",
)
@limiter.limit("3/hour")
async def register(
    request: Request,
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> RegisterResponse:
    return await register_controller(
        session,
        body,
        settings,
        redis,
        background_tasks,
        ip_address=_client_ip(request),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email + password",
)
@limiter.limit("5/15minutes")
async def login(
    request: Request,
    body: LoginRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> TokenResponse:
    return await login_controller(
        session,
        body,
        settings,
        redis,
        background_tasks,
        ip_address=_client_ip(request),
    )


# ── Token management ──────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue a new access + refresh pair",
)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> TokenResponse:
    return await refresh_token_controller(session, body, settings)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate a session (logout from one device)",
)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    await logout_controller(session, body)


# ── OTP flow ──────────────────────────────────────────────────────────────────

@router.post(
    "/otp/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a 6-digit OTP sent via SMS",
)
@limiter.limit("3/10minutes")
async def otp_request(
    request: Request,
    body: OTPRequestSchema,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await otp_request_controller(session, body, redis, settings)
    return MessageResponse(message="OTP sent successfully.")


@router.post(
    "/otp/verify",
    response_model=TokenResponse,
    summary="Verify OTP and authenticate (creates account on first use)",
)
async def otp_verify(
    request: Request,
    body: OTPVerifyRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> TokenResponse:
    return await otp_verify_controller(
        session,
        body,
        settings,
        redis,
        ip_address=_client_ip(request),
    )


# ── Password reset ─────────────────────────────────────────────────────────────

@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset OTP via email",
    description=(
        "Sends a 6-digit reset code to the registered email address. "
        "Always returns 200 even if the email is not registered (prevents enumeration). "
        "Code expires in 15 minutes."
    ),
)
@limiter.limit("3/hour")
async def password_reset_request(
    request: Request,
    body: PasswordResetRequestSchema,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await password_reset_request_controller(session, body, settings, background_tasks, redis)
    return MessageResponse(message="If an account exists for this email, a reset code has been sent.")


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset with OTP and new password",
    description=(
        "Verifies the 6-digit OTP, updates the password, and invalidates all active sessions "
        "(forcing re-login on all devices)."
    ),
)
async def password_reset_confirm(
    body: PasswordResetConfirmSchema,
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await password_reset_confirm_controller(session, body)
    return MessageResponse(message="Password reset successfully. Please log in with your new password.")


@router.post(
    "/password-reset/confirm-link",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset via email link (1-hour token)",
    description=(
        "Validates the URL-safe token from the reset link, updates the password, "
        "and invalidates all active sessions (forcing re-login on all devices). "
        "Token expires in 1 hour and is single-use."
    ),
)
async def password_reset_confirm_link(
    body: PasswordResetLinkConfirmSchema,
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await password_reset_confirm_link_controller(session, redis, body)
    return MessageResponse(message="Password reset successfully. Please log in with your new password.")


# ── Email verification ────────────────────────────────────────────────────────

@router.get(
    "/email/verify",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify email address via link",
    description=(
        "Token is sent in the verification email after registration. "
        "Marks the account's email as verified. Link expires after 24 hours."
    ),
)
async def verify_email(
    token: str = Query(..., description="Verification token from the email link"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await verify_email_controller(session, redis, token)
    return MessageResponse(message="Email verified successfully.")


@router.post(
    "/email/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend email verification link",
    description=(
        "Generates a fresh 24-hour verification link and sends it to the user's email. "
        "Requires an active access token."
    ),
)
async def resend_verification(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await resend_verification_controller(
        session, redis, settings, current_user.id, background_tasks
    )
    return MessageResponse(message="Verification email sent. Please check your inbox.")


# ── Email OTP (6-digit code verification via email) ─────────────────────────

@router.post(
    "/email-otp/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a 6-digit OTP sent via email",
    description=(
        "Sends a 6-digit verification code to the given email address. "
        "Always returns 200 even if the email is not registered (prevents enumeration). "
        "Code expires in 5 minutes."
    ),
)
@limiter.limit("5/10minutes")
async def email_otp_request(
    request: Request,
    body: EmailOTPRequestSchema,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await email_otp_request_controller(session, body, redis, settings, background_tasks)
    return MessageResponse(message="If an account exists for this email, a verification code has been sent.")


@router.post(
    "/email-otp/verify",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify 6-digit email OTP and mark email as verified",
    description=(
        "Validates the 6-digit code sent to the user's email. "
        "On success, marks the email as verified."
    ),
)
async def email_otp_verify(
    body: EmailOTPVerifyRequest,
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    await email_otp_verify_controller(session, redis, body)
    return MessageResponse(message="Email verified successfully.")
