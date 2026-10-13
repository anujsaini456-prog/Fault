import uuid
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)


@lru_cache
def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One transaction per request, committed on success and rolled back on error.

    RLS context set with `set_rls_user` is transaction-local, so it can never leak to another
    request through the connection pool. Handlers that must persist something before failing
    (e.g. a failed-login counter) call `commit()` themselves before raising."""
    async with _sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def set_rls_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(user_id)})


async def set_rls_auth_email(session: AsyncSession, email: str) -> None:
    """Lets the login transaction see exactly one user row: the one whose email was typed."""
    await session.execute(text("SELECT set_config('app.auth_email', :v, true)"), {"v": email})
