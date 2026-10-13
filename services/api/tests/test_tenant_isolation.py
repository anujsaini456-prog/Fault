"""Acceptance criterion: a user from Organisation A cannot read Organisation B's data —
proven at the database level (RLS, bypassing the API entirely) and at the API level."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from tests.conftest import PASSWORD, make_tenant

pytestmark = pytest.mark.db


async def as_user(conn: AsyncConnection, user_id: uuid.UUID | None) -> None:
    await conn.execute(
        text("SELECT set_config('app.user_id', :v, true)"), {"v": str(user_id) if user_id else ""}
    )


async def ids(conn: AsyncConnection, table: str) -> set[uuid.UUID]:
    return {r[0] for r in await conn.execute(text(f"SELECT id FROM {table}"))}  # noqa: S608 - fixed names


async def test_db_level_isolation_between_organisations(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    a = await make_tenant(owner_engine, "Alpha", ["executive", "admin"])
    b = await make_tenant(owner_engine, "Beta", ["executive"])
    a_exec, a_admin, b_exec = a.users["executive"][0], a.users["admin"][0], b.users["executive"][0]

    async with app_engine.connect() as conn, conn.begin():
        await as_user(conn, b_exec)
        assert await ids(conn, "organisation") == {b.org_id}
        assert await ids(conn, "site") == set(b.site_ids)
        assert await ids(conn, "app_user") == {b_exec}
        assert a.org_id not in await ids(conn, "organisation")

    async with app_engine.connect() as conn, conn.begin():
        await as_user(conn, a_admin)
        # Admin sees the people in their own org, never Beta's.
        assert await ids(conn, "app_user") == {a_exec, a_admin}
        # Writes into another tenant are refused by policy.
        with pytest.raises(DBAPIError):
            await conn.execute(
                text("INSERT INTO membership (user_id, organisation_id, role) VALUES (:u, :o, 'admin')"),
                {"u": str(a_admin), "o": str(b.org_id)},
            )


async def test_no_context_means_no_rows(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    await make_tenant(owner_engine, "Ghost", ["executive"])
    async with app_engine.connect() as conn, conn.begin():
        await as_user(conn, None)
        for table in ("organisation", "region", "site", "app_user", "membership", "audit_log"):
            assert await ids(conn, table) == set(), f"{table} leaked rows without a user context"


async def test_site_scoped_member_sees_only_their_site(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    t = await make_tenant(owner_engine, "Scoped", [])
    uid = uuid.uuid4()
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO app_user (id, email, full_name, password_hash) VALUES (:id, :e, 'Site Eng', 'x')"
            ),
            {"id": uid, "e": f"eng-{uid.hex[:8]}@scoped.test"},
        )
        await conn.execute(
            text(
                "INSERT INTO membership (user_id, organisation_id, site_id, role) VALUES (:u, :o, :s, 'engineer')"
            ),
            {"u": uid, "o": t.org_id, "s": t.site_ids[0]},
        )
    async with app_engine.connect() as conn, conn.begin():
        await as_user(conn, uid)
        assert await ids(conn, "site") == {t.site_ids[0]}


async def test_audit_log_is_append_only(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(text("INSERT INTO audit_log (action) VALUES ('test_event')"))
    async with app_engine.connect() as conn:
        with pytest.raises(DBAPIError):  # app role has no UPDATE/DELETE grant at all
            async with conn.begin():
                await conn.execute(text("DELETE FROM audit_log"))
    async with owner_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):  # even the owner is stopped by the trigger
            async with conn.begin():
                await conn.execute(text("UPDATE audit_log SET action = 'tampered'"))


async def test_api_level_isolation(client, owner_engine: AsyncEngine) -> None:
    a = await make_tenant(owner_engine, "ApiA", ["executive"])
    b = await make_tenant(owner_engine, "ApiB", ["executive"])
    r = await client.post(
        "/auth/login",
        json={"email": b.users["executive"][1], "password": PASSWORD},
        headers={"X-Client": "web"},
    )
    token = r.json()["access_token"]
    home = (await client.get("/dashboard/home", headers={"Authorization": f"Bearer {token}"})).json()
    org_ids = {o["id"] for o in home["organisations"]}
    assert org_ids == {str(b.org_id)} and str(a.org_id) not in org_ids
    assert home["site_count"] == 2
