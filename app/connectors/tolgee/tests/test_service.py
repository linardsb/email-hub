"""Unit tests for TolgeeService with mocked dependencies."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.tolgee.exceptions import (
    TolgeeAuthenticationError,
    TolgeeBaseUrlNotAllowedError,
    TolgeeConnectionError,
)
from app.connectors.tolgee.schemas import (
    LocaleBuildRequest,
    TolgeeConnectionRequest,
    TranslationPullRequest,
    TranslationSyncRequest,
)
from app.connectors.tolgee.service import TolgeeService


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = "developer"
    return user


def _make_connection(
    connection_id: int = 1,
    project_id: int = 1,
    credentials: dict[str, str] | None = None,
) -> MagicMock:
    conn = MagicMock()
    conn.id = connection_id
    conn.project_id = project_id
    conn.name = "Test Tolgee"
    conn.status = "connected"
    conn.credentials_hint = "****test"
    conn.last_synced_at = None
    conn.created_at = datetime.now(UTC)
    conn.esp_type = "tolgee"

    creds = credentials or {
        "pat": "tgpat_test123",
        "base_url": "http://tolgee.test",
        "tolgee_project_id": "42",
    }
    conn.encrypted_credentials = json.dumps(creds)  # Will be patched
    return conn


def _make_template_version(
    html: str = "<html><body><td>Hello World</td></body></html>",
) -> MagicMock:
    version = MagicMock()
    version.html_source = html
    return version


def _make_template(
    subject: str = "Test Subject",
    preheader: str = "Test Preheader",
) -> MagicMock:
    tmpl = MagicMock()
    tmpl.subject_line = subject
    tmpl.preheader_text = preheader
    return tmpl


class TestCreateConnection:
    """Tests for connection creation."""

    @pytest.mark.asyncio
    async def test_creates_connection_with_valid_pat(self) -> None:
        db = AsyncMock()
        service = TolgeeService(db)
        user = _make_user()

        request = TolgeeConnectionRequest(
            name="My Tolgee",
            project_id=1,
            tolgee_project_id=42,
            pat="tgpat_valid_token",
        )

        mock_conn = _make_connection()

        with (
            patch.object(service, "_project_svc") as mock_proj,
            patch("app.connectors.tolgee.service.TolgeeClient") as mock_client_cls,
            patch("app.connectors.tolgee.service.encrypt_token", return_value="encrypted"),
            patch(
                "app.connectors.tolgee.service.decrypt_token",
                return_value=json.dumps(
                    {
                        "pat": "tgpat_valid_token",
                        "base_url": "http://localhost:25432",
                        "tolgee_project_id": "42",
                    }
                ),
            ),
        ):
            mock_proj.verify_project_access = AsyncMock()
            mock_client_inst = AsyncMock()
            mock_client_inst.validate_connection.return_value = True
            mock_client_cls.return_value = mock_client_inst
            service._repo = AsyncMock()
            service._repo.create_connection = AsyncMock(return_value=mock_conn)

            result = await service.create_connection(request, user)

        assert result.name == "Test Tolgee"
        assert result.status == "connected"

    @pytest.mark.asyncio
    async def test_invalid_pat_raises(self) -> None:
        db = AsyncMock()
        service = TolgeeService(db)
        user = _make_user()

        request = TolgeeConnectionRequest(
            name="Bad Tolgee",
            project_id=1,
            tolgee_project_id=42,
            pat="invalid_pat",
        )

        with (
            patch.object(service, "_project_svc") as mock_proj,
            patch("app.connectors.tolgee.service.TolgeeClient") as mock_client_cls,
        ):
            mock_proj.verify_project_access = AsyncMock()
            mock_client_inst = AsyncMock()
            mock_client_inst.validate_connection.return_value = False
            mock_client_cls.return_value = mock_client_inst

            with pytest.raises(TolgeeAuthenticationError):
                await service.create_connection(request, user)


class TestBaseUrlAllowlist:
    """`base_url` overrides must match a configured Tolgee base URL (CodeQL py/partial-ssrf)."""

    @staticmethod
    def _settings(allowed: list[str]) -> MagicMock:
        settings = MagicMock()
        settings.tolgee.base_url = "http://localhost:25432"
        settings.tolgee.allowed_base_urls = allowed
        return settings

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "base_url",
        [
            "http://169.254.169.254/latest/meta-data",
            "http://localhost:25432.evil.test",
            "https://tolgee.example.com/../admin",
        ],
    )
    async def test_unlisted_base_url_rejected_before_any_request(self, base_url: str) -> None:
        service = TolgeeService(AsyncMock())
        request = TolgeeConnectionRequest(
            name="Evil", project_id=1, tolgee_project_id=42, base_url=base_url, pat="tgpat_x"
        )
        with (
            patch.object(service, "_project_svc") as mock_proj,
            patch("app.connectors.tolgee.service.TolgeeClient") as mock_client_cls,
            patch(
                "app.connectors.tolgee.service.get_settings",
                return_value=self._settings(["https://tolgee.example.com"]),
            ),
        ):
            mock_proj.verify_project_access = AsyncMock()
            with pytest.raises(TolgeeBaseUrlNotAllowedError):
                await service.create_connection(request, _make_user())
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("base_url", "expected"),
        [
            (None, "http://localhost:25432"),
            ("http://localhost:25432/", "http://localhost:25432"),
            ("https://tolgee.example.com", "https://tolgee.example.com"),
        ],
    )
    async def test_default_and_listed_base_urls_accepted(
        self, base_url: str | None, expected: str
    ) -> None:
        service = TolgeeService(AsyncMock())
        request = TolgeeConnectionRequest(
            name="Ok", project_id=1, tolgee_project_id=42, base_url=base_url, pat="tgpat_x"
        )
        with (
            patch.object(service, "_project_svc") as mock_proj,
            patch("app.connectors.tolgee.service.TolgeeClient") as mock_client_cls,
            patch(
                "app.connectors.tolgee.service.get_settings",
                return_value=self._settings(["https://tolgee.example.com/"]),
            ),
            patch("app.connectors.tolgee.service.encrypt_token", return_value="encrypted"),
            patch(
                "app.connectors.tolgee.service.decrypt_token",
                return_value=json.dumps({"pat": "tgpat_x", "tolgee_project_id": "42"}),
            ),
        ):
            mock_proj.verify_project_access = AsyncMock()
            mock_client_inst = AsyncMock()
            mock_client_inst.validate_connection.return_value = True
            mock_client_cls.return_value = mock_client_inst
            service._repo = AsyncMock()
            service._repo.create_connection = AsyncMock(return_value=_make_connection())

            await service.create_connection(request, _make_user())

        assert mock_client_cls.call_args.args[0] == expected


class TestSyncKeys:
    """Tests for key extraction and sync."""

    @pytest.mark.asyncio
    async def test_extracts_and_pushes_keys(self) -> None:
        db = AsyncMock()
        service = TolgeeService(db)
        user = _make_user()

        request = TranslationSyncRequest(
            connection_id=1,
            template_id=5,
        )

        mock_conn = _make_connection()
        mock_template = _make_template()
        mock_version = _make_template_version()

        with (
            patch.object(
                service, "_get_verified_connection", new_callable=AsyncMock, return_value=mock_conn
            ),
            patch.object(
                service,
                "_decrypt_credentials",
                return_value={
                    "pat": "tgpat_test",
                    "base_url": "http://tolgee.test",
                    "tolgee_project_id": "42",
                },
            ),
            patch.object(service, "_make_client") as mock_make_client,
        ):
            from app.connectors.tolgee.schemas import PushResult

            mock_client = AsyncMock()
            mock_client.push_keys.return_value = PushResult(created=1, updated=0, skipped=0)
            mock_make_client.return_value = mock_client

            service._template_repo = AsyncMock()
            service._template_repo.get.return_value = mock_template
            service._template_repo.get_latest_version_number.return_value = 1
            service._template_repo.get_version.return_value = mock_version
            service._repo = AsyncMock()

            result = await service.sync_keys(request, user)

        assert result.keys_extracted >= 1
        assert result.template_id == 5
        mock_client.push_keys.assert_called_once()


class TestPullTranslations:
    """Tests for pulling translations."""

    @pytest.mark.asyncio
    async def test_pulls_for_multiple_locales(self) -> None:
        db = AsyncMock()
        service = TolgeeService(db)
        user = _make_user()

        request = TranslationPullRequest(
            connection_id=1,
            tolgee_project_id=42,
            locales=["de", "fr"],
        )

        mock_conn = _make_connection()

        with (
            patch.object(
                service, "_get_verified_connection", new_callable=AsyncMock, return_value=mock_conn
            ),
            patch.object(
                service,
                "_decrypt_credentials",
                return_value={
                    "pat": "tgpat_test",
                    "base_url": "http://tolgee.test",
                    "tolgee_project_id": "42",
                },
            ),
            patch.object(service, "_make_client") as mock_make_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_translations.return_value = {"key1": "translated"}
            mock_make_client.return_value = mock_client
            service._repo = AsyncMock()

            results = await service.pull_translations(request, user)

        assert len(results) == 2
        assert results[0].locale == "de"
        assert results[1].locale == "fr"


class TestBuildLocales:
    """Tests for locale build orchestration."""

    @pytest.mark.asyncio
    async def test_max_locales_schema_validation(self) -> None:
        """Pydantic schema enforces max 20 locales."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="too_long"):
            LocaleBuildRequest(
                connection_id=1,
                template_id=1,
                tolgee_project_id=42,
                locales=["en"] * 21,
            )

    @pytest.mark.parametrize("locale", ["../../v2/projects", "de/../../admin", "de?x=1", ""])
    def test_non_bcp47_locale_rejected(self, locale: str) -> None:
        """Locales land in the Tolgee URL path, so they must be BCP-47 tags."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="string_pattern_mismatch"):
            LocaleBuildRequest(
                connection_id=1, template_id=1, tolgee_project_id=42, locales=[locale]
            )

    @pytest.mark.asyncio
    async def test_connection_not_found_raises(self) -> None:
        db = AsyncMock()
        service = TolgeeService(db)
        user = _make_user()

        request = TranslationSyncRequest(connection_id=999, template_id=1)

        service._repo = AsyncMock()
        service._repo.get_connection.return_value = None
        service._project_svc = AsyncMock()

        with pytest.raises(TolgeeConnectionError, match="999"):
            await service.sync_keys(request, user)
