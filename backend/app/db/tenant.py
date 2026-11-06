"""Transaction-local DB scope. Call only with a server-verified identity.

GUCs are not authentication: the DB principal can SET them. They defend against
missing WHERE clauses, not compromised application credentials/arbitrary SQL.
No ContextVar inheritance, session-wide SET, or all-tenants bypass is supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, with_loader_criteria


@dataclass(frozen=True, slots=True)
class TenantScope:
    org_id: str
    user_id: str
    role: str

    def __post_init__(self):
        for value in (self.org_id, self.user_id):
            if str(UUID(value)) != value:
                raise ValueError("tenant and user IDs must be canonical UUIDs")
        if self.role not in {"admin", "auditor", "reviewer"}:
            raise ValueError("unsupported tenant role")


def scope_values(scope: TenantScope | None) -> dict[str, str]:
    return {
        "org": scope.org_id if scope else "",
        "user": scope.user_id if scope else "",
        "role": scope.role if scope else "",
    }


SCOPE_SQL = text(
    "SELECT set_config('app.current_org_id', :org, true), "
    "set_config('app.current_user_id', :user, true), "
    "set_config('app.current_role', :role, true)"
)


class TenantSession(Session):
    """A fresh session per identity; reapply LOCAL scope after every commit/rollback."""


def bind_scope(session: AsyncSession, scope: TenantScope) -> None:
    # Refuse identity switching even after a commit: the ORM identity map survives.
    if session.in_transaction() or "tenant_scope" in session.info:
        raise RuntimeError("bind a verified scope once, before any SQL, on a fresh session")
    session.info["tenant_scope"] = scope


@event.listens_for(TenantSession, "after_begin")
def _set_scope(session, transaction, connection):
    if connection.dialect.name == "postgresql":
        connection.execute(SCOPE_SQL, scope_values(session.info.get("tenant_scope")))
        connection.execute(
            text("SELECT set_config('app.auth_username', '', true), set_config('app.audit_platform', :platform, true)"),
            {"platform": "1" if session.info.get("audit_platform") else ""},
        )


async def set_local_scope(connection, scope: TenantScope | None) -> None:
    """Raw async connection, BEGIN required. Commit/rollback resets all three GUCs."""
    if not connection.in_transaction():
        raise RuntimeError("BEGIN required before setting transaction-local scope")
    if connection.dialect.name == "postgresql":
        await connection.execute(SCOPE_SQL, scope_values(scope))


async def check_application_role(connection) -> None:
    """Runtime must not have cluster-admin attributes or own/alter its RLS tables.

    Migration/test owner is separate. FORCE protects its ordinary DML too, but
    cannot stop a table owner deliberately issuing DISABLE ROW LEVEL SECURITY.
    """
    if connection.dialect.name != "postgresql":
        return
    role = (
        await connection.execute(
            text("SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname=current_user")
        )
    ).one()
    if any(role):
        raise RuntimeError("application role must be NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
    dangerous_membership = await connection.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE pg_has_role(current_user, oid, 'MEMBER') "
            "AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb))"
        )
    )
    if dangerous_membership:
        raise RuntimeError("application role must not be a member of a privileged PostgreSQL role")
    owns = await connection.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace=current_schema()::regnamespace "
            "AND c.relrowsecurity AND pg_has_role(current_user, c.relowner, 'MEMBER')) "
            "OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname=current_schema() "
            "AND pg_has_role(current_user, n.nspowner, 'MEMBER'))"
        )
    )
    if owns:
        raise RuntimeError("application role must not own or be a member of the RLS table-owner role")


def _criteria(model, predicate):
    return with_loader_criteria(model, predicate, include_aliases=True)


def require_scope(session):
    scope = session.info.get("tenant_scope")
    if session.info.get("scope_required") and scope is None and not session.info.get("audit_platform"):
        raise RuntimeError("verified tenant context required before SQL")
    return scope


@event.listens_for(TenantSession, "do_orm_execute")
def _guard_queries(state):
    """Application-session defense on both engines; NOT SQLite database-level RLS.

    Maintenance/migration sessionmaker is deliberately separate from request/job sessions.
    Raw SQL is forbidden in scoped ORM sessions: use a reviewed connection capability.
    """
    scope = require_scope(state.session)
    if not state.session.info.get("scope_required"):
        return
    if not state.is_orm_statement:
        raise RuntimeError("raw SQL is not allowed in application sessions")
    from app.db.models import (
        AuditLog,
        ChatMessage,
        DemoTamperBackup,
        Document,
        DocumentFields,
        OcrPage,
        RefreshToken,
        Review,
        ReviewDocument,
        Tenant,
        User,
    )

    if scope is None:  # Platform-only audit capability; never a tenant bypass.
        state.statement = state.statement.options(_criteria(AuditLog, AuditLog.tenant_id.is_(None)))
        if any(d.get("entity") is not AuditLog for d in state.statement.column_descriptions):
            raise RuntimeError("platform audit session cannot query business tables")
        return
    org, user = scope.org_id, scope.user_id
    if state.session.info.get("credential_only"):
        if not state.is_select or any(d.get("entity") is not User for d in state.statement.column_descriptions):
            raise RuntimeError("credential session cannot query business data")
        state.statement = state.statement.options(_criteria(User, User.id == user))
    for model in (User, Document, Review, AuditLog):
        state.statement = state.statement.options(_criteria(model, model.tenant_id == org))
    state.statement = state.statement.options(_criteria(Tenant, Tenant.id == org))
    state.statement = state.statement.options(
        _criteria(RefreshToken, RefreshToken.user_id == user),
        _criteria(ChatMessage, ChatMessage.tenant_id == org),
    )
    docs = select(Document.id).where(Document.tenant_id == org)
    reviews = select(Review.id).where(Review.tenant_id == org)
    if scope.role == "reviewer":
        docs = docs.where(Document.owner_id == user)
        reviews = reviews.where(Review.owner_id == user)
    for model in (OcrPage, DocumentFields):
        state.statement = state.statement.options(_criteria(model, model.document_id.in_(docs)))
    state.statement = state.statement.options(
        _criteria(ReviewDocument, ReviewDocument.review_id.in_(reviews) & ReviewDocument.document_id.in_(docs)),
        _criteria(ChatMessage, ChatMessage.review_id.in_(reviews)),
        _criteria(DemoTamperBackup, DemoTamperBackup.log_id.in_(select(AuditLog.id).where(AuditLog.tenant_id == org))),
    )
    if scope.role == "reviewer":
        for model in (Document, Review):
            state.statement = state.statement.options(_criteria(model, model.owner_id == user))


@event.listens_for(TenantSession, "before_flush")
def _guard_writes(session, flush_context, instances):
    scope = require_scope(session)
    if not session.info.get("scope_required"):
        return
    from app.db.models import (
        AuditLog,
        ChatMessage,
        DemoTamperBackup,
        Document,
        DocumentFields,
        OcrPage,
        RefreshToken,
        Review,
        ReviewDocument,
        Tenant,
        User,
    )

    for row in session.new | session.dirty | session.deleted:
        if session.info.get("credential_only"):
            allowed = {"failed_logins", "locked_until", "last_login_at"}
            changed = {a.key for a in inspect(row).attrs if a.history.has_changes()}
            if not isinstance(row, User) or row.id != scope.user_id or row not in session.dirty or changed - allowed:
                raise RuntimeError("credential session can only update authentication counters")
        if scope is None:
            if not isinstance(row, AuditLog) or row.tenant_id is not None or row.actor_id is not None:
                raise RuntimeError("platform audit session cannot write tenant data")
        elif hasattr(row, "tenant_id") and row.tenant_id != scope.org_id:
            raise RuntimeError("cross-tenant write denied")
        elif isinstance(row, AuditLog) and row in session.new and row.actor_id != scope.user_id:
            raise RuntimeError("audit actor does not match context")
        elif isinstance(row, Tenant) and row.id != scope.org_id:
            raise RuntimeError("cross-tenant write denied")
        elif isinstance(row, RefreshToken) and row.user_id != scope.user_id:
            raise RuntimeError("cross-user refresh write denied")
        elif isinstance(row, (Document, Review)) and scope.role == "reviewer" and row.owner_id != scope.user_id:
            raise RuntimeError("cross-owner write denied")

        if scope is not None:
            # SQL reads use this same scoped session: no foreign-parent inference.
            parents = []
            if isinstance(row, (OcrPage, DocumentFields, ReviewDocument)):
                parents.append((Document, row.document_id))
            if isinstance(row, (ChatMessage, ReviewDocument)):
                parents.append((Review, row.review_id))
            if isinstance(row, DemoTamperBackup):
                parents.append((AuditLog, row.log_id))
            if isinstance(row, (Document, Review)):
                parents.append((User, row.owner_id))
            for model, identifier in parents:
                # Pending parent objects can occur during review creation.
                pending = any(
                    isinstance(p, model)
                    and getattr(p, "id", None) == identifier
                    and getattr(p, "tenant_id", None) == scope.org_id
                    for p in session.new
                )
                parent = session.scalar(select(model).where(model.id == identifier).execution_options(autoflush=False))
                if parent is None and not pending:
                    raise RuntimeError("cross-tenant/owner parent denied")
