"""Count unique (sample, cited-rule) pairs, retaining attribution but never prose."""

import re
from collections import Counter, defaultdict

SCOPE_RULE_IDS = frozenset({"SYN-REVIEW"})
SOURCES = frozenset({"rule", "llm", "llm_unverified"})


def finding_metadata(findings):
    """A value/prose-free ledger sufficient to reproduce citation-set metrics."""
    result = []
    for finding in findings:
        source = finding["determined_by"]
        if source not in SOURCES:
            raise ValueError("unsupported finding provenance")
        result.append(
            {
                "determined_by": source,
                "severity": finding["severity"],
                "category": finding.get("category", "other"),
                "field_keys": sorted(set(finding.get("field_keys", []))),
                "rule_ids": sorted(
                    {
                        c["rule_id"]
                        for c in finding.get("citations", [])
                        if re.fullmatch(r"(?:SYN|PUB)-[A-Z0-9-]+", c["rule_id"])
                    }
                ),
            }
        )
    return result


def score_findings(expected_rules, metadata):
    """Exclude scope IDs from BOTH sides; extras are not automatically false positives.

    One rule can be cited by several findings. It counts only once per sample.
    If an extra has both rule/model producers, assign it to deterministic_extra,
    preserving all producer names in the ledger, instead of double-counting it.
    """
    producers = defaultdict(set)
    for finding in metadata:
        if finding["determined_by"] not in SOURCES:
            raise ValueError("unsupported finding provenance")
        for rule in finding["rule_ids"]:
            producers[rule].add(finding["determined_by"])
    actual, expected = set(producers), set(expected_rules)
    eligible_actual, eligible_expected = actual - SCOPE_RULE_IDS, expected - SCOPE_RULE_IDS
    extra = eligible_actual - eligible_expected
    return {
        "legacy": {"hit": len(actual & expected), "extra": len(actual - expected), "miss": len(expected - actual)},
        "corrected": {
            "hit": len(eligible_actual & eligible_expected),
            "extra": len(extra),
            "miss": len(eligible_expected - eligible_actual),
        },
        "scope_counts": dict(Counter(actual & SCOPE_RULE_IDS)),
        "scope_extra_counts": dict(Counter((actual - expected) & SCOPE_RULE_IDS)),
        "model_generated_extra": dict(Counter(r for r in extra if "rule" not in producers[r])),
        "deterministic_extra": dict(Counter(r for r in extra if "rule" in producers[r])),
    }


def attribute_ledger(rows):
    """Exact offline attribution when a per-sample ledger actually exists."""
    totals = Counter()
    buckets = {name: Counter() for name in ("scope", "scope_extra", "model_generated", "deterministic_extra")}
    deterministic_samples = defaultdict(list)
    seen = set()
    for row in rows:
        sample = row["sample"]
        if sample in seen:
            raise ValueError("duplicate sample id")
        seen.add(sample)
        score = score_findings(row["expected_rule_ids"], row["finding_metadata"])
        totals.update(score["corrected"])
        for bucket, key in (
            ("scope", "scope_counts"),
            ("scope_extra", "scope_extra_counts"),
            ("model_generated", "model_generated_extra"),
            ("deterministic_extra", "deterministic_extra"),
        ):
            buckets[bucket].update(score[key])
        for rule in score["deterministic_extra"]:
            deterministic_samples[rule].append(sample)
    return {
        "corrected_counts": dict(totals),
        "bucket_counts": {k: dict(v) for k, v in buckets.items()},
        "deterministic_extra_sample_ids": dict(deterministic_samples),
    }
