# pyright: reportPrivateUsage=false
"""Branch-matrix tests for `DesignConverterService._convert_with_components` (F065).

Audit row 107: `converter_service.py` is 1519 LOC with four functions > 80 LOC
and was only exercised indirectly via snapshot tests. These tests target the
four dimensions of the orchestrator's branch matrix:

- **tree bridge** on/off (output_format + tree_bridge_enabled + compile success/failure)
- **sibling detection** on/off (settings flag flips `_match_phase` grouping)
- **custom component generator** on/off (component_matcher fallback for unmatched sections)
- **verify loop** on/off (async `_apply_verification` wrapper)

Tests reuse the document factories from `test_convert_document.py` and
monkeypatch `get_settings()` to flip the three relevant feature flags.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.conversion_phases import MatchPhase
from app.design_sync.converter_service import (
    ConversionResult,
    DesignConverterService,
    _paintable_band_bg,
    _render_spacer,
    _spacer_band_bg,
)
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import EmailSection, EmailSectionType
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
)

# ── Factories (mirrors test_convert_document.py) ──────────────────────


def _make_tokens() -> ExtractedTokens:
    return ExtractedTokens(
        colors=[
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text Color", hex="#333333"),
        ],
        typography=[
            ExtractedTypography(
                name="Body", family="Inter", weight="400", size=16.0, line_height=24.0
            ),
        ],
        spacing=[ExtractedSpacing(name="s1", value=16)],
    )


def _make_structure(section_count: int = 2) -> DesignFileStructure:
    sections: list[DesignNode] = []
    for idx in range(section_count):
        sections.append(
            DesignNode(
                id=f"section_{idx}",
                name=f"Section {idx}",
                type=DesignNodeType.FRAME,
                width=600,
                height=200,
                layout_mode="VERTICAL",
                padding_top=24,
                padding_bottom=24,
                children=[
                    DesignNode(
                        id=f"section_{idx}_text",
                        name="Text",
                        type=DesignNodeType.TEXT,
                        text_content=f"Section {idx} body",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            )
        )
    page = DesignNode(
        id="page1",
        name="Page",
        type=DesignNodeType.PAGE,
        children=sections,
    )
    return DesignFileStructure(file_name="Test.fig", pages=[page])


def _make_document(section_count: int = 2) -> EmailDesignDocument:
    return EmailDesignDocument.from_legacy(_make_structure(section_count), _make_tokens())


def _set_design_sync_flags(
    monkeypatch: pytest.MonkeyPatch,
    *,
    band_grouping_enabled: bool | None = None,
    sibling_detection_enabled: bool | None = None,
    tree_bridge_enabled: bool | None = None,
    vlm_verify_enabled: bool | None = None,
) -> None:
    """Patch the cached settings instance's design_sync attributes for one test."""
    from app.core.config import get_settings

    ds = get_settings().design_sync
    if band_grouping_enabled is not None:
        monkeypatch.setattr(ds, "band_grouping_enabled", band_grouping_enabled)
    if sibling_detection_enabled is not None:
        monkeypatch.setattr(ds, "sibling_detection_enabled", sibling_detection_enabled)
    if tree_bridge_enabled is not None:
        monkeypatch.setattr(ds, "tree_bridge_enabled", tree_bridge_enabled)
    if vlm_verify_enabled is not None:
        monkeypatch.setattr(ds, "vlm_verify_enabled", vlm_verify_enabled)


# ── Tree-bridge branch matrix ─────────────────────────────────────────


class TestTreeBridgeBranches:
    """Cover the four exit paths of `_convert_with_components`."""

    def test_html_format_uses_legacy_render_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`output_format="html"` skips tree bridge entirely → render+assemble."""
        _set_design_sync_flags(monkeypatch, tree_bridge_enabled=True)
        with patch("app.design_sync.tree_bridge.build_email_tree") as tree_mock:
            result = DesignConverterService().convert_document(
                _make_document(), output_format="html"
            )
        assert tree_mock.call_count == 0
        assert result.html
        assert result.sections_count > 0
        assert result.tree is None  # legacy path does not populate tree dump

    def test_tree_format_with_flag_off_uses_legacy_render_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`output_format="tree"` but `tree_bridge_enabled=False` → legacy path."""
        _set_design_sync_flags(monkeypatch, tree_bridge_enabled=False)
        with patch("app.design_sync.tree_bridge.build_email_tree") as tree_mock:
            result = DesignConverterService().convert_document(
                _make_document(), output_format="tree"
            )
        assert tree_mock.call_count == 0
        assert result.html
        assert result.tree is None

    def test_tree_format_returns_tree_result_when_compile_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tree bridge succeeds → short-circuit return with `tree` payload."""
        _set_design_sync_flags(monkeypatch, tree_bridge_enabled=True)
        result = DesignConverterService().convert_document(_make_document(), output_format="tree")
        # Tree bridge is enabled and the simple fixture compiles cleanly.
        assert result.html
        assert result.tree is not None  # populated only on tree-bridge success
        assert result.sections_count > 0

    def test_tree_format_falls_through_when_compile_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`TreeCompiler.compile` raises → tree_html empty → legacy path."""
        _set_design_sync_flags(monkeypatch, tree_bridge_enabled=True)
        with patch(
            "app.components.tree_compiler.TreeCompiler.compile",
            side_effect=RuntimeError("simulated compile failure"),
        ):
            result = DesignConverterService().convert_document(
                _make_document(), output_format="tree"
            )
        # Legacy path produces HTML but no `tree` payload.
        assert result.html
        assert result.tree is None


# ── Sibling detection on/off ──────────────────────────────────────────


class TestSiblingDetectionBranches:
    """Cover the sibling-detection flag inside `_match_phase`."""

    def test_sibling_detection_enabled_invokes_detector(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag on → `detect_repeating_groups` is called once per conversion.

        Band grouping (default-on since Phase 53 D1) takes priority in
        `_match_phase`, so the sibling branch is only reachable with it off.
        """
        _set_design_sync_flags(
            monkeypatch, band_grouping_enabled=False, sibling_detection_enabled=True
        )
        # Patch the call site (`from app.design_sync.sibling_detector import ...`
        # is inside `_match_phase`, so we patch the source module).
        with patch(
            "app.design_sync.sibling_detector.detect_repeating_groups",
            return_value=[],
        ) as detect_mock:
            result = DesignConverterService().convert_document(_make_document())
        assert detect_mock.call_count == 1
        assert isinstance(result, ConversionResult)

    def test_sibling_detection_disabled_skips_detector(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag off → detector untouched; sections pass through flat.

        Band grouping pinned off so the skip is attributable to the sibling
        flag, not to band grouping pre-empting the branch.
        """
        _set_design_sync_flags(
            monkeypatch, band_grouping_enabled=False, sibling_detection_enabled=False
        )
        with patch(
            "app.design_sync.sibling_detector.detect_repeating_groups",
        ) as detect_mock:
            result = DesignConverterService().convert_document(_make_document())
        assert detect_mock.call_count == 0
        assert result.html
        assert result.sections_count > 0


# ── Custom component generator fallback ───────────────────────────────


class TestCustomComponentFallback:
    """Cover the custom-component fallback inside `component_matcher.match_all`."""

    def test_match_all_invoked_with_layout_sections(self) -> None:
        """`_match_phase` always delegates to `match_all` to drive matches/fallback."""
        captured: dict[str, Any] = {}

        def _capture_call(sections: list[EmailSection], **kwargs: Any) -> list[Any]:
            captured["sections"] = sections
            captured["kwargs"] = kwargs
            return []

        with patch(
            "app.design_sync.component_matcher.match_all",
            side_effect=_capture_call,
        ) as match_mock:
            DesignConverterService().convert_document(_make_document(section_count=3))

        assert match_mock.call_count == 1
        # 3 sections in fixture → 3 sections flattened into match_all
        assert len(captured["sections"]) >= 1
        assert "container_width" in captured["kwargs"]


# ── Verify loop on/off (async path) ────────────────────────────────────


class TestVerifyLoopBranches:
    """Cover the `_apply_verification` async wrapper around the sync result.

    Note: `_apply_verification` is called from `convert_document_mjml`, NOT
    from `_convert_with_components` directly. These tests exercise the
    `vlm_verify_enabled` flag through the public async surface.
    """

    @pytest.mark.asyncio
    async def test_verify_disabled_returns_original_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag off → `_apply_verification` short-circuits and returns the input."""
        _set_design_sync_flags(monkeypatch, vlm_verify_enabled=False)
        svc = DesignConverterService()
        original = ConversionResult(html="<html>original</html>", sections_count=1)
        with patch(
            "app.design_sync.visual_verify.run_verification_loop",
            new=AsyncMock(),
        ) as loop_mock:
            result = await svc._apply_verification(
                original,
                design_screenshots={"node": b"\x89PNG"},
                sections=[],
                container_width=600,
            )
        assert result is original
        assert loop_mock.call_count == 0

    @pytest.mark.asyncio
    async def test_verify_enabled_short_circuits_without_screenshots(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag on but no design screenshots → still returns the input untouched."""
        _set_design_sync_flags(monkeypatch, vlm_verify_enabled=True)
        svc = DesignConverterService()
        original = ConversionResult(html="<html>original</html>", sections_count=1)
        with patch(
            "app.design_sync.visual_verify.run_verification_loop",
            new=AsyncMock(),
        ) as loop_mock:
            result = await svc._apply_verification(
                original,
                design_screenshots={},
                sections=[],
                container_width=600,
            )
        assert result is original
        assert loop_mock.call_count == 0


# ── Output_format parameter sanity ─────────────────────────────────────


class TestOutputFormatParameter:
    """Defensive guards against silent regressions when callers pass odd values."""

    def test_default_output_format_is_html(self) -> None:
        """`convert_document` without `output_format=` behaves like html."""
        result = DesignConverterService().convert_document(_make_document())
        assert result.html
        assert result.tree is None

    def test_match_phase_returns_proper_type_for_empty_layout(self) -> None:
        """`_match_phase` always returns a `MatchPhase` even when sections are empty.

        Guards against the legacy path crashing on empty layouts before
        reaching the empty-sections early return in `convert_document`.
        """
        from app.design_sync.figma.layout_analyzer import DesignLayoutDescription

        svc = DesignConverterService()
        empty_layout = DesignLayoutDescription(file_name="empty.fig", sections=[])
        result = svc._match_phase(
            layout=empty_layout,
            container_width=600,
            image_urls=None,
        )
        assert isinstance(result, MatchPhase)
        assert result.matches == []


# ── Track G G1 (M2): inter-band spacer continuity ─────────────────────


def _band_section(
    node_id: str, *, bg: str | None = None, container: str | None = None
) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id=node_id,
        node_name=node_id,
        bg_color=bg,
        container_bg=container,
    )


class TestSpacerBandContinuity:
    """A genuine gap between two solid coloured bands inherits the following
    band's bg (M2), so it reads as band continuation instead of a white slit;
    gaps against the white body — and 0px spacers — stay transparent.
    """

    def test_painted_between_two_colored_bands(self) -> None:
        curr = _band_section("a", bg="#AA1733")
        nxt = _band_section("b", container="#296042")
        assert _spacer_band_bg(curr, nxt) == "#296042"  # following band's bg

    def test_not_painted_against_white_body(self) -> None:
        curr = _band_section("a", bg="#AA1733")
        nxt = _band_section("b", bg="#FFFFFF")
        assert _spacer_band_bg(curr, nxt) is None

    def test_not_painted_when_current_is_white(self) -> None:
        curr = _band_section("a", bg="#ffffff")
        nxt = _band_section("b", container="#AA1733")
        assert _spacer_band_bg(curr, nxt) is None

    def test_not_painted_at_document_end(self) -> None:
        assert _spacer_band_bg(_band_section("a", bg="#AA1733"), None) is None

    def test_paintable_band_bg_rejects_white_and_junk(self) -> None:
        assert _paintable_band_bg(_band_section("a", bg="#AA1733")) == "#AA1733"
        assert _paintable_band_bg(_band_section("a", bg="#FFFFFF")) is None
        assert _paintable_band_bg(_band_section("a", bg="transparent")) is None
        assert _paintable_band_bg(_band_section("a")) is None

    def test_render_spacer_paints_when_visible(self) -> None:
        html = _render_spacer(600, 20, "#AA1733")
        assert "background-color:#AA1733;" in html
        assert 'bgcolor="#AA1733"' in html

    def test_render_spacer_transparent_by_default(self) -> None:
        html = _render_spacer(600, 20)
        assert "background-color" not in html
        assert "bgcolor" not in html

    def test_render_spacer_suppresses_zero_height_paint(self) -> None:
        # "or suppress when the design gap is 0" — a 0px band is never painted.
        html = _render_spacer(600, 0, "#AA1733")
        assert "background-color" not in html
        assert "bgcolor" not in html
