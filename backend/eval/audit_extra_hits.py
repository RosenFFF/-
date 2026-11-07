"""Offline aggregate audit. Never infer a per-finding ledger from aggregate totals."""

import argparse
import json
from collections import Counter
from pathlib import Path

from eval.finding_metrics import SCOPE_RULE_IDS
from eval.synthetic import samples


def audit_aggregate(metrics):
    labels = samples()
    original = metrics["finding_counts"]
    expected_total = sum(len(set(s["expected_rules"])) for s in labels)
    if len(metrics["samples"]) != len(labels) or original["miss"] != 0 or original["hit"] != expected_total:
        raise ValueError("scope hit count is not identifiable from this aggregate")
    scope = Counter(r for s in labels for r in set(s["expected_rules"]) & SCOPE_RULE_IDS)
    extra = original["false_positive"]
    # Perfect scores establish these rule inputs; otherwise bounds below are invalid.
    for key in ("total_amount", "currency", "hs_code", "origin_country", "quantity", "unit_price"):
        counts = metrics["field_counts"][key]
        if counts != {"correct": 20, "total": 20}:
            raise ValueError("historical input-based bound is not established")
    required_max = 20 - metrics["field_counts"]["invoice_no"]["correct"]
    restricted_max = 20 - metrics["field_counts"]["goods_description"]["correct"]
    return {
        "paid_model_calls": 0,
        "legacy_counts": {"hit": original["hit"], "extra": extra, "miss": original["miss"]},
        "corrected_counts": {"hit": original["hit"] - sum(scope.values()), "extra": extra, "miss": 0},
        "excluded_scope_pair_counts": dict(scope),
        "scope_extra_counts": {r: 0 for r in scope},
        "historical_ledger_available": False,
        "unattributed_extra_pairs": extra,
        "observed_model_generated_extra_pairs": None,
        "observed_deterministic_extra_pairs": None,
        "bounds_not_observations": {
            "deterministic_extra_upper_by_rule": {
                "SYN-REVIEW": 0,
                "SYN-HS": 0,
                "SYN-AMOUNT": 0,
                "SYN-ORIGIN": 0,
                "SYN-REQUIRED": required_max,
                "SYN-RESTRICTED": restricted_max,
                **{
                    r: 0
                    for r in ("PUB-CN-ORIGIN", "PUB-WCO-HS", "PUB-US-INVOICE", "PUB-CN-DUALUSE", "PUB-CN-DECLARATION")
                },
            },
            "deterministic_extra_lower": 0,
            "deterministic_extra_upper": required_max + restricted_max,
            "model_only_extra_lower": max(0, extra - required_max - restricted_max),
            "model_only_extra_upper": extra,
        },
        "actual_false_positive_sample_ids": None,
    }


def label_oracle():
    """Validate labels with deterministic rules on GOLD fields, NOT original extraction."""
    from app.services.rules_engine import check

    class Citations:
        @staticmethod
        def citation(rule):
            return {"rule_id": rule}

    checked = []
    for sample in samples():
        document = {
            "doc_type": "commercial_invoice",
            "fields": [{"key": key, "value": value} for key, value in sample["fields"].items() if value is not None],
        }
        actual = {c["rule_id"] for f in check([document], Citations()) for c in f["citations"]}
        checked.append({"sample": sample["id"], "label_match": actual == set(sample["expected_rules"])})
    return {
        "gold_label_checks": checked,
        "matches": sum(x["label_match"] for x in checked),
        "total": len(checked),
        "original_run_reconstruction": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_aggregate(json.loads(args.input.read_text()))
    report["label_oracle"] = label_oracle()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["corrected_counts"]))


if __name__ == "__main__":
    main()
