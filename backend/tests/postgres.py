"""Opt-in helpers for a LOCAL disposable PostgreSQL acceptance database.

Never print a supplied URL. The schema fixture touches only its random schema;
application data/queries/migrations still use the real asyncpg/PostgreSQL stack.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import make_url


class UnsafePostgresTarget(ValueError):
    pass


def disposable_postgres_url(environ=None) -> str | None:
    environ = os.environ if environ is None else environ
    raw = environ.get("TEST_POSTGRES_URL") or environ.get("DATABASE_URL")
    if not raw:
        return None
    try:
        url = make_url(raw)
    except Exception:
        raise UnsafePostgresTarget("invalid database URL (value withheld)") from None
    # An ordinary SQLite test configuration does not enable the PostgreSQL suite.
    if url.get_backend_name() == "sqlite" and not environ.get("TEST_POSTGRES_URL"):
        return None
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise UnsafePostgresTarget("PostgreSQL URL required (value withheld)")
    if environ.get("TEST_POSTGRES_DISPOSABLE") != "1":
        raise UnsafePostgresTarget("TEST_POSTGRES_DISPOSABLE=1 required; never use a shared database")
    if not (url.database or "").startswith("st143_m2_test_"):
        raise UnsafePostgresTarget("disposable database name must start with st143_m2_test_")
    if url.host not in (None, "", "127.0.0.1", "localhost", "::1"):
        raise UnsafePostgresTarget("only a local PostgreSQL database is permitted")
    # asyncpg accepts host overrides in the query. Only a local socket may override it.
    if set(url.query) - {"host"}:
        raise UnsafePostgresTarget("connection query overrides are not permitted except a local socket host")
    host = url.query.get("host")
    if host and (not isinstance(host, str) or not host.startswith("/") or "," in host):
        raise UnsafePostgresTarget("query host must be a single local Unix socket directory")
    return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
