from __future__ import annotations

import base64
import os
import uuid
from collections.abc import AsyncIterator

import fakeredis.aioredis
import httpx
import pytest

from app.core.config import Settings
from app.db.models import Tenant, User
from app.main import create_app
from app.security.passwords import hash_password

PASSWORDS = {
    "admin": "admin-pass-123456",
    "reviewer": "reviewer-pass-123456",
    "reviewer2": "reviewer2-pass-123456",
    "auditor": "auditor-pass-123456",
}


def make_settings(tmp_path, **kw) -> Settings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = dict(
        env="test",
        demo_mode=True,
        task_mode="inline",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        redis_url="redis://unused",
        jwt_secret="t" * 48,
        data_kek=base64.b64encode(os.urandom(32)).decode(),
        storage_dir=tmp_path / "storage",
        cookie_secure=True,
        llm_provider_chain=["deepseek", "qwen"],
        deepseek_api_key=None,
        qwen_api_key=None,
    )
    base.update(kw)
    return Settings(_env_file=None, **base)


class Api:
    def __init__(self, app, settings: Settings) -> None:
        self.app, self.settings = app, settings

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="https://testserver",
            headers={"Origin": self.settings.cors_origins[0]},
        )

    async def login(self, username: str) -> httpx.AsyncClient:
        c = self.client()
        r = await c.post("/api/v1/auth/login", json={"username": username, "password": PASSWORDS[username]})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]
        return c


async def _seed(app) -> None:
    async with app.state.db.sessionmaker() as s:
        t = Tenant(name="t1")
        s.add(t)
        await s.flush()
        for name in PASSWORDS:
            role = "reviewer" if name.startswith("reviewer") else name
            s.add(User(tenant_id=t.id, username=name, password_hash=hash_password(PASSWORDS[name]), role=role))
        await s.commit()


@pytest.fixture
async def make_api(tmp_path):
    managers = []

    async def _make(**kw) -> Api:
        settings = make_settings(tmp_path / str(len(managers)), **kw)
        app = create_app(settings, redis=fakeredis.aioredis.FakeRedis())
        cm = app.router.lifespan_context(app)
        await cm.__aenter__()
        managers.append(cm)
        await _seed(app)
        return Api(app, settings)

    yield _make
    for cm in managers:
        await cm.__aexit__(None, None, None)


@pytest.fixture
async def api(make_api) -> AsyncIterator[Api]:
    yield await make_api()


@pytest.fixture
async def postgres_test_url(monkeypatch):
    """Real PG, random private schema, and fail-closed explicit disposable opt-in.

    The same configured role owns/migrates this schema and is used by the app.
    No database is dropped, no shared/public schema is cleared, no URL is logged.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db import base

    from .postgres import UnsafePostgresTarget, disposable_postgres_url

    try:
        url = disposable_postgres_url()
    except UnsafePostgresTarget as exc:
        pytest.fail(str(exc), pytrace=False)
    if url is None:
        pytest.skip("live PostgreSQL unavailable: inject a disposable local TEST_POSTGRES_URL or DATABASE_URL")
    schema = "st143_m2_test_" + uuid.uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    created = False
    try:
        try:
            async with admin.begin() as conn:
                role = (
                    await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"))
                ).one()
                if role.rolsuper or role.rolbypassrls:
                    pytest.fail("use a non-superuser NOBYPASSRLS acceptance role", pytrace=False)
                # Identifier is generated here from uuid hex, never a request/env value.
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                created = True
        except Exception:
            pytest.fail(
                "local disposable PostgreSQL unavailable or CREATE SCHEMA denied (connection withheld)", pytrace=False
            )

        def schema_engine(target, **kwargs):
            # Connection option only; this is not a DB/transport/query substitute.
            connect_args = kwargs.setdefault("connect_args", {})
            connect_args.setdefault("server_settings", {})["search_path"] = schema
            return create_async_engine(target, **kwargs)

        monkeypatch.setattr(base, "create_async_engine", schema_engine)
        yield url
    finally:
        try:
            if created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await admin.dispose()


@pytest.fixture
async def postgres_rls_owner(postgres_test_url):
    """Real isolated-schema migration owner; never bypasses RLS, even while seeding."""
    from app.db.base import Database

    db = Database(postgres_test_url)
    try:
        await db.migrate()
        yield db
    finally:
        await db.dispose()


@pytest.fixture
async def postgres_rls_db(postgres_rls_owner):
    """Separate non-owner application login. Never SET ROLE from a privileged session."""
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from app.db.base import Database
    from app.db.tenant import check_application_role

    from .postgres import UnsafePostgresTarget, disposable_postgres_url

    raw = os.environ.get("TEST_POSTGRES_APP_URL")
    if not raw:
        pytest.fail("TEST_POSTGRES_APP_URL required for real non-owner RLS application-role tests", pytrace=False)
    try:
        app_url = disposable_postgres_url({"TEST_POSTGRES_URL": raw, "TEST_POSTGRES_DISPOSABLE": "1"})
        owner_url = postgres_rls_owner.engine.url
        target = make_url(app_url)
        if (target.host, target.port, target.database, target.query) != (
            owner_url.host,
            owner_url.port,
            owner_url.database,
            owner_url.query,
        ) or target.username == owner_url.username:
            pytest.fail("application login must be separate, in the same disposable local database", pytrace=False)
    except UnsafePostgresTarget as exc:
        pytest.fail(str(exc), pytrace=False)
    db = Database(app_url)
    # One physical connection makes accidental cross-request GUC inheritance observable.
    await db.engine.dispose()
    from app.db import base

    db.engine = base.create_async_engine(app_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    db.sessionmaker.configure(bind=db.engine)
    try:
        async with db.engine.connect() as conn:
            role = (await conn.execute(text("SELECT current_user"))).scalar_one()
            # Check unsafe role attributes before granting any isolated-schema privilege.
            attrs = (
                await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                )
            ).one()
            if any(attrs):
                pytest.fail("application login has unsafe PostgreSQL role attributes", pytrace=False)
        async with postgres_rls_owner.engine.begin() as conn:
            schema = (await conn.execute(text("SELECT current_schema()"))).scalar_one()
            quote = conn.dialect.identifier_preparer.quote_identifier
            # Server-returned identifiers are quoted; privileges touch only the random schema.
            await conn.execute(text(f"GRANT USAGE ON SCHEMA {quote(schema)} TO {quote(role)}"))
            from app.db.base import Base

            tables = ", ".join(f"{quote(schema)}.{quote(name)}" for name in Base.metadata.tables)
            await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tables} TO {quote(role)}"))
            await conn.execute(text(f"GRANT SELECT ON TABLE {quote(schema)}.alembic_version TO {quote(role)}"))
            await conn.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {quote(schema)} TO {quote(role)}"))
        async with db.engine.connect() as conn:
            await check_application_role(conn)
        yield db
    finally:
        await db.dispose()
