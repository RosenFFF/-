"""No model/network calls: synthetic counts plus test-fixture API integration."""

import pytest

from app.services.model_findings import grounded_summary
from app.services.summary_text import retained_summary


def finding(rule="SYN-HS", severity="high", *, api_shape=False):
    row = {"severity": severity, "determined_by": "rule", "category": "other"}
    row.update({"citations": [{"rule_id": rule}]} if api_shape else {"rule_ids": [rule]})
    return row


def rebuild(rows, language="zh-CN", removed=2):
    return grounded_summary("SYN-ORIGIN", {"unsupported_finding": removed}, rows, {"SYN-ORIGIN"}, language=language)


@pytest.mark.parametrize(
    "language,expected",
    [
        (
            "zh-CN",
            "保留的审查结果共列出 2 项问题，其中高风险 1 项，涉及规则 SYN-AMOUNT、SYN-HS。"
            "已过滤 2 条无依据结论，建议人工复核。",
        ),
        (
            "en",
            "The retained findings identify 2 issues, including 1 high-risk issue. "
            "They cite rules SYN-AMOUNT and SYN-HS. Removed 2 unsupported conclusions. Manual review is recommended.",
        ),
        (
            "vi",
            "Các kết quả được giữ lại nêu 2 vấn đề, trong đó có 1 vấn đề rủi ro cao, "
            "liên quan đến các quy tắc SYN-AMOUNT và SYN-HS. "
            "Đã lọc 2 kết luận không có căn cứ, khuyến nghị xem xét thủ công.",
        ),
        (
            "ru",
            "В сохранённых результатах проверки отмечены 2 проблемы. Из них 1 проблема с высоким риском. "
            "Выводы связаны с правилами SYN-AMOUNT и SYN-HS. Отфильтрованы 2 необоснованных вывода. "
            "Рекомендуется проверка специалистом.",
        ),
    ],
)
def test_one_natural_template_per_language(language, expected):
    rows = [finding("SYN-HS"), finding("SYN-AMOUNT", "low"), finding("SYN-REVIEW", "info")]
    assert rebuild(rows, language) == expected
    assert rebuild(list(reversed(rows)), language) == expected
    assert "SYN-ORIGIN" not in expected and "SYN-REVIEW" not in expected


@pytest.mark.parametrize(
    "language,phrase",
    [
        ("zh-CN", "保留的审查结果未列出问题"),
        ("en", "No issues are listed in the retained findings"),
        ("ru", "В сохранённых результатах проверки проблемы не указаны"),
        ("vi", "Các kết quả được giữ lại không nêu vấn đề nào"),
    ],
)
@pytest.mark.parametrize("scope_only", [False, True])
def test_zero_issues_no_high_risk_or_rule_clause(language, phrase, scope_only):
    rows = [finding("SYN-REVIEW", "info")] if scope_only else []
    text = rebuild(rows, language)
    assert text.startswith(phrase)
    assert "SYN-REVIEW" not in text
    assert not any(term in text for term in ("高风险", "high-risk", "высоким риском", "rủi ro cao"))


@pytest.mark.parametrize(
    "count,issue,verb,conclusion,removed_verb",
    [
        (1, "проблема", "отмечена", "необоснованный вывод", "Отфильтрован"),
        (2, "проблемы", "отмечены", "необоснованных вывода", "Отфильтрованы"),
        (4, "проблемы", "отмечены", "необоснованных вывода", "Отфильтрованы"),
        (5, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (11, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (12, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (14, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (21, "проблема", "отмечена", "необоснованный вывод", "Отфильтрован"),
        (22, "проблемы", "отмечены", "необоснованных вывода", "Отфильтрованы"),
        (25, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (111, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
        (112, "проблем", "отмечено", "необоснованных выводов", "Отфильтровано"),
    ],
)
def test_russian_cardinal_agreement(count, issue, verb, conclusion, removed_verb):
    text = rebuild([finding() for _ in range(count)], "ru", removed=count)
    assert f"{verb} {count} {issue}." in text
    assert f"Из них {count} {issue} с высоким риском." in text
    assert f"{removed_verb} {count} {conclusion}." in text


@pytest.mark.parametrize("count", [1, 2, 5, 21])
def test_english_singular_plural(count):
    text = rebuild([finding() for _ in range(count)], "en", removed=count)
    suffix = "" if count == 1 else "s"
    assert f"identify {count} issue{suffix}, including {count} high-risk issue{suffix}." in text
    assert f"Removed {count} unsupported conclusion{suffix}." in text
    assert "cite rule SYN-HS." in text  # unique rule count, not finding count


@pytest.mark.parametrize("language,tail", [("zh-CN", "等。"), ("en", ", etc."), ("ru", " и др."), ("vi", ", v.v.")])
def test_rule_list_sorted_unique_and_capped(language, tail):
    rows = [finding(f"RULE-{i}", "low", api_shape=True) for i in reversed(range(7))]
    rows.append(finding("RULE-0", "low"))
    text = rebuild(rows, language)
    assert "RULE-4" + tail in text
    assert "RULE-5" not in text and "RULE-6" not in text
    assert text.count("RULE-0") == 1 and ".." not in text
    assert "high-risk" not in text and "高风险" not in text and "высоким риском" not in text


@pytest.mark.parametrize("language", ["zh", "unknown", "en-US", "pt", "ar", None])
def test_default_and_unimplemented_language_fallback_is_api_default_chinese(language):
    rows = [finding()]
    assert rebuild(rows, language) == rebuild(rows, "zh-CN")
    assert grounded_summary("SYN-ORIGIN", {"unsupported_finding": 2}, rows, {"SYN-ORIGIN"}) == rebuild(rows)


def test_scope_exclusion_is_only_pure_info_note_and_never_mutates_findings_or_counts():
    rows = [finding("SYN-REVIEW", "info"), finding("SYN-REVIEW", "high"), finding("PUB-GUIDANCE", "info")]
    rows.append({"severity": "info", "rule_ids": ["SYN-REVIEW", "SYN-HS"], "determined_by": "llm"})
    assert "共列出 3 项问题，其中高风险 1 项" in rebuild(rows)
    assert len(rows) == 4
    counts = {"unsupported_finding": 2, "duplicate_finding": 3}
    grounded_summary("SYN-ORIGIN", counts, rows, {"SYN-ORIGIN"})
    assert counts == {"unsupported_finding": 2, "duplicate_finding": 3}
    assert "涉及规则" not in retained_summary([{"severity": "low", "rule_ids": []}], 1)


@pytest.mark.parametrize("language", ["zh-CN", "en", "ru", "vi"])
def test_unaffected_model_summary_is_not_translated_or_replaced(language):
    text = "Unrelated original summary."
    assert grounded_summary(text, {"unsupported_finding": 1}, [], {"SYN-ORIGIN"}, language=language) == text


@pytest.mark.parametrize("language", ["zh-CN", "en", "ru", "vi"])
async def test_review_forwards_row_language_and_preserves_scope_disclaimer_prefix(api, monkeypatch, language):
    from app.ai.ocr import OcrBlock, ocr_engine
    from app.services import review
    from app.services.provenance import COMPLIANCE_DISCLAIMER, CORPUS_LABELS

    from .fakes import FakeLLM
    from .samples import invoice_image
    from .test_documents import _upload

    api.app.state.ai.llm = FakeLLM()  # fixture-only, no real-model evidence/calls
    monkeypatch.setattr(
        ocr_engine, "recognize", lambda _: ([OcrBlock("INVOICE NO: SYN-1", [0.1, 0.1, 0.8, 0.2], 1)], 1)
    )
    seen = []

    def summary_spy(*args, language):
        seen.append(language)
        return retained_summary([finding()], 2, language)

    monkeypatch.setattr(review, "grounded_summary", summary_spy)
    client = await api.login("reviewer")
    uploaded = await _upload(client, invoice_image())
    created = await client.post(
        "/api/v1/reviews",
        json={
            "document_ids": [uploaded.json()["id"]],
            "destination_country": "VN",
            "language": language,
        },
    )
    assert created.status_code == 202
    report = (await client.get(f"/api/v1/reviews/{created.json()['id']}")).json()
    assert seen == [language] and report["language"] == language
    prefix = CORPUS_LABELS[report["security"]["rule_corpus"]] + "。" + COMPLIANCE_DISCLAIMER + "\n"
    assert report["summary"] == prefix + retained_summary([finding()], 2, language)
    counts = report["security"]["model_output_filter"]
    assert counts.get("duplicate_finding", 0) + counts.get("unsupported_finding", 0) == 1
    await client.aclose()


@pytest.mark.parametrize("count", [1, 2])
def test_vietnamese_code_count_and_natural_list_without_plural_inflection(count):
    from typing import get_args

    from app.api.v1.schemas import Language

    assert "vi" in get_args(Language)
    rows = [finding(f"RULE-{i}", "low") for i in range(count)]
    text = rebuild(rows, "vi", removed=count)
    assert f"nêu {count} vấn đề" in text
    assert f"Đã lọc {count} kết luận" in text
    assert "rủi ro cao" not in text
    assert ("quy tắc RULE-0." if count == 1 else "các quy tắc RULE-0 và RULE-1.") in text
    assert rebuild([finding(f"RULE-{i}", "low") for i in range(3)], "vi").count("RULE-0, RULE-1 và RULE-2.") == 1
    assert text != rebuild(rows, "zh-CN", removed=count)
