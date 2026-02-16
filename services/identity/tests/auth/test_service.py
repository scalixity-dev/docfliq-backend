import pytest
from uuid import uuid4

from app.auth.service import register_user, authenticate_user, get_user_by_email
from app.exceptions import UserAlreadyExists, InvalidCredentials
from shared.constants import Role


@pytest.mark.asyncio
async def test_register_user(db_session) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    db_session: AsyncSession = db_session
    user = await register_user(db_session, "svc@example.com", "secret123")
    assert user.email == "svc@example.com"
    assert user.roles == [Role.USER.value]
    assert user.password_hash != "secret123"


@pytest.mark.asyncio
async def test_register_duplicate_raises(db_session) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    db_session: AsyncSession = db_session
    await register_user(db_session, "dup@example.com", "pass")
    with pytest.raises(UserAlreadyExists):
        await register_user(db_session, "dup@example.com", "other")


@pytest.mark.asyncio
async def test_authenticate_user(db_session) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    db_session: AsyncSession = db_session
    await register_user(db_session, "auth@example.com", "mypass")
    user = await authenticate_user(db_session, "auth@example.com", "mypass")
    assert user.email == "auth@example.com"


@pytest.mark.asyncio
async def test_authenticate_wrong_password(db_session) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    db_session: AsyncSession = db_session
    await register_user(db_session, "wrong@example.com", "right")
    with pytest.raises(InvalidCredentials):
        await authenticate_user(db_session, "wrong@example.com", "wrong")
