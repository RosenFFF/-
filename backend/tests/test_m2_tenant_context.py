"""Runnable SQLite/fakeredis integration evidence, NEVER live PostgreSQL/LLM acceptance."""

import asyncio
import json
from dataclasses import asdict
from io import StringIO
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select, text, update

from alembic import command
from app.audit.service import Actor
from app.core.errors import AppError
from app.db.base import Database
from app.db.models import AuditLog, ChatMessage, Review, User, uid
from app.db.tenant import TenantScope, bind_scope
from app.deps import CurrentUser
from app.security.cookies import issue_csrf
from app.security.tokens import issue_access

from .test_m1_chat_sse import parse_sse, path, seed_review
from .test_m2_audit_isolation import foreign_admin


@pytest.fixture
async def workers(api, monkeypatch):
    # ARQ settings intentionally require configured secrets at import/startup.
    # Supply this test's synthetic Settings, never an environment/credential file.
    monkeypatch.setattr("app.core.config.get_settings", lambda: api.settings)
    from app.workers import tasks

    monkeypatch.setattr(tasks, "get_settings", lambda: api.settings)
    return tasks


async def identity(api, username="admin"):
    async with api.app.state.db.maintenance_sessionmaker() as s:
        u = await s.scalar(select(User).where(User.username == username))
        return CurrentUser(u.id, u.tenant_id, u.username, u.role)


async def test_anonymous_invalid_and_malformed_claims_do_not_query_user_or_business(api):
    statements = []

    def sql(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(api.app.state.db.engine.sync_engine, "before_cursor_execute", sql)
    try:
        async with api.client() as c:
            for token in (None, "invalid", issue_access(api.settings, user_id="bad", tenant_id=uid(), role="admin")):
                headers = {"Authorization": "Bearer " + token} if token else {}
                for url in ("/api/v1/auth/me", "/api/v1/documents", "/api/v1/audit/logs"):
                    assert (await c.get(url, headers=headers)).status_code == 401
        assert statements == []
    finally:
        event.remove(api.app.state.db.engine.sync_engine, "before_cursor_execute", sql)


@pytest.mark.parametrize("sql", [select(User), select(Review), text("SELECT * FROM users")])
async def test_request_style_session_without_context_fails_before_sql(api, sql):
    async with api.app.state.db.sessionmaker() as s:
        assert s.info["scope_required"] is True
        with pytest.raises(RuntimeError, match="context required"):
            await s.execute(sql)
        assert not s.in_transaction()


async def test_pre_auth_exact_lookup_is_not_business_scope_and_injection_does_not_enumerate(api):
    db = api.app.state.db
    user = await identity(api)
    row = await db.login_candidate("admin")
    assert row["id"] == user.id and row["tenant_id"] == user.tenant_id
    assert await db.login_candidate("admin' OR 1=1 --") is None
    async with db.tenant_session(user.scope) as s:
        s.info["credential_only"] = True
        assert (await s.scalars(select(User.id))).all() == [user.id]
        for sql in (select(Review), select(AuditLog)):
            with pytest.raises(RuntimeError, match="credential session"):
                await s.execute(sql)
        u = await s.get(User, user.id)
        u.role = "reviewer"
        with pytest.raises(RuntimeError, match="authentication counters"):
            await s.commit()
    # Closing the credential transaction must not publish any login identity.
    async with db.sessionmaker() as s:
        assert s.info["scope_required"] is True
        with pytest.raises(RuntimeError, match="context required"):
            await s.scalars(select(User))


@pytest.mark.parametrize("kind", ["wrong_tenant", "stale_role"])
async def test_verified_claims_are_bound_before_first_identity_query_and_stale_claims_rejected(api, kind):
    own = await identity(api)
    _, other = await foreign_admin(api)
    token = issue_access(
        api.settings,
        user_id=own.id,
        tenant_id=other.tenant_id if kind == "wrong_tenant" else own.tenant_id,
        role="reviewer" if kind == "stale_role" else own.role,
    )
    async with api.client() as c:
        response = await c.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 401 and own.username not in response.text


@pytest.mark.parametrize("raw", ["opaque-legacy-cookie", "forged.routing.proof"])
async def test_refresh_without_signed_routing_proof_never_searches_token_table(api, raw):
    statements = []

    def sql(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(api.app.state.db.engine.sync_engine, "before_cursor_execute", sql)
    try:
        csrf = issue_csrf(api.settings, "", raw)
        async with api.client() as c:
            for route in ("refresh", "logout"):
                r = await c.post(
                    "/api/v1/auth/" + route,
                    headers={"Cookie": f"csrf_token={csrf}; refresh_token={raw}", "X-CSRF-Token": csrf},
                )
                assert r.status_code == 401
        assert statements == []
    finally:
        event.remove(api.app.state.db.engine.sync_engine, "before_cursor_execute", sql)


async def test_shared_physical_audit_storage_has_independent_tenant_and_platform_chains(api):
    own = await identity(api)
    _, other = await foreign_admin(api)
    audit = api.app.state.audit
    ids = []
    for actor in (own.actor, other, own.actor, None, other, own.actor):
        ids.append(await audit.record("test.isolation", "success", actor=actor))
    async with api.app.state.db.maintenance_sessionmaker() as s:
        rows = (await s.scalars(select(AuditLog).order_by(AuditLog.seq))).all()
        heads = {}
        for row in rows:
            assert row.prev_hash == heads.get(row.tenant_id)
            heads[row.tenant_id] = row.hash
        assert [r.actor_role for r in rows if r.actor_id == own.id] == [own.role] * 3
    assert (await audit.verify(own.scope))["checked"] == 3
    assert (await audit.verify(TenantScope(other.tenant_id, other.id, other.role)))["checked"] == 2
    async with api.app.state.db.tenant_session(own.scope) as s:
        assert (await s.scalars(select(AuditLog).where(AuditLog.tenant_id == other.tenant_id))).all() == []
    for actor in (
        Actor(id=own.id),
        Actor(own.id, role=own.role, tenant_id=other.tenant_id),
        Actor(own.id, role="auditor", tenant_id=own.tenant_id),
    ):
        with pytest.raises(ValueError, match="actor"):
            await audit.record("test.invalid", "failed", actor=actor)


async def test_legacy_global_link_is_not_rehashed_or_silently_accepted(api):
    own = await identity(api)
    _, foreign = await foreign_admin(api)
    fid = await api.app.state.audit.record("test.legacy", "success", actor=foreign)
    oid = await api.app.state.audit.record("test.legacy", "success", actor=own.actor)
    async with api.app.state.db.maintenance_sessionmaker() as s:
        foreign_row = await s.scalar(select(AuditLog).where(AuditLog.id == fid))
        own_row = await s.scalar(select(AuditLog).where(AuditLog.id == oid))
        own_row.prev_hash = foreign_row.hash
        await s.commit()
    result = await api.app.state.audit.verify(own.scope)
    assert not result["valid"] and result["first_broken_id"] == oid


@pytest.mark.parametrize("ending", ["commit", "rollback", "exception"])
async def test_one_connection_reuse_does_not_retain_scopes_identity_maps_or_unbound_access(api, ending):
    db = api.app.state.db
    own = await identity(api)
    _, other = await foreign_admin(api)
    from sqlalchemy.ext.asyncio import create_async_engine

    await db.engine.dispose()
    db.engine = create_async_engine(api.settings.database_url, pool_size=1, max_overflow=0)
    db.sessionmaker.configure(bind=db.engine)
    db.maintenance_sessionmaker.configure(bind=db.engine)
    for scope in [own.scope, TenantScope(other.tenant_id, other.id, other.role), own.scope]:
        try:
            async with db.tenant_session(scope) as s:
                assert set((await s.scalars(select(User.tenant_id))).all()) == {scope.org_id}
                await getattr(s, "rollback" if ending == "rollback" else "commit")()
                assert set((await s.scalars(select(User.tenant_id))).all()) == {scope.org_id}
                with pytest.raises(RuntimeError, match="fresh session"):
                    bind_scope(s, own.scope)
                if ending == "exception":
                    raise LookupError("synthetic cancellation")
        except LookupError:
            assert ending == "exception"
        async with db.sessionmaker() as s:
            assert s.info["scope_required"] is True
            assert "tenant_scope" not in s.info
            with pytest.raises(RuntimeError, match="context required"):
                await s.execute(select(User))


@pytest.mark.parametrize("task", ["ocr_task", "review_task"])
@pytest.mark.parametrize("kind", ["missing", "foreign_identity", "stale_role", "disabled"])
async def test_worker_missing_or_mismatched_identity_rejected_without_resource_lookup(api, workers, task, kind):
    own = await identity(api, "reviewer")
    payload = asdict(own.scope)
    if kind == "missing":
        payload = None
    elif kind == "foreign_identity":
        _, other = await foreign_admin(api)
        payload["org_id"] = other.tenant_id
    elif kind == "stale_role":
        payload["role"] = "admin"
    elif kind == "disabled":
        async with api.app.state.db.maintenance_sessionmaker() as s:
            await s.execute(update(User).where(User.id == own.id).values(disabled=True))
            await s.commit()
    st = api.app.state
    with pytest.raises(ValueError, match="context|identity"):
        await getattr(workers, task)(
            {"db": st.db, "store": st.store, "audit": st.audit, "ai": st.ai}, uid(), tenant_context=payload
        )


@pytest.mark.parametrize("mode", ["foreign_org", "same_org_other_owner"])
async def test_worker_valid_identity_cannot_claim_foreign_review(api, workers, mode):
    rid = await seed_review(api, status="queued")
    own = await identity(api, "reviewer2")
    if mode == "foreign_org":
        _, actor = await foreign_admin(api)
        own = CurrentUser(actor.id, actor.tenant_id, actor.username, actor.role)
    st = api.app.state
    await workers.review_task(
        {"db": st.db, "store": st.store, "audit": st.audit, "ai": st.ai}, rid, tenant_context=asdict(own.scope)
    )
    async with st.db.maintenance_sessionmaker() as s:
        assert (await s.get(Review, rid)).status == "queued"
        assert (await s.scalars(select(AuditLog).where(AuditLog.resource_id == rid))).all() == []


async def test_sse_replay_and_generation_require_and_revalidate_identity(api):
    from .fakes import FakeLLM

    api.app.state.ai.llm = FakeLLM()
    rid = await seed_review(api)
    c = await api.login("reviewer")
    response = await c.post(path(rid), json={"content": "Explain"}, headers={"Accept": "text/event-stream"})
    assert parse_sse(response)[-1]["event"] == "done"
    sid = response.headers["x-chat-stream-id"]
    user = await identity(api, "reviewer")
    foreign, actor = await foreign_admin(api)
    wrong = CurrentUser(actor.id, actor.tenant_id, actor.username, actor.role)
    service = api.app.state.chat
    with pytest.raises(AppError, match="流不存在"):
        _ = [e async for e in service.events(sid, user=wrong, review_id=rid)]
    # Redis metadata is checked for every replay loop, not merely on resume HTTP.
    meta = json.loads(await api.app.state.redis.get(service.key(sid, "meta")))
    meta["tenant_id"] = actor.tenant_id
    await api.app.state.redis.set(service.key(sid, "meta"), json.dumps(meta))
    with pytest.raises(AppError, match="流不存在"):
        _ = [e async for e in service.events(sid, user=user, review_id=rid)]
    with pytest.raises(AppError, match="流不存在"):
        await service.generate(sid, meta, {}, [], "Explain", "en", None, user)
    assert len(api.app.state.ai.llm.messages) == 1
    await c.aclose()
    await foreign.aclose()


async def test_sse_identity_revocation_during_generation_never_persists_or_replays_answer(api):
    from .fakes import FakeLLM

    entered, release = asyncio.Event(), asyncio.Event()

    class Paused(FakeLLM):
        async def chat_stream(self, messages, *, task):
            entered.set()
            await release.wait()
            async for chunk in super().chat_stream(messages, task=task):
                yield chunk

    api.app.state.ai.llm = Paused()
    rid = await seed_review(api)
    user = await identity(api, "reviewer")
    async with api.app.state.db.tenant_session(user.scope) as s:
        review = await s.get(Review, rid)
    sid = await api.app.state.chat.start(review, user, "Explain", "en", "synthetic-revocation")
    producer = api.app.state.chat.tasks[sid]
    await asyncio.wait_for(entered.wait(), 3)
    async with api.app.state.db.maintenance_sessionmaker() as s:
        await s.execute(update(User).where(User.id == user.id).values(disabled=True))
        await s.commit()
    release.set()
    with pytest.raises(AppError):
        await asyncio.wait_for(producer, 3)
    assert await api.app.state.redis.lrange(api.app.state.chat.key(sid, "events"), 0, -1) == []
    async with api.app.state.db.maintenance_sessionmaker() as s:
        rows = (await s.scalars(select(ChatMessage).where(ChatMessage.review_id == rid))).all()
        assert [r.role for r in rows] == ["user"]


def test_additive_context_migration_has_narrow_select_only_auth_and_no_definer_bypass():
    cfg = Database.migration_config()
    cfg.attributes["database_url"] = "postgresql+asyncpg://unused/unused"
    cfg.output_buffer = StringIO()
    command.upgrade(cfg, "0002_m2_tenant_rls:head", sql=True)
    sql = cfg.output_buffer.getvalue()
    assert "app.auth_username" in sql and "FOR SELECT" in sql
    assert "tenant_insert" in sql and "tenant_update" in sql and "tenant_delete" in sql
    assert "app.audit_platform" in sql and "actor_id IS NULL" in sql
    assert "SECURITY DEFINER" not in sql and "DISABLE ROW LEVEL" not in sql and "BYPASSRLS" not in sql


@pytest.mark.parametrize("entry", ["api", "worker"])
async def test_api_and_worker_startup_keep_postgres_gate_before_ai_redis_and_bootstrap(
    api, workers, monkeypatch, entry
):
    from app.main import create_app

    tasks = workers

    monkeypatch.setattr(Database, "check_migrated", AsyncMock())
    monkeypatch.setattr(Database, "migrate", AsyncMock())
    monkeypatch.setattr(Database, "is_postgres", True, raising=False)
    original = Database.__init__

    def init(self, url):
        original(self, url)
        self.is_postgres = True

    monkeypatch.setattr(Database, "__init__", init)
    monkeypatch.setattr("app.db.base.check_application_role", AsyncMock())
    if entry == "api":
        app = create_app(api.settings)
        with pytest.raises(RuntimeError, match="deployment blocked.*real non-owner PostgreSQL"):
            async with app.router.lifespan_context(app):
                pytest.fail("PG API startup must remain blocked")
        assert not hasattr(app.state, "ai") and not hasattr(app.state, "redis")
    else:
        monkeypatch.setattr(tasks, "get_settings", lambda: api.settings)
        context = {}
        with pytest.raises(RuntimeError, match="deployment blocked.*real non-owner PostgreSQL"):
            await tasks.startup(context)
        assert "ai" not in context and "store" not in context


async def test_background_processing_failure_is_audited_to_correct_org_actor_role(api, monkeypatch):
    from .samples import invoice_image
    from .test_documents import _upload

    def broken_renderer(*args):
        raise ValueError("synthetic failure before OCR")

    monkeypatch.setattr("app.services.files.render_pages", broken_renderer)
    c = await api.login("reviewer")
    own = await identity(api, "reviewer")
    response = await _upload(c, invoice_image())
    assert response.status_code == 202
    doc_id = response.json()["id"]
    async with api.app.state.db.maintenance_sessionmaker() as s:
        logs = (
            await s.scalars(select(AuditLog).where(AuditLog.resource_id == doc_id, AuditLog.result == "failed"))
        ).all()
        assert len(logs) == 1
        assert (logs[0].tenant_id, logs[0].actor_id, logs[0].actor_role) == (own.tenant_id, own.id, own.role)
    await c.aclose()


async def test_arq_enqueue_serializes_authenticated_context_for_both_tasks(api):
    from app.db.models import Document, DocumentFields
    from app.services.fields import seal_fields

    from .samples import invoice_image
    from .test_documents import _upload

    queue = AsyncMock()
    api.app.state.arq = queue
    api.settings.task_mode = "arq"
    c = await api.login("reviewer")
    user = await identity(api, "reviewer")
    response = await _upload(c, invoice_image())
    assert response.status_code == 202
    doc_id = response.json()["id"]
    async with api.app.state.db.maintenance_sessionmaker() as s:
        doc = await s.get(Document, doc_id)
        doc.status = "ready"
        s.add(DocumentFields(document_id=doc_id, source="rule", fields=seal_fields(api.app.state.store, doc, [])))
        await s.commit()
    response = await c.post("/api/v1/reviews", json={"document_ids": [doc_id], "destination_country": "VN"})
    assert response.status_code == 202
    calls = queue.enqueue_job.await_args_list
    assert [c.args[0] for c in calls] == ["ocr_task", "review_task"]
    assert all(c.kwargs["tenant_context"] == asdict(user.scope) for c in calls)
    await c.aclose()


async def test_scoped_aliases_child_reads_and_foreign_parent_writes_are_denied(api):
    from sqlalchemy.orm import aliased

    from app.db.models import Document, OcrPage

    from .test_m2_postgres_rls import seed

    db = api.app.state.db
    scopes, rows = await seed(db)  # SQLite fixture shape, explicitly NOT RLS.
    foreign_doc = rows[1]["documents"]["id"]
    async with db.tenant_session(scopes[0]) as s:
        alias = aliased(Document)
        assert (await s.scalars(select(alias.id))).all() == [rows[0]["documents"]["id"]]
        assert (await s.scalars(select(OcrPage).where(OcrPage.document_id == foreign_doc))).all() == []
        s.add(OcrPage(document_id=foreign_doc, page=2, blocks=[], engine="test", duration_ms=0))
        with pytest.raises(RuntimeError, match="parent denied"):
            await s.commit()


async def test_concurrent_jobs_cannot_share_ambient_tenant_context(api):
    own = await identity(api)
    _, other = await foreign_admin(api)
    scopes = [own.scope, TenantScope(other.tenant_id, other.id, other.role)]

    async def job(scope):
        async with api.app.state.db.job_session(asdict(scope)) as s:
            await asyncio.sleep(0)
            assert set((await s.scalars(select(User.tenant_id))).all()) == {scope.org_id}
            await s.commit()
            await asyncio.sleep(0)
            assert set((await s.scalars(select(User.tenant_id))).all()) == {scope.org_id}
            assert s.info["tenant_scope"] == scope

    await asyncio.gather(*(job(scope) for scope in scopes * 4))
