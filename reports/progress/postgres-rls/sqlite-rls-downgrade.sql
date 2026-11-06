-- Running downgrade 0002_m2_tenant_rls -> 0001_m2_initial

UPDATE alembic_version SET version_num='0001_m2_initial' WHERE alembic_version.version_num = '0002_m2_tenant_rls';

