"""Deterministic retained-finding prose, not translation or a new model call."""

RULE_LIST_LIMIT = 5


def _rule_ids(finding):
    return finding["rule_ids"] if "rule_ids" in finding else [c["rule_id"] for c in finding.get("citations", [])]


def _ru_form(count, forms):
    """Russian cardinal agreement: 1/21, 2–4/22–24, 0/5–20/25–30, etc."""
    if count % 10 == 1 and count % 100 != 11:
        return forms[0]
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return forms[1]
    return forms[2]


def _rule_list(rules, language):
    listed = rules[:RULE_LIST_LIMIT]
    capped = len(rules) > RULE_LIST_LIMIT
    if language == "zh-CN":
        return "、".join(listed) + ("等" if capped else "")
    if capped:
        suffix = {"en": ", etc.", "vi": ", v.v.", "ru": " и др."}[language]
        return ", ".join(listed) + suffix
    if len(listed) < 2:
        return "".join(listed)
    conjunction = {"en": " and ", "vi": " và ", "ru": " и "}[language]
    comma = "," if language == "en" and len(listed) > 2 else ""
    return ", ".join(listed[:-1]) + comma + conjunction + listed[-1]


def retained_summary(findings, removed, language="zh-CN"):
    """Default/fallback zh-CN; API also accepts pt/ar, which have no template yet.

    An info finding citing ONLY SYN-REVIEW is a scope note, not an issue. A mixed
    citation or non-info finding still counts; info scope citations aren't listed.
    Count finding objects, not unique rules, and never inspect document values.
    """
    language = language if language in ("en", "ru", "vi") else "zh-CN"
    issues = [f for f in findings if not (f["severity"] == "info" and set(_rule_ids(f)) == {"SYN-REVIEW"})]
    count = len(issues)
    high = sum(f["severity"] == "high" for f in issues)
    rules = sorted({r for f in issues for r in _rule_ids(f) if r != "SYN-REVIEW" or f["severity"] != "info"})
    listed = _rule_list(rules, language)
    if language == "vi":
        text = (
            f"Các kết quả được giữ lại nêu {count} vấn đề" if count else "Các kết quả được giữ lại không nêu vấn đề nào"
        )
        if high:
            text += f", trong đó có {high} vấn đề rủi ro cao"
        if listed:
            noun = "quy tắc" if len(rules) == 1 else "các quy tắc"
            text += f", liên quan đến {noun} {listed}"
        return text.rstrip(".") + f". Đã lọc {removed} kết luận không có căn cứ, khuyến nghị xem xét thủ công."
    if language == "en":
        text = (
            f"The retained findings identify {count} {'issue' if count == 1 else 'issues'}"
            if count
            else "No issues are listed in the retained findings"
        )
        if high:
            text += f", including {high} high-risk {'issue' if high == 1 else 'issues'}"
        text += "."  # Zero is bounded to retained findings, not legal clearance.
        if listed:
            text += f" They cite {'rule' if len(rules) == 1 else 'rules'} {listed}".rstrip(".") + "."
        return (
            text
            + f" Removed {removed} unsupported {'conclusion' if removed == 1 else 'conclusions'}."
            + " Manual review is recommended."
        )
    if language == "ru":
        if count:
            verb = _ru_form(count, ("отмечена", "отмечены", "отмечено"))
            noun = _ru_form(count, ("проблема", "проблемы", "проблем"))
            text = f"В сохранённых результатах проверки {verb} {count} {noun}."
        else:
            text = "В сохранённых результатах проверки проблемы не указаны."
        if high:
            noun = _ru_form(high, ("проблема", "проблемы", "проблем"))
            text += f" Из них {high} {noun} с высоким риском."
        if listed:
            noun = "правилом" if len(rules) == 1 else "правилами"
            text += f" Выводы связаны с {noun} {listed}".rstrip(".") + "."
        verb = _ru_form(removed, ("Отфильтрован", "Отфильтрованы", "Отфильтровано"))
        noun = _ru_form(removed, ("необоснованный вывод", "необоснованных вывода", "необоснованных выводов"))
        return text + f" {verb} {removed} {noun}. Рекомендуется проверка специалистом."
    text = f"保留的审查结果共列出 {count} 项问题" if count else "保留的审查结果未列出问题"
    if high:
        text += f"，其中高风险 {high} 项"
    if listed:
        text += f"，涉及规则 {listed}"
    return text + f"。已过滤 {removed} 条无依据结论，建议人工复核。"
