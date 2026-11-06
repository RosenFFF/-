from __future__ import annotations

import base64
import os
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
