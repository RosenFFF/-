from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import User
from app.deps import Ctx, CurrentUser, ctx, require, session
from app.security.passwords import hash_password
from app.security.rbac import Perm

from .schemas import UserCreateIn, UserOut, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require(Perm.user_manage)),
    s: AsyncSession = Depends(session),
) -> dict:
    q = select(User).where(User.tenant_id == user.tenant_id)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (await s.execute(q.order_by(User.created_at).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [UserOut.model_validate(r).model_dump(mode="json") for r in rows],
    }


@router.post("", status_code=201, response_model=UserOut)
async def create_user(
    body: UserCreateIn,
    user: CurrentUser = Depends(require(Perm.user_manage)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> UserOut:
    if (await s.execute(select(User.id).where(User.username == body.username))).scalar_one_or_none():
        raise AppError(409, "ALREADY_EXISTS", "用户名已存在")
    u = User(
        tenant_id=user.tenant_id,
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role.value,
    )
    s.add(u)
    await s.commit()
    await c.audit.record(
        "user.create",
        "success",
        actor=user.actor,
        resource_type="user",
        resource_id=u.id,
        ip=c.ip,
        request_id=c.request_id,
        detail={"role": u.role},
    )
    return UserOut.model_validate(u)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: str,
    body: UserPatchIn,
    user: CurrentUser = Depends(require(Perm.user_manage)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> UserOut:
    u = (await s.execute(select(User).where(User.id == user_id, User.tenant_id == user.tenant_id))).scalar_one_or_none()
    if u is None:
        raise AppError(404, "NOT_FOUND", "用户不存在")
    if u.id == user.id and (body.disabled or (body.role and body.role.value != u.role)):
        raise AppError(409, "VERSION_CONFLICT", "不能停用自己或修改自己的角色")
    changes = body.model_dump(exclude_none=True, mode="json")
    for k, v in changes.items():
        setattr(u, k, v)
    await s.commit()
    await c.audit.record(
        "user.update",
        "success",
        actor=user.actor,
        resource_type="user",
        resource_id=u.id,
        ip=c.ip,
        request_id=c.request_id,
        detail=changes,
    )
    return UserOut.model_validate(u)
