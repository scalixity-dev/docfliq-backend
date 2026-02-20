import os
import ssl
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _build_ssl_connect_args() -> dict[str, Any]:
    """Return asyncpg ``connect_args`` for SSL when DATABASE_SSL is set."""
    mode = os.environ.get("DATABASE_SSL", "").lower()
    if not mode or mode == "disable":
        return {}

    cert_path = os.environ.get("RDS_SSL_CERT", "")
    if cert_path and Path(cert_path).exists():
        ctx = ssl.create_default_context(cafile=cert_path)
        return {"connect_args": {"ssl": ctx}}

    # Fall back to simple 'require' (encrypted, no cert verification)
    return {"connect_args": {"ssl": "require"}}


def get_async_engine(database_url: str, **kwargs: Any) -> Any:
    ssl_kwargs = _build_ssl_connect_args()
    merged = {**ssl_kwargs, **kwargs}
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        **merged,
    )


def get_async_session_factory(
    database_url: str,
    *,
    expire_on_commit: bool = False,
    **engine_kwargs: Any,
) -> async_sessionmaker[AsyncSession]:
    engine = get_async_engine(database_url, **engine_kwargs)
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=expire_on_commit,
        autoflush=False,
        autocommit=False,
    )


AsyncSessionFactory = async_sessionmaker[AsyncSession]


async def get_session(
    session_factory: AsyncSessionFactory,
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
