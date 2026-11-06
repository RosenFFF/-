-- Running upgrade 0002_m2_tenant_rls -> 0003_m2_auth_audit_context

UPDATE alembic_version SET version_num='0003_m2_auth_audit_context' WHERE alembic_version.version_num = '0002_m2_tenant_rls';

