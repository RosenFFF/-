"""Opt-in real DeepSeek multi-question SSE regression + failure-stage diagnosis.

Evidence records counts, rule ids, stages and timing only; never model prose, prompts or credentials.
"""

import json
import os
import re
import time
from pathlib import Path

import pytest

from app.main import create_app
from app.security.injection import inspect, out_of_scope
from app.security.output import _PROMPT_LEAK, redact_secrets
from app.security.redact import mask
from app.services.chat import _CITATION

from .conftest import Api, _seed, make_settings
from .samples import invoice_image
from .test_documents import _upload
from .test_m1_chat_sse import parse_sse

QUESTIONS = [
    ("broad_fields", "What invoice fields should I verify next?"),
    ("broad_risks", "Summarize the main compliance risks in this report and what to do about them."),
    ("broad_zh", "这份报告里最需要优先处理的问题是什么？请给出下一步建议。"),
    ("rule_explain", "Explain which rules the findings rely on and why they matter."),
    ("short_country", "In one short sentence, what destination country is this report for?"),
]


def classify(text, allowed, report_rule_ids, max_chars):
    """Stage against question-only retrieval (pre-fix allow-set); rejected text is never persisted."""
    if not text.strip():
        return {"stage": "empty_or_incomplete"}
    if len(text) > max_chars:
        return {"stage": "output_too_long", "chars": len(text)}
    n = inspect(text)
    flags = {
        "injection_pattern": n.detected,
        "prompt_leak": bool(_PROMPT_LEAK.search(n.text)),
        "out_of_scope": out_of_scope(n.text),
        "secret_pattern": redact_secrets(n.text) != n.text,
        "pii_kinds": sorted(mask(text).counts),
    }
    cited = list(dict.fromkeys(_CITATION.findall(text)))
    bad = [c for c in cited if c not in allowed]
    detail = {
        "chars": len(text),
        "output_flags": flags,
        "cited_count": len(cited),
        "disallowed_citations": [
            {
                "id_shape": "rule_id_from_report"
                if c in report_rule_ids
                else ("placeholder_like" if re.fullmatch(r"[A-Z]+_\d+", c) else "other_bracket_token"),
                "id": c if c in report_rule_ids else None,
            }
            for c in bad
        ],
    }
    if any(v for k, v in flags.items()):
        detail["stage"] = "output_filter"
    elif bad:
        detail["stage"] = "cites_outside_question_retrieval"
    else:
        detail["stage"] = "would_pass_checks"
    return detail


@pytest.mark.skipif(os.environ.get("RUN_DEEPSEEK_E2E") != "1", reason="RUN_DEEPSEEK_E2E=1 required")
async def test_deepseek_multi_question_sse_diagnosis(tmp_path, postgres_rls_db, live_redis):
    key = os.environ.get("DEEPSEEK_API_KEY")
    assert key, "DEEPSEEK_API_KEY required (value withheld)"
    out = Path(os.environ["DEEPSEEK_EVIDENCE_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    settings = make_settings(
        tmp_path,
        database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False),
        demo_mode=False,
        llm_provider_chain=["deepseek", "qwen", "ollama"],
        deepseek_api_key=key,
        llm_timeout_s=120,
        llm_max_retries=0,
        model_probe_timeout_s=5,
        chat_generation_timeout_s=180,
    )
    redis, _ = live_redis
    app = create_app(settings, redis=redis)
    results = {"scope": "real DeepSeek/OCR/PG RLS/Redis; ASGITransport; inline; synthetic invoice", "questions": []}
    async with app.router.lifespan_context(app):
        await _seed(app)
        api = Api(app, settings)
        client = await api.login("reviewer")
        try:
            doc = (await _upload(client, invoice_image())).json()["id"]
            created = await client.post("/api/v1/reviews", json={"document_ids": [doc], "destination_country": "VN"})
            rid = created.json()["id"]
            report = (await client.get(f"/api/v1/reviews/{rid}")).json()
            results["review"] = {"degrade_level": report["degrade_level"], "llm_verified": report["llm_verified"]}
            report_rule_ids = {c["rule_id"] for f in report["findings"] for c in f.get("citations", [])}
            captured = {}
            llm, rag = app.state.ai.llm, app.state.ai.rag
            original_stream, original_search = llm.chat_stream, rag.search

            async def stream(messages, *, task="chat"):
                parts = []
                async for chunk in original_stream(messages, task=task):
                    parts.append(chunk.text)
                    yield chunk
                captured["text"] = "".join(parts)  # memory only

            def search(query, *a, **kw):
                cites, traces = original_search(query, *a, **kw)
                captured["allowed"] = [c["rule_id"] for c in cites]
                return cites, traces

            llm.chat_stream, rag.search = stream, search
            rounds = int(os.environ.get("DEEPSEEK_SSE_ROUNDS", "1"))
            corpus_report_ids = {r for r in report_rule_ids if r in rag.rules}
            for round_no, (label, question) in [(n, q) for n in range(1, rounds + 1) for q in QUESTIONS]:
                captured.clear()
                t0 = time.perf_counter()
                r = await client.post(
                    f"/api/v1/reviews/{rid}/messages",
                    json={"content": question, "language": "en"},
                    headers={"Accept": "text/event-stream"},
                )
                events = parse_sse(r)
                names = [e["event"] for e in events]
                done = events[-1]["data"] if names and names[-1] == "done" else {}
                cited = [e["data"]["rule_id"] for e in events if e["event"] == "citation"]
                permitted = set(captured.get("allowed") or []) | corpus_report_ids
                replay_ok = None
                if done:
                    sid = r.headers["x-chat-stream-id"]
                    replay = await client.post(
                        f"/api/v1/reviews/{rid}/messages",
                        json={"content": question, "language": "en"},
                        headers={"Accept": "text/event-stream", "Last-Event-ID": f"{sid}:0"},
                    )
                    replay_ok = parse_sse(replay) == events
                item = {
                    "round": round_no,
                    "label": label,
                    "http_status": r.status_code,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000),
                    "output_chars": len(done.get("content", "")),
                    "delta_concat_equals_done": "".join(e["data"]["text"] for e in events if e["event"] == "delta")
                    == done.get("content"),
                    "cited_rule_ids": cited,
                    "cited_within_retrieved_or_report": set(cited) <= permitted,
                    "llm_providers": sorted(
                        {t["provider"] for t in done.get("models", []) if t.get("category") == "llm"}
                    ),
                    "completed_replay_identical": replay_ok,
                    "error_codes": [e["data"].get("code") for e in events if e["event"] == "error"],
                    "events": {n: names.count(n) for n in ("delta", "citation", "done", "error")},
                    "success": "done" in names and "error" not in names,
                    "retrieved_rule_ids": captured.get("allowed"),
                    "report_rule_ids_in_retrieved": sorted(report_rule_ids & set(captured.get("allowed") or [])),
                }
                item["diagnosis"] = classify(
                    captured.get("text", ""),
                    set(captured.get("allowed") or []),
                    report_rule_ids,
                    settings.chat_max_output_chars,
                )
                captured.pop("text", None)
                results["questions"].append(item)
            results["report_rule_ids"] = sorted(report_rule_ids)
        finally:
            await client.aclose()
            out.joinpath("diagnosis.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    if os.environ.get("DEEPSEEK_SSE_DIAGNOSE_ONLY") == "1":
        return
    assert results["review"] == {"degrade_level": "L0", "llm_verified": True}
    for q in results["questions"]:
        assert q["http_status"] == 200 and q["success"], (q["label"], q["diagnosis"]["stage"])
        assert q["events"]["delta"] >= 1 and q["events"]["error"] == 0
        assert q["delta_concat_equals_done"] and q["completed_replay_identical"]
        assert q["cited_within_retrieved_or_report"]
        assert "deepseek" in q["llm_providers"] and "fake" not in q["llm_providers"]
