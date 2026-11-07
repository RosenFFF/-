"""ASGI fault injection is mock evidence; the reconnect test requires real PG RLS."""

import time
from types import SimpleNamespace

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.ai.llm import ProviderChain
from app.db.models import Tenant
from eval.recovery_support import BudgetTransport

from .conftest import PASSWORDS
from .fakes import FakeLLM
from .test_m2_postgres_rls import seed


async def test_asgi_redis_fault_fail_closed_writes_reads_survive_and_recover(api, monkeypatch):
    api.app.state.ai.llm = FakeLLM()
    client = await api.login("reviewer")
    down = True
    original_ping = api.app.state.redis.ping
    original_hit = api.app.state.limiter.hit

    async def ping(*args, **kwargs):
        if down:
            raise RedisConnectionError("fixture unavailable")
        return await original_ping(*args, **kwargs)

    async def hit(*args, **kwargs):
        if down:
            raise RedisConnectionError("fixture unavailable")
        return await original_hit(*args, **kwargs)

    monkeypatch.setattr(api.app.state.redis, "ping", ping)
    monkeypatch.setattr(api.app.state.limiter, "hit", hit)
    ready = await client.get("/api/v1/readyz")
    assert ready.status_code == 503 and ready.json()["checks"]["redis"]["detail"] == "unreachable"
    login = await client.post("/api/v1/auth/login", json={"username": "reviewer", "password": PASSWORDS["reviewer"]})
    assert login.status_code == 503 and login.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    assert (await client.get("/api/v1/documents")).status_code == 200
    down = False
    assert (await client.get("/api/v1/readyz")).status_code == 200
    assert (
        await client.post("/api/v1/auth/login", json={"username": "reviewer", "password": PASSWORDS["reviewer"]})
    ).status_code == 200
    await client.aclose()


@pytest.mark.parametrize("failure", ["operational", "refused", "invalidated", "unclassified"])
async def test_asgi_database_connection_fault_generic_errors_then_same_app_recovers(api, failure):
    api.app.state.ai.llm = FakeLLM()
    down = False

    def fail_sql(*args):
        if down:
            if failure == "refused":
                raise ConnectionRefusedError("NEVER_EXPOSE_FIXTURE_DETAIL")
            if failure == "unclassified":
                raise DBAPIError("withheld", {}, RuntimeError("NEVER_EXPOSE_FIXTURE_DETAIL"))
            if failure == "invalidated":
                raise DBAPIError(
                    "withheld", {}, RuntimeError("NEVER_EXPOSE_FIXTURE_DETAIL"), connection_invalidated=True
                )
            raise OperationalError("withheld", {}, RuntimeError("NEVER_EXPOSE_FIXTURE_DETAIL"))

    engine = api.app.state.db.engine.sync_engine
    event.listen(engine, "before_cursor_execute", fail_sql)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app, raise_app_exceptions=False),
            base_url="https://testserver",
            headers={"Origin": api.settings.cors_origins[0]},
        ) as client:
            login_body = {"username": "reviewer", "password": PASSWORDS["reviewer"]}
            assert (await client.post("/api/v1/auth/login", json=login_body)).status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
            down = True
            ready = await client.get("/api/v1/readyz")
            assert ready.status_code == 503 and ready.json()["checks"]["database"]["detail"] == "unreachable"
            for method, url in [("POST", "/api/v1/auth/login"), ("GET", "/api/v1/documents")]:
                response = await client.request(method, url, json=login_body if method == "POST" else None)
                assert response.status_code == (500 if failure == "unclassified" else 503)
                assert response.json()["code"] == (
                    "INTERNAL_ERROR" if failure == "unclassified" else "DEPENDENCY_UNAVAILABLE"
                )
                assert "NEVER_EXPOSE" not in response.text and "withheld" not in response.text
            down = False
            assert (await client.get("/api/v1/readyz")).status_code == 200
            assert (await client.get("/api/v1/documents")).status_code == 200
            assert (await client.post("/api/v1/auth/login", json=login_body)).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", fail_sql)


async def test_asgi_provider_connect_failure_l2_cached_then_recovers_without_restart(api, monkeypatch):
    from app.ai import llm

    clock = {"now": 1000.0}
    monkeypatch.setattr(
        llm, "time", SimpleNamespace(monotonic=lambda: clock["now"], time=time.time, perf_counter=time.perf_counter)
    )
    down = {"value": True}
    requests = []
    cfg = api.settings.model_copy(
        update={"llm_provider_chain": ["deepseek", "ollama"], "deepseek_api_key": "fixture-not-a-real-key"}
    )

    def transport(request):
        requests.append(request.method)
        if request.url.host == "api.deepseek.com":
            if down["value"]:
                raise httpx.ConnectError("fixture connection unavailable", request=request)
            return httpx.Response(200, json={"data": [{"id": cfg.deepseek_model}]})
        return httpx.Response(200, json={"models": [{"name": cfg.ollama_model}]})

    chain = ProviderChain(cfg, transport=httpx.MockTransport(transport))
    api.app.state.ai.llm = chain
    client = await api.login("reviewer")
    response = await client.get("/api/v1/readyz")
    assert response.status_code == 200 and response.json()["degrade_level"] == "L2"
    down["value"] = False
    clock["now"] += 14.9
    assert (await client.get("/api/v1/readyz")).json()["degrade_level"] == "L2"
    clock["now"] += 0.2
    assert (await client.get("/api/v1/readyz")).json()["degrade_level"] == "L0"
    models = (await client.get("/api/v1/system/models")).json()
    assert not any(m.get("circuit_open") for m in models["models"])
    assert "POST" not in requests
    await client.aclose()


async def test_pg_force_rls_scope_reapplied_after_physical_invalidation(postgres_rls_db, postgres_rls_owner):
    db = postgres_rls_db
    scopes, rows = await seed(postgres_rls_owner)
    for scope, row in zip(scopes, rows, strict=True):
        async with db.tenant_session(scope) as session:
            for reconnect in (False, True):
                if reconnect:
                    connection = await session.connection()
                    await connection.invalidate()
                    await session.rollback()
                own = list((await session.execute(select(Tenant.id))).scalars())
                assert own == [scope.org_id]
                connection = await session.connection()
                gucs = (
                    await connection.execute(
                        text(
                            "SELECT current_setting('app.current_org_id'),"
                            "current_setting('app.current_user_id'),current_setting('app.current_role')"
                        )
                    )
                ).one()
                assert tuple(gucs) == (scope.org_id, scope.user_id, scope.role)
                visible = list((await connection.execute(text("SELECT id FROM documents"))).scalars())
                assert visible == [row["documents"]["id"]]
                assert await connection.scalar(
                    text(
                        "SELECT relforcerowsecurity AND relrowsecurity AND "
                        "NOT pg_has_role(current_user,relowner,'MEMBER') "
                        "FROM pg_class WHERE oid='documents'::regclass"
                    )
                )
    async with db.engine.begin() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM documents")) == 0


def test_live_budget_is_shared_and_persists_only_counts(tmp_path):
    counter = tmp_path / "counter.json"
    first, second = BudgetTransport(counter, "one"), BudgetTransport(counter, "two")
    first.record(True)
    second.record(True)
    first.record(True)
    with pytest.raises(httpx.ConnectError, match="budget"):
        second.record(True)
    import json

    assert json.loads(counter.read_text()) == {
        "model_post_calls": 3,
        "http_counts": {"one:alias_POST": 2, "two:alias_POST": 1},
    }
