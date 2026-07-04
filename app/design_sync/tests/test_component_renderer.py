"""Tests for component renderer — fills component templates with Figma content."""

from __future__ import annotations

import re

import pytest

from app.design_sync.component_matcher import (
    ComponentMatch,
    SlotFill,
    TokenOverride,
    match_section,
)
from app.design_sync.component_renderer import (
    ComponentRenderer,
    RenderedSection,
    _find_matching_close,
    _is_blankable_text,
)
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
)


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_name: str = "TestSection",
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id="frame_1",
        node_name=node_name,
    )


def _make_match(
    slug: str,
    *,
    idx: int = 0,
    fills: list[SlotFill] | None = None,
    overrides: list[TokenOverride] | None = None,
    section: EmailSection | None = None,
) -> ComponentMatch:
    return ComponentMatch(
        section_idx=idx,
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


class TestRendererLoad:
    def test_loads_templates(self, renderer: ComponentRenderer) -> None:
        assert renderer._loaded is True
        assert len(renderer._templates) > 0

    def test_has_key_slugs(self, renderer: ComponentRenderer) -> None:
        for slug in [
            "hero-block",
            "text-block",
            "cta-button",
            "email-footer",
            "column-layout-2",
            "spacer",
            "divider",
            "logo-header",
        ]:
            assert slug in renderer._templates, f"Missing template: {slug}"


class TestSlotFilling:
    def test_fill_text_slot(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "hero-block",
            fills=[SlotFill("headline", "Summer Sale!")],
        )
        result = renderer.render_section(match)
        assert "Summer Sale!" in result.html
        # Original placeholder replaced
        assert "Discover What" not in result.html

    def test_fill_cta_text_slot(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "cta-button",
            fills=[SlotFill("cta_text", "Buy Now")],
        )
        result = renderer.render_section(match)
        assert "Buy Now" in result.html

    def test_fill_image_slot(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "full-width-image",
            fills=[
                SlotFill(
                    "image_url",
                    "/api/v1/design-sync/assets/123.png",
                    slot_type="image",
                    attr_overrides={"width": "580"},
                ),
            ],
        )
        result = renderer.render_section(match)
        assert "/api/v1/design-sync/assets/123.png" in result.html

    def test_fill_cta_url_slot(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "cta-button",
            # F4a: a real CTA carries its label; without cta_text the now-empty
            # anchor would be pruned before the href assertion.
            fills=[
                SlotFill("cta_text", "Shop"),
                SlotFill("cta_url", "https://shop.example.com", slot_type="cta"),
            ],
        )
        result = renderer.render_section(match)
        assert 'href="https://shop.example.com"' in result.html

    def test_fill_spacer_height(self, renderer: ComponentRenderer) -> None:
        match = _make_match("spacer", fills=[SlotFill("spacer_height", "48")])
        result = renderer.render_section(match)
        assert "height:48px" in result.html
        assert 'height="48"' in result.html

    def test_fill_hero_background_image(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "hero-block",
            fills=[SlotFill("hero_image", "/img/hero.jpg", slot_type="image")],
        )
        result = renderer.render_section(match)
        assert "url('/img/hero.jpg')" in result.html
        # Also in VML src
        assert 'src="/img/hero.jpg"' in result.html

    def test_fill_column_layout(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "column-layout-2",
            fills=[
                SlotFill("col_1", "Left content"),
                SlotFill("col_2", "Right content"),
            ],
        )
        result = renderer.render_section(match)
        assert "Left content" in result.html
        assert "Right content" in result.html

    def test_fill_article_card(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "article-card",
            fills=[
                SlotFill("heading", "Article Title"),
                SlotFill("body_text", "Article body."),
                SlotFill("image_url", "/img/article.jpg", slot_type="image"),
            ],
        )
        result = renderer.render_section(match)
        assert "Article Title" in result.html
        assert "Article body." in result.html

    def test_fill_body_slot_with_br_separators(self, renderer: ComponentRenderer) -> None:
        """Multi-paragraph body fills use <br><br> separators instead of <p> tags."""
        match = _make_match(
            "text-block",
            fills=[
                SlotFill("heading", "Title"),
                SlotFill("body", "First paragraph.<br><br>Second paragraph."),
            ],
        )
        result = renderer.render_section(match)
        assert "First paragraph.<br><br>Second paragraph." in result.html
        assert "<p" not in result.html


class TestTokenOverrides:
    def test_background_color_override(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("background-color", "_outer", "#f5f0e8")],
        )
        result = renderer.render_section(match)
        assert (
            "background-color:#f5f0e8" in result.html or "background-color: #f5f0e8" in result.html
        )

    def test_heading_font_override(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("font-family", "_heading", "Georgia, serif")],
        )
        result = renderer.render_section(match)
        assert "Georgia, serif" in result.html

    def test_heading_color_override(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("color", "_heading", "#FFFFFF")],
        )
        result = renderer.render_section(match)
        assert "color:#FFFFFF" in result.html

    def test_body_color_override(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("color", "_body", "#AABBCC")],
        )
        result = renderer.render_section(match)
        assert "color:#AABBCC" in result.html

    def test_color_override_does_not_corrupt_background_color(
        self, renderer: ComponentRenderer
    ) -> None:
        """Regression: color override must not match background-color: property."""
        match = _make_match(
            "text-block",
            overrides=[
                TokenOverride("background-color", "_outer", "#FE5117"),
                TokenOverride("color", "_heading", "#FFFFFF"),
            ],
        )
        result = renderer.render_section(match)
        assert "background-color:#FE5117" in result.html
        assert "color:#FFFFFF" in result.html

    def test_placeholder_url_stripped(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "article-card",
            fills=[
                SlotFill("image_url", "https://via.placeholder.com/280x200", slot_type="image"),
                SlotFill("heading", "Test Title"),
            ],
        )
        result = renderer.render_section(match)
        assert "via.placeholder.com" not in result.html


class TestTokenOverrideExpansion:
    """Tests for 49.4: expanded element-type matching for token overrides."""

    def test_heading_font_override_headline_slot(self, renderer: ComponentRenderer) -> None:
        """data-slot="headline" (hero-block) gets heading font override."""
        match = _make_match(
            "hero-block",
            overrides=[TokenOverride("font-family", "_heading", "Helvetica, sans-serif")],
        )
        result = renderer.render_section(match)
        assert "Helvetica, sans-serif" in result.html

    def test_heading_font_override_title_slot(self, renderer: ComponentRenderer) -> None:
        """data-slot="title" (product-card) gets heading font override."""
        match = _make_match(
            "product-card",
            overrides=[TokenOverride("font-family", "_heading", "Georgia, serif")],
        )
        result = renderer.render_section(match)
        assert "Georgia, serif" in result.html

    def test_body_font_override_body_text_slot(self, renderer: ComponentRenderer) -> None:
        """data-slot="body_text" (article-card) gets body font override."""
        match = _make_match(
            "article-card",
            overrides=[TokenOverride("font-family", "_body", "Verdana, sans-serif")],
        )
        result = renderer.render_section(match)
        assert "Verdana, sans-serif" in result.html

    def test_body_font_override_description_slot(self, renderer: ComponentRenderer) -> None:
        """data-slot="description" (event-card) gets body font override."""
        match = _make_match(
            "event-card",
            overrides=[TokenOverride("font-family", "_body", "Trebuchet MS, sans-serif")],
        )
        result = renderer.render_section(match)
        assert "Trebuchet MS, sans-serif" in result.html

    def test_heading_font_override_by_class(self, renderer: ComponentRenderer) -> None:
        """Elements with heading semantic class (no data-slot) get font override."""
        html_str = (
            '<td class="hero-title" style="font-family:Arial;font-size:32px;color:#333;">'
            "Heading</td>"
        )
        overrides = [TokenOverride("font-family", "_heading", "Helvetica")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "font-family:Helvetica" in result
        assert "font-family:Arial" not in result

    def test_body_font_override_by_class(self, renderer: ComponentRenderer) -> None:
        """Elements with body semantic class (no data-slot) get font override."""
        html_str = (
            '<td class="textblock-body" style="font-family:Arial;font-size:16px;color:#555;">'
            "Body text</td>"
        )
        overrides = [TokenOverride("font-family", "_body", "Verdana")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "font-family:Verdana" in result
        assert "font-family:Arial" not in result

    def test_heading_color_override_by_class(self, renderer: ComponentRenderer) -> None:
        """Elements with heading semantic class get color override."""
        html_str = (
            '<td class="artcard-heading" style="font-size:24px;color:#333333;font-weight:bold;">'
            "Title</td>"
        )
        overrides = [TokenOverride("color", "_heading", "#000000")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "color:#000000" in result
        assert "color:#333333" not in result

    def test_body_color_override_by_class(self, renderer: ComponentRenderer) -> None:
        """Elements with body semantic class get color override."""
        html_str = '<td class="product-desc" style="font-size:14px;color:#555555;">Description</td>'
        overrides = [TokenOverride("color", "_body", "#222222")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "color:#222222" in result
        assert "color:#555555" not in result

    def test_heading_size_override(self, renderer: ComponentRenderer) -> None:
        """data-slot="heading" gets font-size override."""
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("font-size", "_heading", "28px")],
        )
        result = renderer.render_section(match)
        assert "font-size:28px" in result.html

    def test_body_size_override(self, renderer: ComponentRenderer) -> None:
        """data-slot="body" gets font-size override."""
        match = _make_match(
            "text-block",
            overrides=[TokenOverride("font-size", "_body", "18px")],
        )
        result = renderer.render_section(match)
        assert "font-size:18px" in result.html

    def test_size_override_by_class(self, renderer: ComponentRenderer) -> None:
        """Elements with heading semantic class get font-size override."""
        html_str = (
            '<td class="hero-title" style="font-family:Arial;font-size:32px;color:#333;">'
            "Heading</td>"
        )
        overrides = [TokenOverride("font-size", "_heading", "40px")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "font-size:40px" in result
        assert "font-size:32px" not in result

    def test_bg_class_color_override(self, renderer: ComponentRenderer) -> None:
        """Elements with bg container class get background-color override."""
        html_str = (
            '<table class="textblock-bg" style="background-color:#ffffff;" '
            'role="presentation"><tr><td>Content</td></tr></table>'
        )
        overrides = [TokenOverride("background-color", "_outer", "#f5f0e8")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert "background-color:#f5f0e8" in result
        assert "background-color:#ffffff" not in result

    def test_no_match_unchanged(self, renderer: ComponentRenderer) -> None:
        """Elements with no data-slot and no semantic class are unchanged."""
        html_str = (
            '<td class="custom-unknown" style="font-family:Arial;font-size:16px;color:#555;">'
            "Text</td>"
        )
        overrides = [
            TokenOverride("font-family", "_heading", "Helvetica"),
            TokenOverride("color", "_body", "#000000"),
        ]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert result == html_str

    def test_data_slot_heading_regression(self, renderer: ComponentRenderer) -> None:
        """Original data-slot='heading' still works after expansion (regression)."""
        match = _make_match(
            "text-block",
            overrides=[
                TokenOverride("font-family", "_heading", "Georgia, serif"),
                TokenOverride("color", "_heading", "#112233"),
            ],
        )
        result = renderer.render_section(match)
        assert "Georgia, serif" in result.html
        assert "color:#112233" in result.html


class TestRenderPeelRow:
    """D3 follow-up: peeled same-row siblings compose side-by-side."""

    @staticmethod
    def _section(node_id: str, *, x: float, width: float) -> EmailSection:
        return EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id=node_id,
            node_name=f"card {node_id}",
            x_position=x,
            width=width,
            peel_row_id="wrap:r0",
            container_bg="#AA1733",
        )

    @staticmethod
    def _rendered(node_id: str) -> RenderedSection:
        return RenderedSection(
            html=f"<table><tr><td>card {node_id}</td></tr></table>",
            component_slug="article-card",
            section_idx=0,
            dark_mode_classes=(f"dm-{node_id}",),
            images=[{"node_id": node_id, "src": f"/assets/{node_id}.png"}],
        )

    def test_widths_scale_to_container(self, renderer: ComponentRenderer) -> None:
        """maap shape: 272 + 8 + 272 design px scale proportionally into 600."""
        sections = [
            self._section("a", x=0, width=272.0),
            self._section("gut", x=272, width=8.0),
            self._section("b", x=280, width=272.0),
        ]
        rendered = [self._rendered(s.node_id) for s in sections]
        row = renderer.render_peel_row(sections, rendered)
        assert 'data-peel-row="wrap:r0"' in row.html
        # 272/552*600 ≈ 296, 8/552*600 ≈ 9, last absorbs rounding → 600 total
        assert '<td width="296" valign="top">' in row.html
        assert '<td width="9" valign="top">' in row.html
        assert '<td width="295" valign="top">' in row.html
        assert "max-width: 296px" in row.html
        assert "card a" in row.html and "card b" in row.html

    def test_band_bg_and_member_merge(self, renderer: ComponentRenderer) -> None:
        sections = [
            self._section("a", x=0, width=300.0),
            self._section("b", x=300, width=300.0),
        ]
        rendered = [self._rendered(s.node_id) for s in sections]
        row = renderer.render_peel_row(sections, rendered)
        assert 'bgcolor="#AA1733"' in row.html
        assert "background-color:#AA1733;" in row.html
        # Row container carries the dark-mode inversion hook (Track 41.3)
        assert 'class="bgcolor-AA1733"' in row.html
        assert row.dark_mode_classes == ("bgcolor-AA1733", "dm-a", "dm-b")
        assert [img["node_id"] for img in row.images] == ["a", "b"]
        # members render in given order inside inline-block column divs
        assert row.html.index("card a") < row.html.index("card b")
        assert row.html.count('class="column"') == 2


class TestTextNodeOverrides:
    """RC-D-prime: _text_<node_id> overrides land on per-node <td> anchors."""

    _ANCHORS = (
        '<td data-slot="body" style="font-size:16px;color:#555;">'
        '<table role="presentation"><tr>'
        '<td data-node-id="p1" style="mso-line-height-rule:exactly;">One</td></tr>'
        '<tr><td data-node-id="p2" style="mso-line-height-rule:exactly;">Two</td></tr>'
        "</table></td>"
    )

    def test_each_anchor_gets_its_own_typography(self, renderer: ComponentRenderer) -> None:
        overrides = [
            TokenOverride("font-size", "_text_p1", "18.0px"),
            TokenOverride("color", "_text_p1", "#111111"),
            TokenOverride("font-size", "_text_p2", "14.0px"),
            TokenOverride("color", "_text_p2", "#666666"),
        ]
        result = renderer._apply_token_overrides(self._ANCHORS, overrides)
        assert (
            '<td data-node-id="p1" style="mso-line-height-rule:exactly;font-size:18.0px;color:#111111;">'
            in result
        )
        assert (
            '<td data-node-id="p2" style="mso-line-height-rule:exactly;font-size:14.0px;color:#666666;">'
            in result
        )
        # The shared body slot's own style is untouched
        assert 'data-slot="body" style="font-size:16px;color:#555;"' in result

    def test_line_height_does_not_clobber_mso_rule(self, renderer: ComponentRenderer) -> None:
        overrides = [TokenOverride("line-height", "_text_p1", "24px")]
        result = renderer._apply_token_overrides(self._ANCHORS, overrides)
        assert "mso-line-height-rule:exactly;line-height:24px;" in result

    def test_replaces_existing_declaration(self, renderer: ComponentRenderer) -> None:
        html_str = '<td data-node-id="p1" style="font-size:12px;">One</td>'
        overrides = [TokenOverride("font-size", "_text_p1", "20.0px")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert result == '<td data-node-id="p1" style="font-size:20.0px;">One</td>'

    def test_img_with_same_node_id_untouched(self, renderer: ComponentRenderer) -> None:
        html_str = (
            '<img data-node-id="p1" style="border:0;" src="x.png" alt="">'
            '<td data-node-id="p1" style="">One</td>'
        )
        overrides = [TokenOverride("color", "_text_p1", "#111111")]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert '<img data-node-id="p1" style="border:0;"' in result
        assert '<td data-node-id="p1" style="color:#111111;">' in result

    def test_cell_padding_longhand_upserts_into_first_td(self, renderer: ComponentRenderer) -> None:
        html_str = '<table><tr><td style="padding:32px 24px;">Content</td></tr></table>'
        overrides = [
            TokenOverride("padding-top", "_cell", "24px"),
            TokenOverride("padding-bottom", "_cell", "8px"),
        ]
        result = renderer._apply_token_overrides(html_str, overrides)
        assert 'style="padding:32px 24px;padding-top:24px;padding-bottom:8px;"' in result


class TestCtaScopedOverrides:
    """_cta token overrides must only touch CTA elements, not adjacent HTML.

    Regression: the original implementation used `re.sub` with document-wide
    patterns for `bgcolor`/`fillcolor`/`strokecolor` and a blanket
    `_replace_css_prop_all` for `background-color`/`border-radius`/`border-color`
    /`border-width`, clobbering outer card styles in composite templates like
    event-card and pricing-table.
    """

    def test_cta_border_radius_override_does_not_clobber_outer_card_radius(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        html_in = (
            '<table class="event-card" style="border-radius: 8px;">'
            '<tr><td><a data-slot="cta_url" href="#" '
            'style="padding: 12px; border-radius: 4px;">Go</a></td></tr>'
            "</table>"
        )
        overrides = [TokenOverride("border-radius", "_cta", "6px")]
        out = renderer._apply_token_overrides(html_in, overrides)
        assert 'class="event-card" style="border-radius: 8px;"' in out
        assert "border-radius:6px" in out
        assert out.count("border-radius: 8px") == 1  # outer preserved

    def test_cta_background_override_does_not_clobber_outer_card_bg(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        html_in = (
            '<table class="event-card" style="background-color: #FE5117;">'
            '<tr><td><a data-slot="cta_url" href="#" '
            'style="background-color: #0066cc;">Go</a></td></tr>'
            "</table>"
        )
        out = renderer._apply_token_overrides(
            html_in, [TokenOverride("background-color", "_cta", "#00AA88")]
        )
        assert "#FE5117" in out  # outer preserved
        assert "#00AA88" in out  # CTA updated
        assert "#0066cc" not in out  # CTA's old value replaced

    def test_cta_border_color_override_scoped_to_cta_class(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        html_in = (
            '<table class="event-card" style="border-color: #cccccc;">'
            '<tr><td><table class="cta-btn" style="border-color: #1a1a1a;">'
            '<tr><td><a data-slot="cta_url" href="#" '
            'style="border-color: #1a1a1a;">x</a></td></tr>'
            "</table></td></tr></table>"
        )
        out = renderer._apply_token_overrides(
            html_in, [TokenOverride("border-color", "_cta", "#FF0000")]
        )
        assert "border-color: #cccccc" in out  # outer event-card preserved
        assert out.count("#FF0000") >= 1  # at least CTA updated

    def test_cta_background_override_preserves_outer_hero_hex(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        """Concrete data/debug/10 regression: before the fix, the outer
        ``#FE5117`` event-card background and the inner ``#0066cc`` CTA
        background both flattened to the override value. Now only the CTA
        updates; the hero background stays put.
        """
        html_in = (
            '<table role="presentation" class="event-card" width="100%" '
            'cellpadding="0" cellspacing="0" border="0" '
            'style="background-color:#FE5117; border: 1px solid #e0e0e0; '
            'border-radius: 8px; overflow: hidden;">'
            "<tr><td>"
            '<a data-slot="cta_url" href="https://example.com/event" '
            'style="display: inline-block; padding: 12px 32px; '
            "background-color: #0066cc; color: #ffffff; "
            'font-size: 16px; border-radius: 4px;">'
            '<span data-slot="cta_text">Register Now</span></a>'
            "</td></tr></table>"
        )
        out = renderer._apply_token_overrides(
            html_in, [TokenOverride("background-color", "_cta", "#3366ff")]
        )
        assert "#FE5117" in out  # outer hero hex preserved
        assert "#3366ff" in out  # CTA updated
        assert "#0066cc" not in out  # CTA's old color gone

    def test_cta_override_handles_data_slot_before_style_only(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        """Happy path: `data-slot` appears before `style` in the same tag."""
        html_in = '<a data-slot="cta_url" href="#" style="border-radius: 4px;">x</a>'
        out = renderer._apply_token_overrides(
            html_in, [TokenOverride("border-radius", "_cta", "6px")]
        )
        assert "border-radius:6px" in out

    def test_cta_override_skips_style_before_data_slot_regression(
        self,
        renderer: ComponentRenderer,
    ) -> None:
        """Locks down the current attribute-order assumption.

        If a template author ever writes ``style`` before ``data-slot`` on
        the ``<a>``, the scoped regex will NOT match and the override is
        silently dropped. That is acceptable today — this test fails only
        if someone removes the assumption without widening the regex.
        Flip the assertion + widen `_CTA_LINK_STYLE_RE_TEMPLATE` if a real
        template ever lands in this shape.
        """
        html_in = '<a style="border-radius: 4px;" data-slot="cta_url" href="#">x</a>'
        out = renderer._apply_token_overrides(
            html_in, [TokenOverride("border-radius", "_cta", "6px")]
        )
        # Known limitation — style before data-slot isn't matched.
        assert "border-radius: 4px" in out


class TestAnnotations:
    def test_section_comment_marker(self, renderer: ComponentRenderer) -> None:
        match = _make_match("text-block", idx=3)
        result = renderer.render_section(match)
        assert "<!-- section:section_3 -->" in result.html
        assert "<!-- /section:section_3 -->" in result.html

    def test_component_name_attribute(self, renderer: ComponentRenderer) -> None:
        section = _make_section(node_name="Hero Banner")
        match = _make_match("hero-block", section=section)
        result = renderer.render_section(match)
        assert 'data-component-name="Hero Banner"' in result.html

    def test_component_name_html_escaped(self, renderer: ComponentRenderer) -> None:
        section = _make_section(node_name='Frame "Special" <1>')
        match = _make_match("text-block", section=section)
        result = renderer.render_section(match)
        assert "&quot;" in result.html or "&#34;" in result.html


class TestMsoWidths:
    def test_updates_mso_width_600(self, renderer: ComponentRenderer) -> None:
        match = _make_match("text-block")
        result = renderer.render_section(match)
        assert 'width="600"' in result.html

    def test_updates_mso_width_custom(self) -> None:
        r = ComponentRenderer(container_width=700)
        r.load()
        match = _make_match("text-block")
        result = r.render_section(match)
        assert 'width="700"' in result.html

    # B6 (Mode D): clamp full-bleed 600/640 widths inside MSO blocks to the
    # container. Seeds never emit 640 inside an MSO conditional, so the clamp
    # is exercised here by calling _update_mso_widths directly.
    def test_clamps_640_attr_to_container(self, renderer: ComponentRenderer) -> None:
        html = '<!--[if mso]><table width="640" align="center"><tr><td><![endif]-->'
        assert renderer._update_mso_widths(html, 600) == (
            '<!--[if mso]><table width="600" align="center"><tr><td><![endif]-->'
        )

    def test_clamps_640_style_forms_to_container(self, renderer: ComponentRenderer) -> None:
        html = '<!--[if mso]><table style="max-width: 640px;width:640px;"><![endif]-->'
        out = renderer._update_mso_widths(html, 600)
        assert "max-width: 600px" in out  # prefix + spacing preserved
        assert "width:600px" in out
        assert "640" not in out

    def test_640_preserved_when_container_is_640(self, renderer: ComponentRenderer) -> None:
        # Clamp target IS the container, so 640-in-640 is a no-op — this is
        # what keeps the container=640 baselines (cases 6, 9) byte-identical.
        html = '<!--[if mso]><table width="640" style="max-width:640px;"><![endif]-->'
        assert renderer._update_mso_widths(html, 640) == html

    def test_non_width_640_left_untouched(self, renderer: ComponentRenderer) -> None:
        # height + URL digits that merely contain 640 must not be clamped.
        html = (
            '<!--[if mso]><img height="640" '
            'src="https://x/lib/fe37117075640474741075/a.jpg"><![endif]-->'
        )
        assert renderer._update_mso_widths(html, 600) == html

    def test_640_outside_mso_block_untouched(self, renderer: ComponentRenderer) -> None:
        # MSO-scoping intact: a fixed-640 table outside any MSO conditional
        # (the responsive main table) is left alone.
        html = '<table width="640" style="max-width:640px;">x</table>'
        assert renderer._update_mso_widths(html, 600) == html


class TestDarkModeExtraction:
    def test_extracts_dark_mode_classes(self, renderer: ComponentRenderer) -> None:
        match = _make_match("text-block")
        result = renderer.render_section(match)
        assert "textblock-bg" in result.dark_mode_classes

    def test_hero_has_overlay_class(self, renderer: ComponentRenderer) -> None:
        match = _make_match("hero-block")
        result = renderer.render_section(match)
        assert "hero-overlay" in result.dark_mode_classes


class TestImageExtraction:
    def test_extracts_images(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "full-width-image",
            fills=[
                SlotFill("image_url", "/img/banner.jpg", slot_type="image"),
            ],
        )
        result = renderer.render_section(match)
        assert len(result.images) >= 1
        assert any("/img/banner.jpg" in img["src"] for img in result.images)


class TestFallbackRender:
    def test_missing_slug_falls_back(self) -> None:
        r = ComponentRenderer(container_width=600)
        r.load()
        match = _make_match("nonexistent-component-xyz")
        result = r.render_section(match)
        assert result.component_slug == "text-block"
        assert "table" in result.html


class TestOutputStructure:
    """Verify the output uses independent table blocks (not tr-stacking)."""

    def test_output_is_independent_table(self, renderer: ComponentRenderer) -> None:
        match = _make_match("text-block")
        result = renderer.render_section(match)
        # Should NOT be wrapped in <tr>
        assert "<tr data-section-id" not in result.html
        # Should be an independent table
        assert '<table role="presentation"' in result.html

    def test_output_has_mso_wrapper(self, renderer: ComponentRenderer) -> None:
        match = _make_match("text-block")
        result = renderer.render_section(match)
        assert "<!--[if mso]>" in result.html
        assert "<![endif]-->" in result.html

    def test_nesting_depth_under_5(self, renderer: ComponentRenderer) -> None:
        """Component templates should have max 4 levels of table nesting."""
        for slug in ["text-block", "hero-block", "cta-button", "email-footer", "divider"]:
            match = _make_match(slug)
            result = renderer.render_section(match)
            # Count max nesting by tracking open/close table tags
            depth = 0
            max_depth = 0
            for line in result.html.split("\n"):
                depth += line.count("<table") - line.count("</table")
                max_depth = max(max_depth, depth)
            assert max_depth <= 5, f"{slug} has {max_depth} levels of table nesting"


class TestBlankUnfilledTextSlots:
    """Phase 53 B3: unfilled <td> text slots are blanked; structural slots kept.

    Snapshot baselines also cover this, but they self-skip in CI (gitignored
    `data/debug` fixtures), so these seed-template tests are the CI guard.
    """

    @staticmethod
    def _td_inner(html_str: str, slot_id: str) -> str | None:
        m = re.search(rf'<td\b[^>]*\bdata-slot="{slot_id}"[^>]*>(.*?)</td>', html_str, re.DOTALL)
        return m.group(1).strip() if m else None

    def test_unfilled_td_text_slot_blanked(self, renderer: ComponentRenderer) -> None:
        # headline is filled; subtext gets no fill and must not leak its seed.
        match = _make_match("hero-block", fills=[SlotFill("headline", "Summer Sale!")])
        result = renderer.render_section(match)
        assert self._td_inner(result.html, "subtext") == ""
        assert "Summer Sale!" in result.html

    def test_filled_td_slot_not_blanked(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "hero-block",
            fills=[SlotFill("headline", "Hi"), SlotFill("subtext", "There")],
        )
        result = renderer.render_section(match)
        assert "There" in result.html

    def test_divider_structural_slot_preserved(self, renderer: ComponentRenderer) -> None:
        # divider_style wraps the visible <div class="divider-line"> — never blank.
        result = renderer.render_section(_make_match("divider"))
        assert 'class="divider-line"' in result.html

    def test_footer_legal_fields_preserved(self, renderer: ComponentRenderer) -> None:
        # _fills_footer never emits company_name/company_address; the seed text is
        # legally required and must survive an empty fill set.
        result = renderer.render_section(_make_match("footer"))
        assert self._td_inner(result.html, "company_name")
        assert self._td_inner(result.html, "company_address")

    def test_unfilled_cta_anchor_pruned(self, renderer: ComponentRenderer) -> None:
        # F4a (RC-F4): an unfilled CTA is a leaked seed default. The whole
        # <a>…<span data-slot="cta_text">…</span></a> is removed — blanking the
        # span alone would leave an empty clickable anchor (B3 advisor rule).
        result = renderer.render_section(_make_match("article-card"))
        assert "Read More" not in result.html
        assert 'data-slot="cta_text"' not in result.html
        assert 'data-slot="cta_url"' not in result.html

    def test_cta_button_empty_no_seed_leak(self, renderer: ComponentRenderer) -> None:
        # F4a: an empty cta-button leaks "Shop Now" on BOTH surfaces (non-MSO
        # <span> + MSO <v:roundrect><center>) plus the seed-blue chrome — all go.
        result = renderer.render_section(_make_match("cta-button"))
        assert "Shop Now" not in result.html
        assert "v:roundrect" not in result.html
        assert 'class="cta-btn"' not in result.html

    def test_hero_block_empty_drops_cta_keeps_background(self, renderer: ComponentRenderer) -> None:
        # F4a: hero with no button drops its "Learn More" seed CTA anchor, but
        # the MSO <v:rect> background twin (not a roundrect) is untouched.
        result = renderer.render_section(_make_match("hero-block"))
        assert "Learn More" not in result.html
        assert 'data-slot="cta_url"' not in result.html
        assert "v:rect" in result.html

    def test_filled_cta_not_pruned(self, renderer: ComponentRenderer) -> None:
        # Guard against over-pruning: a real CTA fill keeps its anchor + label.
        result = renderer.render_section(
            _make_match(
                "cta-button",
                fills=[
                    SlotFill("cta_text", "Buy Now"),
                    SlotFill("cta_url", "https://x.test", slot_type="cta"),
                ],
            )
        )
        assert "Buy Now" in result.html
        assert 'data-slot="cta_url"' in result.html

    def test_col_icon_placeholder_imgs_stripped(self, renderer: ComponentRenderer) -> None:
        # F4b (RC-F4): col-icon's fakeimg placeholders — the desktop unfilled
        # icon_2 AND the no-data-slot mobile twins — are removed whole, so
        # neither the src nor the "Feature icon" alt survives.
        result = renderer.render_section(_make_match("col-icon"))
        assert "fakeimg" not in result.html
        assert "Feature icon" not in result.html

    def test_col_icon_real_image_not_stripped(self, renderer: ComponentRenderer) -> None:
        # Guard against over-stripping: a filled (relative /api) icon survives
        # while the sibling placeholders are still dropped.
        result = renderer.render_section(
            _make_match(
                "col-icon",
                fills=[
                    SlotFill(
                        "icon_1_url",
                        "/api/v1/design-sync/assets/ic1.png",
                        slot_type="image",
                        attr_overrides={"alt": "Truck icon"},
                    ),
                ],
            )
        )
        assert "/api/v1/design-sync/assets/ic1.png" in result.html
        assert "fakeimg" not in result.html

    def test_is_blankable_text_predicate(self) -> None:
        assert _is_blankable_text("Section Heading") is True
        assert _is_blankable_text("Line 1<br>Line 2") is True
        assert _is_blankable_text("<strong>Bold</strong>") is True
        assert _is_blankable_text('<div class="divider-line">&nbsp;</div>') is False
        assert _is_blankable_text('<a href="#">Home</a>') is False
        assert _is_blankable_text("&nbsp;") is False
        assert _is_blankable_text("") is False


class TestFindMatchingClose:
    """Phase 53 B4: depth-balanced close-tag finder (CI guard, snapshot-free)."""

    def test_nested_same_tag_returns_outer_close(self) -> None:
        s = "<td>A<td>B</td>C</td>"
        start = len("<td>")
        idx = _find_matching_close(s, "td", start)
        assert idx is not None
        # the final (outer) </td>, not the first inner one
        assert s[idx:] == "</td>"
        assert s[start:idx] == "A<td>B</td>C"

    def test_leaf_returns_own_close(self) -> None:
        s = "<td>hello</td>"
        assert _find_matching_close(s, "td", len("<td>")) == s.index("</td>")

    def test_different_tag_nesting_ignored(self) -> None:
        s = '<td>x<a href="#">y</a>z</td>'
        idx = _find_matching_close(s, "td", len("<td>"))
        assert idx is not None and s[idx:] == "</td>"

    def test_unbalanced_returns_none(self) -> None:
        assert _find_matching_close("<td>oops", "td", len("<td>")) is None


class TestFooterContentNoTruncation:
    """Phase 53 B4: a footer_content <td> wrapping a nested table is filled
    whole, not truncated at the first inner </td> (Mode A2)."""

    def test_footer_content_fill_replaces_whole_cell(self, renderer: ComponentRenderer) -> None:
        fill = "Acme Ltd legal line<br><br>Unsubscribe | Preferences"
        match = _make_match("email-footer", fills=[SlotFill("footer_content", fill)])
        result = renderer.render_section(match).html
        # The Figma-derived footer content survives in full…
        assert "Acme Ltd legal line" in result
        assert "Unsubscribe | Preferences" in result
        # …and the seed scaffold it replaced is gone — these strings only
        # survive when the fill truncates at the first nested </td>.
        assert "123 Business Street" not in result
        assert "2026 Company Name" not in result
        # Structure stays balanced — truncation orphans closing tags.
        assert result.count("<td") == result.count("</td>")
        assert result.count("<table") == result.count("</table>")


class TestColumnWidthFractions:
    """A8 (Phase 53 D2): column seed widths rewritten from measured fractions."""

    @staticmethod
    def _column_match(slug: str, fractions: tuple[float, ...]) -> ComponentMatch:
        section = EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id="frame_1",
            node_name="Columns",
            column_width_fractions=fractions,
        )
        return ComponentMatch(
            section_idx=0,
            section=section,
            component_slug=slug,
            slot_fills=[],
            token_overrides=[],
        )

    def test_asymmetric_two_column_widths(self, renderer: ComponentRenderer) -> None:
        """A 2:1 split rewrites both the MSO <td> and the div max-width surfaces."""
        match = self._column_match("column-layout-2", (2 / 3, 1 / 3))
        result = renderer.render_section(match).html
        assert '<td width="400" valign="top">' in result
        assert '<td width="200" valign="top">' in result
        assert '<td width="300" valign="top">' not in result
        assert "max-width: 400px" in result
        assert "max-width: 200px" in result
        assert "max-width: 300px" not in result

    def test_widths_sum_preserved_with_rounding(self, renderer: ComponentRenderer) -> None:
        """The last column absorbs rounding so the seed's total never drifts."""
        match = self._column_match("column-layout-3", (0.55, 0.27, 0.18))
        result = renderer.render_section(match).html
        widths = [int(w) for w in re.findall(r'<td width="(\d+)" valign="top">', result)]
        assert len(widths) == 3
        assert sum(widths) == 600
        assert widths == [330, 162, 108]

    def test_equal_within_tolerance_is_byte_stable(self, renderer: ComponentRenderer) -> None:
        """Near-equal fractions render byte-identically to the no-fractions seed."""
        baseline = renderer.render_section(self._column_match("column-layout-2", ())).html
        nudged = renderer.render_section(self._column_match("column-layout-2", (0.52, 0.48))).html
        assert nudged == baseline

    def test_count_mismatch_is_no_op(self, renderer: ComponentRenderer) -> None:
        """Fraction count != seed column count leaves the seed untouched."""
        baseline = renderer.render_section(self._column_match("column-layout-2", ())).html
        mismatched = renderer.render_section(
            self._column_match("column-layout-2", (0.5, 0.3, 0.2))
        ).html
        assert mismatched == baseline

    def test_non_column_slug_untouched(self, renderer: ComponentRenderer) -> None:
        """Fractions on a non-column component are ignored."""
        section = EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id="frame_1",
            node_name="TestSection",
            column_width_fractions=(0.7, 0.3),
        )
        with_fractions = renderer.render_section(
            ComponentMatch(
                section_idx=0,
                section=section,
                component_slug="text-block",
                slot_fills=[],
                token_overrides=[],
            )
        ).html
        baseline = renderer.render_section(_make_match("text-block")).html
        assert with_fractions == baseline

    def test_mso_and_div_surfaces_agree(self, renderer: ComponentRenderer) -> None:
        """MSO ghost-td widths and div max-widths carry identical values."""
        match = self._column_match("column-layout-2", (0.75, 0.25))
        result = renderer.render_section(match).html
        td_widths = re.findall(r'<td width="(\d+)" valign="top">', result)
        div_widths = re.findall(r'class="column"[^>]*?max-width:\s*(\d+)px', result)
        assert td_widths == div_widths == ["450", "150"]


def _img(node_id: str, w: float, h: float) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name="photo", width=w, height=h)


def _hero_section(images: list[ImagePlaceholder]) -> EmailSection:
    """A single-column HERO section — image-only heroes match ``full-width-image``.

    Mirrors the corpus case 7 §[1] / case 8 §[0] shape: two stacked images in
    one hero band, no heading text.
    """
    return EmailSection(
        section_type=EmailSectionType.HERO,
        node_id="frame_hero",
        node_name="hero",
        images=images,
        column_layout=ColumnLayout.SINGLE,
        width=600,
    )


def _img_tag_for(html: str, src_fragment: str) -> str:
    """Return the single ``<img …>`` tag whose src contains ``src_fragment``."""
    m = re.search(rf"<img\b[^>]*{re.escape(src_fragment)}[^>]*/?>", html)
    assert m is not None, f"no <img> with src containing {src_fragment!r}"
    return m.group(0)


class TestF1MultiImageEmission:
    """F1 (RC-F1): single-image builders emit ALL images in a section.

    Previously ``_fills_full_width_image`` took ``section.images[0]`` and
    silently dropped the rest, so case 7/8 heroes vanished. F1 selects the
    LARGEST image (by area) as the primary slot fill and stacks the remaining
    images as ``<tr><td><img>`` rows in tree order — those before the primary
    above it, those after below — each sized by the inline F3 width rule.

    The corpus exercises only full-width extras (600px-wide strips); the
    sub-threshold width rule and the after-primary ordering are covered here
    synthetically because no fixture triggers them.
    """

    def test_two_image_section_emits_two_imgs(self, renderer: ComponentRenderer) -> None:
        """A 2-image hero renders BOTH images (RED pre-F1: only images[0])."""
        section = _hero_section([_img("strip", 600, 67), _img("hero", 600, 400)])
        match = match_section(section, 0, container_width=600)
        assert match.component_slug == "full-width-image"
        html = renderer.render_section(match).html
        assert html.count("<img") == 2
        assert "strip.png" in html
        assert "hero.png" in html

    def test_largest_image_is_primary(self, renderer: ComponentRenderer) -> None:
        """The seed's primary image slot carries the largest image, not images[0]."""
        section = _hero_section([_img("strip", 600, 67), _img("hero", 600, 400)])
        match = match_section(section, 0, container_width=600)
        html = renderer.render_section(match).html
        # The primary lives in the seed's bannerimg (data-slot=image_url) element.
        primary = re.search(r'<img\b[^>]*class="bannerimg"[^>]*>', html)
        assert primary is not None
        assert "hero.png" in primary.group(0)

    def test_extra_before_primary_renders_above(self, renderer: ComponentRenderer) -> None:
        """An image preceding the primary in tree order renders above it."""
        section = _hero_section([_img("strip", 600, 67), _img("hero", 600, 400)])
        match = match_section(section, 0, container_width=600)
        html = renderer.render_section(match).html
        assert html.index("strip.png") < html.index("hero.png")

    def test_extra_after_primary_renders_below(self, renderer: ComponentRenderer) -> None:
        """An image following the primary in tree order renders below it."""
        section = _hero_section([_img("hero", 600, 400), _img("strip", 600, 67)])
        match = match_section(section, 0, container_width=600)
        html = renderer.render_section(match).html
        assert html.index("hero.png") < html.index("strip.png")

    def test_small_stacked_image_uses_natural_width(self, renderer: ComponentRenderer) -> None:
        """A sub-threshold stacked image keeps its natural width (F3 icon guard)."""
        section = _hero_section([_img("hero", 600, 400), _img("icon", 64, 64)])
        match = match_section(section, 0, container_width=600)
        html = renderer.render_section(match).html
        icon_tag = _img_tag_for(html, "icon.png")
        assert "width:64px" in icon_tag
        assert "width:100%" not in icon_tag
        assert 'width="64"' in icon_tag
