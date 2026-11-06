"""演示专用：篡改一条审计日志，用于现场展示 /audit/verify 能定位断链。

只在 DEMO_MODE=true 时注册路由（生产配置下这些端点根本不存在，返回 404），且仅 admin 可用。
篡改本身也会追加一条审计记录。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import AuditLog, DemoTamperBackup
from app.deps import Ctx, CurrentUser, ctx, require, session
from app.security.rbac import Perm

router = APIRouter(prefix="/demo", tags=["demo"])


class TamperIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    log_id: str = Field(min_length=36, max_length=36)


async def _row(s: AsyncSession, user: CurrentUser, log_id: str) -> AuditLog:
    r = (
        await s.execute(select(AuditLog).where(AuditLog.id == log_id, AuditLog.tenant_id == user.tenant_id))
    ).scalar_one_or_none()
    if r is None:
        raise AppError(404, "NOT_FOUND", "审计记录不存在")
    return r


@router.post("/audit/tamper")
async def tamper(
    body: TamperIn,
    user: CurrentUser = Depends(require(Perm.user_manage)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> dict:
    r = await _row(s, user, body.log_id)
    if await s.get(DemoTamperBackup, r.id) is None:
        s.add(DemoTamperBackup(log_id=r.id, original_detail=dict(r.detail or {})))
    r.detail = {**(r.detail or {}), "tampered": True}  # 故意不重算 hash
    await s.commit()
    await c.audit.record(
        "demo.audit_tamper",
        "success",
        actor=user.actor,
        resource_type="audit_log",
        resource_id=r.id,
        ip=c.ip,
        request_id=c.request_id,
    )
    return {"tampered_id": r.id}


@router.post("/audit/restore")
async def restore(
    body: TamperIn,
    user: CurrentUser = Depends(require(Perm.user_manage)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> dict:
    r = await _row(s, user, body.log_id)
    b = await s.get(DemoTamperBackup, r.id)
    if b is None:
        raise AppError(404, "NOT_FOUND", "没有该记录的篡改备份")
    r.detail = b.original_detail
    await s.delete(b)
    await s.commit()
    await c.audit.record(
        "demo.audit_restore",
        "success",
        actor=user.actor,
        resource_type="audit_log",
        resource_id=r.id,
        ip=c.ip,
        request_id=c.request_id,
    )
    return {"restored_id": r.id}
