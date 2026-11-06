from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.deps import Ctx, CurrentUser, ctx, require, session
from app.security.rbac import Perm

router = APIRouter(prefix="/audit", tags=["audit"])

FIELDS = (
    "id",
    "ts",
    "actor_id",
    "actor_username",
    "actor_role",
    "action",
    "resource_type",
    "resource_id",
    "result",
    "ip",
    "request_id",
    "detail",
    "prev_hash",
    "hash",
)


def to_dict(r: AuditLog) -> dict:
    return {k: getattr(r, k) for k in FIELDS}


@router.get("/logs")
async def logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None, max_length=48),
    result: str | None = Query(None, pattern="^(success|denied|blocked|failed)$"),
    actor_id: str | None = Query(None, max_length=36),
    since: datetime | None = None,
    until: datetime | None = None,
    user: CurrentUser = Depends(require(Perm.audit_read_all)),
    s: AsyncSession = Depends(session),
) -> dict:
    q = select(AuditLog).where((AuditLog.tenant_id == user.tenant_id) | AuditLog.tenant_id.is_(None))
    if action:
        q = q.where(AuditLog.action == action)
    if result:
        q = q.where(AuditLog.result == result)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if since:
        q = q.where(AuditLog.ts >= since)
    if until:
        q = q.where(AuditLog.ts < until)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (await s.execute(q.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return {"page": page, "page_size": page_size, "total": total, "items": [to_dict(r) for r in rows]}


@router.get("/verify")
async def verify(user: CurrentUser = Depends(require(Perm.audit_read_all)), c: Ctx = Depends(ctx)) -> dict:
    return await c.audit.verify()
