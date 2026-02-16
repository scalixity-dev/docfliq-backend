from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.auth.service import (
    authenticate_user,
    create_access_token,
    register_user,
)
from app.config import Settings


async def register(
    session: AsyncSession,
    body: RegisterRequest,
    settings: Settings,
) -> TokenResponse:
    user = await register_user(session, body.email, body.password)
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expire_seconds=settings.jwt_expire_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_seconds)


async def login(
    session: AsyncSession,
    body: LoginRequest,
    settings: Settings,
) -> TokenResponse:
    user = await authenticate_user(session, body.email, body.password)
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expire_seconds=settings.jwt_expire_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_seconds)
