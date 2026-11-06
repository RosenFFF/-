"""Transaction-local DB scope. Call only with a server-verified identity.

GUCs are not authentication: the DB principal can SET them. They defend against
missing WHERE clauses, not compromised application credentials/arbitrary SQL.
No ContextVar inheritance, session-wide SET, or all-tenants bypass is supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


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
