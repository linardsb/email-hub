"""Tests for embedding provider factory, specifically API key fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ai.exceptions import AIConfigurationError
from app.knowledge.embedding import OpenAIEmbeddingProvider, get_embedding_provider


def _make_settings(
    *,
    embedding_api_key: str | None = None,
    ai_api_key: str | None = None,
    provider: str = "openai",
) -> object:
    """Build a minimal settings-like object for testing."""
    from types import SimpleNamespace

    return SimpleNamespace(
        embedding=SimpleNamespace(
            provider=provider,
            model="text-embedding-3-small",
            dimension=1536,
            api_key=embedding_api_key,
            base_url=None,
        ),
        ai=SimpleNamespace(api_key=ai_api_key),
    )


class TestEmbeddingApiKeyFallback:
    """Verify that get_embedding_provider falls back to AI__API_KEY."""

    def test_uses_embedding_api_key_when_set(self) -> None:
        settings = _make_settings(embedding_api_key="emb-key", ai_api_key="ai-key")
        provider = get_embedding_provider(settings)  # type: ignore[arg-type]
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._api_key == "emb-key"

    def test_falls_back_to_ai_api_key(self) -> None:
        settings = _make_settings(embedding_api_key=None, ai_api_key="ai-key")
        provider = get_embedding_provider(settings)  # type: ignore[arg-type]
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._api_key == "ai-key"

    def test_warns_when_no_key_available(self) -> None:
        settings = _make_settings(embedding_api_key=None, ai_api_key=None)
        with patch("app.knowledge.embedding.logger") as mock_logger:
            provider = get_embedding_provider(settings)  # type: ignore[arg-type]
            mock_logger.warning.assert_called_once()
            assert "no_api_key" in mock_logger.warning.call_args[0][0]
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._api_key == ""

    @pytest.mark.asyncio
    async def test_no_key_raises_at_embed_time(self) -> None:
        settings = _make_settings(embedding_api_key=None, ai_api_key=None)
        with patch("app.knowledge.embedding.logger"):
            provider = get_embedding_provider(settings)  # type: ignore[arg-type]
        assert isinstance(provider, OpenAIEmbeddingProvider)
        with pytest.raises(AIConfigurationError, match="EMBEDDING__API_KEY or AI__API_KEY"):
            await provider.embed(["x"])

    def test_local_provider_ignores_api_key(self) -> None:
        from app.knowledge.embedding import LocalEmbeddingProvider

        settings = _make_settings(provider="local")
        provider = get_embedding_provider(settings)  # type: ignore[arg-type]
        assert isinstance(provider, LocalEmbeddingProvider)
