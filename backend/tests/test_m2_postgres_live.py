"""REAL PostgreSQL acceptance harness; not evidence until this module actually runs.

Redis, OCR and LLM use declared test fixtures. The raw-SQL case is a NEGATIVE
RLS baseline: passing it demonstrates missing DB isolation, NOT RLS acceptance.
"""

import fakeredis.aioredis
import pytest
from sqlalchemy import text

from app.main import create_app

from . import test_m2_audit_isolation as isolation
from .conftest import Api, _seed, make_settings
from .fakes import FakeLLM
from .test_m1_pipeline import _report, quick_ocr  # noqa: F401
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


@pytest.mark.usefixtures("quick_ocr")
async def test_postgres_current_rls_absent_raw_sql_bypasses_application_scope(postgres_api):
    """A reproducible bypass detector for the CURRENT no-RLS implementation.

    Once RLS is implemented, this baseline MUST fail and be replaced by enforced
    same/foreign-tenant SELECT/INSERT/UPDATE/DELETE + transaction reset tests.
    """
    api = postgres_api
    api.app.state.ai.llm = FakeLLM()
    owner = await api.login("reviewer")
    me = (await owner.get("/api/v1/auth/me")).json()
    doc_id, review_id, _ = await _report(api, owner)
    foreign, actor = await isolation.foreign_admin(api)
    try:
        assert (await foreign.get(f"/api/v1/documents/{doc_id}")).status_code == 404
        assert (await foreign.get(f"/api/v1/reviews/{review_id}")).status_code == 404
        assert (await foreign.get("/api/v1/audit/logs")).json()["items"] == []
        async with api.app.state.db.engine.begin() as conn:
            protected = (
                await conn.execute(
                    text("""
                SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE relnamespace=current_schema()::regnamespace AND relkind='r'
                AND relname <> 'alembic_version' ORDER BY relname
            """)
                )
            ).all()
            assert len(protected) == 11
            assert all(not row.relrowsecurity and not row.relforcerowsecurity for row in protected)
            # Custom GUCs alone are NOT policies. Use a foreign tenant context and
            # deliberately omit application WHERE clauses, bypassing no API auth.
            await conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": actor.tenant_id})
            await conn.execute(text("SELECT set_config('app.user_id', :actor, true)"), {"actor": actor.id})
            docs = (await conn.execute(text("SELECT id FROM documents"))).scalars().all()
            reviews = (await conn.execute(text("SELECT id FROM reviews"))).scalars().all()
            audit_tenants = (await conn.execute(text("SELECT DISTINCT tenant_id FROM audit_logs"))).scalars().all()
            assert doc_id in docs and review_id in reviews and me["tenant_id"] in audit_tenants
    finally:
        await owner.aclose()
        await foreign.aclose()
