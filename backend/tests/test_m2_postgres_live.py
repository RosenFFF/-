"""REAL PostgreSQL acceptance harness; not evidence until this module actually runs.

Redis, OCR and LLM use declared test fixtures. Raw-SQL RLS enforcement lives
in test_m2_postgres_rls.py. Full API startup is explicitly gated until the
pre-auth/audit/worker paths are integrated; configured execution must fail, not skip.
"""

import fakeredis.aioredis
import pytest
from sqlalchemy import text

from app.main import create_app

from . import test_m2_audit_isolation as isolation
from .conftest import Api, _seed, make_settings
from .test_m1_pipeline import quick_ocr  # noqa: F401
from .test_m2_migrations import assert_migration_roundtrip


@pytest.fixture
async def postgres_api(tmp_path, postgres_test_url):
    settings = make_settings(tmp_path, database_url=postgres_test_url)
    redis = fakeredis.aioredis.FakeRedis()
    app = create_app(settings, redis=redis)
    try:
        async with app.router.lifespan_context(app):
            # RLS claims must never be based on a superuser/BYPASSRLS connection.
            async with app.state.db.engine.connect() as conn:
                role = (
                    await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"))
                ).one()
                assert not role.rolsuper and not role.rolbypassrls, "use a non-superuser NOBYPASSRLS acceptance role"
                assert (await conn.execute(text("SELECT version()"))).scalar().startswith("PostgreSQL ")
            await _seed(app)
            yield Api(app, settings)
    finally:
        await redis.aclose()


async def test_postgres_alembic_schema_parity_idempotence_and_roundtrip(postgres_test_url):
    await assert_migration_roundtrip(postgres_test_url)


@pytest.mark.usefixtures("quick_ocr")
@pytest.mark.parametrize("mode", ["same_org_other_user", "foreign_org_admin"])
async def test_postgres_cross_scope_document_report_messages_replay_and_audit_denied(postgres_api, mode):
    await isolation.test_cross_scope_document_report_history_replay_and_audit_denied(postgres_api, mode)


async def test_postgres_audit_filters_boundaries_and_pagination(postgres_api):
    await isolation.test_audit_time_action_result_actor_filters_pagination_and_validation(postgres_api)


async def test_postgres_audit_tenant_null_events_and_verify_no_foreign_disclosure(postgres_api):
    await isolation.test_audit_tenant_null_events_secrets_and_verify_no_foreign_disclosure(postgres_api)


@pytest.mark.parametrize("window", ["1h", "24h", "7d"])
async def test_postgres_dashboard_stats_and_reviewer_rbac(postgres_api, window):
    await isolation.test_dashboard_stats_tenant_real_events_and_rbac(postgres_api, window)


async def test_postgres_cross_org_demo_target_is_404_without_tampering(postgres_api):
    await isolation.test_cross_org_specific_audit_demo_target_is_404_without_tampering(postgres_api)
