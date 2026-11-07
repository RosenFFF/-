"""Bounded model-output checks reuse the deterministic engine's fired rule IDs."""

from collections import Counter

SYNTHETIC_CONDITIONS = frozenset({"SYN-REQUIRED", "SYN-HS", "SYN-AMOUNT", "SYN-RESTRICTED", "SYN-ORIGIN"})


def condition_flags(rule_findings):
    fired = {c["rule_id"] for f in rule_findings if f["determined_by"] == "rule" for c in f.get("citations", [])}
    return {rule: rule in fired for rule in sorted(SYNTHETIC_CONDITIONS)}


def filter_model_findings(findings, flags, deterministic_rule_ids):
    """No prose heuristics, new conditions or legal claims. Deterministic findings survive.

    Drop a model finding if ANY cited synthetic precondition is false/unknown.
    Then remove already-covered deterministic citations, dropping empty duplicates.
    Unknown/public rules are retained: lacking a synthetic label is not proof of FP.
    Supports metadata or actual API finding dictionaries for identical offline replay.
    """
    result, counts = [], Counter()
    for finding in findings:
        if finding["determined_by"] == "rule":
            result.append(finding)
            continue
        metadata = "rule_ids" in finding
        ids = finding["rule_ids"] if metadata else [c["rule_id"] for c in finding.get("citations", [])]
        if any(rule in SYNTHETIC_CONDITIONS and flags.get(rule) is not True for rule in ids):
            counts["unsupported_finding"] += 1
            continue
        remaining = [rule for rule in ids if rule not in deterministic_rule_ids]
        if ids and not remaining:
            counts["duplicate_finding"] += 1
            continue
        item = dict(finding)
        if metadata:
            item["rule_ids"] = remaining
        else:
            item["citations"] = [c for c in finding.get("citations", []) if c["rule_id"] in remaining]
        result.append(item)
        counts["duplicate_citations_removed"] += len(ids) - len(remaining)
    return result, dict(counts)


def grounded_summary(summary, counts):
    """Do not retain an uninspectable narrative when its findings failed grounding."""
    if counts.get("unsupported_finding"):
        return "模型中缺乏确定性证据的结论已过滤；请结合保留结果人工复核。"
    return summary
