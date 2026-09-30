"""Business logic for ESP bidirectional sync."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.connectors.token_rewriter import TokenRewriteResult

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.connectors.activecampaign.sync_provider import ActiveCampaignSyncProvider
from app.connectors.adobe.sync_provider import AdobeSyncProvider
from app.connectors.braze.sync_provider import BrazeSyncProvider
from app.connectors.brevo.sync_provider import BrevoSyncProvider
from app.connectors.exceptions import (
    ESPConnectionNotFoundError,
    ESPSyncFailedError,
    InvalidESPCredentialsError,
    InvalidRemoteTemplateIdError,
)
from app.connectors.hubspot.sync_provider import HubSpotSyncProvider
from app.connectors.iterable.sync_provider import IterableSyncProvider
from app.connectors.klaviyo.sync_provider import KlaviyoSyncProvider
from app.connectors.mailchimp.sync_provider import MailchimpSyncProvider
from app.connectors.sendgrid.sync_provider import SendGridSyncProvider
from app.connectors.sfmc.sync_provider import SFMCSyncProvider
from app.connectors.sync_models import ESPConnection
from app.connectors.sync_protocol import ESPSyncProvider
from app.connectors.sync_repository import ESPSyncRepository
from app.connectors.sync_schemas import (
    BulkExportItemResult,
    BulkExportResponse,
    ESPConnectionCreate,
    ESPConnectionResponse,
    ESPTemplate,
    ESPTemplateList,
    ExportResponse,
)
from app.connectors.taxi.sync_provider import TaxiSyncProvider
from app.core.exceptions import DomainValidationError
from app.core.logging import get_logger
from app.design_sync.crypto import decrypt_token, encrypt_token
from app.projects.service import ProjectService
from app.templates.schemas import TemplateCreate
from app.templates.service import TemplateService

logger = get_logger(__name__)

# A remote template ID becomes a provider URL path segment. Letters, digits and `@ _ . : -`
# cover every ESP's ID shape; a leading `.` would allow `..` traversal.
_REMOTE_TEMPLATE_ID_RE = re.compile(r"[A-Za-z0-9@][A-Za-z0-9@_.:-]{0,255}")

PROVIDER_REGISTRY: dict[str, type[ESPSyncProvider]] = {
    "braze": BrazeSyncProvider,
    "sfmc": SFMCSyncProvider,
    "adobe_campaign": AdobeSyncProvider,
    "taxi": TaxiSyncProvider,
    "klaviyo": KlaviyoSyncProvider,
    "hubspot": HubSpotSyncProvider,
    "mailchimp": MailchimpSyncProvider,
    "sendgrid": SendGridSyncProvider,
    "activecampaign": ActiveCampaignSyncProvider,
    "iterable": IterableSyncProvider,
    "brevo": BrevoSyncProvider,
}


class ConnectorSyncService:
    """Orchestrates ESP connection management and template sync operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._repo = ESPSyncRepository(db)
        self._project_service = ProjectService(db)
        self._template_service = TemplateService(db)

    # ── Token Rewriting ──

    async def rewrite_tokens(
        self, html: str, target_esp: str, source_esp: str | None = None
    ) -> TokenRewriteResult:
        """Rewrite ESP personalisation tokens from one format to another."""
        from app.connectors.token_ir import ESPPlatform
        from app.connectors.token_rewriter import TokenRewriterService

        rewriter = TokenRewriterService()
        return await rewriter.rewrite(
            html,
            cast(ESPPlatform, target_esp),
            cast(ESPPlatform, source_esp) if source_esp else None,
        )

    async def _auto_rewrite_tokens(self, html: str, target_esp_type: str) -> str:
        """Auto-detect source ESP tokens and rewrite to target if different."""
        from app.connectors.token_ir import (
            ALL_PLATFORMS,
            ESPPlatform,
            detect_and_parse,
            emit_tokens,
        )

        if target_esp_type not in ALL_PLATFORMS:
            return html
        try:
            ir, source_esp = detect_and_parse(html)
        except (ValueError, DomainValidationError):
            # No tokens detected — return as-is
            return html

        if source_esp == target_esp_type:
            return html

        new_html, _warnings = emit_tokens(ir, html, cast(ESPPlatform, target_esp_type))
        logger.info(
            "connectors.token_rewrite.auto",
            source_esp=source_esp,
            target_esp=target_esp_type,
            tokens_rewritten=len(ir.variables) + len(ir.conditionals) + len(ir.loops),
        )
        return new_html

    # ── Helpers ──

    def _get_provider(self, esp_type: str) -> ESPSyncProvider:
        """Instantiate the sync provider for a given ESP type."""
        provider_cls = PROVIDER_REGISTRY.get(esp_type)
        if provider_cls is None:
            raise ESPSyncFailedError(f"Unsupported ESP type: {esp_type}")
        return provider_cls()

    def _encrypt_credentials(self, credentials: dict[str, str]) -> str:
        """Serialize and encrypt credentials for storage."""
        return encrypt_token(json.dumps(credentials))

    def _decrypt_credentials(self, encrypted: str) -> dict[str, str]:
        """Decrypt and deserialize stored credentials."""
        return json.loads(decrypt_token(encrypted))  # type: ignore[no-any-return]

    def _credentials_hint(self, credentials: dict[str, str]) -> str:
        """Extract a safe hint from credentials (last 4 chars of first value)."""
        first_value = next(iter(credentials.values()), "")
        return f"****{first_value[-4:]}" if len(first_value) >= 4 else "****"

    async def _get_accessible_project_ids(self, user: User) -> list[int]:
        """Get IDs of projects the user can access."""
        from app.projects.models import Project, ProjectMember

        if user.role == "admin":
            result = await self.db.execute(select(Project.id))
            return [row[0] for row in result.all()]

        result = await self.db.execute(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        )
        return [row[0] for row in result.all()]

    async def _get_connection_with_bola(
        self, connection_id: int, user: User
    ) -> tuple[ESPConnection, dict[str, str]]:
        """Load a connection, verify BOLA, decrypt credentials."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise ESPConnectionNotFoundError(f"ESP connection {connection_id} not found")
        # BOLA: verify the user has access to the connection's project
        await self._project_service.verify_project_access(conn.project_id, user)
        credentials = self._decrypt_credentials(conn.encrypted_credentials)
        return conn, credentials

    # ── Connection CRUD ──

    async def create_connection(
        self, data: ESPConnectionCreate, user: User
    ) -> ESPConnectionResponse:
        """Create a new ESP connection after validating credentials."""
        logger.info(
            "esp_sync.connection_create_started",
            esp_type=data.esp_type,
            project_id=data.project_id,
        )

        # BOLA: verify the user has access to the target project
        await self._project_service.verify_project_access(data.project_id, user)

        # Validate credentials against the ESP
        provider = self._get_provider(data.esp_type)
        is_valid = await provider.validate_credentials(data.credentials)
        if not is_valid:
            raise InvalidESPCredentialsError(f"Invalid credentials for {data.esp_type}")

        encrypted = self._encrypt_credentials(data.credentials)
        hint = self._credentials_hint(data.credentials)

        conn = await self._repo.create_connection(
            esp_type=data.esp_type,
            name=data.name,
            encrypted_credentials=encrypted,
            credentials_hint=hint,
            project_id=data.project_id,
            created_by_id=user.id,
        )

        logger.info(
            "esp_sync.connection_create_completed",
            connection_id=conn.id,
            esp_type=data.esp_type,
        )
        return ESPConnectionResponse.model_validate(conn)

    async def list_connections(self, user: User) -> list[ESPConnectionResponse]:
        """List all ESP connections accessible to the user."""
        accessible_ids = await self._get_accessible_project_ids(user)
        rows = await self._repo.list_connections_for_user(user.id, accessible_ids)
        results: list[ESPConnectionResponse] = []
        for conn, project_name in rows:
            resp = ESPConnectionResponse.model_validate(conn)
            resp.project_name = project_name
            results.append(resp)
        return results

    async def get_connection(self, connection_id: int, user: User) -> ESPConnectionResponse:
        """Get a single ESP connection."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise ESPConnectionNotFoundError(f"ESP connection {connection_id} not found")
        await self._project_service.verify_project_access(conn.project_id, user)
        return ESPConnectionResponse.model_validate(conn)

    async def delete_connection(self, connection_id: int, user: User) -> None:
        """Delete an ESP connection."""
        logger.info("esp_sync.connection_delete_started", connection_id=connection_id)
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            raise ESPConnectionNotFoundError(f"ESP connection {connection_id} not found")
        await self._project_service.verify_project_access(conn.project_id, user)
        await self._repo.delete_connection(connection_id)
        logger.info("esp_sync.connection_delete_completed", connection_id=connection_id)

    # ── Remote Template Operations ──

    async def list_remote_templates(self, connection_id: int, user: User) -> ESPTemplateList:
        """List templates from the remote ESP."""
        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        try:
            templates = await provider.list_templates(credentials)
        except Exception as exc:
            await self._repo.update_status(conn, "error", str(exc))
            raise ESPSyncFailedError(f"Failed to list templates: {exc}") from exc

        await self._repo.update_status(conn, "connected")
        return ESPTemplateList(templates=templates, count=len(templates))

    async def get_remote_template(
        self, connection_id: int, template_id: str, user: User
    ) -> ESPTemplate:
        """Get a single template from the remote ESP."""
        if not _REMOTE_TEMPLATE_ID_RE.fullmatch(template_id):
            raise InvalidRemoteTemplateIdError(f"Invalid remote template id: {template_id!r}")
        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        try:
            template = await provider.get_template(template_id, credentials)
        except Exception as exc:
            raise ESPSyncFailedError(f"Failed to get template: {exc}") from exc

        return template

    async def import_template(self, connection_id: int, remote_template_id: str, user: User) -> int:
        """Import a remote ESP template into the local Hub as a new template.

        Returns the local template ID.
        """
        if not _REMOTE_TEMPLATE_ID_RE.fullmatch(remote_template_id):
            raise InvalidRemoteTemplateIdError(
                f"Invalid remote template id: {remote_template_id!r}"
            )
        logger.info(
            "esp_sync.import_started",
            connection_id=connection_id,
            remote_template_id=remote_template_id,
        )
        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        try:
            remote = await provider.get_template(remote_template_id, credentials)
        except Exception as exc:
            raise ESPSyncFailedError(f"Failed to fetch remote template: {exc}") from exc

        # Create local template in the connection's project
        local = await self._template_service.create_template(
            project_id=conn.project_id,
            data=TemplateCreate(
                name=f"[{conn.esp_type}] {remote.name}",
                description=f"Imported from {conn.esp_type} (ID: {remote.id})",
                subject_line=None,
                preheader_text=None,
                html_source=remote.html,
            ),
            user=user,
        )

        logger.info(
            "esp_sync.import_completed",
            connection_id=connection_id,
            remote_template_id=remote_template_id,
            local_template_id=local.id,
        )
        return local.id

    async def push_template(
        self, connection_id: int, local_template_id: int, user: User
    ) -> ESPTemplate:
        """Push a local Hub template to the remote ESP."""
        logger.info(
            "esp_sync.push_started",
            connection_id=connection_id,
            local_template_id=local_template_id,
        )
        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        # Get local template HTML from latest version
        local = await self._template_service.get_template(local_template_id, user)
        html = ""
        if local.latest_version is not None:
            version = await self._template_service.get_version(
                local_template_id, local.latest_version, user
            )
            html = version.html_source

        # Auto-rewrite tokens if source ESP differs from target
        if html:
            html = await self._auto_rewrite_tokens(html, conn.esp_type)

        try:
            remote = await provider.create_template(local.name, html, credentials)
        except Exception as exc:
            await self._repo.update_status(conn, "error", str(exc))
            raise ESPSyncFailedError(f"Failed to push template: {exc}") from exc

        await self._repo.update_status(conn, "connected")
        logger.info(
            "esp_sync.push_completed",
            connection_id=connection_id,
            local_template_id=local_template_id,
            remote_template_id=remote.id,
        )
        return remote

    # ── Export Orchestration ──

    async def _rewrite_for_export(
        self,
        html: str,
        target_esp: str,
        source_esp: str | None,
        rewrite_tokens: bool,
    ) -> tuple[str, int, list[str]]:
        """Rewrite tokens for export, returning (html, count, warnings)."""
        if not rewrite_tokens:
            return html, 0, []

        from app.connectors.token_ir import (
            ALL_PLATFORMS,
            ESPPlatform,
            detect_and_parse,
            emit_tokens,
        )

        if target_esp not in ALL_PLATFORMS:
            return html, 0, []

        try:
            if source_esp:
                from app.connectors.token_ir import parse_tokens

                ir = parse_tokens(html, cast(ESPPlatform, source_esp))
                detected = source_esp
            else:
                ir, detected = detect_and_parse(html)
        except (ValueError, DomainValidationError):
            return html, 0, []

        if detected == target_esp:
            return html, 0, []

        new_html, warnings = emit_tokens(ir, html, cast(ESPPlatform, target_esp))
        count = len(ir.variables) + len(ir.conditionals) + len(ir.loops)
        return new_html, count, list(warnings)

    async def _fetch_template_html(self, template_id: int, user: User) -> tuple[str, str]:
        """Fetch HTML and name for a local template by ID."""
        local = await self._template_service.get_template(template_id, user)
        html = ""
        if local.latest_version is not None:
            version = await self._template_service.get_version(
                template_id, local.latest_version, user
            )
            html = version.html_source
        return html, local.name

    async def export_template(
        self,
        html: str | None,
        template_id: int | None,
        target_esp: str,
        connection_id: int,
        template_name: str,
        source_esp: str | None,
        rewrite_tokens: bool,
        user: User,
    ) -> ExportResponse:
        """Export HTML to an ESP: optionally rewrite tokens, then push."""
        logger.info(
            "esp_sync.export_started",
            connection_id=connection_id,
            target_esp=target_esp,
            has_html=html is not None,
            template_id=template_id,
        )

        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        # Resolve HTML
        if html is None and template_id is not None:
            html, resolved_name = await self._fetch_template_html(template_id, user)
            if template_name == "Exported Email":
                template_name = resolved_name
        if not html:
            html = ""

        # Rewrite tokens
        html, tokens_rewritten, warnings = await self._rewrite_for_export(
            html, target_esp, source_esp, rewrite_tokens
        )

        # Push to ESP
        try:
            remote = await provider.create_template(template_name, html, credentials)
        except Exception as exc:
            await self._repo.update_status(conn, "error", str(exc))
            raise ESPSyncFailedError(f"Failed to export template: {exc}") from exc

        await self._repo.update_status(conn, "connected")
        logger.info(
            "esp_sync.export_completed",
            connection_id=connection_id,
            esp_template_id=remote.id,
            tokens_rewritten=tokens_rewritten,
        )
        return ExportResponse(
            esp_template_id=remote.id,
            template_name=template_name,
            target_esp=target_esp,
            tokens_rewritten=tokens_rewritten,
            warnings=warnings,
        )

    async def export_templates_bulk(
        self,
        template_ids: list[int],
        target_esp: str,
        connection_id: int,
        rewrite_tokens: bool,
        user: User,
    ) -> BulkExportResponse:
        """Export multiple templates to an ESP with per-item error isolation."""
        logger.info(
            "esp_sync.export_bulk_started",
            connection_id=connection_id,
            target_esp=target_esp,
            template_count=len(template_ids),
        )

        conn, credentials = await self._get_connection_with_bola(connection_id, user)
        provider = self._get_provider(conn.esp_type)

        results: list[BulkExportItemResult] = []
        succeeded = 0

        for tid in template_ids:
            try:
                html, name = await self._fetch_template_html(tid, user)
                html, tokens_rewritten, _warnings = await self._rewrite_for_export(
                    html, target_esp, None, rewrite_tokens
                )
                remote = await provider.create_template(name, html, credentials)
                results.append(
                    BulkExportItemResult(
                        template_id=tid,
                        success=True,
                        esp_template_id=remote.id,
                        tokens_rewritten=tokens_rewritten,
                    )
                )
                succeeded += 1
            except Exception as exc:
                logger.warning(
                    "esp_sync.export_bulk_item_failed",
                    template_id=tid,
                    connection_id=connection_id,
                    error=str(exc),
                )
                results.append(
                    BulkExportItemResult(
                        template_id=tid,
                        success=False,
                        error=str(exc),
                    )
                )

        logger.info(
            "esp_sync.export_bulk_completed",
            connection_id=connection_id,
            total=len(template_ids),
            succeeded=succeeded,
            failed=len(template_ids) - succeeded,
        )
        return BulkExportResponse(
            results=results,
            total=len(template_ids),
            succeeded=succeeded,
            failed=len(template_ids) - succeeded,
        )
