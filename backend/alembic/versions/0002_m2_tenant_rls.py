"""Fail-closed PostgreSQL tenant/owner RLS; SQLite has no equivalent.

Frozen policy DDL: do not import live models or runtime policy builders here.
Missing/empty context never grants access; no administrative bypass GUC exists.
"""

from alembic import op

revision = "0002_m2_tenant_rls"
down_revision = "0001_m2_initial"
branch_labels = None
depends_on = None

ORG = "NULLIF(current_setting('app.current_org_id', true), '')"


def policies():
    tenant = f"tenant_id = {ORG}"
    return {
        "tenants": f"id = {ORG}",
        "users": tenant,
        "documents": (
            "tenant_id = NULLIF(current_setting('app.current_org_id', true), '') "
            "AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') "
            "OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) "
            "AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = documents.owner_id "
            "AND u.tenant_id = documents.tenant_id)"
        ),
        "reviews": (
            "tenant_id = NULLIF(current_setting('app.current_org_id', true), '') "
            "AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') "
            "OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) "
            "AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = reviews.owner_id "
            "AND u.tenant_id = reviews.tenant_id)"
        ),
        "refresh_tokens": (
            "user_id = NULLIF(current_setting('app.current_user_id', true), '') AND EXISTS "
            "(SELECT 1 FROM users AS u WHERE u.id = refresh_tokens.user_id "
            "AND u.tenant_id = NULLIF(current_setting('app.current_org_id', true), ''))"
        ),
        "ocr_pages": "EXISTS (SELECT 1 FROM documents AS d WHERE d.id = ocr_pages.document_id)",
        "document_fields": (
            "EXISTS (SELECT 1 FROM documents AS d WHERE d.id = document_fields.document_id) "
            "AND (updated_by IS NULL OR EXISTS "
            "(SELECT 1 FROM users AS u WHERE u.id = document_fields.updated_by))"
        ),
        "review_documents": (
            "EXISTS (SELECT 1 FROM reviews AS r WHERE r.id = review_documents.review_id) "
            "AND EXISTS (SELECT 1 FROM documents AS d WHERE d.id = review_documents.document_id)"
        ),
        "chat_messages": (
            "tenant_id = NULLIF(current_setting('app.current_org_id', true), '') "
            "AND EXISTS (SELECT 1 FROM reviews AS r "
            "WHERE r.id = chat_messages.review_id AND r.tenant_id = chat_messages.tenant_id)"
        ),
        "audit_logs": tenant,
        "demo_tamper_backups": ("EXISTS (SELECT 1 FROM audit_logs AS a WHERE a.id = demo_tamper_backups.log_id)"),
    }


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        # Explicit non-applicability, NOT an emulation of RLS in SQLite.
        return
    for table, predicate in policies().items():
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        # Restrictive guard survives a future additional permissive policy.
        op.execute(f'CREATE POLICY tenant_allow ON "{table}" FOR ALL USING (true) WITH CHECK (true)')
        op.execute(
            f'CREATE POLICY tenant_guard ON "{table}" AS RESTRICTIVE FOR ALL '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for table in reversed(policies()):
        op.execute(f'DROP POLICY tenant_guard ON "{table}"')
        op.execute(f'DROP POLICY tenant_allow ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
