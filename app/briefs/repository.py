"""Database operations for briefs.

Briefs scope by `created_by_id` (BOLA-style) rather than `client_org_id` —
the `BriefConnection` table has no org column. Filters use
`scoped_access(self.db).user_id`; admin / system bypass via the standard
sentinel (`access.project_ids is None`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.briefs.models import BriefAttachment, BriefConnection, BriefItem, BriefResource
from app.core.scoped_db import scoped_access


class BriefRepository:
    """CRUD operations for brief connections and items."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Connections ──

    async def create_connection(
        self,
        *,
        name: str,
        platform: str,
        project_url: str,
        external_project_id: str,
        encrypted_credentials: str,
        credential_last4: str,
        project_id: int | None,
        created_by_id: int,
    ) -> BriefConnection:
        conn = BriefConnection(
            name=name,
            platform=platform,
            project_url=project_url,
            external_project_id=external_project_id,
            encrypted_credentials=encrypted_credentials,
            credential_last4=credential_last4,
            status="connected",
            project_id=project_id,
            created_by_id=created_by_id,
        )
        self.db.add(conn)
        await self.db.commit()
        await self.db.refresh(conn)
        return conn

    async def get_connection(self, connection_id: int) -> BriefConnection | None:
        access = scoped_access(self.db)
        stmt = select(BriefConnection).where(BriefConnection.id == connection_id)
        if access.project_ids is not None:
            stmt = stmt.where(BriefConnection.created_by_id == access.user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_connections(self) -> list[BriefConnection]:
        """List connections. Admins see all, others see own only."""
        access = scoped_access(self.db)
        stmt = select(BriefConnection).order_by(BriefConnection.created_at.desc())
        if access.project_ids is not None:
            stmt = stmt.where(BriefConnection.created_by_id == access.user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_connection(self, connection_id: int) -> bool:
        conn = await self.get_connection(connection_id)
        if conn is None:
            return False
        await self.db.delete(conn)
        await self.db.commit()
        return True

    async def update_connection_status(
        self,
        connection: BriefConnection,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        # Defense-in-depth: callers must pass a connection they fetched via
        # `get_connection()` (already scope-checked). Re-assert here so a
        # future caller that hands us a foreign connection can't escape scope.
        access = scoped_access(self.db)
        if access.project_ids is not None and connection.created_by_id != access.user_id:
            raise PermissionError("connection out of scope")
        connection.status = status
        connection.error_message = error_message
        if status == "connected":
            connection.last_synced_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(connection)

    # ── Items ──

    async def upsert_item(
        self,
        *,
        connection_id: int,
        external_id: str,
        title: str,
        description: str | None,
        status: str,
        priority: str | None,
        assignees: list[str],
        labels: list[str],
        due_date: datetime | None,
        thumbnail_url: str | None,
    ) -> BriefItem:
        """Upsert an item by (connection_id, external_id). Caller must commit."""
        result = await self.db.execute(
            select(BriefItem).where(
                BriefItem.connection_id == connection_id,
                BriefItem.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.title = title
            existing.description = description
            existing.status = status
            existing.priority = priority
            existing.assignees = assignees
            existing.labels = labels
            existing.due_date = due_date
            existing.thumbnail_url = thumbnail_url
            await self.db.flush()
            return existing

        item = BriefItem(
            connection_id=connection_id,
            external_id=external_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignees=assignees,
            labels=labels,
            due_date=due_date,
            thumbnail_url=thumbnail_url,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def commit(self) -> None:
        """Commit the current transaction (call after batch upserts)."""
        await self.db.commit()

    async def list_items_for_connection(self, connection_id: int) -> list[BriefItem]:
        result = await self.db.execute(
            select(BriefItem)
            .where(BriefItem.connection_id == connection_id)
            .order_by(BriefItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_items(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[BriefItem]:
        """List items scoped to connections the user can access."""
        access = scoped_access(self.db)
        stmt = select(BriefItem).join(BriefConnection)

        # BOLA: non-admins only see items from their own connections
        if access.project_ids is not None:
            stmt = stmt.where(BriefConnection.created_by_id == access.user_id)

        if platform is not None:
            stmt = stmt.where(BriefConnection.platform == platform)
        if status is not None:
            stmt = stmt.where(BriefItem.status == status)
        if search is not None:
            from app.shared.utils import escape_like

            stmt = stmt.where(BriefItem.title.ilike(f"%{escape_like(search)}%"))

        stmt = stmt.order_by(BriefItem.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_item(self, item_id: int) -> BriefItem | None:
        result = await self.db.execute(select(BriefItem).where(BriefItem.id == item_id))
        return result.scalar_one_or_none()

    async def get_item_with_details(self, item_id: int) -> BriefItem | None:
        """Get item with eagerly loaded resources and attachments."""
        result = await self.db.execute(
            select(BriefItem)
            .options(selectinload(BriefItem.resources), selectinload(BriefItem.attachments))
            .where(BriefItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_items_by_ids(self, item_ids: list[int]) -> list[BriefItem]:
        """Fetch items by id, scoped to the caller's own connections (BOLA).

        Mirrors `list_items`: non-admins only see items whose connection they
        created. Without this filter `import_items` would resolve another
        user's brief items by id.
        """
        access = scoped_access(self.db)
        stmt = select(BriefItem).join(BriefConnection).where(BriefItem.id.in_(item_ids))
        if access.project_ids is not None:
            stmt = stmt.where(BriefConnection.created_by_id == access.user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── Resources & Attachments ──

    async def replace_resources(self, item_id: int, resources: list[dict[str, Any]]) -> None:
        """Delete existing resources and insert new ones."""
        result = await self.db.execute(
            select(BriefResource).where(BriefResource.item_id == item_id)
        )
        for existing in result.scalars().all():
            await self.db.delete(existing)

        for rdata in resources:
            self.db.add(
                BriefResource(
                    item_id=item_id,
                    type=str(rdata["type"]),
                    filename=str(rdata["filename"]),
                    url=str(rdata["url"]),
                    size_bytes=rdata.get("size_bytes"),
                )
            )
        await self.db.flush()

    async def replace_attachments(self, item_id: int, attachments: list[dict[str, Any]]) -> None:
        """Delete existing attachments and insert new ones. Caller must commit."""
        result = await self.db.execute(
            select(BriefAttachment).where(BriefAttachment.item_id == item_id)
        )
        for existing in result.scalars().all():
            await self.db.delete(existing)

        for adata in attachments:
            self.db.add(
                BriefAttachment(
                    item_id=item_id,
                    filename=str(adata["filename"]),
                    url=str(adata["url"]),
                    size_bytes=adata.get("size_bytes"),
                )
            )
        await self.db.flush()
