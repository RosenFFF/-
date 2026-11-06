from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Path, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Document, DocumentFields, OcrPage, Review, ReviewDocument, uid
from app.deps import Ctx, CurrentUser, ctx, enforce_rate, require, session
from app.security.rbac import Perm
from app.services import files
from app.services.document_access import get_document as _get
from app.services.document_access import visible_documents as _visible
from app.services.field_edit import edit_fields
from app.services.fields import recognition_out
from app.services.pipeline import process_document

from .schemas import DocStatus, DocType, DocumentOut, FieldsPatchIn

router = APIRouter(prefix="/documents", tags=["documents"])
UUID_RE = r"^[0-9a-fA-F-]{36}$"
CHUNK = 1024 * 1024


def _out(d: Document) -> DocumentOut:
    out = DocumentOut.model_validate(d)
    if d.status == "failed":
        out.error = {
            "type": "about:blank",
            "title": "识别失败",
            "status": 500,
            "code": d.error_code or "INTERNAL_ERROR",
            "request_id": "",
        }
    return out


async def _read_limited(f: UploadFile, limit: int) -> bytes:
    buf = bytearray()
    while chunk := await f.read(CHUNK):
        buf += chunk
        if len(buf) > limit:
            raise AppError(413, "FILE_TOO_LARGE", f"文件超过 {limit // (1024 * 1024)} MB")
    if not buf:
        raise AppError(422, "VALIDATION_FAILED", "文件为空")
    return bytes(buf)


@router.post("", status_code=202, response_model=DocumentOut)
async def upload(
    request: Request,
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: DocType = Form("unknown"),
    user: CurrentUser = Depends(require(Perm.document_upload)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> DocumentOut:
    await enforce_rate(c, f"upload:{user.id}", c.settings.rl_upload_per_min, user.actor)
    data = await _read_limited(file, c.settings.max_upload_bytes)
    try:
        info = files.inspect(data, c.settings.max_pages)
    except AppError as e:
        await c.audit.record(
            "document.upload",
            "blocked",
            actor=user.actor,
            ip=c.ip,
            request_id=c.request_id,
            detail={"reason": e.code, "size": len(data)},
        )
        raise

    store = request.app.state.store
    doc_id = uid()
    dek, wrapped = store.new_wrapped_dek(doc_id)
    store.put(doc_id, "original", dek, data)
    d = Document(
        id=doc_id,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        doc_type=doc_type,
        filename=files.clean_filename(file.filename),
        mime=info.mime,
        size_bytes=len(data),
        pages=info.pages,
        sha256=hashlib.sha256(data).hexdigest(),
        wrapped_dek=wrapped,
        status="uploaded",
        progress=0,
        expire_at=datetime.now(UTC) + timedelta(days=c.settings.retention_days),
    )
    s.add(d)
    await s.commit()
    await c.audit.record(
        "document.upload",
        "success",
        actor=user.actor,
        resource_type="document",
        resource_id=d.id,
        ip=c.ip,
        request_id=c.request_id,
        detail={"mime": d.mime, "pages": d.pages, "size": d.size_bytes, "sha256": d.sha256},
    )

    st = request.app.state
    if c.settings.task_mode == "inline":
        bg.add_task(process_document, st.db, store, st.audit, d.id, c.request_id, ai=st.ai)
    else:
        await st.arq.enqueue_job("ocr_task", d.id, c.request_id)
    return _out(d)


@router.get("")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: DocStatus | None = None,
    user: CurrentUser = Depends(require(Perm.document_read)),
    s: AsyncSession = Depends(session),
) -> dict:
    q = _visible(user)
    if status:
        q = q.where(Document.status == status)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (await s.execute(q.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [_out(r).model_dump(mode="json") for r in rows],
    }


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.document_read)),
    s: AsyncSession = Depends(session),
) -> DocumentOut:
    return _out(await _get(s, user, document_id))


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    request: Request,
    document_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.document_delete)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> Response:
    d = await _get(s, user, document_id)
    review_ids = select(ReviewDocument.review_id).where(ReviewDocument.document_id == d.id)
    linked = list((await s.execute(review_ids)).scalars())
    if linked:
        await s.execute(delete(ReviewDocument).where(ReviewDocument.review_id.in_(linked)))
        await s.execute(delete(Review).where(Review.id.in_(linked)))
    await s.execute(delete(DocumentFields).where(DocumentFields.document_id == d.id))
    await s.execute(delete(OcrPage).where(OcrPage.document_id == d.id))
    await s.delete(d)
    await s.commit()
    request.app.state.store.delete(d.id)
    await c.audit.record(
        "document.delete",
        "success",
        actor=user.actor,
        resource_type="document",
        resource_id=d.id,
        ip=c.ip,
        request_id=c.request_id,
    )
    return Response(status_code=204)


@router.get("/{document_id}/pages/{page}/image")
async def page_image(
    request: Request,
    document_id: str = Path(pattern=UUID_RE),
    page: int = Path(ge=1, le=100),
    user: CurrentUser = Depends(require(Perm.document_read)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> Response:
    d = await _get(s, user, document_id)
    store = request.app.state.store
    name = f"page-{page}.png"
    if d.pages is None or page > d.pages or not store.exists(d.id, name):
        raise AppError(404, "NOT_FOUND", "页面不存在或尚未渲染")
    png = store.get(d.id, name, store.dek(d.id, d.wrapped_dek))
    await c.audit.record(
        "document.read",
        "success",
        actor=user.actor,
        resource_type="document",
        resource_id=d.id,
        ip=c.ip,
        request_id=c.request_id,
        detail={"page": page},
    )
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "Content-Disposition": "inline"})


@router.get("/{document_id}/recognition")
async def recognition(
    request: Request,
    document_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.document_read)),
    s: AsyncSession = Depends(session),
) -> dict:
    d = await _get(s, user, document_id)
    if d.status != "ready":
        raise AppError(409, "DOCUMENT_NOT_READY", "单证仍在处理中")
    pages = (await s.execute(select(OcrPage).where(OcrPage.document_id == d.id).order_by(OcrPage.page))).scalars().all()
    row = await s.get(DocumentFields, d.id)
    if row is None:
        raise AppError(409, "DOCUMENT_NOT_READY", "字段尚未完成抽取，请重新处理单证")
    return recognition_out(d, pages, row, request.app.state.store)


@router.patch("/{document_id}/fields")
async def patch_fields(
    body: FieldsPatchIn,
    request: Request,
    document_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.document_edit)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> dict:
    return await edit_fields(s, request.app.state.store, c.audit, user, document_id, body, c.request_id)
