"""Conservative dashboard provenance for live and legacy ledger entries.

A provider success trace is NOT a real-model acceptance attestation. Until a separate
acceptance mechanism exists, dashboard llm_verified is always false.
"""

from __future__ import annotations

from app.security.output import sanitize_public

UNVERIFIED = "来源未核验 · 非真实模型验收"
MODEL_UNVERIFIED = "模型事件已记录；未完成真实模型验收"
PII_KINDS = {"person_name", "phone", "email", "bank_account", "address", "id_number"}


def public_detail(row) -> dict:
    detail = sanitize_public(row.detail or {}, pii=True)
    model_event = row.action.startswith("model.")
    fixture = detail.get("provider") == "fake" or detail.get("model") == "test-fixture-only"
    kind = "public" if detail.get("source_kind") == "public" and not fixture else "synthetic"
    reason = detail.get("fallback_reason")
    if not isinstance(reason, str):
        reason = None
    if model_event and not reason:
        if detail.get("status") == "fallback" or row.action == "model.fallback":
            reason = "provider_fallback"
        elif row.result == "failed":
            reason = "model_error"
    category = None
    if row.action == "security.injection_detected" or (
        row.action == "chat.blocked" and detail.get("block_reason") == "prompt_injection"
    ):
        category = "prompt"
    elif row.action == "chat.blocked" and detail.get("block_reason") == "out_of_scope":
        category = "scope"
    elif row.action == "security.output_blocked":
        category, reason = "output", "unsafe_output"
    fields = None
    if row.action == "security.pii_masked":
        counts = detail.get("counts", {})
        fields = sorted(set(counts) & PII_KINDS) if isinstance(counts, dict) else []
    scope = None
    if row.action == "rate_limit.hit":
        scope = "ip" if detail.get("bucket") in {"login", "auth"} else "user"
    return {
        **detail,
        "source_kind": kind,
        "source_kind_label": "测试替身/演示来源 · 非真实模型验收"
        if fixture
        else ("公开出处（不等于模型验收）" if kind == "public" else UNVERIFIED),
        "degrade_status": MODEL_UNVERIFIED if model_event else None,
        "llm_verified": False,
        "fallback_reason": reason,
        "injection_category": category,
        "pii_fields": fields,
        "rate_limit_scope": scope,
        "actor_role": row.actor_role,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "ip": row.ip,
    }


def event_counts(row) -> dict[str, int]:
    result = {"requests": 1}
    for action, key in (
        ("auth.login_failed", "logins_failed"),
        ("access.denied", "access_denied"),
        ("rate_limit.hit", "rate_limited"),
        ("security.injection_detected", "injections_blocked"),
        ("security.output_blocked", "outputs_blocked"),
        ("model.call", "model_calls"),
    ):
        if row.action == action:
            result[key] = 1
    detail = row.detail or {}
    if row.action == "access.denied" and detail.get("reason") == "csrf":
        result["csrf_failed"] = 1
    if row.action == "auth.login_failed" and detail.get("account_locked") is True:
        result["auth_locked"] = 1  # Transition into lock, not every retry while locked.
    if row.action == "model.call" and row.result == "failed" and detail.get("status") != "fallback":
        result["model_errors"] = 1
    if row.action == "security.pii_masked":
        counts = detail.get("counts", {})
        if isinstance(counts, dict):
            result["pii_masked"] = sum(v for v in counts.values() if type(v) is int and v >= 0)
    if row.action == "model.fallback" or (row.action == "model.call" and detail.get("status") == "fallback"):
        result["model_fallbacks"] = 1
    if row.action == "model.call":
        result["tokens_used"] = sum(
            v for k in ("tokens_in", "tokens_out") if type(v := detail.get(k)) is int and v >= 0
        )
    return result
