"""Shared test factories for cross-feature integration tests.

Used by `app/tests/test_tenant_isolation.py` and any future cross-entity
regression test that needs to spin up isolated `(org, project, user)`
tuples in a real database.

Each `seed_*` helper commits its writes so subsequent fixtures see them.
`make_*_payload` helpers return the request body expected by the matching
POST route; they take the seeded `User` (which carries `client_org_id`
plus a test-only `project_id` attribute) so callers can build org- or
project-scoped payloads without a second DB lookup.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import AuthService
from app.auth.token import create_access_token
from app.email_engine.models import EmailBuild
from app.projects.models import ClientOrg, Project, ProjectMember
from app.templates.models import Template, TemplateVersion


@dataclass(frozen=True)
class SeededUser:
    """Test wrapper carrying the User row plus its org/project context.

    `ENTITY_FIXTURES` callers need both ids to build org- or project-scoped
    paths and payloads. Exposing them via a dataclass keeps pyright happy
    (the `User` ORM class doesn't declare these as attributes).
    """

    user: User
    client_org_id: int
    project_id: int

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role


async def seed_org(db: AsyncSession, *, name: str | None = None) -> ClientOrg:
    """Create a `ClientOrg` with a unique name/slug."""
    suffix = uuid.uuid4().hex[:8]
    label = name or f"iso-org-{suffix}"
    org = ClientOrg(name=label, slug=label, is_active=True)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def seed_user(
    db: AsyncSession,
    *,
    client_org_id: int,
    role: str = "developer",
    email: str | None = None,
) -> SeededUser:
    """Create a `User` plus a `Project` membership tying them to `client_org_id`.

    The project + ProjectMember row is what `_resolve_access` reads to
    populate `TenantAccess.project_ids` / `org_ids`. Without it, every
    seeded user resolves to empty scope and isolation tests would pass
    trivially.

    Returns a `SeededUser` exposing the User row plus its org and project
    ids — `ENTITY_FIXTURES` in `test_tenant_isolation.py` reads these to
    build org- or project-scoped payloads.
    """
    suffix = uuid.uuid4().hex[:8]
    user_email = email or f"iso-{suffix}@email-hub.test"
    user = User(
        email=user_email,
        hashed_password=AuthService.hash_password("test-password-12345"),
        name=f"iso-{suffix}",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    project = Project(
        name=f"iso-project-{suffix}",
        client_org_id=client_org_id,
        created_by_id=user.id,
        is_active=True,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
    db.add(member)
    await db.commit()

    return SeededUser(user=user, client_org_id=client_org_id, project_id=project.id)


async def seed_template_version(
    db: AsyncSession,
    *,
    project_id: int,
    created_by_id: int,
) -> tuple[Template, TemplateVersion]:
    """Seed a `Template` + initial `TemplateVersion` in the given project.

    Used by `qa_results` fixtures (QA run accepts `template_version_id`).
    Committed before return so downstream API calls can reference the ids.
    """
    suffix = uuid.uuid4().hex[:8]
    template = Template(
        project_id=project_id,
        name=f"iso-tpl-{suffix}",
        status="draft",
        created_by_id=created_by_id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    version = TemplateVersion(
        template_id=template.id,
        version_number=1,
        html_source="<html><body><table><tr><td>iso-test</td></tr></table></body></html>",
        created_by_id=created_by_id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return template, version


async def seed_build(
    db: AsyncSession,
    *,
    project_id: int,
    triggered_by_id: int,
) -> EmailBuild:
    """Seed a completed `EmailBuild` row tied to `project_id`.

    `approval_create` requires a `build_id` to reference. The build is
    marked status='completed' with compiled HTML so the approval service
    accepts it without an actual pipeline run.
    """
    suffix = uuid.uuid4().hex[:8]
    build = EmailBuild(
        project_id=project_id,
        template_name=f"iso-build-{suffix}",
        status="completed",
        source_html="<html><body><table><tr><td>iso</td></tr></table></body></html>",
        compiled_html="<html><body><table><tr><td>iso</td></tr></table></body></html>",
        triggered_by_id=triggered_by_id,
        is_production=False,
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)
    return build


def auth_header(user: User | SeededUser) -> dict[str, str]:
    """Bearer header carrying a valid access token for `user`.

    Accepts the raw ORM `User` or the `SeededUser` wrapper so callers can
    pass whichever is in scope.
    """
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


# ── Payload factories ──
#
# Each helper returns the JSON body for the matching POST route. They take
# whatever ids the route needs (org/project/build) directly so callers in
# `ENTITY_FIXTURES` can keep their lambdas thin.


def make_project_payload(org_id: int) -> dict[str, object]:
    """Body for `POST /api/v1/projects/projects`."""
    return {"name": f"iso-test-{uuid.uuid4().hex[:6]}", "client_org_id": org_id}


def make_template_payload() -> dict[str, object]:
    """Body for `POST /api/v1/projects/{project_id}/templates`.

    `project_id` lives in the URL — no body field for it. `TemplateCreate`
    needs `name` (TemplateBase) and `html_source`.
    """
    return {
        "name": f"iso-tpl-{uuid.uuid4().hex[:6]}",
        "html_source": "<html><body><table><tr><td>iso</td></tr></table></body></html>",
    }


def make_memory_payload(project_id: int) -> dict[str, object]:
    """Body for `POST /memory/`. Tied to `project_id` for tenant filtering."""
    return {
        "agent_type": "scaffolder",
        "memory_type": "episodic",
        "content": f"iso-test-memory-{uuid.uuid4().hex[:6]}",
        "project_id": project_id,
        "is_evergreen": False,
    }


def make_qa_run_payload(template_version_id: int, project_id: int) -> dict[str, object]:
    """Body for `POST /api/v1/qa/run`.

    Carries a `template_version_id` so the result is scoped to the
    template's project; otherwise `qa_results` repository's project-scope
    filter would attach the row to neither org and the cross-org check
    would be a no-op.
    """
    return {
        "template_version_id": template_version_id,
        "project_id": project_id,
        "html": "<html><body><table><tr><td>iso</td></tr></table></body></html>",
    }


def make_approval_payload(build_id: int, project_id: int) -> dict[str, object]:
    """Body for `POST /api/v1/approvals/`. Requires an existing build."""
    return {"build_id": build_id, "project_id": project_id}
