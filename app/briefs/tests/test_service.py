# mypy: disable-error-code="method-assign"
"""Unit tests for BriefService (mock providers and repository)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.briefs.exceptions import (
    BriefConnectionNotFoundError,
    BriefItemNotFoundError,
    BriefSyncFailedError,
    UnsupportedPlatformError,
)
from app.briefs.protocol import RawBriefItem
from app.briefs.schemas import ConnectionCreateRequest
from app.briefs.service import BriefService


def _make_user(user_id: int = 1, role: str = "developer") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_connection(
    connection_id: int = 1,
    platform: str = "jira",
    project_id: int | None = None,
    status: str = "connected",
) -> MagicMock:
    conn = MagicMock()
    conn.id = connection_id
    conn.name = "Test Connection"
    conn.platform = platform
    conn.project_url = "https://test.atlassian.net/jira/software/projects/TEST"
    conn.external_project_id = "test/TEST"
    conn.credential_last4 = "abcd"
    conn.encrypted_credentials = "encrypted"
    conn.status = status
    conn.error_message = None
    conn.project_id = project_id
    conn.last_synced_at = None
    conn.created_by_id = 1
    conn.created_at = "2026-01-01T00:00:00"
    conn.updated_at = "2026-01-01T00:00:00"
    return conn


def _make_item(item_id: int = 1, connection_id: int = 1) -> MagicMock:
    item = MagicMock()
    item.id = item_id
    item.connection_id = connection_id
    item.external_id = f"EXT-{item_id}"
    item.title = f"Task {item_id}"
    item.description = "Description"
    item.status = "open"
    item.priority = "medium"
    item.assignees = ["Alice"]
    item.labels = ["email"]
    item.due_date = None
    item.thumbnail_url = None
    item.resources = []
    item.attachments = []
    item.created_at = "2026-01-01T00:00:00"
    item.updated_at = "2026-01-01T00:00:00"
    return item


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_db: AsyncMock) -> BriefService:
    return BriefService(mock_db)


class TestListConnections:
    @pytest.mark.asyncio
    async def test_returns_connections(self, service: BriefService) -> None:
        conn = _make_connection()
        service._repo.list_connections = AsyncMock(return_value=[conn])
        user = _make_user()

        with patch("app.briefs.schemas.ConnectionResponse.from_model") as mock_from:
            mock_from.return_value = MagicMock()
            result = await service.list_connections(user)

        assert len(result) == 1
        service._repo.list_connections.assert_awaited_once_with()


class TestCreateConnection:
    @pytest.mark.asyncio
    async def test_unsupported_platform_raises(self, service: BriefService) -> None:
        user = _make_user()
        data = ConnectionCreateRequest(
            name="Test",
            platform="unsupported",
            project_url="https://example.com",
            credentials={"key": "value"},
        )

        with pytest.raises(UnsupportedPlatformError):
            await service.create_connection(data, user)

    @pytest.mark.asyncio
    async def test_creates_connection(self, service: BriefService) -> None:
        user = _make_user()
        data = ConnectionCreateRequest(
            name="Test",
            platform="jira",
            project_url="https://test.atlassian.net/jira/software/projects/TEST",
            credentials={"email": "test@test.com", "api_token": "abcdefgh"},
        )

        mock_provider = AsyncMock()
        mock_provider.validate_credentials = AsyncMock(return_value=True)
        mock_provider.extract_project_id = AsyncMock(return_value="test/TEST")

        conn = _make_connection()
        service._repo.create_connection = AsyncMock(return_value=conn)
        service._repo.get_connection = AsyncMock(return_value=conn)
        service._providers["jira"] = mock_provider

        # Mock the sync to avoid side effects
        service._sync_items = AsyncMock()

        with (
            patch("app.briefs.service.encrypt_token", return_value="encrypted"),
            patch("app.briefs.schemas.ConnectionResponse.from_model") as mock_from,
        ):
            mock_from.return_value = MagicMock()
            await service.create_connection(data, user)

        mock_provider.validate_credentials.assert_awaited_once()
        service._repo.create_connection.assert_awaited_once()


class TestDeleteConnection:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service: BriefService) -> None:
        service._repo.get_connection = AsyncMock(return_value=None)
        user = _make_user()

        with pytest.raises(BriefConnectionNotFoundError):
            await service.delete_connection(99, user)

    @pytest.mark.asyncio
    async def test_deletes_connection(self, service: BriefService) -> None:
        conn = _make_connection()
        service._repo.get_connection = AsyncMock(return_value=conn)
        service._repo.delete_connection = AsyncMock(return_value=True)
        user = _make_user()

        result = await service.delete_connection(conn.id, user)
        assert result is True


class TestSyncConnection:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service: BriefService) -> None:
        service._repo.get_connection = AsyncMock(return_value=None)
        user = _make_user()

        with pytest.raises(BriefConnectionNotFoundError):
            await service.sync_connection(99, user)


class TestGetItemDetail:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service: BriefService) -> None:
        service._repo.get_item_with_details = AsyncMock(return_value=None)
        user = _make_user()

        with pytest.raises(BriefItemNotFoundError):
            await service.get_item_detail(99, user)


class TestImportItems:
    @pytest.mark.asyncio
    async def test_missing_or_nonowned_ids_raise_not_found(self, service: BriefService) -> None:
        """get_items_by_ids is owner-scoped, so non-owned/missing ids are absent.

        An incomplete result must 404 (mirrors get_item_detail) rather than
        silently importing only the owned subset. Raises before the project
        lookup, so no DB query is mocked.
        """
        # Two ids requested, owner-scoped repo returns only one → coverage gap.
        service._repo.get_items_by_ids = AsyncMock(return_value=[_make_item(item_id=1)])
        user = _make_user()

        with pytest.raises(BriefItemNotFoundError):
            await service.import_items([1, 2], "Summer Campaign", user)


class TestSyncItems:
    @pytest.mark.asyncio
    async def test_sync_upserts_items(self, service: BriefService) -> None:
        conn = _make_connection()
        service._repo.get_connection = AsyncMock(return_value=conn)
        service._repo.update_connection_status = AsyncMock()
        service._repo.upsert_item = AsyncMock(return_value=_make_item())

        raw_items = [
            RawBriefItem(
                external_id="TEST-1",
                title="Task 1",
                description="Desc",
                status="open",
                priority="high",
                assignees=["Alice"],
                labels=["email"],
            )
        ]

        mock_provider = AsyncMock()
        mock_provider.list_items = AsyncMock(return_value=raw_items)
        service._providers["jira"] = mock_provider

        with patch(
            "app.briefs.service.decrypt_token", return_value='{"email":"a","api_token":"b"}'
        ):
            await service._sync_items(conn.id)

        service._repo.upsert_item.assert_awaited_once()
        # Verify connection status was updated to connected
        assert service._repo.update_connection_status.await_count == 2  # syncing + connected

    @pytest.mark.asyncio
    async def test_sync_failure_sets_error_status(self, service: BriefService) -> None:
        conn = _make_connection()
        service._repo.get_connection = AsyncMock(return_value=conn)
        service._repo.update_connection_status = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.list_items = AsyncMock(side_effect=RuntimeError("API error"))
        service._providers["jira"] = mock_provider

        with (
            patch("app.briefs.service.decrypt_token", return_value='{"email":"a","api_token":"b"}'),
            pytest.raises(BriefSyncFailedError),
        ):
            await service._sync_items(conn.id)
