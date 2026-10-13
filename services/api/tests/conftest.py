import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncEngine

# Configure before any app module reads settings.
os.environ.setdefault("FS_JWT_SECRET", "test-secret-" + "x" * 40)
os.environ["FS_COOKIE_SECURE"] = "false"  # the test client talks plain http
os.environ["FS_COOKIE_PATH"] = "/auth"  # no /api prefix without Caddy in front
os.environ.pop("FS_REDIS_URL", None)  # in-process rate limiter
TEST_DB = os.environ.get("FS_TEST_DATABASE_URL")
TEST_OWNER_DB = os.environ.get("FS_TEST_OWNER_DATABASE_URL")
if TEST_DB:
    os.environ["FS_DATABASE_URL"] = TEST_DB

API_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "Correct-Horse-42"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if TEST_DB and TEST_OWNER_DB:
        return
    skip = pytest.mark.skip(reason="FS_TEST_DATABASE_URL / FS_TEST_OWNER_DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Fresh schema for the run. Alembic runs in a subprocess because its env.py owns an event loop."""
    env = {**os.environ, "FS_OWNER_DATABASE_URL": TEST_OWNER_DB or ""}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, check=True)


@pytest.fixture(scope="session")
async def owner_engine(migrated_db: None) -> AsyncIterator["AsyncEngine"]:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(TEST_OWNER_DB or "")
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def app_engine(migrated_db: None) -> AsyncIterator["AsyncEngine"]:
    from app.db import get_engine

    engine = get_engine()
    yield engine
    await engine.dispose()


@dataclass
class Tenant:
    org_id: uuid.UUID
    site_ids: list[uuid.UUID]
    users: dict[str, tuple[uuid.UUID, str]]  # role -> (id, email)


async def make_tenant(owner_engine: "AsyncEngine", name: str, roles: list[str]) -> Tenant:
    """Create an organisation with two sites and one user per role, bypassing RLS as the owner."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Membership, Organisation, Site, User
    from app.security import hash_password

    tag = uuid.uuid4().hex[:8]
    async with AsyncSession(owner_engine) as s, s.begin():
        org = Organisation(name=f"{name} {tag}")
        s.add(org)
        await s.flush()
        sites = [Site(organisation_id=org.id, name=f"{name} site {i}") for i in (1, 2)]
        s.add_all(sites)
        users: dict[str, tuple[uuid.UUID, str]] = {}
        for role in roles:
            email = f"{role}-{tag}@{name.lower()}.test"
            u = User(email=email, full_name=f"{role} {tag}", password_hash=hash_password(PASSWORD))
            s.add(u)
            await s.flush()
            s.add(Membership(user_id=u.id, organisation_id=org.id, role=role))
            users[role] = (u.id, u.email)
        await s.flush()
        return Tenant(org_id=org.id, site_ids=[x.id for x in sites], users=users)


@pytest.fixture
async def client(app_engine: "AsyncEngine") -> AsyncIterator["httpx.AsyncClient"]:
    import httpx

    from app.main import app
    from app.ratelimit import get_rate_limiter

    get_rate_limiter().reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
