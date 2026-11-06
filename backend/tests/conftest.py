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
