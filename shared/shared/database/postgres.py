from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def get_async_engine(database_url: str, **kwargs: Any) -> Any:
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        **kwargs,
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
