"""Idempotent demo seed. Runs as the schema owner (bypasses RLS), never from a request handler.

Creates two organisations so tenant isolation can be seen, not just claimed:
  * Northgrid Power      — admin (MFA enrolment forced on first sign-in) + an executive
  * Southern Utilities   — an executive who must never see Northgrid data

Usage:  python -m app.seed
"""

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import Membership, Organisation, Region, Site, User
from app.security import hash_password, password_problems

DEMO = {
    "Northgrid Power": {
        "regions": {"North": ["Aberdeen 132kV", "Inverness 33kV"], "Central": ["Perth 132kV"]},
        "users": [
            ("admin", None, "Ada Admin", "FS_SEED_ADMIN_PASSWORD"),  # email from FS_SEED_ADMIN_EMAIL
            ("executive", "ceo@northgrid.example", "Nia Executive", "FS_SEED_EXEC_PASSWORD"),
        ],
    },
    "Southern Utilities": {
        "regions": {"Coast": ["Brighton 33kV", "Dover 132kV"]},
        "users": [("executive", "ceo@southern.example", "Sam Executive", "FS_SEED_EXEC_PASSWORD")],
    },
}


async def seed(session: AsyncSession) -> list[str]:
    created: list[str] = []
    for org_name, spec in DEMO.items():
        org_q = select(Organisation).where(Organisation.name == org_name)
        org = (await session.execute(org_q)).scalar_one_or_none()
        if org is None:
            org = Organisation(name=org_name)
            session.add(org)
            await session.flush()
            for region_name, sites in spec["regions"].items():  # type: ignore[attr-defined]
                region = Region(organisation_id=org.id, name=region_name)
                session.add(region)
                await session.flush()
                for i, site_name in enumerate(sites, 1):
                    code = f"{region_name[:3].upper()}-{i:02d}"
                    session.add(Site(organisation_id=org.id, region_id=region.id, name=site_name, code=code))
            created.append(f"organisation {org_name}")

        for role, email, full_name, password_env in spec["users"]:  # type: ignore[attr-defined]
            email = (email or os.environ.get("FS_SEED_ADMIN_EMAIL", "admin@example.com")).lower()
            password = os.environ.get(password_env)
            if not password:
                raise SystemExit(f"{password_env} must be set")
            if problems := password_problems(password):
                raise SystemExit(f"{password_env}: password " + "; ".join(problems))
            user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email, full_name=full_name, password_hash=hash_password(password))
                session.add(user)
                await session.flush()
                session.add(Membership(user_id=user.id, organisation_id=org.id, role=role))
                created.append(f"{role} {email}")
    return created


async def main() -> None:
    url = os.environ.get("FS_OWNER_DATABASE_URL")
    if not url:
        sys.exit("FS_OWNER_DATABASE_URL must be set")
    engine = create_async_engine(url)
    async with AsyncSession(engine) as session, session.begin():
        created = await seed(session)
    await engine.dispose()
    print("Seeded: " + (", ".join(created) if created else "nothing new (already seeded)"))


if __name__ == "__main__":
    asyncio.run(main())
