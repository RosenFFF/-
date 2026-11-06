"""REAL PostgreSQL-only enforcement. Skipped tests are never RLS evidence.

Runs with two local logins: migration owner and a distinct NOSUPERUSER,
NOBYPASSRLS, non-table-owner runtime role. No SQLite/Redis/AI substitutes here.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.db.base import Base
from app.db.models import Tenant, uid
from app.db.tenant import TenantScope, bind_scope, check_application_role, set_local_scope

TABLES = tuple(Base.metadata.tables)


async def seed(owner):
    scopes = [TenantScope(uid(), uid(), "admin") for _ in range(2)]
    rows = []
    for scope in scopes:
        document, review, audit = uid(), uid(), uid()
        values = {
            "tenants": {"id": scope.org_id, "name": "synthetic"},
            "users": {
                "id": scope.user_id,
                "tenant_id": scope.org_id,
                "username": uid(),
                "password_hash": "disabled-synthetic-fixture",
                "role": "admin",
            },
            "documents": {
                "id": document,
                "tenant_id": scope.org_id,
                "owner_id": scope.user_id,
                "filename": "synthetic.png",
                "mime": "image/png",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "wrapped_dek": "synthetic-not-used",
                "expire_at": datetime.now(UTC) + timedelta(days=1),
            },
            "reviews": {
                "id": review,
                "tenant_id": scope.org_id,
                "owner_id": scope.user_id,
                "document_ids": [document],
                "destination_country": "VN",
            },
            "refresh_tokens": {
                "id": uid(),
                "user_id": scope.user_id,
                "family_id": uid(),
                "token_hash": uid() + uid()[:28],
                "expires_at": datetime.now(UTC) + timedelta(days=1),
            },
            "ocr_pages": {
                "id": uid(),
                "document_id": document,
                "page": 1,
                "blocks": [],
                "engine": "synthetic",
                "duration_ms": 0,
            },
            "document_fields": {"document_id": document, "source": "rule", "fields": {}},
            "review_documents": {
                "review_id": review,
                "document_id": document,
                "version": 1,
                "fields_snapshot": {},
                "doc_type": "unknown",
            },
            "chat_messages": {
                "id": uid(),
                "review_id": review,
                "tenant_id": scope.org_id,
                "role": "user",
                "content": "synthetic",
                "language": "en",
            },
            "audit_logs": {
                "id": audit,
                "tenant_id": scope.org_id,
                "actor_id": scope.user_id,
                "action": "test.synthetic",
                "result": "success",
                "request_id": uid(),
                "hash": "0" * 64,
            },
            "demo_tamper_backups": {"log_id": audit, "original_detail": {}},
        }
        async with owner.engine.begin() as c:
            await set_local_scope(c, scope)
            # Explicit dependency order; no create_all, superuser seed or disabled RLS.
            for name, value in values.items():
                table = Base.metadata.tables[name]
                result = await c.execute(table.insert().values(**value).returning(table))
                values[name] = dict(result.mappings().one())
        rows.append(values)
    return scopes, rows


@pytest.fixture
async def rls_data(postgres_rls_db, postgres_rls_owner):
    scopes, rows = await seed(postgres_rls_owner)
    return postgres_rls_db, postgres_rls_owner, scopes, rows


def where_pk(name, row):
    table = Base.metadata.tables[name]
    conditions = [col == row[col.name] for col in table.primary_key]
    from sqlalchemy import and_

    return and_(*conditions)


def rls_error(exc):
    # Do not accept duplicate keys, missing table grants, or FK failures as RLS.
    assert exc.value.orig.sqlstate == "42501"
    assert "row-level security" in str(exc.value.orig).lower()


async def test_pg_rls_catalog_all_business_tables_forced_and_restrictive(postgres_rls_owner):
    async with postgres_rls_owner.engine.connect() as c:
        role = (await c.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"))).one()
        assert not role.rolsuper and not role.rolbypassrls
        tables = (
            await c.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relnamespace=current_schema()::regnamespace AND relkind='r' AND relname <> 'alembic_version'"
                )
            )
        ).all()
        assert {r.relname for r in tables} == set(TABLES)
        assert all(r.relrowsecurity and r.relforcerowsecurity for r in tables)
        policies = (
            await c.execute(
                text(
                    "SELECT tablename, policyname, permissive, cmd, qual, with_check FROM pg_policies "
                    "WHERE schemaname=current_schema()"
                )
            )
        ).all()
        assert len(policies) == 2 * len(TABLES) + 3
        for policy in policies:
            assert policy.cmd in {"ALL", "SELECT", "INSERT", "UPDATE", "DELETE"}
            assert policy.qual or policy.with_check
            if policy.policyname == "tenant_guard":
                assert policy.permissive == "RESTRICTIVE"
        assert (
            await c.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one() == "0003_m2_auth_audit_context"


async def test_pg_rls_revision_downgrade_upgrade_preserves_rows(postgres_rls_owner):
    owner = postgres_rls_owner
    scopes, _ = await seed(owner)
    async with owner.engine.begin() as c:

        def down(conn):
            cfg = owner.migration_config()
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "0001_m2_initial")

        await c.run_sync(down)
        assert (await c.execute(text("SELECT count(*) FROM tenants"))).scalar_one() == 2
        assert not (
            await c.execute(
                text(
                    "SELECT bool_or(relrowsecurity OR relforcerowsecurity) FROM pg_class "
                    "WHERE relnamespace=current_schema()::regnamespace AND relkind='r'"
                )
            )
        ).scalar_one()
        assert (
            await c.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname=current_schema()"))
        ).scalar_one() == 0
    await owner.migrate()
    await owner.migrate()
    async with owner.engine.begin() as c:
        await set_local_scope(c, scopes[0])
        assert (await c.execute(text("SELECT id FROM tenants"))).scalars().all() == [scopes[0].org_id]


@pytest.mark.parametrize("name", TABLES)
async def test_pg_rls_direct_select_is_tenant_scoped_without_where(rls_data, name):
    db, _, scopes, _ = rls_data
    for scope in scopes:
        async with db.engine.begin() as c:
            await check_application_role(c)
            await set_local_scope(c, scope)
            # Intentionally no application WHERE clause.
            assert len((await c.execute(Base.metadata.tables[name].select())).all()) == 1
    async with db.engine.begin() as c:
        assert (await c.execute(Base.metadata.tables[name].select())).all() == []


@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
@pytest.mark.parametrize("name", TABLES)
async def test_pg_rls_foreign_raw_writes_denied(rls_data, name, operation):
    db, _, scopes, rows = rls_data
    table = Base.metadata.tables[name]
    async with db.engine.connect() as c:
        await c.begin()
        await set_local_scope(c, scopes[1])
        if operation == "insert":
            with pytest.raises(DBAPIError) as exc:
                await c.execute(table.insert().values(**rows[0][name]))
            rls_error(exc)
        elif operation == "update":
            # Existing foreign rows are invisible: UPDATE/DELETE affect zero, not necessarily ERROR.
            column = next(iter(table.primary_key))
            result = await c.execute(
                table.update().where(where_pk(name, rows[0][name])).values({column.name: rows[0][name][column.name]})
            )
            assert result.rowcount == 0
        else:
            result = await c.execute(table.delete().where(where_pk(name, rows[0][name])))
            assert result.rowcount == 0
        await c.rollback()
    # Confirm the row survived using its correct tenant context.
    async with db.engine.begin() as c:
        await set_local_scope(c, scopes[0])
        assert len((await c.execute(table.select())).all()) == 1


@pytest.mark.parametrize(
    "name,column",
    [
        ("users", "tenant_id"),
        ("documents", "tenant_id"),
        ("reviews", "tenant_id"),
        ("chat_messages", "tenant_id"),
        ("audit_logs", "tenant_id"),
        ("documents", "owner_id"),
        ("reviews", "owner_id"),
        ("refresh_tokens", "user_id"),
        ("ocr_pages", "document_id"),
        ("document_fields", "document_id"),
        ("document_fields", "updated_by"),
        ("review_documents", "review_id"),
        ("review_documents", "document_id"),
        ("chat_messages", "review_id"),
        ("demo_tamper_backups", "log_id"),
    ],
)
async def test_pg_rls_with_check_blocks_reparent_and_tenant_transfer(rls_data, name, column):
    db, _, scopes, rows = rls_data
    value = scopes[1].user_id if column == "updated_by" else rows[1][name][column]
    table = Base.metadata.tables[name]
    async with db.engine.connect() as c:
        await c.begin()
        await set_local_scope(c, scopes[0])
        with pytest.raises(DBAPIError) as exc:
            await c.execute(table.update().where(where_pk(name, rows[0][name])).values({column: value}))
        rls_error(exc)
        await c.rollback()


async def test_pg_rls_missing_context_and_null_tenant_deny_writes(rls_data):
    db, _, scopes, rows = rls_data
    async with db.engine.begin() as c:
        for name in TABLES:
            assert (await c.execute(Base.metadata.tables[name].select())).all() == []
    for scope in [None, scopes[0]]:
        async with db.engine.connect() as c:
            await c.begin()
            await set_local_scope(c, scope)
            values = dict(rows[0]["audit_logs"], id=uid(), tenant_id=None)
            with pytest.raises(DBAPIError) as exc:
                await c.execute(Base.metadata.tables["audit_logs"].insert().values(**values))
            rls_error(exc)
            await c.rollback()
    async with db.engine.connect() as c:
        await c.begin()
        with pytest.raises(DBAPIError) as exc:
            await c.execute(Base.metadata.tables["tenants"].insert().values(id=uid(), name="unscoped"))
        rls_error(exc)
        await c.rollback()


async def test_pg_rls_same_tenant_reviewer_owner_and_admin_auditor_scope(rls_data):
    db, owner, scopes, rows = rls_data
    other_id = uid()
    async with owner.engine.begin() as c:
        await set_local_scope(c, scopes[0])
        await c.execute(
            Base.metadata.tables["users"]
            .insert()
            .values(
                id=other_id,
                tenant_id=scopes[0].org_id,
                username=uid(),
                password_hash="disabled-fixture",
                role="reviewer",
            )
        )
    for role, actor, expected in [
        ("reviewer", other_id, 0),
        ("reviewer", scopes[0].user_id, 1),
        ("admin", other_id, 1),
        ("auditor", other_id, 1),
    ]:
        async with db.engine.begin() as c:
            await set_local_scope(c, TenantScope(scopes[0].org_id, actor, role))
            for name in ["documents", "reviews", "ocr_pages", "document_fields", "review_documents", "chat_messages"]:
                assert len((await c.execute(Base.metadata.tables[name].select())).all()) == expected
    # Scope is not inferred from foreign IDs; parent RLS still applies.
    assert rows[0]["documents"]["owner_id"] != other_id


@pytest.mark.parametrize("ending", ["commit", "rollback", "close", "exception"])
async def test_pg_rls_single_connection_pool_clears_context(rls_data, ending):
    db, _, scopes, _ = rls_data
    pid = None
    for scope in [scopes[0], scopes[1], None, scopes[0], None]:
        try:
            async with db.engine.connect() as c:
                await c.begin()
                await set_local_scope(c, scope)
                current_pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                pid = current_pid if pid is None else pid
                assert current_pid == pid
                actual = (await c.execute(text("SELECT id FROM tenants"))).scalars().all()
                assert actual == ([scope.org_id] if scope else [])
                if ending == "commit":
                    await c.commit()
                elif ending == "rollback":
                    await c.rollback()
                elif ending == "exception":
                    raise RuntimeError("synthetic request failure")
                # close: exiting with an active transaction must rollback too.
        except RuntimeError as exc:
            assert ending == "exception" and str(exc) == "synthetic request failure"
        async with db.engine.connect() as c:
            for name in ["org_id", "user_id", "role"]:
                setting = "app.current_" + name
                assert (
                    await c.execute(text("SELECT nullif(current_setting(:name, true), '')"), {"name": setting})
                ).scalar() is None
            assert (await c.execute(text("SELECT id FROM tenants"))).all() == []


async def test_pg_rls_orm_scopes_reapply_after_commit_rollback_and_concurrent_requests(rls_data):
    db, _, scopes, _ = rls_data
    for scope in scopes:
        async with db.tenant_session(scope) as s:
            for ending in [s.commit, s.rollback, s.commit]:
                assert (await s.execute(select(Tenant.id))).scalars().all() == [scope.org_id]
                await ending()
            with pytest.raises(RuntimeError, match="fresh session"):
                bind_scope(s, scopes[1])

    async def request(scope):
        async with db.tenant_session(scope) as s:
            assert (await s.execute(select(Tenant.id))).scalars().all() == [scope.org_id]
            await asyncio.sleep(0)
            await s.commit()

    await asyncio.gather(*(request(scope) for scope in scopes * 3))
    async with db.maintenance_sessionmaker() as s:
        assert (await s.execute(select(Tenant.id))).all() == []


async def test_pg_rls_owner_ddl_permission_is_not_runtime_safe(postgres_rls_owner):
    async with postgres_rls_owner.engine.connect() as c:
        with pytest.raises(RuntimeError, match="must not own"):
            await check_application_role(c)


async def test_pg_rls_unintegrated_api_startup_is_explicitly_blocked(postgres_rls_db):
    with pytest.raises(RuntimeError, match="deployment blocked"):
        await postgres_rls_db.check_runtime_access()


async def test_pg_rls_same_tenant_application_role_can_insert_update_delete_all_tables(postgres_rls_db):
    db = postgres_rls_db
    scopes, rows = await seed(db)  # All INSERTs now use the actual non-owner application login.
    for scope, data in zip(scopes, rows, strict=True):
        async with db.engine.begin() as c:
            await set_local_scope(c, scope)
            for name, row in data.items():
                table = Base.metadata.tables[name]
                column = next(iter(table.primary_key))
                result = await c.execute(
                    table.update().where(where_pk(name, row)).values({column.name: row[column.name]})
                )
                assert result.rowcount == 1
            for name, row in reversed(data.items()):
                result = await c.execute(Base.metadata.tables[name].delete().where(where_pk(name, row)))
                assert result.rowcount == 1
