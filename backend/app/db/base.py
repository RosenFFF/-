from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from alembic import command
from app.db.tenant import TenantScope, TenantSession, bind_scope, check_application_role


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(
            self.engine, expire_on_commit=False, sync_session_class=TenantSession, info={"scope_required": True}
        )
        # Explicit operator/test-only capability. Never inject this into request/job code.
        # It does not bypass PostgreSQL RLS; missing GUCs remain fail-closed there.
        self.maintenance_sessionmaker = async_sessionmaker(
            self.engine, expire_on_commit=False, sync_session_class=TenantSession, info={"scope_required": False}
        )
        self.is_postgres = url.startswith("postgresql")

    @staticmethod
    def migration_config() -> Config:
        root = Path(__file__).resolve().parents[2]
        return Config(str(root / "alembic.ini"))

    async def migrate(self) -> None:
        """Explicit migration command; startup never races DDL among production workers."""

        def upgrade(connection):
            config = self.migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with self.engine.begin() as connection:
            await connection.run_sync(upgrade)

    async def adopt_legacy_schema(self) -> None:
        """Stamp only a complete, identical legacy schema; no blind stamp or auto-DDL."""
        from app.db import models  # noqa: F401

        def adopt(connection):
            context = MigrationContext.configure(connection)
            if context.get_current_heads() or compare_metadata(context, Base.metadata):
                raise RuntimeError("Legacy schema differs or is already versioned; manual migration review required")
            inspector = inspect(connection)
            for table in Base.metadata.sorted_tables:
                actual = inspector.get_pk_constraint(table.name)["constrained_columns"]
                expected = [column.name for column in table.primary_key]
                if actual != expected:
                    raise RuntimeError("Legacy schema primary key differs; manual migration review required")
            config = self.migration_config()
            config.attributes["connection"] = connection
            # Schema parity does NOT prove that PostgreSQL policies exist. Stamp only
            # the legacy schema revision, then actually execute later migrations.
            command.stamp(config, "0001_m2_initial")
            command.upgrade(config, "head")

        async with self.engine.begin() as connection:
            await connection.run_sync(adopt)

    async def check_migrated(self) -> None:
        def check(connection):
            current = MigrationContext.configure(connection).get_current_heads()
            heads = ScriptDirectory.from_config(self.migration_config()).get_heads()
            if set(current) != set(heads):
                raise RuntimeError("Database migration required: run alembic upgrade head before startup")

        async with self.engine.connect() as connection:
            await connection.run_sync(check)

    async def check_runtime_access(self) -> None:
        if not self.is_postgres:
            return
        async with self.engine.connect() as connection:
            await check_application_role(connection)
        # Do not silently ship a database-only milestone as an operational API.
        # In particular, a pre-auth lookup and the existing shared audit chain
        # cannot safely use an all-tenants GUC to evade the new restrictions.
        raise RuntimeError(
            "PostgreSQL RLS deployment blocked: pre-authentication/audit/worker tenant integration "
            "requires real non-owner PostgreSQL acceptance; SQLite/fakeredis tests do not release this gate"
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s:
            s.info["scope_required"] = True
            yield s

    @asynccontextmanager
    async def tenant_session(self, scope: TenantScope) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s:
            bind_scope(s, scope)
            s.info["scope_required"] = True
            yield s

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def login_candidate(self, username: str):
        """Only pre-auth capability: exact globally-unique username, no business query.

        A fresh transaction sets empty tenant scope BEFORE the narrow lookup GUC.
        It returns no data to callers over HTTP. Commit/rollback clears every GUC.
        """
        from app.db.models import User
        from app.db.tenant import SCOPE_SQL, scope_values

        async with self.engine.begin() as c:
            if self.is_postgres:
                await c.execute(SCOPE_SQL, scope_values(None))
                await c.execute(
                    text(
                        "SELECT set_config('app.audit_platform', '', true), "
                        "set_config('app.auth_username', :username, true)"
                    ),
                    {"username": username},
                )
            return (
                (await c.execute(select(User.__table__).where(User.username == username).limit(1))).mappings().first()
            )

    @asynccontextmanager
    async def job_session(self, context: dict | None) -> AsyncIterator[AsyncSession]:
        """Queue payload comes only from an authenticated enqueue; recheck at execution.

        Missing/legacy jobs fail closed, never discover a tenant from the resource ID.
        No process-global/ContextVar identity survives a job or a connection checkout.
        """
        from app.db.models import User

        if not isinstance(context, dict) or set(context) != {"org_id", "user_id", "role"}:
            raise ValueError("verified job tenant context required")
        scope = TenantScope(**context)
        async with self.tenant_session(scope) as s:
            user = await s.get(User, scope.user_id)
            if user is None or user.tenant_id != scope.org_id or user.role != scope.role or user.disabled:
                raise ValueError("job tenant identity mismatch or revoked")
            yield s
