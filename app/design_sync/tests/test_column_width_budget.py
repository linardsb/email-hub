"""F9 (Track F close-out c7 item 1) — column width budget rescale.

``column-layout-{2,3,4}`` seeds hardcode per-column pixel widths sized for a
full 600px context (ghost ``<td width="300">`` + div ``max-width: 300px``).
Horizontal insets the renderer itself applies — a repeating-group band's row
padding (24px/side) and the RC-F7 card wrapper's relocated ``_cell`` padding
(20px/side) — shrink the live content box below the seed total, so the
inline-block column divs wrap and multi-column sections render stacked.

``_shrink_column_ghost_widths`` rescales BOTH width surfaces together (plus the
ghost ``<table width>`` total) to fit the effective box, preserving measured A8
fractions and A8's all-or-nothing invariant (surface-count mismatch ⇒ no-op).
Tests render from the REAL seeds (with MSO ghosts) via the public paths —
``render_section`` for the card inset, ``render_repeating_group`` for the band
inset — mirroring the RC-F7 test discipline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.component_matcher import ComponentMatch, TokenOverride
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import EmailSection, EmailSectionType
from app.design_sync.sibling_detector import RepeatingGroup

_COMPONENT_DIR = Path("email-templates/components")


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


def _section(
    idx: int = 0,
    *,
    padding_right: float | None = 24.0,
    fractions: tuple[float, ...] = (),
) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id=f"col_sec_{idx}",
        node_name=f"Columns {idx}",
        padding_top=20.0,
        padding_right=padding_right,
        item_spacing=16.0,
        column_width_fractions=fractions,
    )


def _match(
    slug: str,
    section: EmailSection,
    *,
    overrides: list[TokenOverride] | None = None,
) -> ComponentMatch:
    return ComponentMatch(
        section_idx=section.node_id.count("_"),
        section=section,
        component_slug=slug,
        slot_fills=[],
        token_overrides=overrides or [],
    )


def _card_overrides() -> list[TokenOverride]:
    """The c7 benefit-card override shape: _inner bg first, then _cell padding
    (matcher order — the wrap must exist before the padding relocates onto it)."""
    return [
        TokenOverride("background-color", "_inner", "#FFFFFF"),
        TokenOverride("padding", "_cell", "20px 20px 20px 20px"),
    ]


class TestBandInsetRescale:
    """render_repeating_group members: the row cell's horizontal padding
    (2 x item_spacing.horizontal) shrinks the members' column budget."""

    def test_two_col_member_fits_padded_band(self, renderer: ComponentRenderer) -> None:
        # 600 - 2x24 = 552 -> 276/276 per member (c8 spec grid / c10 product grid).
        sections = [_section(0), _section(1)]
        group = RepeatingGroup(sections=sections, container_bgcolor="#FFFFFF")
        matches = [_match("column-layout-2", s) for s in sections]
        html = renderer.render_repeating_group(group, matches).html
        assert html.count('<td width="276" valign="top">') == 4
        assert html.count("max-width: 276px") == 4
        assert html.count('width="552"') == 2  # one ghost-table total per member
        assert '<td width="300" valign="top">' not in html
        assert "max-width: 300px" not in html
        # the group's own full-width ghost wrapper is untouched
        assert 'width="600"' in html

    def test_four_col_member_keeps_four_cells_on_one_line(
        self, renderer: ComponentRenderer
    ) -> None:
        # 600 - 48 = 552 -> 138x4 (c7 sec[13] "Andy | 0" user-info row): the four
        # cells sum to the live box, so the 4th no longer wraps.
        sections = [_section(0), _section(1)]
        group = RepeatingGroup(sections=sections, container_bgcolor="#F4F4F4")
        matches = [_match("column-layout-4", s) for s in sections]
        html = renderer.render_repeating_group(group, matches).html
        assert html.count('<td width="138" valign="top">') == 8
        assert html.count("max-width: 138px") == 8
        assert html.count('width="552"') == 2
        assert '<td width="150" valign="top">' not in html

    def test_zero_horizontal_band_leaves_member_untouched(
        self, renderer: ComponentRenderer
    ) -> None:
        # horizontal=0 → no inset → seed widths survive verbatim.
        sections = [_section(0, padding_right=0.0), _section(1, padding_right=0.0)]
        group = RepeatingGroup(sections=sections, container_bgcolor="#FFFFFF")
        matches = [_match("column-layout-2", s) for s in sections]
        html = renderer.render_repeating_group(group, matches).html
        assert html.count('<td width="300" valign="top">') == 4
        assert html.count("max-width: 300px") == 4

    def test_non_column_member_untouched(self, renderer: ComponentRenderer) -> None:
        # Slug gate: a text-block member in a padded band keeps its bytes.
        sections = [_section(0), _section(1)]
        group = RepeatingGroup(sections=sections, container_bgcolor="#FFFFFF")
        matches = [_match("text-block", s) for s in sections]
        before = [renderer.render_section(m).html for m in matches]
        html = renderer.render_repeating_group(group, matches).html
        for member_html in before:
            assert member_html in html


class TestCardInsetRescale:
    """render_section: the RC-F7 card wrapper's relocated _cell padding
    shrinks the column budget inside the card."""

    def test_carded_two_col_fits_card_box(self, renderer: ComponentRenderer) -> None:
        # 600 - 2x20 = 560 -> 280/280 (standalone carded column section).
        match = _match("column-layout-2", _section(0), overrides=_card_overrides())
        html = renderer.render_section(match).html
        assert 'class="product-card _inner"' in html  # F7 wrap fired (pre-condition)
        assert "padding:20px 20px 20px 20px" in html
        assert html.count('<td width="280" valign="top">') == 2
        assert html.count("max-width: 280px") == 2
        assert 'width="560"' in html
        assert '<td width="300" valign="top">' not in html

    def test_carded_member_in_band_composes_both_insets(self, renderer: ComponentRenderer) -> None:
        # 600 - 2x24 (band) - 2x20 (card) = 512 -> 256/256 (c7 benefit cards).
        sections = [_section(0), _section(1)]
        group = RepeatingGroup(sections=sections, container_bgcolor="#AFCA01")
        matches = [_match("column-layout-2", s, overrides=_card_overrides()) for s in sections]
        html = renderer.render_repeating_group(group, matches).html
        assert html.count('<td width="256" valign="top">') == 4
        assert html.count("max-width: 256px") == 4
        assert html.count('width="512"') == 2
        assert '<td width="300" valign="top">' not in html

    def test_uncarded_uninset_section_keeps_seed_widths(self, renderer: ComponentRenderer) -> None:
        # No card, no band → the 600px budget is intact and the seed's ghost
        # surfaces survive verbatim (c8 sec[9] un-inset control).
        match = _match("column-layout-4", _section(0))
        html = renderer.render_section(match).html
        assert html.count('<td width="150" valign="top">') == 4
        assert html.count("max-width: 150px") == 4
        assert 'width="600"' in html


class TestFractionAndInvariantPreservation:
    """A8 contract: measured fractions survive the rescale; the two surfaces
    rewrite together or not at all."""

    def test_a8_fractions_preserved_under_band_inset(self, renderer: ComponentRenderer) -> None:
        # A8 first redistributes 600 → 400/200 (2:1); the band rescale keeps the
        # fractions on the shrunk total: 552 → 368/184.
        sections = [
            _section(0, fractions=(2 / 3, 1 / 3)),
            _section(1, fractions=(2 / 3, 1 / 3)),
        ]
        group = RepeatingGroup(sections=sections, container_bgcolor="#FFFFFF")
        matches = [_match("column-layout-2", s) for s in sections]
        html = renderer.render_repeating_group(group, matches).html
        assert html.count('<td width="368" valign="top">') == 2
        assert html.count('<td width="184" valign="top">') == 2
        assert html.count("max-width: 368px") == 2
        assert html.count("max-width: 184px") == 2
        assert html.count('width="552"') == 2

    def test_surface_count_mismatch_noops(self, renderer: ComponentRenderer) -> None:
        # 2 ghost tds but only 1 column div → the surfaces would diverge → no-op.
        html_in = (
            '<table role="presentation" width="600" align="center"><tr>'
            '<td width="300" valign="top"></td><td width="300" valign="top">'
            '<div class="column" style="display: inline-block; max-width: 300px;">x</div>'
            "</td></tr></table>"
        )
        assert renderer._shrink_column_ghost_widths(html_in, 48) == html_in

    def test_zero_inset_is_identity(self, renderer: ComponentRenderer) -> None:
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        assert renderer._shrink_column_ghost_widths(seed, 0) == seed
        assert renderer._shrink_column_ghost_widths(seed, -8) == seed

    def test_degenerate_inset_noops(self, renderer: ComponentRenderer) -> None:
        # Inset consuming (nearly) the whole budget → no sane per-column width → no-op.
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        assert renderer._shrink_column_ghost_widths(seed, 600) == seed
        assert renderer._shrink_column_ghost_widths(seed, 599) == seed


class TestStyleHorizontalPaddingParse:
    """_style_horizontal_padding_px: CSS shorthand forms + longhand overrides."""

    @pytest.mark.parametrize(
        ("style", "expected"),
        [
            ("padding:20px", 40),  # 1-value: both sides
            ("padding:10px 30px", 60),  # 2-value: tb / lr
            ("padding:16px 24px 0", 48),  # 3-value: top / lr / bottom
            ("padding:1px 2px 3px 4px", 6),  # 4-value: right + left
            ("padding: 0;", 0),
            ("padding:0;padding-left:24px", 24),  # longhand wins its side
            ("padding:10px 20px;padding-right:5px", 25),
            ("padding-left:7px;padding-right:9px", 16),
            ("font-size:0;text-align:center", 0),  # no padding at all
            ("padding:5%", 0),  # non-px contributes nothing
        ],
    )
    def test_horizontal_padding(self, style: str, expected: int) -> None:
        from app.design_sync.component_renderer import _style_horizontal_padding_px

        assert _style_horizontal_padding_px(style) == expected
