# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Briefs BOLA-by-creator user-isolation regression.

Briefs scope by ``created_by_id``, not ``client_org_id`` — the brief tables
have no org column (see ``app/briefs/repository.py`` module docstring). The
cross-org harness in ``test_tenant_isolation.py`` therefore can't cover them:
it seeds users in *different* orgs, but the briefs boundary must also hold
between two users in the *same* org. This file is that missing net and closes
deferred entry ``tech-debt-03-briefs-user-isolation-test``.

Seeding goes through the ORM directly rather than ``POST /connections``,
because ``BriefService.create_connection`` validates credentials against the
live external platform (``provider.validate_credentials``) — unavailable in
CI. The boundary under test is the repository's ``created_by_id`` filter and
the route guards that depend on it; neither is touched by the seed path.
``project_id=None`` on the seeded connection isolates the creator boundary
from any project-membership confound.

Activation mirrors ``test_tenant_isolation.py``: integration-only, runs on a
session-scoped event loop (the ``app.main:app`` singleton + starlette
``BaseHTTPMiddleware`` require it — see that file's pytestmark rationale), and
the ``db`` fixture comes from ``app/tests/conftest.py`` (alembic-upgrade-head +
TRUNCATE-per-test). Without ``TEST_DATABASE__URL`` the module collect-skips.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.models import BriefConnection, BriefItem
from app.briefs.repository import BriefRepository
from app.core.scoped_db import TenantAccess, clear_membership_cache
from app.main import app
from app.tests.factories import SeededUser, auth_header, seed_org, seed_user

pytestmark = [
    pytest.mark.integration,
    pytest.mark.tenant_isolation,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest_asyncio.fixture(loop_scope="session")
async def same_org_two_users(db: AsyncSession) -> tuple[SeededUser, SeededUser]:
    """Two developer-role users in the SAME org — the briefs BOLA boundary.

    ``clear_membership_cache()`` because the 30s-TTL scope cache is keyed by
    ``user.id`` and the harness ``RESTART IDENTITY`` reuses ids across tests;
    a stale entry would otherwise leak a previous test's scope.
    """
    clear_membership_cache()
    org = await seed_org(db, name=None)
    user1 = await seed_user(db, client_org_id=org.id, role="developer")
    user2 = await seed_user(db, client_org_id=org.id, role="developer")
    return user1, user2


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncClient:
    """ASGI httpx client against the live FastAPI app (no TestClient overrides)."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_brief(db: AsyncSession, owner: SeededUser) -> tuple[BriefConnection, BriefItem]:
    """Seed a connection + one item owned by ``owner`` via the ORM.

    Bypasses the credential-validating create route. ``project_id=None`` keeps
    the assertion on the ``created_by_id`` boundary alone.
    """
    conn = BriefConnection(
        name="iso-conn",
        platform="jira",
        project_url="https://example.atlassian.net/browse/ISO",
        external_project_id="ISO",
        encrypted_credentials="iso-not-decrypted-on-read",
        credential_last4="0000",
        status="connected",
        project_id=None,
        created_by_id=owner.id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    item = BriefItem(
        connection_id=conn.id,
        external_id="ISO-1",
        title="iso brief item",
        status="open",
        assignees=[],
        labels=[],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return conn, item


def _scope(session: AsyncSession, user: SeededUser) -> AsyncSession:
    """Stamp ``session.info`` with ``user``'s tenant scope, as ``get_scoped_db`` does.

    Hand-built rather than via ``_resolve_access`` so the repository assertion
    is a direct check of the ``created_by_id`` filter. ``project_ids`` is a
    non-None frozenset so the scoping branch is active (``None`` is the admin
    bypass).
    """
    session.info["tenant_access"] = TenantAccess(
        project_ids=frozenset({user.project_id}),
        org_ids=frozenset({user.client_org_id}),
        role="developer",
        user_id=user.id,
    )
    return session


async def test_repository_get_connection_filters_by_creator(
    db: AsyncSession, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Repository layer: a non-owner's scoped session cannot fetch the connection."""
    user1, user2 = same_org_two_users
    conn, _item = await _seed_brief(db, user1)

    owner_repo = BriefRepository(_scope(db, user1))
    assert await owner_repo.get_connection(conn.id) is not None  # control

    nonowner_repo = BriefRepository(_scope(db, user2))
    assert await nonowner_repo.get_connection(conn.id) is None  # the boundary


async def test_list_connections_excludes_other_users_rows(
    db: AsyncSession, client: AsyncClient, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Route layer: user2's connection list must not leak user1's connection."""
    user1, user2 = same_org_two_users
    conn, _item = await _seed_brief(db, user1)

    resp = await client.get("/api/v1/briefs/connections", headers=auth_header(user2))
    assert resp.status_code == 200, resp.text
    assert conn.id not in [c["id"] for c in resp.json()]

    owner_resp = await client.get("/api/v1/briefs/connections", headers=auth_header(user1))
    assert conn.id in [c["id"] for c in owner_resp.json()]  # control


async def test_list_items_for_connection_denies_other_user(
    db: AsyncSession, client: AsyncClient, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Route layer: listing items under another user's connection is a 404."""
    user1, user2 = same_org_two_users
    conn, _item = await _seed_brief(db, user1)

    resp = await client.get(
        f"/api/v1/briefs/connections/{conn.id}/items", headers=auth_header(user2)
    )
    assert resp.status_code == 404, resp.text


async def test_sync_connection_denies_other_user(
    db: AsyncSession, client: AsyncClient, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Route layer: syncing another user's connection is a 404 (before any provider call)."""
    user1, user2 = same_org_two_users
    conn, _item = await _seed_brief(db, user1)

    resp = await client.post(
        "/api/v1/briefs/connections/sync", json={"id": conn.id}, headers=auth_header(user2)
    )
    assert resp.status_code == 404, resp.text


async def test_get_item_detail_denies_other_user(
    db: AsyncSession, client: AsyncClient, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Route layer: GET /items/{id} must not leak another user's item.

    Regression for a fail-open BOLA: ``get_item_with_details`` is unscoped, and
    ``get_item_detail``'s connection guard fell through to ``return`` when
    ``get_connection`` returned ``None`` for the non-owner — leaking the item.
    """
    user1, user2 = same_org_two_users
    _conn, item = await _seed_brief(db, user1)

    resp = await client.get(f"/api/v1/briefs/items/{item.id}", headers=auth_header(user2))
    assert resp.status_code == 404, resp.text

    owner_resp = await client.get(f"/api/v1/briefs/items/{item.id}", headers=auth_header(user1))
    assert owner_resp.status_code == 200, owner_resp.text  # control


async def test_repository_get_items_by_ids_filters_by_creator(
    db: AsyncSession, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Repository layer: get_items_by_ids must drop items the caller doesn't own.

    Backs the import BOLA fix — `import_items` resolves source items through this
    method, so an unscoped result would let a user import another user's items.
    """
    user1, user2 = same_org_two_users
    _conn, item = await _seed_brief(db, user1)

    owner_repo = BriefRepository(_scope(db, user1))
    assert [i.id for i in await owner_repo.get_items_by_ids([item.id])] == [item.id]  # control

    nonowner_repo = BriefRepository(_scope(db, user2))
    assert await nonowner_repo.get_items_by_ids([item.id]) == []  # the boundary


async def test_import_items_denies_other_user(
    db: AsyncSession, client: AsyncClient, same_org_two_users: tuple[SeededUser, SeededUser]
) -> None:
    """Route layer: POST /import must not resolve another user's brief items.

    Same request body for both users, with a guaranteed-nonexistent project so
    no import actually runs. The status split is the proof: user2 is blocked at
    the item-ownership gate (404, before the project lookup), while user1 clears
    that gate and only then fails the project lookup (422). A pre-fix unscoped
    read would have let user2 resolve the item and 422 alongside user1.
    """
    user1, user2 = same_org_two_users
    _conn, item = await _seed_brief(db, user1)
    body = {"brief_item_ids": [item.id], "project_name": f"no-such-project-{uuid.uuid4().hex}"}

    resp = await client.post("/api/v1/briefs/import", json=body, headers=auth_header(user2))
    assert resp.status_code == 404, resp.text

    owner_resp = await client.post("/api/v1/briefs/import", json=body, headers=auth_header(user1))
    assert owner_resp.status_code == 422, owner_resp.text  # control: cleared the item gate
