"""Tests for 49.7: CTA fidelity — button color/shape extraction and rendering."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.design_sync.component_matcher import (
    ComponentMatch,
    CompositeSlot,
    SlotFill,
    TokenOverride,
    _build_column_fill_html,
    _build_slot_fills,
    _cta_overrides,
    _cta_padding_css,
    _cta_radius_css,
    _fills_text_block,
    match_section,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.frame_rules import CornerRadiusSpec
from app.design_sync.protocol import DesignNode, DesignNodeType
from app.design_sync.tests.regression_runner import run_case_conversion

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _button(
    text: str = "Shop Now",
    *,
    fill_color: str | None = None,
    text_color: str | None = None,
    border_radius: float | None = None,
    stroke_color: str | None = None,
    stroke_weight: float | None = None,
    url: str | None = "https://example.com",
    padding_top: float | None = None,
    padding_right: float | None = None,
    padding_bottom: float | None = None,
    padding_left: float | None = None,
    height: float | None = 48,
    font_size: float | None = None,
) -> ButtonElement:
    return ButtonElement(
        node_id="btn_1",
        text=text,
        width=220,
        height=height,
        fill_color=fill_color,
        url=url,
        border_radius=border_radius,
        text_color=text_color,
        stroke_color=stroke_color,
        stroke_weight=stroke_weight,
        padding_top=padding_top,
        padding_right=padding_right,
        padding_bottom=padding_bottom,
        padding_left=padding_left,
        font_size=font_size,
    )


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CTA,
    *,
    buttons: list[ButtonElement] | None = None,
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    bg_color: str | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id="frame_1",
        node_name="CTA Section",
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        bg_color=bg_color,
    )


def _make_match(
    slug: str,
    *,
    fills: list[SlotFill] | None = None,
    overrides: list[TokenOverride] | None = None,
    section: EmailSection | None = None,
) -> ComponentMatch:
    return ComponentMatch(
        section_idx=0,
        section=section or _make_section(),
        component_slug=slug,
        slot_fills=fills or [],
        token_overrides=overrides or [],
    )


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


# ---------------------------------------------------------------------------
# 1. ButtonElement dataclass fields
# ---------------------------------------------------------------------------


class TestButtonElementFields:
    def test_stroke_fields_default_none(self) -> None:
        btn = ButtonElement(node_id="b1", text="Go")
        assert btn.stroke_color is None
        assert btn.stroke_weight is None
        assert btn.icon_node_id is None

    def test_stroke_fields_populated(self) -> None:
        btn = ButtonElement(
            node_id="b1",
            text="Go",
            stroke_color="#ff0000",
            stroke_weight=2.0,
            icon_node_id="icon_node_1",
        )
        assert btn.stroke_color == "#ff0000"
        assert btn.stroke_weight == 2.0
        assert btn.icon_node_id == "icon_node_1"


# ---------------------------------------------------------------------------
# 2-4. Button extraction from DesignNode
# ---------------------------------------------------------------------------


def _make_button_node(
    *,
    name: str = "CTA Button",
    fill_color: str | None = "#c6fc6a",
    text_color: str | None = "#000000",
    corner_radius: float | None = 6.0,
    stroke_color: str | None = None,
    stroke_weight: float | None = None,
    icon_child: bool = False,
) -> DesignNode:
    """Build a minimal DesignNode tree that _walk_for_buttons will recognise."""
    children: list[DesignNode] = [
        DesignNode(
            id="text_1",
            name="Label",
            type=DesignNodeType.TEXT,
            text_content="Shop Now",
            text_color=text_color,
            width=100,
            height=20,
        ),
    ]
    if icon_child:
        children.append(
            DesignNode(
                id="icon_1",
                name="arrow-icon",
                type=DesignNodeType.VECTOR,
                width=24,
                height=24,
            )
        )
    return DesignNode(
        id="btn_frame",
        name=name,
        type=DesignNodeType.FRAME,
        width=220,
        height=48,
        fill_color=fill_color,
        corner_radius=corner_radius,
        stroke_color=stroke_color,
        stroke_weight=stroke_weight,
        children=children,
    )


class TestButtonExtraction:
    def test_extract_fill_color(self) -> None:
        from app.design_sync.figma.layout_analyzer import _walk_for_buttons

        node = _make_button_node(fill_color="#c6fc6a")
        results: list[ButtonElement] = []
        _walk_for_buttons(node, results)
        assert len(results) == 1
        assert results[0].fill_color == "#c6fc6a"

    def test_extract_stroke_properties(self) -> None:
        from app.design_sync.figma.layout_analyzer import _walk_for_buttons

        node = _make_button_node(stroke_color="#333333", stroke_weight=2.0)
        results: list[ButtonElement] = []
        _walk_for_buttons(node, results)
        assert len(results) == 1
        assert results[0].stroke_color == "#333333"
        assert results[0].stroke_weight == 2.0

    def test_extract_icon_child(self) -> None:
        from app.design_sync.figma.layout_analyzer import _walk_for_buttons

        node = _make_button_node(icon_child=True)
        results: list[ButtonElement] = []
        _walk_for_buttons(node, results)
        assert len(results) == 1
        assert results[0].icon_node_id == "icon_1"

    def test_no_icon_when_absent(self) -> None:
        from app.design_sync.figma.layout_analyzer import _walk_for_buttons

        node = _make_button_node(icon_child=False)
        results: list[ButtonElement] = []
        _walk_for_buttons(node, results)
        assert len(results) == 1
        assert results[0].icon_node_id is None


# ---------------------------------------------------------------------------
# 5-9. CTA token overrides via match_section
# ---------------------------------------------------------------------------


class TestCTATokenOverrides:
    def test_cta_bg_color_override(self) -> None:
        s = _make_section(buttons=[_button(fill_color="#c6fc6a")])
        m = match_section(s, 0)
        bg = [
            o
            for o in m.token_overrides
            if o.target_class == "_cta" and o.css_property == "background-color"
        ]
        assert len(bg) == 1
        assert bg[0].value == "#c6fc6a"

    def test_cta_text_color_override(self) -> None:
        s = _make_section(buttons=[_button(text_color="#000000")])
        m = match_section(s, 0)
        color = [
            o for o in m.token_overrides if o.target_class == "_cta" and o.css_property == "color"
        ]
        assert len(color) == 1
        assert color[0].value == "#000000"

    def test_cta_border_radius_override(self) -> None:
        s = _make_section(buttons=[_button(border_radius=6.0)])
        m = match_section(s, 0)
        radius = [
            o
            for o in m.token_overrides
            if o.target_class == "_cta" and o.css_property == "border-radius"
        ]
        assert len(radius) == 1
        assert radius[0].value == "6px"

    def test_cta_stroke_override(self) -> None:
        s = _make_section(buttons=[_button(stroke_color="#ff0000", stroke_weight=2.0)])
        m = match_section(s, 0)
        border_color = [
            o
            for o in m.token_overrides
            if o.target_class == "_cta" and o.css_property == "border-color"
        ]
        border_width = [
            o
            for o in m.token_overrides
            if o.target_class == "_cta" and o.css_property == "border-width"
        ]
        assert len(border_color) == 1
        assert border_color[0].value == "#ff0000"
        assert len(border_width) == 1
        assert border_width[0].value == "2px"

    def test_no_cta_override_when_missing(self) -> None:
        s = _make_section(buttons=[_button()])
        m = match_section(s, 0)
        cta = [o for o in m.token_overrides if o.target_class == "_cta"]
        assert len(cta) == 0


# ---------------------------------------------------------------------------
# 10-12. Renderer CTA token override application
# ---------------------------------------------------------------------------


class TestRendererCTAOverrides:
    def test_cta_bg_color_applied(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "cta-button",
            # F4a: overrides accompany real content in production; supply the
            # label so the button isn't pruned as an empty CTA.
            fills=[SlotFill("cta_text", "Shop")],
            overrides=[TokenOverride("background-color", "_cta", "#c6fc6a")],
        )
        result = renderer.render_section(match)
        assert (
            "background-color:#c6fc6a" in result.html or "background-color: #c6fc6a" in result.html
        )
        # VML fillcolor
        assert 'fillcolor="#c6fc6a"' in result.html

    def test_cta_border_radius_applied(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "cta-button",
            fills=[SlotFill("cta_text", "Shop")],  # F4a: keep the button present
            overrides=[TokenOverride("border-radius", "_cta", "6px")],
        )
        result = renderer.render_section(match)
        assert "border-radius:6px" in result.html
        # VML arcsize updated
        assert "arcsize=" in result.html

    def test_cta_text_color_applied(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "cta-button",
            fills=[SlotFill("cta_text", "Shop")],  # F4a: keep the button present
            overrides=[TokenOverride("color", "_cta", "#000000")],
        )
        result = renderer.render_section(match)
        assert "color:#000000" in result.html


# ---------------------------------------------------------------------------
# 51.1 own-row CTA — _fills_text_block emits a composite CTA row
# ---------------------------------------------------------------------------


class TestOwnRowCTAComposite:
    """The text-block CTA renders centered on its own row (spliced after the body)
    instead of folded into the body <td> where it hugged the left padding."""

    def _text_section(self, buttons: list[ButtonElement]) -> EmailSection:
        return _make_section(
            EmailSectionType.CONTENT,
            texts=[
                TextBlock(node_id="h1", content="Heading", is_heading=True),
                TextBlock(node_id="b1", content="Body copy.", is_heading=False),
            ],
            buttons=buttons,
        )

    def test_builder_emits_composite_cta_row(self) -> None:
        fills = _fills_text_block(self._text_section([_button("Explore now")]), 600)
        cta = next(f for f in fills if f.slot_id == "cta_row")
        assert cta.slot_type == "composite"
        assert isinstance(cta.composite, CompositeSlot)
        assert cta.composite.after_slot == "body"
        assert any("<a " in c.value and "Explore now" in c.value for c in cta.composite.children)

    def test_body_fill_no_longer_carries_anchor(self) -> None:
        fills = _fills_text_block(self._text_section([_button("Explore now")]), 600)
        body = next(f for f in fills if f.slot_id == "body")
        assert "<a " not in body.value  # no longer folded into body

    def test_render_places_cta_in_centered_row_after_body(
        self, renderer: ComponentRenderer
    ) -> None:
        section = self._text_section([_button("Explore now", fill_color="#4e3092")])
        fills = _fills_text_block(section, 600)
        match = _make_match("text-block", fills=fills, section=section)
        html = renderer.render_section(match).html
        body_cell = html.split('data-slot="body"')[1].split("</td>")[0]
        assert "<a " not in body_cell  # anchor moved out of the body cell
        assert re.search(r'<td align="center"[^>]*>\s*<a [^>]*>Explore now</a>', html)
        assert html.index("Explore now") > html.index('data-slot="body"')

    def test_multi_button_both_in_one_centered_row(self, renderer: ComponentRenderer) -> None:
        section = self._text_section([_button("SHOP"), _button("DISCOVER")])
        fills = _fills_text_block(section, 600)
        cta = next(f for f in fills if f.slot_id == "cta_row")
        assert cta.composite is not None
        assert len(cta.composite.children) == 2
        match = _make_match("text-block", fills=fills, section=section)
        html = renderer.render_section(match).html
        row_match = re.search(r'<td align="center"[^>]*>(.*?)</td>', html, re.DOTALL)
        assert row_match is not None
        assert "SHOP" in row_match.group(1) and "DISCOVER" in row_match.group(1)


# ---------------------------------------------------------------------------
# 13-14. Column fill uses button properties
# ---------------------------------------------------------------------------


class TestColumnFillButtonProperties:
    def test_column_fill_uses_button_text_color(self) -> None:
        btn = _button(fill_color="#c6fc6a", text_color="#112233")
        group = ColumnGroup(
            column_idx=0,
            node_id="col_1",
            node_name="Column",
            texts=[],
            images=[],
            buttons=[btn],
        )
        html = _build_column_fill_html(group)
        assert "color:#112233" in html

    def test_column_fill_uses_button_radius(self) -> None:
        btn = _button(fill_color="#c6fc6a", border_radius=12.0)
        group = ColumnGroup(
            column_idx=0,
            node_id="col_1",
            node_name="Column",
            texts=[],
            images=[],
            buttons=[btn],
        )
        html = _build_column_fill_html(group)
        assert "border-radius:12px" in html

    def test_column_fill_uses_stroke(self) -> None:
        btn = _button(
            fill_color="#c6fc6a",
            stroke_color="#333333",
            stroke_weight=2.0,
        )
        group = ColumnGroup(
            column_idx=0,
            node_id="col_1",
            node_name="Column",
            texts=[],
            images=[],
            buttons=[btn],
        )
        html = _build_column_fill_html(group)
        assert "border:2px solid #333333" in html


class TestTextBlockCTARadius:
    """The text-block inline CTA honours ButtonElement.border_radius.

    Guards phase-53f-f7-text-block-cta-hardcoded-radius: `_fills_text_block`
    hardcoded `border-radius:4px`, flattening every designed pill radius on the
    text-block path (c5 'Discover →', c6 'Order your fall favorite', c7/LEGO
    'Explore now' at r25).
    """

    def _body_html(self, btn: ButtonElement) -> str:
        from app.design_sync.component_matcher import _fills_text_block

        section = _make_section(EmailSectionType.CONTENT, buttons=[btn])
        fills = _fills_text_block(section, 600)
        body = next(f for f in fills if f.slot_id == "body")
        return body.value

    def test_designed_radius_renders(self) -> None:
        html = self._body_html(
            _button(
                "Explore now",
                fill_color="#FFFFFF",
                text_color="#000000",
                stroke_color="#000000",
                stroke_weight=2.0,
                border_radius=25.0,
            )
        )
        assert "border-radius:25px" in html
        assert "border:2px solid #000000" in html
        assert "color:#000000" in html

    def test_missing_radius_keeps_4px_fallback(self) -> None:
        html = self._body_html(_button("Shop Now", fill_color="#0066cc"))
        assert "border-radius:4px" in html


class TestTextBlockCTALabelColor:
    """The stroke-less text-block CTA honours ButtonElement.text_color (F11).

    Guards phase-53-b8-text-block-solid-cta-text-color: the stroke-less branch
    hardcoded `color:#ffffff`, ignoring the design's label colour (c5
    'Discover →' extracts text_color #000000). White is the absence-fallback
    only — `_safe_color(btn.text_color, "#ffffff")`, mirroring _column_cta_row.
    """

    def _body_html(self, btn: ButtonElement) -> str:
        from app.design_sync.component_matcher import _fills_text_block

        section = _make_section(EmailSectionType.CONTENT, buttons=[btn])
        fills = _fills_text_block(section, 600)
        body = next(f for f in fills if f.slot_id == "body")
        return body.value

    def test_dark_label_on_light_fill(self) -> None:
        html = self._body_html(_button("Discover →", fill_color="#FFFFFF", text_color="#010101"))
        assert "color:#010101" in html
        # The invisible white-on-white signature must be gone…
        assert "color:#ffffff" not in html
        # …and no border invented for a stroke-less button.
        assert "border:" not in html

    def test_white_fallback_when_text_color_absent(self) -> None:
        html = self._body_html(_button("Shop Now", fill_color="#0066cc"))
        assert "color:#ffffff" in html


# ---------------------------------------------------------------------------
# 15. Multiple CTAs with different colors
# ---------------------------------------------------------------------------


class TestMultipleCTAs:
    def test_different_cta_colors_per_section(self, renderer: ComponentRenderer) -> None:
        colors = ["#c6fc6a", "#ffbaf3", "#06d5ff"]
        for color in colors:
            match = _make_match(
                "cta-button",
                fills=[SlotFill("cta_text", "Shop")],  # F4a: keep the button present
                overrides=[TokenOverride("background-color", "_cta", color)],
            )
            result = renderer.render_section(match)
            assert f'fillcolor="{color}"' in result.html
            assert f"background-color:{color}" in result.html


# ---------------------------------------------------------------------------
# 16. Dual-CTA sections route to cta-pair (B8)
# ---------------------------------------------------------------------------


class TestDualCTAPair:
    def _dual(self) -> EmailSection:
        return _make_section(
            buttons=[
                _button("Shop Now", url="https://example.com/shop"),
                _button("Learn More", url="https://example.com/learn"),
            ],
        )

    def test_two_buttons_route_to_cta_pair(self) -> None:
        m = match_section(self._dual(), 0)
        assert m.component_slug == "cta-pair"

    def test_single_button_keeps_cta_button(self) -> None:
        m = match_section(_make_section(buttons=[_button("Shop Now")]), 0)
        assert m.component_slug == "cta-button"
        assert "cta_text" in {f.slot_id for f in m.slot_fills}

    def test_cta_pair_emits_primary_and_secondary_fills(self) -> None:
        m = match_section(self._dual(), 0)
        by_id = {f.slot_id: f for f in m.slot_fills}
        assert by_id["primary_text"].value == "Shop Now"
        assert by_id["primary_url"].value == "https://example.com/shop"
        assert by_id["secondary_text"].value == "Learn More"
        assert by_id["secondary_url"].value == "https://example.com/learn"
        # The legacy single-CTA slots must not coexist with the pair slots.
        assert "cta_text" not in by_id
        assert "cta_url" not in by_id

    def test_third_button_dropped(self) -> None:
        s = _make_section(
            buttons=[
                _button("One", url="https://example.com/1"),
                _button("Two", url="https://example.com/2"),
                _button("Three", url="https://example.com/3"),
            ],
        )
        m = match_section(s, 0)
        by_id = {f.slot_id: f for f in m.slot_fills}
        assert by_id["primary_text"].value == "One"
        assert by_id["secondary_text"].value == "Two"
        assert all(f.value != "Three" for f in m.slot_fills)

    def test_cta_pair_renders_both_labels_and_hrefs(self, renderer: ComponentRenderer) -> None:
        result = renderer.render_section(match_section(self._dual(), 0))
        html = result.html
        assert "Shop Now" in html
        assert "Learn More" in html
        assert "https://example.com/shop" in html
        assert "https://example.com/learn" in html
        # Reverse phantom-slug tripwire: cta-pair has never been emitted, so
        # confirm no seed placeholder survives into the rendered output.
        assert "Primary button" not in html
        assert "Secondary button" not in html
        assert "example.com/link" not in html


# ---------------------------------------------------------------------------
# 17. Dual-CTA per-button color fidelity (phase-53-b8-cta-pair-color-fidelity)
# ---------------------------------------------------------------------------


class TestDualCTAColorFidelity:
    """Each cta-pair button must render in its OWN Figma color, not the seed
    default (#e84e0f).

    Before this fix the renderer's ``_cta`` helpers matched only
    ``class="cta-btn"``/``data-slot="cta_url"``, so the cta-pair seed
    (``class="cta"`` + ``primary_url``/``secondary_url``) ignored every color
    override and both buttons rendered the seed orange. The test exercises the
    full ``match_section`` → ``render_section`` path and asserts per-button
    *isolation* — a color must land in its own button block and be ABSENT from
    the other's — which catches both a no-op (seed default survives) and a
    global leak (one override paints both buttons).
    """

    _PRIMARY = "#ff0000"  # filled primary button fill
    _SECONDARY = "#0000ff"  # outlined secondary button fill (paints its border)
    _SEED_DEFAULT = "#e84e0f"

    def _section(self) -> EmailSection:
        return _make_section(
            buttons=[
                _button("Shop Now", url="https://example.com/shop", fill_color=self._PRIMARY),
                _button("Learn More", url="https://example.com/learn", fill_color=self._SECONDARY),
            ],
        )

    @staticmethod
    def _block(html: str, class_name: str) -> str:
        """Isolate one button's (non-nested) ``<table class="…cta-x…">…</table>``."""
        m = re.search(
            rf'<table\b[^>]*\bclass="[^"]*\b{class_name}\b[^"]*"[^>]*>.*?</table>',
            html,
            re.DOTALL,
        )
        assert m is not None, f"cta-pair output has no {class_name} button block"
        return m.group(0)

    def test_matcher_emits_per_button_color_overrides(self) -> None:
        m = match_section(self._section(), 0)
        by_key = {(o.target_class, o.css_property): o.value for o in m.token_overrides}
        assert by_key.get(("_cta_primary", "background-color")) == self._PRIMARY
        assert by_key.get(("_cta_secondary", "background-color")) == self._SECONDARY

    def test_each_button_renders_its_own_color(self, renderer: ComponentRenderer) -> None:
        html = renderer.render_section(match_section(self._section(), 0)).html
        primary = self._block(html, "cta-primary")
        secondary = self._block(html, "cta-secondary")

        # The filled primary carries its fill on the bgcolor surface...
        assert f'bgcolor="{self._PRIMARY}"' in primary
        assert self._PRIMARY in primary
        # ...the outlined secondary carries its fill on its border...
        assert self._SECONDARY in secondary
        # ...and neither button bleeds into the other (global-leak tripwire)...
        assert self._SECONDARY not in primary
        assert self._PRIMARY not in secondary
        # ...and the primary no longer falls back to the seed default.
        assert self._SEED_DEFAULT not in primary


# ---------------------------------------------------------------------------
# 17. Slug-aware _fills_cta — slot set follows the chosen slug, not button
# count (phase-53-b8-fills-cta-slug-desync-vlm). The VLM fallback path sets
# the slug independently of button count, so a count-keyed filler can emit
# slots the seed doesn't have.
# ---------------------------------------------------------------------------


class TestFillsCtaSlugAware:
    def _two_buttons(self) -> EmailSection:
        return _make_section(
            buttons=[
                _button("Shop Now", url="https://example.com/shop"),
                _button("Learn More", url="https://example.com/learn"),
            ],
        )

    def test_cta_button_slug_with_two_buttons_emits_single_slots(self) -> None:
        """A VLM 'cta-button' pick for a 2-button section must fill the seed's
        actual slots (cta_text/cta_url) from the primary button — not emit
        pair slots that no-op against the cta-button seed."""
        fills = _build_slot_fills("cta-button", self._two_buttons(), 600)
        by_id = {f.slot_id: f for f in fills}
        assert by_id["cta_text"].value == "Shop Now"
        assert by_id["cta_url"].value == "https://example.com/shop"
        assert "primary_text" not in by_id
        assert "secondary_text" not in by_id

    def test_cta_pair_slug_with_two_buttons_emits_pair_slots(self) -> None:
        fills = _build_slot_fills("cta-pair", self._two_buttons(), 600)
        by_id = {f.slot_id: f for f in fills}
        assert by_id["primary_text"].value == "Shop Now"
        assert by_id["secondary_text"].value == "Learn More"
        assert "cta_text" not in by_id

    def test_cta_pair_slug_with_one_button_blanks_secondary(self) -> None:
        fills = _build_slot_fills(
            "cta-pair",
            _make_section(buttons=[_button("Shop Now", url="https://example.com/shop")]),
            600,
        )
        by_id = {f.slot_id: f for f in fills}
        assert by_id["primary_text"].value == "Shop Now"
        assert by_id["secondary_text"].value == ""
        assert by_id["secondary_url"].value == ""

    def test_cta_pair_slug_with_one_button_no_placeholder_leak(
        self, renderer: ComponentRenderer
    ) -> None:
        """Renderer-level guard: a cta-pair seed filled from a 1-button section
        must not leak the seed's 'Secondary button' / placeholder-URL text."""
        section = _make_section(buttons=[_button("Shop Now", url="https://example.com/shop")])
        fills = _build_slot_fills("cta-pair", section, 600)
        result = renderer.render_section(_make_match("cta-pair", fills=fills, section=section))
        html = result.html
        assert "Shop Now" in html
        assert "https://example.com/shop" in html
        assert "Primary button" not in html
        assert "Secondary button" not in html
        assert "example.com/link" not in html

    def test_text_link_slug_emits_link_slots(self) -> None:
        """text-link's seed uses link_text/link_url — cta_text/cta_url fills
        would no-op against it (same desync class)."""
        fills = _build_slot_fills(
            "text-link",
            _make_section(buttons=[_button("Read more", url="https://example.com/read")]),
            600,
        )
        by_id = {f.slot_id: f for f in fills}
        assert by_id["link_text"].value == "Read more"
        assert by_id["link_url"].value == "https://example.com/read"
        assert "cta_text" not in by_id


class TestFillsCtaEmptyDiscipline:
    """F4a (RC-F4): CTA builders emit explicit EMPTY fills when a section has no
    button, so the renderer blanks/prunes the seed default instead of leaking
    'Shop Now'/'Learn More'. Mirrors the existing cta-pair empty-fill path."""

    def test_cta_button_no_buttons_emits_empty_fills(self) -> None:
        fills = _build_slot_fills("cta-button", _make_section(buttons=[]), 600)
        by_id = {f.slot_id: f for f in fills}
        assert by_id["cta_text"].value == ""
        assert by_id["cta_url"].value == ""

    def test_text_link_no_buttons_emits_empty_link_fills(self) -> None:
        fills = _build_slot_fills("text-link", _make_section(buttons=[]), 600)
        by_id = {f.slot_id: f for f in fills}
        assert by_id["link_text"].value == ""
        assert by_id["link_url"].value == ""

    def test_hero_no_buttons_emits_empty_cta_fills(self) -> None:
        fills = _build_slot_fills(
            "hero-block",
            _make_section(EmailSectionType.CONTENT, buttons=[]),
            600,
        )
        by_id = {f.slot_id: f for f in fills}
        assert by_id["cta_text"].value == ""
        assert by_id["cta_url"].value == ""


class TestCtaPaddingCss:
    """Track G · G3 — ``_cta_padding_css`` maps captured auto-layout padding to
    the CSS shorthand, with a height-derived speculative fallback and the pre-G3
    ``10px 24px`` final hardcode.
    """

    def test_symmetric_two_value(self) -> None:
        btn = _button(padding_top=5.0, padding_right=10.0, padding_bottom=5.0, padding_left=10.0)
        assert _cta_padding_css(btn) == "5px 10px"

    def test_all_equal_collapses_to_one_value(self) -> None:
        btn = _button(padding_top=12.0, padding_right=12.0, padding_bottom=12.0, padding_left=12.0)
        assert _cta_padding_css(btn) == "12px"

    def test_asymmetric_four_value(self) -> None:
        btn = _button(padding_top=1.0, padding_right=2.0, padding_bottom=3.0, padding_left=4.0)
        assert _cta_padding_css(btn) == "1px 2px 3px 4px"

    def test_designed_zero_padding_preserved(self) -> None:
        btn = _button(padding_top=0.0, padding_right=0.0, padding_bottom=0.0, padding_left=0.0)
        assert _cta_padding_css(btn) == "0px"

    def test_height_fallback_when_padding_absent(self) -> None:
        # No padding → derive vertical from height: round((44 - 16*1.2)/2) = 12.
        btn = _button(height=44.0, font_size=16.0)
        assert _cta_padding_css(btn) == "12px 24px"

    def test_final_hardcode_when_no_padding_no_font(self) -> None:
        btn = _button(height=48.0, font_size=None)
        assert _cta_padding_css(btn) == "10px 24px"


class TestButtonBoxGeometry:
    """Track G · G3 — both CTA render sites emit the button's captured padding
    (via _cta_padding_css) and a square-in-design radius (0.0 → 0px).
    """

    def _column_html(self, btn: ButtonElement) -> str:
        group = ColumnGroup(
            column_idx=0,
            node_id="col_1",
            node_name="Column",
            texts=[],
            images=[],
            buttons=[btn],
        )
        return _build_column_fill_html(group)

    def _text_block_html(self, btn: ButtonElement) -> str:
        from app.design_sync.component_matcher import _fills_text_block

        section = _make_section(EmailSectionType.CONTENT, buttons=[btn])
        fills = _fills_text_block(section, 600)
        return next(f for f in fills if f.slot_id == "body").value

    def test_column_site_emits_padding_and_square_radius(self) -> None:
        btn = _button(
            "Art prints",
            fill_color="#000000",
            text_color="#ffffff",
            border_radius=0.0,
            padding_top=5.0,
            padding_right=10.0,
            padding_bottom=5.0,
            padding_left=10.0,
        )
        html = self._column_html(btn)
        assert "padding:5px 10px" in html
        assert "border-radius:0px" in html

    def test_text_block_site_emits_padding_and_square_radius(self) -> None:
        btn = _button(
            "Stationery",
            fill_color="#000000",
            text_color="#ffffff",
            border_radius=0.0,
            padding_top=5.0,
            padding_right=10.0,
            padding_bottom=5.0,
            padding_left=10.0,
        )
        html = self._text_block_html(btn)
        assert "padding:5px 10px" in html
        assert "border-radius:0px" in html

    def test_main_button_padding_and_rounded_radius(self) -> None:
        btn = _button(
            "Shop now",
            fill_color="#4e3092",
            text_color="#ffffff",
            border_radius=25.0,
            padding_top=12.0,
            padding_right=20.0,
            padding_bottom=12.0,
            padding_left=20.0,
        )
        html = self._column_html(btn)
        assert "padding:12px 20px" in html
        assert "border-radius:25px" in html

    def test_speculative_height_fallback_renders(self) -> None:
        # No captured padding → helper derives vertical from height (h44/f16 → 12).
        btn = _button("Shop Now", fill_color="#0066cc", height=44.0, font_size=16.0)
        html = self._column_html(btn)
        assert "padding:12px 24px" in html


# Per-corner longhand string (TL,TR,BR,BL) for an asymmetric r12/r18 pill —
# shared by the helper and render-site tests below.
_PER_CORNER_SPEC = CornerRadiusSpec(scalar=None, per_corner=(12.0, 12.0, 18.0, 18.0))
_PER_CORNER_LONGHANDS = (
    "border-top-left-radius:12px;"
    "border-top-right-radius:12px;"
    "border-bottom-right-radius:18px;"
    "border-bottom-left-radius:18px"
)


class TestCtaRadiusCss:
    """Track G · G5 — ``_cta_radius_css`` emits the four per-corner longhands when
    the button carries ``corner_radius_spec.per_corner`` (Rule 8 asymmetric pill),
    else the scalar ``border-radius`` shorthand. The scalar branch is byte-identical
    to the pre-G5 inline emission (``{r:.0f}px``, legacy ``4`` fallback when absent) —
    every corpus button has ``corner_radii: null``, so the per-corner branch is
    synthetic-only defensive plumbing.
    """

    def test_per_corner_emits_four_longhands_in_order(self) -> None:
        btn = replace(_button(), corner_radius_spec=_PER_CORNER_SPEC)
        assert _cta_radius_css(btn) == _PER_CORNER_LONGHANDS

    def test_scalar_radius_shorthand(self) -> None:
        assert _cta_radius_css(_button(border_radius=25.0)) == "border-radius:25px"

    def test_designed_zero_radius_is_square(self) -> None:
        assert _cta_radius_css(_button(border_radius=0.0)) == "border-radius:0px"

    def test_absent_radius_keeps_legacy_4px_fallback(self) -> None:
        assert _cta_radius_css(_button(border_radius=None)) == "border-radius:4px"

    def test_scalar_spec_without_per_corner_uses_scalar(self) -> None:
        # A spec carrying only ``scalar`` (no ``per_corner``) must NOT trigger the
        # longhand branch — the render still reads ``btn.border_radius``.
        btn = replace(
            _button(border_radius=25.0),
            corner_radius_spec=CornerRadiusSpec(scalar=25.0, per_corner=None),
        )
        assert _cta_radius_css(btn) == "border-radius:25px"


class TestCtaRadiusRenderSites:
    """Track G · G5 — per-corner longhands reach all three button radius sites:
    the two inline ``<a>`` sites (column + text-block) and the ``_cta_overrides``
    TokenOverride form.
    """

    def test_column_site_emits_longhands(self) -> None:
        btn = replace(
            _button("Art prints", fill_color="#4e3092", text_color="#ffffff"),
            corner_radius_spec=_PER_CORNER_SPEC,
        )
        group = ColumnGroup(
            column_idx=0,
            node_id="col_1",
            node_name="Column",
            texts=[],
            images=[],
            buttons=[btn],
        )
        html = _build_column_fill_html(group)
        assert _PER_CORNER_LONGHANDS in html
        # The scalar shorthand must be suppressed (``border-radius:`` is not a
        # substring of the ``border-*-radius:`` longhands).
        assert "border-radius:" not in html

    def test_text_block_site_emits_longhands(self) -> None:
        btn = replace(
            _button("Stationery", fill_color="#4e3092", text_color="#ffffff"),
            corner_radius_spec=_PER_CORNER_SPEC,
        )
        section = _make_section(EmailSectionType.CONTENT, buttons=[btn])
        fills = _fills_text_block(section, 600)
        body = next(f for f in fills if f.slot_id == "body").value
        assert _PER_CORNER_LONGHANDS in body
        assert "border-radius:" not in body

    def test_cta_overrides_emits_four_longhand_overrides(self) -> None:
        btn = replace(_button(border_radius=None), corner_radius_spec=_PER_CORNER_SPEC)
        radius = {
            o.css_property: o.value
            for o in _cta_overrides(btn, "_cta")
            if o.css_property.endswith("-radius")
        }
        assert radius == {
            "border-top-left-radius": "12px",
            "border-top-right-radius": "12px",
            "border-bottom-right-radius": "18px",
            "border-bottom-left-radius": "18px",
        }

    def test_cta_overrides_scalar_radius_unchanged(self) -> None:
        # No per_corner → a single scalar border-radius override (byte-identical
        # to the pre-G5 corpus emission).
        radius = [
            o
            for o in _cta_overrides(_button(border_radius=0.0), "_cta")
            if "radius" in o.css_property
        ]
        assert len(radius) == 1
        assert radius[0].css_property == "border-radius"
        assert radius[0].value == "0px"


# Byte-identical reference for the corpus tag-pills, recorded from the committed
# ``data/debug/{7,5}/expected.html`` at the G5 branch point (post-G3/G4/F10).
_C7_ART_PRINTS = (
    '<a href="#" style="display:inline-block;padding:5px 10px;'
    "background-color:#4E3092;color:#FFFFFF;text-decoration:none;"
    "font-family:Noto Sans,sans-serif;font-size:10px;font-weight:700;"
    'border-radius:0px;">Art prints</a>'
)
_C7_STATIONERY = _C7_ART_PRINTS.replace(">Art prints<", ">Stationery<")
_C5_MELBOURNE = (
    '<a href="#" style="display:inline-block;padding:12px;'
    "background-color:#222222;color:#FFFFFF;text-decoration:none;"
    "font-family:Helvetica,sans-serif;font-size:14px;font-weight:400;"
    'border-radius:25px;">Melbourne</a>'
)

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"


class TestPillGuardByteIdentical:
    """Track G · G5 — the corpus tag-pills stay byte-identical after G5.

    Renders case 7 (c7 'Art prints'/'Stationery' square #4E3092 pills, r0) and
    case 5 ('Melbourne' r25 #222222 city pills) through the real converter and
    pins each pill's ``<a>`` style string. CI-runnable without the gitignored
    pixel assets — ``run_case_conversion`` reads only ``structure.json`` +
    ``tokens.json``. Load-bearing net for the "G5 is corpus byte-identical" claim.
    """

    def _render(self, case_id: str) -> str:
        result = run_case_conversion(_DEBUG_DIR / case_id)
        if result is None:
            pytest.skip(f"case {case_id}: missing structure.json/tokens.json")
        return result.html

    def test_c7_square_pills_byte_identical(self) -> None:
        html = self._render("7")
        assert _C7_ART_PRINTS in html
        assert _C7_STATIONERY in html

    def test_c5_rounded_city_pill_byte_identical(self) -> None:
        assert _C5_MELBOURNE in self._render("5")
