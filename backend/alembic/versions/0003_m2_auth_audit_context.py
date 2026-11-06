"""Narrow pre-auth SELECT capability and platform-private audit chain.

No SECURITY DEFINER, role change, session-wide SET, or all-tenant bypass.
No historical audit rows are rehashed. Legacy shared-chain verification fails
closed until a separately reviewed archival/cutover migration is supplied.
"""

from alembic import op

revision = "0003_m2_auth_audit_context"
down_revision = "0002_m2_tenant_rls"
branch_labels = None
depends_on = None

ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
TENANT = f"tenant_id = {ORG}"


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute('DROP POLICY tenant_guard ON "users"')
    # Exact username is a credential lookup capability, NOT a tenant identity.
    auth = "username = NULLIF(current_setting('app.auth_username', true), '')"
    op.execute(f'CREATE POLICY tenant_guard ON "users" AS RESTRICTIVE FOR SELECT USING ({TENANT} OR ({auth}))')
    for cmd in ("INSERT", "UPDATE", "DELETE"):
        using = f"USING ({TENANT})" if cmd != "INSERT" else ""
        check = f"WITH CHECK ({TENANT})" if cmd != "DELETE" else ""
        op.execute(f'CREATE POLICY tenant_{cmd.lower()} ON "users" AS RESTRICTIVE FOR {cmd} {using} {check}')
    op.execute('DROP POLICY tenant_guard ON "audit_logs"')
    platform = "tenant_id IS NULL AND actor_id IS NULL AND current_setting('app.audit_platform', true) = '1'"
    op.execute(
        f'CREATE POLICY tenant_guard ON "audit_logs" AS RESTRICTIVE FOR ALL '
        f"USING ({TENANT} OR ({platform})) WITH CHECK ({TENANT} OR ({platform}))"
    )


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    for name in ("tenant_guard", "tenant_insert", "tenant_update", "tenant_delete"):
        op.execute(f'DROP POLICY {name} ON "users"')
    op.execute(f'CREATE POLICY tenant_guard ON "users" AS RESTRICTIVE FOR ALL USING ({TENANT}) WITH CHECK ({TENANT})')
    op.execute('DROP POLICY tenant_guard ON "audit_logs"')
    op.execute(
        f'CREATE POLICY tenant_guard ON "audit_logs" AS RESTRICTIVE FOR ALL USING ({TENANT}) WITH CHECK ({TENANT})'
    )
