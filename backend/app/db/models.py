from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(128))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(32), default="unknown")
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    pages: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    wrapped_dek: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OcrPage(Base):
    __tablename__ = "ocr_pages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    blocks: Mapped[list] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)


class AuditLog(Base):
    """只追加的审计日志；hash = sha256(prev_hash + 规范化记录)，形成哈希链。"""

    __tablename__ = "audit_logs"
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, default=uid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(48), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class DemoTamperBackup(Base):
    """仅 DEMO_MODE 使用：保存被篡改记录的原始内容，便于演示后恢复。"""

    __tablename__ = "demo_tamper_backups"
    log_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


JSON_DATA = JSON().with_variant(JSONB(), "postgresql")


class DocumentFields(Base):
    __tablename__ = "document_fields"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(16))
    # Encrypted JSON envelope, never the transient PII placeholder mapping.
    fields: Mapped[dict] = mapped_column(JSON_DATA)
    models: Mapped[list] = mapped_column(JSON_DATA, default=list)
    security: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    degrade_level: Mapped[str] = mapped_column(String(2), default="L3")
    aigc_meta: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    document_ids: Mapped[list] = mapped_column(JSON_DATA)
    destination_country: Mapped[str] = mapped_column(String(2))
    origin_country: Mapped[str | None] = mapped_column(String(2))
    language: Mapped[str] = mapped_column(String(8), default="zh-CN")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    risk_level: Mapped[str | None] = mapped_column(String(8))
    summary: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[list] = mapped_column(JSON_DATA, default=list)
    models: Mapped[list] = mapped_column(JSON_DATA, default=list)
    security: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    degrade_level: Mapped[str] = mapped_column(String(2), default="L3")
    aigc_meta: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    progress: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewDocument(Base):
    __tablename__ = "review_documents"
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    fields_snapshot: Mapped[dict] = mapped_column(JSON_DATA)  # encrypted, immutable input snapshot
    doc_type: Mapped[str] = mapped_column(String(32))


class ChatMessage(Base):
    """Only masked chat prose is persisted; no PII placeholder mappings or raw prompts."""

    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    citations: Mapped[list] = mapped_column(JSON_DATA, default=list)
    models: Mapped[list] = mapped_column(JSON_DATA, default=list)
    aigc_meta: Mapped[dict] = mapped_column(JSON_DATA, default=dict)
    stream_id: Mapped[str | None] = mapped_column(String(36), index=True)
