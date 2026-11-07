"""Offline replay only: no HTTP/model requests; use the production output filter."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from app.services.model_findings import SYNTHETIC_CONDITIONS, filter_model_findings
from eval.finding_metrics import SCOPE_RULE_IDS, attribute_ledger, score_findings
from eval.live_capture import atomic_json


def replay(rows):
    completed = [r for r in rows if r.get("review_completed") and r.get("model_output_captured")]
    after_rows, extra_before, extra_after = [], Counter(), Counter()
    genuine_before, genuine_after, deterministic_fp = defaultdict(list), defaultdict(list), defaultdict(list)
    stats = Counter()
    extra_samples_before, extra_samples_after = defaultdict(list), defaultdict(list)
    predicates = {}
    for row in completed:
        expected = set(row["expected_rule_ids"]) - SCOPE_RULE_IDS
        before = row["finding_metadata"]
        filtered, counts = filter_model_findings(before, row["condition_flags"], set(row["deterministic_rule_ids"]))
        stats.update(counts)
        after_rows.append({**row, "finding_metadata": filtered})
        predicates[row["sample"]] = row["condition_flags"]
        for metadata, extras, genuine in (
            (before, extra_before, genuine_before),
            (filtered, extra_after, genuine_after),
        ):
            actual = {rule for f in metadata for rule in f["rule_ids"]} - SCOPE_RULE_IDS
            extras.update(actual - expected)
            index = extra_samples_before if metadata is before else extra_samples_after
            for rule in actual - expected:
                index[rule].append(row["sample"])
            for rule in actual - expected:
                producers = {f["determined_by"] for f in metadata if rule in f["rule_ids"]}
                if "rule" in producers:
                    if metadata is before:
                        deterministic_fp[rule].append(row["sample"])
                elif rule in SYNTHETIC_CONDITIONS and row["condition_flags"].get(rule) is not True:
                    genuine[rule].append(row["sample"])
        old = score_findings(row["expected_rule_ids"], before)["corrected"]
        new = score_findings(row["expected_rule_ids"], filtered)["corrected"]
        if new["miss"] > old["miss"]:
            raise ValueError("offline replay introduced a miss; do not claim success")
        # Deterministic findings must survive exactly, even if false/unknown flags supplied.
        if not all(f in filtered for f in before if f["determined_by"] == "rule"):
            raise ValueError("deterministic finding removed")
    return {
        "samples_captured": len(rows),
        "samples_complete_with_model_output": len(completed),
        "partial_samples": [r["sample"] for r in rows if r not in completed],
        "before": attribute_ledger(completed),
        "after": attribute_ledger(after_rows),
        "extra_pairs_before_by_rule": dict(extra_before),
        "extra_pairs_after_by_rule": dict(extra_after),
        "genuine_model_fp_sample_ids_before": dict(genuine_before),
        "genuine_model_fp_sample_ids_after": dict(genuine_after),
        "deterministic_fp_sample_ids": dict(deterministic_fp),
        "extra_sample_ids_before_by_rule": dict(extra_samples_before),
        "extra_sample_ids_after_by_rule": dict(extra_samples_after),
        "removed_extra_sample_ids_by_rule": {
            rule: sorted(set(ids) - set(extra_samples_after.get(rule, [])))
            for rule, ids in extra_samples_before.items()
        },
        "filter_object_counts": dict(stats),
        "offline_model_calls": 0,
        "scope_rule_ids_excluded": sorted(SCOPE_RULE_IDS),
        "per_sample_conditions": predicates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(p.read_text()) for p in sorted(args.capture.glob("sample-*.json"))]
    result = replay(rows)
    atomic_json(args.output, result)
    print(json.dumps({"before": result["before"]["corrected_counts"], "after": result["after"]["corrected_counts"]}))


if __name__ == "__main__":
    main()
