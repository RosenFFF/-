import asyncio
import secrets

import fakeredis.aioredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from app.db.models import AuditLog, uid
from app.security.ratelimit import RateLimiter

from .test_m1_chat_sse import path, seed_review


@pytest.mark.parametrize(
    "route", ["login", "upload", "report", "chat", "sse", "refresh", "logout", "fields", "users", "delete"]
)
async def test_sensitive_write_limits_are_429_problem_with_retry(make_api, route):
    # No successful model is required to exercise limiter boundaries.
    api = await make_api()
    c = await api.login("admin" if route == "users" else "reviewer")
    settings = api.settings
    if route == "login":
        settings.rl_login_per_min = 1  # Initial login already consumed this IP's bucket.
        response = await api.client().post(
            "/api/v1/auth/login", json={"username": "unknown", "password": "wrong-pass-fixture"}
        )
    else:
        if route in {"chat", "sse"}:
            rid = await seed_review(api)
            settings.rl_chat_per_min = 1

            async def hit():
                return await c.post(
                    path(rid),
                    json={"content": "Explain"},
                    headers={"Accept": "text/event-stream" if route == "sse" else "application/json"},
                )
        elif route == "upload":
            settings.rl_upload_per_min = 1

            async def hit():
                return await c.post("/api/v1/documents", files={"file": ("bad.png", b"not-image", "image/png")})
        elif route == "report":
            settings.rl_review_per_min = 1

            async def hit():
                return await c.post("/api/v1/reviews", json={"document_ids": [uid()], "destination_country": "VN"})
        elif route in {"refresh", "logout"}:
            settings.rl_auth_per_min = 1

            async def hit():
                return await c.post(f"/api/v1/auth/{route}")
        else:
            settings.rl_default_per_min = 1

            async def hit():
                if route == "fields":
                    return await c.patch(
                        f"/api/v1/documents/{uid()}/fields",
                        json={
                            "version": 1,
                            "fields": [{"key": "hs_code", "value": "123456"}],
                        },
                    )
                if route == "users":
                    return await c.post(
                        "/api/v1/users",
                        json={"username": "admin", "password": secrets.token_urlsafe(18), "role": "reviewer"},
                    )
                return await c.delete(f"/api/v1/documents/{uid()}")

        await hit()
        # Refresh rotated the signed CSRF pair; logout cleared cookies, so re-login if needed.
        if route == "refresh":
            c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]
        if route == "logout":
            await c.aclose()
            c = await api.login("reviewer")
        response = await hit()
    assert response.status_code == 429, response.text
    assert response.json()["code"] == "RATE_LIMITED" and response.json()["request_id"]
    assert int(response.headers["retry-after"]) >= 1
    assert response.headers["content-type"].startswith("application/problem+json")
    async with api.app.state.db.sessionmaker() as s:
        assert (await s.scalars(select(AuditLog).where(AuditLog.action == "rate_limit.hit"))).all()


async def test_sliding_window_atomic_bounded_expiry_and_bucket_isolation(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis()
    limiter = RateLimiter(redis)
    monkeypatch.setattr("app.security.ratelimit.time.time", lambda: 1000)
    results = await asyncio.gather(*(limiter.hit("write:tenant:user", 3) for _ in range(30)))
    assert sum(ok for ok, _ in results) == 3
    assert await redis.zcard("rl:write:tenant:user") == 3
    assert 0 < await redis.ttl("rl:write:tenant:user") <= 60
    assert (await limiter.hit("write:other:user", 3))[0]
    monkeypatch.setattr("app.security.ratelimit.time.time", lambda: 1061)
    assert (await limiter.hit("write:tenant:user", 3))[0]
    await redis.aclose()


async def test_redis_failure_fails_closed_not_unlimited_write(api, monkeypatch):
    c = await api.login("reviewer")

    async def unavailable(*args, **kw):
        raise RedisConnectionError("synthetic infrastructure error")

    monkeypatch.setattr(api.app.state.limiter, "hit", unavailable)
    result = await c.delete(f"/api/v1/documents/{uid()}")
    assert result.status_code == 503 and result.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    assert "infrastructure" not in result.text


async def test_failed_login_burst_and_sse_resume_share_limits(make_api):
    from .fakes import FakeLLM

    api = await make_api(rl_login_per_min=2, rl_chat_per_min=2)
    c = await api.login("reviewer")
    attempt = {"username": "nonexistent-fixture", "password": secrets.token_urlsafe(18)}
    assert (await api.client().post("/api/v1/auth/login", json=attempt)).status_code == 401
    assert (await api.client().post("/api/v1/auth/login", json=attempt)).status_code == 429
    api.app.state.ai.llm = FakeLLM()
    rid = await seed_review(api)
    body = {"content": "Explain"}
    first = await c.post(path(rid), json=body, headers={"Accept": "text/event-stream"})
    headers = {"Accept": "text/event-stream", "Last-Event-ID": first.headers["x-chat-stream-id"] + ":0"}
    assert (await c.post(path(rid), json=body, headers=headers)).status_code == 200
    limited = await c.post(path(rid), json=body, headers=headers)
    assert limited.status_code == 429 and limited.json()["code"] == "RATE_LIMITED"
    assert len(api.app.state.ai.llm.messages) == 1


@pytest.mark.parametrize(
    "name",
    [
        "rl_login_per_min",
        "rl_auth_per_min",
        "rl_default_per_min",
        "rl_upload_per_min",
        "rl_review_per_min",
        "rl_chat_per_min",
    ],
)
def test_zero_cannot_disable_limits(tmp_path, name):
    from pydantic import ValidationError

    from .conftest import make_settings

    with pytest.raises(ValidationError):
        make_settings(tmp_path, **{name: 0})
