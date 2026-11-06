from sqlalchemy import select

from app.db.models import AuditLog

from .conftest import PASSWORDS


async def _actions(api, action):
    async with api.app.state.db.maintenance_sessionmaker() as s:
        return (await s.execute(select(AuditLog).where(AuditLog.action == action))).scalars().all()


async def test_login_sets_httponly_cookies_and_never_returns_token_in_body(api):
    async with api.client() as c:
        r = await c.post("/api/v1/auth/login", json={"username": "reviewer", "password": PASSWORDS["reviewer"]})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" not in body and body["user"]["role"] == "reviewer"
    assert "audit:read_all" not in body["user"]["permissions"]
    cookies = r.headers.get_list("set-cookie")
    access = next(h for h in cookies if h.startswith("access_token="))
    refresh = next(h for h in cookies if h.startswith("refresh_token="))
    csrf = next(h for h in cookies if h.startswith("csrf_token="))
    for h in (access, refresh):
        assert "HttpOnly" in h and "Secure" in h and "SameSite=strict" in h
    assert "Path=/api/v1/auth" in refresh
    assert "HttpOnly" not in csrf
    assert r.headers["Cache-Control"] == "no-store"


async def test_me_with_cookie(api):
    c = await api.login("auditor")
    r = await c.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["username"] == "auditor"


async def test_wrong_password_is_generic_and_audited(api):
    async with api.client() as c:
        r1 = await c.post("/api/v1/auth/login", json={"username": "reviewer", "password": "wrong-password"})
        r2 = await c.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong-password"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["code"] == r2.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert len(await _actions(api, "auth.login_failed")) == 2


async def test_lockout_after_repeated_failures(api):
    async with api.client() as c:
        for _ in range(5):
            await c.post("/api/v1/auth/login", json={"username": "reviewer", "password": "wrong-password"})
        r = await c.post("/api/v1/auth/login", json={"username": "reviewer", "password": PASSWORDS["reviewer"]})
    assert r.status_code == 423 and r.json()["code"] == "AUTH_LOCKED"


async def test_login_rate_limited(make_api):
    api = await make_api(rl_login_per_min=3, login_max_failures=100)
    async with api.client() as c:
        codes = [
            (await c.post("/api/v1/auth/login", json={"username": "reviewer", "password": "bad-pass-x"})).status_code
            for _ in range(4)
        ]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429
    assert len(await _actions(api, "rate_limit.hit")) == 1


async def test_refresh_rotates_and_reuse_revokes_family(api):
    c = await api.login("reviewer")
    old = c.cookies["refresh_token"]
    old_csrf = c.cookies["csrf_token"]
    r = await c.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new = c.cookies["refresh_token"]
    assert new != old
    c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]

    # 攻击者重放旧刷新令牌
    async with api.client() as attacker:
        r = await attacker.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": old_csrf, "Cookie": f"csrf_token={old_csrf}; refresh_token={old}"},
        )
    assert r.status_code == 401
    assert len(await _actions(api, "auth.refresh_reuse_detected")) == 1
    # 整条令牌族被作废，合法用户的新令牌也失效
    assert (await c.post("/api/v1/auth/refresh")).status_code == 401


async def test_csrf_required_for_cookie_authenticated_writes(api):
    c = await api.login("admin")
    del c.headers["X-CSRF-Token"]
    r = await c.post("/api/v1/users", json={"username": "newuser", "password": "x" * 12, "role": "reviewer"})
    assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"
    c.headers["X-CSRF-Token"] = "forged"
    r = await c.post("/api/v1/users", json={"username": "newuser", "password": "x" * 12, "role": "reviewer"})
    assert r.status_code == 403
    c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]
    r = await c.post("/api/v1/users", json={"username": "newuser", "password": "x" * 12, "role": "reviewer"})
    assert r.status_code == 201


async def test_logout_revokes_refresh(api):
    c = await api.login("reviewer")
    refresh = c.cookies["refresh_token"]
    old_csrf = c.cookies["csrf_token"]
    assert (await c.post("/api/v1/auth/logout")).status_code == 204
    async with api.client() as again:
        r = await again.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": old_csrf, "Cookie": f"csrf_token={old_csrf}; refresh_token={refresh}"},
        )
    assert r.status_code == 401


async def test_disabled_user_token_stops_working(api):
    admin = await api.login("admin")
    rev = await api.login("reviewer")
    uid = (await rev.get("/api/v1/auth/me")).json()["id"]
    assert (await admin.patch(f"/api/v1/users/{uid}", json={"disabled": True})).status_code == 200
    assert (await rev.get("/api/v1/auth/me")).status_code == 401
