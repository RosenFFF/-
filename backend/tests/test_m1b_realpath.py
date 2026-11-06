"""Opt-in REAL RapidOCR -> local Ollama extraction -> RAG -> Ollama review, no mock transport."""

import json
import os
import time
from pathlib import Path

import pytest

from .samples import invoice_image
from .test_documents import _upload


@pytest.mark.skipif(os.environ.get("RUN_OLLAMA_E2E") != "1", reason="需要本机 Ollama；RUN_OLLAMA_E2E=1 显式运行")
async def test_real_ollama_upload_to_review(make_api):
    api = await make_api(
        llm_provider_chain=["ollama"],
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b"),
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
        "success": (
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
    # Only sanitized metadata; no cookies, credentials, document text or model prose in this artifact.
    if os.environ.get("REALPATH_RESULT_FILE"):
        Path(os.environ["REALPATH_RESULT_FILE"]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("realpath=" + json.dumps(result, ensure_ascii=False))
    assert result["success"], result
    for task in ("field_extraction", "compliance_reasoning"):
        assert any(
            t["provider"] == "ollama" and t["task"] == task and t["status"] != "failed" for t in report["models"]
        )
    assert all(t["provider"] != "fake" for t in report["models"])
    citations, _ = api.app.state.ai.rag.search("商业发票必要项 quantity currency")
    assert any(c.get("url", "") and c["url"].startswith("https://") for c in citations)
    await client.aclose()
