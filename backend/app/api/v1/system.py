from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.deps import CurrentUser, current_user
from app.services.model_health import apply_audit_metrics, model_health

router = APIRouter(tags=["system"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    st = request.app.state
    checks: dict[str, dict] = {}

    t0 = time.perf_counter()
    try:
        async with st.db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "latency_ms": int((time.perf_counter() - t0) * 1000), "detail": None}
    except Exception:
        checks["database"] = {"ok": False, "latency_ms": None, "detail": "unreachable"}

    t0 = time.perf_counter()
    try:
        await st.redis.ping()
        checks["redis"] = {"ok": True, "latency_ms": int((time.perf_counter() - t0) * 1000), "detail": None}
    except Exception:
        checks["redis"] = {"ok": False, "latency_ms": None, "detail": "unreachable"}

    model_status = await model_health(st.ai)
    for category in ("ocr", "llm", "embedding", "reranker"):
        selected = [m for m in model_status["models"] if m["category"] == category and m.get("enabled", True)]
        ok = any(m["healthy"] for m in selected)
        checks[category] = {
            "ok": ok,
            "latency_ms": None,
            "detail": ", ".join(m["model"] for m in selected if m["healthy"]) or "unavailable",
        }
    core_ok = all(checks[name]["ok"] for name in ("database", "redis", "ocr", "embedding", "reranker"))
    level = model_status["degrade_level"]
    status = ("ready" if level == "L0" else "degraded") if core_ok else "not_ready"
    body = {"status": status, "degrade_level": level, "checks": checks}
    return JSONResponse(body, status_code=200 if core_ok else 503)


@router.get("/system/models")
async def models(request: Request, _: CurrentUser = Depends(current_user)) -> dict:
    st = request.app.state
    result = await model_health(st.ai)
    result = await apply_audit_metrics(result, st.db, _.scope, st.settings)
    result["llm_provider_chain"] = st.settings.llm_provider_chain  # Declared order (backwards compatible).
    result["local_model_enabled"] = st.settings.local_model_enabled
    result["effective_llm_provider_chain"] = [
        m["provider"] for m in result["models"] if m["category"] == "llm" and m.get("enabled", True)
    ]
    return result
