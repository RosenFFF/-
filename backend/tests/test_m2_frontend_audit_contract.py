"""Backend evidence against frontend @76830b2 field request; synthetic accounts only."""

import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.audit.service import Actor
from app.db.models import User

DETAIL_FIELDS = {
    "source_kind",
    "source_kind_label",
    "degrade_status",
    "llm_verified",
    "fallback_reason",
    "injection_category",
    "pii_fields",
    "rate_limit_scope",
    "actor_role",
    "resource_type",
    "resource_id",
    "ip",
}


@pytest.mark.parametrize("role", ["admin", "auditor"])
async def test_frontend_requested_snapshot_metrics_timeline_and_detail_are_present(api, role):
    c = await api.login(role)
    me = (await c.get("/api/v1/auth/me")).json()
    actor = Actor(me["id"], role, role, me["tenant_id"])
    events = [
        ("security.pii_masked", "success", {"counts": {"email": 2, "phone": 1}}),
        ("security.injection_detected", "blocked", {"patterns": ["3"]}),
        ("rate_limit.hit", "blocked", {"bucket": "write"}),
        ("rate_limit.hit", "blocked", {"bucket": "login"}),
        ("model.call", "success", {"provider": "fake", "model": "test-fixture-only", "status": "fallback"}),
        ("model.call", "failed", {"provider": "fake", "model": "test-fixture-only", "status": "failed"}),
        ("auth.login_failed", "denied", {"reason": "bad_credentials", "account_locked": True}),
    ]
    for action, result, detail in events:
        await api.app.state.audit.record(action, result, actor=actor, detail=detail)
    # An actually rejected CSRF request with signed active-user cookie must be scoped to that tenant.
    csrf = c.headers.pop("X-CSRF-Token")
    assert (await c.post("/api/v1/auth/refresh")).status_code == 403
    c.headers["X-CSRF-Token"] = csrf
    stats = (await c.get("/api/v1/audit/stats?window=1h")).json()
    parse = lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))  # noqa: E731
    assert parse(stats["window_end"]) - parse(stats["window_start"]) == timedelta(hours=1)
    assert parse(stats["generated_at"]) >= parse(stats["window_end"])
    assert stats["degrade_status"] and stats["llm_verified"] is False
    assert stats["source_kind"] == "synthetic" and stats["source_kind_label"]
    for key, expected in {
        "csrf_failed": 1,
        "auth_locked": 1,
        "model_errors": 1,
        "logins_failed": 1,
        "pii_masked": 3,
        "model_fallbacks": 1,
    }.items():
        assert stats["totals"][key] == expected, key
        assert sum(bucket[key] for bucket in stats["timeline"]) == expected, key
    logs = (await c.get("/api/v1/audit/logs?page_size=100")).json()["items"]
    assert logs and all(DETAIL_FIELDS <= set(row["detail"]) for row in logs)
    for row in logs:
        assert row["detail"]["llm_verified"] is False
        assert all(row["detail"][key] == row[key] for key in ("actor_role", "resource_type", "resource_id", "ip"))
    pii = next(r for r in logs if r["action"] == "security.pii_masked")
    assert pii["detail"]["pii_fields"] == ["email", "phone"]
    injection = next(r for r in logs if r["action"] == "security.injection_detected")
    assert injection["detail"]["injection_category"] == "prompt"
    assert {r["detail"]["rate_limit_scope"] for r in logs if r["action"] == "rate_limit.hit"} == {"ip", "user"}
    fallback = next(r for r in logs if r["detail"].get("status") == "fallback")
    assert fallback["detail"]["fallback_reason"] == "provider_fallback"
    assert "测试" in fallback["detail"]["source_kind_label"]


async def test_actual_account_lock_transition_counted_once_not_each_blocked_retry(api):
    admin = await api.login("admin")
    api.settings.login_max_failures = 1
    body = {"username": "reviewer", "password": secrets.token_urlsafe(18)}
    c = api.client()
    assert (await c.post("/api/v1/auth/login", json=body)).status_code == 401
    assert (await c.post("/api/v1/auth/login", json=body)).status_code == 423
    stats = (await admin.get("/api/v1/audit/stats")).json()
    assert stats["totals"]["auth_locked"] == 1 and stats["totals"]["logins_failed"] == 2


async def test_reviewer_both_global_audit_endpoints_403_and_audited(api):
    c = await api.login("reviewer")
    for endpoint in ("logs", "stats"):
        response = await c.get("/api/v1/audit/" + endpoint)
        assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"
    aud = await api.login("auditor")
    logs = (await aud.get("/api/v1/audit/logs?action=access.denied")).json()["items"]
    assert len(logs) == 2 and all(row["actor_role"] == "reviewer" for row in logs)


async def test_bad_cookie_csrf_events_never_attributed_from_unsigned_claims(api):
    c = await api.login("admin")
    me = (await c.get("/api/v1/auth/me")).json()
    anonymous = api.client()
    response = await anonymous.post(
        "/api/v1/auth/refresh",
        headers={
            "Cookie": "access_token=forged; csrf_token=forged",
            "X-CSRF-Token": "forged",
        },
    )
    assert response.status_code == 403
    assert (await c.get("/api/v1/audit/stats")).json()["totals"]["csrf_failed"] == 0
    async with api.app.state.db.maintenance_sessionmaker() as s:
        user = (await s.scalars(select(User).where(User.id == me["id"]))).one()
        assert user.tenant_id == me["tenant_id"]
