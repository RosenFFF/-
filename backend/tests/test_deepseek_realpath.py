"""Opt-in real DeepSeek/OCR/non-owner PostgreSQL RLS/Redis acceptance.

Only synthetic invoice data is sent; evidence excludes credentials and model prose.
"""

import json
import os
import time
from pathlib import Path

import pytest

from app.main import create_app

from .conftest import Api, _seed, make_settings
from .samples import invoice_image
from .test_documents import _upload
from .test_m1_chat_sse import parse_sse


@pytest.mark.skipif(os.environ.get("RUN_DEEPSEEK_E2E") != "1", reason="RUN_DEEPSEEK_E2E=1 required")
async def test_deepseek_real_pg_redis_review_and_sse(tmp_path, postgres_rls_db, live_redis):
    key = os.environ.get("DEEPSEEK_API_KEY")
    assert key, "DEEPSEEK_API_KEY required (value withheld)"
    evidence = Path(os.environ["DEEPSEEK_EVIDENCE_DIR"])
    evidence.mkdir(parents=True, exist_ok=True)

    def save(name, data):
        evidence.joinpath(name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    settings = make_settings(
        tmp_path,
        database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False),
        demo_mode=False,
        llm_provider_chain=["deepseek", "qwen", "ollama"],
        deepseek_api_key=key,
        ollama_base_url="http://127.0.0.1:11434",
        llm_timeout_s=120,
        llm_max_retries=0,
        model_probe_timeout_s=5,
        chat_generation_timeout_s=180,
    )
    redis, _ = live_redis
    app = create_app(settings, redis=redis)
    started = time.perf_counter()
    result = {
        "success": False,
        "scope": (
            "real DeepSeek, RapidOCR, PostgreSQL non-owner FORCE RLS and isolated loopback Redis; "
            "HTTP via ASGITransport; inline tasks; synthetic invoice"
        ),
        "business_code_base": "8c42d49",
        "startup_gates": "unmodified and executed",
    }
    save("realpath.json", result)
    async with app.router.lifespan_context(app):
        await _seed(app)
        api = Api(app, settings)
        client = await api.login("reviewer")
        try:
            ready = await client.get("/api/v1/readyz")
            save("readyz.json", {"http_status": ready.status_code, "response": ready.json()})
            probe = await client.get("/api/v1/system/models")
            save("models-probe.json", {"http_status": probe.status_code, "response": probe.json()})
            assert probe.status_code == 200
            assert probe.json()["degrade_level"] == "L0"
            assert any(
                m["provider"] == "deepseek" and m["healthy"] for m in probe.json()["models"] if m["category"] == "llm"
            )
            assert ready.status_code == 200
            t0 = time.perf_counter()
            uploaded = await _upload(client, invoice_image())
            assert uploaded.status_code == 202
            doc_id = uploaded.json()["id"]
            recognition = (await client.get(f"/api/v1/documents/{doc_id}/recognition")).json()
            result["upload_extraction_ms"] = round((time.perf_counter() - t0) * 1000)
            result["recognition"] = {
                "degrade_level": recognition["degrade_level"],
                "field_count": len(recognition["fields"]),
                "llm_grounded_fields": sum(
                    f["source"] == "llm" and bool(f["source_block_ids"]) for f in recognition["fields"]
                ),
                "ocr_blocks": len(recognition["ocr"]["blocks"]),
            }
            save("realpath.json", result)
            assert result["recognition"]["llm_grounded_fields"] > 0
            assert recognition["degrade_level"] == "L0"
            t0 = time.perf_counter()
            created = await client.post("/api/v1/reviews", json={"document_ids": [doc_id], "destination_country": "VN"})
            assert created.status_code == 202
            review_id = created.json()["id"]
            report = (await client.get(f"/api/v1/reviews/{review_id}")).json()
            result["review_ms"] = round((time.perf_counter() - t0) * 1000)
            result["review"] = {
                "status": report["status"],
                "degrade_level": report["degrade_level"],
                "llm_verified": report["llm_verified"],
                "models": report["models"],
                "finding_counts": report["finding_counts"],
                "finding_sources": [f["determined_by"] for f in report["findings"]],
                "citation_count": sum(len(f["citations"]) for f in report["findings"]),
                "security": report["security"],
            }
            save("realpath.json", result)
            assert report["status"] == "completed"
            assert report["degrade_level"] == "L0" and report["llm_verified"]
            assert any(f["determined_by"] == "llm" and f["citations"] for f in report["findings"])
            for task in ("field_extraction", "compliance_reasoning"):
                assert any(
                    t["provider"] == "deepseek" and t["task"] == task and t["status"] != "failed"
                    for t in report["models"]
                )
            assert all(t["provider"] != "fake" for t in report["models"])
            t0 = time.perf_counter()
            body = {"content": "In one short sentence, what destination country is this report for?", "language": "en"}
            path = f"/api/v1/reviews/{review_id}/messages"
            response = await client.post(path, json=body, headers={"Accept": "text/event-stream"})
            events = parse_sse(response)
            names = [e["event"] for e in events]
            done = events[-1]["data"] if names and names[-1] == "done" else {}
            result["sse"] = {
                "http_status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000),
                "event_counts": {n: names.count(n) for n in ("delta", "citation", "done", "error")},
                "output_chars": len(done.get("content", "")),
                "blocked": done.get("blocked"),
                "models": done.get("models", []),
                "error_codes": [e["data"].get("code") for e in events if e["event"] == "error"],
            }
            save("realpath.json", result)
            assert response.status_code == 200 and "delta" in names and "error" not in names
            assert done.get("content") and not done.get("blocked", True)
            assert any(t["provider"] == "deepseek" and t["status"] != "failed" for t in done["models"])
            assert all(t["provider"] != "fake" for t in done["models"])
            assert "".join(e["data"]["text"] for e in events if e["event"] == "delta") == done["content"]
            sid = response.headers["x-chat-stream-id"]
            replay = await client.post(
                path, json=body, headers={"Accept": "text/event-stream", "Last-Event-ID": f"{sid}:0"}
            )
            assert parse_sse(replay) == events
            result["sse"]["completed_replay_verified"] = True
            other = await api.login("reviewer2")
            try:
                assert (await other.get(f"/api/v1/reviews/{review_id}")).status_code == 404
            finally:
                await other.aclose()
            admin = await api.login("admin")
            try:
                audit = (await admin.get("/api/v1/audit/verify")).json()
                assert audit["valid"] and audit["checked"] >= 3
                result["audit"] = {"valid": audit["valid"], "checked": audit["checked"]}
            finally:
                await admin.aclose()
            result["success"] = True
            result["total_ms"] = round((time.perf_counter() - started) * 1000)
            save("realpath.json", result)
        finally:
            await client.aclose()
