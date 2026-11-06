from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from alembic import command


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        self.is_postgres = url.startswith("postgresql")

    @staticmethod
    def migration_config() -> Config:
        root = Path(__file__).resolve().parents[2]
        return Config(str(root / "alembic.ini"))

    async def migrate(self) -> None:
        """Explicit migration command; startup never races DDL among production workers."""

        def upgrade(connection):
            config = self.migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with self.engine.begin() as connection:
            await connection.run_sync(upgrade)

    async def adopt_legacy_schema(self) -> None:
        """Stamp only a complete, identical legacy schema; no blind stamp or auto-DDL."""
        from app.db import models  # noqa: F401

        def adopt(connection):
            context = MigrationContext.configure(connection)
            if context.get_current_heads() or compare_metadata(context, Base.metadata):
                raise RuntimeError("Legacy schema differs or is already versioned; manual migration review required")
            inspector = inspect(connection)
            for table in Base.metadata.sorted_tables:
                actual = inspector.get_pk_constraint(table.name)["constrained_columns"]
                expected = [column.name for column in table.primary_key]
                if actual != expected:
                    raise RuntimeError("Legacy schema primary key differs; manual migration review required")
            config = self.migration_config()
            config.attributes["connection"] = connection
            command.stamp(config, "head")

        async with self.engine.begin() as connection:
            await connection.run_sync(adopt)

    async def check_migrated(self) -> None:
        def check(connection):
            current = MigrationContext.configure(connection).get_current_heads()
            heads = ScriptDirectory.from_config(self.migration_config()).get_heads()
            if set(current) != set(heads):
                raise RuntimeError("Database migration required: run alembic upgrade head before startup")

        async with self.engine.connect() as connection:
            await connection.run_sync(check)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s:
            yield s

    async def dispose(self) -> None:
        await self.engine.dispose()
