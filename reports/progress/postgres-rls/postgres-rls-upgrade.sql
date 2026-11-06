BEGIN;

-- Running upgrade 0001_m2_initial -> 0002_m2_tenant_rls

ALTER TABLE "tenants" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "tenants" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "tenants" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "tenants" AS RESTRICTIVE FOR ALL USING (id = NULLIF(current_setting('app.current_org_id', true), '')) WITH CHECK (id = NULLIF(current_setting('app.current_org_id', true), ''));

ALTER TABLE "users" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "users" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "users" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "users" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), ''));

ALTER TABLE "documents" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "documents" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "documents" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "documents" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = documents.owner_id AND u.tenant_id = documents.tenant_id)) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = documents.owner_id AND u.tenant_id = documents.tenant_id));

ALTER TABLE "reviews" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "reviews" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "reviews" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "reviews" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = reviews.owner_id AND u.tenant_id = reviews.tenant_id)) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND (owner_id = NULLIF(current_setting('app.current_user_id', true), '') OR NULLIF(current_setting('app.current_role', true), '') IN ('admin', 'auditor')) AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = reviews.owner_id AND u.tenant_id = reviews.tenant_id));

ALTER TABLE "refresh_tokens" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "refresh_tokens" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "refresh_tokens" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "refresh_tokens" AS RESTRICTIVE FOR ALL USING (user_id = NULLIF(current_setting('app.current_user_id', true), '') AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = refresh_tokens.user_id AND u.tenant_id = NULLIF(current_setting('app.current_org_id', true), ''))) WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '') AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = refresh_tokens.user_id AND u.tenant_id = NULLIF(current_setting('app.current_org_id', true), '')));

ALTER TABLE "ocr_pages" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "ocr_pages" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "ocr_pages" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "ocr_pages" AS RESTRICTIVE FOR ALL USING (EXISTS (SELECT 1 FROM documents AS d WHERE d.id = ocr_pages.document_id)) WITH CHECK (EXISTS (SELECT 1 FROM documents AS d WHERE d.id = ocr_pages.document_id));

ALTER TABLE "document_fields" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "document_fields" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "document_fields" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "document_fields" AS RESTRICTIVE FOR ALL USING (EXISTS (SELECT 1 FROM documents AS d WHERE d.id = document_fields.document_id) AND (updated_by IS NULL OR EXISTS (SELECT 1 FROM users AS u WHERE u.id = document_fields.updated_by))) WITH CHECK (EXISTS (SELECT 1 FROM documents AS d WHERE d.id = document_fields.document_id) AND (updated_by IS NULL OR EXISTS (SELECT 1 FROM users AS u WHERE u.id = document_fields.updated_by)));

ALTER TABLE "review_documents" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "review_documents" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "review_documents" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "review_documents" AS RESTRICTIVE FOR ALL USING (EXISTS (SELECT 1 FROM reviews AS r WHERE r.id = review_documents.review_id) AND EXISTS (SELECT 1 FROM documents AS d WHERE d.id = review_documents.document_id)) WITH CHECK (EXISTS (SELECT 1 FROM reviews AS r WHERE r.id = review_documents.review_id) AND EXISTS (SELECT 1 FROM documents AS d WHERE d.id = review_documents.document_id));

ALTER TABLE "chat_messages" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "chat_messages" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "chat_messages" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "chat_messages" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND EXISTS (SELECT 1 FROM reviews AS r WHERE r.id = chat_messages.review_id AND r.tenant_id = chat_messages.tenant_id)) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), '') AND EXISTS (SELECT 1 FROM reviews AS r WHERE r.id = chat_messages.review_id AND r.tenant_id = chat_messages.tenant_id));

ALTER TABLE "audit_logs" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "audit_logs" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "audit_logs" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "audit_logs" AS RESTRICTIVE FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_org_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_org_id', true), ''));

ALTER TABLE "demo_tamper_backups" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "demo_tamper_backups" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_allow ON "demo_tamper_backups" FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY tenant_guard ON "demo_tamper_backups" AS RESTRICTIVE FOR ALL USING (EXISTS (SELECT 1 FROM audit_logs AS a WHERE a.id = demo_tamper_backups.log_id)) WITH CHECK (EXISTS (SELECT 1 FROM audit_logs AS a WHERE a.id = demo_tamper_backups.log_id));

UPDATE alembic_version SET version_num='0002_m2_tenant_rls' WHERE alembic_version.version_num = '0001_m2_initial';

COMMIT;

