from __future__ import annotations

from sqlalchemy import select, update

from app.core.errors import AppError
from app.db.models import DocumentFields, OcrPage
from app.services.document_access import get_document
from app.services.fields import DOC_FIELDS, align_field, open_fields, recognition_out, seal_fields


async def edit_fields(s, store, audit, user, doc_id: str, body, request_id: str) -> dict:
    doc = await get_document(s, user, doc_id)
    if doc.status != "ready":
        raise AppError(409, "DOCUMENT_NOT_READY", "单证仍在处理中")
    row = await s.get(DocumentFields, doc.id)
    if row is None or row.version != body.version:
        raise AppError(409, "VERSION_CONFLICT", "字段版本已变化，请重新加载")
    keys = [f.key for f in body.fields]
    if len(set(keys)) != len(keys) or set(keys) - DOC_FIELDS[doc.doc_type]:
        raise AppError(422, "VALIDATION_FAILED", "字段名重复或不适用此单证类型")
    fields = {f["key"]: f for f in open_fields(store, doc, row.fields)}
    pages = (
        (await s.execute(select(OcrPage).where(OcrPage.document_id == doc.id).order_by(OcrPage.page))).scalars().all()
    )
    blocks = [b for p in pages for b in p.blocks]
    for item in body.fields:
        fields[item.key] = align_field(item.key, item.value, blocks, source="manual")
    result = await s.execute(
        update(DocumentFields)
        .where(DocumentFields.document_id == doc.id, DocumentFields.version == body.version)
        .values(
            fields=seal_fields(store, doc, list(fields.values())),
            source="manual",
            version=body.version + 1,
            updated_by=user.id,
        )
    )
    if not result.rowcount:
        await s.rollback()
        raise AppError(409, "VERSION_CONFLICT", "字段版本已变化，请重新加载")
    await s.commit()
    await s.refresh(row)
    await audit.record(
        "document.fields_edit",
        "success",
        actor=user.actor,
        resource_type="document",
        resource_id=doc.id,
        request_id=request_id,
        detail={"keys": keys, "version": row.version},
    )
    return recognition_out(doc, pages, row, store)
