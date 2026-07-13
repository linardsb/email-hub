"""Idempotent demo data seeder for the Email Hub.

Seeds the database with demo-worthy data: admin user, client org, project
with design system, components from seeds, and a pre-configured ESP connection.

Usage:
    uv run python -m app.seed_demo
    # or via Makefile:
    make seed-demo
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import AuthService
from app.components.data.seeds import COMPONENT_SEEDS
from app.components.models import Component, ComponentVersion
from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import get_logger
from app.core.scoped_db import get_system_db_context
from app.design_sync.crypto import encrypt_token
from app.design_sync.models import DesignConnection, DesignTokenSnapshot
from app.projects.models import ClientOrg, Project, ProjectMember
from app.qa_engine.models import (
    QAResult,  # noqa: F401  # pyright: ignore[reportUnusedImport] — ensures metadata for FK resolution
)

logger = get_logger(__name__)

# ── Design system for "Summer Campaign 2026" ──

DEMO_DESIGN_SYSTEM: dict[str, object] = {
    "palette": {
        "primary": "#2563EB",
        "secondary": "#7C3AED",
        "accent": "#F59E0B",
        "background": "#FFFFFF",
        "text": "#1F2937",
        "link": "#2563EB",
        "dark_background": "#111827",
        "dark_text": "#F9FAFB",
    },
    "typography": {
        "heading_font": "Inter, Arial, sans-serif",
        "body_font": "Inter, Arial, sans-serif",
        "base_size": 16,
    },
    "logo": {
        "url": "https://via.placeholder.com/180x48/2563EB/FFFFFF?text=Merkle",
        "alt_text": "Merkle",
        "width": 180,
        "height": 48,
    },
    "footer": {
        "company_name": "Merkle Demo Agency",
        "legal_text": "You are receiving this email because you opted in. Unsubscribe at any time.",
        "address": "123 Innovation Drive, London EC2A 1NT",
        "unsubscribe_text": "Unsubscribe",
    },
    "social_links": [
        {"platform": "twitter", "url": "https://twitter.com/merkle", "icon_url": None},
        {"platform": "linkedin", "url": "https://linkedin.com/company/merkle", "icon_url": None},
    ],
    "button_border_radius": "6px",
    "button_style": "filled",
    "colors": {"cta": "#2563EB", "cta_text": "#FFFFFF", "divider": "#E5E7EB"},
    "fonts": {},
    "font_sizes": {"h1": "28px", "h2": "22px", "body": "16px", "small": "12px"},
    "spacing": {"section": "32px", "element": "16px"},
}


async def _seed_user(db: AsyncSession) -> User:
    """Seed the admin user if none exist."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if count > 0:
        # Return the first admin user
        result = await db.execute(select(User).where(User.role == "admin").limit(1))
        user = result.scalar_one_or_none()
        if user:
            logger.info("seed.user_exists", user_id=user.id)
            return user
        # Fallback to first user
        result = await db.execute(select(User).limit(1))
        return result.scalar_one()

    settings = get_settings()
    password = settings.auth.demo_user_password
    user = User(
        email="admin@email-hub.dev",
        hashed_password=AuthService.hash_password(password),
        name="Admin",
        role="admin",
    )
    db.add(user)
    await db.flush()
    logger.info("seed.user_created", user_id=user.id, email=user.email)
    return user


async def _seed_client_org(db: AsyncSession) -> ClientOrg:
    """Seed client org."""
    result = await db.execute(select(ClientOrg).where(ClientOrg.slug == "merkle-demo-agency"))
    org = result.scalar_one_or_none()
    if org:
        logger.info("seed.client_org_exists", org_id=org.id)
        return org

    org = ClientOrg(name="Merkle Demo Agency", slug="merkle-demo-agency")
    db.add(org)
    await db.flush()
    logger.info("seed.client_org_created", org_id=org.id)
    return org


async def _seed_project(db: AsyncSession, org: ClientOrg, user: User) -> Project:
    """Seed project with design system."""
    result = await db.execute(
        select(Project).where(
            Project.name == "Summer Campaign 2026",
            Project.client_org_id == org.id,
        )
    )
    project = result.scalar_one_or_none()
    if project:
        logger.info("seed.project_exists", project_id=project.id)
        return project

    project = Project(
        name="Summer Campaign 2026",
        description="Cross-channel summer promotion campaign with responsive email templates.",
        client_org_id=org.id,
        created_by_id=user.id,
        target_clients=["gmail_web", "outlook_2019", "apple_mail", "ios_mail", "outlook_com"],
        design_system=DEMO_DESIGN_SYSTEM,
    )
    db.add(project)
    await db.flush()

    # Add user as project admin member
    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role="admin",
    )
    db.add(member)
    await db.flush()

    logger.info("seed.project_created", project_id=project.id)
    return project


async def _seed_components(db: AsyncSession, user: User) -> int:
    """Seed components from pre-built seeds. Upserts by slug — adds missing, updates existing."""
    # Build lookup of existing (non-deleted) components by slug
    result = await db.execute(select(Component).where(Component.deleted_at.is_(None)))
    existing: dict[str, Component] = {c.slug: c for c in result.scalars().all()}

    created = 0
    updated = 0
    for seed in COMPONENT_SEEDS:
        slug = str(seed["slug"])
        component = existing.get(slug)

        if component is None:
            # Create new component
            component = Component(
                name=str(seed["name"]),
                slug=slug,
                description=str(seed.get("description", "")),
                category=str(seed.get("category", "general")),
                created_by_id=user.id,
            )
            db.add(component)
            await db.flush()

            version = ComponentVersion(
                component_id=component.id,
                version_number=1,
                html_source=str(seed["html_source"]),
                css_source=str(seed["css_source"]) if seed.get("css_source") else None,
                compatibility=seed.get("compatibility"),
                slot_definitions=seed.get("slot_definitions"),
                default_tokens=seed.get("default_tokens"),
                changelog="Initial seed version",
                created_by_id=user.id,
            )
            db.add(version)
            created += 1
        else:
            # Update existing component metadata
            component.name = str(seed["name"])
            component.description = str(seed.get("description", ""))
            component.category = str(seed.get("category", "general"))

            # Update latest version with upgraded HTML/slots/tokens
            ver_result = await db.execute(
                select(ComponentVersion)
                .where(ComponentVersion.component_id == component.id)
                .order_by(ComponentVersion.version_number.desc())
                .limit(1)
            )
            latest_version = ver_result.scalar_one_or_none()
            if latest_version is not None:
                latest_version.html_source = str(seed["html_source"])
                latest_version.css_source = (
                    str(seed["css_source"]) if seed.get("css_source") else None
                )
                latest_version.compatibility = seed.get("compatibility")
                latest_version.slot_definitions = seed.get("slot_definitions")
                latest_version.default_tokens = seed.get("default_tokens")
                updated += 1
            else:
                # Component exists but has no version — create initial version
                version = ComponentVersion(
                    component_id=component.id,
                    version_number=1,
                    html_source=str(seed["html_source"]),
                    css_source=str(seed["css_source"]) if seed.get("css_source") else None,
                    compatibility=seed.get("compatibility"),
                    slot_definitions=seed.get("slot_definitions"),
                    default_tokens=seed.get("default_tokens"),
                    changelog="Initial seed version",
                    created_by_id=user.id,
                )
                db.add(version)
                created += 1

    await db.flush()
    logger.info("seed.components_upserted", created=created, updated=updated)
    return created + updated


async def _seed_design_connections(db: AsyncSession, project: Project, user: User) -> int:
    """Seed demo design connections with token snapshots."""
    result = await db.execute(
        select(DesignConnection).where(DesignConnection.project_id == project.id)
    )
    existing = result.scalars().all()
    if existing:
        logger.info("seed.design_connections_exist", count=len(existing))
        return len(existing)

    demo_token = "demo-figma-token-not-real"
    encrypted = encrypt_token(demo_token)
    now = datetime.now(tz=UTC)
    now_naive = now.replace(tzinfo=None)  # last_synced_at is TIMESTAMP WITHOUT TIME ZONE

    connections_data = [
        {
            "name": "Summer Campaign — Brand Kit",
            "provider": "figma",
            "file_ref": "abc123XYZdef456",
            "file_url": "https://www.figma.com/file/abc123XYZdef456/Summer-Campaign-Brand-Kit",
            "status": "connected",
            "last_synced_at": now_naive,
        },
        {
            "name": "Email Component Library",
            "provider": "figma",
            "file_ref": "ghi789JKLmno012",
            "file_url": "https://www.figma.com/file/ghi789JKLmno012/Email-Component-Library",
            "status": "connected",
            "last_synced_at": now_naive,
        },
        {
            "name": "Newsletter Layout — Penpot",
            "provider": "penpot",
            "file_ref": "penpot-proj-001/file-001",
            "file_url": "https://design.penpot.app/#/view/penpot-proj-001/file-001",
            "status": "connected",
            "last_synced_at": now_naive,
        },
    ]

    created = 0
    for data in connections_data:
        conn = DesignConnection(
            name=data["name"],
            provider=data["provider"],
            file_ref=data["file_ref"],
            file_url=data["file_url"],
            encrypted_token=encrypted,
            token_last4=demo_token[-4:],
            status=data["status"],
            last_synced_at=data["last_synced_at"],
            project_id=project.id,
            created_by_id=user.id,
        )
        db.add(conn)
        await db.flush()

        # Add a token snapshot for each connection
        snapshot = DesignTokenSnapshot(
            connection_id=conn.id,
            tokens_json={
                "colors": {
                    "primary": "#2563EB",
                    "secondary": "#7C3AED",
                    "accent": "#F59E0B",
                    "background": "#FFFFFF",
                    "text": "#1F2937",
                },
                "typography": {
                    "heading": "Inter, sans-serif",
                    "body": "Inter, sans-serif",
                    "base_size": 16,
                },
                "spacing": {"section": "32px", "element": "16px"},
            },
            extracted_at=now_naive,
        )
        db.add(snapshot)
        created += 1

    await db.flush()
    logger.info("seed.design_connections_created", count=created)
    return created


async def seed_all() -> None:
    """Run the full idempotent seed pipeline."""
    settings = get_settings()
    if settings.environment not in ("development", "production"):
        logger.warning("seed.skipped", environment=settings.environment)
        print(f"Seed skipped: environment is '{settings.environment}'")
        return

    async with get_system_db_context() as db:
        try:
            user = await _seed_user(db)
            org = await _seed_client_org(db)
            project = await _seed_project(db, org, user)
            comp_count = await _seed_components(db, user)
            design_count = await _seed_design_connections(db, project, user)

            await db.commit()

            print("Demo seed complete:")
            print(f"  Admin user: {user.email} (id={user.id})")
            print(f"  Client org: {org.name} (id={org.id})")
            print(f"  Project: {project.name} (id={project.id})")
            print(f"  Components seeded: {comp_count}")
            print(f"  Design connections: {design_count}")
            print(
                "\nLogin: email=admin@email-hub.dev (password from AUTH__DEMO_USER_PASSWORD env var)"
            )
        except Exception:
            await db.rollback()
            logger.exception("seed.failed")
            raise
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_all())
