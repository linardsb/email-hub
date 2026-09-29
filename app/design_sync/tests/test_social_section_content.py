"""T1: social-classified sections render their text and divider content.

A SOCIAL section used to render only its icon row (``_fills_social``), dropping the
footer legal texts and in-column dividers that sit beside the icons. These tests drive
the real converter on the ``data/debug`` corpus and assert on the rendered section.
Ledger: ``phase-53g-g11-social-section-drops-column-content``.
"""

from __future__ import annotations

import dataclasses
import re
from unittest.mock import patch

from app.design_sync import component_matcher
from app.design_sync.component_matcher import ComponentMatch, _fills_social
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import ButtonElement, EmailSection
from app.design_sync.tests.test_snapshot_regression import _DEBUG_DIR, _run_conversion

_ICON_IMG = 'width="32" height="32"'


def _section_chunk(case_id: str, idx: int) -> str:
    html = _run_conversion(_DEBUG_DIR / case_id).html
    m = re.search(
        rf"<!-- section:section_{idx} -->(.*?)<!-- /section:section_{idx} -->", html, re.DOTALL
    )
    assert m, f"section_{idx} not found in case {case_id}"
    return m.group(1)


def _social_matches(case_id: str) -> list[ComponentMatch]:
    captured: list[list[ComponentMatch]] = []
    original = component_matcher.match_all

    def spy(*args: object, **kwargs: object) -> list[ComponentMatch]:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        captured.append(result)
        return result

    with patch.object(component_matcher, "match_all", spy):
        _run_conversion(_DEBUG_DIR / case_id)
    return [m for m in captured[-1] if m.component_slug == "social-icons"]


class TestSocialSectionRendersContent:
    def test_c8_footer_keeps_legal_texts_and_divider_in_order(self) -> None:
        chunk = _section_chunk("8", 10)
        first = chunk.find("automatically generated email")
        rule = chunk.find("border-top:1px solid #373737")
        second = chunk.find("Ferrari N.V.")
        assert first != -1 and rule != -1 and second != -1
        assert chunk.rfind(_ICON_IMG) < first < rule < second

    def test_c9_label_above_icons_legal_below(self) -> None:
        chunk = _section_chunk("9", 9)
        label = chunk.find("FOLLOW US")
        assert label != -1
        assert label < chunk.find(_ICON_IMG)
        for text in ("Privacy Policy", "Unsubscribe"):
            pos = chunk.find(text)
            assert pos > chunk.rfind(_ICON_IMG), text

    def test_c9_template_label_blanked_when_design_has_text(self) -> None:
        chunk = _section_chunk("9", 9)
        assert "Follow us" not in chunk

    def test_c10_footer_keeps_legal_texts(self) -> None:
        chunk = _section_chunk("10", 14)
        assert "Privacy Policy" in chunk
        assert "Mammut Sports Group" in chunk

    def test_c6_footer_and_peeled_column_keep_texts(self) -> None:
        assert "26-6-NWSL" in _section_chunk("6", 8)
        assert "REWARDS" in _section_chunk("6", 7)

    def test_icon_row_is_nested_when_text_rows_present(self) -> None:
        (match,) = _social_matches("8")
        links = next(f for f in match.slot_fills if f.slot_id == "social_links")
        assert links.value.startswith('<tr><td align="center"><table role="presentation"')
        # every top-level row of the slot table is a single cell
        top_rows = re.sub(r"<table.*?</table>", "", links.value, flags=re.DOTALL)
        for row in re.findall(r"<tr>(.*?)</tr>", top_rows, re.DOTALL):
            assert row.count("<td") == 1

    def test_blanked_label_row_collapses_and_design_padding_moves_down(self) -> None:
        """F1: the emptied label leaves no padded ghost row above the footer."""
        chunk = _section_chunk("8", 10)
        assert 'data-slot="social_label"' not in chunk
        links_td = re.search(r'<td style="([^"]*)">\s*<table data-slot="social_links"', chunk)
        assert links_td is not None
        assert "padding:40px 40px 40px 40px" in links_td.group(1)


def _icon_only_c8() -> EmailSection:
    (match,) = _social_matches("8")
    section = match.section
    group = dataclasses.replace(section.column_groups[0], texts=[], dividers=[])
    return dataclasses.replace(section, texts=[], column_groups=[group])


# `_fills_social` value for `_icon_only_c8()` captured from the pre-T1 code at f26ee233.
_PRE_T1_ICON_ROW = (
    "<tr>"
    + "".join(
        '<td style="padding: 0 8px;"><a href="#" style="text-decoration: none;">'
        f'<img src="/api/v1/design-sync/assets/2833:{node}.png" alt="Social icon" '
        'width="32" height="32" style="display: block; border: 0;" /></a></td>'
        for node in (2353, 2355, 2357, 2359, 2361)
    )
    + "</tr>"
)


class TestFillsSocialIconOnly:
    def test_texts_without_any_icon_render_nothing(self) -> None:
        """No resolvable icon: the section yields no fill, as before T1."""
        (match,) = _social_matches("8")
        section = match.section
        group = dataclasses.replace(section.column_groups[0], images=[])
        bare = dataclasses.replace(section, images=[], buttons=[], column_groups=[group])
        assert _fills_social(bare, 600) == []

    def test_icon_only_section_output_unchanged(self) -> None:
        """A section with no texts or dividers keeps the pre-T1 icon row byte for byte."""
        fills = _fills_social(_icon_only_c8(), 600)
        assert [(f.slot_id, f.value, f.slot_type) for f in fills] == [
            ("social_links", _PRE_T1_ICON_ROW, "attr")
        ]

    def test_icon_only_render_keeps_template_label(self) -> None:
        """L1: an icon-only section keeps the template's "Follow us" label."""
        (match,) = _social_matches("8")
        section = _icon_only_c8()
        renderer = ComponentRenderer(container_width=600)
        renderer.load()
        rendered = renderer.render_section(
            dataclasses.replace(match, section=section, slot_fills=_fills_social(section, 600))
        )
        assert "Follow us" in rendered.html


class TestSocialColumnOrderEdges:
    """Paths the corpus does not exercise, driven from the real c8 footer section."""

    def test_button_icons_anchor_the_icon_row(self) -> None:
        """F3: icons from Figma buttons sit at their design position, above the legal text."""
        (match,) = _social_matches("8")
        section = match.section
        group = section.column_groups[0]
        buttons = [
            ButtonElement(node_id=img.node_id, text=f"Social {i}", url="https://example.com/s")
            for i, img in enumerate(group.images)
        ]
        image_urls = {b.node_id: f"https://cdn.example.com/{i}.png" for i, b in enumerate(buttons)}
        group = dataclasses.replace(group, images=[], buttons=buttons)
        section = dataclasses.replace(section, images=[], buttons=buttons, column_groups=[group])
        links = next(
            f
            for f in _fills_social(section, 600, image_urls=image_urls)
            if f.slot_id == "social_links"
        )
        assert links.value.rfind(_ICON_IMG) < links.value.find("automatically generated email")

    def test_every_column_group_is_rendered(self) -> None:
        """F4: text in a second column group is not dropped."""
        (match,) = _social_matches("8")
        section = match.section
        group = section.column_groups[0]
        first, second = group.texts
        g1 = dataclasses.replace(group, texts=[first], dividers=[])
        g2 = dataclasses.replace(group, column_idx=2, images=[], texts=[second])
        section = dataclasses.replace(section, column_groups=[g1, g2])
        links = next(f for f in _fills_social(section, 600) if f.slot_id == "social_links")
        assert links.value.find("automatically generated email") < links.value.find("Ferrari N.V.")

    def test_ungrouped_texts_are_logged(self) -> None:
        """F4: a text outside every column group has no position, so it is logged, not placed."""
        (match,) = _social_matches("8")
        section = match.section
        group = section.column_groups[0]
        section = dataclasses.replace(
            section, column_groups=[dataclasses.replace(group, texts=group.texts[:1])]
        )
        with patch.object(component_matcher.logger, "warning") as warn:
            _fills_social(section, 600)
        events = [c.args[0] for c in warn.call_args_list]
        assert "design_sync.social_texts_ungrouped" in events

    def test_texts_without_any_group_are_logged(self) -> None:
        """R2: a section with texts but no column or content group logs them instead of a silent drop."""
        (match,) = _social_matches("8")
        section = dataclasses.replace(match.section, column_groups=[], child_content_groups=[])
        with patch.object(component_matcher.logger, "warning") as warn:
            _fills_social(section, 600)
        events = [c.args[0] for c in warn.call_args_list]
        assert "design_sync.social_texts_ungrouped" in events

    def test_content_group_follows_design_order(self) -> None:
        """F5: inside a content group, a text that precedes its image renders above the icons."""
        (match,) = [m for m in _social_matches("6") if m.section.node_id == "2833:1470"]
        section = match.section
        img_group, text_group = section.child_content_groups
        (img,) = img_group.images
        (text,) = text_group.texts
        merged = dataclasses.replace(
            img_group, texts=[text], content_order=(text.node_id, img.node_id)
        )
        section = dataclasses.replace(section, child_content_groups=[merged, text_group])
        links = next(f for f in _fills_social(section, 600) if f.slot_id == "social_links")
        assert links.value.find("REWARDS") < links.value.find(_ICON_IMG)
