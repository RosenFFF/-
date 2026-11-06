from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import StrictModel
from app.core.errors import AppError
from app.db.models import Review
from app.deps import Ctx, CurrentUser, ctx, enforce_rate, require, session
from app.security.rbac import Perm, Role
from app.services.review import create_review_record, process_review, review_out

from .documents import UUID_RE
from .schemas import Language

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewIn(StrictModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=10)
    destination_country: str = Field(pattern=r"^[A-Z]{2}$")
    origin_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    language: Language = "zh-CN"

    @field_validator("document_ids")
    @classmethod
    def _unique(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("单证ID不能重复")
        return value


def _visible(user):
    q = select(Review).where(Review.tenant_id == user.tenant_id)
    if user.role == Role.reviewer:
        q = q.where(Review.owner_id == user.id)
    return q


async def _get(s, user, review_id):
    row = (await s.execute(_visible(user).where(Review.id == review_id))).scalar_one_or_none()
    if row is None:
        raise AppError(404, "NOT_FOUND", "审查不存在")
    return row


@router.post("", status_code=202)
async def create_review(
    body: ReviewIn,
    request: Request,
    bg: BackgroundTasks,
    user: CurrentUser = Depends(require(Perm.review_create)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> dict:
    await enforce_rate(c, f"review:{user.id}", c.settings.rl_review_per_min, user.actor)
    row = await create_review_record(s, user, body, c.audit, c.request_id)
    st = request.app.state
    if c.settings.task_mode == "inline":
        bg.add_task(process_review, st.db, st.store, st.audit, st.ai, row.id, c.request_id)
    else:
        await st.arq.enqueue_job("review_task", row.id, c.request_id)
    return review_out(row)


@router.get("")
async def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str | None = Query(default=None, pattern=r"^(pass|low|medium|high)$"),
    user: CurrentUser = Depends(require(Perm.review_read)),
    s: AsyncSession = Depends(session),
) -> dict:
    q = _visible(user)
    if risk_level:
        q = q.where(Review.risk_level == risk_level)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (await s.execute(q.order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return {"page": page, "page_size": page_size, "total": total, "items": [review_out(row) for row in rows]}


@router.get("/{review_id}")
async def get_review(
    review_id: str = Path(pattern=UUID_RE),
    language: Language | None = None,
    user: CurrentUser = Depends(require(Perm.review_read)),
    c: Ctx = Depends(ctx),
    s: AsyncSession = Depends(session),
) -> dict:
    row = await _get(s, user, review_id)
    if language is not None and language != row.language:
        raise AppError(501, "MODEL_UNAVAILABLE", "M1 暂不支持报告二次翻译；请创建指定语言的新审查")
    await c.audit.record(
        "review.read", "success", actor=user.actor, resource_type="review", resource_id=row.id, request_id=c.request_id
    )
    return review_out(row)


@router.get("/{review_id}/messages")
async def messages(
    review_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.review_read)),
    s: AsyncSession = Depends(session),
):
    await _get(s, user, review_id)
    raise AppError(501, "MODEL_UNAVAILABLE", "M1 暂未实现追问历史")


@router.post("/{review_id}/messages")
async def post_message(
    review_id: str = Path(pattern=UUID_RE),
    user: CurrentUser = Depends(require(Perm.chat_write)),
    s: AsyncSession = Depends(session),
):
    await _get(s, user, review_id)
    raise AppError(501, "MODEL_UNAVAILABLE", "M1 暂未实现追问/SSE")
