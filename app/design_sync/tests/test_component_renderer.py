"""Tests for component renderer — fills component templates with Figma content."""

from __future__ import annotations

import re

import pytest

from app.design_sync.component_matcher import ComponentMatch, SlotFill, TokenOverride
from app.design_sync.component_renderer import ComponentRenderer, _is_blankable_text
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    EmailSectionType,
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
            fills=[SlotFill("cta_url", "https://shop.example.com", slot_type="cta")],
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

    def test_cta_label_span_preserved(self, renderer: ComponentRenderer) -> None:
        # <span data-slot="cta_text"> lives inside <a>; td-only scope leaves it
        # intact (blanking would create an empty clickable link).
        result = renderer.render_section(_make_match("article-card"))
        cta = re.search(
            r'<span\b[^>]*\bdata-slot="cta_text"[^>]*>(.*?)</span>',
            result.html,
            re.DOTALL,
        )
        assert cta is not None and cta.group(1).strip() != ""

    def test_is_blankable_text_predicate(self) -> None:
        assert _is_blankable_text("Section Heading") is True
        assert _is_blankable_text("Line 1<br>Line 2") is True
        assert _is_blankable_text("<strong>Bold</strong>") is True
        assert _is_blankable_text('<div class="divider-line">&nbsp;</div>') is False
        assert _is_blankable_text('<a href="#">Home</a>') is False
        assert _is_blankable_text("&nbsp;") is False
        assert _is_blankable_text("") is False
