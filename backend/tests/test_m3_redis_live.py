"""Real loopback Redis evidence; SQLite/LLM substitutes are explicitly separate.

Enable with TEST_REDIS_SERVER=/absolute/path/to/redis-server. Each test starts
its own no-persistence instance; no FLUSHDB, shared keys, or remote targets.
A configured but broken binary is a failure, never a skip.
"""

import asyncio

import pytest

from app.main import create_app
from app.security.ratelimit import RateLimiter

from . import test_m1_chat_sse as chat
from . import test_m2_limits as limits
from .conftest import Api, _seed, make_settings
from .fakes import FakeLLM


@pytest.fixture
async def live_redis_api(tmp_path, live_redis):
    redis, _ = live_redis
    settings = make_settings(tmp_path / "sqlite-stand-in")
    app = create_app(settings, redis=redis)
    async with app.router.lifespan_context(app):
        await _seed(app)
        yield Api(app, settings)


async def test_live_redis_limiter_atomic_bounded_expiry_and_tenant_buckets(live_redis):
    redis, _ = live_redis
    limiter = RateLimiter(redis)
    hits = await asyncio.gather(*(limiter.hit("m3:tenant-a:user", 3, window_s=1) for _ in range(30)))
    assert sum(ok for ok, _ in hits) == 3
    assert all(retry >= 1 for ok, retry in hits if not ok)
    assert await redis.zcard("rl:m3:tenant-a:user") == 3
    assert 0 < await redis.pttl("rl:m3:tenant-a:user") <= 1000
    assert (await limiter.hit("m3:tenant-b:user", 3))[0]
    await asyncio.sleep(1.05)
    assert await redis.exists("rl:m3:tenant-a:user") == 0
    assert (await limiter.hit("m3:tenant-a:user", 3))[0]


async def test_live_redis_sse_event_ids_replay_and_no_duplicate_generation(live_redis_api):
    live_redis_api.app.state.ai.llm = FakeLLM()  # Protocol evidence only, NOT real-model acceptance.
    await chat.test_sse_order_event_ids_and_completed_replay(live_redis_api)


async def test_live_redis_sse_disconnect_and_inflight_resume(live_redis_api, monkeypatch):
    live_redis_api.app.state.ai.llm = FakeLLM()
    await chat.test_disconnect_does_not_cancel_producer_and_inflight_resume(live_redis_api, monkeypatch)


async def test_live_redis_sse_replay_actor_review_body_binding(live_redis_api):
    live_redis_api.app.state.ai.llm = FakeLLM()
    await chat.test_replay_is_actor_review_body_bound_and_validates_cursor(live_redis_api)


async def test_live_redis_no_model_error_is_replayed_without_success(live_redis_api):
    await chat.test_production_no_model_explicit_error_no_success_message(live_redis_api, "text/event-stream")


async def test_live_redis_login_burst_resume_limit_and_retry_after(live_redis_api):
    async def make(**kw):
        for key, value in kw.items():
            setattr(live_redis_api.settings, key, value)
        return live_redis_api

    await limits.test_failed_login_burst_and_sse_resume_share_limits(make)


async def test_live_redis_actual_server_loss_returns_503_fail_closed(live_redis_api, live_redis):
    _, process = live_redis
    client = await live_redis_api.login("reviewer")
    process.terminate()
    await asyncio.wait_for(process.wait(), 5)
    response = await client.delete("/api/v1/documents/00000000-0000-4000-8000-000000000001")
    assert response.status_code == 503 and response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    assert "127.0.0.1" not in response.text
    await client.aclose()
