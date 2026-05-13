"""Tests for converter quality persistence to memory (48.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.design_sync.converter_memory import (
    _CLEAN_CONFIDENCE_THRESHOLD,
    _MAX_CONTENT_LENGTH,
    build_conversion_metadata,
    format_conversion_quality,
    persist_conversion_quality,
)
from app.design_sync.quality_contracts import QualityWarning


@dataclass(frozen=True)
class _FakeConversionResult:
    """Minimal stub matching ConversionResult fields used by converter_memory."""

    html: str = "<table></table>"
    sections_count: int = 5
    warnings: list[str] = field(default_factory=list[str])
    quality_warnings: list[QualityWarning] = field(default_factory=list[QualityWarning])
    match_confidences: dict[int, float] = field(default_factory=dict[int, float])
    figma_url: str | None = None
    node_id: str | None = None
    design_tokens_used: dict[str, object] | None = None


def _make_warning(
    category: Literal["contrast", "completeness", "placeholder", "image_bgcolor"] = "contrast",
    severity: Literal["error", "warning", "info"] = "warning",
    message: str = "Low contrast ratio",
) -> QualityWarning:
    return QualityWarning(category=category, severity=severity, message=message)


class TestFormatConversionQuality:
    def test_with_warnings(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[
                _make_warning("contrast", "warning", "Ratio 2.1 below 4.5"),
                _make_warning("completeness", "error", "Missing CTA button"),
            ],
            match_confidences={0: 0.95, 1: 0.72, 2: 0.41},
            figma_url="https://figma.com/file/abc",
        )
        content = format_conversion_quality(result)  # type: ignore[arg-type]
        assert content is not None
        assert "contrast (warning)" in content
        assert "completeness (error)" in content
        assert "Low-confidence matches" in content
        assert "sections [2]" in content
        assert "https://figma.com/file/abc" in content
        assert len(content) <= _MAX_CONTENT_LENGTH

    def test_clean_returns_none(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[],
            match_confidences={0: 0.95, 1: 0.88},
        )
        assert format_conversion_quality(result) is None  # type: ignore[arg-type]

    def test_content_truncation(self) -> None:
        warnings = [
            _make_warning("contrast", "warning", f"Warning message #{i} " + "x" * 100)
            for i in range(100)
        ]
        result = _FakeConversionResult(quality_warnings=warnings)
        content = format_conversion_quality(result)  # type: ignore[arg-type]
        assert content is not None
        assert len(content) <= _MAX_CONTENT_LENGTH
        assert content.endswith("...")

    def test_design_tokens_included(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[_make_warning()],
            design_tokens_used={"primary_color": "#1a1a1a", "font_family": "Arial"},
        )
        content = format_conversion_quality(result)  # type: ignore[arg-type]
        assert content is not None
        assert "#1a1a1a" in content
        assert "Arial" in content


class TestBuildConversionMetadata:
    def test_all_keys_present(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[_make_warning()],
            match_confidences={0: 0.9, 1: 0.4},
            figma_url="https://figma.com/file/abc",
            node_id="2833:1623",
        )
        meta = build_conversion_metadata(result, "42")  # type: ignore[arg-type]
        assert meta["source"] == "converter_quality"
        assert meta["connection_id"] == "42"
        assert meta["figma_url"] == "https://figma.com/file/abc"
        assert meta["node_id"] == "2833:1623"
        assert meta["sections_count"] == 5
        assert meta["warning_count"] == 1
        assert meta["warning_categories"] == ["contrast"]
        assert isinstance(meta["avg_match_confidence"], float)
        assert meta["low_confidence_sections"] == [1]
        assert meta["has_quality_issues"] is True


class TestPersistConversionQuality:
    @pytest.mark.asyncio
    async def test_skips_clean_conversion(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[],
            match_confidences={0: 0.95, 1: _CLEAN_CONFIDENCE_THRESHOLD},
        )
        mock_service = AsyncMock()

        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.conversion_memory_enabled = True
            await persist_conversion_quality(result, None, None)  # type: ignore[arg-type]

        mock_service.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_quality_issues(self) -> None:
        result = _FakeConversionResult(
            quality_warnings=[_make_warning()],
            match_confidences={0: 0.5},
            figma_url="https://figma.com/file/xyz",
        )
        mock_service = AsyncMock()

        with (
            patch("app.design_sync.traces.converter.get_settings") as mock_settings,
            patch("app.core.database.get_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider") as mock_embed,
            patch("app.memory.service.MemoryService", return_value=mock_service),
        ):
            mock_settings.return_value.design_sync.conversion_memory_enabled = True
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_embed.return_value = MagicMock()

            await persist_conversion_quality(result, "42", 7)  # type: ignore[arg-type]

        mock_service.store.assert_called_once()
        call_args = mock_service.store.call_args[0][0]
        assert call_args.agent_type == "design_sync"
        assert call_args.memory_type == "semantic"
        assert call_args.project_id == 7
        assert call_args.is_evergreen is False
        assert "contrast" in call_args.content

    @pytest.mark.asyncio
    async def test_fire_and_forget(self) -> None:
        """Exception in store() doesn't propagate."""
        result = _FakeConversionResult(quality_warnings=[_make_warning()])

        with (
            patch("app.design_sync.traces.converter.get_settings") as mock_settings,
            patch("app.core.database.get_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider") as mock_embed,
            patch(
                "app.memory.service.MemoryService",
                return_value=AsyncMock(store=AsyncMock(side_effect=RuntimeError("DB down"))),
            ),
        ):
            mock_settings.return_value.design_sync.conversion_memory_enabled = True
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_embed.return_value = MagicMock()

            # Should not raise
            await persist_conversion_quality(result, None, None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_respects_config_gate(self) -> None:
        result = _FakeConversionResult(quality_warnings=[_make_warning()])

        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.conversion_memory_enabled = False
            # Should return early, no DB interaction
            await persist_conversion_quality(result, None, None)  # type: ignore[arg-type]
