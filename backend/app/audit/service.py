"""审计日志：只追加 + 哈希链。

每条记录的 hash = sha256(prev_hash || 规范化 JSON)。任何一条被改动，从它开始校验就会断链，
`verify()` 返回第一条断链记录的 id。写审计用独立会话提交，业务事务回滚也不影响审计落库。
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text

from app.db.base import Database
from app.db.models import AuditLog, uid

_ADVISORY_KEY = 7_143_001
_lock = asyncio.Lock()


@dataclass(slots=True)
class Actor:
    id: str | None = None
    username: str | None = None
    role: str | None = None
    tenant_id: str | None = None


def mask_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version == 4:
        return ".".join(ip.split(".")[:3] + ["*"])
    return str(ipaddress.ip_network(f"{ip}/48", strict=False).network_address) + "*"


def _ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def compute_hash(row: AuditLog) -> str:
    payload = {
        "id": row.id,
        "ts": _ts(row.ts),
        "tenant_id": row.tenant_id,
        "actor_id": row.actor_id,
        "actor_role": row.actor_role,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "result": row.result,
        "request_id": row.request_id,
        "detail": row.detail or {},
    }
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(((row.prev_hash or "") + canon).encode()).hexdigest()


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def record(
        self,
        action: str,
        result: str,
        *,
        actor: Actor | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip: str | None = None,
        request_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> str:
        actor = actor or Actor()
        async with _lock, self.db.sessionmaker() as s, s.begin():
            if self.db.is_postgres:
                await s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_KEY})
            prev = (await s.execute(select(AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1))).scalar()
            row = AuditLog(
                id=uid(),
                ts=datetime.now(UTC),
                tenant_id=actor.tenant_id,
                actor_id=actor.id,
                actor_username=actor.username,
                actor_role=actor.role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                ip=mask_ip(ip),
                request_id=request_id,
                detail=detail or {},
                prev_hash=prev,
            )
            row.hash = compute_hash(row)
            s.add(row)
        return row.id

    async def verify(self) -> dict[str, Any]:
        checked, prev, head = 0, None, None
        async with self.db.sessionmaker() as s:
            rows = await s.stream_scalars(select(AuditLog).order_by(AuditLog.seq))
            async for row in rows:
                if row.prev_hash != prev or compute_hash(row) != row.hash:
                    return {"valid": False, "checked": checked, "head_hash": head, "first_broken_id": row.id}
                checked += 1
                prev = head = row.hash
        return {"valid": True, "checked": checked, "head_hash": head, "first_broken_id": None}
