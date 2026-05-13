# pyright: reportUnknownMemberType=false
"""Tenant-scoped database session dependency.

`get_scoped_db` resolves the authenticated user, computes their accessible
project and organization sets from `ProjectMember`, and stamps both on
`session.info`. Repository methods read those sets via :func:`scoped_access`
and apply `WHERE project_id IN (...)` / `WHERE client_org_id IN (...)` filters
on every list/get/update/delete.

Admin role bypasses scoping by stamping ``None`` for both sets — repositories
treat ``None`` as "no filter" (admins get cross-tenant reads, by design).

Routes that genuinely need cross-tenant access without a user (login flow,
``/health``, the ``get_current_user`` resolver itself) keep the unscoped
``get_db`` — see the allowlist in
``.agents/plans/tech-debt-03-multi-tenant-isolation.md`` §A3.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from cachetools import TTLCache
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import AsyncSessionLocal
from app.projects.models import Project, ProjectMember


@dataclass(frozen=True, slots=True)
class TenantAccess:
    """Per-request tenant scope.

    ``None`` on ``project_ids`` / ``org_ids`` is the admin sentinel:
    repositories treat it as "no filter". Regular users get a concrete
    `frozenset` (possibly empty).

    ``user_id`` carries the originating user's id for repos that scope by
    `created_by_id` (BOLA-style) rather than org membership — primarily
    `briefs`, where rows have no `client_org_id` column. ``None`` in
    `_SYSTEM_ACCESS` (cron / webhook contexts with no user).
    """

    project_ids: frozenset[int] | None
    org_ids: frozenset[int] | None
    role: str
    user_id: int | None = None


# 30s TTL, 200 entries — mirrors the existing _user_cache in
# app/auth/dependencies.py. Membership changes (add_member / project delete /
# user role change) become visible after at most one TTL window. That's
# acceptable: this scope is defense-in-depth on top of explicit access checks.
_membership_cache: TTLCache[int, TenantAccess] = TTLCache[int, TenantAccess](maxsize=200, ttl=30)


def invalidate_membership_cache(user_id: int) -> None:
    """Drop a user from the membership cache.

    Call on `add_member`, project delete, or role change so the next request
    recomputes access without waiting for TTL expiry.
    """
    _membership_cache.pop(user_id, None)


def clear_membership_cache() -> None:
    """Clear the entire membership cache (test isolation)."""
    _membership_cache.clear()


async def _resolve_access(db: AsyncSession, user: User) -> TenantAccess:
    """Compute (project_ids, org_ids) for a user.

    Admin → sentinel ``None`` for both. Other users → joined ProjectMember →
    Project lookup. Result is cached for 30s.
    """
    cached = _membership_cache.get(user.id)
    if cached is not None:
        return cached

    if user.role == "admin":
        access = TenantAccess(project_ids=None, org_ids=None, role=user.role, user_id=user.id)
        _membership_cache[user.id] = access
        return access

    stmt = (
        select(Project.id, Project.client_org_id)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            Project.deleted_at.is_(None),
        )
    )
    rows = (await db.execute(stmt)).all()
    project_ids = frozenset(int(r[0]) for r in rows)
    org_ids = frozenset(int(r[1]) for r in rows)

    access = TenantAccess(project_ids=project_ids, org_ids=org_ids, role=user.role, user_id=user.id)
    _membership_cache[user.id] = access
    # Detach to mirror the user-cache safety pattern: nothing ORM here, but
    # downstream reads of `project_ids` / `org_ids` are pure Python sets, so
    # session lifetime is irrelevant.
    return access


async def get_scoped_db(
    user: Annotated[User, Depends(get_current_user)],
) -> AsyncGenerator[AsyncSession, None]:
    """Open a session whose `.info` carries the caller's tenant scope."""
    async with AsyncSessionLocal() as session:
        try:
            access = await _resolve_access(session, user)
            session.info["tenant_access"] = access
            yield session
        except Exception:
            await session.rollback()
            raise


_SYSTEM_ACCESS = TenantAccess(project_ids=None, org_ids=None, role="system")


@asynccontextmanager
async def get_scoped_db_context(user: User) -> AsyncGenerator[AsyncSession, None]:
    """Standalone session for background tasks spawned by an authenticated request.

    Stamps the user's `TenantAccess` so repos that call :func:`scoped_access`
    apply the same tenant filters they would on a request-bound session. Use
    when a route accepts a request, returns 202, and continues work in an
    `asyncio` task that opens its own session — the originating user's scope
    must follow the work, not vanish at the request boundary.

    Cross-tenant background work (cron, webhooks with no user) keeps using
    :func:`get_system_db_context`.
    """
    session = AsyncSessionLocal()
    try:
        access = await _resolve_access(session, user)
        session.info["tenant_access"] = access
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def get_system_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Standalone session for background jobs (no request user).

    Stamps a "system" `TenantAccess` whose `None` sentinels disable repo
    scoping — same effect as admin. Use only from cron jobs, blueprint
    workers, MCP tools, and other code paths that legitimately operate
    across tenants. Request-bound code MUST use `get_scoped_db`.
    """
    session = AsyncSessionLocal()
    try:
        session.info["tenant_access"] = _SYSTEM_ACCESS
        yield session
    finally:
        await session.close()


def scoped_access(session: AsyncSession) -> TenantAccess:
    """Return the `TenantAccess` stamped on the session by `get_scoped_db`.

    Raises ``RuntimeError`` if the session was opened via plain `get_db`.
    Failing loud is the point — silent fallback would defeat tenant scoping.
    """
    access = session.info.get("tenant_access")
    if not isinstance(access, TenantAccess):
        msg = (
            "Session was not opened via get_scoped_db; tenant_access missing. "
            "Did a route forget to swap Depends(get_db) → Depends(get_scoped_db)?"
        )
        raise RuntimeError(msg)
    return access
