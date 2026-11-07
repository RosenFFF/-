"""Summary/prompt policy tests are entirely offline."""

import pytest

from app.services.model_findings import filter_model_findings, grounded_summary, summary_needs_rebuild


@pytest.mark.parametrize(
    "rule,keyword",
    [
        ("SYN-ORIGIN", "Origin_country"),
        ("SYN-AMOUNT", "金额"),
        ("SYN-HS", "HS编码"),
        ("SYN-REQUIRED", "missing"),
        ("SYN-RESTRICTED", "禁限"),
    ],
)
def test_dropped_rule_keyword_triggers_only_relevant_rebuild(rule, keyword):
    counts = {"unsupported_finding": 2}
    assert summary_needs_rebuild(keyword, counts, {rule})
    assert summary_needs_rebuild(rule.lower(), counts, {rule})
    assert not summary_needs_rebuild("Human review recommended.", counts, {rule})
    assert not summary_needs_rebuild(keyword, {}, {rule})


def test_summary_keeps_unrelated_original_text_even_with_filtered_findings():
    text = "Human review recommended."
    assert grounded_summary(text, {"unsupported_finding": 2}, [], {"SYN-ORIGIN"}) == text
    assert not summary_needs_rebuild("Twelve months", {"unsupported_finding": 1}, {"SYN-HS"})
    assert not summary_needs_rebuild("Original paperwork", {"unsupported_finding": 1}, {"SYN-ORIGIN"})
    assert grounded_summary(text, {"duplicate_finding": 1}, [], {"SYN-REQUIRED"}) == text


def test_summary_rebuild_is_retained_fact_counts_not_generic_or_dropped_claims():
    retained = [
        {"determined_by": "rule", "severity": "high", "category": "valuation", "rule_ids": ["SYN-AMOUNT"]},
        {"determined_by": "rule", "severity": "info", "category": "other", "rule_ids": ["SYN-REVIEW"]},
        {"determined_by": "llm", "severity": "low", "category": "other", "rule_ids": ["PUB-US-INVOICE"]},
    ]
    text = grounded_summary("Origin concern", {"unsupported_finding": 3}, retained, {"SYN-ORIGIN"})
    assert "风险等级：high" in text
    assert "high=1, medium=0, low=1, info=1" in text
    assert "other=2, valuation=1" in text
    assert "PUB-US-INVOICE, SYN-AMOUNT, SYN-REVIEW" in text
    assert text.endswith("已过滤 3 条无依据结论")
    assert "SYN-ORIGIN" not in text and "Origin concern" not in text
    assert text == grounded_summary("SYN-ORIGIN", {"unsupported_finding": 3}, list(reversed(retained)), {"SYN-ORIGIN"})


def test_dropped_ids_recorded_without_changing_model_output_filter_counts():
    ids = set()
    data = [{"determined_by": "llm", "rule_ids": ["SYN-ORIGIN", "PUB-US-INVOICE"]}]
    kept, counts = filter_model_findings(data, {"SYN-ORIGIN": False}, set(), dropped_rule_ids=ids)
    assert kept == [] and ids == {"SYN-ORIGIN", "PUB-US-INVOICE"}
    assert counts == {"unsupported_finding": 1}


def test_review_prompt_explicitly_states_all_five_predicates_and_single_document_ban():
    from app.services.review_prompt import SYNTHETIC_REVIEW_PRECONDITIONS

    for rule in ("SYN-REQUIRED", "SYN-HS", "SYN-AMOUNT", "SYN-RESTRICTED", "SYN-ORIGIN"):
        assert rule in SYNTHETIC_REVIEW_PRECONDITIONS
    assert "Single-document reviews MUST NEVER cite SYN-ORIGIN" in SYNTHETIC_REVIEW_PRECONDITIONS
    assert ">1 distinct non-empty origin_country" in SYNTHETIC_REVIEW_PRECONDITIONS
    assert "of the SAME review" in SYNTHETIC_REVIEW_PRECONDITIONS
    assert "0.01" in SYNTHETIC_REVIEW_PRECONDITIONS
    assert "DEMO-RESTRICTED" in SYNTHETIC_REVIEW_PRECONDITIONS


def test_saved_five_same_subset_no_new_misses_and_actual_report_agrees():
    from pathlib import Path

    from eval.compare_prompt_five import compare, load

    evidence = Path(__file__).resolve().parents[2] / "reports" / "evidence"
    result = compare(
        load(evidence / "backend-eval-model-fp" / "live"),
        load(evidence / "backend-review-summary-prompt" / "live-five"),
    )
    assert result["paired_sample_ids"] == [1, 9, 12, 15, 18]
    assert result["previous_same_subset"]["before"]["corrected_counts"] == {"hit": 4, "extra": 22, "miss": 0}
    assert result["current_same_subset"]["before"]["corrected_counts"] == {"hit": 4, "extra": 5, "miss": 0}
    assert result["actual_post_filter_counts"] == {"hit": 4, "extra": 4, "miss": 0}
    assert result["current_same_subset"]["genuine_model_fp_sample_ids_before"] == {"SYN-ORIGIN": [12]}
    assert result["current_same_subset"]["genuine_model_fp_sample_ids_after"] == {}
    assert (result["current_summary_kept"], result["current_summary_rebuilt"]) == (4, 1)
    assert result["offline_model_calls"] == 0


def test_comparison_handles_no_completed_samples_without_retry():
    from eval.compare_prompt_five import compare

    result = compare([], [{"sample": 1, "review_completed": False}])
    assert result["current_samples_captured"] == 1
    assert result["current_complete"] == 0
    assert result["actual_post_filter_counts"] == {"hit": 0, "extra": 0, "miss": 0}


def test_comparison_refuses_missing_historical_pair():
    from eval.compare_prompt_five import compare

    with pytest.raises(ValueError, match="historical ledger"):
        compare([], [{"sample": 1, "review_completed": True, "model_output_captured": True}])
