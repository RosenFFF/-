"""Test-only server: real FastAPI/RapidOCR, isolated SQLite + fake Redis.
Run via PYTHONPATH=backend uvicorn integration_fixture:app --app-dir web/scripts.
Never use this fixture, its synthetic accounts or its Redis in a deployment.
"""
import base64
import json
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import fakeredis.aioredis
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import User
from app.main import create_app
from tests.conftest import _seed

root = Path(os.environ.get("M1_INTEGRATION_DIR") or tempfile.mkdtemp(prefix="silkroad-frontend-m1-"))
root.mkdir(parents=True, exist_ok=True)
env = root / ".env"
if not env.exists():
    with os.fdopen(os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write(f"JWT_SECRET={secrets.token_urlsafe(48)}\nDATA_KEK={base64.b64encode(os.urandom(32)).decode()}\n")
settings = Settings(
    _env_file=env, env="test", task_mode="inline", demo_mode=False,
    database_url=f"sqlite+aiosqlite:///{root}/integration.db", redis_url="redis://unused",
    storage_dir=root / "storage", cookie_secure=True, cors_origins=["https://localhost:5173"],
)
app = create_app(settings, redis=fakeredis.aioredis.FakeRedis())
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        async with application.state.db.sessionmaker() as s:
            count = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        if not count:
            await _seed(application)
        yield


app.router.lifespan_context = lifespan


@app.middleware("http")
async def record_proxy_origin(request, call_next):
    # No cookies, passwords or token values recorded; test-only transport observations.
    if request.method == "POST" and request.url.path == "/api/v1/documents":
        (root / "transport.json").write_text(json.dumps({
            "origin": request.headers.get("origin"), "host": request.headers.get("host"),
            "forwarded_proto": request.headers.get("x-forwarded-proto"),
        }))
    return await call_next(request)
