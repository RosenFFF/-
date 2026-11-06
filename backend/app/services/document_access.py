from __future__ import annotations

from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import Document
from app.security.rbac import Role


def visible_documents(user):
    q = select(Document).where(Document.tenant_id == user.tenant_id)
    if user.role == Role.reviewer:
        q = q.where(Document.owner_id == user.id)
    return q


async def get_document(s, user, doc_id: str) -> Document:
    d = (await s.execute(visible_documents(user).where(Document.id == doc_id))).scalar_one_or_none()
    if d is None:
        raise AppError(404, "NOT_FOUND", "单证不存在")
    return d
