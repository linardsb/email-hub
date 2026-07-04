"""Tests for component matcher — maps EmailSection to component slugs."""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _build_column_fill_html,
    _build_slot_fills,
    _derive_image_alt,
    _is_descriptive_alt,
    _is_placeholder,
    _safe_color,
    _safe_url,
    match_all,
    match_section,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_id: str = "frame_1",
    node_name: str = "Section",
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    buttons: list[ButtonElement] | None = None,
    column_layout: ColumnLayout = ColumnLayout.SINGLE,
    column_count: int = 1,
    width: float | None = None,
    height: float | None = 200,
    bg_color: str | None = None,
    spacing_after: float | None = None,
    padding_top: float | None = None,
    padding_right: float | None = None,
    padding_bottom: float | None = None,
    padding_left: float | None = None,
    column_groups: list[ColumnGroup] | None = None,
    content_roles: tuple[str, ...] = (),
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name=node_name,
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        column_layout=column_layout,
        column_count=column_count,
        width=width,
        height=height,
        bg_color=bg_color,
        spacing_after=spacing_after,
        padding_top=padding_top,
        padding_right=padding_right,
        padding_bottom=padding_bottom,
        padding_left=padding_left,
        column_groups=column_groups or [],
        content_roles=content_roles,
    )


def _text(content: str, *, is_heading: bool = False, font_family: str | None = None) -> TextBlock:
    return TextBlock(node_id="t1", content=content, is_heading=is_heading, font_family=font_family)


def _image(
    node_id: str = "img_1", name: str = "photo", w: float = 600, h: float = 400
) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name=name, width=w, height=h)


def _button(text: str = "Click me") -> ButtonElement:
    return ButtonElement(node_id="btn_1", text=text)


class TestMatchSectionType:
    """Test that each EmailSectionType maps to the expected component slug."""

    def test_preheader(self) -> None:
        s = _make_section(EmailSectionType.PREHEADER, texts=[_text("Preview")])
        m = match_section(s, 0)
        assert m.component_slug == "preheader"
        assert m.confidence == 1.0

    def test_header_with_image(self) -> None:
        s = _make_section(EmailSectionType.HEADER, images=[_image()])
        m = match_section(s, 0)
        assert m.component_slug == "logo-header"

    def test_header_with_nav_text(self) -> None:
        s = _make_section(
            EmailSectionType.HEADER,
            texts=[_text("Home"), _text("About"), _text("Contact")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "email-header"

    def test_hero_with_image_and_text(self) -> None:
        s = _make_section(
            EmailSectionType.HERO,
            texts=[_text("Big Title", is_heading=True)],
            images=[_image()],
            buttons=[_button("Shop")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "hero-block"

    def test_hero_image_only(self) -> None:
        s = _make_section(EmailSectionType.HERO, images=[_image()])
        m = match_section(s, 0)
        assert m.component_slug == "full-width-image"

    def test_content_text_only(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Heading", is_heading=True), _text("Body text")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "text-block"

    def test_content_image_and_text(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True)],
            images=[_image()],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"

    def test_content_image_only_full_width(self) -> None:
        s = _make_section(EmailSectionType.CONTENT, images=[_image(w=600, h=400)])
        m = match_section(s, 0)
        assert m.component_slug == "full-width-image"

    def test_content_image_only_small(self) -> None:
        s = _make_section(EmailSectionType.CONTENT, images=[_image(w=200, h=150)], width=600)
        m = match_section(s, 0)
        assert m.component_slug == "image-block"

    def test_content_multiple_images(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            images=[_image("i1", "p1"), _image("i2", "p2")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "image-grid"

    def test_cta(self) -> None:
        s = _make_section(EmailSectionType.CTA, buttons=[_button("Buy")])
        m = match_section(s, 0)
        assert m.component_slug == "cta-button"

    def test_footer(self) -> None:
        s = _make_section(EmailSectionType.FOOTER, texts=[_text("Legal")])
        m = match_section(s, 0)
        assert m.component_slug == "email-footer"

    def test_social(self) -> None:
        s = _make_section(EmailSectionType.SOCIAL)
        m = match_section(s, 0)
        assert m.component_slug == "social-icons"

    def test_divider(self) -> None:
        s = _make_section(EmailSectionType.DIVIDER)
        m = match_section(s, 0)
        assert m.component_slug == "divider"

    def test_spacer(self) -> None:
        s = _make_section(EmailSectionType.SPACER, height=24)
        m = match_section(s, 0)
        assert m.component_slug == "spacer"

    def test_nav(self) -> None:
        s = _make_section(EmailSectionType.NAV)
        m = match_section(s, 0)
        assert m.component_slug == "navigation-bar"

    def test_unknown_with_text(self) -> None:
        s = _make_section(EmailSectionType.UNKNOWN, texts=[_text("Something")])
        m = match_section(s, 0)
        assert m.component_slug == "text-block"
        assert m.confidence < 1.0

    def test_unknown_with_image_and_text(self) -> None:
        s = _make_section(
            EmailSectionType.UNKNOWN,
            texts=[_text("Title")],
            images=[_image()],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"
        assert m.confidence < 1.0


class TestColumnLayout:
    """Test that column layouts override section type."""

    def test_two_column(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            column_layout=ColumnLayout.TWO_COLUMN,
            column_count=2,
            texts=[_text("Col 1"), _text("Col 2")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "column-layout-2"

    def test_three_column(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            column_layout=ColumnLayout.THREE_COLUMN,
            column_count=3,
        )
        m = match_section(s, 0)
        assert m.component_slug == "column-layout-3"

    def test_multi_column(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            column_layout=ColumnLayout.MULTI_COLUMN,
            column_count=4,
        )
        m = match_section(s, 0)
        assert m.component_slug == "column-layout-4"


class TestSlotFills:
    """Test that slot fills are extracted correctly from section content."""

    def test_hero_slot_fills(self) -> None:
        s = _make_section(
            EmailSectionType.HERO,
            texts=[_text("Big Title", is_heading=True), _text("Description")],
            images=[_image("hero_img", "Banner")],
            buttons=[_button("Shop Now")],
        )
        m = match_section(s, 0)
        fill_ids = {f.slot_id for f in m.slot_fills}
        assert "headline" in fill_ids
        assert "subtext" in fill_ids
        assert "hero_image" in fill_ids
        assert "cta_text" in fill_ids

    def test_text_block_heading_and_body(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True), _text("Body content")],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert fills_by_id["heading"].value == "Title"
        assert "Body content" in fills_by_id["body"].value

    def test_cta_button_fills(self) -> None:
        s = _make_section(EmailSectionType.CTA, buttons=[_button("Buy Now")])
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert fills_by_id["cta_text"].value == "Buy Now"
        assert fills_by_id["cta_url"].value == "#"

    def test_spacer_height_fill(self) -> None:
        s = _make_section(EmailSectionType.SPACER, height=48)
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert fills_by_id["spacer_height"].value == "48"

    def test_logo_header_image_fill(self) -> None:
        s = _make_section(EmailSectionType.HEADER, images=[_image("logo_1", "Logo", 180, 48)])
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "logo_url" in fills_by_id
        assert fills_by_id["logo_url"].attr_overrides["width"] == "180"

    def test_column_fills_distribute_texts(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            column_layout=ColumnLayout.TWO_COLUMN,
            column_count=2,
            texts=[_text("Left"), _text("Right")],
        )
        m = match_section(s, 0)
        fill_ids = {f.slot_id for f in m.slot_fills}
        assert "col_1" in fill_ids
        assert "col_2" in fill_ids


class TestTokenOverrides:
    """Test token override extraction from section properties."""

    def test_bg_color_override(self) -> None:
        s = _make_section(EmailSectionType.CONTENT, bg_color="#f5f0e8")
        m = match_section(s, 0)
        bg_overrides = [o for o in m.token_overrides if o.css_property == "background-color"]
        assert len(bg_overrides) == 1
        assert bg_overrides[0].value == "#f5f0e8"

    def test_font_family_override(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True, font_family="Georgia, serif")],
        )
        m = match_section(s, 0)
        font_overrides = [o for o in m.token_overrides if o.css_property == "font-family"]
        assert len(font_overrides) >= 1

    def test_padding_override(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            padding_top=16,
            padding_right=24,
            padding_bottom=16,
            padding_left=24,
        )
        m = match_section(s, 0)
        pad_overrides = [o for o in m.token_overrides if o.css_property == "padding"]
        assert len(pad_overrides) == 1
        assert pad_overrides[0].value == "16px 24px 16px 24px"


class TestMatchAll:
    """Test batch matching."""

    def test_matches_multiple_sections(self) -> None:
        sections = [
            _make_section(EmailSectionType.HEADER, images=[_image()]),
            _make_section(
                EmailSectionType.HERO, images=[_image()], texts=[_text("H", is_heading=True)]
            ),
            _make_section(EmailSectionType.CONTENT, texts=[_text("Body")]),
            _make_section(EmailSectionType.FOOTER),
        ]
        matches = match_all(sections)
        assert len(matches) == 4
        assert matches[0].component_slug == "logo-header"
        assert matches[1].component_slug == "hero-block"
        assert matches[2].component_slug == "text-block"
        assert matches[3].component_slug == "email-footer"

    def test_section_idx_sequential(self) -> None:
        sections = [
            _make_section(EmailSectionType.SPACER),
            _make_section(EmailSectionType.DIVIDER),
        ]
        matches = match_all(sections)
        assert matches[0].section_idx == 0
        assert matches[1].section_idx == 1

    def test_spacing_after_preserved(self) -> None:
        s = _make_section(EmailSectionType.CONTENT, texts=[_text("X")], spacing_after=24.0)
        m = match_section(s, 0)
        assert m.spacing_after == 24.0


class TestEdgeCases:
    """Test edge cases and fallbacks."""

    def test_empty_content_section_becomes_spacer(self) -> None:
        s = _make_section(EmailSectionType.CONTENT, height=50)
        m = match_section(s, 0)
        assert m.component_slug == "spacer"
        assert m.confidence < 1.0

    def test_html_escape_in_slot_fills(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("<script>alert(1)</script>", is_heading=True)],
        )
        m = match_section(s, 0)
        heading_fill = next(f for f in m.slot_fills if f.slot_id == "heading")
        assert "<script>" not in heading_fill.value
        assert "&lt;script&gt;" in heading_fill.value


class TestNavSlotFills:
    """Test navigation-bar slot fill generation."""

    def test_nav_with_buttons(self) -> None:
        """Buttons become nav links."""
        s = _make_section(
            EmailSectionType.NAV,
            buttons=[_button("Melbourne"), _button("Amsterdam"), _button("Seoul")],
            texts=[_text("Stores (LaB)", is_heading=True)],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "nav_links" in fills_by_id
        assert "Melbourne" in fills_by_id["nav_links"].value
        assert "Amsterdam" in fills_by_id["nav_links"].value
        assert "Seoul" in fills_by_id["nav_links"].value

    def test_nav_with_texts_fallback(self) -> None:
        """When no buttons, body texts become nav links."""
        s = _make_section(
            EmailSectionType.NAV,
            texts=[_text("Home"), _text("About"), _text("Contact")],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "nav_links" in fills_by_id
        assert "Home" in fills_by_id["nav_links"].value

    def test_nav_with_all_headings_fallback(self) -> None:
        """When all texts are headings, they still become nav links."""
        s = _make_section(
            EmailSectionType.NAV,
            texts=[
                _text("Man", is_heading=True),
                _text("Woman", is_heading=True),
                _text("Accessories", is_heading=True),
            ],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "nav_links" in fills_by_id
        assert "Man" in fills_by_id["nav_links"].value
        assert "Accessories" in fills_by_id["nav_links"].value

    def test_nav_empty_section(self) -> None:
        """Empty NAV section produces no fills."""
        s = _make_section(EmailSectionType.NAV)
        m = match_section(s, 0)
        assert m.slot_fills == []

    def test_nav_links_are_anchor_tags(self) -> None:
        """Nav links are rendered as <a> tags with navbar-link class."""
        s = _make_section(
            EmailSectionType.NAV,
            buttons=[_button("Products")],
        )
        m = match_section(s, 0)
        nav_fill = next(f for f in m.slot_fills if f.slot_id == "nav_links")
        assert '<a class="navbar-link"' in nav_fill.value
        assert "Products" in nav_fill.value

    def test_nav_html_escape(self) -> None:
        """Nav link text is HTML-escaped."""
        s = _make_section(
            EmailSectionType.NAV,
            buttons=[_button("A&B <Co>")],
        )
        m = match_section(s, 0)
        nav_fill = next(f for f in m.slot_fills if f.slot_id == "nav_links")
        assert "A&amp;B &lt;Co&gt;" in nav_fill.value


class TestFooterSlotFills:
    """Test email-footer slot fill generation."""

    def test_footer_with_texts(self) -> None:
        """Footer texts become footer_content with bare text and br separators."""
        s = _make_section(
            EmailSectionType.FOOTER,
            texts=[
                _text("Contact Us  Instagram  Facebook"),
                _text("You can unsubscribe here"),
            ],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "footer_content" in fills_by_id
        assert "<p " not in fills_by_id["footer_content"].value
        assert "Contact Us" in fills_by_id["footer_content"].value
        assert "unsubscribe" in fills_by_id["footer_content"].value

    def test_footer_empty_section(self) -> None:
        """Empty FOOTER section produces no fills."""
        s = _make_section(EmailSectionType.FOOTER)
        m = match_section(s, 0)
        assert m.slot_fills == []

    def test_footer_html_escape(self) -> None:
        """Footer text is HTML-escaped."""
        s = _make_section(
            EmailSectionType.FOOTER,
            texts=[_text("© 2026 A&B Corp")],
        )
        m = match_section(s, 0)
        footer_fill = next(f for f in m.slot_fills if f.slot_id == "footer_content")
        assert "A&amp;B Corp" in footer_fill.value


class TestTinyIconHeuristic:
    """Test that content sections with only tiny icons → navigation-bar."""

    def test_tiny_icons_with_text_becomes_nav(self) -> None:
        """6 category texts + 6 tiny 20x20 icons → navigation-bar, not article-card."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                _text("Man", is_heading=True),
                _text("Woman", is_heading=True),
                _text("Accessories", is_heading=True),
            ],
            images=[
                _image("i1", "arrow", 20, 20),
                _image("i2", "arrow", 20, 20),
                _image("i3", "arrow", 20, 20),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "navigation-bar"
        assert m.confidence == 0.9

    def test_large_images_with_text_remains_article_card(self) -> None:
        """Normal-sized images + text still → article-card."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True)],
            images=[_image("i1", "photo", 300, 200)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"

    def test_mixed_icon_sizes_two_images_becomes_image_grid(self) -> None:
        """Two images (mixed sizes) with text → image-grid (multi-candidate scoring)."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True)],
            images=[
                _image("i1", "arrow", 20, 20),
                _image("i2", "photo", 300, 200),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "image-grid"

    def test_icon_threshold_boundary(self) -> None:
        """Single image exactly at 30px threshold + 1 text → col-icon (more specific)."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Link")],
            images=[_image("i1", "icon", 30, 30)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "col-icon"

    def test_icon_just_above_threshold(self) -> None:
        """Images at 31px exceed nav-icon threshold but still match col-icon (<=64px)."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title")],
            images=[_image("i1", "img", 31, 31)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "col-icon"

    def test_image_above_col_icon_threshold(self) -> None:
        """Images at 65px exceed col-icon threshold → article-card."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title")],
            images=[_image("i1", "img", 65, 65)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"


# ── Phase 38.6 Bug Fix Tests ──


class TestSemanticColumnHTML:
    """Bug 51: Column fills should produce structured HTML, not raw text."""

    def test_column_fill_html_heading_in_td(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            texts=[
                TextBlock(node_id="t1", content="Product title", is_heading=True, font_size=18.0)
            ],
        )
        result = _build_column_fill_html(group)
        assert "<h3" not in result
        assert "<td" in result
        assert "Product title" in result
        assert "font-size:18px" in result
        assert "font-weight:bold" in result

    def test_column_fill_html_body_text_in_td(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            texts=[TextBlock(node_id="t1", content="Description text")],
        )
        result = _build_column_fill_html(group)
        assert "<p " not in result
        assert "<td" in result
        assert "Description text" in result

    def test_column_fill_html_button_as_anchor(self) -> None:
        """Bug 49: Buttons must render as <a> elements, not plain text."""
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            buttons=[ButtonElement(node_id="b1", text="SHOP NOW", fill_color="#FF5500")],
        )
        result = _build_column_fill_html(group)
        assert "<a " in result
        assert "SHOP NOW" in result
        assert "background-color:#FF5500" in result

    def test_column_fill_html_preserves_text_color(self) -> None:
        """Bug 50: Text color from design should be applied."""
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            texts=[TextBlock(node_id="t1", content="White text", text_color="#FFFFFF")],
        )
        result = _build_column_fill_html(group)
        assert "color:#FFFFFF" in result

    def test_column_fill_strips_placeholder_text(self) -> None:
        """Bug 54: Placeholder text must not appear in output."""
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            texts=[
                TextBlock(node_id="t1", content="Image caption — describe the image"),
                TextBlock(node_id="t2", content="Real content"),
            ],
        )
        result = _build_column_fill_html(group)
        assert "describe the image" not in result
        assert "Real content" in result


class TestTextColorOverrides:
    """Bug 50: Text color should propagate through token overrides."""

    def test_heading_color_override(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                TextBlock(node_id="t1", content="Title", is_heading=True, text_color="#FFFFFF"),
            ],
        )
        m = match_section(s, 0)
        color_overrides = [o for o in m.token_overrides if o.css_property == "color"]
        assert len(color_overrides) >= 1
        assert color_overrides[0].value == "#FFFFFF"

    def test_body_color_override(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                TextBlock(node_id="t1", content="Body", text_color="#AABBCC"),
            ],
        )
        m = match_section(s, 0)
        color_overrides = [o for o in m.token_overrides if o.css_property == "color"]
        assert any(o.value == "#AABBCC" for o in color_overrides)


class TestArticleCardGuard:
    """Bug 52: Sections with >2 images or column groups should NOT match article-card."""

    def test_many_images_becomes_image_gallery(self) -> None:
        """3+ images → image-gallery (not article-card or image-grid)."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title")],
            images=[_image("i1", "p1"), _image("i2", "p2"), _image("i3", "p3")],
        )
        m = match_section(s, 0)
        assert m.component_slug != "article-card"
        assert m.component_slug == "image-gallery"

    def test_column_groups_not_article_card(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title")],
            images=[_image()],
            column_groups=[
                ColumnGroup(column_idx=1, node_id="c1", node_name="Col 1"),
                ColumnGroup(column_idx=2, node_id="c2", node_name="Col 2"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug != "article-card"


class TestMultiParagraphBody:
    """Bug 53 / RC-D-prime: multi-text bodies render one <td> anchor per node."""

    def test_multiple_body_paragraphs(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                _text("Heading", is_heading=True),
                _text("First paragraph"),
                _text("Second paragraph"),
            ],
        )
        m = match_section(s, 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert "<p " not in body.value
        assert body.value.count("<td data-node-id=") == 2
        assert "First paragraph" in body.value
        assert "Second paragraph" in body.value

    def test_article_card_multi_paragraph(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                _text("Title", is_heading=True),
                _text("Para 1"),
                _text("Para 2"),
            ],
            images=[_image()],
        )
        m = match_section(s, 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body_text")
        assert "<p " not in body.value
        assert "Para 1" in body.value
        assert "Para 2" in body.value
        assert "<br><br>" in body.value


class TestPerNodeTypography:
    """RC-D-prime (phase-52.4b): every body text node keeps its own typography."""

    @staticmethod
    def _two_body_section() -> EmailSection:
        return _make_section(
            EmailSectionType.CONTENT,
            texts=[
                TextBlock(node_id="h1", content="Heading", is_heading=True),
                TextBlock(
                    node_id="p1",
                    content="First paragraph",
                    font_family="Georgia",
                    font_size=18.0,
                    font_weight=700,
                    line_height=24.0,
                    text_color="#111111",
                ),
                TextBlock(
                    node_id="p2",
                    content="Second paragraph",
                    font_family="Arial",
                    font_size=14.0,
                    font_weight=400,
                    line_height=20.0,
                    text_color="#666666",
                ),
            ],
        )

    def test_per_node_anchors_carry_distinct_node_ids(self) -> None:
        m = match_section(self._two_body_section(), 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert '<td data-node-id="p1"' in body.value
        assert '<td data-node-id="p2"' in body.value
        assert "<br><br>" not in body.value

    def test_per_node_overrides_carry_each_nodes_typography(self) -> None:
        m = match_section(self._two_body_section(), 0)
        by_target: dict[str, dict[str, str]] = {}
        for o in m.token_overrides:
            by_target.setdefault(o.target_class, {})[o.css_property] = o.value
        assert by_target["_text_p1"] == {
            "font-family": "Georgia",
            "font-size": "18.0px",
            "color": "#111111",
            "font-weight": "700",
            "line-height": "24px",
        }
        assert by_target["_text_p2"] == {
            "font-family": "Arial",
            "font-size": "14.0px",
            "color": "#666666",
            "font-weight": "400",
            "line-height": "20px",
        }

    def test_single_body_text_keeps_plain_fill(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                _text("Heading", is_heading=True),
                _text("Only paragraph"),
            ],
        )
        m = match_section(s, 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert body.value == "Only paragraph"
        assert not any(o.target_class.startswith("_text_") for o in m.token_overrides)

    def test_partial_padding_emits_per_side_longhands(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Hello")],
            padding_top=24.0,
            padding_bottom=32.0,
        )
        m = match_section(s, 0)
        cell = [(o.css_property, o.value) for o in m.token_overrides if o.target_class == "_cell"]
        assert cell == [("padding-top", "24px"), ("padding-bottom", "32px")]

    def test_full_padding_keeps_shorthand(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Hello")],
            padding_top=10.0,
            padding_right=20.0,
            padding_bottom=30.0,
            padding_left=40.0,
        )
        m = match_section(s, 0)
        cell = [(o.css_property, o.value) for o in m.token_overrides if o.target_class == "_cell"]
        assert cell == [("padding", "10px 20px 30px 40px")]


class TestPlaceholderSuppression:
    """Bug 54: Placeholder text must be filtered out."""

    def test_placeholder_filtered_from_body(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[
                _text("Heading", is_heading=True),
                _text("Your text here"),
                _text("Real content"),
            ],
        )
        m = match_section(s, 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert "Your text here" not in body.value
        assert "Real content" in body.value

    def test_is_placeholder_detection(self) -> None:
        assert _is_placeholder("Image caption — describe the image")
        assert _is_placeholder("Lorem ipsum dolor sit amet")
        assert _is_placeholder("Add your text here")
        assert not _is_placeholder("SHOP THE COLLECTION")
        assert not _is_placeholder("Eiger Nordwand Jacket")


class TestColIconSlotFills:
    """F4b (RC-F4): col-icon fills its own icon_N_url/heading_N slots, not the
    text-block heading/body slots it used to mis-route to (0/4 fill by
    construction → fakeimg + 'Feature icon' leak)."""

    def test_col_icon_emits_icon_and_heading_slots(self) -> None:
        s = _make_section(
            texts=[_text("Fast shipping")],
            images=[_image(node_id="ic1", name="truck", w=48, h=48)],
        )
        by_id = {f.slot_id: f for f in _build_slot_fills("col-icon", s, 600)}
        assert by_id["icon_1_url"].slot_type == "image"
        assert by_id["heading_1"].value == "Fast shipping"
        # NOT the old text-block mis-route slots.
        assert "heading" not in by_id
        assert "body" not in by_id


class TestButtonInTextBlock:
    """Bug 49: Buttons in text-block sections should render as CTA HTML."""

    def test_text_block_with_button(self) -> None:
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Heading", is_heading=True), _text("Body text")],
            buttons=[ButtonElement(node_id="b1", text="Shop Now", fill_color="#0066cc")],
        )
        m = match_section(s, 0)
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert "<a " in body.value
        assert "Shop Now" in body.value
        assert "background-color:#0066cc" in body.value
        # Solid-fill button (no stroke) keeps white label text and no border.
        assert "color:#ffffff" in body.value
        assert "border:" not in body.value

    def test_text_block_renders_all_buttons(self) -> None:
        """phase-53-b8-non-cta-multibutton-drop: a content/text-block section can
        carry a stacked CTA pair in one column (mammut case 10). Every button must
        render with its designed colours — not just buttons[0], and not collapsed
        to invisible white-on-white from a hardcoded color:#ffffff. RED pre-fix on
        both counts (only the first button survived; its colour was hardcoded).
        """
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Eiger Extreme", is_heading=True), _text("Body text")],
            buttons=[
                ButtonElement(
                    node_id="b1",
                    text="SHOP THE COLLECTION",
                    fill_color="#FFFFFF",
                    text_color="#010101",
                    stroke_color="#FE5219",
                    stroke_weight=1.0,
                ),
                ButtonElement(
                    node_id="b2",
                    text="DISCOVER EIGER EXTREME 6.0",
                    fill_color="#FFFFFF",
                    text_color="#010101",
                    stroke_color="#FE5219",
                    stroke_weight=1.0,
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "text-block"
        body = next(f for f in m.slot_fills if f.slot_id == "body")
        assert "SHOP THE COLLECTION" in body.value
        assert "DISCOVER EIGER EXTREME 6.0" in body.value
        assert body.value.count("<a ") == 2
        # designed colours + stroke used, not collapsed to invisible white-on-white
        assert "color:#010101" in body.value
        assert "border:1px solid #FE5219" in body.value
        assert "color:#ffffff" not in body.value


class TestURLValidation:
    """Bug 59: Button URLs must be validated."""

    def test_safe_url_allows_http(self) -> None:
        assert _safe_url("https://example.com") == "https://example.com"

    def test_safe_url_blocks_javascript(self) -> None:
        assert _safe_url("javascript:alert(1)") == "#"

    def test_safe_url_allows_relative(self) -> None:
        assert _safe_url("/path/to/page") == "/path/to/page"

    def test_safe_url_none_returns_hash(self) -> None:
        assert _safe_url(None) == "#"


class TestColorValidation:
    """Security: Color values must be validated hex."""

    def test_safe_color_valid_hex(self) -> None:
        assert _safe_color("#FF5500") == "#FF5500"
        assert _safe_color("#abc") == "#abc"

    def test_safe_color_rejects_injection(self) -> None:
        assert _safe_color("#333;position:fixed") == "#333333"

    def test_safe_color_none_returns_fallback(self) -> None:
        assert _safe_color(None) == "#333333"
        assert _safe_color(None, "#0066cc") == "#0066cc"


# ── Phase 39.6: Multi-Candidate Scoring Tests ──


class TestMultiCandidateScoring:
    """Verify multi-candidate scoring selects the correct component."""

    def test_product_grid_detection(self) -> None:
        """2+ column groups with image + text → product-grid."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title A"), _text("Title B")],
            images=[_image("i1", "p1"), _image("i2", "p2")],
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Col 1",
                    texts=[TextBlock(node_id="t1", content="Title A", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i1", node_name="p1")],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="c2",
                    node_name="Col 2",
                    texts=[TextBlock(node_id="t2", content="Title B", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i2", node_name="p2")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "product-grid"
        assert m.confidence == 0.95

    def test_product_grid_over_article_card(self) -> None:
        """Product grid (0.95) beats article-card (0.9) for mixed column content."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Prod A", is_heading=True), _text("Prod B", is_heading=True)],
            images=[_image("i1", "p1"), _image("i2", "p2")],
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Col 1",
                    texts=[TextBlock(node_id="t1", content="Prod A", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i1", node_name="p1")],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="c2",
                    node_name="Col 2",
                    texts=[TextBlock(node_id="t2", content="Prod B", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i2", node_name="p2")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "product-grid"
        assert m.component_slug != "article-card"

    def test_image_grid_two_images(self) -> None:
        """Exactly 2 images with ≤1 text → image-grid."""
        s = _make_section(
            EmailSectionType.CONTENT,
            images=[_image("i1", "p1"), _image("i2", "p2")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "image-grid"
        assert m.confidence == 0.85

    def test_image_gallery_three_plus(self) -> None:
        """3+ images with no text → image-gallery."""
        s = _make_section(
            EmailSectionType.CONTENT,
            images=[_image("i1", "a"), _image("i2", "b"), _image("i3", "c")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "image-gallery"
        assert m.confidence == 0.88

    def test_article_card_single_image_text(self) -> None:
        """1 image + text, single column → article-card at 0.9."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Heading", is_heading=True), _text("Body text")],
            images=[_image()],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"
        assert m.confidence == 0.9

    def test_category_nav_short_texts(self) -> None:
        """3+ short texts (<20 chars) → category-nav."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Shoes"), _text("Bags"), _text("Watches"), _text("Hats")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "category-nav"
        assert m.confidence == 0.7

    def test_fallback_to_text_block(self) -> None:
        """Empty content section falls back to spacer at 0.5."""
        s = _make_section(EmailSectionType.CONTENT)
        m = match_section(s, 0)
        assert m.component_slug == "spacer"
        assert m.confidence == 0.5

    def test_icon_nav_still_works(self) -> None:
        """Tiny icons + text → navigation-bar at 0.9."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Home"), _text("About")],
            images=[
                _image("i1", "icon1", 20, 20),
                _image("i2", "icon2", 20, 20),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "navigation-bar"
        assert m.confidence == 0.9


class TestSpatialColumnAssignment:
    """Column groups are used for column assignment when present."""

    def test_column_groups_fill_by_index(self) -> None:
        """Column groups fill col_1, col_2 by column_idx."""
        s = _make_section(
            EmailSectionType.CONTENT,
            column_layout=ColumnLayout.TWO_COLUMN,
            column_count=2,
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Left",
                    texts=[TextBlock(node_id="t1", content="Left content")],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="c2",
                    node_name="Right",
                    texts=[TextBlock(node_id="t2", content="Right content")],
                ),
            ],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "col_1" in fills_by_id
        assert "col_2" in fills_by_id
        assert "Left content" in fills_by_id["col_1"].value
        assert "Right content" in fills_by_id["col_2"].value

    def test_column_groups_preferred_over_roundrobin(self) -> None:
        """When column_groups exist, they are used instead of round-robin."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("A"), _text("B"), _text("C")],
            column_layout=ColumnLayout.TWO_COLUMN,
            column_count=2,
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Left",
                    texts=[
                        TextBlock(node_id="t1", content="A"),
                        TextBlock(node_id="t2", content="B"),
                    ],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="c2",
                    node_name="Right",
                    texts=[TextBlock(node_id="t3", content="C")],
                ),
            ],
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        # Both A and B in col_1 (not round-robin A→1, B→2, C→1)
        assert "A" in fills_by_id["col_1"].value
        assert "B" in fills_by_id["col_1"].value
        assert "C" in fills_by_id["col_2"].value

    def test_roundrobin_fallback_without_groups(self) -> None:
        """Without column_groups, round-robin distributes texts."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("A"), _text("B")],
            column_layout=ColumnLayout.TWO_COLUMN,
            column_count=2,
        )
        m = match_section(s, 0)
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "col_1" in fills_by_id
        assert "col_2" in fills_by_id

    def test_single_group_mixed_content_gets_editorial(self) -> None:
        """Single column_group with mixed image+text matches editorial-2."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True)],
            images=[_image()],
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Col 1",
                    texts=[TextBlock(node_id="t1", content="Title", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i1", node_name="img")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "editorial-2"


class TestSlotValidation:
    """Slot fill rate validation."""

    def test_full_fill_rate(self) -> None:
        from app.design_sync.component_matcher import SlotFill
        from app.design_sync.component_renderer import _validate_slot_fill_rate

        html = '<td data-slot="a">X</td><td data-slot="b">Y</td>'
        fills = [SlotFill("a", "val1"), SlotFill("b", "val2")]
        rate, warnings = _validate_slot_fill_rate(html, fills)
        assert rate == 1.0
        assert not warnings

    def test_low_fill_rate_warning(self) -> None:
        from app.design_sync.component_matcher import SlotFill
        from app.design_sync.component_renderer import _validate_slot_fill_rate

        html = '<td data-slot="a">X</td><td data-slot="b">Y</td><td data-slot="c">Z</td>'
        fills = [SlotFill("a", "val1")]
        rate, warnings = _validate_slot_fill_rate(html, fills)
        assert rate < 0.5
        assert len(warnings) == 1
        assert "Low slot fill rate" in warnings[0]

    def test_no_slots_template(self) -> None:
        from app.design_sync.component_renderer import _validate_slot_fill_rate

        html = "<table><tr><td>No slots here</td></tr></table>"
        rate, warnings = _validate_slot_fill_rate(html, [])
        assert rate == 1.0
        assert not warnings


class TestConfidenceInResult:
    """Confidence scores propagated through the pipeline."""

    def test_confidence_in_component_match(self) -> None:
        """Match carries the correct confidence from scoring."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Heading", is_heading=True)],
            images=[_image()],
        )
        m = match_section(s, 0)
        assert isinstance(m.confidence, float)
        assert 0.0 < m.confidence <= 1.0

    def test_confidence_varies_by_type(self) -> None:
        """Different component types get different confidence scores."""
        s_article = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Title", is_heading=True)],
            images=[_image()],
        )
        s_grid = _make_section(
            EmailSectionType.CONTENT,
            images=[_image("i1", "a"), _image("i2", "b")],
        )
        m_article = match_section(s_article, 0)
        m_grid = match_section(s_grid, 1)
        # Article-card and image-grid have different confidence values
        assert m_article.confidence != m_grid.confidence


class TestNewComponentSlotFills:
    """Slot fills for new component types."""

    def test_product_grid_slot_fills(self) -> None:
        """Product grid fills per-group slots: product_1_title, product_2_title, etc."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("A"), _text("B")],
            images=[_image("i1", "p1"), _image("i2", "p2")],
            column_groups=[
                ColumnGroup(
                    column_idx=1,
                    node_id="c1",
                    node_name="Col 1",
                    texts=[TextBlock(node_id="t1", content="Product A", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i1", node_name="p1")],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="c2",
                    node_name="Col 2",
                    texts=[TextBlock(node_id="t2", content="Product B", is_heading=True)],
                    images=[ImagePlaceholder(node_id="i2", node_name="p2")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "product-grid"
        fills_by_id = {f.slot_id: f for f in m.slot_fills}
        assert "product_1_title" in fills_by_id
        assert "product_2_title" in fills_by_id
        assert fills_by_id["product_1_title"].value == "Product A"
        assert fills_by_id["product_2_title"].value == "Product B"


class TestExpandedMatcherRules:
    """Tests for file-based component richness expansions (40.7.5)."""

    def test_hero_with_subtitle_title_emits_hero_text(self) -> None:
        """Hero with 2+ headings emits hero-text instead of hero-block."""
        s = _make_section(
            EmailSectionType.HERO,
            texts=[
                _text("Summer Collection", is_heading=True),
                _text("Shop the Latest Styles", is_heading=True),
            ],
            images=[_image()],
            buttons=[_button("Shop Now")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "hero-text"
        assert m.confidence == 1.0

    def test_hero_single_heading_emits_hero_block(self) -> None:
        """Hero with 1 heading stays as hero-block."""
        s = _make_section(
            EmailSectionType.HERO,
            texts=[_text("Big Title", is_heading=True)],
            images=[_image()],
            buttons=[_button("Shop")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "hero-block"

    def test_vertical_nav_emits_nav_hamburger(self) -> None:
        """NAV with stacked text items and no column groups → nav-hamburger."""
        s = _make_section(
            EmailSectionType.NAV,
            texts=[
                _text("Home"),
                _text("Products"),
                _text("About"),
                _text("Contact"),
            ],
            column_groups=[],
        )
        m = match_section(s, 0)
        assert m.component_slug == "nav-hamburger"
        assert m.confidence == 0.95

    def test_horizontal_nav_stays_navigation_bar(self) -> None:
        """NAV with fewer than 3 texts stays as navigation-bar."""
        s = _make_section(
            EmailSectionType.NAV,
            texts=[_text("Home"), _text("Products")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "navigation-bar"

    def test_editorial_two_column_with_image_and_text(self) -> None:
        """Content with 1 column group containing image+text → editorial-2."""
        s = _make_section(
            EmailSectionType.CONTENT,
            texts=[_text("Editorial body")],
            images=[_image()],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Column Group",
                    images=[_image()],
                    texts=[_text("Body text")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "editorial-2"
        assert m.confidence >= 0.9


class TestExtendedComponentScoring:
    """Tests for extended component types added in 47.6."""

    def test_countdown_timer_time_pattern(self) -> None:
        """3+ time-pattern texts + heading → countdown-timer."""
        s = _make_section(
            texts=[
                _text("Sale ends in", is_heading=True),
                _text("12:30"),
                _text("45:00"),
                _text("08:15"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "countdown-timer"
        assert m.confidence == 0.92

    def test_countdown_timer_unit_words(self) -> None:
        """Time-unit word texts + heading → countdown-timer."""
        s = _make_section(
            texts=[
                _text("Hurry!", is_heading=True),
                _text("2 Days"),
                _text("14 Hours"),
                _text("30 Minutes"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "countdown-timer"
        assert m.confidence == 0.92

    def test_testimonial_with_quote_and_avatar(self) -> None:
        """Quoted text + small avatar image → testimonial."""
        s = _make_section(
            texts=[_text("\u201cGreat service\u201d")],
            images=[_image(w=80, h=80)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "testimonial"
        assert m.confidence == 0.9

    def test_testimonial_no_avatar_stays_text(self) -> None:
        """Quoted text only, no image → falls back to text-block."""
        s = _make_section(
            texts=[_text("\u201cGreat service\u201d")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "text-block"

    def test_pricing_table_with_currency(self) -> None:
        """Currency text + 2 col_groups + buttons → pricing-table."""
        s = _make_section(
            texts=[_text("$9.99/mo"), _text("$19.99/mo")],
            buttons=[_button("Buy now")],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Plan 1",
                    images=[],
                    texts=[_text("$9.99/mo")],
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="Plan 2",
                    images=[],
                    texts=[_text("$19.99/mo")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "pricing-table"
        assert m.confidence == 0.93

    def test_video_placeholder_16_9(self) -> None:
        """1 image with 16:9 ratio + button → video-placeholder."""
        s = _make_section(
            images=[_image(w=640, h=360)],
            buttons=[_button("Play")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "video-placeholder"
        assert m.confidence == 0.88

    def test_video_wrong_ratio_not_matched(self) -> None:
        """1 image with 1:1 ratio + button → not video-placeholder."""
        s = _make_section(
            images=[_image(w=600, h=600)],
            buttons=[_button("Play")],
        )
        m = match_section(s, 0)
        assert m.component_slug != "video-placeholder"

    def test_event_card_date_pattern(self) -> None:
        """Date pattern + compact thumbnail + single CTA → event-card.

        The matcher rejects event-card when a section carries a hero-sized
        image (>=200px) or more than one button — those are hero/article
        sections, not compact event listings.
        """
        s = _make_section(
            texts=[_text("March 15, 2026"), _text("Join us for the event")],
            images=[_image(w=120, h=120)],
            buttons=[_button("Register")],
        )
        m = match_section(s, 0)
        assert m.component_slug == "event-card"
        assert m.confidence == 0.85

    def test_event_card_rejected_when_hero_image(self) -> None:
        """Hero-sized image (>=200px) disqualifies event-card (false-positive gate)."""
        s = _make_section(
            texts=[_text("March 15, 2026"), _text("Join us for the event")],
            images=[_image(w=600, h=400)],
            buttons=[_button("Register")],
        )
        m = match_section(s, 0)
        assert m.component_slug != "event-card"

    def test_event_card_rejected_when_multiple_ctas(self) -> None:
        """Two or more buttons disqualifies event-card (false-positive gate)."""
        s = _make_section(
            texts=[_text("October 15, 2026"), _text("Details inside")],
            buttons=[_button("Register"), _button("Learn more")],
        )
        m = match_section(s, 0)
        assert m.component_slug != "event-card"

    def test_faq_question_answer_pairs(self) -> None:
        """Alternating Q?/A texts, no images → text-block.

        The ``faq-accordion`` slug was a phantom (absent from
        ``component_manifest.yaml`` and from the slot-fill builders), so it
        was removed in B7. FAQ-shaped content now falls through to the base
        scorer's ``text-block``, which renders the real Q/A text.
        """
        s = _make_section(
            texts=[
                _text("What is your return policy?"),
                _text("You can return items within 30 days."),
                _text("Do you offer free shipping?"),
                _text("Yes, on orders over $50."),
                _text("How do I track my order?"),
                _text("Use the tracking link in your confirmation email."),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "text-block"

    def test_zigzag_alternating_columns(self) -> None:
        """3+ col_groups each with mixed image+text → zigzag-alternating."""
        s = _make_section(
            texts=[_text("Row 1"), _text("Row 2"), _text("Row 3")],
            images=[_image(node_id="img1"), _image(node_id="img2"), _image(node_id="img3")],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Row 1",
                    images=[_image(node_id="img1")],
                    texts=[_text("Row 1")],
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="Row 2",
                    images=[_image(node_id="img2")],
                    texts=[_text("Row 2")],
                ),
                ColumnGroup(
                    column_idx=2,
                    node_id="cg3",
                    node_name="Row 3",
                    images=[_image(node_id="img3")],
                    texts=[_text("Row 3")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "zigzag-alternating"
        assert m.confidence == 0.9

    def test_existing_product_grid_unchanged(self) -> None:
        """Regression: product-grid scoring is not affected by extended scorer."""
        s = _make_section(
            texts=[_text("Product A"), _text("Product B")],
            images=[_image(node_id="img1"), _image(node_id="img2")],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Product 1",
                    images=[_image(node_id="img1")],
                    texts=[_text("Product A")],
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="Product 2",
                    images=[_image(node_id="img2")],
                    texts=[_text("Product B")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "product-grid"
        assert m.confidence == 0.95

    def test_existing_article_card_unchanged(self) -> None:
        """Regression: article-card scoring is not affected by extended scorer."""
        s = _make_section(
            texts=[_text("Article title", is_heading=True), _text("Article body")],
            images=[_image()],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"
        assert m.confidence == 0.9


class TestClassificationImprovements:
    """Tests for 49.3 section-to-component classification fixes."""

    # ── editorial-2 false positive fix ──

    def test_single_col_image_text_not_editorial(self) -> None:
        """1 img + 2 texts + 1 wide col_group → NOT editorial-2 (stacked layout)."""
        s = _make_section(
            texts=[_text("Title", is_heading=True), _text("Body text")],
            images=[_image(w=560, h=300)],
            width=600,
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Column",
                    images=[_image(w=560, h=300)],
                    texts=[_text("Title", is_heading=True), _text("Body text")],
                    width=560,
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug != "editorial-2"

    def test_two_col_groups_is_editorial(self) -> None:
        """2 col_groups: one image-only, one text-only → editorial-2 (not product-grid)."""
        s = _make_section(
            texts=[_text("Editorial body")],
            images=[_image(node_id="img1", w=280, h=200)],
            width=600,
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Image col",
                    images=[_image(node_id="img1", w=280, h=200)],
                    texts=[],
                    width=280,
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="Text col",
                    images=[],
                    texts=[_text("Editorial body")],
                    width=280,
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "editorial-2"
        assert m.confidence == 0.92

    def test_narrow_col_group_is_editorial(self) -> None:
        """1 narrow col_group (<70% width) with img+text → editorial-2."""
        s = _make_section(
            texts=[_text("Side text")],
            images=[_image(w=200, h=200)],
            width=600,
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="Narrow col",
                    images=[_image(w=200, h=200)],
                    texts=[_text("Side text")],
                    width=250,
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "editorial-2"
        assert m.confidence == 0.92

    # ── col-icon detector ──

    def test_icon_image_matches_col_icon(self) -> None:
        """1 img 40x40 + 2 texts -> col-icon (not article-card)."""
        s = _make_section(
            texts=[_text("Feature title", is_heading=True), _text("Description")],
            images=[_image(w=40, h=40)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "col-icon"
        assert m.confidence == 0.92

    def test_large_image_still_article_card(self) -> None:
        """1 img 300x200 + 2 texts -> article-card (not col-icon)."""
        s = _make_section(
            texts=[_text("Title", is_heading=True), _text("Body")],
            images=[_image(w=300, h=200)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"
        assert m.confidence == 0.9

    # ── full-width-image vs image-block ──

    def test_full_width_image_content_section(self) -> None:
        """1 img 600x400 + 0 texts, section_width=600 -> full-width-image."""
        s = _make_section(
            images=[_image(w=600, h=400)],
            width=600,
        )
        m = match_section(s, 0)
        assert m.component_slug == "full-width-image"
        assert m.confidence == 1.0

    def test_small_image_stays_image_block(self) -> None:
        """1 img 200x150 + 0 texts, section_width=600 -> image-block."""
        s = _make_section(
            images=[_image(w=200, h=150)],
            width=600,
        )
        m = match_section(s, 0)
        assert m.component_slug == "image-block"
        assert m.confidence == 1.0

    # ── event-card improvements ──

    def test_event_card_keyword_labels(self) -> None:
        """3 short texts 'Date: ...', 'Time: ...', 'Location: ...' → event-card."""
        s = _make_section(
            texts=[
                _text("Annual Conference", is_heading=True),
                _text("Date: October 15, 2026"),
                _text("Time: 9:00 AM"),
                _text("Location: Convention Center"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "event-card"

    def test_event_card_date_regex_no_images(self) -> None:
        """Texts with 'October 23, 2025' + no images → event-card."""
        s = _make_section(
            texts=[
                _text("Join us October 23, 2025"),
                _text("A special gathering"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "event-card"
        assert m.confidence == 0.85

    def test_event_card_time_pattern(self) -> None:
        """Texts with '9:30am', '6:30pm' keywords → event-card via keyword path."""
        s = _make_section(
            texts=[
                _text("Workshop Details", is_heading=True),
                _text("When: Saturday"),
                _text("Time: 9:30am - 6:30pm"),
                _text("Where: Room 101"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "event-card"

    def test_non_event_short_texts(self) -> None:
        """3 short texts without event keywords → NOT event-card."""
        s = _make_section(
            texts=[
                _text("Shop the look"),
                _text("New arrivals"),
                _text("Best sellers"),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug != "event-card"

    # ── Regressions ──

    def test_editorial_regression_real_two_col(self) -> None:
        """Real 2-col (2 col_groups, each img+text) → editorial-2 unchanged."""
        s = _make_section(
            texts=[_text("A"), _text("B")],
            images=[_image(node_id="i1", w=280, h=200), _image(node_id="i2", w=280, h=200)],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="L",
                    images=[_image(node_id="i1", w=280, h=200)],
                    texts=[_text("A")],
                    width=280,
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="R",
                    images=[_image(node_id="i2", w=280, h=200)],
                    texts=[_text("B")],
                    width=280,
                ),
            ],
        )
        m = match_section(s, 0)
        # product-grid (0.95) beats editorial-2 (0.92) when 2+ mixed col_groups
        assert m.component_slug == "product-grid"
        assert m.confidence == 0.95

    def test_article_card_regression(self) -> None:
        """1 large img + text + 0 col_groups → article-card unchanged."""
        s = _make_section(
            texts=[_text("Article"), _text("Description")],
            images=[_image(w=300, h=200)],
        )
        m = match_section(s, 0)
        assert m.component_slug == "article-card"
        assert m.confidence == 0.9

    def test_product_grid_regression(self) -> None:
        """2+ col_groups mixed → product-grid unchanged."""
        s = _make_section(
            texts=[_text("P1"), _text("P2")],
            images=[_image(node_id="i1"), _image(node_id="i2")],
            column_groups=[
                ColumnGroup(
                    column_idx=0,
                    node_id="cg1",
                    node_name="P1",
                    images=[_image(node_id="i1")],
                    texts=[_text("P1")],
                ),
                ColumnGroup(
                    column_idx=1,
                    node_id="cg2",
                    node_name="P2",
                    images=[_image(node_id="i2")],
                    texts=[_text("P2")],
                ),
            ],
        )
        m = match_section(s, 0)
        assert m.component_slug == "product-grid"
        assert m.confidence == 0.95

    def test_col_icon_vs_testimonial(self) -> None:
        """1 small img + quoted text → col-icon (0.92) beats testimonial (0.9)."""
        s = _make_section(
            texts=[_text("\u201cGreat feature\u201d")],
            images=[_image(w=48, h=48)],
        )
        m = match_section(s, 0)
        # col-icon 0.92 in extended scorer overrides base
        assert m.component_slug == "col-icon"
        assert m.confidence == 0.92

    def test_content_roles_populated(self) -> None:
        """Section with icon+text → content_roles includes 'text-with-icon'."""
        from app.design_sync.figma.layout_analyzer import _compute_content_roles

        roles = _compute_content_roles(
            texts=[_text("Feature title"), _text("Description")],
            images=[_image(w=40, h=40)],
            buttons=[],
        )
        assert "text-with-icon" in roles


class TestFillsSocial:
    """`_fills_social` must resolve icon node ids through ``image_urls``.

    Regression: previously ``ButtonElement.icon_url`` stored a Figma node id,
    which got rendered directly into ``<img src="2833:1172" ...>``.
    """

    def test_fills_social_resolves_icon_node_id_via_image_urls(self) -> None:
        from app.design_sync.component_matcher import _fills_social

        section = _make_section(
            EmailSectionType.FOOTER,
            buttons=[
                ButtonElement(
                    node_id="btn_1",
                    text="Twitter",
                    url="https://twitter.com/acme",
                    icon_node_id="icon_42",
                ),
            ],
        )
        image_urls = {"icon_42": "https://cdn.example.com/icons/twitter.png"}
        fills = _fills_social(section, 600, image_urls=image_urls)
        assert len(fills) == 1
        row = fills[0].value
        assert "https://cdn.example.com/icons/twitter.png" in row
        assert "icon_42" not in row

    def test_fills_social_does_not_emit_raw_node_id_in_src(self) -> None:
        from app.design_sync.component_matcher import _fills_social

        section = _make_section(
            EmailSectionType.FOOTER,
            buttons=[
                ButtonElement(
                    node_id="btn_1",
                    text="Twitter",
                    url="https://twitter.com/acme",
                    icon_node_id="2833:1172",
                ),
            ],
        )
        fills = _fills_social(section, 600, image_urls=None)
        assert fills == [] or '"2833:1172"' not in fills[0].value


class TestDeriveImageAlt:
    """Phase 53 B5 — alt derivation stops the Figma layer-name leak.

    Every emitted alt must clear the G3-neg golden-conformance gate: never
    empty, never a lone generic token, never MJML internals or a raw node-id.
    """

    @staticmethod
    def _img(name: str) -> ImagePlaceholder:
        return ImagePlaceholder(node_id="n1", node_name=name)

    def test_descriptive_name_kept_verbatim(self) -> None:
        for good in ("Gallery image 1", "Article image", "Full width image", "LEGO hero"):
            assert _derive_image_alt(self._img(good)) == good
            assert _is_descriptive_alt(good)

    def test_mjml_internal_leak_becomes_placeholder(self) -> None:
        assert _derive_image_alt(self._img("mj-image")) == "Content image"
        assert _derive_image_alt(self._img("mj-image, (mjml:mj-image)")) == "Content image"
        assert not _is_descriptive_alt("mj-image")

    def test_logo_typed_leak_becomes_company_logo(self) -> None:
        leak = "mj-image, (mjml:mj-image), (type: logo)"
        assert _derive_image_alt(self._img(leak)) == "Company logo"

    def test_empty_and_nodeid_become_placeholder(self) -> None:
        assert _derive_image_alt(self._img("")) == "Content image"
        assert _derive_image_alt(self._img("2833:1869")) == "Content image"
        assert not _is_descriptive_alt("")
        assert not _is_descriptive_alt("2833:1869")

    def test_no_derived_alt_trips_g3neg(self) -> None:
        # The G3-neg forbidden set: empty or a lone generic token.
        forbidden = {
            "",
            "image",
            "photo",
            "picture",
            "img",
            "mj-image",
            "mj-text",
            "frame",
            "banner",
        }
        for name in ("mj-image", "(type: logo)", "", "2833:1869", "Gallery image 1"):
            alt = _derive_image_alt(self._img(name))
            assert alt.lower() not in forbidden
