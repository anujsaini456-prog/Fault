import time

import httpx
import pyotp
import pytest

from app.security import TOTP_PERIOD
from tests.conftest import PASSWORD, make_tenant

pytestmark = pytest.mark.db

WEB = {"X-Client": "web"}
MOBILE = {"X-Client": "mobile"}


async def login(
    client: httpx.AsyncClient, email: str, password: str = PASSWORD, headers: dict[str, str] = WEB
) -> httpx.Response:
    return await client.post("/auth/login", json={"email": email, "password": password}, headers=headers)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_executive_signs_in_without_mfa_and_sees_own_org(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Acme", ["executive"])
    _, email = t.users["executive"]

    r = await login(client, email.upper())  # emails are case-insensitive
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["refresh_token"] is None, "web clients must never see the refresh token"
    assert "fs_refresh" in r.cookies
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie

    me = await client.get("/me", headers=bearer(body["access_token"]))
    assert me.json()["memberships"][0]["role"] == "executive"

    home = (await client.get("/dashboard/home", headers=bearer(body["access_token"]))).json()
    assert [o["id"] for o in home["organisations"]] == [str(t.org_id)]
    assert home["site_count"] == 2
    assert len(home["kpis"]) == 5 and all(k["trust"] == "none" for k in home["kpis"])


async def test_requests_without_token_are_rejected(client) -> None:
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers=bearer("garbage"))).status_code == 401


async def test_client_header_is_required(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Hdr", ["executive"])
    r = await login(client, t.users["executive"][1], headers={})
    assert r.status_code == 400


async def test_unknown_and_wrong_password_look_identical(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Same", ["executive"])
    a = await login(client, t.users["executive"][1], "Wrong-Password-1")
    b = await login(client, "nobody@nowhere.test", "Wrong-Password-1")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


async def test_lockout_after_repeated_failures(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Lock", ["executive"])
    email = t.users["executive"][1]
    for _ in range(5):
        assert (await login(client, email, "Wrong-Password-1")).status_code == 401
    # Correct password is refused while locked.
    assert (await login(client, email)).status_code == 401


async def test_login_is_rate_limited(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Rate", ["executive"])
    codes = [
        (await login(client, t.users["executive"][1], "Wrong-Password-1")).status_code for _ in range(12)
    ]
    assert 429 in codes


async def test_admin_must_enrol_mfa_then_use_it(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Mfa", ["admin"])
    email = t.users["admin"][1]

    r = (await login(client, email)).json()
    assert r["status"] == "mfa_setup_required"
    assert r["qr_svg"].startswith("<svg") and "access_token" not in r
    secret, mfa_token = r["secret"], r["mfa_token"]

    bad = await client.post("/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"}, headers=WEB)
    assert bad.status_code == 401

    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    ok = await client.post("/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code}, headers=WEB)
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["mfa_enabled"] is True

    # Second sign-in asks for a code, not enrolment.
    r2 = (await login(client, email)).json()
    assert r2["status"] == "mfa_required"
    replay = await client.post(
        "/auth/mfa/verify", json={"mfa_token": r2["mfa_token"], "code": code}, headers=WEB
    )
    assert replay.status_code == 401, "a TOTP code must not be accepted twice"
    nxt = pyotp.TOTP(secret).at(now + TOTP_PERIOD)
    ok2 = await client.post("/auth/mfa/verify", json={"mfa_token": r2["mfa_token"], "code": nxt}, headers=WEB)
    assert ok2.status_code == 200, ok2.text


async def test_mfa_token_cannot_be_used_as_access_token(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Typ", ["admin"])
    r = (await login(client, t.users["admin"][1])).json()
    assert (await client.get("/me", headers=bearer(r["mfa_token"]))).status_code == 401


async def test_web_refresh_rotates_cookie(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Cookie", ["executive"])
    r = await login(client, t.users["executive"][1])
    first = r.cookies["fs_refresh"]
    r2 = await client.post("/auth/refresh", headers=WEB)
    assert r2.status_code == 200, r2.text
    assert r2.cookies["fs_refresh"] != first
    assert (await client.get("/me", headers=bearer(r2.json()["access_token"]))).status_code == 200


async def test_mobile_refresh_reuse_revokes_family(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Mobile", ["executive"])
    r = (await login(client, t.users["executive"][1], headers=MOBILE)).json()
    old = r["refresh_token"]
    assert old

    new = (await client.post("/auth/refresh", json={"refresh_token": old}, headers=MOBILE)).json()[
        "refresh_token"
    ]
    # Someone replays the old token: refused, and the legitimate new token dies with it.
    assert (
        await client.post("/auth/refresh", json={"refresh_token": old}, headers=MOBILE)
    ).status_code == 401
    assert (
        await client.post("/auth/refresh", json={"refresh_token": new}, headers=MOBILE)
    ).status_code == 401


async def test_logout_revokes_refresh_token(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Out", ["executive"])
    tok = (await login(client, t.users["executive"][1], headers=MOBILE)).json()["refresh_token"]
    assert (await client.post("/auth/logout", json={"refresh_token": tok}, headers=MOBILE)).status_code == 204
    assert (
        await client.post("/auth/refresh", json={"refresh_token": tok}, headers=MOBILE)
    ).status_code == 401


async def _admin_session(client: httpx.AsyncClient, email: str) -> str:
    r = (await login(client, email)).json()
    code = pyotp.TOTP(r["secret"]).now()
    v = await client.post("/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": code}, headers=WEB)
    return str(v.json()["access_token"])


async def test_rbac_admin_endpoints(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Rbac", ["admin", "executive"])
    other = await make_tenant(owner_engine, "Other", ["admin"])
    exec_token = (await login(client, t.users["executive"][1])).json()["access_token"]
    admin_token = await _admin_session(client, t.users["admin"][1])

    new_user = {
        "email": f"analyst-{t.org_id.hex[:6]}@rbac.test",
        "full_name": "New Analyst",
        "password": "Another-Strong-9",
        "organisation_id": str(t.org_id),
        "role": "analyst",
    }
    assert (await client.post("/admin/users", json=new_user, headers=bearer(exec_token))).status_code == 403
    created = await client.post("/admin/users", json=new_user, headers=bearer(admin_token))
    assert created.status_code == 201, created.text
    assert (await client.post("/admin/users", json=new_user, headers=bearer(admin_token))).status_code == 409

    weak = {**new_user, "email": "weak@rbac.test", "password": "short"}
    assert (await client.post("/admin/users", json=weak, headers=bearer(admin_token))).status_code == 422

    cross = {**new_user, "email": "x@rbac.test", "organisation_id": str(other.org_id)}
    assert (await client.post("/admin/users", json=cross, headers=bearer(admin_token))).status_code == 403

    # The new user can sign in.
    assert (await login(client, new_user["email"], "Another-Strong-9")).json()["status"] == "ok"


async def test_audit_log_records_and_is_admin_only(client, owner_engine) -> None:
    t = await make_tenant(owner_engine, "Audit", ["admin", "executive"])
    exec_token = (await login(client, t.users["executive"][1])).json()["access_token"]
    admin_token = await _admin_session(client, t.users["admin"][1])

    assert (await client.get("/admin/audit", headers=bearer(exec_token))).status_code == 403
    entries = (await client.get("/admin/audit", headers=bearer(admin_token))).json()
    actions = {e["action"] for e in entries}
    assert {"login", "mfa_enrolled", "mfa_enrolment_started"} <= actions
    exec_id = str(t.users["executive"][0])
    assert any(e["action"] == "login" and e["actor_user_id"] == exec_id for e in entries)


async def test_security_headers_present(client) -> None:
    r = await client.get("/me")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
