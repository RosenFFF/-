"""arq Worker：`arq app.workers.tasks.WorkerSettings`。"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from app.ai.ocr import ocr_engine
from app.ai.runtime import AIRuntime
from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.base import Database
from app.services.pipeline import process_document
from app.services.review import process_review
from app.services.storage import EncryptedStore


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    settings = get_settings()
    ctx["db"] = Database(settings.database_url)
    await ctx["db"].check_migrated()
    try:
        await ctx["db"].check_runtime_access()
    except Exception:
        await ctx["db"].dispose()
        raise
    ctx["store"] = EncryptedStore(settings)
    ctx["audit"] = AuditService(ctx["db"])
    ctx["ai"] = AIRuntime(settings)
    ocr_engine.load()  # 预热，避免第一单慢


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["db"].dispose()


async def ocr_task(
    ctx: dict[str, Any], doc_id: str, request_id: str = "", *, tenant_context: dict | None = None
) -> None:
    await process_document(
        ctx["db"], ctx["store"], ctx["audit"], doc_id, request_id, ai=ctx["ai"], tenant_context=tenant_context
    )


async def review_task(
    ctx: dict[str, Any], review_id: str, request_id: str = "", *, tenant_context: dict | None = None
) -> None:
    await process_review(
        ctx["db"], ctx["store"], ctx["audit"], ctx["ai"], review_id, request_id, tenant_context=tenant_context
    )


class WorkerSettings:
    functions = [ocr_task, review_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2  # OCR 吃 CPU，限制并发
    job_timeout = 300
