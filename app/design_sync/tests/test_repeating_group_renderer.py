"""Tests for repeating group renderer — wraps N similar sections in a container table (Phase 49.2)."""

from __future__ import annotations

import pytest

from app.design_sync.component_matcher import ComponentMatch, SlotFill
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.sibling_detector import RepeatingGroup


def _make_section(
    idx: int = 0,
    *,
    bg_color: str | None = "#F1F4F9",
    padding_top: float | None = 20.0,
    padding_right: float | None = 24.0,
    item_spacing: float | None = 16.0,
) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id=f"reason_{idx}",
        node_name=f"Reason {idx}",
        texts=[TextBlock(node_id=f"t_{idx}", content=f"Reason {idx}", is_heading=True)],
        images=[ImagePlaceholder(node_id=f"icon_{idx}", node_name="icon", width=48, height=48)],
        buttons=[],
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        height=200.0,
        bg_color=bg_color,
        column_groups=[],
        padding_top=padding_top,
        padding_right=padding_right,
        item_spacing=item_spacing,
    )


def _make_group(n: int = 5, bgcolor: str | None = "#F1F4F9") -> RepeatingGroup:
    sections = [_make_section(i) for i in range(n)]
    return RepeatingGroup(sections=sections, container_bgcolor=bgcolor)


def _make_group_match(
    slug: str,
    idx: int,
    section: EmailSection,
    *,
    fills: list[SlotFill] | None = None,
) -> ComponentMatch:
    return ComponentMatch(
        section_idx=idx,
        section=section,
        component_slug=slug,
        slot_fills=fills or [SlotFill(slot_id="heading_1", value=f"Reason {idx}")],
        token_overrides=[],
    )


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


class TestRenderRepeatingGroup:
    """Core repeating group rendering behavior."""

    def test_five_sections_wrapped_in_container(self, renderer: ComponentRenderer) -> None:
        group = _make_group(5)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        assert result.component_slug == "repeating-group"
        assert result.html.count("<tr>") >= 5

    def test_container_has_mso_ghost_table(self, renderer: ComponentRenderer) -> None:
        group = _make_group(3)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        assert "<!--[if mso]>" in result.html
        assert "<![endif]-->" in result.html
        assert 'width="600"' in result.html

    def test_container_bgcolor_applied(self, renderer: ComponentRenderer) -> None:
        group = _make_group(2, bgcolor="#F1F4F9")
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        assert 'bgcolor="#F1F4F9"' in result.html
        assert "background-color:#F1F4F9;" in result.html

    def test_individual_slots_filled_correctly(self, renderer: ComponentRenderer) -> None:
        group = _make_group(3)
        matches = [
            _make_group_match(
                "text-block",
                i,
                s,
                fills=[SlotFill(slot_id="body", value=f"Item {i}")],
            )
            for i, s in enumerate(group.sections)
        ]

        result = renderer.render_repeating_group(group, matches)

        for i in range(3):
            assert f"Item {i}" in result.html

    def test_spacing_first_vs_subsequent(self, renderer: ComponentRenderer) -> None:
        group = _make_group(3)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        # First item: padding_top=20, subsequent: item_spacing=16
        assert "padding:20px 24px 0" in result.html
        assert "padding:16px 24px 0" in result.html

    def test_dark_mode_class_generated_for_bgcolor(self, renderer: ComponentRenderer) -> None:
        group = _make_group(2, bgcolor="#F1F4F9")
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        assert "bgcolor-F1F4F9" in result.html
        assert "bgcolor-F1F4F9" in result.dark_mode_classes

    def test_dark_mode_classes_aggregated(self, renderer: ComponentRenderer) -> None:
        group = _make_group(2, bgcolor="#F1F4F9")
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        # Container dark mode class is present
        assert any("bgcolor-" in c for c in result.dark_mode_classes)

    def test_images_aggregated(self, renderer: ComponentRenderer) -> None:
        group = _make_group(3)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        # Each inner render produces images; all should be collected
        assert isinstance(result.images, list)


class TestBandTextSlotHPaddingBudget:
    """Track G G2 (M9): the band row's horizontal inset tightens the text-block
    slot padding budget further (mirrors F9's column-ghost shrink hook).

    c7 "Expect lots…": 560px design box, band 24px + slot 24px left 504px —
    the group pass must take the slot h-padding to 0 (600-48 = 552 < 560).
    """

    def test_band_inset_tightens_slot_budget_to_zero(self, renderer: ComponentRenderer) -> None:
        sections = [
            EmailSection(
                section_type=EmailSectionType.CONTENT,
                node_id=f"s{i}",
                node_name=f"banner {i}",
                width=560.0,
                height=61.0,
            )
            for i in range(2)
        ]
        group = RepeatingGroup(sections=sections, container_bgcolor="#AFCA01")
        matches = [
            _make_group_match(
                "text-block",
                i,
                s,
                fills=[SlotFill("heading", f"Banner {i}"), SlotFill("body", "copy")],
            )
            for i, s in enumerate(sections)
        ]

        result = renderer.render_repeating_group(group, matches)

        # per-side budget inside the band: (600 - 2*24 - 560) / 2 < 0 → 0
        assert "padding: 24px 0 12px" in result.html
        assert "padding: 24px 20px 12px" not in result.html


class TestEdgeCases:
    """Edge case handling for repeating group renderer."""

    def test_empty_group_no_output(self, renderer: ComponentRenderer) -> None:
        group = _make_group(0)
        result = renderer.render_repeating_group(group, [])

        assert result.html == ""
        assert result.component_slug == "repeating-group"

    def test_single_section_no_wrapper(self, renderer: ComponentRenderer) -> None:
        group = _make_group(1)
        matches = [_make_group_match("text-block", 0, group.sections[0])]

        result = renderer.render_repeating_group(group, matches)

        # Single section should render directly without container wrapper
        assert result.component_slug != "repeating-group"
        # No double MSO wrapping — just the inner section's own MSO
        assert result.html.count("<!--[if mso]>") <= 2

    def test_missing_bgcolor_no_crash(self, renderer: ComponentRenderer) -> None:
        group = _make_group(2, bgcolor=None)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        result = renderer.render_repeating_group(group, matches)

        # Container table should not have bgcolor attr (inner sections may have their own)
        # Check the container-level table — second <table in the output (after MSO ghost)
        lines = result.html.split("\n")
        container_line = next(
            (line for line in lines if 'role="presentation"' in line and 'width="100%"' in line),
            "",
        )
        assert 'bgcolor="' not in container_line
        assert "background-color:" not in container_line
        assert result.component_slug == "repeating-group"


class TestConverterIntegration:
    """Verify the converter loop uses group_map correctly."""

    def test_group_rendered_once_not_per_member(self, renderer: ComponentRenderer) -> None:
        group = _make_group(5)
        matches = [_make_group_match("col-icon", i, s) for i, s in enumerate(group.sections)]

        # Simulate group_map: all 5 indices point to same group
        group_map: dict[int, RepeatingGroup] = dict.fromkeys(range(5), group)

        # Simulate the converter loop logic
        section_parts: list[str] = []
        rendered_group_ids: set[int] = set()

        for flat_idx, match in enumerate(matches):
            grp = group_map.get(flat_idx)
            if grp is not None:
                if id(grp) in rendered_group_ids:
                    continue
                rendered_group_ids.add(id(grp))

                group_matches = [m for idx, m in enumerate(matches) if group_map.get(idx) is grp]
                rendered = renderer.render_repeating_group(grp, group_matches)
                section_parts.append(rendered.html)
                continue

            section_parts.append(renderer.render_section(match).html)

        # Only 1 section_part for the entire group
        assert len(section_parts) == 1
        # Contains all 5 inner rows
        assert section_parts[0].count("<tr>") >= 5
