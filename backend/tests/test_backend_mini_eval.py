"""Opt-in real providers, real OCR/PG FORCE RLS/isolated Redis. Counts/timings only."""

import json
import math
import os
import time
from collections import Counter
from pathlib import Path

import pytest

from app.main import create_app
from eval.finding_metrics import finding_metadata, score_findings
from eval.synthetic import samples

from .conftest import Api, _seed, make_settings
from .samples import invoice_image
from .test_documents import _upload
from .test_m1_chat_sse import parse_sse


def percentiles(values):
    values = sorted(values)
    return {
        k: values[min(len(values) - 1, math.ceil(len(values) * p) - 1)] if values else None
        for k, p in (("p50", 0.5), ("p95", 0.95), ("max", 1))
    }


class WireTiming:
    """Observe actual ASGI SSE send frames, not buffered httpx receive times."""

    def __init__(self, app, measurements):
        self.app, self.measurements = app, measurements

    async def __call__(self, scope, receive, send):
        started = time.perf_counter()
        timing = {}

        async def observe(message):
            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                for event in ("delta", "done"):
                    if (b"event: " + event.encode()) in body and event not in timing:
                        timing[event] = round((time.perf_counter() - started) * 1000)
            await send(message)

        await self.app(scope, receive, observe)
        if scope["type"] == "http" and scope["path"].endswith("/messages"):
            self.measurements.append(timing)


def test_synthetic_labels():
    data = samples()
    assert len(data) == 20
    assert Counter(x["kind"] for x in data) == dict(clean=8, missing=3, hs=3, amount=3, restricted=3)
    assert len({invoice_image(lines=x["lines"]) for x in data}) == 20


@pytest.mark.skipif(os.environ.get("RUN_EVAL_E2E") != "1", reason="RUN_EVAL_E2E=1 required")
async def test_real_backend_mini_eval(tmp_path, postgres_rls_db, live_redis):
    local = os.environ.get("EVAL_PROVIDER") == "ollama"
    out = Path(os.environ["EVAL_EVIDENCE_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    settings = make_settings(
        tmp_path,
        database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False),
        demo_mode=False,
        llm_provider_chain=["deepseek", "qwen", "ollama"],
        deepseek_api_key=None if local else os.environ["DEEPSEEK_API_KEY"],
        qwen_api_key=None,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model=os.environ.get("EVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        llm_timeout_s=120,
        llm_max_retries=0,
        llm_circuit_failures=100,
        model_probe_timeout_s=5,
        chat_generation_timeout_s=300,
    )
    redis, _ = live_redis
    app = create_app(settings, redis=redis)
    measurements = []
    app.add_middleware(WireTiming, measurements=measurements)
    result = dict(
        synthetic=True,
        samples=[],
        field_counts={},
        finding_counts=dict(hit=0, false_positive=0, miss=0),
        corrected_finding_counts=dict(hit=0, extra=0, miss=0),
        provider_counts={},
        level_counts={},
        chat_subset_size=1 if local else 3,
    )

    def save():
        result["review_latency_ms"] = percentiles([x["upload_review_ms"] for x in result["samples"]])
        result["chat_first_delta_ms"] = percentiles(
            [
                x["chat"]["first_delta_ms"]
                for x in result["samples"]
                if x.get("chat", {}).get("first_delta_ms") is not None
            ]
        )
        result["chat_done_ms"] = percentiles(
            [x["chat"]["done_ms"] for x in result["samples"] if x.get("chat", {}).get("done_ms") is not None]
        )
        out.joinpath("metrics.json").write_text(json.dumps(result, indent=2) + "\n")

    save()
    async with app.router.lifespan_context(app):
        await _seed(app)
        client = await Api(app, settings).login("reviewer")
        try:
            probe = (await client.get("/api/v1/system/models")).json()
            result["probe"] = {
                "degrade_level": probe["degrade_level"],
                "llm": [
                    {k: m[k] for k in ("provider", "model", "healthy", "circuit_open")}
                    for m in probe["models"]
                    if m["category"] == "llm"
                ],
            }
            save()
            dataset = samples()[: 1 if local else 20]
            if local and os.environ.get("EVAL_LOCAL_MINIMAL") == "1":
                dataset[0]["lines"] = ["COMMERCIAL INVOICE", "INVOICE NO: SYN-001", "TOTAL: USD 101.00"]
                dataset[0]["fields"] = {
                    k: v if k in {"invoice_no", "total_amount", "currency"} else None
                    for k, v in dataset[0]["fields"].items()
                }
                dataset[0]["expected_rules"] = ["SYN-REQUIRED", "SYN-REVIEW"]
            for sample in dataset:
                started = time.perf_counter()
                upload = await _upload(client, invoice_image(lines=sample["lines"]))
                assert upload.status_code == 202
                doc = upload.json()["id"]
                recognition = (await client.get(f"/api/v1/documents/{doc}/recognition")).json()
                extraction_ms = round((time.perf_counter() - started) * 1000)
                created = await client.post(
                    "/api/v1/reviews", json={"document_ids": [doc], "destination_country": "VN"}
                )
                assert created.status_code == 202
                rid = created.json()["id"]
                report = (await client.get(f"/api/v1/reviews/{rid}")).json()
                item = dict(
                    sample=sample["id"],
                    upload_extraction_ms=extraction_ms,
                    upload_review_ms=round((time.perf_counter() - started) * 1000),
                    recognition_level=recognition["degrade_level"],
                    review_level=report["degrade_level"],
                    llm_verified=report["llm_verified"],
                    completed=report["status"] == "completed",
                    grounded_llm_fields=sum(
                        f["source"] == "llm" and bool(f["source_block_ids"]) for f in recognition["fields"]
                    ),
                    traces=[
                        {k: t.get(k) for k in ("provider", "task", "status", "latency_ms")}
                        for t in report["models"]
                        if t["category"] == "llm"
                    ],
                )
                actual = {f["key"]: f["value"] for f in recognition["fields"]}
                item["field_mismatch_keys"] = []
                for field, expected in sample["fields"].items():
                    count = result["field_counts"].setdefault(field, dict(correct=0, total=0))
                    count["total"] += 1
                    count["correct"] += actual.get(field) == expected
                    if actual.get(field) != expected:
                        item["field_mismatch_keys"].append(field)
                item["expected_rule_ids"] = sample["expected_rules"]
                item["finding_metadata"] = finding_metadata(report["findings"])
                item["finding_score"] = score_findings(sample["expected_rules"], item["finding_metadata"])
                for key, count in item["finding_score"]["corrected"].items():
                    result["corrected_finding_counts"][key] += count
                expected = set(sample["expected_rules"])
                actual_rules = {c["rule_id"] for f in report["findings"] for c in f.get("citations", [])}
                for name, value in (
                    ("hit", len(expected & actual_rules)),
                    ("false_positive", len(actual_rules - expected)),
                    ("miss", len(expected - actual_rules)),
                ):
                    result["finding_counts"][name] += value
                for level in [report["degrade_level"]]:
                    result["level_counts"][level] = result["level_counts"].get(level, 0) + 1
                providers = sorted({t["provider"] for t in item["traces"] if t["status"] != "failed"})
                for provider in providers:
                    result["provider_counts"][provider] = result["provider_counts"].get(provider, 0) + 1
                result["samples"].append(item)
                save()  # Preserve the review ledger even if subsequent SSE handling fails.
                if sample["id"] <= result["chat_subset_size"]:
                    response = await client.post(
                        f"/api/v1/reviews/{rid}/messages",
                        json={
                            "content": (
                                "Explain SYN-REVIEW in one short sentence and cite [SYN-REVIEW]."
                                if local
                                else "In one short sentence, what destination country is this report for?"
                            ),
                            "language": "en",
                        },
                        headers={"Accept": "text/event-stream"},
                    )
                    events = parse_sse(response)
                    counts = Counter(e["event"] for e in events)
                    done = next((e["data"] for e in events if e["event"] == "done"), {})
                    item["chat"] = dict(
                        events=dict(counts),
                        first_delta_ms=measurements[-1].get("delta"),
                        done_ms=measurements[-1].get("done"),
                        providers=sorted(
                            {
                                t["provider"]
                                for t in done.get("models", [])
                                if t.get("category") == "llm" and t["status"] != "failed"
                            }
                        ),
                        delta_matches_done="".join(e["data"]["text"] for e in events if e["event"] == "delta")
                        == done.get("content"),
                    )
                save()
        finally:
            await client.aclose()
            save()
    # Persist observations even if the acceptance fails; fallback is NOT model evidence.
    if local:
        item = result["samples"][0]
        assert result["probe"]["degrade_level"] == "L2"
        assert item["recognition_level"] == item["review_level"] == "L2"
        assert item["grounded_llm_fields"] > 0 and item["llm_verified"] and item["completed"]
        assert all(item["chat"]["events"].get(e, 0) > 0 for e in ("delta", "citation", "done"))
        assert item["chat"]["providers"] == ["ollama"] and item["chat"]["delta_matches_done"]
    else:
        assert len(result["samples"]) == 20
