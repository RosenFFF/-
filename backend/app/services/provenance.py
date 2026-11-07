"""Conservative provenance labels: a reachable source never certifies a trade decision."""

from urllib.parse import urlparse

COMPLIANCE_DISCLAIMER = "自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。"
SOURCE_KIND_LABELS = {
    "synthetic": "合成规则 · 非真实合规结论",
    "public": "公开出处已核验 · 仍须人工复核",
}
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


def source_kind_of_corpus(corpus: str) -> str:
    """Frontend badge field: only synthetic|public. mixed/unknown → synthetic (conservative)."""
    return "public" if corpus == "public_verified" else "synthetic"


def source_kind_of_rule(rule: dict) -> str:
    return "public" if is_public(rule) else "synthetic"


def provenance(rules: list[dict], retrieval_mode: str) -> dict:
    corpus = corpus_of(rules)
    kind = source_kind_of_corpus(corpus)
    return {
        "rule_corpus": corpus,
        "rule_corpus_label": CORPUS_LABELS[corpus],
        "source_kind": kind,
        "source_kind_label": SOURCE_KIND_LABELS[kind],
        "retrieval_mode": retrieval_mode,
        "compliance_disclaimer": COMPLIANCE_DISCLAIMER,
    }


DEGRADE_STATUS = {
    "L0": "正常：真实模型链路可用",
    "L1": "已切换备用云端模型",
    "L2": "本地模型",
    "L3": "规则引擎降级，需人工复核",
}


def degrade_fields(level: str) -> dict:
    level = level if level in DEGRADE_STATUS else "L3"
    return {
        "degrade_level": level,
        "degrade_status": DEGRADE_STATUS[level],
        "degrade_warning": "完整离线流程尚未验收" if level == "L2" else None,
        "llm_verified": level in {"L0", "L1", "L2"},
    }
