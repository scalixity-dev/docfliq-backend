import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import ACCESS_TOKEN_EXPIRE_SECONDS
from app.auth.models import User
from app.auth.utils import hash_password, verify_password
from app.exceptions import InvalidCredentials, UserAlreadyExists
from shared.constants import Role


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    existing = await get_user_by_email(session, email)
    if existing is not None:
        raise UserAlreadyExists()
    user = User(
        email=email,
        password_hash=hash_password(password),
        roles=[Role.USER.value],
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    user = await get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    if not user.is_active:
        raise InvalidCredentials()
    return user


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
