from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.database.postgres import get_async_session_factory

_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    global _session_factory
    # Media service needs a larger pool because background tasks (image
    # processing, video polling) run concurrently alongside request handlers.
    _session_factory = get_async_session_factory(
        database_url,
        expire_on_commit=False,
        pool_size=10,
        max_overflow=20,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized")
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
