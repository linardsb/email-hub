"""Tests for converter low-confidence → insight bus (48.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.converter_insights import (
    extract_conversion_insights,
    persist_conversion_insights,
)
from app.design_sync.quality_contracts import QualityWarning


class _FakeSectionType(Enum):
    HERO = "hero"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _FakeSection:
    section_type: _FakeSectionType = _FakeSectionType.HERO


@dataclass(frozen=True)
class _FakeLayout:
    sections: list[_FakeSection] = field(default_factory=list[_FakeSection])


@dataclass(frozen=True)
class _FakeConversionResult:
    html: str = "<table></table>"
    sections_count: int = 3
    warnings: list[str] = field(default_factory=list[str])
    quality_warnings: list[QualityWarning] = field(default_factory=list[QualityWarning])
    match_confidences: dict[int, float] = field(default_factory=dict[int, float])
    figma_url: str | None = None
    node_id: str | None = None
    design_tokens_used: dict[str, object] | None = None
    layout: _FakeLayout | None = None


class TestExtractConversionInsights:
    def test_no_insights_high_confidence(self) -> None:
        result = _FakeConversionResult(match_confidences={0: 0.9, 1: 0.85, 2: 0.7})
        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            insights = extract_conversion_insights(result)  # type: ignore[arg-type]
        assert insights == []

    def test_single_low_confidence(self) -> None:
        result = _FakeConversionResult(
            match_confidences={0: 0.9, 1: 0.3},
            layout=_FakeLayout(
                sections=[
                    _FakeSection(_FakeSectionType.HERO),
                    _FakeSection(_FakeSectionType.FOOTER),
                ]
            ),
        )
        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            insights = extract_conversion_insights(result)  # type: ignore[arg-type]
        assert len(insights) == 1
        assert "Section 1" in insights[0].insight
        assert "footer" in insights[0].insight
        assert "30%" in insights[0].insight

    def test_groups_same_type(self) -> None:
        result = _FakeConversionResult(
            match_confidences={0: 0.3, 1: 0.4, 2: 0.9},
            layout=_FakeLayout(
                sections=[
                    _FakeSection(_FakeSectionType.HERO),
                    _FakeSection(_FakeSectionType.HERO),
                    _FakeSection(_FakeSectionType.FOOTER),
                ]
            ),
        )
        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            insights = extract_conversion_insights(result)  # type: ignore[arg-type]
        assert len(insights) == 1
        assert "Sections [0, 1]" in insights[0].insight
        assert "hero" in insights[0].insight

    def test_insight_targets_scaffolder(self) -> None:
        result = _FakeConversionResult(match_confidences={0: 0.2})
        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            insights = extract_conversion_insights(result)  # type: ignore[arg-type]
        assert insights[0].target_agents == ("scaffolder",)

    def test_insight_category_is_conversion(self) -> None:
        result = _FakeConversionResult(match_confidences={0: 0.2})
        with patch("app.design_sync.traces.converter.get_settings") as mock_settings:
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            insights = extract_conversion_insights(result)  # type: ignore[arg-type]
        assert insights[0].category == "conversion"


class TestPersistConversionInsights:
    @pytest.mark.asyncio
    async def test_fire_and_forget(self) -> None:
        result = _FakeConversionResult(match_confidences={0: 0.2})

        with (
            patch("app.design_sync.traces.converter.get_settings") as mock_settings,
            patch(
                "app.design_sync.traces.converter.persist_insights",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB down"),
            ),
        ):
            mock_settings.return_value.design_sync.conversion_memory_enabled = True
            mock_settings.return_value.design_sync.low_match_confidence_threshold = 0.6
            # Should not raise
            count = await persist_conversion_insights(result, None, None)  # type: ignore[arg-type]
            assert count == 0
