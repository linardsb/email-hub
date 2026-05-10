# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedFunction=false
"""Integration harness for cross-feature tests under `app/tests/`.

Provides a session-scoped Postgres engine (`_integration_engine`) and a
per-test `db` fixture (`AsyncSession` with `TRUNCATE ... RESTART IDENTITY
CASCADE` on entry) so cross-entity regression tests like
`test_tenant_isolation.py` can run against a real DB without bespoke
infrastructure in every test module.

Activation
----------
- Set `TEST_DATABASE__URL=postgresql+asyncpg://…` (CI does this in the
  `integration` job; locally run via `make test-integration`).
- Without the env var, every test under `app/tests/` using the `db` fixture
  module-skips at collection — the unit-test job stays Postgres-free.

Schema source
-------------
Schema comes from `alembic upgrade head` against the test DB, not
`Base.metadata.create_all`. This is intentional: drift between models and
migrations (tracked under `tech-debt-19`) is one of the failure modes this
harness is meant to surface. Using `metadata.create_all` would mask it.

Per-test isolation
------------------
TRUNCATE-with-CASCADE on all model tables (in reverse-dependency order)
before each test. RESTART IDENTITY resets sequences so id=1 is stable
test-to-test. CASCADE handles FK chains without enumerating topology.
Tables created by migrations but not present in `Base.metadata` (e.g.
`alembic_version`) are intentionally left alone — they belong to the
schema, not the test data.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture(scope="session")
async def _integration_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped engine pointed at `TEST_DATABASE__URL`.

    Runs `alembic upgrade head` once on entry so the harness validates
    against the same migration-derived schema CI/production sees. Yields
    the engine for per-test fixtures; disposes on teardown.
    """
    url = os.environ.get("TEST_DATABASE__URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE__URL not set — integration harness inactive. "
            "Run via `make test-integration`.",
            allow_module_level=True,
        )

    # alembic.command.upgrade is sync; run it inline at session start before
    # any async work. Driver-suffix (`+asyncpg`) must be stripped for
    # alembic's sync env.py.
    from alembic.config import Config as AlembicConfig

    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(url, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(_integration_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test `AsyncSession` with TRUNCATE-on-entry isolation.

    Reverse-sorts tables by FK dependency so CASCADE has the cleanest path.
    Single TRUNCATE statement is ~10x faster than per-table deletes against
    a populated test DB.
    """
    sm = async_sessionmaker(_integration_engine, expire_on_commit=False, class_=AsyncSession)
    table_list = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with sm() as session:
        await session.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
        await session.commit()
        yield session
