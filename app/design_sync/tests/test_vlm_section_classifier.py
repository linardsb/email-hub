"""Tests for Phase 41.7 VLM section type classification.

Covers:
- VLMSectionClassification model (2 tests)
- VLMSectionClassifier service (4 tests)
- Confidence scoring in _classify_section sub-functions (3 tests)
- Hybrid merge in analyze_layout (3 tests)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.figma.layout_analyzer import (
    EmailSectionType,
    _classify_by_name,
    _classify_by_position,
    analyze_layout,
)
from app.design_sync.tests.conftest import make_design_node, make_file_structure
from app.design_sync.vlm_classifier import (
    VLMSectionClassification,
    VLMSectionClassifier,
    clear_section_cache,
)

_FAKE_SCREENSHOT = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_section_cache()


# ── VLMSectionClassification Model Tests ──


class TestVLMSectionClassification:
    def test_model_fields(self) -> None:
        c = VLMSectionClassification(
            node_id="n1",
            section_type="hero",
            confidence=0.9,
            reasoning="Big image",
            column_layout="single",
            content_signals=("large_image", "heading"),
        )
        assert c.node_id == "n1"
        assert c.section_type == "hero"
        assert c.confidence == 0.9
        assert c.reasoning == "Big image"
        assert c.column_layout == "single"
        assert c.content_signals == ("large_image", "heading")

    def test_model_defaults(self) -> None:
        c = VLMSectionClassification(node_id="n2", section_type="footer", confidence=0.8)
        assert c.reasoning == ""
        assert c.column_layout is None
        assert c.content_signals == ()


# ── VLMSectionClassifier Service Tests ──


def _make_provider(content: str, *, side_effect: Exception | None = None) -> AsyncMock:
    provider = AsyncMock()
    if side_effect:
        provider.complete.side_effect = side_effect
    else:
        from app.ai.protocols import CompletionResponse

        provider.complete.return_value = CompletionResponse(
            content=content,
            model="test",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
    return provider


def _mock_settings(*, enabled: bool = True, timeout: float = 15.0) -> Any:
    mock_ds = type(
        "DS",
        (),
        {
            "vlm_classification_enabled": enabled,
            "vlm_classification_model": "",
            "vlm_classification_confidence_threshold": 0.7,
            "vlm_classification_timeout": timeout,
        },
    )()
    mock_s = type("S", (), {"design_sync": mock_ds})()
    return patch("app.design_sync.vlm_classifier.get_settings", return_value=mock_s)


class TestVLMSectionClassifier:
    @pytest.mark.asyncio
    async def test_classify_sections_success(self) -> None:
        response_json = json.dumps(
            [
                {
                    "node_id": "n1",
                    "section_type": "hero",
                    "confidence": 0.9,
                    "reasoning": "Large image",
                    "column_layout": "single",
                    "content_signals": ["large_image"],
                },
                {
                    "node_id": "n2",
                    "section_type": "footer",
                    "confidence": 0.85,
                    "reasoning": "Legal text",
                    "column_layout": "single",
                    "content_signals": ["legal"],
                },
            ]
        )
        provider = _make_provider(response_json)
        screenshots = {"n1": _FAKE_SCREENSHOT, "n2": _FAKE_SCREENSHOT}
        metadata = [
            {"node_id": "n1", "name": "Frame 1", "index": 0, "total": 2},
            {"node_id": "n2", "name": "Frame 2", "index": 1, "total": 2},
        ]

        with (
            _mock_settings(enabled=True),
            patch("app.ai.registry.get_registry") as mock_reg,
            patch("app.ai.routing.resolve_model_by_capabilities", return_value="test-model"),
        ):
            mock_reg.return_value.get_llm.return_value = provider
            classifier = VLMSectionClassifier()
            result = await classifier.classify_sections(screenshots, metadata)

        assert len(result) == 2
        assert result["n1"].section_type == "hero"
        assert result["n1"].confidence == 0.9
        assert result["n2"].section_type == "footer"

    @pytest.mark.asyncio
    async def test_classify_sections_timeout(self) -> None:
        """Timeout returns empty dict gracefully."""
        provider = AsyncMock()
        # Make the provider hang
        provider.complete.side_effect = lambda *_a, **_kw: asyncio.sleep(100)

        screenshots = {"n1": _FAKE_SCREENSHOT}
        metadata = [{"node_id": "n1", "name": "Frame 1", "index": 0, "total": 1}]

        with (
            _mock_settings(enabled=True, timeout=0.01),
            patch("app.ai.registry.get_registry") as mock_reg,
            patch("app.ai.routing.resolve_model_by_capabilities", return_value="test-model"),
        ):
            mock_reg.return_value.get_llm.return_value = provider
            classifier = VLMSectionClassifier()
            result = await classifier.classify_sections(screenshots, metadata)

        assert result == {}

    @pytest.mark.asyncio
    async def test_classify_sections_api_error(self) -> None:
        """API error returns empty dict gracefully."""
        provider = _make_provider("", side_effect=RuntimeError("API down"))
        screenshots = {"n1": _FAKE_SCREENSHOT}
        metadata = [{"node_id": "n1", "name": "Frame 1", "index": 0, "total": 1}]

        with (
            _mock_settings(enabled=True),
            patch("app.ai.registry.get_registry") as mock_reg,
            patch("app.ai.routing.resolve_model_by_capabilities", return_value="test-model"),
        ):
            mock_reg.return_value.get_llm.return_value = provider
            classifier = VLMSectionClassifier()
            result = await classifier.classify_sections(screenshots, metadata)

        assert result == {}

    @pytest.mark.asyncio
    async def test_classify_sections_disabled(self) -> None:
        """Flag off returns empty dict without API call."""
        screenshots = {"n1": _FAKE_SCREENSHOT}
        metadata = [{"node_id": "n1", "name": "Frame 1", "index": 0, "total": 1}]

        with _mock_settings(enabled=False):
            classifier = VLMSectionClassifier()
            result = await classifier.classify_sections(screenshots, metadata)

        assert result == {}


# ── Confidence Scoring Tests ──


class TestClassifyWithConfidence:
    def test_name_match_high_confidence(self) -> None:
        """Name-based match returns high confidence."""
        section_type, confidence = _classify_by_name("hero-banner")
        assert section_type == EmailSectionType.HERO
        assert confidence == 0.90

    def test_position_fallback_low_confidence(self) -> None:
        """Position-based fallback returns low confidence."""
        node = make_design_node(id="f1", name="xyz-unknown", height=500.0)
        section_type, confidence = _classify_by_position(node, 3, 8, False)
        assert section_type == EmailSectionType.CONTENT
        assert confidence == 0.40

    def test_unknown_returns_low_confidence(self) -> None:
        """No name match returns UNKNOWN with low confidence."""
        section_type, confidence = _classify_by_name("asdfqwerty")
        assert section_type == EmailSectionType.UNKNOWN
        assert confidence == 0.30


# ── Hybrid Merge Tests ──


def _mock_layout_settings() -> Any:
    """Mock settings for analyze_layout merge logic."""
    mock_ds = type(
        "DS",
        (),
        {
            "vlm_classification_enabled": True,
            "vlm_classification_model": "",
            "vlm_classification_confidence_threshold": 0.7,
            "vlm_classification_timeout": 15.0,
            "nested_card_detection_enabled": False,
            "nested_card_perceptual_threshold": 30,
            "physical_card_detection_enabled": False,
            "physical_card_min_signals": 2,
            "frame_export_fallback_enabled": False,
        },
    )()
    mock_s = type("S", (), {"design_sync": mock_ds})()
    return patch(
        "app.design_sync.figma.layout_analyzer.get_settings",
        return_value=mock_s,
    )


class TestHybridMerge:
    def test_high_confidence_rule_keeps_result(self) -> None:
        """Rule confidence > 0.9 wins even when VLM disagrees."""
        # "hero" name gives 0.90 confidence — but custom map gives 1.0
        frame = make_design_node(id="f1", name="hero-section")
        structure = make_file_structure(frame)

        vlm_cls = {
            "f1": VLMSectionClassification(
                node_id="f1",
                section_type="footer",
                confidence=0.95,
            ),
        }

        with _mock_layout_settings():
            layout = analyze_layout(
                structure,
                section_name_map={"hero-section": "hero"},
                vlm_classifications=vlm_cls,
            )

        # Custom map confidence = 1.0 > 0.9 threshold, so rule wins
        assert layout.sections[0].section_type == EmailSectionType.HERO

    def test_unknown_overridden_by_vlm(self) -> None:
        """Rule returns UNKNOWN (low conf), VLM says HERO (high conf) -> HERO."""
        frame = make_design_node(id="f1", name="xyz-gibberish", height=500.0)
        structure = make_file_structure(frame)

        vlm_cls = {
            "f1": VLMSectionClassification(
                node_id="f1",
                section_type="hero",
                confidence=0.85,
            ),
        }

        with _mock_layout_settings():
            layout = analyze_layout(structure, vlm_classifications=vlm_cls)

        # Name match fails -> content/position fallback gives low confidence
        # VLM hero at 0.85 >= 0.7 threshold overrides
        assert layout.sections[0].section_type == EmailSectionType.HERO
        assert layout.sections[0].vlm_classification == "hero"
        assert layout.sections[0].vlm_confidence == 0.85

    def test_vlm_below_threshold_keeps_rule(self) -> None:
        """VLM confidence below threshold keeps rule result."""
        frame = make_design_node(id="f1", name="xyz-gibberish", height=500.0)
        structure = make_file_structure(frame)

        vlm_cls = {
            "f1": VLMSectionClassification(
                node_id="f1",
                section_type="hero",
                confidence=0.5,  # Below 0.7 threshold
            ),
        }

        with _mock_layout_settings():
            layout = analyze_layout(structure, vlm_classifications=vlm_cls)

        # VLM below threshold -> keep rule result (CONTENT from position fallback)
        assert layout.sections[0].section_type != EmailSectionType.HERO
        assert layout.sections[0].vlm_classification == "hero"
        assert layout.sections[0].vlm_confidence == 0.5
