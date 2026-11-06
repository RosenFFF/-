"""Offline DDL/session/role tests only. None of these are live RLS acceptance."""

import importlib.util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from alembic import command
from app.db.base import Base, Database
from app.db.tenant import TenantScope, _set_scope, bind_scope, check_application_role, scope_values, set_local_scope

ORG = "00000000-0000-4000-8000-000000000001"
USER = "00000000-0000-4000-8000-000000000002"


def ddl(dialect, down=False):
    cfg = Database.migration_config()
    cfg.attributes["database_url"] = dialect + "://unused/unused"
    cfg.output_buffer = StringIO()
    if down:
        command.downgrade(cfg, "0002_m2_tenant_rls:0001_m2_initial", sql=True)
    else:
        command.upgrade(cfg, "head", sql=True)
    return cfg.output_buffer.getvalue()


def test_offline_pg_rls_all_tables_forced_using_check_and_restrictive_guard():
    sql = ddl("postgresql+asyncpg")
    for name in Base.metadata.tables:
        assert f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY tenant_guard ON "{name}" AS RESTRICTIVE FOR ALL USING (' in sql
        assert f'CREATE POLICY tenant_allow ON "{name}" FOR ALL USING (true) WITH CHECK (true)' in sql
    assert sql.count("CREATE POLICY tenant_guard") == 11
    assert sql.count("WITH CHECK (") == 22
    assert "NULLIF(current_setting('app.current_org_id', true), '')" in sql
    assert "SECURITY DEFINER" not in sql and "BYPASSRLS" not in sql
    assert "CREATE ROLE" not in sql  # Cluster logins are operator provisioning, never app migration side effects.
    down = ddl("postgresql+asyncpg", down=True)
    for name in Base.metadata.tables:
        assert f'DROP POLICY tenant_guard ON "{name}"' in down
        assert f'ALTER TABLE "{name}" DISABLE ROW LEVEL SECURITY' in down
    assert "DROP TABLE" not in down


def test_frozen_rls_covers_parent_children_owner_and_null_audit():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0002_m2_tenant_rls.py"
    spec = importlib.util.spec_from_file_location("frozen_rls_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predicates = module.policies()
    assert set(predicates) == set(Base.metadata.tables)
    for name in ["documents", "reviews"]:
        assert "owner_id = " in predicates[name] and "('admin', 'auditor')" in predicates[name]
        assert f"u.tenant_id = {name}.tenant_id" in predicates[name]
    for name in ["ocr_pages", "document_fields", "review_documents", "chat_messages", "demo_tamper_backups"]:
        assert "EXISTS" in predicates[name]
    assert "tenant_id = NULLIF" in predicates["audit_logs"] and "IS NULL" not in predicates["audit_logs"]
    assert "user_id = NULLIF" in predicates["refresh_tokens"]


def test_sqlite_rls_is_explicitly_not_applicable():
    sql = ddl("sqlite+aiosqlite")
    down = ddl("sqlite+aiosqlite", down=True)
    for output in [sql, down]:
        assert "ROW LEVEL SECURITY" not in output and "CREATE POLICY" not in output
    assert "0002_m2_tenant_rls" in sql


@pytest.mark.parametrize(
    "org,user,role",
    [
        ("", USER, "admin"),
        (ORG, "", "reviewer"),
        ("not-a-uuid", USER, "admin"),
        (ORG, USER, "superuser"),
        (ORG, USER, "worker"),
        (ORG, USER, "ADMIN"),
    ],
)
def test_invalid_or_missing_context_rejected(org, user, role):
    with pytest.raises(ValueError):
        TenantScope(org, user, role)


async def test_fresh_session_scope_immutable_and_sqlite_does_not_emulate_rls(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/scope.db")
    scope = TenantScope(ORG, USER, "reviewer")
    try:
        async with db.tenant_session(scope) as s:
            assert s.info["tenant_scope"] == scope
            assert (await s.execute(text("SELECT 1"))).scalar() == 1
            await s.commit()
            with pytest.raises(RuntimeError, match="fresh session"):
                bind_scope(s, scope)
        async with db.sessionmaker() as s:
            await s.execute(text("SELECT 1"))
            with pytest.raises(RuntimeError, match="fresh session"):
                bind_scope(s, scope)
        await db.check_runtime_access()  # SQLite only; no PG safety claims.
    finally:
        await db.dispose()


def test_orm_transaction_hook_uses_local_bound_parameters_and_explicit_empty_scope():
    connection = MagicMock(dialect=SimpleNamespace(name="postgresql"))
    initial = TenantScope(ORG, USER, "admin")
    for scope in [initial, None]:
        _set_scope(SimpleNamespace(info={"tenant_scope": scope}), None, connection)
        statement, values = connection.execute.call_args.args
        assert str(statement).count(", true)") == 3
        assert values == scope_values(scope)
        assert ORG not in str(statement)
    assert scope_values(None) == {"org": "", "user": "", "role": ""}


async def test_raw_set_scope_requires_begin_and_does_not_open_a_hidden_transaction():
    connection = MagicMock(dialect=SimpleNamespace(name="postgresql"))
    connection.in_transaction.return_value = False
    connection.execute = AsyncMock()
    with pytest.raises(RuntimeError, match="BEGIN required"):
        await set_local_scope(connection, TenantScope(ORG, USER, "admin"))
    connection.execute.assert_not_awaited()
    connection.in_transaction.return_value = True
    await set_local_scope(connection, None)
    assert connection.execute.call_args.args[1] == scope_values(None)


@pytest.mark.parametrize(
    "flags",
    [
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
    ],
)
async def test_application_role_rejects_admin_attributes_offline(flags):
    result = MagicMock()
    result.one.return_value = flags
    connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), execute=AsyncMock(return_value=result))
    with pytest.raises(RuntimeError, match="NOSUPERUSER NOBYPASSRLS"):
        await check_application_role(connection)


@pytest.mark.parametrize("dangerous,owns", [(True, False), (False, True), (False, False)])
async def test_application_role_checks_membership_and_table_schema_ownership_offline(dangerous, owns):
    result = MagicMock()
    result.one.return_value = (False, False, False, False)
    connection = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        execute=AsyncMock(return_value=result),
        scalar=AsyncMock(side_effect=[dangerous, owns]),
    )
    if dangerous or owns:
        with pytest.raises(RuntimeError, match="member of a privileged|must not own"):
            await check_application_role(connection)
    else:
        await check_application_role(connection)


async def test_legacy_adoption_executes_later_migrations_instead_of_blind_head_stamp(tmp_path, monkeypatch):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/adopt.db")
    try:
        async with db.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)  # Test-only legacy database.
        real_stamp, real_upgrade = command.stamp, command.upgrade
        calls = []

        def stamp(cfg, revision):
            calls.append(("stamp", revision))
            real_stamp(cfg, revision)

        def upgrade(cfg, revision):
            calls.append(("upgrade", revision))
            real_upgrade(cfg, revision)

        monkeypatch.setattr(command, "stamp", stamp)
        monkeypatch.setattr(command, "upgrade", upgrade)
        await db.adopt_legacy_schema()
        assert calls == [("stamp", "0001_m2_initial"), ("upgrade", "head")]
        await db.check_migrated()
    finally:
        await db.dispose()


async def test_postgres_api_rollout_gate_is_explicit_not_a_fake_passing_api(monkeypatch, tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/gate.db")
    db.is_postgres = True
    monkeypatch.setattr("app.db.base.check_application_role", AsyncMock())
    try:
        with pytest.raises(RuntimeError, match="deployment blocked: pre-authentication"):
            await db.check_runtime_access()
    finally:
        await db.dispose()


async def test_pg_fixture_seed_shapes_compile_and_roundtrip_on_sqlite_only(tmp_path):
    # Data-shape smoke test, deliberately NOT RLS/PG acceptance. Catches bad defaults/PKs
    # before a real PG becomes available; SQLite has no tenant filtering here.
    from .test_m2_postgres_rls import seed, where_pk

    db = Database(f"sqlite+aiosqlite:///{tmp_path}/fixture-shape.db")
    try:
        await db.migrate()
        scopes, rows = await seed(db)
        assert len(scopes) == 2
        async with db.engine.begin() as c:
            for data in rows:
                assert set(data) == set(Base.metadata.tables)
                for name, row in data.items():
                    table = Base.metadata.tables[name]
                    result = await c.execute(table.select().where(where_pk(name, row)))
                    assert len(result.all()) == 1
                    column = next(iter(table.primary_key))
                    changed = await c.execute(
                        table.update().where(where_pk(name, row)).values({column.name: row[column.name]})
                    )
                    assert changed.rowcount == 1
            for data in rows:
                for name, row in reversed(data.items()):
                    result = await c.execute(Base.metadata.tables[name].delete().where(where_pk(name, row)))
                    assert result.rowcount == 1
    finally:
        await db.dispose()
