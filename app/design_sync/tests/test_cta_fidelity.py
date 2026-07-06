"""Tests for 49.7: CTA fidelity — button color/shape extraction and rendering."""

from __future__ import annotations

import re

import pytest

from app.design_sync.component_matcher import (
    ComponentMatch,
    SlotFill,
    TokenOverride,
    _build_column_fill_html,
    _build_slot_fills,
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
from app.design_sync.protocol import DesignNode, DesignNodeType

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
) -> ButtonElement:
    return ButtonElement(
        node_id="btn_1",
        text=text,
        width=220,
        height=48,
        fill_color=fill_color,
        url=url,
        border_radius=border_radius,
        text_color=text_color,
        stroke_color=stroke_color,
        stroke_weight=stroke_weight,
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
