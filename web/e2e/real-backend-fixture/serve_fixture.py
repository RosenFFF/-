"""Real-backend fixture for the frontend demo-ready e2e.

Serves backend code from a checkout at a437305 (BACKEND_DIR) on isolated
SQLite + fakeredis STAND-INS (not Postgres/Redis). The tenant gate stays ON:
existence check uses maintenance_sessionmaker, seeding uses the official
tests.conftest._seed (tenant_session). No credentials live in this file;
JWT_SECRET / DATA_KEK are generated per run into FIXTURE_STATE_DIR/.env (0600).
"""
from __future__ import annotations

import base64
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import fakeredis.aioredis
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import User
from app.main import create_app
from tests.conftest import _seed

state = Path(
    os.environ.get("FIXTURE_STATE_DIR") or Path(tempfile.gettempdir()) / "st143-real-fixture"
).resolve()
state.mkdir(parents=True, exist_ok=True)
env = state / ".env"
if not env.exists():
    with os.fdopen(os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write(
            f"JWT_SECRET={secrets.token_urlsafe(48)}\n"
            f"DATA_KEK={base64.b64encode(os.urandom(32)).decode()}\n"
        )

db_path = state / "integration.db"
if os.environ.get("M2_FRESH") == "1" and db_path.exists():
    db_path.unlink()

settings = Settings(
    _env_file=env,
    env="test",
    task_mode="inline",
    demo_mode=True,
    database_url=f"sqlite+aiosqlite:///{db_path}",
    redis_url="redis://unused",
    storage_dir=state / "storage",
    cookie_secure=True,
    cors_origins=["https://localhost:5173"],
    rl_default_per_min=int(os.environ.get("FIXTURE_RL_DEFAULT_PER_MIN", "2")),
    rl_login_per_min=60,
    rl_auth_per_min=120,
    llm_provider_chain=["deepseek", "qwen", "ollama"],
    ollama_base_url=os.environ.get("FIXTURE_OLLAMA_URL", "http://127.0.0.1:11434"),
    deepseek_api_key=None,
    qwen_api_key=None,
)
app = create_app(settings, redis=fakeredis.aioredis.FakeRedis())
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        # No unscoped COUNT on the business sessionmaker; tenant gate untouched.
        async with application.state.db.maintenance_sessionmaker() as s:
            exists = (await s.execute(select(User.id).limit(1))).first()
        if exists is None:
            await _seed(application)
        yield


app.router.lifespan_context = lifespan
