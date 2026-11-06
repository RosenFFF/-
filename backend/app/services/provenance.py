"""Conservative provenance labels: a reachable source never certifies a trade decision."""

from urllib.parse import urlparse

COMPLIANCE_DISCLAIMER = "自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。"
CORPUS_LABELS = {
    "synthetic": "合成或未核验语料（非真实合规结论）",
    "mixed": "混合语料（含合成或未核验规则，非真实合规结论）",
    "public_verified": "公开出处已核验（适用范围与时效仍须人工复核）",
}


def is_public(rule: dict) -> bool:
    """Only curated metadata qualifies; an HTTPS URL alone is not verification."""
    return (
        rule.get("corpus") == "public_verified"
        and bool(rule.get("verified_at"))
        and urlparse(rule.get("url") or "").scheme in {"http", "https"}
        and bool(urlparse(rule.get("url") or "").hostname)
        and not str(rule.get("rule_id", rule.get("id", ""))).startswith("SYN-")
        and "SYNTHETIC" not in rule.get("jurisdiction", "").upper()
        and "合成" not in rule.get("source", "")
    )


def corpus_of(rules: list[dict]) -> str:
    kinds = {is_public(rule) for rule in rules}
    if kinds == {True}:
        return "public_verified"
    return "mixed" if kinds == {True, False} else "synthetic"


def provenance(rules: list[dict], retrieval_mode: str) -> dict:
    corpus = corpus_of(rules)
    return {
        "rule_corpus": corpus,
        "rule_corpus_label": CORPUS_LABELS[corpus],
        "retrieval_mode": retrieval_mode,
        "compliance_disclaimer": COMPLIANCE_DISCLAIMER,
    }
