"""渲染 → OCR → 注入检测 → 脱敏 → 抽取 → 加密保存；失败不记录明文。"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import delete, update

from app.ai.ocr import ocr_engine
from app.ai.types import trace
from app.audit.service import Actor, AuditService
from app.db.base import Database
from app.db.models import Document, DocumentFields, OcrPage
from app.services import files
from app.services.fields import aigc, extract, seal_fields
from app.services.storage import EncryptedStore

log = structlog.get_logger()


async def process_document(
    db: Database,
    store: EncryptedStore,
    audit: AuditService,
    doc_id: str,
    request_id: str = "",
    *,
    ai=None,
    tenant_context: dict | None = None,
) -> None:
    async with db.job_session(tenant_context) as s:
        scope = s.info["tenant_scope"]
        claimed = await s.execute(
            update(Document)
            .where(
                Document.id == doc_id,
                Document.tenant_id == scope.org_id,
                Document.owner_id == scope.user_id,
                Document.status.in_(("uploaded", "failed")),
            )
            .values(status="ocr_running", progress=5)
        )
        await s.commit()
        if not claimed.rowcount:
            return
        doc = await s.get(Document, doc_id)
        try:
            if ai is None:
                raise RuntimeError("AI runtime not initialized")
            all_blocks = []
            dek = store.dek(doc.id, doc.wrapped_dek)
            original = store.get(doc.id, "original", dek)
            pages = await asyncio.to_thread(files.render_pages, original, doc.mime)
            await s.execute(delete(OcrPage).where(OcrPage.document_id == doc.id))
            total_ms = 0
            for i, png in enumerate(pages, start=1):
                store.put(doc.id, f"page-{i}.png", dek, png)
                blocks, ms = await asyncio.to_thread(ocr_engine.recognize, png)
                total_ms += ms
                page_blocks = [
                    {"id": f"p{i}-b{j}", "page": i, "text": b.text, "bbox": b.bbox, "confidence": b.confidence}
                    for j, b in enumerate(blocks, start=1)
                ]
                all_blocks.extend(page_blocks)
                s.add(
                    OcrPage(
                        document_id=doc.id,
                        page=i,
                        engine=ocr_engine.name,
                        duration_ms=ms,
                        blocks=page_blocks,
                    )
                )
                doc.progress = 5 + int(90 * i / len(pages))
                await s.commit()
            doc.pages, doc.status, doc.progress = len(pages), "extracting", 95
            await s.commit()
            extracted, security, traces, degrade = await extract(
                doc,
                all_blocks,
                ai,
                audit,
                request_id,
                actor=Actor(id=scope.user_id, role=scope.role, tenant_id=scope.org_id),
            )
            models = [trace("ocr", ocr_engine.name, "ocr", total_ms), *traces]
            await s.execute(delete(DocumentFields).where(DocumentFields.document_id == doc.id))
            s.add(
                DocumentFields(
                    document_id=doc.id,
                    version=1,
                    source="llm" if degrade != "L3" else "rule",
                    fields=seal_fields(store, doc, extracted),
                    models=models,
                    security=security,
                    degrade_level=degrade,
                    aigc_meta=aigc(doc.id, models),
                )
            )
            doc.status, doc.progress, doc.error_code = "ready", 100, None
            await s.commit()
            for model in traces:
                await audit.record(
                    "model.call",
                    "failed" if model["status"] == "failed" else "success",
                    actor=Actor(id=scope.user_id, role=scope.role, tenant_id=scope.org_id),
                    resource_type="document",
                    resource_id=doc.id,
                    request_id=request_id,
                    detail=model,
                )
            await audit.record(
                "model.call",
                "success",
                actor=Actor(id=scope.user_id, role=scope.role, tenant_id=scope.org_id),
                resource_type="document",
                resource_id=doc.id,
                request_id=request_id,
                detail={"category": "ocr", "model": ocr_engine.name, "pages": len(pages), "latency_ms": total_ms},
            )
        except Exception:
            log.error("document_processing_failed", document_id=doc_id)
            await s.rollback()
            doc = await s.get(Document, doc_id)
            if doc is None:
                return
            doc.status, doc.error_code = "failed", "MODEL_UNAVAILABLE"
            s.add(doc)
            await s.commit()
            await audit.record(
                "model.call",
                "failed",
                actor=Actor(id=scope.user_id, role=scope.role, tenant_id=scope.org_id),
                resource_type="document",
                resource_id=doc.id,
                request_id=request_id,
                detail={"category": "ocr", "model": ocr_engine.name},
            )
