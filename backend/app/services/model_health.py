from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ai.llm import health_level
from app.ai.ocr import ocr_engine
from app.db.models import AuditLog
from app.db.tenant import TenantScope


async def model_health(ai) -> dict:
    level, items = await ai.health()
    try:
        await asyncio.to_thread(ocr_engine.load)
        ocr_ok = ocr_engine.loaded
    except Exception:
        ocr_ok = False
    items.insert(
        0,
        {
            "category": "ocr",
            "provider": "local",
            "model": ocr_engine.name,
            "deployment": "local",
            "stage": "单证识别",
            "healthy": ocr_ok,
            "circuit_open": False,
            "p95_latency_ms": None,
            "calls_24h": 0,
        },
    )
    return {"degrade_level": level, "models": items}


async def apply_audit_metrics(result: dict, db, scope: TenantScope, settings) -> dict:
    """API and arq do not share memory: read real worker calls from the audit ledger."""
    since = datetime.now(UTC) - timedelta(hours=24)
    async with db.tenant_session(scope) as s:
        rows = (
            (
                await s.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.action == "model.call",
                        AuditLog.tenant_id == scope.org_id,
                        AuditLog.ts >= since,
                    )
                    .order_by(AuditLog.seq.desc())
                )
            )
            .scalars()
            .all()
        )
    for model in result["models"]:
        events = [
            r
            for r in rows
            if r.detail.get("category") == model["category"]
            and r.detail.get("model") == model["model"]
            and r.detail.get("provider", "local") == model["provider"]
        ]
        ms = sorted(r.detail["latency_ms"] for r in events if isinstance(r.detail.get("latency_ms"), int))
        model["calls_24h"] = len(events)
        model["p95_latency_ms"] = ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None
        if not model.get("enabled", True):
            model["healthy"], model["circuit_open"] = False, False
            continue  # Historical counts remain visible; disabled models cannot become candidates.
        if model["category"] == "llm" and events:
            recent_failures = 0
            for event in events:
                ts = event.ts.replace(tzinfo=UTC) if event.ts.tzinfo is None else event.ts
                if event.result != "failed" or (datetime.now(UTC) - ts).total_seconds() >= settings.llm_circuit_reset_s:
                    break
                recent_failures += 1
            if recent_failures >= settings.llm_circuit_failures:
                model["circuit_open"], model["healthy"] = True, False
    result["degrade_level"] = health_level(result["models"])
    return result
