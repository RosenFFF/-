"""Bounded model-output checks reuse the deterministic engine's fired rule IDs."""

import re
from collections import Counter

from app.services.rules_engine import risk_level

SYNTHETIC_CONDITIONS = frozenset({"SYN-REQUIRED", "SYN-HS", "SYN-AMOUNT", "SYN-RESTRICTED", "SYN-ORIGIN"})


def condition_flags(rule_findings):
    fired = {c["rule_id"] for f in rule_findings if f["determined_by"] == "rule" for c in f.get("citations", [])}
    return {rule: rule in fired for rule in sorted(SYNTHETIC_CONDITIONS)}


def filter_model_findings(findings, flags, deterministic_rule_ids, *, dropped_rule_ids=None):
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
            if dropped_rule_ids is not None:
                dropped_rule_ids.update(ids)
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


SUMMARY_KEYWORDS = {
    "SYN-ORIGIN": ("原产国", "原产地", "origin"),
    "SYN-AMOUNT": ("金额", "总额", "amount"),
    "SYN-HS": ("hs", "海关编码", "税则"),
    "SYN-REQUIRED": ("缺失", "缺少", "missing", "required"),
    "SYN-RESTRICTED": ("禁限", "禁运", "restricted", "embargo"),
}


def summary_needs_rebuild(summary, counts, dropped_rule_ids):
    if not counts.get("unsupported_finding"):
        return False
    text = summary.casefold()
    for rule in dropped_rule_ids:
        if rule.casefold() in text:
            return True
        for keyword in SUMMARY_KEYWORDS.get(rule, ()):
            if keyword.isascii():
                # Match HS编码/origin_country, but not incidental English substrings (months).
                if re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text):
                    return True
            elif keyword in text:
                return True
    return False


def grounded_summary(summary, counts, retained_findings=(), dropped_rule_ids=()):
    """Keep unrelated model text; rebuild affected summaries from retained facts only."""
    if not summary_needs_rebuild(summary, counts, dropped_rule_ids):
        return summary
    severity = Counter(f["severity"] for f in retained_findings)
    categories = Counter(f.get("category", "other") for f in retained_findings)
    rules = sorted(
        {
            r
            for f in retained_findings
            for r in (f["rule_ids"] if "rule_ids" in f else [c["rule_id"] for c in f.get("citations", [])])
        }
    )
    return (
        f"风险等级：{risk_level(retained_findings)}；"
        + "严重性计数："
        + ", ".join(f"{k}={severity[k]}" for k in ("high", "medium", "low", "info"))
        + "；分类计数："
        + (", ".join(f"{k}={v}" for k, v in sorted(categories.items())) or "none")
        + "；保留规则："
        + (", ".join(rules) or "none")
        + f"\n已过滤 {counts['unsupported_finding']} 条无依据结论"
    )
