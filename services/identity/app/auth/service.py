"""
Identity service — pure business logic for authentication.

Rules:
  - Zero FastAPI imports.
  - Zero direct DB driver calls — only SQLAlchemy async session.
  - All I/O functions are async def.
  - No side effects beyond the session passed in (no global state mutated).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    EMAIL_VERIFY_EXPIRE_SECONDS,
    MAX_SESSIONS_PER_USER,
    OTP_EXPIRE_SECONDS,
    OTPPurpose,
    PASSWORD_RESET_LINK_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    UserRole,
    VerificationStatus,
)
from app.auth.models import AuthSession, OTPRequest, PasswordResetToken, User
from app.auth.utils import hash_password, verify_password
import redis.asyncio as aioredis

from app.exceptions import (
    AccountLocked,
    InvalidCredentials,
    InvalidOTP,
    OTPExhausted,
    OTPExpired,
    PhoneAlreadyExists,
    SessionNotFound,
    TokenInvalid,
    UserAlreadyExists,
    UserBanned,
    UserInactive,
    UserNotFound,
    UserSuspended,
)
from shared.constants import Role


# ── User queries ──────────────────────────────────────────────────────────────

async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    # Case-insensitive match so that password reset links (which normalize to lowercase)
    # still find users who registered with mixed-case email addresses.
    result = await session.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_phone(
    session: AsyncSession, phone_number: str
) -> User | None:
    result = await session.execute(
        select(User).where(User.phone_number == phone_number)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(
    session: AsyncSession, user_id: uuid.UUID
) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Guard: ensure account is usable ──────────────────────────────────────────

def assert_account_usable(user: User) -> None:
    """
    Raise the appropriate HTTP exception for any account-level block.

    Call this after every successful credential verification to surface the
    most specific error rather than a generic 401.
    Also called on token refresh so that bans/deactivations take effect
    immediately without waiting for the 7-day refresh token to expire.
    """
    if user.is_banned:
        raise UserBanned()
    if not user.is_active:
        raise UserInactive()
    if user.verification_status == VerificationStatus.SUSPENDED:
        raise UserSuspended()


# ── Registration (email + password) ──────────────────────────────────────────

async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
    phone_number: str | None = None,
    specialty: str | None = None,
    sub_specialty: str | None = None,
    years_of_experience: int | None = None,
    medical_license_number: str | None = None,
    hospital_name: str | None = None,
    certification: str | None = None,
    university: str | None = None,
    graduation_year: int | None = None,
    student_id: str | None = None,
    pharmacist_license_number: str | None = None,
    pharmacy_name: str | None = None,
) -> User:
    """
    Create a new user account via email + password.

    Guard clauses (uniqueness checks) run first — the happy path is last.
    Uses flush() so the caller can use user.id without committing.
    """
    if await get_user_by_email(session, email) is not None:
        raise UserAlreadyExists()

    if phone_number and await get_user_by_phone(session, phone_number) is not None:
        raise PhoneAlreadyExists()

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        phone_number=phone_number,
        specialty=specialty,
        sub_specialty=sub_specialty,
        years_of_experience=years_of_experience,
        medical_license_number=medical_license_number,
        hospital_name=hospital_name,
        certification=certification,
        university=university,
        graduation_year=graduation_year,
        student_id=student_id,
        pharmacist_license_number=pharmacist_license_number,
        pharmacy_name=pharmacy_name,
        roles=[Role.USER.value],
    )
    session.add(user)
    await session.flush()
    return user


# ── Authentication (email + password) ────────────────────────────────────────

async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    """
    Verify credentials and return the User.

    Deliberately generic error on bad credentials to prevent email enumeration.
    Account state (banned / inactive / suspended) is checked separately to give
    the user a specific, actionable message.
    """
    user = await get_user_by_email(session, email)
    # Guard: unknown email or no password (OTP-only account) → same generic error
    if user is None or user.password_hash is None:
        raise InvalidCredentials()
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    assert_account_usable(user)
    return user


# ── JWT access token ──────────────────────────────────────────────────────────

def create_access_token(
    user_id: uuid.UUID,
    email: str,
    roles: list[str],
    secret: str,
    algorithm: str,
    issuer: str,
    audience: str,
    expire_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(seconds=expire_seconds),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


# ── Refresh token ─────────────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """Return a cryptographically secure opaque 64-byte URL-safe token."""
    return secrets.token_urlsafe(64)


# ── Session management ────────────────────────────────────────────────────────

async def _count_user_sessions(
    session: AsyncSession, user_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count()).select_from(AuthSession).where(
            AuthSession.user_id == user_id
        )
    )
    return result.scalar_one()


async def _evict_oldest_session(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """Delete the session with the earliest created_at for this user (FIFO)."""
    result = await session.execute(
        select(AuthSession)
        .where(AuthSession.user_id == user_id)
        .order_by(AuthSession.created_at.asc())
        .limit(1)
    )
    oldest = result.scalar_one_or_none()
    if oldest is not None:
        await session.delete(oldest)


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    refresh_token: str,
    device_id: str | None = None,
    device_info: dict | None = None,
    ip_address: str | None = None,
    expire_seconds: int = REFRESH_TOKEN_EXPIRE_SECONDS,
) -> AuthSession:
    """
    Persist a new session and enforce the per-user session cap.

    If the user already has MAX_SESSIONS_PER_USER active sessions, the oldest
    one is evicted before the new one is inserted (FIFO eviction, per MS-1 spec).
    """
    count = await _count_user_sessions(session, user_id)
    if count >= MAX_SESSIONS_PER_USER:
        await _evict_oldest_session(session, user_id)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
    auth_session = AuthSession(
        user_id=user_id,
        refresh_token=refresh_token,
        device_id=device_id,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )
    session.add(auth_session)
    await session.flush()
    return auth_session


async def get_session_by_refresh_token(
    session: AsyncSession, refresh_token: str
) -> AuthSession | None:
    """Return the session only if it exists and has not expired."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(AuthSession).where(
            AuthSession.refresh_token == refresh_token,
            AuthSession.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def rotate_session(
    session: AsyncSession,
    *,
    old_refresh_token: str,
    new_refresh_token: str,
    expire_seconds: int = REFRESH_TOKEN_EXPIRE_SECONDS,
) -> AuthSession:
    """
    Token rotation: replace old refresh token with a new one atomically.

    Raises SessionNotFound if the old token is missing or expired, which
    prevents replay attacks on stolen refresh tokens.
    """
    auth_session = await get_session_by_refresh_token(session, old_refresh_token)
    if auth_session is None:
        raise SessionNotFound()

    auth_session.refresh_token = new_refresh_token
    auth_session.expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=expire_seconds
    )
    await session.flush()
    return auth_session


async def invalidate_session(
    session: AsyncSession, refresh_token: str
) -> None:
    """Delete a specific session (logout from one device)."""
    auth_session = await get_session_by_refresh_token(session, refresh_token)
    if auth_session is not None:
        await session.delete(auth_session)


async def invalidate_all_user_sessions(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """Delete every session for a user (password change, ban, or admin action)."""
    await session.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id)
    )


# ── Audit: last login ─────────────────────────────────────────────────────────

async def record_login(session: AsyncSession, user: User) -> None:
    """Stamp last_login_at without ending the transaction."""
    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()


# ── OTP ───────────────────────────────────────────────────────────────────────

async def _get_active_otp(
    session: AsyncSession,
    phone_number: str,
    purpose: OTPPurpose,
) -> OTPRequest | None:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(OTPRequest).where(
            OTPRequest.phone_number == phone_number,
            OTPRequest.purpose == purpose,
            OTPRequest.is_used.is_(False),
            OTPRequest.expires_at > now,
            OTPRequest.attempts_remaining > 0,
        )
    )
    return result.scalar_one_or_none()


async def create_otp(
    session: AsyncSession,
    *,
    phone_number: str,
    plain_otp: str,
    purpose: OTPPurpose,
    expire_seconds: int,
) -> OTPRequest:
    """
    Store a hashed OTP record.

    Any existing active (unexpired, unused) OTPs for the same phone+purpose are
    invalidated first — this prevents MultipleResultsFound on verify and stops
    users from replaying an older code after requesting a new one.
    The plain_otp must be sent to the user via SMS (Twilio) by the caller.
    """
    now = datetime.now(timezone.utc)
    await session.execute(
        update(OTPRequest)
        .where(
            OTPRequest.phone_number == phone_number,
            OTPRequest.purpose == purpose,
            OTPRequest.is_used.is_(False),
            OTPRequest.expires_at > now,
        )
        .values(is_used=True)
    )
    expires_at = now + timedelta(seconds=expire_seconds)
    otp = OTPRequest(
        phone_number=phone_number,
        otp_code=hash_password(plain_otp),
        purpose=purpose,
        expires_at=expires_at,
    )
    session.add(otp)
    await session.flush()
    return otp


async def verify_otp(
    session: AsyncSession,
    *,
    phone_number: str,
    plain_otp: str,
    purpose: OTPPurpose,
) -> None:
    """
    Validate the OTP and mark it used, or decrement remaining attempts.

    Raises:
      OTPExpired   — no active (unexpired, unused) OTP found for this number
      OTPExhausted — OTP exists but all attempts have been consumed
      InvalidOTP   — code is wrong; attempts_remaining is decremented
    """
    otp = await _get_active_otp(session, phone_number, purpose)
    if otp is None:
        raise OTPExpired()

    if not verify_password(plain_otp, otp.otp_code):
        otp.attempts_remaining -= 1
        await session.flush()
        if otp.attempts_remaining <= 0:
            raise OTPExhausted()
        raise InvalidOTP(attempts_remaining=otp.attempts_remaining)

    # Correct code — mark single-use consumed
    otp.is_used = True
    await session.flush()


# ── OTP in Redis (primary) with PostgreSQL as fallback ────────────────────────

_OTP_REDIS_PREFIX = "otp:"
_OTP_TRIES_PREFIX = "otp_tries:"
_OTP_MAX_REDIS_ATTEMPTS = 5


async def create_otp_in_redis(
    redis: aioredis.Redis,
    phone_number: str,
    plain_otp: str,
    expire_seconds: int = OTP_EXPIRE_SECONDS,
) -> None:
    """
    Store the plain OTP and a zeroed attempt counter in Redis.

    Uses a pipeline so both keys are written atomically. A new call for the
    same phone number overwrites the previous OTP (implicit invalidation).
    The caller must send plain_otp to the user via SMS.
    """
    pipe = redis.pipeline()
    pipe.setex(f"{_OTP_REDIS_PREFIX}{phone_number}", expire_seconds, plain_otp)
    pipe.setex(f"{_OTP_TRIES_PREFIX}{phone_number}", expire_seconds, "0")
    await pipe.execute()


async def verify_otp_from_redis(
    redis: aioredis.Redis,
    phone_number: str,
    plain_otp: str,
) -> None:
    """
    Validate the OTP stored in Redis.

    Raises:
      OTPExpired   — key not found (TTL elapsed or OTP was never created here)
      OTPExhausted — attempt counter reached _OTP_MAX_REDIS_ATTEMPTS
      InvalidOTP   — code is wrong; attempt counter incremented
    On success the OTP and attempt keys are deleted (single-use).
    """
    stored = await redis.get(f"{_OTP_REDIS_PREFIX}{phone_number}")
    if stored is None:
        raise OTPExpired()

    tries_raw = await redis.get(f"{_OTP_TRIES_PREFIX}{phone_number}")
    tries = int(tries_raw or 0)
    if tries >= _OTP_MAX_REDIS_ATTEMPTS:
        raise OTPExhausted()

    if not secrets.compare_digest(stored, plain_otp):
        await redis.incr(f"{_OTP_TRIES_PREFIX}{phone_number}")
        remaining = _OTP_MAX_REDIS_ATTEMPTS - tries - 1
        if remaining <= 0:
            raise OTPExhausted()
        raise InvalidOTP(attempts_remaining=remaining)

    # Correct code — single-use: delete both keys immediately
    await redis.delete(
        f"{_OTP_REDIS_PREFIX}{phone_number}",
        f"{_OTP_TRIES_PREFIX}{phone_number}",
    )


# ── Password reset ────────────────────────────────────────────────────────────

async def _get_active_reset_token(
    session: AsyncSession,
    email: str,
) -> PasswordResetToken | None:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.email == email,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expires_at > now,
            PasswordResetToken.attempts_remaining > 0,
        )
    )
    return result.scalar_one_or_none()


async def create_password_reset_otp(
    session: AsyncSession,
    *,
    email: str,
    plain_otp: str,
    expire_seconds: int = OTP_EXPIRE_SECONDS,
) -> PasswordResetToken:
    """
    Store a hashed password reset OTP keyed by email.

    Any existing active (unexpired, unused) tokens for the same email are
    invalidated first to prevent replay of an older code.
    The plain_otp must be sent to the user via email by the caller.
    """
    now = datetime.now(timezone.utc)
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.email == email,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expires_at > now,
        )
        .values(is_used=True)
    )
    token = PasswordResetToken(
        email=email,
        token_hash=hash_password(plain_otp),
        expires_at=now + timedelta(seconds=expire_seconds),
    )
    session.add(token)
    await session.flush()
    return token


async def verify_password_reset_otp(
    session: AsyncSession,
    *,
    email: str,
    plain_otp: str,
) -> None:
    """
    Validate the reset OTP and mark it used, or decrement remaining attempts.

    Raises:
      OTPExpired   — no active (unexpired, unused) token found for this email
      OTPExhausted — all attempts consumed
      InvalidOTP   — wrong code; attempts_remaining is decremented
    """
    token = await _get_active_reset_token(session, email)
    if token is None:
        raise OTPExpired()

    if not verify_password(plain_otp, token.token_hash):
        token.attempts_remaining -= 1
        await session.flush()
        if token.attempts_remaining <= 0:
            raise OTPExhausted()
        raise InvalidOTP(attempts_remaining=token.attempts_remaining)

    # Correct code — mark single-use consumed
    token.is_used = True
    await session.flush()


async def reset_password(
    session: AsyncSession,
    *,
    email: str,
    new_password: str,
) -> None:
    """
    Update the user's password hash and invalidate all sessions.

    Raises UserNotFound if the email has no account.
    (OTP was already verified by the caller, so the email is trusted.
    This guard handles the edge case where the account was deleted between
    the OTP request and the confirm call.)
    """
    user = await get_user_by_email(session, email)
    if user is None:
        raise UserNotFound()
    user.password_hash = hash_password(new_password)
    await session.flush()
    # Invalidate all sessions — forces re-login on all devices after a password change
    await invalidate_all_user_sessions(session, user.id)


# ── Password reset link (Redis-backed, 1h TTL) ────────────────────────────────

_PWD_RESET_LINK_PREFIX = "pwd_reset_link:"


async def create_password_reset_link_token(
    redis: aioredis.Redis,
    email: str,
    expire_seconds: int = PASSWORD_RESET_LINK_EXPIRE_SECONDS,
) -> str:
    """
    Generate a URL-safe token for link-based password reset and store it in
    Redis with a 1-hour TTL.  The token maps to the lowercased email address.

    Generating a new token does not invalidate previous tokens for the same
    email (would require a reverse lookup); the 1-hour TTL keeps the exposure
    window short.
    """
    token = secrets.token_urlsafe(32)
    await redis.setex(
        f"{_PWD_RESET_LINK_PREFIX}{token}",
        expire_seconds,
        email.lower(),
    )
    return token


async def verify_password_reset_link_token(
    session: AsyncSession,
    redis: aioredis.Redis,
    token: str,
    new_password: str,
) -> None:
    """
    Validate the link token, reset the password, and delete the token
    (single-use).  Raises TokenInvalid if the token is missing or expired.
    """
    email = await redis.get(f"{_PWD_RESET_LINK_PREFIX}{token}")
    if email is None:
        raise TokenInvalid()
    # Delete immediately — single-use even if reset_password fails
    await redis.delete(f"{_PWD_RESET_LINK_PREFIX}{token}")
    await reset_password(session, email=email, new_password=new_password)


async def find_or_create_user_by_phone(
    session: AsyncSession,
    phone_number: str,
    *,
    full_name: str,
    role: UserRole,
) -> tuple[User, bool]:
    """
    Return (user, is_new_user).

    Called by the OTP verify endpoint after a successful OTP check.
    For returning users, full_name and role are ignored.
    """
    user = await get_user_by_phone(session, phone_number)
    if user is not None:
        assert_account_usable(user)
        return user, False

    # First-time OTP registration — create account
    new_user = User(
        # Placeholder email; user must set a real one via profile update
        email=f"otp_{phone_number.lstrip('+')}@placeholder.docfliq.internal",
        phone_number=phone_number,
        full_name=full_name,
        role=role,
        roles=[Role.USER.value],
    )
    session.add(new_user)
    await session.flush()
    return new_user, True


# ── Email verification (Redis-backed, 24h TTL) ────────────────────────────────

_EMAIL_VERIFY_PREFIX = "email_verify:"


async def create_email_verification_token(
    redis: aioredis.Redis,
    user_id: uuid.UUID,
    expire_seconds: int = EMAIL_VERIFY_EXPIRE_SECONDS,
) -> str:
    """
    Generate a URL-safe token, store user_id in Redis with a TTL, and return
    the token for inclusion in the verification link.

    Any previous token for the same user is implicitly superseded because the
    new token holds a fresh TTL. The old token will still work until it expires
    naturally; invalidating it explicitly would require a reverse lookup which
    adds complexity for minimal security gain (24h TTL is short enough).
    """
    token = secrets.token_urlsafe(32)
    await redis.setex(
        f"{_EMAIL_VERIFY_PREFIX}{token}",
        expire_seconds,
        str(user_id),
    )
    return token


async def verify_email_token(
    session: AsyncSession,
    redis: aioredis.Redis,
    token: str,
) -> User:
    """
    Validate the email verification token, mark the user's email as verified,
    and delete the token from Redis (single-use).

    Raises TokenInvalid if the token is missing, malformed, or expired.
    Raises UserNotFound if the user_id stored in Redis has no matching account.
    """
    raw = await redis.get(f"{_EMAIL_VERIFY_PREFIX}{token}")
    if raw is None:
        raise TokenInvalid()

    try:
        user_id = uuid.UUID(raw)
    except ValueError:
        raise TokenInvalid()

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFound()

    user.email_verified = True
    await session.flush()
    await redis.delete(f"{_EMAIL_VERIFY_PREFIX}{token}")
    return user


# ── Login lockout (Redis-backed, per-account) ─────────────────────────────────

_LOGIN_FAIL_PREFIX = "login_fails:"
_LOGIN_LOCK_PREFIX = "login_lock:"
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_FAIL_TTL = 900    # 15 min — same window as slowapi IP rate limit
_LOGIN_LOCK_TTL = 1800   # 30 min lockout per spec


async def check_login_lock(redis: aioredis.Redis, email: str) -> None:
    """Raise AccountLocked (403) if the account is currently in lockout."""
    locked = await redis.get(f"{_LOGIN_LOCK_PREFIX}{email.lower()}")
    if locked is not None:
        raise AccountLocked()


async def record_failed_login(
    redis: aioredis.Redis,
    email: str,
) -> bool:
    """
    Increment the per-account failure counter.

    Returns True if the account just crossed the threshold (caller should send
    the lockout email notification). The caller is responsible for sending the
    email because it needs BackgroundTasks (a FastAPI dependency).
    """
    key_fails = f"{_LOGIN_FAIL_PREFIX}{email.lower()}"
    key_lock = f"{_LOGIN_LOCK_PREFIX}{email.lower()}"

    count = await redis.incr(key_fails)
    if count == 1:
        # First failure — set the expiry window
        await redis.expire(key_fails, _LOGIN_FAIL_TTL)

    if count >= _LOGIN_MAX_ATTEMPTS:
        # Lock the account
        await redis.setex(key_lock, _LOGIN_LOCK_TTL, "1")
        await redis.delete(key_fails)
        return True  # caller should send lockout email

    return False


async def clear_failed_logins(redis: aioredis.Redis, email: str) -> None:
    """Reset the failure counter on successful login."""
    await redis.delete(f"{_LOGIN_FAIL_PREFIX}{email.lower()}")
