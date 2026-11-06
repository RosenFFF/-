import os
from io import StringIO

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from alembic import command
from app.db.base import Base, Database
from app.db.models import Tenant


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
async def test_initial_migration_schema_parity_idempotence_and_roundtrip(tmp_path, dialect):
    url = f"sqlite+aiosqlite:///{tmp_path}/roundtrip.db" if dialect == "sqlite" else os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("explicit disposable TEST_POSTGRES_URL not provided")
    if dialect == "postgresql":
        if os.environ.get("TEST_POSTGRES_DISPOSABLE") != "1":
            pytest.skip("TEST_POSTGRES_DISPOSABLE=1 required; never target shared databases")
        target = make_url(url)
        assert (target.database or "").startswith("st143_m2_test_"), "disposable DB name prefix required"
        assert target.host in (None, "", "127.0.0.1", "localhost", "::1"), "only local disposable DB permitted"
        assert not target.query.get("host") or str(target.query["host"]).startswith("/"), "Unix socket host required"
    db = Database(url)
    try:
        with pytest.raises(RuntimeError, match="migration required"):
            await db.check_migrated()
        await db.migrate()
        await db.check_migrated()
        await db.migrate()
        async with db.engine.begin() as c:
            diff = await c.run_sync(lambda conn: compare_metadata(MigrationContext.configure(conn), Base.metadata))
            assert diff == []
            tables = await c.run_sync(lambda conn: inspect(conn).get_table_names())
            assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
            await c.execute(Tenant.__table__.insert().values(id="migration-sentinel", name="synthetic"))
        await db.migrate()
        async with db.engine.begin() as c:
            assert (
                await c.execute(text("SELECT name FROM tenants WHERE id='migration-sentinel'"))
            ).scalar() == "synthetic"

            def down(conn):
                cfg = db.migration_config()
                cfg.attributes["connection"] = conn
                command.downgrade(cfg, "base")

            await c.run_sync(down)
            assert await c.run_sync(lambda conn: inspect(conn).get_table_names()) == ["alembic_version"]
        await db.migrate()
        await db.check_migrated()
    finally:
        await db.dispose()


async def test_legacy_adoption_only_identical_schema_preserves_rows(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/legacy.db")
    try:
        with pytest.raises(RuntimeError, match="differs"):
            await db.adopt_legacy_schema()
        async with db.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)  # Represents pre-M2 complete legacy schema, test-only.
            await c.execute(Tenant.__table__.insert().values(id="legacy-sentinel", name="synthetic"))
        await db.adopt_legacy_schema()
        await db.check_migrated()
        async with db.engine.connect() as c:
            assert (await c.execute(text("SELECT name FROM tenants"))).scalar() == "synthetic"
        with pytest.raises(RuntimeError, match="already versioned"):
            await db.adopt_legacy_schema()
    finally:
        await db.dispose()


def test_postgres_offline_sql_has_frozen_all_tables_jsonb_and_sequence():
    db = Database
    cfg = db.migration_config()
    cfg.attributes["database_url"] = "postgresql+asyncpg://unused/unused"
    cfg.output_buffer = StringIO()
    command.upgrade(cfg, "head", sql=True)
    sql = cfg.output_buffer.getvalue()
    assert "BIGSERIAL" in sql and "JSONB" in sql
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table}" in sql


async def test_legacy_adoption_rejects_primary_key_drift(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/wrong-pk.db")
    try:
        async with db.engine.begin() as c:
            await c.execute(text("CREATE TABLE tenants (id VARCHAR(36) NOT NULL, name VARCHAR(128) NOT NULL)"))
            await c.run_sync(Base.metadata.create_all)
        with pytest.raises(RuntimeError, match="differs"):
            await db.adopt_legacy_schema()
    finally:
        await db.dispose()
