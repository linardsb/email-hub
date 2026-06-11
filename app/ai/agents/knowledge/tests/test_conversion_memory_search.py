"""Tests for Knowledge agent conversion memory search (48.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.agents.knowledge.service import (
    _is_conversion_query,
    _search_conversion_memory,
)


class TestIsConversionQuery:
    def test_positive_cases(self) -> None:
        assert _is_conversion_query("why did the conversion fail?")
        assert _is_conversion_query("What is the match confidence for hero sections?")
        assert _is_conversion_query("design sync quality warning report")
        assert _is_conversion_query("Figma converter issues")

    def test_negative_cases(self) -> None:
        assert not _is_conversion_query("what is dark mode?")
        assert not _is_conversion_query("How do I fix Outlook rendering?")
        assert not _is_conversion_query("best practices for email accessibility")


class TestSearchConversionMemory:
    @pytest.mark.asyncio
    async def test_returns_formatted(self) -> None:
        mock_memory = MagicMock()
        mock_memory.content = "Conversion quality report (sections=5, warnings=2):"
        mock_memory.metadata_json = {"source": "converter_quality"}
        mock_memory.created_at = datetime(2026, 3, 31, 12, 0, 0, tzinfo=UTC)

        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[(mock_memory, 0.8)])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.ai.agents.knowledge.service.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await _search_conversion_memory("conversion failures", None)

        assert len(results) == 1
        assert "2026-03-31" in results[0]
        assert "Conversion quality report" in results[0]

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.ai.agents.knowledge.service.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await _search_conversion_memory("conversion failures", None)

        assert results == []

    @pytest.mark.asyncio
    async def test_filters_non_converter_memories(self) -> None:
        mock_converter = MagicMock()
        mock_converter.content = "Converter quality data"
        mock_converter.metadata_json = {"source": "converter_quality"}
        mock_converter.created_at = datetime(2026, 3, 31, tzinfo=UTC)

        mock_other = MagicMock()
        mock_other.content = "Other memory"
        mock_other.metadata_json = {"source": "cross_agent_insight"}
        mock_other.created_at = datetime(2026, 3, 30, tzinfo=UTC)

        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[(mock_converter, 0.8), (mock_other, 0.7)])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.ai.agents.knowledge.service.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await _search_conversion_memory("conversion", None)

        assert len(results) == 1
        assert "Converter quality data" in results[0]

    @pytest.mark.asyncio
    async def test_handles_errors_gracefully(self) -> None:
        with patch(
            "app.core.scoped_db.get_system_db_context",
            side_effect=RuntimeError("DB down"),
        ):
            results = await _search_conversion_memory("conversion", None)
        assert results == []
