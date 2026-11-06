"""依赖注入：数据库会话、当前用户、权限校验（拒绝即写审计）、限流。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import Actor, AuditService
from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import Database
from app.db.models import User
from app.security.cookies import ACCESS_COOKIE
from app.security.ratelimit import RateLimiter
from app.security.rbac import Perm, perms_of
from app.security.tokens import decode_access

_bearer = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class Ctx:
    settings: Settings
    db: Database
    audit: AuditService
    limiter: RateLimiter
    request_id: str
    ip: str | None


def ctx(request: Request) -> Ctx:
    st = request.app.state
    return Ctx(
        st.settings,
        st.db,
        st.audit,
        st.limiter,
        request.state.request_id,
        request.client.host if request.client else None,
    )


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessionmaker() as s:
        yield s


@dataclass(slots=True)
class CurrentUser:
    id: str
    tenant_id: str
    username: str
    role: str

    @property
    def actor(self) -> Actor:
        return Actor(self.id, self.username, self.role, self.tenant_id)

    def can(self, perm: Perm) -> bool:
        return perm in perms_of(self.role)


async def current_user(
    request: Request,
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    # 浏览器走 httpOnly cookie；脚本/测试工具也可用 Authorization: Bearer
    token = (
        cred.credentials if cred is not None and cred.scheme.lower() == "bearer" else request.cookies.get(ACCESS_COOKIE)
    )
    if not token:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "未登录")
    claims = decode_access(c.settings, token)
    user = (await s.execute(select(User).where(User.id == claims["sub"]))).scalar_one_or_none()
    # 令牌签发后被停用或改了角色：以数据库为准
    if user is None or user.disabled:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "账号不可用")
    current = CurrentUser(user.id, user.tenant_id, user.username, user.role)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        await enforce_rate(c, f"write:{current.tenant_id}:{current.id}", c.settings.rl_default_per_min, current.actor)
    return current


def require(perm: Perm) -> Callable:
    async def _dep(request: Request, user: CurrentUser = Depends(current_user), c: Ctx = Depends(ctx)) -> CurrentUser:
        if not user.can(perm):
            await c.audit.record(
                "access.denied",
                "denied",
                actor=user.actor,
                ip=c.ip,
                request_id=c.request_id,
                detail={"required": perm.value, "method": request.method, "path": request.url.path},
            )
            raise AppError(403, "PERMISSION_DENIED", "没有权限执行该操作")
        return user

    return _dep


async def enforce_rate(c: Ctx, key: str, limit: int, actor: Actor | None = None) -> None:
    try:
        ok, retry = await c.limiter.hit(key, limit)
    except RedisError:
        raise AppError(503, "RATE_LIMIT_UNAVAILABLE", "限流服务暂不可用，请稍后再试") from None
    if not ok:
        await c.audit.record(
            "rate_limit.hit",
            "blocked",
            actor=actor,
            ip=c.ip,
            request_id=c.request_id,
            detail={"bucket": key.split(":", 1)[0]},
        )
        raise AppError(429, "RATE_LIMITED", "请求过于频繁，请稍后再试", headers={"Retry-After": str(retry)})
