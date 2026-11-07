"""Model probe diagnostics contain no exception text or authentication material."""

import logging

import httpx
import pytest

from app.ai.llm import ProviderChain

from .conftest import make_settings


@pytest.mark.parametrize("timeout", [True, False])
async def test_alias_probe_timeout_and_success(tmp_path, caplog, timeout):
    secret = "synthetic-probe-sensitive-value"
    settings = make_settings(tmp_path, deepseek_api_key=secret, demo_mode=False)
    assert settings.model_probe_timeout_s == 4
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.extensions["timeout"]["read"] == 4
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "other-model"}]})
        assert request.read() and request.headers["authorization"] == f"Bearer {secret}"
        if timeout:
            raise httpx.ReadTimeout(secret, request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    chain = ProviderChain(settings, transport=httpx.MockTransport(handle))
    with caplog.at_level(logging.WARNING, logger="app.ai.llm"):
        health = await chain._probe(chain.providers[0])
    assert calls == ["GET", "POST"]
    assert health["healthy"] is (not timeout)
    if timeout:
        record = next(r for r in caplog.records if r.message == "model_probe_failed")
        assert (record.provider, record.stage, record.exception_class) == ("deepseek", "alias_check", "ReadTimeout")
    else:
        assert not caplog.records
    assert secret not in caplog.text
    assert all(secret not in str(r.__dict__) for r in caplog.records)


async def test_list_probe_warning_never_includes_upstream_text(tmp_path, caplog):
    secret = "sensitive-exception-payload"
    settings = make_settings(tmp_path, deepseek_api_key=secret)

    def handle(request):
        raise httpx.ConnectError(secret, request=request)

    chain = ProviderChain(settings, transport=httpx.MockTransport(handle))
    with caplog.at_level(logging.WARNING, logger="app.ai.llm"):
        health = await chain._probe(chain.providers[0])
    assert not health["healthy"]
    record = caplog.records[-1]
    assert (record.provider, record.stage, record.exception_class) == ("deepseek", "list_models", "ConnectError")
    assert secret not in str(record.__dict__)
