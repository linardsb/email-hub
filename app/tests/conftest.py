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
Two distinct asyncio hazards drive the shape:

(a) `alembic/env.py::run_migrations_online` calls
    `asyncio.run(run_async_migrations())`. If invoked from inside any
    running event loop it raises `cannot be called from a running event
    loop`. → keep the alembic fixture **sync** so no loop is active.

(b) `app.main:app` is a module-level FastAPI singleton with starlette
    `BaseHTTPMiddleware`. The middleware spawns tasks bound to whatever
    loop the request first arrives on. With the default function-scope
    test loop, test #2's loop sees Futures attached to test #1's now-
    dead loop and asyncpg raises `Future attached to a different loop`.
    → tenant-isolation tests run on a **session-scoped event loop**
    (declared at the test module via `pytest.mark.asyncio(loop_scope=
    "session")`). Once the loop is shared session-wide, the engine and
    db fixtures can also be session-scoped.

Layout:

1. `_alembic_upgraded` (sync, session) — alembic upgrade once. Sync so
   env.py's nested `asyncio.run` has no outer loop. Returns the URL.
2. `_integration_engine` (async, session, loop_scope=session) — one
   `AsyncEngine` for the whole session. Connections stay bound to the
   session loop, so no cross-loop affinity issue.
3. `db` (async, function, loop_scope=session) — fresh `AsyncSession`
   per test from the shared engine, TRUNCATE-then-yield.

Per-test isolation
------------------
TRUNCATE-with-CASCADE on all tables actually present in the `public`
schema (looked up via `information_schema`, with `alembic_version`
excluded), before each test. Querying the live schema instead of
`Base.metadata.sorted_tables` is intentional: this harness is meant to
catch model↔migration drift (tech-debt-19), so the truncation list must
come from the migrated DB, not from the ORM model registry — otherwise
a TRUNCATE on a missing-from-migrations table would fail and mask the
drift it should surface. RESTART IDENTITY resets sequences so id=1 is
stable test-to-test. CASCADE handles FK chains without enumerating
topology.
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

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(scope="session")
def _alembic_upgraded() -> str:
    """Sync session fixture: alembic upgrade head, exactly once.

    Sync so it runs outside any pytest-asyncio event loop —
    `alembic/env.py::run_migrations_online` uses
    `async_engine_from_config` + `asyncio.run(run_async_migrations())`
    internally, which would raise `cannot be called from a running
    event loop` if invoked from inside pytest-asyncio's session loop.

    Reads `TEST_DATABASE__URL` for harness activation. Note that
    `alembic/env.py:49` overrides `sqlalchemy.url` with
    `settings.database.url` (i.e. `DATABASE__URL`), so the test runner
    is responsible for setting **both** env vars to the same URL —
    `make test-integration` and the CI `integration` job both do this.
    """
    url = os.environ.get("TEST_DATABASE__URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE__URL not set — integration harness inactive. "
            "Run via `make test-integration`.",
            allow_module_level=True,
        )

    db_url = os.environ.get("DATABASE__URL")
    if db_url != url:
        pytest.skip(
            "DATABASE__URL must match TEST_DATABASE__URL "
            "(alembic/env.py reads settings.database.url). "
            "Run via `make test-integration` which sets both.",
            allow_module_level=True,
        )

    from alembic.config import Config as AlembicConfig

    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    return url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _integration_engine(
    _alembic_upgraded: str,
) -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine.

    `loop_scope="session"` pins the engine to the same event loop the
    session-scoped tests run on (see test module's
    `pytest.mark.asyncio(loop_scope="session")` pytestmark). Without
    that match, the engine's asyncpg connections would be bound to a
    different loop than the tests use and asyncpg would raise
    `Future attached to a different loop`.
    """
    engine = create_async_engine(_alembic_upgraded, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(_integration_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test `AsyncSession` with TRUNCATE-on-entry isolation.

    Resolves the truncation list from `information_schema.tables` so it
    only ever names tables that actually exist in the migrated schema —
    `Base.metadata.sorted_tables` would include model-only tables that
    migrations don't create (model↔migration drift, the very thing this
    harness is meant to catch). `alembic_version` is excluded so the
    migration state survives between tests.

    Single TRUNCATE statement with CASCADE handles FK chains; RESTART
    IDENTITY makes id=1 stable test-to-test.
    """
    sm = async_sessionmaker(_integration_engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        tables = [row[0] for row in result.all()]
        if tables:
            table_list = ", ".join(f'"{t}"' for t in tables)
            await session.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
            await session.commit()
        yield session
