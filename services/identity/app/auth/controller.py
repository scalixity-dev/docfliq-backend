"""
Identity service — auth controller (request orchestration layer).

Responsibilities:
  - Receive validated input from the router.
  - Call service functions (which own business logic).
  - Compose and return the response model.
  - Pass HTTP-layer context (IP, device info) from router to service.

No framework validation logic here — that belongs in schemas.py.
No business logic here — that belongs in service.py.
"""
from __future__ import annotations

import random
import uuid

import redis.asyncio as aioredis
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import OTP_EXPIRE_SECONDS, OTPPurpose, UserRole
from app.auth.schemas import (
    ChangePasswordRequest,
    EmailOTPLoginRequest,
    EmailOTPRequestSchema,
    EmailOTPVerifyRequest,
    LoginRequest,
    LogoutRequest,
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
    UserResponse,
)
from app.auth.service import (
    assert_account_usable,
    authenticate_user,
    change_user_password,
    check_login_lock,
    clear_failed_logins,
    create_access_token,
    create_email_otp_in_redis,
    create_email_verification_token,
    create_otp,
    create_otp_in_redis,
    create_password_reset_link_token,
    create_password_reset_otp,
    create_session,
    find_or_create_oauth_user,
    find_or_create_user_by_email,
    find_or_create_user_by_phone,
    generate_refresh_token,
    get_session_by_refresh_token,
    get_user_by_email,
    get_user_by_id,
    invalidate_session,
    record_failed_login,
    record_login,
    register_user,
    reset_password,
    rotate_session,
    verify_email_otp_from_redis,
    verify_email_token,
    verify_otp,
    verify_otp_from_redis,
    verify_password_reset_link_token,
    verify_password_reset_otp,
)
from app.auth.oauth import (
    exchange_google_code,
    exchange_microsoft_code,
)
from app.config import Settings
from app.email import send as email
from app.exceptions import (
    InvalidCredentials,
    InvalidOTP,
    OTPExhausted,
    SMSDeliveryFailed,
    SessionNotFound,
    UserNotFound,
)
from app.sms import twilio


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_token_pair(
    user_id: uuid.UUID,
    email: str,
    roles: list[str],
    settings: Settings,
) -> tuple[str, str]:
    """Return (access_token, refresh_token)."""
    access_token = create_access_token(
        user_id=user_id,
        email=email,
        roles=roles,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expire_seconds=settings.jwt_expire_seconds,
    )
    refresh_token = generate_refresh_token()
    return access_token, refresh_token


# ── Register ──────────────────────────────────────────────────────────────────

async def register(
    session: AsyncSession,
    body: RegisterRequest,
    settings: Settings,
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> RegisterResponse:
    user = await register_user(
        session,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
        phone_number=body.phone_number,
        specialty=body.specialty,
        sub_specialty=body.sub_specialty,
        years_of_experience=body.years_of_experience,
        medical_license_number=body.medical_license_number,
        hospital_name=body.hospital_name,
        certification=body.certification,
        university=body.university,
        graduation_year=body.graduation_year,
        student_id=body.student_id,
        pharmacist_license_number=body.pharmacist_license_number,
        pharmacy_name=body.pharmacy_name,
    )

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )

    # Send email OTP + verification link in the background (non-blocking)
    plain_otp = f"{random.SystemRandom().randint(100_000, 999_999)}"
    await create_email_otp_in_redis(redis, user.email, plain_otp)
    token = await create_email_verification_token(redis, user.id)
    verify_url = f"{settings.app_base_url}/auth/email/verify?token={token}"
    background_tasks.add_task(
        email.send_email_otp, user.email, user.full_name, plain_otp, settings, verify_url
    )

    return RegisterResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_expire_seconds,
        ),
    )


# ── Login ─────────────────────────────────────────────────────────────────────

async def login(
    session: AsyncSession,
    body: LoginRequest,
    settings: Settings,
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> TokenResponse:
    # Per-account lockout check (30-min lockout after 5 failures)
    await check_login_lock(redis, body.email)

    try:
        user = await authenticate_user(session, body.email, body.password)
    except InvalidCredentials:
        # Increment per-account failure counter; lock and notify if threshold reached
        just_locked = await record_failed_login(redis, body.email)
        if just_locked:
            # Look up the user to get full_name for the email (best-effort; skip if not found)
            target_user = await get_user_by_email(session, body.email)
            if target_user is not None:
                background_tasks.add_task(
                    email.send_account_locked,
                    target_user.email,
                    target_user.full_name,
                    settings,
                )
        raise  # re-raise InvalidCredentials (401) to the client

    # Successful auth — reset failure counter
    await clear_failed_logins(redis, body.email)
    await record_login(session, user)

    # If email not verified, send OTP for verification (frontend shows OTP screen)
    if not user.email_verified:
        plain_otp = f"{random.SystemRandom().randint(100_000, 999_999)}"
        await create_email_otp_in_redis(redis, user.email, plain_otp)
        token = await create_email_verification_token(redis, user.id)
        verify_url = f"{settings.app_base_url}/auth/email/verify?token={token}"
        background_tasks.add_task(
            email.send_email_otp, user.email, user.full_name, plain_otp, settings, verify_url
        )

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── Token refresh ─────────────────────────────────────────────────────────────

async def refresh_token(
    session: AsyncSession,
    body: RefreshRequest,
    settings: Settings,
) -> TokenResponse:
    """
    Rotate the refresh token and issue a new access + refresh pair.

    SessionNotFound is raised (401) if the token is expired or doesn't exist,
    preventing replay attacks on stolen refresh tokens.
    """
    # Look up the session first to get user_id before rotating
    auth_session = await get_session_by_refresh_token(session, body.refresh_token)
    if auth_session is None:
        raise SessionNotFound()

    user = await get_user_by_id(session, auth_session.user_id)
    if user is None:
        raise SessionNotFound()  # treat deleted-user sessions as invalid (401, not 404)
    assert_account_usable(user)  # enforce ban/inactive/suspended on every token rotation

    new_refresh_token = generate_refresh_token()
    new_access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expire_seconds=settings.jwt_expire_seconds,
    )
    await rotate_session(
        session,
        old_refresh_token=body.refresh_token,
        new_refresh_token=new_refresh_token,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── Logout ────────────────────────────────────────────────────────────────────

async def logout(
    session: AsyncSession,
    body: LogoutRequest,
) -> None:
    """Invalidate the given session (logout from one device)."""
    await invalidate_session(session, body.refresh_token)


# ── OTP: request ─────────────────────────────────────────────────────────────

async def otp_request(
    session: AsyncSession,
    body: OTPRequestSchema,
    redis: aioredis.Redis,
    settings: Settings,
) -> None:
    """
    Send a 6-digit OTP via SMS to the given phone number.

    Provider strategy:
      1. Twilio Verify (production) — Twilio generates the OTP, sends SMS,
         and owns the verification lifecycle.  Nothing stored locally.
      2. Redis / PostgreSQL (development) — we generate the OTP ourselves
         and store it locally.  No SMS is sent.
    """
    if twilio.is_configured(settings):
        sent = await twilio.send_otp(body.phone_number, settings)
        if not sent:
            raise SMSDeliveryFailed()
        return

    # Dev fallback: generate + store OTP locally (no SMS sent)
    plain_otp = f"{random.SystemRandom().randint(100_000, 999_999)}"
    try:
        await create_otp_in_redis(redis, body.phone_number, plain_otp)
    except Exception:
        await create_otp(
            session,
            phone_number=body.phone_number,
            plain_otp=plain_otp,
            purpose=OTPPurpose.LOGIN,
            expire_seconds=OTP_EXPIRE_SECONDS,
        )


# ── Password reset ────────────────────────────────────────────────────────────

async def password_reset_request(
    session: AsyncSession,
    body: PasswordResetRequestSchema,
    settings: Settings,
    background_tasks: BackgroundTasks,
    redis: aioredis.Redis,
) -> None:
    """
    Generate a 6-digit OTP (15 min) AND a reset link token (1 hour), then
    send a single email containing both options.

    Always returns successfully — even for unknown emails — to prevent
    account enumeration. Tokens are only stored and emailed if the account exists.
    """
    plain_otp = f"{random.SystemRandom().randint(100_000, 999_999)}"
    user = await get_user_by_email(session, body.email)
    if user is not None:
        await create_password_reset_otp(
            session, email=body.email, plain_otp=plain_otp
        )
        link_token = await create_password_reset_link_token(redis, body.email)
        reset_link = f"{settings.app_base_url}/auth/reset-password?token={link_token}"
        background_tasks.add_task(
            email.send_password_reset_otp,
            body.email,
            user.full_name,
            plain_otp,
            settings,
            reset_link,
        )


async def password_reset_confirm(
    session: AsyncSession,
    body: PasswordResetConfirmSchema,
) -> None:
    """Verify the reset OTP, update password, and invalidate all sessions."""
    await verify_password_reset_otp(
        session, email=body.email, plain_otp=body.otp_code
    )
    await reset_password(session, email=body.email, new_password=body.new_password)


async def password_reset_confirm_link(
    session: AsyncSession,
    redis: aioredis.Redis,
    body: PasswordResetLinkConfirmSchema,
) -> None:
    """Validate the 1-hour link token, update password, and invalidate all sessions."""
    await verify_password_reset_link_token(
        session, redis, body.token, body.new_password
    )


# ── Email verification ────────────────────────────────────────────────────────

async def verify_email(
    session: AsyncSession,
    redis: aioredis.Redis,
    token: str,
) -> None:
    """Validate the email verification token and mark the user's email as verified."""
    await verify_email_token(session, redis, token)


async def resend_verification(
    session: AsyncSession,
    redis: aioredis.Redis,
    settings: Settings,
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
) -> None:
    """
    Generate a fresh email verification token and resend the verification email.

    The previous token stays valid until its TTL runs out (24h), but the new
    one is the one users will typically use (most recent email is clicked).
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFound()
    token = await create_email_verification_token(redis, user.id)
    verify_url = f"{settings.app_base_url}/auth/email/verify?token={token}"
    background_tasks.add_task(
        email.send_email_verification, user.email, user.full_name, verify_url, settings
    )


# ── OTP: verify ──────────────────────────────────────────────────────────────

async def otp_verify(
    session: AsyncSession,
    body: OTPVerifyRequest,
    settings: Settings,
    redis: aioredis.Redis,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> TokenResponse:
    """
    Verify OTP, find-or-create the user, and issue a token pair.

    Provider strategy:
      1. Twilio Verify (production) — code checked by Twilio's API.
      2. Redis / PostgreSQL (development) — code checked against local store.

    For first-time registration full_name and role are required in the body.
    """
    if twilio.is_configured(settings):
        approved = await twilio.check_otp(body.phone_number, body.otp_code, settings)
        if not approved:
            raise InvalidOTP(attempts_remaining=0)
    else:
        try:
            await verify_otp_from_redis(redis, body.phone_number, body.otp_code)
        except (OTPExhausted, InvalidOTP):
            raise
        except Exception:
            await verify_otp(
                session,
                phone_number=body.phone_number,
                plain_otp=body.otp_code,
                purpose=OTPPurpose.LOGIN,
            )

    full_name = body.full_name or "Unknown"
    role = body.role or UserRole.NON_PHYSICIAN

    user, _ = await find_or_create_user_by_phone(
        session,
        body.phone_number,
        full_name=full_name,
        role=role,
    )
    await record_login(session, user)

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── Email OTP: request ──────────────────────────────────────────────────────

async def email_otp_request(
    session: AsyncSession,
    body: EmailOTPRequestSchema,
    redis: aioredis.Redis,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> None:
    """
    Generate a 6-digit OTP, store in Redis, and send to the user's email.

    Always returns 200 even for unknown emails (prevents enumeration).
    """
    plain_otp = f"{random.SystemRandom().randint(100_000, 999_999)}"
    user = await get_user_by_email(session, body.email)
    if user is not None:
        await create_email_otp_in_redis(redis, body.email, plain_otp)
        # Also create a verification link as fallback
        token = await create_email_verification_token(redis, user.id)
        verify_url = f"{settings.app_base_url}/auth/email/verify?token={token}"
        background_tasks.add_task(
            email.send_email_otp, user.email, user.full_name, plain_otp, settings, verify_url
        )


# ── Email OTP: verify ───────────────────────────────────────────────────────

async def email_otp_verify(
    session: AsyncSession,
    redis: aioredis.Redis,
    body: EmailOTPVerifyRequest,
) -> None:
    """
    Verify the 6-digit email OTP and mark the user's email as verified.

    Raises OTPExpired / OTPExhausted / InvalidOTP on failure.
    """
    await verify_email_otp_from_redis(redis, body.email, body.otp_code)
    # Mark email as verified
    user = await get_user_by_email(session, body.email)
    if user is not None:
        user.email_verified = True
        await session.flush()


# ── OAuth: Google ──────────────────────────────────────────────────────────

async def oauth_google(
    session: AsyncSession,
    body: OAuthCallbackRequest,
    settings: Settings,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> TokenResponse:
    """
    Exchange a Google authorization code for user info, find-or-create the
    user, and issue a JWT token pair.
    """
    user_info = await exchange_google_code(
        code=body.code,
        redirect_uri=body.redirect_uri,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )

    user, _ = await find_or_create_oauth_user(
        session,
        provider=user_info.provider,
        provider_id=user_info.provider_id,
        email=user_info.email,
        full_name=user_info.full_name,
        picture_url=user_info.picture_url,
        email_verified=user_info.email_verified,
    )
    await record_login(session, user)

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── OAuth: Microsoft ──────────────────────────────────────────────────────

async def oauth_microsoft(
    session: AsyncSession,
    body: OAuthCallbackRequest,
    settings: Settings,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> TokenResponse:
    """
    Exchange a Microsoft authorization code for user info, find-or-create the
    user, and issue a JWT token pair.
    """
    user_info = await exchange_microsoft_code(
        code=body.code,
        redirect_uri=body.redirect_uri,
        client_id=settings.microsoft_client_id,
        client_secret=settings.microsoft_client_secret,
    )

    user, _ = await find_or_create_oauth_user(
        session,
        provider=user_info.provider,
        provider_id=user_info.provider_id,
        email=user_info.email,
        full_name=user_info.full_name,
        picture_url=user_info.picture_url,
        email_verified=user_info.email_verified,
    )
    await record_login(session, user)

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── Email OTP: login ─────────────────────────────────────────────────────────

async def email_otp_login(
    session: AsyncSession,
    body: EmailOTPLoginRequest,
    settings: Settings,
    redis: aioredis.Redis,
    *,
    ip_address: str | None = None,
    device_id: str | None = None,
    device_info: dict | None = None,
) -> TokenResponse:
    """
    Verify email OTP, find-or-create the user, and issue a token pair.

    Mirrors the phone OTP verify flow but for email-based OTP.
    """
    await verify_email_otp_from_redis(redis, body.email, body.otp_code)

    full_name = body.full_name or "Unknown"
    role = body.role or UserRole.NON_PHYSICIAN

    user, _ = await find_or_create_user_by_email(
        session,
        body.email,
        full_name=full_name,
        role=role,
    )
    await record_login(session, user)

    access_token, refresh_token = _build_token_pair(
        user.id, user.email, user.roles, settings
    )
    await create_session(
        session,
        user_id=user.id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expire_seconds=settings.jwt_refresh_expire_seconds,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_seconds,
    )


# ── Change password (authenticated) ─────────────────────────────────────────

async def change_password(
    session: AsyncSession,
    body: ChangePasswordRequest,
    user_id: uuid.UUID,
) -> None:
    """Verify the current password and update to the new one."""
    await change_user_password(
        session,
        user_id=user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
