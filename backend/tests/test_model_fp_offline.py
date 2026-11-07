"""No network: output predicates, ledger replay and strict paid-request budget."""

import json

import httpx
import pytest

from app.services.model_findings import condition_flags, filter_model_findings
from app.services.rules_engine import check
from eval.finding_metrics import finding_metadata, score_findings
from eval.live_capture import MODEL_TASK, CountedModelTransport
from eval.synthetic import samples


async def test_model_budget_and_counter_are_persisted_without_body(tmp_path):
    transport = CountedModelTransport(budget=2, counter_path=tmp_path / "calls.json")
    await transport.inner.aclose()
    seen = []

    def handle(request):
        seen.append(request.method)
        return httpx.Response(200, json={"not_saved": "response prose"})

    transport.inner = httpx.MockTransport(handle)
    token = MODEL_TASK.set("field_extraction")
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            for _ in range(2):
                await client.post("https://api.deepseek.com/v1/chat/completions", json={"not_saved": "prompt prose"})
            with pytest.raises(RuntimeError, match="budget"):
                await client.post("https://api.deepseek.com/v1/chat/completions")
    finally:
        MODEL_TASK.reset(token)
        await transport.finish()
    saved = json.loads((tmp_path / "calls.json").read_text())
    assert saved == {"model_http_calls_by_task": {"field_extraction": 2}, "model_http_status_counts": {"200": 2}}
    assert seen == ["POST", "POST"]
    assert "prose" not in (tmp_path / "calls.json").read_text()


class Cite:
    @staticmethod
    def citation(rule):
        return {"rule_id": rule}


def doc(fields):
    return {
        "doc_type": "commercial_invoice",
        "fields": [{"key": k, "value": v} for k, v in fields.items() if v is not None],
    }


def model(rule_ids):
    return {"determined_by": "llm", "rule_ids": rule_ids, "severity": "medium", "category": "other", "field_keys": []}


@pytest.mark.parametrize(
    "rule,changes",
    [
        ("SYN-REQUIRED", {"origin_country": None}),
        ("SYN-HS", {"hs_code": "12345"}),
        ("SYN-AMOUNT", {"quantity": "2"}),
        ("SYN-RESTRICTED", {"goods_description": "DEMO-RESTRICTED"}),
    ],
)
def test_each_synthetic_precondition(rule, changes):
    clean = samples()[0]["fields"]
    assert not condition_flags(check([doc(clean)], Cite()))[rule]
    changed = {**clean, **changes}
    assert condition_flags(check([doc(changed)], Cite()))[rule]
    original = model([rule])
    kept, stats = filter_model_findings([original], {rule: True}, set())
    assert kept == [original] and not stats.get("unsupported_finding")
    dropped, stats = filter_model_findings([original], {rule: False}, set())
    assert dropped == [] and stats["unsupported_finding"] == 1


def test_origin_precondition_needs_multiple_distinct_origins():
    clean = samples()[0]["fields"]
    one = [doc(clean)]
    same = [doc(clean), doc(clean)]
    different = [doc(clean), doc({**clean, "origin_country": "VN"})]
    assert not condition_flags(check(one, Cite()))["SYN-ORIGIN"]
    assert not condition_flags(check(same, Cite()))["SYN-ORIGIN"]
    flags = condition_flags(check(different, Cite()))
    assert flags["SYN-ORIGIN"]
    assert filter_model_findings([model(["SYN-ORIGIN"])], flags, set())[0]
    assert not filter_model_findings([model(["SYN-ORIGIN"])], {}, set())[0]


def test_amount_invalid_values_and_tolerance_follow_existing_rule_engine():
    clean = samples()[0]["fields"]
    for amount in ("NaN", "-1", "Infinity", "bad"):
        assert condition_flags(check([doc({**clean, "total_amount": amount})], Cite()))["SYN-AMOUNT"]
    assert not condition_flags(check([doc({**clean, "total_amount": "101.01"})], Cite()))["SYN-AMOUNT"]
    assert condition_flags(check([doc({**clean, "total_amount": "101.02"})], Cite()))["SYN-AMOUNT"]


def test_dedup_preserves_rules_and_retains_unadjudicated_public_guidance():
    rule = {"determined_by": "rule", "rule_ids": ["SYN-HS"], "severity": "medium"}
    items = [rule, model(["SYN-HS"]), model(["SYN-HS", "PUB-WCO-HS"])]
    result, stats = filter_model_findings(items, {"SYN-HS": True}, {"SYN-HS"})
    assert result[0] is rule
    assert result[1]["rule_ids"] == ["PUB-WCO-HS"]
    assert stats["duplicate_finding"] == 1
    assert items[2]["rule_ids"] == ["SYN-HS", "PUB-WCO-HS"]  # input immutable
    assert filter_model_findings([rule], {}, set())[0] == [rule]
    assert filter_model_findings([model(["SYN-HS", "PUB-WCO-HS"])], {}, set())[0] == []


def test_all_twenty_gold_cases_create_no_new_misses_even_if_models_hallucinate():
    for sample in samples():
        deterministic = check([doc(sample["fields"])], Cite())
        metadata = finding_metadata(deterministic)
        all_model = [model([rule]) for rule in ("SYN-REQUIRED", "SYN-HS", "SYN-AMOUNT", "SYN-RESTRICTED", "SYN-ORIGIN")]
        before = metadata + all_model
        after, _ = filter_model_findings(
            before, condition_flags(deterministic), {r for f in metadata for r in f["rule_ids"]}
        )
        assert score_findings(sample["expected_rules"], before)["corrected"]["miss"] == 0
        assert score_findings(sample["expected_rules"], after)["corrected"] == {
            "hit": len(set(sample["expected_rules"]) - {"SYN-REVIEW"}),
            "extra": 0,
            "miss": 0,
        }
        assert all(f in after for f in metadata)


def test_real_shape_filter_matches_metadata_replay():
    full = {
        "determined_by": "llm",
        "severity": "medium",
        "category": "other",
        "field_keys": [],
        "citations": [{"rule_id": "SYN-HS"}, {"rule_id": "PUB-WCO-HS"}],
        "message": "not persisted",
    }
    flags = {"SYN-HS": True}
    actual, stats = filter_model_findings([full], flags, {"SYN-HS"})
    replay, replay_stats = filter_model_findings(finding_metadata([full]), flags, {"SYN-HS"})
    assert finding_metadata(actual) == replay and stats == replay_stats


def test_unfounded_model_summary_is_replaced_not_republished():
    from app.services.model_findings import grounded_summary

    original = "synthetic unverified narrative"
    assert grounded_summary(original, {"unsupported_finding": 1}) != original
    assert grounded_summary(original, {"duplicate_finding": 1}) == original


def test_persisted_real_ledger_replays_without_new_model_calls_or_misses():
    from pathlib import Path

    from eval.replay_model_fp import replay

    root = Path(__file__).resolve().parents[2] / "reports/evidence/backend-eval-model-fp/live"
    rows = [json.loads(p.read_text()) for p in sorted(root.glob("sample-*.json"))]
    result = replay(rows)
    assert result["samples_complete_with_model_output"] == 20
    assert result["before"]["corrected_counts"] == dict(hit=12, extra=81, miss=0)
    assert result["after"]["corrected_counts"] == dict(hit=12, extra=25, miss=0)
    assert result["genuine_model_fp_sample_ids_after"] == {}
    assert result["deterministic_fp_sample_ids"] == {}
    assert result["offline_model_calls"] == 0
