# pyright: reportPrivateUsage=false
"""Tests for converter fixes B1-B4 (recursive converter improvements)."""

from __future__ import annotations

from app.design_sync.converter import (
    _calculate_column_widths,
    _has_visible_content,
    _is_inline_row,
    node_to_email_html,
)
from app.design_sync.protocol import DesignNode, DesignNodeType
from app.design_sync.render_context import RenderContext

# ---------------------------------------------------------------------------
# B3: _has_visible_content — empty subtree pruning
# ---------------------------------------------------------------------------


class TestHasVisibleContent:
    def test_text_node_is_visible(self) -> None:
        node = DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Hi")
        assert _has_visible_content(node) is True

    def test_image_node_is_visible(self) -> None:
        node = DesignNode(id="i1", name="I", type=DesignNodeType.IMAGE, width=100, height=50)
        assert _has_visible_content(node) is True

    def test_empty_frame_is_not_visible(self) -> None:
        node = DesignNode(id="f1", name="F", type=DesignNodeType.FRAME, children=[])
        assert _has_visible_content(node) is False

    def test_frame_with_no_children_attr(self) -> None:
        node = DesignNode(id="f1", name="F", type=DesignNodeType.FRAME)
        assert _has_visible_content(node) is False

    def test_nested_text_is_visible(self) -> None:
        inner = DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="X")
        outer = DesignNode(id="f1", name="F", type=DesignNodeType.FRAME, children=[inner])
        assert _has_visible_content(outer) is True

    def test_deeply_nested_image_is_visible(self) -> None:
        img = DesignNode(id="i1", name="I", type=DesignNodeType.IMAGE, width=10, height=10)
        mid = DesignNode(id="f2", name="F2", type=DesignNodeType.GROUP, children=[img])
        outer = DesignNode(id="f1", name="F1", type=DesignNodeType.FRAME, children=[mid])
        assert _has_visible_content(outer) is True

    def test_nested_empty_frames_not_visible(self) -> None:
        inner = DesignNode(id="f2", name="F2", type=DesignNodeType.FRAME, children=[])
        outer = DesignNode(id="f1", name="F1", type=DesignNodeType.FRAME, children=[inner])
        assert _has_visible_content(outer) is False


class TestEmptyFramePruningService:
    """B3: Empty frames behave consistently in the modern document path."""

    # `test_empty_frame_pruned_from_conversion` was deleted in 08c part 2.
    # It asserted the legacy `_collect_frames`-based "No frames found" warning
    # on an empty FRAME. Under the modern document path, an empty FRAME still
    # matches a section template, so the empty-frame branch is exercised
    # higher up (in `from_legacy`'s section dropping) and isn't observable
    # via this kind of integration test.

    def test_visible_frame_kept(self) -> None:
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.email_design_document import EmailDesignDocument
        from app.design_sync.protocol import DesignFileStructure, ExtractedTokens

        structure = DesignFileStructure(
            file_name="test.fig",
            pages=[
                DesignNode(
                    id="page",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Section",
                            type=DesignNodeType.FRAME,
                            width=600,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="T",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        assert result.sections_count >= 1
        assert "Hello" in result.html


# ---------------------------------------------------------------------------
# B2: _is_inline_row — inline content heuristic
# ---------------------------------------------------------------------------


class TestIsInlineRow:
    def test_text_and_small_image(self) -> None:
        children = [
            DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Nav"),
            DesignNode(id="i1", name="Icon", type=DesignNodeType.IMAGE, width=16, height=16),
        ]
        assert _is_inline_row(children) is True

    def test_two_texts(self) -> None:
        children = [
            DesignNode(id="t1", name="A", type=DesignNodeType.TEXT, text_content="A"),
            DesignNode(id="t2", name="B", type=DesignNodeType.TEXT, text_content="B"),
        ]
        assert _is_inline_row(children) is True

    def test_large_image_not_inline(self) -> None:
        children = [
            DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Label"),
            DesignNode(id="i1", name="Big", type=DesignNodeType.IMAGE, width=200, height=100),
        ]
        assert _is_inline_row(children) is False

    def test_single_child_not_inline(self) -> None:
        children = [
            DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Solo"),
        ]
        assert _is_inline_row(children) is False

    def test_five_children_not_inline(self) -> None:
        children = [
            DesignNode(id=f"t{i}", name=f"T{i}", type=DesignNodeType.TEXT, text_content=f"T{i}")
            for i in range(5)
        ]
        assert _is_inline_row(children) is False

    def test_frames_not_inline(self) -> None:
        children = [
            DesignNode(id="f1", name="F1", type=DesignNodeType.FRAME, width=200),
            DesignNode(id="f2", name="F2", type=DesignNodeType.FRAME, width=200),
        ]
        assert _is_inline_row(children) is False

    def test_image_at_boundary_30px(self) -> None:
        children = [
            DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Nav"),
            DesignNode(id="i1", name="Icon", type=DesignNodeType.IMAGE, width=30, height=30),
        ]
        assert _is_inline_row(children) is True

    def test_image_just_over_boundary(self) -> None:
        children = [
            DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Nav"),
            DesignNode(id="i1", name="Icon", type=DesignNodeType.IMAGE, width=31, height=16),
        ]
        assert _is_inline_row(children) is False


class TestInlineRowRendering:
    """B2: Inline rows render as single <td> without ghost table overhead."""

    def test_inline_row_no_ghost_table(self) -> None:
        parent = DesignNode(
            id="nav",
            name="Nav Item",
            type=DesignNodeType.FRAME,
            width=200,
            height=30,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id="t1", name="Label", type=DesignNodeType.TEXT, text_content="Man", y=0
                ),
                DesignNode(
                    id="i1",
                    name="Arrow",
                    type=DesignNodeType.IMAGE,
                    width=16,
                    height=16,
                    y=0,
                ),
            ],
        )
        html = node_to_email_html(parent)
        # TEXT rendered as <span> with font styles (not <td><p>)
        assert "<span" in html
        assert "Man" in html
        # IMAGE rendered as inline <img> (not ghost table column)
        assert "<img" in html
        assert "Arrow" in html
        # No <p> tags — inline content uses <span> for text
        assert "<p " not in html
        # No MSO ghost table
        assert "<!--[if mso]>" not in html

    def test_inline_text_has_font_styles(self) -> None:
        parent = DesignNode(
            id="nav",
            name="Nav",
            type=DesignNodeType.FRAME,
            width=200,
            height=30,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Click", y=0),
                DesignNode(
                    id="i1", name="Icon", type=DesignNodeType.IMAGE, width=12, height=12, y=0
                ),
            ],
        )
        html = node_to_email_html(parent)
        # Text <span> should have font-family on parent <td>
        assert "font-family:" in html
        # Structure: <td> wraps all inline children — no nested <td>
        assert html.count("<td") >= 1
        assert "<td><td" not in html.replace(" ", "").replace("\n", "")


# ---------------------------------------------------------------------------
# B4: Sparse layout detection in _calculate_column_widths
# ---------------------------------------------------------------------------


class TestSparseColumnWidths:
    def test_sparse_keeps_natural_widths(self) -> None:
        """3 x 80px buttons in 600px -> sparse (240/600=40%) -> keep natural widths."""
        children = [
            DesignNode(id=f"c{i}", name=f"C{i}", type=DesignNodeType.FRAME, width=80)
            for i in range(3)
        ]
        widths = _calculate_column_widths(children, 600)
        assert widths == [80, 80, 80]

    def test_not_sparse_redistributes(self) -> None:
        """200+400 in 600px → 100% → NOT sparse → proportional redistribution."""
        children = [
            DesignNode(id="c1", name="A", type=DesignNodeType.FRAME, width=200, height=100),
            DesignNode(id="c2", name="B", type=DesignNodeType.FRAME, width=400, height=100),
        ]
        widths = _calculate_column_widths(children, 600)
        assert widths[0] == 200
        assert widths[1] == 400

    def test_threshold_boundary_59_percent(self) -> None:
        """Total = 59% of container → sparse (< 60%)."""
        children = [
            DesignNode(id="c1", name="A", type=DesignNodeType.FRAME, width=177),
            DesignNode(id="c2", name="B", type=DesignNodeType.FRAME, width=177),
        ]
        # 354 / 600 = 59% < 60% → sparse
        widths = _calculate_column_widths(children, 600)
        assert widths == [177, 177]

    def test_threshold_boundary_61_percent(self) -> None:
        """Total = 61% of container → NOT sparse (> 60%)."""
        children = [
            DesignNode(id="c1", name="A", type=DesignNodeType.FRAME, width=183),
            DesignNode(id="c2", name="B", type=DesignNodeType.FRAME, width=183),
        ]
        # 366 / 600 = 61% > 60% → NOT sparse → proportional redistribution
        widths = _calculate_column_widths(children, 600)
        assert sum(widths) == 600

    def test_unknown_widths_not_affected(self) -> None:
        """Children with no widths → equal distribution (sparse check N/A)."""
        children = [
            DesignNode(id=f"c{i}", name=f"C{i}", type=DesignNodeType.FRAME) for i in range(3)
        ]
        widths = _calculate_column_widths(children, 600)
        assert sum(widths) == 600


# ---------------------------------------------------------------------------
# B1: Table wrapper replaces div wrapper in multi-column
# ---------------------------------------------------------------------------


class TestTableColumnWrapper:
    """38.7: Multi-column uses <div class="column"> matching golden components."""

    def test_column_uses_div_not_table(self) -> None:
        parent = DesignNode(
            id="frame1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            height=200,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id="c1", name="A", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
                DesignNode(
                    id="c2", name="B", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
            ],
        )
        html = node_to_email_html(parent)
        # 38.7: golden pattern uses <div class="column"> for mobile stacking
        assert '<div class="column"' in html
        assert '<table class="column"' not in html

    def test_column_has_inline_block(self) -> None:
        parent = DesignNode(
            id="frame1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            height=200,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id="c1", name="A", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
                DesignNode(
                    id="c2", name="B", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
            ],
        )
        html = node_to_email_html(parent)
        assert "display:inline-block" in html

    def test_mso_ghost_table_still_present(self) -> None:
        parent = DesignNode(
            id="frame1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            height=200,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id="c1", name="A", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
                DesignNode(
                    id="c2", name="B", type=DesignNodeType.FRAME, width=300, height=200, y=0
                ),
            ],
        )
        html = node_to_email_html(parent)
        assert "<!--[if mso]>" in html
        assert "<![endif]-->" in html

    def test_no_double_table_nesting(self) -> None:
        """38.7: div wrapper + single inner table per column."""
        parent = DesignNode(
            id="frame1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            height=200,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id="c1",
                    name="A",
                    type=DesignNodeType.FRAME,
                    width=300,
                    height=200,
                    y=0,
                    children=[
                        DesignNode(
                            id="t1",
                            name="Text",
                            type=DesignNodeType.TEXT,
                            text_content="Col 1",
                        ),
                    ],
                ),
                DesignNode(
                    id="c2",
                    name="B",
                    type=DesignNodeType.FRAME,
                    width=300,
                    height=200,
                    y=0,
                    children=[
                        DesignNode(
                            id="t2",
                            name="Text",
                            type=DesignNodeType.TEXT,
                            text_content="Col 2",
                        ),
                    ],
                ),
            ],
        )
        html = node_to_email_html(parent)
        # Count tables: parent(1) + padding wrapper(1) + 2 inner column tables + 2 child frames = 6
        # (div wrapper replaces table wrapper — same table count)
        table_count = html.count("<table")
        assert table_count <= 6


# ── Phase 38.4 Tests ──


class TestDuplicateButtonMsoConditional:
    """Bug 22: Button must not render both VML and HTML in non-MSO clients."""

    def test_button_has_mso_conditional(self) -> None:
        parent = DesignNode(
            id="btn1",
            name="CTA",
            type=DesignNodeType.FRAME,
            width=200,
            height=50,
            children=[
                DesignNode(
                    id="t1",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Click me",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        # VML for Outlook
        assert "<!--[if mso]>" in html
        assert "v:roundrect" in html
        # HTML for non-MSO, wrapped in conditional
        assert "<!--[if !mso]><!-->" in html
        assert "<!--<![endif]-->" in html
        # Only one <a> tag — the HTML button
        assert html.count("<a ") == 1

    def test_vml_stroke_is_false(self) -> None:
        """Bug 27: VML stroke attribute must be proper XML value."""
        parent = DesignNode(
            id="btn1",
            name="CTA",
            type=DesignNodeType.FRAME,
            width=200,
            height=50,
            children=[
                DesignNode(
                    id="t1",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Click me",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert 'stroke="false"' in html
        assert 'stroke="f"' not in html


# ── Phase 39.1 Tests: Enriched field rendering ──


class TestButtonEnrichedFields:
    """39.1: Button rendering uses corner_radius and hyperlink from DesignNode."""

    def test_button_uses_corner_radius(self) -> None:
        parent = DesignNode(
            id="btn1",
            name="CTA",
            type=DesignNodeType.FRAME,
            width=200,
            height=48,
            corner_radius=8.0,
            children=[
                DesignNode(
                    id="t1",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Click me",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert "border-radius:8px" in html
        # VML arcsize should use 8px not 4px
        # arcsize = round(8/48*100) = 17%
        assert 'arcsize="17%"' in html

    def test_button_uses_hyperlink(self) -> None:
        parent = DesignNode(
            id="btn1",
            name="CTA",
            type=DesignNodeType.FRAME,
            width=200,
            height=48,
            hyperlink="https://example.com/shop",
            children=[
                DesignNode(
                    id="t1",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Shop Now",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert 'href="https://example.com/shop"' in html
        assert 'href="#"' not in html

    def test_button_default_href_when_no_hyperlink(self) -> None:
        """Backward compat: no hyperlink → still gets href='#'."""
        parent = DesignNode(
            id="btn1",
            name="CTA",
            type=DesignNodeType.FRAME,
            width=200,
            height=48,
            children=[
                DesignNode(
                    id="t1",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Click",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert 'href="#"' in html


class TestBorderFromStroke:
    """39.1: Frame stroke_weight + stroke_color → CSS border."""

    def test_border_from_stroke(self) -> None:
        parent = DesignNode(
            id="card1",
            name="Card",
            type=DesignNodeType.FRAME,
            width=300,
            height=200,
            stroke_weight=1.0,
            stroke_color="#E0E0E0",
            children=[
                DesignNode(
                    id="t1",
                    name="Title",
                    type=DesignNodeType.TEXT,
                    text_content="Product",
                    font_size=16.0,
                ),
            ],
        )
        html = node_to_email_html(parent)
        assert "border:1px solid #E0E0E0" in html


class TestTextAlignCSS:
    """39.1: Text alignment from design → CSS text-align."""

    def test_text_align_center_css(self) -> None:
        node = DesignNode(
            id="t1",
            name="Centered",
            type=DesignNodeType.TEXT,
            text_content="Center me",
            text_align="center",
        )
        html = node_to_email_html(node)
        assert "text-align:center" in html


class TestStyleRunsRendering:
    """39.1: Style runs → inline HTML tags."""

    def test_style_runs_render_bold(self) -> None:
        from app.design_sync.converter import _render_style_runs
        from app.design_sync.protocol import StyleRun

        result = _render_style_runs("Hello Bold", (StyleRun(start=6, end=10, bold=True),))
        assert "<strong>Bold</strong>" in result
        assert "Hello " in result

    def test_style_runs_render_link(self) -> None:
        from app.design_sync.converter import _render_style_runs
        from app.design_sync.protocol import StyleRun

        result = _render_style_runs(
            "Click here now",
            (StyleRun(start=6, end=10, link_url="https://example.com"),),
        )
        assert 'href="https://example.com"' in result
        assert ">here</a>" in result

    def test_style_runs_escapes_content(self) -> None:
        from app.design_sync.converter import _render_style_runs
        from app.design_sync.protocol import StyleRun

        result = _render_style_runs(
            "<script>alert(1)</script>",
            (StyleRun(start=0, end=25, bold=True),),
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestBackgroundImageRendering:
    """38.8: FRAME with image_ref renders CSS background-image + VML."""

    def test_frame_with_image_ref_renders_background(self) -> None:
        """FRAME with image_ref + children → CSS background-image on table."""
        child = DesignNode(id="t1", name="Overlay", type=DesignNodeType.TEXT, text_content="Hello")
        parent = DesignNode(
            id="f1",
            name="Hero",
            type=DesignNodeType.FRAME,
            width=600,
            height=400,
            image_ref="https://example.com/hero.jpg",
            children=[child],
        )
        html = node_to_email_html(parent)
        assert "background-image:url('https://example.com/hero.jpg')" in html
        assert "background-size:cover" in html

    def test_frame_background_has_vml_fallback(self) -> None:
        """FRAME with image_ref + children → VML v:rect + v:fill for Outlook."""
        child = DesignNode(id="t1", name="Overlay", type=DesignNodeType.TEXT, text_content="Hello")
        parent = DesignNode(
            id="f1",
            name="Hero",
            type=DesignNodeType.FRAME,
            width=600,
            height=400,
            image_ref="https://example.com/hero.jpg",
            children=[child],
        )
        html = node_to_email_html(parent)
        assert "v:rect" in html
        assert "v:fill" in html
        assert 'src="https://example.com/hero.jpg"' in html
        assert "<!--[if gte mso 9]>" in html

    def test_frame_image_ref_no_children_renders_img(self) -> None:
        """FRAME with image_ref but no children → standalone <img> tag."""
        node = DesignNode(
            id="f1",
            name="Banner Image",
            type=DesignNodeType.FRAME,
            width=600,
            height=300,
            image_ref="https://example.com/banner.jpg",
            children=[],
        )
        html = node_to_email_html(node)
        assert "<img" in html
        assert 'src="https://example.com/banner.jpg"' in html
        assert 'alt="Banner Image"' in html

    def test_background_url_validation(self) -> None:
        """javascript: URL in image_ref → rejected, no background rendered."""
        child = DesignNode(id="t1", name="Text", type=DesignNodeType.TEXT, text_content="Hello")
        parent = DesignNode(
            id="f1",
            name="Hero",
            type=DesignNodeType.FRAME,
            width=600,
            height=400,
            image_ref="javascript:alert(1)",
            children=[child],
        )
        html = node_to_email_html(parent)
        assert "background-image" not in html
        assert "v:fill" not in html
