"""Business logic for brief connections and sync."""

from __future__ import annotations

import json
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.briefs.exceptions import (
    BriefConnectionNotFoundError,
    BriefItemNotFoundError,
    BriefSyncFailedError,
    BriefValidationError,
    UnsupportedPlatformError,
)
from app.briefs.protocol import BriefProvider
from app.briefs.providers import get_provider_registry
from app.briefs.repository import BriefRepository
from app.briefs.schemas import (
    PLATFORMS,
    BriefDetailResponse,
    BriefItemResponse,
    ConnectionCreateRequest,
    ConnectionResponse,
    ImportResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.crypto import decrypt_token, encrypt_token
from app.projects.service import ProjectService

logger = get_logger(__name__)


class BriefService:
    """Orchestrates brief connections, sync, and import."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._repo = BriefRepository(db)
        self._providers: dict[str, BriefProvider] = {}

    def _get_provider(self, platform: str) -> BriefProvider:
        """Get or create a provider instance for the given platform."""
        if platform not in self._providers:
            registry = get_provider_registry()
            provider_cls = registry.get(platform)
            if provider_cls is None:
                raise UnsupportedPlatformError(
                    f"Platform '{platform}' is not supported. "
                    f"Supported: {', '.join(sorted(registry))}"
                )
            settings = get_settings()
            base_url = settings.briefs.provider_base_urls.get(platform)
            self._providers[platform] = provider_cls(base_url=base_url)  # type: ignore[call-arg]
        return self._providers[platform]

    def _get_primary_credential(self, platform: str, credentials: dict[str, str]) -> str:
        """Get the primary credential value for last4 display."""
        key_priority = {
            "jira": "api_token",
            "asana": "personal_access_token",
            "monday": "api_key",
            "clickup": "api_token",
            "trello": "api_token",
            "notion": "integration_token",
            "wrike": "access_token",
            "basecamp": "access_token",
        }
        key = key_priority.get(platform, "")
        value = credentials.get(key, "")
        if not value:
            # Fall back to first value
            value = next(iter(credentials.values()), "")
        return value

    # ── Connections ──

    async def list_connections(self, user: User) -> list[ConnectionResponse]:  # noqa: ARG002
        """List connections visible to the user.

        `user` is retained in the signature so call sites stay symmetric with
        sibling service methods; tenant scoping reads from `session.info` set
        by `get_scoped_db`, not from the parameter.
        """
        connections = await self._repo.list_connections()
        return [ConnectionResponse.from_model(c) for c in connections]

    async def create_connection(
        self, data: ConnectionCreateRequest, user: User
    ) -> ConnectionResponse:
        """Create a new brief connection with credential validation."""
        if data.platform not in PLATFORMS:
            raise UnsupportedPlatformError(
                f"Platform '{data.platform}' is not supported. "
                f"Supported: {', '.join(sorted(PLATFORMS))}"
            )

        if data.project_id is not None:
            await self._verify_access(data.project_id, user)

        # Validate required credential keys before calling provider
        self._validate_credential_keys(data.platform, data.credentials)

        provider = self._get_provider(data.platform)

        # Validate credentials with the platform API
        try:
            await provider.validate_credentials(data.credentials, data.project_url)
        except Exception as exc:
            raise BriefSyncFailedError(f"Failed to validate {data.platform} credentials") from exc

        # Extract project ID from URL
        external_project_id = await provider.extract_project_id(data.project_url)

        # Encrypt credentials
        creds_json = json.dumps(data.credentials)
        encrypted = encrypt_token(creds_json)
        primary_cred = self._get_primary_credential(data.platform, data.credentials)
        last4 = primary_cred[-4:] if len(primary_cred) >= 4 else primary_cred

        conn = await self._repo.create_connection(
            name=data.name,
            platform=data.platform,
            project_url=data.project_url,
            external_project_id=external_project_id,
            encrypted_credentials=encrypted,
            credential_last4=last4,
            project_id=data.project_id,
            created_by_id=user.id,
        )

        logger.info(
            "briefs.connection_created",
            connection_id=conn.id,
            platform=data.platform,
            user_id=user.id,
        )

        # Run initial sync
        try:
            await self._sync_items(conn.id)
        except Exception:
            logger.warning(
                "briefs.initial_sync_failed",
                connection_id=conn.id,
                exc_info=True,
            )

        # Refresh to get latest state
        refreshed = await self._repo.get_connection(conn.id)
        if refreshed is None:
            raise BriefConnectionNotFoundError("Connection disappeared after creation")
        return ConnectionResponse.from_model(refreshed)

    async def delete_connection(self, connection_id: int, user: User) -> bool:
        """Delete a connection with access check."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise BriefConnectionNotFoundError(f"Connection {connection_id} not found")
        if conn.project_id is not None:
            await self._verify_access(conn.project_id, user)

        logger.info("briefs.connection_deleted", connection_id=connection_id, user_id=user.id)
        return await self._repo.delete_connection(connection_id)

    async def sync_connection(self, connection_id: int, user: User) -> ConnectionResponse:
        """Trigger a sync for a connection."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise BriefConnectionNotFoundError(f"Connection {connection_id} not found")
        if conn.project_id is not None:
            await self._verify_access(conn.project_id, user)

        await self._sync_items(connection_id)

        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise BriefConnectionNotFoundError(f"Connection {connection_id} not found")
        return ConnectionResponse.from_model(conn)

    # ── Items ──

    async def list_items_for_connection(
        self, connection_id: int, user: User
    ) -> list[BriefItemResponse]:
        """List items for a specific connection."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise BriefConnectionNotFoundError(f"Connection {connection_id} not found")
        if conn.project_id is not None:
            await self._verify_access(conn.project_id, user)

        items = await self._repo.list_items_for_connection(connection_id)
        return [BriefItemResponse.model_validate(item, from_attributes=True) for item in items]

    async def list_items(
        self,
        user: User,  # noqa: ARG002
        *,
        platform: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[BriefItemResponse]:
        """List all items scoped to the user's accessible connections.

        `user` is retained for API symmetry; scoping reads from
        `session.info` set by `get_scoped_db`.
        """
        items = await self._repo.list_items(platform=platform, status=status, search=search)
        return [BriefItemResponse.model_validate(item, from_attributes=True) for item in items]

    async def get_item_detail(self, item_id: int, user: User) -> BriefDetailResponse:
        """Get item with full detail (description, resources, attachments)."""
        item = await self._repo.get_item_with_details(item_id)
        if item is None:
            raise BriefItemNotFoundError(f"Brief item {item_id} not found")

        # BOLA: the item is fetched unscoped; the connection's created_by_id
        # filter is the ownership gate. A missing connection means the item
        # belongs to another user — deny (mirrors list_items_for_connection /
        # sync_connection). Falling through here leaked items across creators.
        conn = await self._repo.get_connection(item.connection_id)
        if conn is None:
            raise BriefItemNotFoundError(f"Brief item {item_id} not found")
        if conn.project_id is not None:
            await self._verify_access(conn.project_id, user)

        return BriefDetailResponse.model_validate(item, from_attributes=True)

    # ── Import ──

    async def import_items(
        self, brief_item_ids: list[int], project_name: str, user: User
    ) -> ImportResponse:
        """Import brief items into a project (find by name)."""
        # BOLA: get_items_by_ids is owner-scoped, so non-owned/missing ids are
        # absent from the result. Require full coverage of the requested set —
        # a non-owned id must 404, not be silently dropped (mirrors
        # get_item_detail). set() dedups repeated ids in the request.
        items = await self._repo.get_items_by_ids(brief_item_ids)
        if len(items) != len(set(brief_item_ids)):
            raise BriefItemNotFoundError("One or more brief items not found")

        # Find project by exact name
        from sqlalchemy import select

        from app.projects.models import Project

        result = await self.db.execute(
            select(Project)
            .where(Project.name == project_name, Project.deleted_at.is_(None))
            .limit(1)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise BriefValidationError(f"Project '{project_name}' not found")

        # Verify access
        await self._verify_access(project.id, user)

        logger.info(
            "briefs.items_imported",
            project_id=project.id,
            item_count=len(items),
            user_id=user.id,
        )

        return ImportResponse(project_id=project.id)

    # ── Sync Engine ──

    async def _sync_items(self, connection_id: int) -> None:
        """Sync items from the external platform."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise BriefConnectionNotFoundError(f"Connection {connection_id} not found")

        provider = self._get_provider(conn.platform)
        await self._repo.update_connection_status(conn, "syncing")

        try:
            # Decrypt credentials
            creds_json = decrypt_token(conn.encrypted_credentials)
            credentials: dict[str, str] = json.loads(creds_json)

            # Fetch items from platform
            settings = get_settings()
            raw_items = await provider.list_items(credentials, conn.external_project_id)

            # Apply safety cap
            max_items = settings.briefs.max_items_per_sync
            if len(raw_items) > max_items:
                logger.warning(
                    "briefs.sync_items_capped",
                    connection_id=connection_id,
                    total=len(raw_items),
                    cap=max_items,
                )
                raw_items = raw_items[:max_items]

            # Upsert each item
            for raw in raw_items:
                item = await self._repo.upsert_item(
                    connection_id=connection_id,
                    external_id=raw.external_id,
                    title=raw.title,
                    description=raw.description,
                    status=raw.status,
                    priority=raw.priority,
                    assignees=raw.assignees,
                    labels=raw.labels,
                    due_date=raw.due_date,
                    thumbnail_url=raw.thumbnail_url,
                )

                # Replace resources and attachments
                if raw.resources:
                    await self._repo.replace_resources(
                        item.id,
                        [
                            {
                                "type": r.type,
                                "filename": r.filename,
                                "url": r.url,
                                "size_bytes": r.size_bytes,
                            }
                            for r in raw.resources
                        ],
                    )
                if raw.attachments:
                    await self._repo.replace_attachments(
                        item.id,
                        [
                            {
                                "filename": a.filename,
                                "url": a.url,
                                "size_bytes": a.size_bytes,
                            }
                            for a in raw.attachments
                        ],
                    )

            # Commit all upserts in a single transaction
            await self._repo.commit()
            await self._repo.update_connection_status(conn, "connected")

            logger.info(
                "briefs.sync_completed",
                connection_id=connection_id,
                platform=conn.platform,
                item_count=len(raw_items),
            )

        except Exception as exc:
            await self._repo.update_connection_status(conn, "error", error_message="Sync failed")
            logger.error(
                "briefs.sync_failed",
                connection_id=connection_id,
                error=str(exc),
                exc_info=True,
            )
            raise BriefSyncFailedError("Failed to sync items from platform") from exc

    # ── Helpers ──

    _REQUIRED_CREDENTIAL_KEYS: ClassVar[dict[str, list[str]]] = {
        "jira": ["email", "api_token"],
        "asana": ["personal_access_token"],
        "monday": ["api_key"],
        "clickup": ["api_token"],
        "trello": ["api_key", "api_token"],
        "notion": ["integration_token"],
        "wrike": ["access_token"],
        "basecamp": ["access_token"],
    }

    def _validate_credential_keys(self, platform: str, credentials: dict[str, str]) -> None:
        """Validate that all required credential keys are present."""
        required = self._REQUIRED_CREDENTIAL_KEYS.get(platform, [])
        missing = [k for k in required if not credentials.get(k)]
        if missing:
            raise BriefValidationError(
                f"Missing required credential fields for {platform}: {', '.join(missing)}"
            )

    async def _verify_access(self, project_id: int, user: User) -> None:
        """Verify user has access to the project (BOLA check)."""
        project_service = ProjectService(self.db)
        await project_service.verify_project_access(project_id, user)
