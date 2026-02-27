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
    change_password as change_password_controller,
    email_otp_login as email_otp_login_controller,
    email_otp_request as email_otp_request_controller,
    email_otp_verify as email_otp_verify_controller,
    login as login_controller,
    logout as logout_controller,
    oauth_google as oauth_google_controller,
    oauth_microsoft as oauth_microsoft_controller,
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
    ChangePasswordRequest,
    EmailOTPLoginRequest,
    EmailOTPRequestSchema,
    EmailOTPVerifyRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    OAuthCallbackRequest,
    OTPRequestSchema,
    OTPVerifyRequest,
    PasswordResetConfirmSchema,
    PasswordResetLinkConfirmSchema,
    PasswordResetRequestSchema,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    DeleteUserRequest,
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
    "/check-user",
    response_model=dict,
    summary="Check if user exists by email or phone",
)
@limiter.limit("10/minute")
async def check_user(
    request: Request,
    body: dict,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Check if a user already exists by email or phone number.
    Returns {email_exists: bool, phone_exists: bool}
    """
    from app.auth.service import get_user_by_email, get_user_by_phone
    
    email = body.get("email", "").lower().strip()
    phone_number = body.get("phone_number", "").strip()
    
    email_exists = False
    phone_exists = False
    
    if email:
        user = await get_user_by_email(session, email)
        email_exists = user is not None
    
    if phone_number:
        user = await get_user_by_phone(session, phone_number)
        phone_exists = user is not None
    
    return {"email_exists": email_exists, "phone_exists": phone_exists}


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


@router.post(
    "/email-otp/login",
    response_model=TokenResponse,
    summary="Verify email OTP and authenticate (creates account on first use)",
    description=(
        "Verifies the 6-digit email OTP, finds or creates the user account, "
        "and returns a JWT token pair. For first-time registration, "
        "full_name and role are optional (defaults applied)."
    ),
)
async def email_otp_login(
    request: Request,
    body: EmailOTPLoginRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
    redis: aioredis.Redis = Depends(_get_redis),
) -> TokenResponse:
    return await email_otp_login_controller(
        session,
        body,
        settings,
        redis,
        ip_address=_client_ip(request),
    )


# ── OAuth SSO ────────────────────────────────────────────────────────────────

@router.post(
    "/oauth/google",
    response_model=TokenResponse,
    summary="Authenticate via Google OAuth (authorization code exchange)",
    description=(
        "Exchange a Google authorization code for user info, find-or-create "
        "the user account, and return a JWT token pair. "
        "If the email matches an existing account, the Google identity is linked to it."
    ),
)
@limiter.limit("10/minute")
async def oauth_google(
    request: Request,
    body: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> TokenResponse:
    return await oauth_google_controller(
        session,
        body,
        settings,
        ip_address=_client_ip(request),
    )


@router.post(
    "/oauth/microsoft",
    response_model=TokenResponse,
    summary="Authenticate via Microsoft OAuth (authorization code exchange)",
    description=(
        "Exchange a Microsoft authorization code for user info, find-or-create "
        "the user account, and return a JWT token pair. "
        "If the email matches an existing account, the Microsoft identity is linked to it."
    ),
)
@limiter.limit("10/minute")
async def oauth_microsoft(
    request: Request,
    body: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_get_settings),
) -> TokenResponse:
    return await oauth_microsoft_controller(
        session,
        body,
        settings,
        ip_address=_client_ip(request),
    )


# ── Change password (authenticated) ──────────────────────────────────────────

@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password (authenticated)",
    description=(
        "Verifies the current password and updates to the new one. "
        "Requires a valid access token."
    ),
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await change_password_controller(session, body, current_user.id)
    return MessageResponse(message="Password changed successfully.")


# ── Debug / Admin Utility ─────────────────────────────────────────────────────

@router.post(
    "/delete-user",
    response_model=MessageResponse,
    summary="[DEBUG/ADMIN] Delete a user entirely by email or phone",
)
async def delete_user_route(
    body: DeleteUserRequest,
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(_get_redis),
) -> MessageResponse:
    from app.auth.service import get_user_by_email, get_user_by_phone
    from app.auth.models import AuthSession, OTPRequest, PasswordResetToken
    from fastapi import HTTPException
    from sqlalchemy import delete

    if not body.email and not body.phone_number:
        raise HTTPException(status_code=400, detail="Must provide email or phone_number")

    user = None
    if body.email:
        user = await get_user_by_email(session, body.email)
    elif body.phone_number:
        user = await get_user_by_phone(session, body.phone_number)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cascade delete all related data manually to ensure complete removal
    user_id = user.id

    # Delete auth sessions
    await session.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id)
    )

    # Delete social graph relationships (follows, blocks, mutes where user is either party)
    from app.social_graph.models import Follow, Block, Mute
    await session.execute(
        delete(Follow).where((Follow.follower_id == user_id) | (Follow.following_id == user_id))
    )
    await session.execute(
        delete(Block).where((Block.blocker_id == user_id) | (Block.blocked_id == user_id))
    )
    await session.execute(
        delete(Mute).where((Mute.muter_id == user_id) | (Mute.muted_id == user_id))
    )

    # Delete reports made by user
    from app.social_graph.models import Report
    await session.execute(
        delete(Report).where(Report.reporter_id == user_id)
    )

    # Delete verification documents
    from app.verification.models import UserVerification
    await session.execute(
        delete(UserVerification).where(UserVerification.user_id == user_id)
    )

    # Delete OTP requests (only if user has a phone number)
    if user.phone_number:
        await session.execute(
            delete(OTPRequest).where(OTPRequest.phone_number == user.phone_number)
        )

    # Delete password reset tokens (only if user has an email)
    if user.email:
        await session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.email == user.email)
        )

    # Clean up Redis keys (OTPs, login locks, email verification)
    redis_keys_to_delete = []
    if user.phone_number:
        redis_keys_to_delete.extend([
            f"otp:{user.phone_number}",
            f"otp_tries:{user.phone_number}",
        ])
    if user.email:
        email_lower = user.email.lower()
        redis_keys_to_delete.extend([
            f"email_otp:{email_lower}",
            f"email_otp_tries:{email_lower}",
            f"login_fails:{email_lower}",
            f"login_lock:{email_lower}",
        ])
    if redis_keys_to_delete:
        await redis.delete(*redis_keys_to_delete)

    # Finally delete the user (get_db commits at request end)
    await session.delete(user)

    identifier = body.email or body.phone_number
    return MessageResponse(
        message=f"User {identifier} and all associated data completely deleted. "
        "Note: Content in other services (media, content) may require separate cleanup."
    )
