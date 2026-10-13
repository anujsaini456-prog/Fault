import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("FS_OWNER_DATABASE_URL")
    if not url:
        raise RuntimeError("FS_OWNER_DATABASE_URL must be set to run migrations")
    return url


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
