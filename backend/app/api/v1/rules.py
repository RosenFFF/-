from fastapi import APIRouter, Depends, Path, Request

from app.core.errors import AppError
from app.deps import CurrentUser, current_user

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/{rule_id}")
async def rule(request: Request, rule_id: str = Path(max_length=64), _: CurrentUser = Depends(current_user)) -> dict:
    result = request.app.state.ai.rag.detail(rule_id)
    if result is None:
        raise AppError(404, "NOT_FOUND", "规则不存在")
    return result
