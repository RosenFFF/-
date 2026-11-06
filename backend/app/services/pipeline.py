"""单证处理流水线（M0：渲染 → OCR；M1 在此之后接 脱敏 → LLM 字段抽取）。"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import delete, select

from app.ai.ocr import ocr_engine
from app.audit.service import AuditService
from app.db.base import Database
from app.db.models import Document, OcrPage
from app.services import files
from app.services.storage import EncryptedStore

log = structlog.get_logger()


async def process_document(
    db: Database, store: EncryptedStore, audit: AuditService, doc_id: str, request_id: str = ""
) -> None:
    async with db.sessionmaker() as s:
        doc = (await s.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
        if doc is None or doc.status not in ("uploaded", "failed"):
            return
        doc.status, doc.progress = "ocr_running", 5
        await s.commit()
        try:
            dek = store.dek(doc.id, doc.wrapped_dek)
            original = store.get(doc.id, "original", dek)
            pages = await asyncio.to_thread(files.render_pages, original, doc.mime)
            await s.execute(delete(OcrPage).where(OcrPage.document_id == doc.id))
            total_ms = 0
            for i, png in enumerate(pages, start=1):
                store.put(doc.id, f"page-{i}.png", dek, png)
                blocks, ms = await asyncio.to_thread(ocr_engine.recognize, png)
                total_ms += ms
                s.add(
                    OcrPage(
                        document_id=doc.id,
                        page=i,
                        engine=ocr_engine.name,
                        duration_ms=ms,
                        blocks=[
                            {"id": f"p{i}-b{j}", "page": i, "text": b.text, "bbox": b.bbox, "confidence": b.confidence}
                            for j, b in enumerate(blocks, start=1)
                        ],
                    )
                )
                doc.progress = 5 + int(90 * i / len(pages))
                await s.commit()
            doc.pages, doc.status, doc.progress = len(pages), "ready", 100
            await s.commit()
            await audit.record(
                "model.call",
                "success",
                resource_type="document",
                resource_id=doc.id,
                request_id=request_id,
                detail={"category": "ocr", "model": ocr_engine.name, "pages": len(pages), "latency_ms": total_ms},
            )
        except Exception:
            log.exception("ocr_failed", document_id=doc.id)
            await s.rollback()
            doc.status, doc.error_code = "failed", "MODEL_UNAVAILABLE"
            s.add(doc)
            await s.commit()
            await audit.record(
                "model.call",
                "failed",
                resource_type="document",
                resource_id=doc.id,
                request_id=request_id,
                detail={"category": "ocr", "model": ocr_engine.name},
            )
