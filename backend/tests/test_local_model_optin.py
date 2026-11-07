"""Mock-only opt-in and per-capability evidence; NEVER real model calls."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.ai.llm import ProviderChain, health_level
from app.ai.ocr import OcrBlock, ocr_engine
from app.ai.types import Extraction, ModelUnavailable, trace
from app.audit.service import Actor
from app.services.chat import message_out
from app.services.provenance import degrade_fields

from .conftest import make_settings
from .test_m1_chat_sse import parse_sse, path, upstream_frames
from .test_m1_llm import envelope
from .test_m1_pipeline import _report


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_ENABLED", raising=False)

    async def forbidden(*args, **kwargs):
        pytest.fail("real HTTP transport forbidden: mock evidence only")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.fixture
def fixture_ocr(monkeypatch):
    monkeypatch.setattr(ocr_engine, "_engine", object())
    monkeypatch.setattr(ocr_engine, "load", lambda: None)
    monkeypatch.setattr(
        ocr_engine,
        "recognize",
        lambda _: (
            [
                OcrBlock("INVOICE NO: SR-2026-001", [0.05, 0.1, 0.8, 0.2], 0.99),
                OcrBlock("TOTAL: USD 12,500.00", [0.05, 0.3, 0.8, 0.4], 0.99),
            ],
            1,
        ),
    )


def test_default_off_and_environment_optin(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_ENABLED", raising=False)
    assert make_settings(tmp_path).local_model_enabled is False
    for raw, expected in (("true", True), ("false", False), ("1", True), ("0", False)):
        monkeypatch.setenv("LOCAL_MODEL_ENABLED", raw)
        assert make_settings(tmp_path).local_model_enabled is expected
    monkeypatch.setenv("LOCAL_MODEL_ENABLED", "not-a-bool")
    with pytest.raises(ValidationError):
        make_settings(tmp_path)


@pytest.mark.parametrize(
    "order",
    [
        ["deepseek", "qwen", "ollama"],
        ["ollama"],
        ["ollama", "deepseek"],
        ["deepseek", "ollama", "qwen"],
    ],
)
async def test_default_excludes_local_from_all_operations_and_probes(tmp_path, monkeypatch, order):
    monkeypatch.delenv("LOCAL_MODEL_ENABLED", raising=False)

    def forbidden(request):
        pytest.fail("unconfigured cloud or disabled Ollama reached transport")

    chain = ProviderChain(make_settings(tmp_path, llm_provider_chain=order), transport=httpx.MockTransport(forbidden))
    original = chain._probe

    async def spy(provider):
        assert provider.name != "ollama"
        return await original(provider)

    monkeypatch.setattr(chain, "_probe", spy)
    assert [p.name for p in chain.providers] == [p for p in order if p != "ollama"]
    assert (await chain.chat_json([], Extraction, task="field_extraction")).degrade_level == "L3"
    assert (await chain.chat_text([], task="chat")).degrade_level == "L3"
    with pytest.raises(ModelUnavailable):
        _ = [chunk async for chunk in chain.chat_stream([], task="chat")]
    items = await chain.health()
    assert health_level(items) == "L3"
    local = next(m for m in items if m["provider"] == "ollama")
    assert local["enabled"] is local["healthy"] is local["circuit_open"] is False
    assert local["disabled_reason"] == "local_model_disabled"


def replay_transport(settings, cloud, modes, requests):
    def handle(request):
        host = request.url.host
        requests.append((host, request.method, request.url.path))
        local = host == "ollama.invalid"
        if local:
            assert settings.local_model_enabled, "disabled Ollama was contacted"
        if request.method == "GET":
            if local:
                return httpx.Response(200, json={"models": [{"name": settings.ollama_model}]})
            if not (cloud == "primary" or (cloud == "secondary" and host == "qwen.invalid")):
                raise httpx.ConnectError("fixture cloud unavailable", request=request)
            model = settings.deepseek_model if host == "deepseek.invalid" else settings.qwen_model
            return httpx.Response(200, json={"data": [{"id": model}]})
        body = json.loads(request.content)
        if body["stream"]:
            task = "chat"
        else:
            schema = json.loads(body["messages"][0]["content"].split("schema: ", 1)[1])
            task = "extraction" if "fields" in schema["properties"] else "review"
        mode = modes.get(task, cloud) if modes else cloud
        if not (local or mode == "primary" or (mode == "secondary" and host == "qwen.invalid")):
            raise httpx.ConnectError("fixture cloud unavailable", request=request)
        if task == "chat":
            return httpx.Response(200, text=upstream_frames("TEST FIXTURE ONLY: Review with a human."))
        data = (
            {"fields": [{"key": "invoice_no", "value": "SR-2026-001", "confidence": 0.9}]}
            if task == "extraction"
            else {
                "summary": "TEST FIXTURE ONLY: Manual review required.",
                "findings": [],
            }
        )
        return httpx.Response(200, json=envelope(data))

    return httpx.MockTransport(handle)


async def configured_api(make_api, *, enabled=None, cloud="down", modes=None):
    options = {"local_model_enabled": enabled} if enabled is not None else {}
    api = await make_api(
        **options,
        llm_provider_chain=["deepseek", "qwen", "ollama"],
        deepseek_api_key="fixture-only",
        qwen_api_key="fixture-only",
        deepseek_base_url="https://deepseek.invalid",
        qwen_base_url="https://qwen.invalid",
        ollama_base_url="http://ollama.invalid",
        llm_max_retries=0,
        llm_circuit_failures=100,
        rl_chat_per_min=100,
    )
    requests = []
    api.app.state.ai.llm = ProviderChain(api.settings, transport=replay_transport(api.settings, cloud, modes, requests))
    return api, requests


def assert_degrade(result, level):
    assert {k: result[k] for k in degrade_fields(level)} == degrade_fields(level)


@pytest.mark.parametrize(
    "enabled,cloud,expected",
    [
        (None, "down", "L3"),
        (True, "down", "L2"),
        (None, "primary", "L0"),
        (True, "primary", "L0"),
        (None, "secondary", "L1"),
        (True, "secondary", "L1"),
    ],
)
async def test_capability_and_health_matrix(make_api, fixture_ocr, enabled, cloud, expected):
    api, requests = await configured_api(make_api, enabled=enabled, cloud=cloud)
    client = await api.login("reviewer")
    ready = await client.get("/api/v1/readyz")
    assert ready.status_code == 200 and ready.json()["degrade_level"] == expected
    assert ready.json()["status"] == ("ready" if expected == "L0" else "degraded")
    status = (await client.get("/api/v1/system/models")).json()
    assert status["degrade_level"] == expected
    assert status["local_model_enabled"] is bool(enabled)
    assert status["llm_provider_chain"] == ["deepseek", "qwen", "ollama"]
    assert status["effective_llm_provider_chain"] == ["deepseek", "qwen"] + (["ollama"] if enabled else [])
    local = next(m for m in status["models"] if m["provider"] == "ollama")
    assert local["enabled"] is bool(enabled)
    assert local["disabled_reason"] == (None if enabled else "local_model_disabled")
    doc, rid, report = await _report(api, client)
    rec = (await client.get(f"/api/v1/documents/{doc}/recognition")).json()
    assert_degrade(rec, expected)
    assert_degrade(report, expected)
    assert report["status"] == "completed"
    assert rec["fields"] and all(f["source"] == ("rule" if expected == "L3" else "llm") for f in rec["fields"])
    if expected == "L3":
        assert all(f["determined_by"] == "rule" for f in report["findings"])
        assert "规则引擎降级，需人工复核" in report["summary"]
    response = await client.post(
        path(rid), json={"content": "Explain the finding"}, headers={"Accept": "text/event-stream"}
    )
    events = parse_sse(response)
    terminal = events[-1]
    assert terminal["event"] == ("error" if expected == "L3" else "done")
    assert_degrade(terminal["data"], expected)
    before = len(requests)
    replay = await client.post(
        path(rid),
        json={"content": "Explain the finding"},
        headers={
            "Accept": "text/event-stream",
            "Last-Event-ID": terminal["id"].rsplit(":", 1)[0] + ":0",
        },
    )
    assert parse_sse(replay) == events and len(requests) == before
    history = (await client.get(path(rid))).json()["items"]
    assert len(requests) == before
    if expected != "L3":
        assert history[-1] == terminal["data"]
    else:
        assert [m["role"] for m in history] == ["user"]
    response = await client.post(path(rid), json={"content": "Explain the finding"})
    assert response.status_code == (503 if expected == "L3" else 200)
    assert_degrade(response.json(), expected)
    if not enabled:
        assert all(host != "ollama.invalid" for host, _, _ in requests)
    await client.aclose()


@pytest.mark.parametrize(
    "enabled,modes,expected",
    [
        (False, {"extraction": "primary", "review": "down", "chat": "down"}, ["L0", "L3", "L3"]),
        (True, {"extraction": "down", "review": "primary", "chat": "down"}, ["L2", "L0", "L2"]),
    ],
)
async def test_capabilities_do_not_inherit_system_or_each_other_levels(make_api, fixture_ocr, enabled, modes, expected):
    api, _ = await configured_api(make_api, enabled=enabled, cloud="primary", modes=modes)
    client = await api.login("reviewer")
    assert (await client.get("/api/v1/system/models")).json()["degrade_level"] == "L0"
    doc, rid, report = await _report(api, client)
    rec = (await client.get(f"/api/v1/documents/{doc}/recognition")).json()
    response = await client.post(
        path(rid), json={"content": "Explain the finding"}, headers={"Accept": "text/event-stream"}
    )
    terminal = parse_sse(response)[-1]["data"]
    assert [r["degrade_level"] for r in (rec, report, terminal)] == expected
    await client.aclose()


async def test_optin_but_not_in_declared_chain_stays_disabled(tmp_path):
    cfg = make_settings(tmp_path, local_model_enabled=True, llm_provider_chain=["deepseek"])
    chain = ProviderChain(cfg, transport=httpx.MockTransport(lambda _: pytest.fail("no configured key")))
    local = next(m for m in await chain.health() if m["provider"] == "ollama")
    assert local["enabled"] is False and local["disabled_reason"] == "not_in_provider_chain"
    assert (await chain.chat_json([], Extraction, task="field_extraction")).degrade_level == "L3"


async def test_historical_audit_does_not_enable_disabled_model_or_circuit(api, fixture_ocr):
    client = await api.login("reviewer")
    me = (await client.get("/api/v1/auth/me")).json()
    assert api.settings.local_model_enabled is False
    detail = trace("llm", api.settings.ollama_model, "chat", 17, provider="ollama", status="failed")
    for _ in range(api.settings.llm_circuit_failures):
        await api.app.state.audit.record(
            "model.call", "failed", actor=Actor(id=me["id"], tenant_id=me["tenant_id"]), detail=detail
        )
    status = (await client.get("/api/v1/system/models")).json()
    local = next(m for m in status["models"] if m["provider"] == "ollama")
    assert local["calls_24h"] == api.settings.llm_circuit_failures and local["p95_latency_ms"] == 17
    assert local["enabled"] is local["healthy"] is local["circuit_open"] is False
    assert status["degrade_level"] == "L3"
    local["healthy"] = True
    assert health_level([local]) == "L3"
    assert health_level([local, {"category": "llm", "provider": "deepseek", "enabled": True, "healthy": True}]) == "L0"
    await client.aclose()


@pytest.mark.parametrize(
    "role,blocked,models",
    [
        ("user", False, []),
        ("assistant", True, []),
        (
            "assistant",
            False,
            [trace("llm", "legacy-model", "chat", 1, provider="ollama")],
        ),
    ],
)
def test_no_inferred_local_badge_for_user_blocked_or_legacy(role, blocked, models):
    row = SimpleNamespace(
        role=role,
        blocked=blocked,
        models=models,
        created_at=datetime.now(UTC),
        id="fixture",
        content="TEST FIXTURE ONLY",
        block_reason=None,
        language="en",
        citations=[],
        aigc_meta={},
    )
    result = message_out(row)
    assert result["degrade_level"] is result["degrade_status"] is result["degrade_warning"] is None
    assert result["llm_verified"] is False
