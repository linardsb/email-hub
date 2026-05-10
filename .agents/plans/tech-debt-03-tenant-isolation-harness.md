# Tech-Debt 03 — Tenant-Isolation Integration Harness

**Cluster:** C (soft severity, but unblocks Cluster D's regression net).
**Closes:** `tech-debt-03-tenant-isolation-regression-harness`.
**Branch:** `tech-debt/03-tenant-iso-harness`.
**Estimated effort:** 1 session (most of the work is fixture plumbing; the test
file already exists).

## Problem

`app/tests/test_tenant_isolation.py` is the cross-entity regression test for
`scoped_access` filtering — it's the load-bearing net that catches the
"someone wrote a new repo without a scope filter" failure mode (the F001/F002
fail-loud `RuntimeError` covers the *forgot-to-swap-get_db* case but not the
*new-repo-with-no-scope-filter* case).

Today the test self-skips on `pytest.skip("TEST_DATABASE__URL not set …")`
(line 56–57) and 4 of its 6 entity rows are `xfail(strict=True)` because the
payload schemas were never wired. The fixture (`db: AsyncSession`) is a stub.
The whole regression net is dormant.

The deferred-items entry says it closes when:
- A `db: AsyncSession` fixture lands (per-test isolated Postgres schema or
  truncate-between-tests) under `app/tests/conftest.py` or root `conftest.py`.
- The test runs green in CI without the `TEST_DATABASE__URL` gate.
- The 4 `xfail(strict=True)` entries (templates / memory / qa_results /
  approvals) get promoted to plain `id=...`.

## Approach

Two viable harness shapes — pick **truncate-between-tests**, not per-test
schema:

| Option | Setup cost | Run cost | Why I'm not picking it |
|---|---|---|---|
| Per-test isolated schema (`CREATE SCHEMA test_<uuid>`) | Each test creates+drops a schema; runs `Base.metadata.create_all` against the schema | High (~3-5s per test) | Slow, and current models use the public schema everywhere — switching `search_path` per session adds a footgun for mixed unit+integration runs |
| Truncate-between-tests on a dedicated DB | One-time `Base.metadata.create_all`; per-test `TRUNCATE … CASCADE` on all tables | ~50-100ms per test | Picked. Matches existing `app/tests/factories.py` pattern (`seed_org` etc. assume tables exist and are empty). |

CI infrastructure: a `postgres-tenant-iso` service in `docker-compose.test.yml`
on port 5433, with `TEST_DATABASE__URL=postgresql+asyncpg://…@localhost:5433/test`
exported in CI. Runs only on the `make test-integration` target — the unit
suite stays Postgres-free.

## Files

| File | Change |
|---|---|
| `app/tests/conftest.py` (new or extend) | Add session-scoped `_create_schema` fixture + per-test `db` fixture with truncation |
| `app/tests/test_tenant_isolation.py` | Replace skip-on-no-URL fixture with the new shared one; promote 4 xfails by wiring the missing payloads |
| `app/tests/factories.py` | Add `make_template_payload`, `make_memory_payload`, `make_qa_result_payload`, `make_approval_payload` helpers |
| `Makefile` | Add `test-integration` target (or extend existing) that exports `TEST_DATABASE__URL` and runs the integration job |
| `docker-compose.test.yml` | Add `postgres-tenant-iso` service on port 5433 (if not already there) |
| `.github/workflows/ci.yml` | Wire the integration job to the new compose service |

## Steps

### 1. Pre-flight

```bash
git checkout -b tech-debt/03-tenant-iso-harness
make check
rg -n "TEST_DATABASE__URL|tenant_isolation" app/tests/ conftest.py
```

Read `app/tests/factories.py` end-to-end (it's the existing pattern).
`seed_org` / `seed_user` / `auth_header` already exist; the gap is **payload
factories** for templates / memory / qa_results / approvals.

### 2. Shared `db` fixture in `app/tests/conftest.py`

Either create the file or extend if it exists:

```python
"""Shared fixtures for app/tests/ — integration harness for tenant isolation."""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base


@pytest_asyncio.fixture(scope="session")
async def _integration_engine():
    """Session-scoped engine. Schema comes from `alembic upgrade head` so the
    harness tests against the real migration-derived schema (not the
    model-derived one). This matters because `tech-debt-19` is fixing drift
    between those two: running `Base.metadata.create_all` here would mask the
    same drift this harness is meant to catch.

    Skips the entire integration job on no DB.
    """
    url = os.environ.get("TEST_DATABASE__URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE__URL not set — integration harness inactive. "
            "Run via `make test-integration`.",
            allow_module_level=True,
        )

    # Run alembic upgrade head against the test DB before opening the engine.
    # Use alembic.command rather than shelling out so local + CI use the same
    # code path; respects the project's alembic.ini and env.py.
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url.replace("+asyncpg", ""))
    command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(url, future=True)
    yield engine
    # No drop_all — leave schema in place for re-runs; truncation handles
    # per-test isolation. CI tears down the whole Postgres container anyway.
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_integration_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test session with TRUNCATE on entry — fast isolation."""
    sm = async_sessionmaker(_integration_engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        # TRUNCATE all tables in dependency order via a single statement.
        # `RESTART IDENTITY` resets sequences so id=1 is stable test-to-test.
        # `CASCADE` handles FKs without us listing the topology.
        all_tables = ", ".join(
            f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
        )
        await session.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        await session.commit()
        yield session
```

The `pytest.skip(allow_module_level=True)` bails the entire collection when the
DB isn't reachable, so `make test` (unit job) doesn't try to truncate anything.

### 3. Replace the local `db` fixture in `test_tenant_isolation.py`

Delete lines 46–62 (the local stub). The shared fixture from §2 takes over by
name. The `pytestmark = [integration, tenant_isolation]` line stays — those
markers control the autouse `_override_scoped_db` opt-out in root `conftest.py`.

### 4. Wire the 4 xfail entities

For each of `templates`, `memory`, `qa_results`, `approvals`, read the existing
POST-route schema and add a payload factory in `app/tests/factories.py`.
Example:

```python
def make_template_payload(org_id: int) -> dict[str, object]:
    return {
        "name": "iso-test-template",
        "client_org_id": org_id,
        "html": "<p>hi</p>",
        # … any other required fields per TemplateCreate schema
    }
```

Then update `ENTITY_FIXTURES` in `test_tenant_isolation.py`:

```python
ENTITY_FIXTURES: dict[str, dict[str, Any]] = {
    "projects": { … },  # already wired
    "templates": {
        "list_path": "/api/v1/templates",
        "get_path": "/api/v1/templates/{id}",
        "create_payload": lambda org_id: make_template_payload(org_id),
    },
    "memory": { … },
    "qa_results": { … },
    "approvals": { … },
}
```

And drop the `xfail(strict=True)` markers from those 4 `pytest.param` entries.
**Keep `briefs`** as `xfail(strict=False, reason="briefs are BOLA-by-creator")`
— the entry's note is correct; briefs need a user-isolation variant test, not
the org-isolation pattern. That variant is out of scope for this plan but worth
adding as a follow-up TODO.

### 5. Compose service + Makefile target

`docker-compose.test.yml` (extend or create the integration service):

```yaml
services:
  postgres-tenant-iso:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: test
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d test"]
      interval: 2s
      retries: 30
```

`Makefile` — add or extend. Note: alembic upgrade is run by the fixture, not
the Makefile, so local and CI go through the same code path:

```makefile
.PHONY: test-integration
test-integration:
	docker compose -f docker-compose.test.yml up -d postgres-tenant-iso
	docker compose -f docker-compose.test.yml exec -T postgres-tenant-iso \
		bash -c 'until pg_isready -U postgres -d test; do sleep 1; done'
	TEST_DATABASE__URL=postgresql+asyncpg://postgres:postgres@localhost:5433/test \
		uv run pytest -m integration -q
```

### 6. CI integration

Add an `integration` job to `.github/workflows/ci.yml`:

```yaml
integration:
  name: Integration tests (tenant isolation)
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:16-alpine
      env:
        POSTGRES_DB: test
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres
      ports:
        - 5433:5432
      options: >-
        --health-cmd pg_isready
        --health-interval 2s
        --health-retries 30
  steps:
    - uses: actions/checkout@v6
    - uses: astral-sh/setup-uv@v7
    - run: uv python install
    - run: uv sync
    - name: Tenant isolation
      env:
        # Fixture runs `alembic upgrade head` itself — no separate migrate step.
        TEST_DATABASE__URL: postgresql+asyncpg://postgres:postgres@localhost:5433/test
      run: uv run pytest app/tests/test_tenant_isolation.py -v
```

### 7. Verify

```bash
make test-integration                 # local
# In CI, the new integration job must run and pass.
```

The 5 entity rows (projects, templates, memory, qa_results, approvals) must
all run; the briefs row must `xfail(strict=False)`. **No skips.** If any row
skips, the harness isn't actually wired.

### 8. PR checklist

- [ ] `.agents/deferred-items.json` — close `tech-debt-03-tenant-isolation-regression-harness`.
- [ ] `.agents/plans/deferred-items-tracker.md` — strike Cluster C.
- [ ] `make check-full` + `make test-integration` green.
- [ ] CI's `integration` job present and required for merge.
- [ ] Briefs follow-up TODO recorded as a new deferred-items entry (BOLA-by-creator
      isolation test) before this PR closes, so the gap doesn't disappear.

## Out of scope

- Promoting `briefs` from `xfail(strict=False)` to a green test — needs a
  user-isolation pattern (not org-isolation). Track as a new soft deferred entry.
- Migrating the integration harness off Postgres-in-Docker to a managed test
  DB. Current setup is fine; revisit only if CI runtimes balloon.
