# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Cross-entity tenant isolation regression.

Per `.agents/plans/tech-debt-03-multi-tenant-isolation.md` §C this is the
load-bearing regression test. The scoping logic itself (F001/F002) is
already enforced at the repository layer (`scoped_access` raises if a
route forgets to swap to `get_scoped_db`); this file is the cross-entity
*regression net* that would catch a future repo shipping without scoping.

Activation
----------
- `pytestmark = [integration, tenant_isolation]` keeps this out of the
  unit-test job (`-m "not integration"`) and opts out of the autouse
  `scoped_access` / `get_scoped_db` patches in root `conftest.py`.
- The `db` fixture comes from `app/tests/conftest.py` — see that file for
  the alembic-upgrade-head + TRUNCATE-per-test harness.

Per-entity scoping rules
------------------------
Each row in `ENTITY_FIXTURES` exercises three checks against the entity
created by `user1`:

1. user2 cannot fetch the entity by id (403 or 404).
2. user2's `list` call (filtered by user1's project where applicable)
   does not leak the entity id. A 403/404 list response also counts as a
   pass — that's stronger scoping, not weaker.
3. `pre_seed` runs against `db` before the user1 POST when the entity
   needs prerequisite rows (build for approvals, template_version for
   qa_results).

Components and Knowledge are intentionally *not* in `ENTITY_FIXTURES`
because their repos are documented tenant-exempt (see their respective
`repository.py` module docstrings).

Briefs stay as `xfail(strict=False)` — they're BOLA-by-creator, not
org-scoped, so the org-isolation pattern below doesn't apply. Their
same-org, different-creator variant lives in
`app/tests/test_briefs_user_isolation.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.tests.factories import (
    SeededUser,
    auth_header,
    make_approval_payload,
    make_memory_payload,
    make_project_payload,
    make_qa_run_payload,
    make_template_payload,
    seed_build,
    seed_org,
    seed_template_version,
    seed_user,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.tenant_isolation,
    # Session-scoped event loop is required because the FastAPI app
    # (`app.main:app`) is a module-level singleton with starlette's
    # BaseHTTPMiddleware. The middleware spawns tasks bound to the loop
    # the request first arrives on; with the default function-scope
    # loop, test #2's loop sees Futures attached to test #1's dead loop
    # and asyncpg raises "got Future ... attached to a different loop".
    # All fixtures in this file (and the shared ones in conftest.py) use
    # loop_scope="session" to match.
    pytest.mark.asyncio(loop_scope="session"),
]


PreSeed = Callable[[AsyncSession, SeededUser], Awaitable[dict[str, int]]]
PathBuilder = Callable[[SeededUser, dict[str, int]], str]
PayloadBuilder = Callable[[SeededUser, dict[str, int]], dict[str, object]]


@dataclass(frozen=True)
class EntitySpec:
    """Per-entity wiring for the cross-org regression test.

    `pre_seed` returns a context dict (e.g. `{build_id: 7}`) consumed by
    `create_path`, `create_payload`, and `list_path`. `list_path=None`
    skips the list-leakage check (use when the entity has no list route,
    e.g. memory).
    """

    create_path: PathBuilder
    get_path_template: str
    create_payload: PayloadBuilder
    list_path: PathBuilder | None = None
    pre_seed: PreSeed | None = None
    create_status_ok: tuple[int, ...] = field(default=(200, 201))


async def _pre_seed_qa(db: AsyncSession, user: SeededUser) -> dict[str, int]:
    """Seed a TemplateVersion in user's project so QA run can attach to it."""
    _, version = await seed_template_version(db, project_id=user.project_id, created_by_id=user.id)
    return {"template_version_id": version.id}


async def _pre_seed_approval(db: AsyncSession, user: SeededUser) -> dict[str, int]:
    """Seed an EmailBuild in user's project so approval create has a build_id."""
    build = await seed_build(db, project_id=user.project_id, triggered_by_id=user.id)
    return {"build_id": build.id}


ENTITY_FIXTURES: dict[str, EntitySpec] = {
    "projects": EntitySpec(
        # Router has prefix="/api/v1" and the route is @router.post("/projects").
        # The skeleton-era /api/v1/projects/projects path was wrong but never
        # surfaced because the test self-skipped before this harness landed.
        create_path=lambda _u, _c: "/api/v1/projects",
        get_path_template="/api/v1/projects/{id}",
        list_path=lambda _u, _c: "/api/v1/projects",
        create_payload=lambda u, _c: make_project_payload(u.client_org_id),
    ),
    "templates": EntitySpec(
        create_path=lambda u, _c: f"/api/v1/projects/{u.project_id}/templates",
        get_path_template="/api/v1/templates/{id}",
        # user2 hits user1's project list — scoping must 403/404 OR return []
        list_path=lambda u, _c: f"/api/v1/projects/{u.project_id}/templates",
        create_payload=lambda _u, _c: make_template_payload(),
    ),
    "memory": EntitySpec(
        # POST /memory/ instantiates `get_embedding_provider(settings)` and
        # calls it to compute an embedding before INSERT. The integration job
        # has neither EMBEDDING__API_KEY/AI__API_KEY (OpenAI provider) nor
        # sentence-transformers (local provider), so the `embedding_stub`
        # fixture (conftest.py) monkeypatches the route's provider lookup with
        # a 1024-dim zero-vector stub — letting this row exercise scoping
        # without a live embedding backend.
        create_path=lambda _u, _c: "/memory/",
        get_path_template="/memory/{id}",
        list_path=None,  # no GET-list route — only POST /search
        create_payload=lambda u, _c: make_memory_payload(u.project_id),
    ),
    "qa_results": EntitySpec(
        create_path=lambda _u, _c: "/api/v1/qa/run",
        get_path_template="/api/v1/qa/results/{id}",
        list_path=lambda _u, c: (
            f"/api/v1/qa/results?template_version_id={c['template_version_id']}"
        ),
        create_payload=lambda u, c: make_qa_run_payload(c["template_version_id"], u.project_id),
        pre_seed=_pre_seed_qa,
    ),
    "approvals": EntitySpec(
        create_path=lambda _u, _c: "/api/v1/approvals/",
        get_path_template="/api/v1/approvals/{id}",
        list_path=lambda u, _c: f"/api/v1/approvals/?project_id={u.project_id}",
        create_payload=lambda u, c: make_approval_payload(c["build_id"], u.project_id),
        pre_seed=_pre_seed_approval,
    ),
}


@pytest_asyncio.fixture(loop_scope="session")
async def two_orgs(db: AsyncSession) -> tuple[SeededUser, SeededUser]:
    """Two orgs each with a developer-role user + project membership."""
    org1 = await seed_org(db, name=None)
    org2 = await seed_org(db, name=None)
    user1 = await seed_user(db, client_org_id=org1.id, role="developer")
    user2 = await seed_user(db, client_org_id=org2.id, role="developer")
    return user1, user2


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncClient:
    """ASGI httpx client against the live FastAPI app (no TestClient overrides)."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(
    "entity",
    [
        pytest.param("projects", id="projects"),
        pytest.param("templates", id="templates"),
        pytest.param("memory", id="memory"),
        pytest.param("qa_results", id="qa_results"),
        pytest.param(
            "briefs",
            id="briefs",
            marks=pytest.mark.xfail(
                strict=False,
                reason="briefs are BOLA-by-creator (not org-scoped); the "
                "user-isolation variant lives in test_briefs_user_isolation.py, "
                "not the org-isolation pattern below",
            ),
        ),
        pytest.param("approvals", id="approvals"),
    ],
)
async def test_no_cross_org_read(
    db: AsyncSession,
    client: AsyncClient,
    two_orgs: tuple[SeededUser, SeededUser],
    entity: str,
    embedding_stub: None,
) -> None:
    """user2 must not see entities user1 created in a different org."""
    user1, user2 = two_orgs
    if entity == "briefs":
        # Briefs need a user-isolation pattern, not org-isolation. The
        # parametrize-level xfail marker handles this row; the body is
        # left intentionally empty so the test doesn't NameError on a
        # missing fixture entry.
        pytest.fail("briefs row should xfail before reaching the body")

    spec = ENTITY_FIXTURES[entity]
    context: dict[str, int] = {}
    if spec.pre_seed is not None:
        context = await spec.pre_seed(db, user1)

    # user1 creates
    create_resp = await client.post(
        spec.create_path(user1, context),
        json=spec.create_payload(user1, context),
        headers=auth_header(user1),
    )
    assert create_resp.status_code in spec.create_status_ok, (
        f"{entity}: create failed: {create_resp.status_code} {create_resp.text}"
    )
    entity_id = create_resp.json()["id"]

    # user2 cannot fetch by id
    get_resp = await client.get(
        spec.get_path_template.format(id=entity_id),
        headers=auth_header(user2),
    )
    assert get_resp.status_code in (403, 404), (
        f"{entity}: cross-org GET succeeded ({get_resp.status_code})"
    )

    # user2's list must not leak the id (or be forbidden outright)
    if spec.list_path is not None:
        list_resp = await client.get(spec.list_path(user1, context), headers=auth_header(user2))
        if list_resp.status_code in (403, 404):
            return  # stronger scoping than per-row filtering — also a pass
        assert list_resp.status_code == 200, (
            f"{entity}: list returned {list_resp.status_code}: {list_resp.text}"
        )
        body = list_resp.json()
        items: list[dict[str, Any]]
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            items_field = body.get("items") or body.get("results") or []
            items = items_field if isinstance(items_field, list) else []
        else:
            items = []
        assert entity_id not in [e.get("id") for e in items], (
            f"{entity}: cross-org list leaked id {entity_id}"
        )
