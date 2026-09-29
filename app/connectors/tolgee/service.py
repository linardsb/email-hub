"""Tolgee TMS business logic orchestrator."""

from __future__ import annotations

import asyncio
import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.connectors.sync_models import ESPConnection
from app.connectors.sync_repository import ESPSyncRepository
from app.connectors.tolgee.builder import build_all_locales
from app.connectors.tolgee.client import TolgeeClient
from app.connectors.tolgee.exceptions import (
    TolgeeAuthenticationError,
    TolgeeBaseUrlNotAllowedError,
    TolgeeConnectionError,
    TolgeeSyncError,
)
from app.connectors.tolgee.extractor import extract_keys
from app.connectors.tolgee.schemas import (
    LocaleBuildRequest,
    LocaleBuildResponse,
    TolgeeConnectionRequest,
    TolgeeConnectionResponse,
    TolgeeLanguage,
    TranslationPullRequest,
    TranslationPullResponse,
    TranslationSyncRequest,
    TranslationSyncResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.crypto import decrypt_token, encrypt_token
from app.projects.service import ProjectService
from app.templates.repository import TemplateRepository

logger = get_logger(__name__)


def _resolve_base_url(requested: str | None) -> str:
    """Return the configured Tolgee base URL matching ``requested``.

    The PAT is sent to this URL, so a caller may only pick from the configured
    default and ``TOLGEE__ALLOWED_BASE_URLS``. The configured string is returned,
    never the caller's.
    """
    settings = get_settings()
    if requested is None:
        return settings.tolgee.base_url
    wanted = requested.rstrip("/")
    for allowed in (settings.tolgee.base_url, *settings.tolgee.allowed_base_urls):
        if allowed.rstrip("/") == wanted:
            return allowed.rstrip("/")
    raise TolgeeBaseUrlNotAllowedError("Tolgee base URL is not in TOLGEE__ALLOWED_BASE_URLS")


class TolgeeService:
    """Orchestrates Tolgee TMS operations: connect, sync keys, pull translations, build locales."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ESPSyncRepository(db)
        self._project_svc = ProjectService(db)
        self._template_repo = TemplateRepository(db)

    # --- Connection management ---

    async def create_connection(
        self, request: TolgeeConnectionRequest, user: User
    ) -> TolgeeConnectionResponse:
        """Create and validate a Tolgee connection."""
        await self._project_svc.verify_project_access(request.project_id, user)

        base_url = _resolve_base_url(request.base_url)

        # Validate PAT
        client = TolgeeClient(base_url, request.pat)
        if not await client.validate_connection():
            raise TolgeeAuthenticationError("Invalid Tolgee PAT or unreachable instance")

        # Store as ESPConnection (reusing model — esp_type="tolgee")
        credentials = {
            "pat": request.pat,
            "base_url": base_url,
            "tolgee_project_id": str(request.tolgee_project_id),
        }
        encrypted = encrypt_token(json.dumps(credentials))
        hint = request.pat[-4:] if len(request.pat) >= 4 else "****"

        connection = await self._repo.create_connection(
            esp_type="tolgee",
            name=request.name,
            encrypted_credentials=encrypted,
            credentials_hint=f"****{hint}",
            project_id=request.project_id,
            created_by_id=user.id,
        )

        return self._to_response(connection)

    async def get_connection(self, connection_id: int, user: User) -> TolgeeConnectionResponse:
        """Get a Tolgee connection by ID."""
        connection = await self._repo.get_connection(connection_id)
        if not connection:
            raise TolgeeConnectionError(f"Connection {connection_id} not found")
        await self._project_svc.verify_project_access(connection.project_id, user)
        return self._to_response(connection)

    # --- Key extraction & sync ---

    async def sync_keys(
        self, request: TranslationSyncRequest, user: User
    ) -> TranslationSyncResponse:
        """Extract translatable keys from a template and push to Tolgee."""
        connection = await self._get_verified_connection(request.connection_id, user)
        credentials = self._decrypt_credentials(connection)
        client = self._make_client(credentials)

        # Get latest template version HTML
        template = await self._template_repo.get(request.template_id)
        if not template:
            raise TolgeeSyncError(f"Template {request.template_id} not found")

        latest_num = await self._template_repo.get_latest_version_number(request.template_id)
        if latest_num == 0:
            raise TolgeeSyncError(f"No versions found for template {request.template_id}")

        latest_version = await self._template_repo.get_version(request.template_id, latest_num)
        if not latest_version:
            raise TolgeeSyncError(f"No versions found for template {request.template_id}")

        # Extract keys
        keys = extract_keys(
            latest_version.html_source,
            request.template_id,
            namespace=request.namespace,
            subject=template.subject_line,
            preheader=template.preheader_text,
        )

        # Push to Tolgee
        tolgee_project_id = int(credentials["tolgee_project_id"])
        push_result = await client.push_keys(tolgee_project_id, keys)

        # Update last_synced_at
        await self._repo.update_status(connection, "connected")

        logger.info(
            "tolgee.keys_synced",
            template_id=request.template_id,
            keys_extracted=len(keys),
            created=push_result.created,
            updated=push_result.updated,
        )

        return TranslationSyncResponse(
            keys_extracted=len(keys),
            push_result=push_result,
            template_id=request.template_id,
        )

    # --- Pull translations ---

    async def pull_translations(
        self, request: TranslationPullRequest, user: User
    ) -> list[TranslationPullResponse]:
        """Pull translations from Tolgee for specified locales."""
        connection = await self._get_verified_connection(request.connection_id, user)
        credentials = self._decrypt_credentials(connection)
        client = self._make_client(credentials)

        tolgee_project_id = request.tolgee_project_id
        results: list[TranslationPullResponse] = []

        for locale in request.locales:
            translations = await client.get_translations(
                tolgee_project_id, locale, request.namespace
            )
            results.append(
                TranslationPullResponse(
                    locale=locale,
                    translations_count=len(translations),
                    translations=translations,
                )
            )

        await self._repo.update_status(connection, "connected")

        logger.info(
            "tolgee.translations_pulled",
            locales=request.locales,
            total_keys=sum(r.translations_count for r in results),
        )

        return results

    # --- Locale builds ---

    async def build_locales(self, request: LocaleBuildRequest, user: User) -> LocaleBuildResponse:
        """Pull translations and build email in multiple locales."""
        settings = get_settings()
        if len(request.locales) > settings.tolgee.max_locales_per_build:
            raise TolgeeSyncError(f"Max {settings.tolgee.max_locales_per_build} locales per build")

        connection = await self._get_verified_connection(request.connection_id, user)
        credentials = self._decrypt_credentials(connection)
        client = self._make_client(credentials)

        # Get template HTML
        latest_num = await self._template_repo.get_latest_version_number(request.template_id)
        if latest_num == 0:
            raise TolgeeSyncError(f"No versions for template {request.template_id}")

        latest_version = await self._template_repo.get_version(request.template_id, latest_num)
        if not latest_version:
            raise TolgeeSyncError(f"No versions for template {request.template_id}")

        source_html = latest_version.html_source

        # Extract source text for reverse mapping (key → source_text)
        keys = extract_keys(
            source_html, request.template_id, namespace=request.namespace or "email"
        )
        key_to_source: dict[str, str] = {k.key: k.source_text for k in keys}

        # Pull translations for all locales concurrently
        start = time.monotonic()

        async def _pull_locale(locale: str) -> tuple[str, dict[str, str]]:
            tolgee_translations = await client.get_translations(
                request.tolgee_project_id, locale, request.namespace
            )
            source_to_translated: dict[str, str] = {}
            for key, translated in tolgee_translations.items():
                source_text = key_to_source.get(key)
                if source_text and translated:
                    source_to_translated[source_text] = translated
            return locale, source_to_translated

        pull_results = await asyncio.gather(*[_pull_locale(loc) for loc in request.locales])
        locale_translations: dict[str, dict[str, str]] = dict(pull_results)

        # Build all locales concurrently
        results = await build_all_locales(
            source_html,
            locale_translations,
            is_production=request.is_production,
        )

        total_ms = (time.monotonic() - start) * 1000

        logger.info(
            "tolgee.locales_built",
            template_id=request.template_id,
            locales=request.locales,
            total_build_time_ms=round(total_ms, 1),
        )

        return LocaleBuildResponse(
            template_id=request.template_id,
            results=results,
            total_build_time_ms=round(total_ms, 1),
        )

    # --- Languages ---

    async def get_languages(self, connection_id: int, user: User) -> list[TolgeeLanguage]:
        """List languages available in the connected Tolgee project."""
        connection = await self._get_verified_connection(connection_id, user)
        credentials = self._decrypt_credentials(connection)
        client = self._make_client(credentials)
        tolgee_project_id = int(credentials["tolgee_project_id"])
        return await client.get_languages(tolgee_project_id)

    # --- Helpers ---

    async def _get_verified_connection(self, connection_id: int, user: User) -> ESPConnection:
        """Get connection with BOLA check."""
        connection = await self._repo.get_connection(connection_id)
        if not connection:
            raise TolgeeConnectionError(f"Connection {connection_id} not found")
        await self._project_svc.verify_project_access(connection.project_id, user)
        return connection

    def _decrypt_credentials(self, connection: ESPConnection) -> dict[str, str]:
        """Decrypt stored credentials."""
        raw: dict[str, str] = json.loads(decrypt_token(connection.encrypted_credentials))
        return raw

    def _make_client(self, credentials: dict[str, str]) -> TolgeeClient:
        """Create a TolgeeClient from decrypted credentials."""
        settings = get_settings()
        return TolgeeClient(
            base_url=credentials.get("base_url", settings.tolgee.base_url),
            pat=credentials["pat"],
            timeout=settings.tolgee.request_timeout,
        )

    def _to_response(self, connection: ESPConnection) -> TolgeeConnectionResponse:
        """Convert ESPConnection to Tolgee response schema."""
        credentials = self._decrypt_credentials(connection)
        tolgee_project_id = credentials.get("tolgee_project_id")
        return TolgeeConnectionResponse(
            id=connection.id,
            name=connection.name,
            status=connection.status,
            credentials_hint=connection.credentials_hint,
            tolgee_project_id=int(tolgee_project_id) if tolgee_project_id else None,
            project_id=connection.project_id,
            last_synced_at=connection.last_synced_at,
            created_at=connection.created_at,  # pyright: ignore[reportArgumentType]
        )
