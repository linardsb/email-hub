# pyright: reportUnknownMemberType=false, reportUnknownParameterType=false
"""Unit tests for ConnectorSyncService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.exceptions import (
    ESPConnectionNotFoundError,
    ESPSyncFailedError,
    InvalidESPCredentialsError,
    InvalidRemoteTemplateIdError,
)
from app.connectors.sync_schemas import (
    ESPConnectionResponse,
    ESPTemplate,
)
from app.connectors.sync_service import PROVIDER_REGISTRY, ConnectorSyncService

# ── Helpers ──


def _make_user(role: str = "developer", user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.email = "test@example.com"
    return user


def _make_connection(
    id: int = 1,
    esp_type: str = "braze",
    project_id: int = 1,
    encrypted_credentials: str = "",
    credentials_hint: str = "****1234",
    status: str = "connected",
) -> MagicMock:
    conn = MagicMock()
    conn.id = id
    conn.esp_type = esp_type
    conn.name = "Test Connection"
    conn.encrypted_credentials = encrypted_credentials
    conn.credentials_hint = credentials_hint
    conn.status = status
    conn.error_message = None
    conn.project_id = project_id
    conn.project_name = None
    conn.created_by_id = 1
    conn.last_synced_at = None
    conn.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    conn.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return conn


def _make_esp_template(
    id: str = "tpl_1",
    name: str = "Test Template",
    html: str = "<div>Hello</div>",
    esp_type: str = "braze",
) -> ESPTemplate:
    return ESPTemplate(
        id=id,
        name=name,
        html=html,
        esp_type=esp_type,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(db: AsyncMock) -> ConnectorSyncService:
    return ConnectorSyncService(db)


# ── Provider Registry ──


class TestProviderRegistry:
    def test_registry_has_all_providers(self) -> None:
        assert {"braze", "sfmc", "adobe_campaign", "taxi"} <= set(PROVIDER_REGISTRY.keys())

    def test_get_provider_returns_instance(self, service: ConnectorSyncService) -> None:
        for key in PROVIDER_REGISTRY:
            provider = service._get_provider(key)
            assert provider is not None

    def test_get_provider_unsupported_raises(self, service: ConnectorSyncService) -> None:
        with pytest.raises(ESPSyncFailedError, match="Unsupported ESP type"):
            service._get_provider("unknown_esp")


# ── Encryption Helpers ──


class TestEncryptionHelpers:
    def test_encrypt_decrypt_roundtrip(self, service: ConnectorSyncService) -> None:
        creds = {"api_key": "secret-key-12345678"}
        encrypted = service._encrypt_credentials(creds)
        decrypted = service._decrypt_credentials(encrypted)
        assert decrypted == creds

    def test_credentials_hint_masks(self, service: ConnectorSyncService) -> None:
        hint = service._credentials_hint({"api_key": "my-secret-key-1234"})
        assert hint == "****1234"

    def test_credentials_hint_short_value(self, service: ConnectorSyncService) -> None:
        hint = service._credentials_hint({"api_key": "ab"})
        assert hint == "****"

    def test_credentials_hint_empty(self, service: ConnectorSyncService) -> None:
        hint = service._credentials_hint({"api_key": ""})
        assert hint == "****"


# ── Create Connection ──


class TestCreateConnection:
    @pytest.mark.asyncio
    async def test_create_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        mock_conn = _make_connection()

        with (
            patch.object(service._project_service, "verify_project_access", new_callable=AsyncMock),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._repo, "create_connection", new_callable=AsyncMock, return_value=mock_conn
            ),
            patch.object(service, "_encrypt_credentials", return_value="encrypted"),
        ):
            mock_provider = AsyncMock()
            mock_provider.validate_credentials = AsyncMock(return_value=True)
            mock_get_provider.return_value = mock_provider

            from app.connectors.sync_schemas import ESPConnectionCreate

            data = ESPConnectionCreate(
                esp_type="braze",
                name="Test",
                project_id=1,
                credentials={"api_key": "test-key-1234"},
            )
            result = await service.create_connection(data, user)

        assert isinstance(result, ESPConnectionResponse)
        mock_provider.validate_credentials.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_invalid_credentials(self, service: ConnectorSyncService) -> None:
        user = _make_user()

        with (
            patch.object(service._project_service, "verify_project_access", new_callable=AsyncMock),
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            mock_provider = AsyncMock()
            mock_provider.validate_credentials = AsyncMock(return_value=False)
            mock_get_provider.return_value = mock_provider

            from app.connectors.sync_schemas import ESPConnectionCreate

            data = ESPConnectionCreate(
                esp_type="braze",
                name="Test",
                project_id=1,
                credentials={"api_key": "bad-key"},
            )
            with pytest.raises(InvalidESPCredentialsError):
                await service.create_connection(data, user)

    @pytest.mark.asyncio
    async def test_create_bola_denied(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        from app.projects.exceptions import ProjectAccessDeniedError

        with patch.object(
            service._project_service,
            "verify_project_access",
            new_callable=AsyncMock,
            side_effect=ProjectAccessDeniedError("denied"),
        ):
            from app.connectors.sync_schemas import ESPConnectionCreate

            data = ESPConnectionCreate(
                esp_type="braze",
                name="Test",
                project_id=99,
                credentials={"api_key": "key"},
            )
            with pytest.raises(ProjectAccessDeniedError):
                await service.create_connection(data, user)


# ── List Connections ──


class TestListConnections:
    @pytest.mark.asyncio
    async def test_list_returns_accessible(self, service: ConnectorSyncService) -> None:
        user = _make_user(role="developer")
        conn = _make_connection()

        with (
            patch.object(
                service, "_get_accessible_project_ids", new_callable=AsyncMock, return_value=[1]
            ),
            patch.object(
                service._repo,
                "list_connections_for_user",
                new_callable=AsyncMock,
                return_value=[(conn, "My Project")],
            ),
        ):
            result = await service.list_connections(user)

        assert len(result) == 1
        assert result[0].project_name == "My Project"


# ── Get Connection ──


class TestGetConnection:
    @pytest.mark.asyncio
    async def test_get_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()

        with (
            patch.object(
                service._repo, "get_connection", new_callable=AsyncMock, return_value=conn
            ),
            patch.object(service._project_service, "verify_project_access", new_callable=AsyncMock),
        ):
            result = await service.get_connection(1, user)

        assert isinstance(result, ESPConnectionResponse)

    @pytest.mark.asyncio
    async def test_get_not_found(self, service: ConnectorSyncService) -> None:
        user = _make_user()

        with patch.object(
            service._repo, "get_connection", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ESPConnectionNotFoundError):
                await service.get_connection(999, user)

    @pytest.mark.asyncio
    async def test_get_bola_denied(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection(project_id=99)
        from app.projects.exceptions import ProjectAccessDeniedError

        with (
            patch.object(
                service._repo, "get_connection", new_callable=AsyncMock, return_value=conn
            ),
            patch.object(
                service._project_service,
                "verify_project_access",
                new_callable=AsyncMock,
                side_effect=ProjectAccessDeniedError("denied"),
            ),
        ):
            with pytest.raises(ProjectAccessDeniedError):
                await service.get_connection(1, user)


# ── Delete Connection ──


class TestDeleteConnection:
    @pytest.mark.asyncio
    async def test_delete_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()

        with (
            patch.object(
                service._repo, "get_connection", new_callable=AsyncMock, return_value=conn
            ),
            patch.object(service._project_service, "verify_project_access", new_callable=AsyncMock),
            patch.object(service._repo, "delete_connection", new_callable=AsyncMock) as mock_delete,
        ):
            await service.delete_connection(1, user)
            mock_delete.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service: ConnectorSyncService) -> None:
        user = _make_user()

        with patch.object(
            service._repo, "get_connection", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ESPConnectionNotFoundError):
                await service.delete_connection(999, user)

    @pytest.mark.asyncio
    async def test_delete_bola_denied(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection(project_id=99)
        from app.projects.exceptions import ProjectAccessDeniedError

        with (
            patch.object(
                service._repo, "get_connection", new_callable=AsyncMock, return_value=conn
            ),
            patch.object(
                service._project_service,
                "verify_project_access",
                new_callable=AsyncMock,
                side_effect=ProjectAccessDeniedError("denied"),
            ),
        ):
            with pytest.raises(ProjectAccessDeniedError):
                await service.delete_connection(1, user)


# ── List Remote Templates ──


class TestListRemoteTemplates:
    @pytest.mark.asyncio
    async def test_list_remote_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()
        templates = [_make_esp_template()]

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._repo, "update_status", new_callable=AsyncMock
            ) as mock_update_status,
        ):
            mock_provider = AsyncMock()
            mock_provider.list_templates = AsyncMock(return_value=templates)
            mock_get_provider.return_value = mock_provider

            result = await service.list_remote_templates(1, user)

            assert result.count == 1
            assert result.templates[0].id == "tpl_1"
            mock_update_status.assert_awaited_once_with(conn, "connected")

    @pytest.mark.asyncio
    async def test_list_remote_provider_error(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._repo, "update_status", new_callable=AsyncMock
            ) as mock_update_status,
        ):
            mock_provider = AsyncMock()
            mock_provider.list_templates = AsyncMock(side_effect=Exception("API down"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(ESPSyncFailedError, match="Failed to list templates"):
                await service.list_remote_templates(1, user)

            mock_update_status.assert_awaited_once_with(conn, "error", "API down")


# ── Get Remote Template ──


class TestGetRemoteTemplate:
    @pytest.mark.asyncio
    async def test_get_remote_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()
        tpl = _make_esp_template()

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            mock_provider = AsyncMock()
            mock_provider.get_template = AsyncMock(return_value=tpl)
            mock_get_provider.return_value = mock_provider

            result = await service.get_remote_template(1, "tpl_1", user)

        assert result.id == "tpl_1"

    @pytest.mark.asyncio
    async def test_get_remote_provider_error(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            mock_provider = AsyncMock()
            mock_provider.get_template = AsyncMock(side_effect=Exception("Not found"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(ESPSyncFailedError, match="Failed to get template"):
                await service.get_remote_template(1, "tpl_missing", user)


# ── Import Template ──


class TestImportTemplate:
    @pytest.mark.asyncio
    async def test_import_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection(esp_type="braze")
        remote_tpl = _make_esp_template(id="remote_1", name="ESP Welcome")
        local_tpl = MagicMock()
        local_tpl.id = 42

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._template_service,
                "create_template",
                new_callable=AsyncMock,
                return_value=local_tpl,
            ) as mock_create_template,
        ):
            mock_provider = AsyncMock()
            mock_provider.get_template = AsyncMock(return_value=remote_tpl)
            mock_get_provider.return_value = mock_provider

            result = await service.import_template(1, "remote_1", user)

            assert result == 42
            # Verify template created with correct name prefix
            call_kwargs = mock_create_template.call_args
            template_data = call_kwargs.kwargs["data"]
            assert template_data.name == "[braze] ESP Welcome"
            assert "remote_1" in template_data.description

    @pytest.mark.asyncio
    async def test_import_provider_error(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            mock_provider = AsyncMock()
            mock_provider.get_template = AsyncMock(side_effect=Exception("API error"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(ESPSyncFailedError, match="Failed to fetch remote template"):
                await service.import_template(1, "tpl_1", user)


# ── Remote Template ID Guard ──

_BAD_REMOTE_IDS = ["../account", "a/b", "a?b=c", "a#b", "..", ".hidden", "", "a b", "x" * 257]
_GOOD_REMOTE_IDS = [
    "tpl_1",
    "d-55",
    "TMPL_5",
    "cb_2",
    "200",
    "09024c5a-5864-46a4-b061-eed128b2af2d",
    "@AbC-12_x",
]


class TestRemoteTemplateIdGuard:
    """The remote ID is a provider URL path segment; malformed IDs never reach the wire."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _BAD_REMOTE_IDS)
    async def test_get_remote_rejects_malformed_id(
        self, service: ConnectorSyncService, template_id: str
    ) -> None:
        with (
            patch.object(service, "_get_connection_with_bola", new_callable=AsyncMock) as bola,
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            with pytest.raises(InvalidRemoteTemplateIdError):
                await service.get_remote_template(1, template_id, _make_user())
        bola.assert_not_called()
        mock_get_provider.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _BAD_REMOTE_IDS)
    async def test_import_rejects_malformed_id(
        self, service: ConnectorSyncService, template_id: str
    ) -> None:
        with (
            patch.object(service, "_get_connection_with_bola", new_callable=AsyncMock) as bola,
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            with pytest.raises(InvalidRemoteTemplateIdError):
                await service.import_template(1, template_id, _make_user())
        bola.assert_not_called()
        mock_get_provider.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _GOOD_REMOTE_IDS)
    async def test_get_remote_accepts_real_id_shapes(
        self, service: ConnectorSyncService, template_id: str
    ) -> None:
        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(_make_connection(), {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
        ):
            mock_provider = AsyncMock()
            mock_provider.get_template = AsyncMock(return_value=_make_esp_template(id=template_id))
            mock_get_provider.return_value = mock_provider

            result = await service.get_remote_template(1, template_id, _make_user())

        mock_provider.get_template.assert_awaited_once_with(template_id, {"api_key": "k"})
        assert result.id == template_id


# ── Push Template ──


class TestPushTemplate:
    @pytest.mark.asyncio
    async def test_push_success(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()
        local_tpl = MagicMock()
        local_tpl.name = "My Email"
        local_tpl.latest_version = 2
        version = MagicMock()
        version.html_source = "<div>Content</div>"
        remote_tpl = _make_esp_template(id="remote_new")

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._template_service,
                "get_template",
                new_callable=AsyncMock,
                return_value=local_tpl,
            ),
            patch.object(
                service._template_service,
                "get_version",
                new_callable=AsyncMock,
                return_value=version,
            ),
            patch.object(
                service._repo, "update_status", new_callable=AsyncMock
            ) as mock_update_status,
        ):
            mock_provider = AsyncMock()
            mock_provider.create_template = AsyncMock(return_value=remote_tpl)
            mock_get_provider.return_value = mock_provider

            result = await service.push_template(1, 10, user)

            assert result.id == "remote_new"
            mock_provider.create_template.assert_awaited_once_with(
                "My Email", "<div>Content</div>", {"api_key": "k"}
            )
            mock_update_status.assert_awaited_once_with(conn, "connected")

    @pytest.mark.asyncio
    async def test_push_no_version(self, service: ConnectorSyncService) -> None:
        """Push with no template versions sends empty HTML."""
        user = _make_user()
        conn = _make_connection()
        local_tpl = MagicMock()
        local_tpl.name = "Empty"
        local_tpl.latest_version = None
        remote_tpl = _make_esp_template(id="remote_empty")

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._template_service,
                "get_template",
                new_callable=AsyncMock,
                return_value=local_tpl,
            ),
            patch.object(service._repo, "update_status", new_callable=AsyncMock),
        ):
            mock_provider = AsyncMock()
            mock_provider.create_template = AsyncMock(return_value=remote_tpl)
            mock_get_provider.return_value = mock_provider

            await service.push_template(1, 10, user)

        mock_provider.create_template.assert_awaited_once_with("Empty", "", {"api_key": "k"})

    @pytest.mark.asyncio
    async def test_push_provider_error(self, service: ConnectorSyncService) -> None:
        user = _make_user()
        conn = _make_connection()
        local_tpl = MagicMock()
        local_tpl.name = "My Email"
        local_tpl.latest_version = 1
        version = MagicMock()
        version.html_source = "<div>Content</div>"

        with (
            patch.object(
                service,
                "_get_connection_with_bola",
                new_callable=AsyncMock,
                return_value=(conn, {"api_key": "k"}),
            ),
            patch.object(service, "_get_provider") as mock_get_provider,
            patch.object(
                service._template_service,
                "get_template",
                new_callable=AsyncMock,
                return_value=local_tpl,
            ),
            patch.object(
                service._template_service,
                "get_version",
                new_callable=AsyncMock,
                return_value=version,
            ),
            patch.object(
                service._repo, "update_status", new_callable=AsyncMock
            ) as mock_update_status,
        ):
            mock_provider = AsyncMock()
            mock_provider.create_template = AsyncMock(side_effect=Exception("ESP error"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(ESPSyncFailedError, match="Failed to push template"):
                await service.push_template(1, 10, user)

            mock_update_status.assert_awaited_once_with(conn, "error", "ESP error")
