"""Opt-in live Ollama absence probe; API harness uses SQLite/fakeredis, never FakeLLM.

This is blocked/degradation evidence, NOT a successful inference acceptance test.
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from .test_m1_chat_sse import parse_sse, seed_review


@pytest.mark.skipif(os.environ.get("RUN_MODEL_PROBE") != "1", reason="opt-in live model availability probe")
async def test_live_empty_ollama_reports_l3_and_explicit_sse_error(make_api):
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    async with httpx.AsyncClient(timeout=5) as upstream:
        tags = await upstream.get(f"{base}/api/tags")
        tags.raise_for_status()
        if tags.json().get("models"):
            pytest.skip("Ollama has models; run RUN_OLLAMA_E2E=1 for real inference acceptance")
    api = await make_api(
        demo_mode=False,
        llm_provider_chain=["deepseek", "qwen", "ollama"],
        deepseek_api_key=None,
        qwen_api_key=None,
        ollama_base_url=base,
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b"),
        llm_max_retries=0,
    )
    client = await api.login("reviewer")
    try:
        response = await client.get("/api/v1/system/models")
        assert response.status_code == 200
        health = response.json()
        assert health["degrade_level"] == "L3"
        llms = [m for m in health["models"] if m["category"] == "llm"]
        assert len(llms) == 3 and all(not m["healthy"] for m in llms)
        rid = await seed_review(api)  # Synthetic review context, not a generated real report.
        response = await client.post(
            f"/api/v1/reviews/{rid}/messages",
            json={"content": "What should I verify next?", "language": "en"},
            headers={"Accept": "text/event-stream"},
        )
        events = parse_sse(response)
        assert response.status_code == 200
        assert [e["event"] for e in events] == ["error"]
        assert events[0]["data"]["code"] == "MODEL_UNAVAILABLE"
        assert events[0]["data"]["status"] == 503
        result = {
            "real_inference_verified": False,
            "real_sse_success_verified": False,
            "degradation_probe_passed": True,
            "scope": "real local Ollama HTTP; SQLite/fakeredis API harness; synthetic review; no FakeLLM",
            "cloud_keys": "deliberately absent in probe; not a cloud connectivity test",
            "system_models": health,
            "sse": {
                "http_status": response.status_code,
                "events": ["error"],
                "code": "MODEL_UNAVAILABLE",
                "problem_status": 503,
            },
        }
        if os.environ.get("MODEL_PROBE_RESULT_FILE"):
            Path(os.environ["MODEL_PROBE_RESULT_FILE"]).write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
    finally:
        await client.aclose()
