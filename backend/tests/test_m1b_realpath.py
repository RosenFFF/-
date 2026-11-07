"""Opt-in REAL RapidOCR -> local Ollama extraction -> RAG -> Ollama review, no mock transport."""

import json
import os
import time
from pathlib import Path

import httpx
import pytest

from .samples import invoice_image
from .test_documents import _upload
from .test_m1_chat_sse import parse_sse


@pytest.mark.skipif(os.environ.get("RUN_OLLAMA_E2E") != "1", reason="需要本机 Ollama；RUN_OLLAMA_E2E=1 显式运行")
async def test_real_ollama_upload_to_review(make_api):
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
    async with httpx.AsyncClient(timeout=10) as upstream:
        tags = await upstream.get(f"{base_url}/api/tags")
        tags.raise_for_status()
        installed = next((m for m in tags.json()["models"] if m.get("name") == model), None)
        assert installed and installed.get("digest"), "Requested real model is not installed"
    api = await make_api(
        demo_mode=False,
        llm_provider_chain=["ollama"],
        ollama_base_url=base_url,
        ollama_model=model,
        llm_timeout_s=120,
        llm_max_retries=0,
        llm_max_tokens=2048,
    )
    start = time.perf_counter()
    client = await api.login("reviewer")
    uploaded = await _upload(client, invoice_image())
    assert uploaded.status_code == 202, uploaded.text
    doc_id = uploaded.json()["id"]
    recognition = (await client.get(f"/api/v1/documents/{doc_id}/recognition")).json()
    assert recognition["ocr"]["blocks"]
    created = await client.post("/api/v1/reviews", json={"document_ids": [doc_id], "destination_country": "VN"})
    assert created.status_code == 202, created.text
    review_id = created.json()["id"]
    report = (await client.get(f"/api/v1/reviews/{review_id}")).json()
    result = {
        "model": api.settings.ollama_model,
        "installed_model_digest": installed["digest"],
        "infrastructure_scope": "real Ollama and OCR; SQLite and fakeredis test infrastructure",
        "inference_success": (
            report["status"] == "completed"
            and report["degrade_level"] == "L2"
            and recognition["degrade_level"] == "L2"
            and any(f["source"] == "llm" and f["source_block_ids"] for f in recognition["fields"])
        ),
        "recognition_degrade_level": recognition["degrade_level"],
        "elapsed_ms": round((time.perf_counter() - start) * 1000),
        "degrade_level": report["degrade_level"],
        "field_count": len(recognition["fields"]),
        "grounded_field_count": sum(bool(f["source_block_ids"]) for f in recognition["fields"]),
        "rule_corpus": report["security"]["rule_corpus"],
        "retrieval_mode": report["security"]["retrieval_mode"],
        "models": report["models"],
    }
    result["success"] = False  # Overall acceptance also requires real SSE and replay.
    # Only sanitized metadata; no cookies, credentials, document text or model prose in this artifact.
    if os.environ.get("REALPATH_RESULT_FILE"):
        Path(os.environ["REALPATH_RESULT_FILE"]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("realpath=" + json.dumps(result, ensure_ascii=False))
    assert result["inference_success"], result
    for task in ("field_extraction", "compliance_reasoning"):
        assert any(
            t["provider"] == "ollama" and t["task"] == task and t["status"] != "failed" for t in report["models"]
        )
    assert all(t["provider"] != "fake" for t in report["models"])
    citations, _ = api.app.state.ai.rag.search("商业发票必要项 quantity currency")
    assert any(c.get("url", "") and c["url"].startswith("https://") for c in citations)
    response = await client.post(
        f"/api/v1/reviews/{review_id}/messages",
        json={"content": "What invoice fields should I verify next?", "language": "en"},
        headers={"Accept": "text/event-stream"},
    )
    events = parse_sse(response)
    names = [event["event"] for event in events]
    done = events[-1]["data"] if names and names[-1] == "done" else {}
    sse_success = (
        response.status_code == 200
        and "delta" in names
        and "error" not in names
        and bool(done.get("content"))
        and not done.get("blocked", True)
        and any(t["provider"] == "ollama" and t["status"] != "failed" for t in done.get("models", []))
        and all(t["provider"] != "fake" for t in done.get("models", []))
    )
    result["sse"] = {
        "success": sse_success,
        "event_counts": {name: names.count(name) for name in ("delta", "citation", "done", "error")},
        "models": done.get("models", []),
        "output_chars": len(done.get("content", "")),
    }
    result["infrastructure_scope"] = "real Ollama and OCR; SQLite and fakeredis test infrastructure"
    if os.environ.get("REALPATH_RESULT_FILE"):
        Path(os.environ["REALPATH_RESULT_FILE"]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    assert sse_success, result["sse"]
    assert "".join(e["data"]["text"] for e in events if e["event"] == "delta") == done["content"]
    sid = response.headers["x-chat-stream-id"]
    replay = await client.post(
        f"/api/v1/reviews/{review_id}/messages",
        json={"content": "What invoice fields should I verify next?", "language": "en"},
        headers={"Accept": "text/event-stream", "Last-Event-ID": f"{sid}:0"},
    )
    assert parse_sse(replay) == events
    result["sse"]["completed_replay_verified"] = True
    result["success"] = True
    if os.environ.get("REALPATH_RESULT_FILE"):
        Path(os.environ["REALPATH_RESULT_FILE"]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    await client.aclose()
