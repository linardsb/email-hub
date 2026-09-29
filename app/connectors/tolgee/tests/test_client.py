"""Unit tests for TolgeeClient with httpx mocking."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.connectors.tolgee.client import TolgeeClient
from app.connectors.tolgee.schemas import TranslationKey


@pytest.fixture
def client() -> TolgeeClient:
    return TolgeeClient(base_url="http://tolgee.test", pat="tgpat_test123")


class TestTolgeeClient:
    """Tests for TolgeeClient HTTP operations."""

    @pytest.mark.asyncio
    async def test_list_projects(self, client: TolgeeClient) -> None:
        """Parses paginated Tolgee project response."""
        mock_response = httpx.Response(
            200,
            json={
                "_embedded": {
                    "projects": [
                        {"id": 1, "name": "Email Campaign", "description": "Main project"},
                        {"id": 2, "name": "Marketing", "description": ""},
                    ]
                }
            },
        )
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            projects = await client.list_projects()
        assert len(projects) == 2
        assert projects[0].name == "Email Campaign"
        assert projects[1].id == 2

    @pytest.mark.asyncio
    async def test_get_languages(self, client: TolgeeClient) -> None:
        """Parses language list response."""
        mock_response = httpx.Response(
            200,
            json={
                "_embedded": {
                    "languages": [
                        {
                            "id": 1,
                            "tag": "en",
                            "name": "English",
                            "originalName": "English",
                            "flagEmoji": "🇬🇧",
                            "base": True,
                        },
                        {
                            "id": 2,
                            "tag": "de",
                            "name": "German",
                            "originalName": "Deutsch",
                            "flagEmoji": "🇩🇪",
                            "base": False,
                        },
                    ]
                }
            },
        )
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            languages = await client.get_languages(project_id=1)
        assert len(languages) == 2
        assert languages[0].tag == "en"
        assert languages[0].base is True
        assert languages[1].original_name == "Deutsch"

    @pytest.mark.asyncio
    async def test_get_translations_flat_format(self, client: TolgeeClient) -> None:
        """Parses flat {key: text} response format."""
        mock_response = httpx.Response(
            200,
            json={
                "email.hero.heading": "Willkommen",
                "email.hero.body": "Entdecken Sie unsere Angebote",
            },
        )
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            translations = await client.get_translations(project_id=1, language="de")
        assert translations["email.hero.heading"] == "Willkommen"
        assert len(translations) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language", ["../keys", "de/../../x", "de?x=1", ""])
    async def test_get_translations_rejects_non_bcp47_language(
        self, client: TolgeeClient, language: str
    ) -> None:
        """`language` is a URL path segment; anything but a BCP-47 tag never reaches the wire."""
        with patch(
            "app.connectors.tolgee.client.resilient_request", new_callable=AsyncMock
        ) as mock_request:
            with pytest.raises(ValueError, match="Invalid BCP-47 locale"):
                await client.get_translations(project_id=1, language=language)
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_id", ["1/../2", "-1", "1?x=1"])
    async def test_get_translations_rejects_non_numeric_project_id(
        self, client: TolgeeClient, project_id: str
    ) -> None:
        """`project_id` is a URL path segment; only digits reach the wire."""
        with patch(
            "app.connectors.tolgee.client.resilient_request", new_callable=AsyncMock
        ) as mock_request:
            with pytest.raises(ValueError, match="Invalid Tolgee project id"):
                await client.get_translations(project_id=project_id, language="de")  # type: ignore[arg-type]
        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_translations_nested_format(self, client: TolgeeClient) -> None:
        """Parses nested {key: {text: "..."}} response format."""
        mock_response = httpx.Response(
            200,
            json={
                "email.hero.heading": {"text": "Willkommen"},
                "email.hero.body": {"text": "Hallo Welt"},
            },
        )
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            translations = await client.get_translations(project_id=1, language="de")
        assert translations["email.hero.heading"] == "Willkommen"

    @pytest.mark.asyncio
    async def test_push_keys(self, client: TolgeeClient) -> None:
        """Correct payload structure and result parsing."""
        mock_response = httpx.Response(
            200,
            json={"created": 3, "updated": 1, "skipped": 0},
        )
        keys = [
            TranslationKey(key="t.hero.h1", source_text="Welcome"),
            TranslationKey(key="t.hero.p", source_text="Hello world"),
            TranslationKey(key="t.cta.a", source_text="Shop Now"),
        ]
        mock_fn = AsyncMock(return_value=mock_response)
        with patch("app.connectors.tolgee.client.resilient_request", mock_fn):
            result = await client.push_keys(project_id=1, keys=keys)

        assert result.created == 3
        assert result.updated == 1
        # Verify payload structure
        call_kwargs = mock_fn.call_args
        assert call_kwargs.kwargs["json"]["keys"][0]["name"] == "t.hero.h1"
        assert call_kwargs.kwargs["json"]["keys"][0]["translations"]["en"] == "Welcome"

    @pytest.mark.asyncio
    async def test_validate_connection_success(self, client: TolgeeClient) -> None:
        """Returns True when list_projects succeeds."""
        mock_response = httpx.Response(200, json={"_embedded": {"projects": []}})
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            assert await client.validate_connection() is True

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self, client: TolgeeClient) -> None:
        """Returns False when list_projects fails."""
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "401", request=httpx.Request("GET", "http://x"), response=httpx.Response(401)
            ),
        ):
            assert await client.validate_connection() is False

    @pytest.mark.asyncio
    async def test_export_translations(self, client: TolgeeClient) -> None:
        """Export returns binary content."""
        mock_response = httpx.Response(200, content=b'{"key":"value"}')
        with patch(
            "app.connectors.tolgee.client.resilient_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            data = await client.export_translations(
                project_id=1, format="JSON", languages=["en", "de"]
            )
        assert data == b'{"key":"value"}'
