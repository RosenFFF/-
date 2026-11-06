"""Real PG/RLS and PG+Redis evidence; OCR/LLM substitutes remain explicit.

Both PostgreSQL logins are local disposable roles; API/worker DML never uses
the owner login. All schema drift below touches only a random fixture schema.
"""

import asyncio
from dataclasses import asdict

import pytest
from sqlalchemy import select, text

from app.db.models import User
from app.main import create_app

from .conftest import Api, _seed, make_settings
from .fakes import FakeLLM
from .test_m1_chat_sse import parse_sse, path, seed_review
from .test_m1_pipeline import _report, quick_ocr  # noqa: F401
from .test_m2_postgres_rls import seed


@pytest.mark.parametrize(
    "drift",
    [
        "ALTER TABLE documents DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE documents NO FORCE ROW LEVEL SECURITY",
        "DROP POLICY tenant_guard ON documents",
        "ALTER POLICY tenant_guard ON documents USING (true) WITH CHECK (true)",
        "CREATE POLICY unexpected_permissive ON documents FOR ALL USING (true)",
        "ALTER POLICY tenant_guard ON documents TO m3_runtime",
        "REVOKE DELETE ON documents FROM m3_runtime",
        "UPDATE alembic_version SET version_num='0002_m2_tenant_rls'",
    ],
    ids=[
        "rls-off",
        "force-off",
        "guard-missing",
        "guard-broadened",
        "extra-policy",
        "role-drift",
        "grant-missing",
        "revision-stale",
    ],
)
async def test_pg_runtime_gate_rejects_catalog_or_grant_drift(postgres_rls_db, postgres_rls_owner, drift):
    await postgres_rls_db.check_runtime_access()
    # Fixed test role name matches local M3 provisioning. Derive actual configured
    # role for portability; identifier is a server value, never raw string SQL input.
    async with postgres_rls_db.engine.connect() as c:
        role = await c.scalar(text("SELECT current_user"))
    async with postgres_rls_owner.engine.begin() as c:
        quote = c.dialect.identifier_preparer.quote_identifier
        statement = drift.replace("m3_runtime", quote(role))
        await c.execute(text(statement))
    with pytest.raises(RuntimeError, match="deployment blocked|migration required"):
        await postgres_rls_db.check_runtime_access()


async def test_pg_worker_context_revalidated_and_concurrent_pool_reuse_isolated(postgres_rls_db):
    db = postgres_rls_db
    scopes, _ = await seed(db)

    async def job(scope):
        async with db.job_session(asdict(scope)) as s:
            for ending in (s.commit, s.rollback):
                assert set((await s.scalars(select(User.tenant_id))).all()) == {scope.org_id}
                await ending()

    await asyncio.gather(*(job(scope) for scope in scopes * 4))
    bad = dict(asdict(scopes[0]), org_id=scopes[1].org_id)
    for context in (None, {}, bad):
        with pytest.raises(ValueError, match="context required|identity mismatch"):
            async with db.job_session(context):
                pytest.fail("unverified job context reached business work")
    async with db.engine.connect() as c:
        for key in ("app.current_org_id", "app.current_user_id", "app.current_role", "app.auth_username"):
            assert await c.scalar(text("SELECT nullif(current_setting(:key, true), '')"), {"key": key}) is None


@pytest.fixture
async def pg_redis_api(tmp_path, postgres_rls_db, live_redis):
    redis, _ = live_redis
    settings = make_settings(tmp_path, database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False))
    app = create_app(settings, redis=redis)
    # Actual lifespan: no gate monkeypatch, no owner login, no in-process Redis fake.
    async with app.router.lifespan_context(app):
        await _seed(app)
        yield Api(app, settings)


@pytest.mark.usefixtures("quick_ocr")
async def test_pg_redis_upload_rule_fallback_chat_error_replay_audit_and_isolation(pg_redis_api):
    api = pg_redis_api
    owner = await api.login("reviewer")
    _, rid, report = await _report(api, owner)
    assert report["llm_verified"] is False and report["degrade_level"] == "L3"
    body = {"content": "Explain the report"}
    response = await owner.post(path(rid), json=body, headers={"Accept": "text/event-stream"})
    events = parse_sse(response)
    assert [event["event"] for event in events] == ["error"]
    assert events[0]["data"]["code"] == "MODEL_UNAVAILABLE"
    replay_headers = {"Accept": "text/event-stream", "Last-Event-ID": response.headers["x-chat-stream-id"] + ":0"}
    assert parse_sse(await owner.post(path(rid), json=body, headers=replay_headers)) == events
    assert [m["role"] for m in (await owner.get(path(rid))).json()["items"]] == ["user"]
    other = await api.login("reviewer2")
    assert (await other.get(path(rid))).status_code == 404
    assert (await other.post(path(rid), json=body, headers=replay_headers)).status_code == 404
    admin = await api.login("admin")
    verification = (await admin.get("/api/v1/audit/verify")).json()
    assert verification["valid"] and verification["checked"] >= 3
    await owner.aclose()
    await other.aclose()
    await admin.aclose()


async def test_pg_redis_sse_fixture_answer_replays_once_no_model_claim(pg_redis_api):
    from .test_m1_chat_sse import test_sse_order_event_ids_and_completed_replay

    pg_redis_api.app.state.ai.llm = FakeLLM()
    await test_sse_order_event_ids_and_completed_replay(pg_redis_api)


async def test_pg_redis_sse_fixture_disconnect_resume(pg_redis_api, monkeypatch):
    from .test_m1_chat_sse import test_disconnect_does_not_cancel_producer_and_inflight_resume

    pg_redis_api.app.state.ai.llm = FakeLLM()
    await test_disconnect_does_not_cancel_producer_and_inflight_resume(pg_redis_api, monkeypatch)


async def test_pg_redis_actual_redis_loss_is_503_not_unlimited(pg_redis_api, live_redis):
    _, process = live_redis
    client = await pg_redis_api.login("reviewer")
    process.terminate()
    await asyncio.wait_for(process.wait(), 5)
    response = await client.delete("/api/v1/documents/00000000-0000-4000-8000-000000000001")
    assert response.status_code == 503 and response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    await client.aclose()


async def test_pg_redis_refresh_rotation_and_replay_preserve_tenant(pg_redis_api):
    api = pg_redis_api
    client = await api.login("reviewer")
    old_refresh = client.cookies["refresh_token"]
    before = (await client.get("/api/v1/auth/me")).json()
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    after = (await client.get("/api/v1/auth/me")).json()
    assert before["id"] == after["id"] and before["tenant_id"] == after["tenant_id"]
    assert client.cookies["refresh_token"] != old_refresh
    rid = await seed_review(api)
    assert (await client.get(path(rid))).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get(path(rid))).status_code == 401
    await client.aclose()


async def test_pg_worker_real_non_owner_startup_checks_migration_and_catalog(
    postgres_rls_db, workers, tmp_path, monkeypatch
):
    settings = make_settings(tmp_path, database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(workers, "get_settings", lambda: settings)
    # DB acceptance is real; OCR warmup is not part of this environment milestone.
    monkeypatch.setattr(workers.ocr_engine, "load", lambda: None)
    ctx = {}
    try:
        await workers.startup(ctx)
        assert ctx["db"].engine.url.username == postgres_rls_db.engine.url.username
        await ctx["db"].check_runtime_access()
        assert "ai" in ctx and "audit" in ctx
    finally:
        if "db" in ctx:
            await ctx["db"].dispose()


@pytest.mark.parametrize("entry", ["api", "worker"])
async def test_pg_actual_startup_policy_drift_rejected_before_ai_or_redis(
    postgres_rls_db, postgres_rls_owner, workers, tmp_path, monkeypatch, entry
):
    async with postgres_rls_owner.engine.begin() as c:
        await c.execute(text("ALTER POLICY tenant_guard ON documents USING (true) WITH CHECK (true)"))
    settings = make_settings(tmp_path, database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False))
    if entry == "api":
        app = create_app(settings)
        with pytest.raises(RuntimeError, match="deployment blocked: policy catalog"):
            async with app.router.lifespan_context(app):
                pytest.fail("unsafe real catalog passed startup")
        assert not hasattr(app.state, "ai") and not hasattr(app.state, "redis")
    else:
        monkeypatch.setattr(workers, "get_settings", lambda: settings)
        ctx = {}
        with pytest.raises(RuntimeError, match="deployment blocked: policy catalog"):
            await workers.startup(ctx)
        assert "store" not in ctx and "ai" not in ctx


async def test_pg_startup_refuses_unscoped_bootstrap_instead_of_claiming_empty_user_table(postgres_rls_db, tmp_path):
    settings = make_settings(
        tmp_path,
        database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False),
        bootstrap_admin_username="synthetic-admin",
    )
    app = create_app(settings)
    with pytest.raises(RuntimeError, match="explicit scoped operator provisioning"):
        async with app.router.lifespan_context(app):
            pytest.fail("runtime must not bootstrap tenant rows without an operator scope")
    assert not hasattr(app.state, "ai") and not hasattr(app.state, "redis")
