from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import AuditLog
from app.deps import Ctx, CurrentUser, ctx, require, session
from app.security.output import sanitize_public
from app.security.rbac import Perm

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogOut(BaseModel):
    id: str
    ts: datetime
    actor_id: str | None
    actor_username: str | None
    actor_role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    result: Literal["success", "denied", "blocked", "failed"]
    ip: str | None
    request_id: str
    detail: dict
    prev_hash: str | None
    hash: str


class AuditPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[AuditLogOut]


class AuditVerify(BaseModel):
    valid: bool
    checked: int
    head_hash: str | None
    first_broken_id: str | None


class SecurityTotals(BaseModel):
    requests: int = 0  # Audit events, NOT HTTP request telemetry.
    logins_failed: int = 0
    access_denied: int = 0
    rate_limited: int = 0
    injections_blocked: int = 0
    pii_masked: int = 0
    model_calls: int = 0
    model_fallbacks: int = 0
    tokens_used: int = 0
    outputs_blocked: int = 0


class SecurityBucket(BaseModel):
    bucket_start: datetime
    access_denied: int = 0
    injections_blocked: int = 0
    rate_limited: int = 0
    model_calls: int = 0


class DeniedActor(BaseModel):
    actor_username: str | None
    count: int


class SecurityStats(BaseModel):
    window: Literal["1h", "24h", "7d"]
    totals: SecurityTotals
    timeline: list[SecurityBucket]
    top_denied_actors: list[DeniedActor]
    audit_chain_valid: bool


@dataclass
class AuditFilters:
    action: str | None
    result: str | None
    actor_id: str | None
    since: datetime | None
    until: datetime | None

    def apply(self, q):
        for column, value in (
            (AuditLog.action, self.action),
            (AuditLog.result, self.result),
            (AuditLog.actor_id, self.actor_id),
        ):
            if value is not None:
                q = q.where(column == value)
        if self.since:
            q = q.where(AuditLog.ts >= self.since)
        if self.until:
            q = q.where(AuditLog.ts < self.until)
        return q


def filters(
    action: str | None = Query(None, max_length=48),
    result: str | None = Query(None, pattern="^(success|denied|blocked|failed)$"),
    actor_id: str | None = Query(None, max_length=36),
    since: datetime | None = None,
    until: datetime | None = None,
) -> AuditFilters:
    if any(v is not None and v.tzinfo is None for v in (since, until)):
        raise AppError(422, "VALIDATION_FAILED", "时间须包含时区")
    if since and until and since >= until:
        raise AppError(422, "VALIDATION_FAILED", "since 必须早于 until")
    return AuditFilters(
        action,
        result,
        actor_id,
        since.astimezone(UTC) if since else None,
        until.astimezone(UTC) if until else None,
    )


def to_dict(row: AuditLog) -> dict:
    result = {k: getattr(row, k) for k in AuditLogOut.model_fields}
    # SQLAlchemy SQLite loses timezone info; the DB stores UTC.
    result["ts"] = aware(row.ts)
    result["detail"] = sanitize_public(row.detail, pii=True)
    result["actor_username"] = sanitize_public(row.actor_username, pii=True)
    return result


def aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


async def paginate(s, q, page: int, page_size: int) -> dict:
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await s.scalars(q.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {"page": page, "page_size": page_size, "total": total, "items": [to_dict(r) for r in rows]}


@router.get("/logs", response_model=AuditPage)
async def logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    f: AuditFilters = Depends(filters),
    user: CurrentUser = Depends(require(Perm.audit_read_all)),
    s: AsyncSession = Depends(session),
) -> dict:
    # Null-tenant auth/infrastructure events are platform-private, NOT shared with tenants.
    q = f.apply(select(AuditLog).where(AuditLog.tenant_id == user.tenant_id))
    return await paginate(s, q, page, page_size)


@router.get("/stats", response_model=SecurityStats)
async def stats(
    window: Literal["1h", "24h", "7d"] = "24h",
    user: CurrentUser = Depends(require(Perm.audit_read_all)),
    s: AsyncSession = Depends(session),
    c: Ctx = Depends(ctx),
) -> SecurityStats:
    end = datetime.now(UTC)
    seconds = {"1h": 3600, "24h": 86400, "7d": 604800}[window]
    step = {"1h": 300, "24h": 3600, "7d": 86400}[window]
    start = end - timedelta(seconds=seconds)
    bucket_start = datetime.fromtimestamp(int(start.timestamp()) // step * step, UTC)
    buckets = {}
    while bucket_start <= end:
        buckets[bucket_start] = SecurityBucket(bucket_start=bucket_start)
        bucket_start += timedelta(seconds=step)
    totals, denied = SecurityTotals(), Counter()
    q = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id, AuditLog.ts >= start, AuditLog.ts < end)
    rows = await s.stream_scalars(q)
    async for row in rows:
        totals.requests += 1
        names = []
        if row.action == "auth.login_failed":
            totals.logins_failed += 1
        for action, name in (
            ("access.denied", "access_denied"),
            ("rate_limit.hit", "rate_limited"),
            ("security.injection_detected", "injections_blocked"),
            ("model.call", "model_calls"),
        ):
            if row.action == action:
                setattr(totals, name, getattr(totals, name) + 1)
                names.append(name)
        if row.action == "security.output_blocked":
            totals.outputs_blocked += 1
        if row.action == "security.pii_masked":
            counts = row.detail.get("counts", {})
            if isinstance(counts, dict):
                totals.pii_masked += sum(v for v in counts.values() if type(v) is int and v >= 0)
        if row.action == "model.fallback" or (row.action == "model.call" and row.detail.get("status") == "fallback"):
            totals.model_fallbacks += 1
        if row.action == "model.call":
            totals.tokens_used += sum(
                v for k in ("tokens_in", "tokens_out") if type(v := row.detail.get(k)) is int and v >= 0
            )
        if row.action == "access.denied":
            denied[sanitize_public(row.actor_username, pii=True)] += 1
        stamp = datetime.fromtimestamp(int(aware(row.ts).timestamp()) // step * step, UTC)
        for name in names:
            setattr(buckets[stamp], name, getattr(buckets[stamp], name) + 1)
    integrity = await c.audit.verify(user.tenant_id)
    return SecurityStats(
        window=window,
        totals=totals,
        timeline=list(buckets.values()),
        top_denied_actors=[DeniedActor(actor_username=k, count=v) for k, v in denied.most_common(10)],
        audit_chain_valid=integrity["valid"],
    )


@router.get("/verify", response_model=AuditVerify)
async def verify(user: CurrentUser = Depends(require(Perm.audit_read_all)), c: Ctx = Depends(ctx)) -> dict:
    return await c.audit.verify(user.tenant_id)
