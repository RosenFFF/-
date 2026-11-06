from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.security.rbac import Role


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: Role
    disabled: bool
    last_login_at: datetime | None = None
    created_at: datetime


class CurrentUserOut(UserOut):
    tenant_id: str
    permissions: list[str]


class SessionOut(BaseModel):
    """登录/刷新响应。令牌只在 httpOnly cookie 里，前端脚本拿不到。"""

    expires_in: int
    user: CurrentUserOut


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role


class UserPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    disabled: bool | None = None


DocType = Literal[
    "commercial_invoice", "packing_list", "certificate_of_origin", "customs_declaration", "bill_of_lading", "unknown"
]
DocStatus = Literal["uploaded", "ocr_running", "extracting", "ready", "failed"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    doc_type: DocType
    filename: str
    mime: str
    size_bytes: int
    pages: int | None
    sha256: str
    status: DocStatus
    progress: int
    error: dict | None = None
    owner_id: str
    created_at: datetime
    expire_at: datetime


class Page(BaseModel):
    page: int
    page_size: int
    total: int
