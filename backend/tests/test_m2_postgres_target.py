"""Offline guard tests only: these do not count as PostgreSQL live evidence."""

import pytest

from .postgres import UnsafePostgresTarget, disposable_postgres_url


def test_absent_and_sqlite_url_do_not_enable_live_postgres():
    assert disposable_postgres_url({}) is None
    assert disposable_postgres_url({"DATABASE_URL": "sqlite+aiosqlite:///:memory:"}) is None


@pytest.mark.parametrize("scheme", ["postgresql", "postgres", "postgresql+asyncpg"])
def test_local_disposable_url_normalized_without_logging(scheme):
    result = disposable_postgres_url(
        {
            "DATABASE_URL": scheme + "://local_owner@127.0.0.1/st143_m2_test_acceptance",
            "TEST_POSTGRES_DISPOSABLE": "1",
        }
    )
    assert result.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    "values",
    [
        {"DATABASE_URL": "postgresql://localhost/st143_m2_test_acceptance"},
        {"DATABASE_URL": "postgresql://localhost/production", "TEST_POSTGRES_DISPOSABLE": "1"},
        {"DATABASE_URL": "postgresql://remote.invalid/st143_m2_test_acceptance", "TEST_POSTGRES_DISPOSABLE": "1"},
        {
            "DATABASE_URL": "postgresql://localhost/st143_m2_test_acceptance?host=remote.invalid",
            "TEST_POSTGRES_DISPOSABLE": "1",
        },
        {"DATABASE_URL": "postgresql://localhost/st143_m2_test_acceptance?port=9999", "TEST_POSTGRES_DISPOSABLE": "1"},
        {"TEST_POSTGRES_URL": "sqlite+aiosqlite:///:memory:", "TEST_POSTGRES_DISPOSABLE": "1"},
        {"DATABASE_URL": "not-a-url", "TEST_POSTGRES_DISPOSABLE": "1"},
    ],
)
def test_unsafe_targets_fail_closed(values):
    with pytest.raises(UnsafePostgresTarget):
        disposable_postgres_url(values)


def test_explicit_test_url_preferred_and_unix_socket_allowed():
    result = disposable_postgres_url(
        {
            "DATABASE_URL": "postgresql://remote.invalid/production",
            "TEST_POSTGRES_URL": "postgresql:///st143_m2_test_acceptance?host=/tmp",
            "TEST_POSTGRES_DISPOSABLE": "1",
        }
    )
    assert "remote.invalid" not in result and "host=%2Ftmp" in result
