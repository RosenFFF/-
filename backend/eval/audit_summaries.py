"""Count identifiable summary decisions without inventing absent historical prose."""

import argparse
import json
from pathlib import Path

from app.services.model_findings import filter_model_findings
from eval.live_capture import atomic_json


def audit(rows):
    kept, unknown, details = [], [], []
    for row in rows:
        dropped = set()
        retained, counts = filter_model_findings(
            row["finding_metadata"],
            row["condition_flags"],
            set(row["deterministic_rule_ids"]),
            dropped_rule_ids=dropped,
        )
        if not counts.get("unsupported_finding"):
            kept.append(row["sample"])
        else:
            unknown.append(row["sample"])
        details.append(
            {
                "sample": row["sample"],
                "dropped_rule_ids": sorted(dropped),
                "unsupported_finding_count": counts.get("unsupported_finding", 0),
                "retained_finding_count": len(retained),
            }
        )
    return {
        "samples": len(rows),
        "summary_text_absent": len(rows),
        "known_kept": len(kept),
        "known_rebuilt": 0,
        "decision_unknown": len(unknown),
        "known_kept_sample_ids": kept,
        "unknown_sample_ids": unknown,
        "model_calls": 0,
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit([json.loads(p.read_text()) for p in sorted(args.capture.glob("sample-*.json"))])
    atomic_json(args.output, result)
    print(json.dumps({k: result[k] for k in ("samples", "known_kept", "known_rebuilt", "decision_unknown")}))


if __name__ == "__main__":
    main()
