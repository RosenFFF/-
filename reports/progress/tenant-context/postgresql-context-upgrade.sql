BEGIN;

-- Running upgrade 0002_m2_tenant_rls -> 0003_m2_auth_audit_context

DROP POLICY tenant_guard ON "users";

CREATE POLICY tenant_guard ON "users" AS RESTRICTIVE FOR SELECT USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') OR (username = NULLIF(current_setting('app.auth_username', true), '')));

CREATE POLICY tenant_insert ON "users" AS RESTRICTIVE FOR INSERT  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), ''));

CREATE POLICY tenant_update ON "users" AS RESTRICTIVE FOR UPDATE USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), ''));

CREATE POLICY tenant_delete ON "users" AS RESTRICTIVE FOR DELETE USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), ''));

DROP POLICY tenant_guard ON "audit_logs";

CREATE POLICY tenant_guard ON "audit_logs" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') OR (tenant_id IS NULL AND actor_id IS NULL AND current_setting('app.audit_platform', true) = '1')) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') OR (tenant_id IS NULL AND actor_id IS NULL AND current_setting('app.audit_platform', true) = '1'));

UPDATE alembic_version SET version_num='0003_m2_auth_audit_context' WHERE alembic_version.version_num = '0002_m2_tenant_rls';

COMMIT;

