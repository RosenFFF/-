from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import Actor
from app.core.errors import AppError
from app.db.models import RefreshToken, User, uid
from app.deps import Ctx, CurrentUser, ctx, current_user, enforce_rate, session
from app.security.cookies import REFRESH_COOKIE, clear_session, set_session
from app.security.passwords import verify_password
from app.security.rbac import perms_of
from app.security.tokens import hash_refresh, issue_access, new_refresh

from .schemas import CurrentUserOut, LoginIn, SessionOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def _me(u: User) -> CurrentUserOut:
    return CurrentUserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        disabled=u.disabled,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        tenant_id=u.tenant_id,
        permissions=sorted(p.value for p in perms_of(u.role)),
    )


async def _issue(c: Ctx, s: AsyncSession, resp: Response, u: User, family: str | None = None) -> SessionOut:
    raw, h = new_refresh()
    s.add(
        RefreshToken(
            user_id=u.id,
            family_id=family or uid(),
            token_hash=h,
            expires_at=datetime.now(UTC) + timedelta(seconds=c.settings.refresh_token_ttl_s),
        )
    )
    await s.commit()
    access = issue_access(c.settings, user_id=u.id, tenant_id=u.tenant_id, role=u.role)
    set_session(resp, c.settings, access=access, refresh=raw)
    return SessionOut(expires_in=c.settings.access_token_ttl_s, user=_me(u))


@router.post("/login", response_model=SessionOut)
async def login(body: LoginIn, resp: Response, c: Ctx = Depends(ctx), s: AsyncSession = Depends(session)) -> SessionOut:
    await enforce_rate(c, f"login:{c.ip}", c.settings.rl_login_per_min)
    u = (await s.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    now = datetime.now(UTC)
    actor = Actor(u.id, u.username, u.role, u.tenant_id) if u else Actor(username=body.username[:64])

    if u is not None and u.locked_until and _aware(u.locked_until) > now:
        verify_password(body.password, None)  # 保持耗时一致
        await c.audit.record(
            "auth.login_failed", "blocked", actor=actor, ip=c.ip, request_id=c.request_id, detail={"reason": "locked"}
        )
        raise AppError(423, "AUTH_LOCKED", "登录失败次数过多，账号已临时锁定")

    if u is None or u.disabled or not verify_password(body.password, u.password_hash):
        if u is not None:
            u.failed_logins += 1
            if u.failed_logins >= c.settings.login_max_failures:
                u.locked_until = now + timedelta(seconds=c.settings.login_lock_s)
                u.failed_logins = 0
            await s.commit()
        await c.audit.record(
            "auth.login_failed",
            "denied",
            actor=actor,
            ip=c.ip,
            request_id=c.request_id,
            detail={"reason": "bad_credentials"},
        )
        raise AppError(401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误")

    u.failed_logins, u.locked_until, u.last_login_at = 0, None, now
    out = await _issue(c, s, resp, u)
    await c.audit.record("auth.login", "success", actor=actor, ip=c.ip, request_id=c.request_id)
    return out


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    resp: Response,
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> SessionOut:
    if not refresh_token:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "请重新登录")
    rt = (
        await s.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(refresh_token)))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if rt is None:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "请重新登录")
    u = (await s.execute(select(User).where(User.id == rt.user_id))).scalar_one()
    if rt.revoked_at is not None:
        # 已轮换过的令牌被再次使用 → 判定为被盗用，作废整条令牌族
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await s.commit()
        await c.audit.record(
            "auth.refresh_reuse_detected",
            "blocked",
            actor=Actor(u.id, u.username, u.role, u.tenant_id),
            ip=c.ip,
            request_id=c.request_id,
            detail={"family_id": rt.family_id},
        )
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "请重新登录")
    if _aware(rt.expires_at) <= now or u.disabled:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "请重新登录")
    rt.revoked_at = now
    return await _issue(c, s, resp, u, family=rt.family_id)


@router.post("/logout", status_code=204)
async def logout(
    resp: Response,
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Response:
    if refresh_token:
        rt = (
            await s.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(refresh_token)))
        ).scalar_one_or_none()
        if rt is not None:
            await s.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == rt.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            await s.commit()
            await c.audit.record("auth.logout", "success", actor=Actor(id=rt.user_id), ip=c.ip, request_id=c.request_id)
    r = Response(status_code=204)
    clear_session(r, c.settings)
    return r


@router.get("/me", response_model=CurrentUserOut)
async def me(user: CurrentUser = Depends(current_user), s: AsyncSession = Depends(session)) -> CurrentUserOut:
    u = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
    return _me(u)
