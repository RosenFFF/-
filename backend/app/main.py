from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.ai.runtime import AIRuntime
from app.api.v1 import audit, auth, demo, documents, reviews, rules, system, users
from app.audit.service import AuditService
from app.core.config import Settings, get_settings
from app.core.errors import RATE_RESPONSES, VALIDATION_RESPONSE, install_handlers, problem
from app.core.logging import setup_logging
from app.db.base import Database
from app.db.models import Tenant, User
from app.security.cookies import CSRF_HEADER, csrf_ok
from app.security.passwords import hash_password
from app.security.ratelimit import RateLimiter
from app.services.chat import ChatStreams
from app.services.storage import EncryptedStore

log = structlog.get_logger()
_RID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


async def bootstrap(db: Database, settings: Settings) -> None:
    async with db.sessionmaker() as s:
        if (await s.execute(select(func.count()).select_from(User))).scalar_one() > 0:
            return
        if not (settings.bootstrap_admin_username and settings.bootstrap_admin_password):
            log.warning("no_users_and_no_bootstrap_admin")
            return
        t = Tenant(name="default")
        s.add(t)
        await s.flush()
        s.add(
            User(
                tenant_id=t.id,
                username=settings.bootstrap_admin_username,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role="admin",
            )
        )
        await s.commit()
        log.info("bootstrap_admin_created")


def create_app(
    settings: Settings | None = None, *, redis: Any = None, arq_pool: Any = None, llm: Any = None
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        if settings.env == "test":
            await db.migrate()  # Tests exercise the same versioned schema, never create_all.
        else:
            await db.check_migrated()
        await bootstrap(db, settings)
        r = redis or Redis.from_url(settings.redis_url)
        app.state.settings, app.state.db, app.state.redis = settings, db, r
        app.state.audit = AuditService(db)
        app.state.limiter = RateLimiter(r)
        app.state.store = EncryptedStore(settings)
        app.state.ai = await asyncio.to_thread(AIRuntime, settings, llm=llm)
        if settings.task_mode == "arq":
            from arq import create_pool
            from arq.connections import RedisSettings

            app.state.arq = arq_pool or await create_pool(RedisSettings.from_dsn(settings.redis_url))
        app.state.chat = ChatStreams(db, r, app.state.audit, app.state.ai, settings)
        try:
            yield
        finally:
            await app.state.chat.close()
            await db.dispose()

    docs = settings.env != "prod"
    app = FastAPI(
        title="丝路智审 API",
        version="0.4.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    install_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", CSRF_HEADER, "Accept", "Last-Event-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "X-Chat-Stream-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", "")
        rid = rid if _RID.match(rid) else uuid.uuid4().hex
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path, method=request.method)
        if not csrf_ok(request):
            await request.app.state.audit.record(
                "access.denied",
                "denied",
                ip=request.client.host if request.client else None,
                request_id=rid,
                detail={"reason": "csrf", "method": request.method, "path": request.url.path},
            )
            resp = problem(request, 403, "CSRF_FAILED", "CSRF 校验失败")
        else:
            resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if request.url.path.startswith("/api/docs"):
            del resp.headers["Content-Security-Policy"]  # Swagger UI 需要加载脚本，仅非生产环境开启
        log.info("request", status=resp.status_code)
        return resp

    prefix = "/api/v1"
    routers = [system.router, auth.router, users.router, documents.router, reviews.router, rules.router, audit.router]
    if settings.demo_mode and settings.env != "prod":
        routers.append(demo.router)
    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                route.responses.setdefault(422, VALIDATION_RESPONSE)
                if route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
                    for status, response in RATE_RESPONSES.items():
                        route.responses.setdefault(status, response)
        app.include_router(router, prefix=prefix)
    return app


def app_factory() -> FastAPI:
    return create_app()
