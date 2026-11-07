"""Offline same-subset comparison; never recover missing historical summary text."""

import argparse
import json
from collections import Counter
from pathlib import Path

from eval.finding_metrics import score_findings
from eval.live_capture import atomic_json
from eval.replay_model_fp import replay

SAMPLE_IDS = (1, 9, 12, 15, 18)


def compare(previous, current):
    old = [row for row in previous if row["sample"] in SAMPLE_IDS]
    new = [row for row in current if row["sample"] in SAMPLE_IDS]
    completed = [r for r in new if r.get("review_completed") and r.get("model_output_captured")]
    paired_ids = sorted(r["sample"] for r in completed)
    paired_old = [r for r in old if r["sample"] in paired_ids]
    if {r["sample"] for r in paired_old} != set(paired_ids):
        raise ValueError("historical ledger lacks a completed comparison sample")
    previous_replay, current_replay = replay(paired_old), replay(completed)
    actual_post = Counter(hit=0, extra=0, miss=0)
    for row in completed:
        score = score_findings(row["expected_rule_ids"], row["post_filter_metadata"])["corrected"]
        actual_post.update(score)
    if actual_post != Counter(current_replay["after"]["corrected_counts"]):
        raise ValueError("live post-filter metadata differs from offline replay")
    return {
        "planned_sample_ids": list(SAMPLE_IDS),
        "paired_sample_ids": paired_ids,
        "previous_subset_available": len(old),
        "current_samples_captured": len(new),
        "current_complete": len(completed),
        "previous_same_subset": previous_replay,
        "current_same_subset": current_replay,
        "actual_post_filter_counts": dict(actual_post),
        "current_summary_kept": sum(r.get("summary_rebuilt") is False for r in completed),
        "current_summary_rebuilt": sum(r.get("summary_rebuilt") is True for r in completed),
        "current_summary_unknown": sum("summary_rebuilt" not in r for r in completed),
        "historical_summary_text_available": False,
        "offline_model_calls": 0,
    }


def load(root):
    return [json.loads(p.read_text()) for p in sorted(root.glob("sample-*.json"))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(load(args.previous), load(args.current))
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "paired_sample_ids": result["paired_sample_ids"],
                "post_filter_counts": result["actual_post_filter_counts"],
                "summary_kept": result["current_summary_kept"],
                "summary_rebuilt": result["current_summary_rebuilt"],
            }
        )
    )


if __name__ == "__main__":
    main()
