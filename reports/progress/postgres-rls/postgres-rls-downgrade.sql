BEGIN;

-- Running downgrade 0002_m2_tenant_rls -> 0001_m2_initial

DROP POLICY tenant_guard ON "demo_tamper_backups";

DROP POLICY tenant_allow ON "demo_tamper_backups";

ALTER TABLE "demo_tamper_backups" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "demo_tamper_backups" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "audit_logs";

DROP POLICY tenant_allow ON "audit_logs";

ALTER TABLE "audit_logs" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "audit_logs" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "chat_messages";

DROP POLICY tenant_allow ON "chat_messages";

ALTER TABLE "chat_messages" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "chat_messages" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "review_documents";

DROP POLICY tenant_allow ON "review_documents";

ALTER TABLE "review_documents" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "review_documents" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "document_fields";

DROP POLICY tenant_allow ON "document_fields";

ALTER TABLE "document_fields" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "document_fields" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "ocr_pages";

DROP POLICY tenant_allow ON "ocr_pages";

ALTER TABLE "ocr_pages" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "ocr_pages" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "refresh_tokens";

DROP POLICY tenant_allow ON "refresh_tokens";

ALTER TABLE "refresh_tokens" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "refresh_tokens" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "reviews";

DROP POLICY tenant_allow ON "reviews";

ALTER TABLE "reviews" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "reviews" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "documents";

DROP POLICY tenant_allow ON "documents";

ALTER TABLE "documents" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "documents" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "users";

DROP POLICY tenant_allow ON "users";

ALTER TABLE "users" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "users" DISABLE ROW LEVEL SECURITY;

DROP POLICY tenant_guard ON "tenants";

DROP POLICY tenant_allow ON "tenants";

ALTER TABLE "tenants" NO FORCE ROW LEVEL SECURITY;

ALTER TABLE "tenants" DISABLE ROW LEVEL SECURITY;

UPDATE alembic_version SET version_num='0001_m2_initial' WHERE alembic_version.version_num = '0002_m2_tenant_rls';

COMMIT;

