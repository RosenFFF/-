from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.ai.ocr import ocr_engine
from app.deps import CurrentUser, current_user

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

    checks["ocr"] = {
        "ok": True,
        "latency_ms": None,
        "detail": "loaded" if ocr_engine.loaded else "lazy (worker 进程预热)",
    }
    # M0 尚未接入 LLM：如实报告为 L3（仅规则/识别），M1 接入后按熔断状态计算
    checks["llm"] = {"ok": False, "latency_ms": None, "detail": "M1 接入"}

    core_ok = checks["database"]["ok"] and checks["redis"]["ok"]
    status = ("ready" if checks["llm"]["ok"] else "degraded") if core_ok else "not_ready"
    body = {"status": status, "degrade_level": "L0" if checks["llm"]["ok"] else "L3", "checks": checks}
    return JSONResponse(body, status_code=200 if core_ok else 503)


@router.get("/system/models")
async def models(request: Request, _: CurrentUser = Depends(current_user)) -> dict:
    s = request.app.state.settings
    llm_stage = "字段抽取 / 合规推理 / 多语种解释 / 追问"
    items = [
        {
            "category": "ocr",
            "provider": "local",
            "model": s.ocr_engine,
            "deployment": "local",
            "stage": "单证识别",
            "healthy": True,
            "circuit_open": False,
            "p95_latency_ms": None,
            "calls_24h": 0,
        }
    ]
    for p in s.llm_provider_chain:
        items.append(
            {
                "category": "llm",
                "provider": p,
                "model": p,
                "deployment": "local" if p == "ollama" else "cloud",
                "stage": llm_stage,
                "healthy": False,
                "circuit_open": False,
                "p95_latency_ms": None,
                "calls_24h": 0,
            }
        )
    items += [
        {
            "category": "embedding",
            "provider": "local",
            "model": "bge-m3",
            "deployment": "local",
            "stage": "规则库向量检索",
            "healthy": False,
            "circuit_open": False,
            "p95_latency_ms": None,
            "calls_24h": 0,
        },
        {
            "category": "reranker",
            "provider": "local",
            "model": "bge-reranker-v2-m3",
            "deployment": "local",
            "stage": "条款精排",
            "healthy": False,
            "circuit_open": False,
            "p95_latency_ms": None,
            "calls_24h": 0,
        },
    ]
    return {"degrade_level": "L3", "llm_provider_chain": s.llm_provider_chain, "models": items}
