# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedFunction=false
"""Integration harness for cross-feature tests under `app/tests/`.

Provides a per-test `db` fixture (`AsyncSession` with `TRUNCATE ...
RESTART IDENTITY CASCADE` on entry) so cross-entity regression tests
like `test_tenant_isolation.py` can run against a real DB without
bespoke infrastructure in every test module.

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

Fixture topology
----------------
Three layers, scoped to dodge two distinct asyncio/SQLAlchemy hazards:

1. `_alembic_upgraded` (sync, session) — runs `alembic upgrade head`
   exactly once. Sync so it can spin up its own event loop inside
   `alembic/env.py::run_async_migrations` without colliding with
   pytest-asyncio's per-test loop. Returns the URL.
2. `_integration_engine` (async, function) — fresh `AsyncEngine` per
   test with `NullPool`. Session-scoping the engine causes
   `RuntimeError: ... Future attached to a different loop`: pytest-
   asyncio creates a new event loop per test by default, but a
   long-lived engine caches asyncpg connections bound to the loop that
   first opened them. Function-scope + NullPool eliminates both.
3. `db` (async, function) — `AsyncSession` from the per-test engine,
   TRUNCATEs all model tables before yielding.

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
from sqlalchemy.pool import NullPool

from app.core.database import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(scope="session")
def _alembic_upgraded() -> str:
    """Sync session fixture: alembic upgrade head, exactly once.

    Sync so it runs outside any pytest-asyncio event loop —
    `alembic/env.py::run_migrations_online` calls
    `asyncio.run(run_async_migrations())` internally, which would raise
    `cannot be called from a running event loop` if invoked from inside
    pytest-asyncio's session loop. The driver suffix (`+asyncpg`) must
    be stripped for alembic's sync env.

    Returns the original (async-suffix-bearing) URL for engine creation.
    """
    url = os.environ.get("TEST_DATABASE__URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE__URL not set — integration harness inactive. "
            "Run via `make test-integration`.",
            allow_module_level=True,
        )

    from alembic.config import Config as AlembicConfig

    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(alembic_cfg, "head")
    return url


@pytest_asyncio.fixture
async def _integration_engine(
    _alembic_upgraded: str,
) -> AsyncGenerator[AsyncEngine, None]:
    """Per-test async engine with NullPool.

    Function-scoped on purpose: pytest-asyncio's default test loop scope
    is `function` (see pyproject.toml `asyncio_default_test_loop_scope`),
    so a session-scoped engine would cache asyncpg connections bound to
    the first test's now-dead loop. NullPool avoids any connection reuse
    inside the test as well; engine create/dispose costs ~10ms.
    """
    engine = create_async_engine(_alembic_upgraded, future=True, poolclass=NullPool)
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
