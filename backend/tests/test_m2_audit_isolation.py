"""Cross-user/org denial evidence, no real-model claims."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.audit.service import Actor
from app.db.models import AuditLog, Tenant, User, uid
from app.security.tokens import issue_access

from .fakes import FakeLLM
from .test_m1_chat_sse import path
from .test_m1_pipeline import _report, quick_ocr  # noqa: F401

pytestmark = pytest.mark.usefixtures("quick_ocr")


async def foreign_admin(api):
    async with api.app.state.db.sessionmaker() as s:
        t = Tenant(name="synthetic-foreign-org")
        s.add(t)
        await s.flush()
        user = User(id=uid(), tenant_id=t.id, username="foreign-admin", password_hash="disabled-fixture", role="admin")
        s.add(user)
        await s.commit()
        actor = Actor(user.id, user.username, user.role, t.id)
    c = api.client()
    c.headers["Authorization"] = "Bearer " + issue_access(
        api.settings, user_id=actor.id, tenant_id=actor.tenant_id, role="admin"
    )
    return c, actor


@pytest.mark.parametrize("mode", ["same_org_other_user", "foreign_org_admin"])
async def test_cross_scope_document_report_history_replay_and_audit_denied(api, mode):
    api.app.state.ai.llm = FakeLLM()
    owner = await api.login("reviewer")
    doc_id, rid, _ = await _report(api, owner)
    own = await owner.post(path(rid), json={"content": "Explain"}, headers={"Accept": "text/event-stream"})
    sid = own.headers["x-chat-stream-id"]
    other = await api.login("reviewer2") if mode == "same_org_other_user" else (await foreign_admin(api))[0]
    for url in (
        f"/api/v1/documents/{doc_id}",
        f"/api/v1/documents/{doc_id}/recognition",
        f"/api/v1/documents/{doc_id}/pages/1/image",
        f"/api/v1/reviews/{rid}",
        path(rid),
        f"/api/v1/reviews/{rid}/audit",
    ):
        assert (await other.get(url)).status_code == 404, url
    assert (await other.delete(f"/api/v1/documents/{doc_id}")).status_code == 404
    assert (
        await other.patch(
            f"/api/v1/documents/{doc_id}/fields",
            json={
                "version": 1,
                "fields": [{"key": "hs_code", "value": "123456"}],
            },
        )
    ).status_code == 404
    for accept in ("application/json", "text/event-stream"):
        assert (await other.post(path(rid), json={"content": "Explain"}, headers={"Accept": accept})).status_code == 404
    assert (
        await other.post(
            path(rid),
            json={"content": "Explain"},
            headers={
                "Accept": "text/event-stream",
                "Last-Event-ID": sid + ":0",
            },
        )
    ).status_code == 404
    assert (
        await other.post("/api/v1/reviews", json={"document_ids": [doc_id], "destination_country": "VN"})
    ).status_code == 404
    assert (await other.get("/api/v1/documents")).json()["total"] == 0
    assert (await other.get("/api/v1/reviews")).json()["total"] == 0
    audit = await other.get("/api/v1/audit/logs")
    if mode == "same_org_other_user":
        assert audit.status_code == 403
    else:
        assert audit.status_code == 200 and audit.json()["items"] == []
        assert (await other.get("/api/v1/audit/stats")).json()["totals"]["requests"] == 0
    assert (await owner.get(f"/api/v1/reviews/{rid}/audit")).json()["total"] > 0


async def test_audit_time_action_result_actor_filters_pagination_and_validation(api):
    admin = await api.login("admin")
    me = (await admin.get("/api/v1/auth/me")).json()
    actor = Actor(me["id"], "admin", "admin", me["tenant_id"])
    start = datetime.now(UTC) - timedelta(seconds=1)
    for result in ("blocked", "success", "blocked"):
        await api.app.state.audit.record("security.output_blocked", result, actor=actor)
    end = datetime.now(UTC) + timedelta(seconds=1)
    params = {
        "action": "security.output_blocked",
        "result": "blocked",
        "actor_id": me["id"],
        "since": start.isoformat(),
        "until": end.isoformat(),
        "page_size": 1,
    }
    first = (await admin.get("/api/v1/audit/logs", params=params)).json()
    second = (await admin.get("/api/v1/audit/logs", params={**params, "page": 2})).json()
    local = timezone(timedelta(hours=-8))
    offset_params = {**params, "since": start.astimezone(local).isoformat(), "until": end.astimezone(local).isoformat()}
    assert (await admin.get("/api/v1/audit/logs", params=offset_params)).json()["total"] == 2
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["items"][0]["ts"] >= second["items"][0]["ts"]
    assert (await admin.get("/api/v1/audit/logs", params={**params, "page": 3})).json()["items"] == []
    assert (await admin.get("/api/v1/audit/logs", params={**params, "since": end.isoformat()})).status_code == 422
    for invalid in ({"page": 0}, {"page_size": 101}, {"result": "unknown"}, {"since": "2026-11-05T00:00:00"}):
        assert (await admin.get("/api/v1/audit/logs", params=invalid)).status_code == 422
    # Inclusive lower and exclusive upper boundary.
    stamp = first["items"][0]["ts"]
    assert (await admin.get("/api/v1/audit/logs", params={"action": "security.output_blocked", "until": stamp})).json()[
        "total"
    ] == 2


async def test_audit_tenant_null_events_secrets_and_verify_no_foreign_disclosure(api):
    admin = await api.login("admin")
    me = (await admin.get("/api/v1/auth/me")).json()
    actor = Actor(me["id"], "admin", "admin", me["tenant_id"])
    foreign, fa = await foreign_admin(api)
    secret = "fixture-never-a-real-secret"
    own_id = await api.app.state.audit.record(
        "config.change",
        "success",
        actor=actor,
        detail={"api_key": secret, "nested": {"password": secret}, "message": "Bearer " + secret, "tokens_in": 11},
    )
    foreign_id = await api.app.state.audit.record("config.change", "failed", actor=fa)
    null_id = await api.app.state.audit.record("auth.login_failed", "denied", detail={"reason": "unknown-account"})
    logs = (await admin.get("/api/v1/audit/logs")).json()
    assert own_id in [r["id"] for r in logs["items"]]
    assert foreign_id not in json.dumps(logs) and null_id not in json.dumps(logs) and secret not in json.dumps(logs)
    async with api.app.state.db.sessionmaker() as s:
        saved = await s.scalar(select(AuditLog).where(AuditLog.id == own_id))
        assert secret not in json.dumps(saved.detail) and saved.detail["tokens_in"] == 11
        # A legacy unsanitized row must also be protected at read time (hash now intentionally invalid).
        saved.detail = {"authorization": secret, "nested": {"refresh_token": secret}}
        await s.commit()
    assert secret not in (await admin.get("/api/v1/audit/logs")).text
    verification = (await foreign.get("/api/v1/audit/verify")).json()
    assert verification["valid"] and verification["checked"] == 1 and verification["first_broken_id"] is None
    own = (await admin.get("/api/v1/audit/verify")).json()
    assert not own["valid"] and own["first_broken_id"] == own_id


@pytest.mark.parametrize("window", ["1h", "24h", "7d"])
async def test_dashboard_stats_tenant_real_events_and_rbac(api, window):
    c = await api.login("auditor")
    me = (await c.get("/api/v1/auth/me")).json()
    actor = Actor(me["id"], "auditor", "auditor", me["tenant_id"])
    events = [
        ("security.pii_masked", "success", {"counts": {"email": 2, "phone": 1}}),
        ("model.call", "success", {"status": "fallback", "tokens_in": 5, "tokens_out": 7}),
        ("access.denied", "denied", {}),
        ("security.injection_detected", "blocked", {}),
        ("security.output_blocked", "blocked", {}),
        ("rate_limit.hit", "blocked", {}),
    ]
    for action, result, detail in events:
        await api.app.state.audit.record(action, result, actor=actor, detail=detail)
    _, other = await foreign_admin(api)
    await api.app.state.audit.record("access.denied", "denied", actor=other)
    stats = (await c.get("/api/v1/audit/stats", params={"window": window})).json()
    totals = stats["totals"]
    assert totals["requests"] == len(events) + 1  # Includes auditor login audit event.
    assert totals["pii_masked"] == 3 and totals["tokens_used"] == 12
    assert totals["access_denied"] == totals["injections_blocked"] == totals["outputs_blocked"] == 1
    assert totals["model_fallbacks"] == totals["rate_limited"] == totals["model_calls"] == 1
    assert sum(b["model_calls"] for b in stats["timeline"]) == 1
    assert stats["top_denied_actors"] == [{"actor_username": "auditor", "count": 1}]
    assert stats["audit_chain_valid"]
    assert (await c.get("/api/v1/audit/stats?window=bad")).status_code == 422
    reviewer = await api.login("reviewer")
    assert (await reviewer.get("/api/v1/audit/stats")).status_code == 403
