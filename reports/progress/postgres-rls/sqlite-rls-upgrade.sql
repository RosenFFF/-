-- Running upgrade 0001_m2_initial -> 0002_m2_tenant_rls

UPDATE alembic_version SET version_num='0002_m2_tenant_rls' WHERE alembic_version.version_num = '0001_m2_initial';

