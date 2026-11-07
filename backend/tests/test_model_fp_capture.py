"""Explicit opt-in no-chat captures; persist provenance before post-processing."""

import os
import time
from pathlib import Path

import pytest

from app.main import create_app
from app.services import review
from app.services.model_findings import condition_flags, summary_needs_rebuild
from eval.finding_metrics import finding_metadata
from eval.live_capture import MODEL_TASK, CountedModelTransport, atomic_json, balance_in_memory
from eval.synthetic import samples

from .conftest import Api, _seed, make_settings
from .samples import invoice_image
from .test_documents import _upload


async def capture_no_chat(tmp_path, postgres_rls_db, live_redis, monkeypatch, *, sample_ids=None):
    out = Path(os.environ["MODEL_FP_EVIDENCE_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    if list(out.glob("sample-*.json")):
        raise RuntimeError("capture directory already contains samples; refusing rerun")
    key = os.environ["DEEPSEEK_API_KEY"]
    settings = make_settings(
        tmp_path,
        database_url=postgres_rls_db.engine.url.render_as_string(hide_password=False),
        demo_mode=False,
        llm_provider_chain=["deepseek"],
        deepseek_api_key=key,
        qwen_api_key=None,
        llm_timeout_s=120,
        llm_max_retries=0,
        llm_circuit_failures=100,
    )
    app = create_app(settings, redis=live_redis[0])
    dataset = [s for s in samples() if sample_ids is None or s["id"] in sample_ids]
    transport = CountedModelTransport(budget=2 * len(dataset), counter_path=out / "model-call-counts.json")
    current = {}
    original_check, original_validate = review.check, review.validate_citations
    original_summary = review.grounded_summary

    def persist():
        atomic_json(out / f"sample-{current['sample']:02d}.json", current)

    def check(documents, rag):
        findings = original_check(documents, rag)
        current["condition_flags"] = condition_flags(findings)
        current["finding_metadata"] = finding_metadata(findings)
        current["deterministic_rule_ids"] = sorted({c["rule_id"] for f in findings for c in f["citations"]})
        persist()  # Actual extracted-field predicates, BEFORE the review model call.
        return findings

    def validate(output, citations):
        generated, dropped = original_validate(output, citations)
        current["finding_metadata"].extend(finding_metadata(generated))
        current["model_output_captured"] = True
        persist()  # Before review persistence/HTTP response/any metric computation can fail.
        return generated, dropped

    def summary(text, counts, retained_findings=(), dropped_rule_ids=(), *, language="zh-CN"):
        current["summary_rebuilt"] = summary_needs_rebuild(text, counts, dropped_rule_ids)
        current["summary_text_persisted"] = False
        current["dropped_rule_ids"] = sorted(dropped_rule_ids)
        persist()
        return original_summary(text, counts, retained_findings, dropped_rule_ids, language=language)

    monkeypatch.setattr(review, "grounded_summary", summary)
    monkeypatch.setattr(review, "check", check)
    monkeypatch.setattr(review, "validate_citations", validate)
    accounting = {"model_http_calls": 0, "balance_http_calls": 0, "chat_http_calls": 0}
    async with app.router.lifespan_context(app):
        await _seed(app)
        client = await Api(app, settings).login("reviewer")
        llm = app.state.ai.llm
        llm.transport = transport
        original_json = llm.chat_json

        async def counted(messages, schema, *, task):
            token = MODEL_TASK.set(task)
            try:
                return await original_json(messages, schema, task=task)
            finally:
                MODEL_TASK.reset(token)

        llm.chat_json = counted
        accounting["balance_http_calls"] += 1
        before = await balance_in_memory(key)
        try:
            for sample in dataset:
                current.clear()
                current.update(
                    sample=sample["id"],
                    expected_rule_ids=sample["expected_rules"],
                    field_mismatch_keys=[],
                    finding_metadata=[],
                    review_completed=False,
                    model_output_captured=False,
                )
                persist()
                started = time.perf_counter()
                uploaded = await _upload(client, invoice_image(lines=sample["lines"]))
                if uploaded.status_code != 202:
                    raise RuntimeError("upload failed; details withheld")
                doc = uploaded.json()["id"]
                recognition = (await client.get(f"/api/v1/documents/{doc}/recognition")).json()
                actual = {f["key"]: f["value"] for f in recognition["fields"]}
                current["field_mismatch_keys"] = [k for k, value in sample["fields"].items() if actual.get(k) != value]
                current["recognition_level"] = recognition["degrade_level"]
                current["upload_extraction_ms"] = round((time.perf_counter() - started) * 1000)
                persist()
                created = await client.post(
                    "/api/v1/reviews", json={"document_ids": [doc], "destination_country": "VN"}
                )
                if created.status_code != 202:
                    raise RuntimeError("review create failed; captured ledger retained")
                rid = created.json()["id"]
                report = (await client.get(f"/api/v1/reviews/{rid}")).json()
                current["post_filter_metadata"] = finding_metadata(report["findings"])
                current["model_output_filter"] = report["security"].get("model_output_filter", {})
                current["review_completed"] = report["status"] == "completed"
                current["review_level"] = report["degrade_level"]
                current["llm_verified"] = report["llm_verified"]
                current["upload_review_ms"] = round((time.perf_counter() - started) * 1000)
                current["traces"] = [
                    {k: t.get(k) for k in ("provider", "task", "status", "latency_ms")}
                    for t in report["models"]
                    if t["category"] == "llm"
                ]
                persist()
        finally:
            accounting["balance_http_calls"] += 1
            try:
                after = await balance_in_memory(key)
                accounting["consumed_amount_by_currency"] = {c: str(before[c] - after[c]) for c in before}
                accounting["consumption_measured"] = True
            except RuntimeError:
                accounting["consumption_measured"] = False
            # Never serialize the balance dictionaries, response objects or key.
            accounting["model_http_calls"] = sum(transport.calls.values())
            accounting["model_http_calls_by_task"] = dict(transport.calls)
            accounting["model_http_status_counts"] = dict(transport.statuses)
            atomic_json(out / "accounting.json", accounting)
            await transport.finish()
            await client.aclose()
    assert len(list(out.glob("sample-*.json"))) == len(dataset)


@pytest.mark.skipif(os.environ.get("RUN_MODEL_FP_E2E") != "1", reason="one explicitly approved paid run only")
async def test_capture_once_no_chat(tmp_path, postgres_rls_db, live_redis, monkeypatch):
    await capture_no_chat(tmp_path, postgres_rls_db, live_redis, monkeypatch)
