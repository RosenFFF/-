"""Offline metric and evidence-retention regressions; no provider requests."""

import json
from pathlib import Path

import pytest

from eval.audit_extra_hits import audit_aggregate, label_oracle
from eval.finding_metrics import finding_metadata, score_findings


def test_scope_exclusion_and_producer_overlap():
    metadata = [
        {"determined_by": "rule", "rule_ids": ["SYN-REVIEW", "SYN-HS"]},
        {"determined_by": "llm", "rule_ids": ["SYN-REVIEW", "SYN-HS", "PUB-WCO-HS"]},
        {"determined_by": "llm_unverified", "rule_ids": ["PUB-WCO-HS"]},
    ]
    score = score_findings(["SYN-REVIEW", "SYN-REQUIRED"], metadata)
    assert score["legacy"] == dict(hit=1, extra=2, miss=1)
    assert score["corrected"] == dict(hit=0, extra=2, miss=1)
    assert score["scope_counts"] == {"SYN-REVIEW": 1}
    assert score["model_generated_extra"] == {"PUB-WCO-HS": 1}
    assert score["deterministic_extra"] == {"SYN-HS": 1}
    assert sum(score[k].get("SYN-HS", 0) for k in ("model_generated_extra", "deterministic_extra")) == 1


def test_metadata_excludes_document_and_model_prose():
    finding = dict(
        determined_by="llm",
        severity="info",
        field_keys=["hs_code"],
        citations=[{"rule_id": "SYN-HS"}],
        title="private prose",
        message="private values",
        document_id="not-a-synthetic-sample-id",
    )
    result = finding_metadata([finding])
    assert set(result[0]) == {"determined_by", "severity", "category", "field_keys", "rule_ids"}
    assert "private" not in json.dumps(result)
    assert score_findings(["SYN-HS"], result)["corrected"] == dict(hit=1, extra=0, miss=0)


def test_original_aggregate_correction_cannot_identify_buckets():
    root = Path(__file__).resolve().parents[2]
    metrics = json.loads((root / "reports/evidence/backend-eval-ollama/deepseek-one-round.json").read_text())
    report = audit_aggregate(metrics)
    assert report["legacy_counts"] == dict(hit=32, extra=89, miss=0)
    assert report["corrected_counts"] == dict(hit=12, extra=89, miss=0)
    assert report["excluded_scope_pair_counts"] == {"SYN-REVIEW": 20}
    assert report["scope_extra_counts"] == {"SYN-REVIEW": 0}
    assert report["unattributed_extra_pairs"] == 89
    assert report["observed_model_generated_extra_pairs"] is None
    assert report["observed_deterministic_extra_pairs"] is None
    assert report["bounds_not_observations"]["model_only_extra_lower"] == 70
    assert report["bounds_not_observations"]["deterministic_extra_upper"] == 19
    metrics["finding_counts"]["miss"] = 1
    with pytest.raises(ValueError, match="not identifiable"):
        audit_aggregate(metrics)


def test_gold_labels_match_rules_without_reconstructing_original_run():
    oracle = label_oracle()
    assert oracle["matches"] == oracle["total"] == 20
    assert not oracle["original_run_reconstruction"]


def test_unknown_finding_provenance_fails_closed():
    with pytest.raises(ValueError, match="provenance"):
        score_findings([], [{"determined_by": "unknown", "rule_ids": []}])


def test_exact_ledger_attribution_retains_synthetic_ids_only():
    from eval.finding_metrics import attribute_ledger

    row = {
        "sample": 7,
        "expected_rule_ids": ["SYN-REVIEW"],
        "finding_metadata": [
            {"determined_by": "rule", "rule_ids": ["SYN-REVIEW", "SYN-REQUIRED"]},
            {"determined_by": "llm", "rule_ids": ["PUB-CN-ORIGIN"]},
        ],
    }
    result = attribute_ledger([row])
    assert result["corrected_counts"] == dict(hit=0, extra=2, miss=0)
    assert result["bucket_counts"]["scope"] == {"SYN-REVIEW": 1}
    assert result["bucket_counts"]["model_generated"] == {"PUB-CN-ORIGIN": 1}
    assert result["bucket_counts"]["deterministic_extra"] == {"SYN-REQUIRED": 1}
    assert result["deterministic_extra_sample_ids"] == {"SYN-REQUIRED": [7]}
    with pytest.raises(ValueError, match="duplicate"):
        attribute_ledger([row, row])
