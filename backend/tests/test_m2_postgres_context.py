"""Real non-owner PostgreSQL follow-up tests; skips are NOT passing evidence."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit.service import Actor, AuditService
from app.db.base import Base
from app.db.models import AuditLog, User, uid
from app.db.tenant import set_local_scope

from .test_m2_postgres_rls import rls_error, seed


@pytest.fixture
async def rls_data(postgres_rls_db, postgres_rls_owner):
    scopes, rows = await seed(postgres_rls_owner)
    return postgres_rls_db, postgres_rls_owner, scopes, rows


async def test_pg_auth_exact_username_capability_never_opens_business_rls(rls_data):
    db, _, scopes, rows = rls_data
    row = await db.login_candidate(rows[0]["users"]["username"])
    assert row["id"] == scopes[0].user_id
    async with db.engine.begin() as c:
        await set_local_scope(c, None)
        await c.execute(
            text("SELECT set_config('app.auth_username', :name, true)"), {"name": rows[0]["users"]["username"]}
        )
        assert (await c.execute(text("SELECT id FROM users"))).scalars().all() == [scopes[0].user_id]
        for table in ("documents", "reviews", "refresh_tokens", "audit_logs", "chat_messages"):
            assert (await c.execute(Base.metadata.tables[table].select())).all() == []
    # Capability is LOCAL; even the same physical pooled connection must lose it.
    async with db.engine.begin() as c:
        for setting in (
            "app.current_org_id",
            "app.current_user_id",
            "app.current_role",
            "app.auth_username",
            "app.audit_platform",
        ):
            assert (
                await c.execute(text("SELECT nullif(current_setting(:key, true), '')"), {"key": setting})
            ).scalar() is None
        assert (await c.execute(text("SELECT * FROM users"))).all() == []


@pytest.mark.parametrize("verb", ["UPDATE users SET failed_logins=10", "DELETE FROM users"])
async def test_pg_auth_lookup_context_cannot_mutate_credentials(rls_data, verb):
    db, _, _, rows = rls_data
    async with db.engine.begin() as c:
        await set_local_scope(c, None)
        await c.execute(
            text("SELECT set_config('app.auth_username', :name, true)"), {"name": rows[0]["users"]["username"]}
        )
        assert (await c.execute(text(verb))).rowcount == 0


async def test_pg_audit_writer_and_verifier_use_only_their_tenant_chain(rls_data):
    db, _, scopes, rows = rls_data
    # Isolated synthetic seed hashes were not valid audit evidence. Remove only
    # those fixture rows under their own tenant scopes, then test real AuditService.
    for scope in scopes:
        async with db.engine.begin() as c:
            await set_local_scope(c, scope)
            await c.execute(text("DELETE FROM audit_logs"))
    audit = AuditService(db)
    for scope, data in zip(scopes * 2, rows * 2, strict=True):
        await audit.record(
            "test.context", "success", actor=Actor(scope.user_id, data["users"]["username"], scope.role, scope.org_id)
        )
    await audit.record("test.platform", "blocked")
    for scope in scopes:
        result = await audit.verify(scope)
        assert result["valid"] and result["checked"] == 2
        async with db.tenant_session(scope) as s:
            assert {r.tenant_id for r in (await s.scalars(select(AuditLog))).all()} == {scope.org_id}
    async with db.engine.begin() as c:
        assert (await c.execute(text("SELECT * FROM audit_logs"))).all() == []


async def test_pg_platform_audit_capability_does_not_open_users_or_tenant_events(rls_data):
    db, _, scopes, _ = rls_data
    await AuditService(db).record("test.platform", "blocked")
    async with db.engine.begin() as c:
        await set_local_scope(c, None)
        await c.execute(text("SELECT set_config('app.audit_platform', '1', true)"))
        assert (await c.execute(text("SELECT tenant_id FROM audit_logs"))).scalars().all() == [None]
        assert (await c.execute(select(User))).all() == []
        with pytest.raises(DBAPIError) as exc:
            await c.execute(
                AuditLog.__table__.insert().values(
                    id=uid(),
                    tenant_id=scopes[0].org_id,
                    actor_id=scopes[0].user_id,
                    action="test.invalid",
                    result="failed",
                    request_id="test",
                    hash="0" * 64,
                )
            )
        rls_error(exc)
        await c.rollback()
