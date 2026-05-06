"""Tests for design-to-email converter."""

from __future__ import annotations

import pytest

from app.design_sync.converter import (
    _calculate_column_widths,
    _determine_heading_level,
    _font_stack,
    _group_into_rows,
    _NodeProps,
    _sanitize_css_value,
    _validate_button_contrast,
    convert_colors_to_palette,
    convert_typography,
    node_to_email_html,
    sanitize_web_tags_for_email,
)
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import TextBlock
from app.design_sync.protocol import (
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedGradient,
    ExtractedTypography,
)
from app.design_sync.render_context import RenderContext


class TestConvertColors:
    def test_name_based_mapping(self) -> None:
        colors = [
            ExtractedColor(name="Primary Blue", hex="#0066cc"),
            ExtractedColor(name="Background", hex="#f5f5f5"),
            ExtractedColor(name="Text Color", hex="#333333"),
        ]
        palette = convert_colors_to_palette(colors)
        assert palette.primary == "#0066cc"
        assert palette.background == "#f5f5f5"
        assert palette.text == "#333333"

    def test_fallback_positional(self) -> None:
        colors = [
            ExtractedColor(name="Blue", hex="#0000ff"),
            ExtractedColor(name="Red", hex="#ff0000"),
            ExtractedColor(name="Green", hex="#00ff00"),
        ]
        palette = convert_colors_to_palette(colors)
        assert palette.primary == "#0000ff"
        assert palette.secondary == "#ff0000"
        assert palette.accent == "#00ff00"

    def test_empty_colors(self) -> None:
        palette = convert_colors_to_palette([])
        assert palette.primary == "#333333"

    def test_dark_bg_dark_text_contrast_fix(self) -> None:
        """Dark background with dark text should auto-correct to white text."""
        colors = [
            ExtractedColor(name="Background", hex="#1a1a2e"),
            ExtractedColor(name="Text Color", hex="#000000"),
        ]
        palette = convert_colors_to_palette(colors)
        assert palette.background == "#1a1a2e"
        assert palette.text == "#ffffff"  # contrast-corrected

    def test_light_bg_light_text_contrast_fix(self) -> None:
        """Light background with light text should auto-correct to black text."""
        colors = [
            ExtractedColor(name="Background", hex="#f5f5f5"),
            ExtractedColor(name="Text Color", hex="#eeeeee"),
        ]
        palette = convert_colors_to_palette(colors)
        assert palette.background == "#f5f5f5"
        assert palette.text == "#000000"  # contrast-corrected

    def test_adequate_contrast_preserved(self) -> None:
        """Colors with good contrast should not be modified."""
        colors = [
            ExtractedColor(name="Background", hex="#ffffff"),
            ExtractedColor(name="Text Color", hex="#333333"),
        ]
        palette = convert_colors_to_palette(colors)
        assert palette.text == "#333333"  # unchanged


class TestConvertTypography:
    def test_heading_and_body(self) -> None:
        styles = [
            ExtractedTypography(
                name="Heading 1", family="Inter", weight="700", size=32.0, line_height=1.2
            ),
            ExtractedTypography(
                name="Body Text",
                family="Roboto",
                weight="400",
                size=16.0,
                line_height=1.5,
            ),
        ]
        typo = convert_typography(styles)
        assert "Inter" in typo.heading_font
        assert "Roboto" in typo.body_font
        assert typo.base_size == "16px"

    def test_empty(self) -> None:
        typo = convert_typography([])
        assert typo.heading_font == "Arial, Helvetica, sans-serif"

    def test_typography_line_height_and_letter_spacing(self) -> None:
        styles = [
            ExtractedTypography(
                "Heading",
                "Inter",
                "700",
                32.0,
                38.4,
                letter_spacing=-0.5,
                text_transform="uppercase",
            ),
            ExtractedTypography("Body", "Roboto", "400", 16.0, 24.0, letter_spacing=0.0),
        ]
        t = convert_typography(styles)
        assert t.heading_line_height == "38px"
        assert t.body_line_height == "24px"
        assert t.heading_letter_spacing == "-0.5px"
        assert t.body_letter_spacing is None  # 0.0 maps to None
        assert t.heading_text_transform == "uppercase"


class TestFontStack:
    def test_yaml_fallback_inter(self) -> None:
        assert _font_stack("Inter") == "Inter, Arial, Helvetica, sans-serif"

    def test_yaml_fallback_playfair(self) -> None:
        result = _font_stack("Playfair Display")
        assert "Georgia" in result
        assert "serif" in result

    def test_unknown_font_default(self) -> None:
        assert _font_stack("UnknownFont") == "UnknownFont, Arial, Helvetica, sans-serif"

    def test_already_has_comma(self) -> None:
        assert _font_stack("Inter, Arial") == "Inter, Arial"

    def test_generic_keyword(self) -> None:
        assert _font_stack("sans-serif") == "sans-serif"


class TestNodeToEmailHtml:
    def test_text_node(self) -> None:
        node = DesignNode(id="1", name="Title", type=DesignNodeType.TEXT, text_content="Hello")
        result = node_to_email_html(node)
        assert "<td" in result
        assert "Hello" in result

    def test_image_node(self) -> None:
        node = DesignNode(id="2", name="Hero", type=DesignNodeType.IMAGE, width=600, height=300)
        result = node_to_email_html(node)
        assert "<img" in result
        assert 'width="600"' in result

    def test_image_node_has_node_id_and_alt(self) -> None:
        """Image tags include data-node-id for URL mapping and alt for accessibility."""
        node = DesignNode(id="1:2", name="Logo", type=DesignNodeType.IMAGE, width=200, height=50)
        result = node_to_email_html(node)
        assert 'data-node-id="1:2"' in result
        assert 'alt="Logo"' in result
        assert 'src=""' in result  # empty until _fill_image_urls post-processes

    def test_frame_with_children(self) -> None:
        node = DesignNode(
            id="3",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="4",
                    name="Text",
                    type=DesignNodeType.TEXT,
                    text_content="Hi",
                    y=0,
                ),
                DesignNode(
                    id="5",
                    name="Img",
                    type=DesignNodeType.IMAGE,
                    width=200,
                    height=100,
                    y=50,
                ),
            ],
        )
        result = node_to_email_html(node)
        assert "<table" in result
        assert "<tr>" in result

    def test_instance_node(self) -> None:
        """INSTANCE type renders as table (same as FRAME)."""
        node = DesignNode(
            id="10",
            name="Button Instance",
            type=DesignNodeType.INSTANCE,
            width=200,
            children=[
                DesignNode(
                    id="11", name="Label", type=DesignNodeType.TEXT, text_content="Click", y=0
                ),
            ],
        )
        result = node_to_email_html(node)
        assert "<table" in result
        assert 'width="100%"' in result
        assert "Click" in result

    def test_component_node_with_children(self) -> None:
        """COMPONENT with nested nodes renders recursively."""
        node = DesignNode(
            id="20",
            name="Card Component",
            type=DesignNodeType.COMPONENT,
            width=300,
            children=[
                DesignNode(
                    id="21", name="Title", type=DesignNodeType.TEXT, text_content="Title", y=0
                ),
                DesignNode(
                    id="22", name="Body", type=DesignNodeType.TEXT, text_content="Body text", y=30
                ),
            ],
        )
        result = node_to_email_html(node)
        assert "<table" in result
        assert "Title" in result
        assert "Body text" in result

    def test_props_map_font_override(self) -> None:
        """TEXT node with props_map uses custom font."""
        node = DesignNode(id="30", name="Custom", type=DesignNodeType.TEXT, text_content="Styled")
        props_map = {
            "30": _NodeProps(font_family="Inter", font_size=24.0, font_weight="700"),
        }
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "Inter" in result
        assert "font-size:24px" in result
        assert "font-weight:bold" in result
        assert "Styled" in result

    def test_props_map_bg_color(self) -> None:
        """FRAME with props_map bg_color gets bgcolor attr."""
        node = DesignNode(
            id="40", name="Section", type=DesignNodeType.FRAME, width=600, children=[]
        )
        props_map = {"40": _NodeProps(bg_color="#f5f5f5")}
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert 'bgcolor="#f5f5f5"' in result

    def test_dark_bg_text_gets_white_color(self) -> None:
        """TEXT inside a dark-background FRAME gets color:#ffffff."""
        node = DesignNode(
            id="100",
            name="Dark Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="101", name="Body", type=DesignNodeType.TEXT, text_content="Hello", y=0
                ),
            ],
        )
        props_map = {"100": _NodeProps(bg_color="#1a1a2e")}
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "color:#ffffff" in result
        assert "Hello" in result

    def test_light_bg_text_gets_black_color(self) -> None:
        """TEXT inside a light-background FRAME gets color:#000000."""
        node = DesignNode(
            id="110",
            name="Light Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="111", name="Body", type=DesignNodeType.TEXT, text_content="World", y=0
                ),
            ],
        )
        props_map = {"110": _NodeProps(bg_color="#ffffff")}
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "color:#000000" in result

    def test_nested_dark_bg_propagates(self) -> None:
        """Nested frames inherit parent bg for text contrast."""
        inner = DesignNode(
            id="121",
            name="Inner",
            type=DesignNodeType.GROUP,
            children=[
                DesignNode(
                    id="122", name="Copy", type=DesignNodeType.TEXT, text_content="Deep", y=0
                ),
            ],
        )
        outer = DesignNode(
            id="120",
            name="Outer",
            type=DesignNodeType.FRAME,
            width=600,
            children=[inner],
        )
        props_map = {"120": _NodeProps(bg_color="#0d1117")}
        result = node_to_email_html(outer, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "color:#ffffff" in result
        assert "Deep" in result

    def test_props_map_padding(self) -> None:
        """FRAME with padding props gets padding style on <td> (not <table>)."""
        node = DesignNode(id="50", name="Padded", type=DesignNodeType.FRAME, width=600, children=[])
        props_map = {
            "50": _NodeProps(padding_top=20, padding_right=10, padding_bottom=20, padding_left=10),
        }
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        # Padding on <td>, not <table> — Outlook ignores padding on <table>
        assert "padding:20px 10px 20px 10px" in result
        assert '<td style="padding:' in result

    def test_text_content_html_escaped(self) -> None:
        """Text content with HTML chars is escaped to prevent XSS."""
        node = DesignNode(
            id="60",
            name="XSS",
            type=DesignNodeType.TEXT,
            text_content='<script>alert("xss")</script>',
        )
        result = node_to_email_html(node)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_font_weight_mapping_in_html(self) -> None:
        """Font weight 300→normal, 600→bold in inline styles."""
        node = DesignNode(
            id="t1",
            name="Text",
            type=DesignNodeType.TEXT,
            text_content="Hello",
            width=100,
            height=20,
        )
        props = _NodeProps(font_weight="300", font_size=16.0, line_height_px=24.0)
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map={"t1": props}))
        assert "font-weight:normal" in result
        assert "line-height:24px" in result
        assert "mso-line-height-rule:exactly" in result

    def test_mso_font_alt_for_web_font(self) -> None:
        """Web fonts get mso-font-alt for Outlook fallback."""
        node = DesignNode(
            id="t1",
            name="Text",
            type=DesignNodeType.TEXT,
            text_content="Hi",
            width=100,
            height=20,
        )
        props = _NodeProps(font_family="Inter", font_size=16.0)
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map={"t1": props}))
        assert "mso-font-alt:Arial" in result

    def test_text_transform_and_decoration(self) -> None:
        node = DesignNode(
            id="t1",
            name="Text",
            type=DesignNodeType.TEXT,
            text_content="Hello",
            width=100,
            height=20,
        )
        props = _NodeProps(font_size=16.0, text_transform="uppercase", text_decoration="underline")
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map={"t1": props}))
        assert "text-transform:uppercase" in result
        assert "text-decoration:underline" in result

    def test_letter_spacing_in_html(self) -> None:
        node = DesignNode(
            id="t1",
            name="Text",
            type=DesignNodeType.TEXT,
            text_content="Spaced",
            width=100,
            height=20,
        )
        props = _NodeProps(font_size=16.0, letter_spacing_px=0.5)
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map={"t1": props}))
        assert "letter-spacing:0.5px" in result


class TestSanitizeCssValue:
    def test_clean_value_unchanged(self) -> None:
        assert _sanitize_css_value("Inter") == "Inter"
        assert _sanitize_css_value("Arial, Helvetica, sans-serif") == "Arial, Helvetica, sans-serif"

    def test_strips_semicolon(self) -> None:
        assert ";" not in _sanitize_css_value("Arial; background:url(evil)")

    def test_strips_angle_brackets(self) -> None:
        result = _sanitize_css_value("Inter; } </style><script>alert(1)</script>")
        assert "<" not in result
        assert ">" not in result
        assert "script" in result  # text preserved, tags stripped

    def test_strips_braces(self) -> None:
        assert "{" not in _sanitize_css_value("Inter { color: red }")

    def test_empty_on_all_unsafe(self) -> None:
        assert _sanitize_css_value(";<>{}") == ""

    def test_numeric_weight(self) -> None:
        assert _sanitize_css_value("700") == "700"


class TestGroupIntoRows:
    def test_single_row(self) -> None:
        nodes = [
            DesignNode(id="1", name="A", type=DesignNodeType.TEXT, x=0, y=0),
            DesignNode(id="2", name="B", type=DesignNodeType.TEXT, x=200, y=5),
        ]
        rows = _group_into_rows(nodes)
        assert len(rows) == 1
        assert len(rows[0]) == 2

    def test_two_rows(self) -> None:
        nodes = [
            DesignNode(id="1", name="A", type=DesignNodeType.TEXT, x=0, y=0),
            DesignNode(id="2", name="B", type=DesignNodeType.TEXT, x=0, y=100),
        ]
        rows = _group_into_rows(nodes)
        assert len(rows) == 2

    def test_hero_image_own_row(self) -> None:
        """Wide IMAGE (>=80% parent width) gets its own row."""
        nodes = [
            DesignNode(id="1", name="Hero", type=DesignNodeType.IMAGE, x=0, y=0, width=550),
            DesignNode(id="2", name="Text", type=DesignNodeType.TEXT, x=300, y=0),
        ]
        rows = _group_into_rows(nodes, parent_width=600)
        # Hero image should be in its own row (550 >= 600*0.8=480)
        assert len(rows) == 2
        assert rows[0][0].id == "1"
        assert rows[1][0].id == "2"


class TestFillColorFromNode:
    def test_fill_color_from_node(self) -> None:
        """DesignNode with fill_color renders bgcolor attribute."""
        node = DesignNode(
            id="fc1",
            name="Dark Section",
            type=DesignNodeType.FRAME,
            width=600,
            fill_color="#1a1a2e",
            children=[],
        )
        result = node_to_email_html(node)
        assert 'bgcolor="#1a1a2e"' in result

    def test_text_color_from_node(self) -> None:
        """TEXT node with text_color uses it instead of contrast auto."""
        frame = DesignNode(
            id="tc1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            fill_color="#1a1a2e",
            children=[
                DesignNode(
                    id="tc2",
                    name="Title",
                    type=DesignNodeType.TEXT,
                    text_content="Custom Color",
                    text_color="#ff6600",
                    y=0,
                ),
            ],
        )
        result = node_to_email_html(frame)
        assert "color:#ff6600;" in result
        assert "Custom Color" in result
        # Should NOT use contrast-auto white
        assert "color:#ffffff;" not in result

    def test_text_color_fallback_to_contrast(self) -> None:
        """TEXT node without text_color in dark parent still gets white."""
        frame = DesignNode(
            id="cf1",
            name="Dark",
            type=DesignNodeType.FRAME,
            width=600,
            fill_color="#0d1117",
            children=[
                DesignNode(
                    id="cf2",
                    name="Body",
                    type=DesignNodeType.TEXT,
                    text_content="Auto contrast",
                    y=0,
                ),
            ],
        )
        result = node_to_email_html(frame)
        assert "color:#ffffff;" in result

    def test_image_responsive_styles(self) -> None:
        """Image nodes include width:100%;max-width;height:auto for responsiveness."""
        node = DesignNode(id="ri1", name="Hero", type=DesignNodeType.IMAGE, width=600, height=300)
        result = node_to_email_html(node)
        assert "width:100%;" in result
        assert "max-width:600px;" in result
        assert "height:auto;" in result

    def test_props_map_overrides_fill_color(self) -> None:
        """props_map bg_color takes precedence over node.fill_color."""
        node = DesignNode(
            id="po1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            fill_color="#111111",
            children=[],
        )
        props_map = {"po1": _NodeProps(bg_color="#f5f5f5")}
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert 'bgcolor="#f5f5f5"' in result
        assert 'bgcolor="#111111"' not in result


class TestFrameWidthAndFont:
    def test_frame_table_width_100_percent(self) -> None:
        """FRAME nodes produce width='100%' instead of pixel width."""
        node = DesignNode(
            id="w1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=480,
            children=[],
        )
        result = node_to_email_html(node)
        assert 'width="100%"' in result
        assert 'width="480"' not in result

    def test_font_family_propagates_to_children(self) -> None:
        """Parent frame font reaches child TEXT <td> via parent_font."""
        frame = DesignNode(
            id="f1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="t1", name="Body", type=DesignNodeType.TEXT, text_content="Hello", y=0
                ),
            ],
        )
        props_map = {"f1": _NodeProps(font_family="Inter")}
        result = node_to_email_html(frame, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "Inter,Arial,Helvetica,sans-serif" in result

    def test_font_family_on_td_wrapper(self) -> None:
        """Non-text child <td> gets style='font-family:...' when parent has font."""
        frame = DesignNode(
            id="f2",
            name="Outer",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="inner1",
                    name="Inner",
                    type=DesignNodeType.FRAME,
                    width=300,
                    children=[],
                    y=0,
                ),
            ],
        )
        props_map = {"f2": _NodeProps(font_family="Roboto")}
        result = node_to_email_html(frame, RenderContext.from_legacy_kwargs(props_map=props_map))
        assert "font-family:Roboto,Arial,Helvetica,sans-serif" in result

    def test_email_skeleton_has_width_600(self) -> None:
        """EMAIL_SKELETON formatted output contains width='600' on main table."""
        from app.design_sync.converter_service import EMAIL_SKELETON

        html = EMAIL_SKELETON.format(
            style_block="<style></style>",
            bg_color="#ffffff",
            text_color="#000000",
            body_font="Arial, Helvetica, sans-serif",
            sections="",
            container_width=600,
        )
        # The non-MSO main table should have width="600"
        assert 'width="600"' in html
        assert "max-width:600px" in html
        assert "mso-table-lspace:0pt" in html
        assert "mso-table-rspace:0pt" in html

    def test_email_skeleton_body_has_inline_font(self) -> None:
        """<body> tag includes font-family: in inline style."""
        from app.design_sync.converter_service import EMAIL_SKELETON

        html = EMAIL_SKELETON.format(
            style_block="<style></style>",
            bg_color="#ffffff",
            text_color="#000000",
            body_font="Inter, Arial, Helvetica, sans-serif",
            sections="",
            container_width=600,
        )
        assert "font-family:Inter, Arial, Helvetica, sans-serif;" in html


class TestConverterNoDivOrP:
    """Converter output uses table layout — no div/p for structure."""

    def test_skeleton_no_div_or_p(self) -> None:
        from app.design_sync.converter_service import EMAIL_SKELETON

        html = EMAIL_SKELETON.format(
            style_block="<style></style>",
            bg_color="#ffffff",
            text_color="#000000",
            body_font="Arial, Helvetica, sans-serif",
            sections="<tr><td>Content</td></tr>",
            container_width=600,
        )
        assert "<div" not in html
        assert "<p" not in html

    def test_full_conversion_uses_tables(self) -> None:
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.protocol import DesignFileStructure, ExtractedTokens

        structure = DesignFileStructure(
            file_name="test.penpot",
            pages=[
                DesignNode(
                    id="page",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="frame1",
                            name="Hero",
                            type=DesignNodeType.FRAME,
                            width=600,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="Title",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello World",
                                    y=0,
                                ),
                                DesignNode(
                                    id="img1",
                                    name="Hero Image",
                                    type=DesignNodeType.IMAGE,
                                    width=600,
                                    height=300,
                                    y=50,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        # Test that converter output is table-based (modern component path).
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        assert "<table" in result.html

    def test_node_to_email_html_uses_tables(self) -> None:
        node = DesignNode(
            id="f1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[
                DesignNode(
                    id="t1", name="Text", type=DesignNodeType.TEXT, text_content="Body", y=0
                ),
                DesignNode(
                    id="g1",
                    name="Group",
                    type=DesignNodeType.GROUP,
                    children=[
                        DesignNode(
                            id="t2",
                            name="Nested",
                            type=DesignNodeType.TEXT,
                            text_content="Nested text",
                            y=0,
                        ),
                    ],
                    y=50,
                ),
            ],
        )
        result = node_to_email_html(node)
        assert "<div" not in result
        assert "<table" in result


class TestSanitizeWebTagsForEmail:
    def test_p_inside_td_stripped_styles_merged(self) -> None:
        """<p> inside <td> is stripped, styles merged into parent <td>."""
        html_input = '<td><p style="color:red;">text</p></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "color:red" in result
        assert "text" in result

    def test_p_outside_td_stripped(self) -> None:
        """<p> outside <td> is stripped to content (backward compat)."""
        html_input = "<p>standalone</p>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "standalone" in result

    def test_multiple_p_inside_td_stripped(self) -> None:
        """Multiple <p> tags inside <td> are stripped, content preserved."""
        html_input = "<td><p>one</p><p>two</p></td>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "one" in result
        assert "two" in result

    def test_multiple_p_outside_td_get_br_separator(self) -> None:
        html_input = "<p>one</p><p>two</p>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "one<br><br>two" in result

    def test_p_with_margin_stripped_style_merged(self) -> None:
        """<p> with margin inside <td> is stripped, margin converted to padding on td."""
        html_input = '<td><p style="margin:0;">text</p></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "text" in result
        # margin on p becomes padding on td
        assert "padding:0;" in result

    def test_div_with_layout_css_converted_to_table(self) -> None:
        """<div> with layout CSS becomes table wrapper."""
        html_input = '<div style="width:300px;">content</div>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" not in result
        assert "</div>" not in result
        assert '<table role="presentation"' in result
        assert "</td></tr></table>" in result
        assert "content" in result

    def test_div_simple_wrapper_inside_td_preserved(self) -> None:
        """<div> with text-align inside <td> is preserved (content wrapper)."""
        html_input = '<td><div style="text-align:center;">centered</div></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" in result
        assert "text-align:center" in result
        assert "centered" in result

    def test_div_outside_td_no_layout_unwrapped(self) -> None:
        """<div> outside <td> with no layout CSS is unwrapped."""
        html_input = '<div role="article"><table><tr><td>content</td></tr></table></div>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" not in result
        assert "</div>" not in result
        assert "<table>" in result
        assert "content" in result

    def test_nested_divs_outside_td_stripped(self) -> None:
        html_input = "<div><div><table><tr><td>deep</td></tr></table></div></div>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" not in result
        assert "</div>" not in result
        assert "<table>" in result

    def test_mso_comment_preserved(self) -> None:
        html_input = (
            "before<!--[if mso]><div><table><tr><td>mso</td></tr></table></div><![endif]-->after"
        )
        result = sanitize_web_tags_for_email(html_input)
        assert "<!--[if mso]>" in result
        assert "<div>" in result  # inside MSO block, untouched
        assert "<![endif]-->" in result
        assert "before" in result
        assert "after" in result

    def test_div_with_display_flex_converted(self) -> None:
        """div with display:flex is layout — converted to table."""
        html_input = '<div style="display:flex;">items</div>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" not in result
        assert '<table role="presentation"' in result
        assert "items" in result

    def test_div_with_max_width_converted(self) -> None:
        """div with max-width is layout — converted to table."""
        html_input = '<div style="max-width:600px;">wrapper</div>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" not in result
        assert '<table role="presentation"' in result

    def test_llm_output_p_stripped_div_classified(self) -> None:
        """LLM output inside table: <p> stripped (content kept), simple <div> preserved."""
        llm_output = (
            '<table><tr><td><div style="text-align:center;"><p>Intro</p>'
            "<p>Details</p></div></td></tr></table>"
        )
        result = sanitize_web_tags_for_email(llm_output)
        # <p> inside <td> → stripped, content preserved
        assert "<p" not in result
        assert "Intro" in result
        assert "Details" in result
        # Simple <div> inside <td> → preserved
        assert "text-align:center" in result
        assert "<table>" in result

    def test_p_between_nested_tables_inside_outer_td(self) -> None:
        """<p> between nested tables inside outer <td> is stripped, content preserved."""
        html_input = "<td><table><tr><td>inner</td></tr></table><p>between</p></td>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "between" in result

    def test_div_between_nested_tables_inside_outer_td(self) -> None:
        """Simple <div> between nested tables but inside outer <td> is preserved."""
        html_input = (
            "<td><table><tr><td>inner</td></tr></table>"
            '<div style="text-align:center;">wrap</div></td>'
        )
        result = sanitize_web_tags_for_email(html_input)
        assert "<div" in result
        assert "text-align:center" in result
        assert "wrap" in result

    # --- AI agent output safety net tests ---

    def test_h1_inside_td_stripped_styles_merged(self) -> None:
        """h1 from AI output inside <td> is stripped, styles merged into td."""
        html_input = (
            '<td style="padding:20px;"><h1 style="font-size:32px;font-weight:bold;">Title</h1></td>'
        )
        result = sanitize_web_tags_for_email(html_input)
        assert "<h1" not in result
        assert "</h1>" not in result
        assert "Title" in result
        assert "font-size:32px" in result

    def test_h2_inside_td_stripped_data_slot_transferred(self) -> None:
        """h2 from AI output has data-slot transferred to parent td."""
        html_input = '<td><h2 data-slot="heading" style="font-size:24px;">Heading</h2></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<h2" not in result
        assert 'data-slot="heading"' in result
        assert "Heading" in result

    def test_h3_inside_td_stripped_class_transferred(self) -> None:
        """h3 from AI output has class transferred to parent td."""
        html_input = '<td><h3 class="dark-text" style="color:#fff;">Sub</h3></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<h3" not in result
        assert 'class="dark-text"' in result
        assert "Sub" in result

    def test_mixed_h_and_p_in_ai_output_all_stripped(self) -> None:
        """AI output with mixed h2 + p tags — all stripped, content preserved."""
        html_input = (
            '<td style="padding:20px;">'
            '<h2 style="font-size:24px;">Heading</h2>'
            '<p style="font-size:14px;">Body text</p>'
            "</td>"
        )
        result = sanitize_web_tags_for_email(html_input)
        assert "<h2" not in result
        assert "<p" not in result
        assert "Heading" in result
        assert "Body text" in result

    def test_h_outside_td_stripped_with_br(self) -> None:
        """h tags outside <td> are stripped like p tags."""
        html_input = "<h1>First</h1><h2>Second</h2>"
        result = sanitize_web_tags_for_email(html_input)
        assert "<h1" not in result
        assert "<h2" not in result
        assert "First" in result
        assert "Second" in result

    def test_ai_output_p_margin_becomes_td_padding(self) -> None:
        """AI-generated <p margin:...> becomes padding on parent td."""
        html_input = '<td><p style="margin:0 0 16px 0;font-size:14px;">Text</p></td>'
        result = sanitize_web_tags_for_email(html_input)
        assert "<p" not in result
        assert "padding:0 0 16px 0" in result
        assert "font-size:14px" in result

    def test_mso_block_h_and_p_also_stripped(self) -> None:
        """h/p tags inside <!--[if mso]> blocks are also stripped.

        Outlook's Word engine handles td-based layouts just as well as
        p/h tags, so we strip them everywhere for consistency.
        """
        html_input = "<!--[if mso]><td><h1>Outlook</h1><p>Compat</p></td><![endif]-->"
        result = sanitize_web_tags_for_email(html_input)
        assert "<h1" not in result
        assert "<p>" not in result
        assert "Outlook" in result
        assert "Compat" in result
        assert "<!--[if" in result  # MSO wrapper preserved


class TestEmailSkeletonMetaTags:
    def test_format_detection_meta(self) -> None:
        from app.design_sync.converter_service import EMAIL_SKELETON

        html = EMAIL_SKELETON.format(
            style_block="<style></style>",
            bg_color="#ffffff",
            text_color="#000000",
            body_font="Arial, Helvetica, sans-serif",
            sections="",
            container_width=600,
        )
        assert '<meta name="format-detection"' in html
        assert '<meta name="x-apple-disable-message-reformatting">' in html

    def test_mso_reset_in_style_block(self) -> None:
        from app.design_sync.converter_service import DesignConverterService
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
                                    name="Text",
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
        assert "border-collapse: collapse" in result.html
        assert "mso-table-lspace: 0pt" in result.html
        assert "-ms-interpolation-mode: bicubic" in result.html


class TestInlineMSOStyles:
    def test_table_has_mso_resets(self) -> None:
        """Every <table> in converter output has MSO reset inline styles."""
        node = DesignNode(
            id="1",
            name="Section",
            type=DesignNodeType.FRAME,
            width=600,
            children=[],
        )
        result = node_to_email_html(node)
        assert "border-collapse:collapse" in result
        assert "mso-table-lspace:0pt" in result
        assert "mso-table-rspace:0pt" in result

    def test_image_has_mso_resets(self) -> None:
        """<img> tags include MSO-safe inline styles."""
        node = DesignNode(id="2", name="Photo", type=DesignNodeType.IMAGE, width=600, height=300)
        result = node_to_email_html(node)
        assert "-ms-interpolation-mode:bicubic" in result
        assert "outline:none" in result
        assert "text-decoration:none" in result


class TestNestingDepthGuard:
    def test_depth_exceeding_6_flattens(self) -> None:
        """Deeply nested frames are flattened beyond depth 6."""
        # Build 8-level deep nesting
        deepest = DesignNode(
            id="t-deep",
            name="deep-text",
            type=DesignNodeType.TEXT,
            text_content="deep",
            y=0,
        )
        current = deepest
        for i in range(8):
            current = DesignNode(
                id=f"f{i}",
                name=f"Frame-{i}",
                type=DesignNodeType.FRAME,
                width=600,
                children=[current],
            )
        result = node_to_email_html(current)
        # Should still contain the text
        assert "deep" in result
        # Count <table> tags — should be capped (not 8 nested tables)
        table_count = result.count("<table")
        assert table_count <= 7  # depth 0-6 = 7 tables max


class TestLayoutAnalyzerIntegration:
    def test_convert_populates_layout(self) -> None:
        """convert() returns ConversionResult with layout data."""
        from app.design_sync.converter_service import DesignConverterService
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
                            name="Header",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                            children=[
                                DesignNode(
                                    id="t0",
                                    name="Logo",
                                    type=DesignNodeType.TEXT,
                                    text_content="Logo",
                                ),
                            ],
                        ),
                        DesignNode(
                            id="f2",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=100,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="Body",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello",
                                    y=0,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        assert result.layout is not None
        assert len(result.layout.sections) >= 1
        assert result.sections_count >= 1

    def test_container_width_from_layout(self) -> None:
        """Container width derived from layout.overall_width."""
        from app.design_sync.converter_service import DesignConverterService
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
                            x=0,
                            y=0,
                            width=700,
                            height=200,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="T",
                                    type=DesignNodeType.TEXT,
                                    text_content="X",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        assert 'width="700"' in result.html
        assert "max-width:700px" in result.html

    def test_container_width_clamped(self) -> None:
        """Container width > 800 is clamped to 800."""
        from app.design_sync.converter_service import DesignConverterService
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
                            x=0,
                            y=0,
                            width=1200,
                            height=200,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="T",
                                    type=DesignNodeType.TEXT,
                                    text_content="X",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        assert 'width="800"' in result.html
        assert "max-width:800px" in result.html


class TestBuildPropsMapFromNodes:
    def test_extracts_all_fields(self) -> None:
        """_build_props_map_from_nodes extracts full DesignNode properties."""
        from app.design_sync.converter_service import DesignConverterService

        frames = [
            DesignNode(
                id="f1",
                name="Section",
                type=DesignNodeType.FRAME,
                width=600,
                padding_top=24.0,
                padding_right=16.0,
                padding_bottom=24.0,
                padding_left=16.0,
                layout_mode="HORIZONTAL",
                children=[
                    DesignNode(
                        id="t1",
                        name="Text",
                        type=DesignNodeType.TEXT,
                        font_family="Inter",
                        font_size=18.0,
                        font_weight=700,
                        line_height_px=24.0,
                        letter_spacing_px=0.5,
                        text_content="Hello",
                    ),
                ],
            ),
        ]
        svc = DesignConverterService()
        props = svc._build_props_map_from_nodes(frames)

        assert "f1" in props
        assert props["f1"].padding_top == 24.0
        assert props["f1"].padding_right == 16.0
        assert props["f1"].layout_direction == "row"

        assert "t1" in props
        assert props["t1"].font_family == "Inter"
        assert props["t1"].font_size == 18.0
        assert props["t1"].font_weight == "700"
        assert props["t1"].line_height_px == 24.0
        assert props["t1"].letter_spacing_px == 0.5

    def test_vertical_layout_direction(self) -> None:
        from app.design_sync.converter_service import DesignConverterService

        frames = [
            DesignNode(
                id="f1",
                name="Stack",
                type=DesignNodeType.FRAME,
                width=600,
                layout_mode="VERTICAL",
            ),
        ]
        svc = DesignConverterService()
        props = svc._build_props_map_from_nodes(frames)
        assert props["f1"].layout_direction == "column"


# `TestInterSectionSpacer` was deleted in 08c part 2: it asserted the legacy
# recursive renderer's `mso-line-height-rule:exactly` + `aria-hidden="true"`
# spacer-row markup. Inter-section spacing in the modern component-template
# path is handled inside the assembled component HTML and doesn't surface
# those exact strings on a synthetic two-frame fixture.


class TestMultiColumnLayout:
    def test_two_column_horizontal_proportional_widths(self) -> None:
        """HORIZONTAL frame with two children produces ghost table with proportional widths."""
        node = DesignNode(
            id="p1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="c1", name="Left", type=DesignNodeType.FRAME, width=200, children=[]),
                DesignNode(
                    id="c2", name="Right", type=DesignNodeType.FRAME, width=400, children=[]
                ),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert "max-width:200px" in result
        assert "max-width:400px" in result
        assert '<td width="200"' in result
        assert '<td width="400"' in result
        assert "display:inline-block" in result
        assert "vertical-align:top" in result
        assert 'cellpadding="0" cellspacing="0"' in result
        assert "mso-table-lspace:0pt" in result
        assert "mso-table-rspace:0pt" in result

    def test_three_equal_columns(self) -> None:
        node = DesignNode(
            id="p1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(
                    id=f"c{i}", name=f"Col{i}", type=DesignNodeType.FRAME, width=200, children=[]
                )
                for i in range(3)
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert result.count("max-width:200px") == 3
        assert result.count('<td width="200"') == 3

    def test_horizontal_with_gap(self) -> None:
        node = DesignNode(
            id="p1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            item_spacing=20,
            children=[
                DesignNode(id="c1", name="Left", type=DesignNodeType.FRAME, width=280, children=[]),
                DesignNode(
                    id="c2", name="Right", type=DesignNodeType.FRAME, width=280, children=[]
                ),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert '<td width="20">' in result

    def test_single_child_no_multi_column(self) -> None:
        node = DesignNode(
            id="p1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="c1", name="Only", type=DesignNodeType.FRAME, width=600, children=[]),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert "<!--[if mso]>" not in result or result.count("<!--[if mso]>") == 0
        assert 'class="column"' not in result

    def test_vertical_layout_each_child_own_row(self) -> None:
        node = DesignNode(
            id="p1",
            name="Stack",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="VERTICAL",
            children=[
                DesignNode(
                    id=f"c{i}", name=f"Row{i}", type=DesignNodeType.FRAME, width=600, children=[]
                )
                for i in range(3)
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert result.count("<tr>") >= 3
        assert 'class="column"' not in result

    def test_unknown_widths_distribute_equally(self) -> None:
        node = DesignNode(
            id="p1",
            name="Row",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="c1", name="A", type=DesignNodeType.FRAME, children=[]),
                DesignNode(id="c2", name="B", type=DesignNodeType.FRAME, children=[]),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(container_width=600))
        assert "max-width:300px" in result
        assert result.count("max-width:300px") == 2

    def test_no_nested_mso_conditionals(self) -> None:
        inner_row = DesignNode(
            id="inner",
            name="InnerRow",
            type=DesignNodeType.FRAME,
            width=400,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="ic1", name="IC1", type=DesignNodeType.FRAME, width=200, children=[]),
                DesignNode(id="ic2", name="IC2", type=DesignNodeType.FRAME, width=200, children=[]),
            ],
        )
        outer = DesignNode(
            id="outer",
            name="OuterRow",
            type=DesignNodeType.FRAME,
            width=600,
            layout_mode="HORIZONTAL",
            children=[
                DesignNode(id="oc1", name="OC1", type=DesignNodeType.FRAME, width=200, children=[]),
                inner_row,
            ],
        )
        result = node_to_email_html(outer, RenderContext.from_legacy_kwargs(container_width=600))
        opens = result.count("<!--[if mso]>")
        closes = result.count("<![endif]-->")
        assert opens == closes, f"Unbalanced MSO: {opens} opens vs {closes} closes"
        depth = 0
        max_depth = 0
        for line in result.split("\n"):
            if "<!--[if mso]>" in line:
                depth += 1
                max_depth = max(max_depth, depth)
            if "<![endif]-->" in line:
                depth -= 1
        assert max_depth <= 1, f"Nested MSO conditionals detected (max depth {max_depth})"


class TestGroupIntoRowsExtended:
    def test_y_tolerance_20px(self) -> None:
        nodes = [
            DesignNode(id="1", name="A", type=DesignNodeType.TEXT, x=0, y=0),
            DesignNode(id="2", name="B", type=DesignNodeType.TEXT, x=200, y=15),
        ]
        rows = _group_into_rows(nodes)
        assert len(rows) == 1
        assert len(rows[0]) == 2

    def test_all_y_none_single_row(self) -> None:
        nodes = [
            DesignNode(id="1", name="A", type=DesignNodeType.TEXT),
            DesignNode(id="2", name="B", type=DesignNodeType.TEXT),
            DesignNode(id="3", name="C", type=DesignNodeType.TEXT),
        ]
        rows = _group_into_rows(nodes)
        assert len(rows) == 1
        assert len(rows[0]) == 3

    def test_mixed_y_known_unknown(self) -> None:
        nodes = [
            DesignNode(id="1", name="A", type=DesignNodeType.TEXT, y=0),
            DesignNode(id="2", name="B", type=DesignNodeType.TEXT, y=50),
            DesignNode(id="3", name="C", type=DesignNodeType.TEXT),
        ]
        rows = _group_into_rows(nodes)
        assert len(rows) == 2
        assert any(n.id == "3" for n in rows[-1])


class TestCalculateColumnWidths:
    def test_proportional_widths(self) -> None:
        children = [
            DesignNode(id="1", name="A", type=DesignNodeType.FRAME, width=200),
            DesignNode(id="2", name="B", type=DesignNodeType.FRAME, width=400),
        ]
        widths = _calculate_column_widths(children, 600, gap=0)
        assert widths == [200, 400]

    def test_equal_distribution(self) -> None:
        children = [
            DesignNode(id="1", name="A", type=DesignNodeType.FRAME),
            DesignNode(id="2", name="B", type=DesignNodeType.FRAME),
        ]
        widths = _calculate_column_widths(children, 600, gap=0)
        assert widths == [300, 300]

    def test_gap_subtracted(self) -> None:
        children = [
            DesignNode(id="1", name="A", type=DesignNodeType.FRAME, width=200),
            DesignNode(id="2", name="B", type=DesignNodeType.FRAME, width=200),
        ]
        widths = _calculate_column_widths(children, 600, gap=20)
        assert sum(widths) == 580
        assert widths[0] == 290
        assert widths[1] == 290

    def test_rounding_absorb_last(self) -> None:
        # Use widths > 60% of container to avoid sparse-layout short-circuit
        children = [
            DesignNode(id="1", name="A", type=DesignNodeType.FRAME, width=250),
            DesignNode(id="2", name="B", type=DesignNodeType.FRAME, width=250),
            DesignNode(id="3", name="C", type=DesignNodeType.FRAME, width=250),
        ]
        widths = _calculate_column_widths(children, 600, gap=0)
        assert sum(widths) == 600

    def test_extreme_gap_no_negative_widths(self) -> None:
        children = [
            DesignNode(id="1", name="A", type=DesignNodeType.FRAME, width=100),
            DesignNode(id="2", name="B", type=DesignNodeType.FRAME, width=100),
        ]
        widths = _calculate_column_widths(children, 200, gap=300)
        assert all(w >= 0 for w in widths), f"Negative widths: {widths}"
        assert sum(widths) >= 2


class TestSemanticHTMLGeneration:
    """Tests for 33.6 semantic HTML generation."""

    def test_heading_text_renders_in_td(self) -> None:
        """TEXT with font_size=32 (2x body 16) -> text directly in <td> (no h1 wrapper)."""
        node = DesignNode(
            id="t1",
            name="Title",
            type=DesignNodeType.TEXT,
            text_content="Big Title",
            font_size=32.0,
            y=0,
        )
        text_meta = {
            "t1": TextBlock(
                node_id="t1",
                content="Big Title",
                font_size=32.0,
                is_heading=True,
            ),
        }
        result = node_to_email_html(
            node, RenderContext.from_legacy_kwargs(text_meta=text_meta, body_font_size=16.0)
        )
        assert "<h1" not in result
        assert "Big Title" in result
        assert "<td" in result
        assert "font-family:" in result
        assert "mso-line-height-rule:exactly" in result

    def test_heading_text_h2_size_renders_in_td(self) -> None:
        """TEXT with font_size=24 (1.5x body 16) -> text in <td> (no h2 wrapper)."""
        node = DesignNode(
            id="t1",
            name="Subtitle",
            type=DesignNodeType.TEXT,
            text_content="Subtitle",
            font_size=24.0,
            y=0,
        )
        text_meta = {
            "t1": TextBlock(
                node_id="t1",
                content="Subtitle",
                font_size=24.0,
                is_heading=True,
            ),
        }
        result = node_to_email_html(
            node, RenderContext.from_legacy_kwargs(text_meta=text_meta, body_font_size=16.0)
        )
        assert "<h2" not in result
        assert "<td" in result
        assert "Subtitle" in result
        assert "mso-line-height-rule:exactly" in result

    def test_heading_text_h3_size_renders_in_td(self) -> None:
        """TEXT with font_size=20 (1.25x body 16) -> text in <td> (no h3 wrapper)."""
        node = DesignNode(
            id="t1",
            name="Section",
            type=DesignNodeType.TEXT,
            text_content="Section",
            font_size=20.0,
            y=0,
        )
        text_meta = {
            "t1": TextBlock(
                node_id="t1",
                content="Section",
                font_size=20.0,
                is_heading=True,
            ),
        }
        result = node_to_email_html(
            node, RenderContext.from_legacy_kwargs(text_meta=text_meta, body_font_size=16.0)
        )
        assert "<h3" not in result
        assert "<td" in result
        assert "Section" in result
        assert "mso-line-height-rule:exactly" in result

    def test_body_text_renders_in_td(self) -> None:
        """TEXT at body size -> text directly in <td> with padding."""
        node = DesignNode(
            id="t1",
            name="Body",
            type=DesignNodeType.TEXT,
            text_content="Body text here",
            font_size=16.0,
            y=0,
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(body_font_size=16.0))
        assert "<p" not in result
        assert "<td" in result
        assert "padding:0 0 10px 0" in result
        assert "Body text here" in result

    def test_body_text_no_text_meta_still_td(self) -> None:
        """TEXT without text_meta -> text in <td> with padding (default body)."""
        node = DesignNode(
            id="t1",
            name="Text",
            type=DesignNodeType.TEXT,
            text_content="Fallback",
            y=0,
        )
        result = node_to_email_html(node)
        assert "<p" not in result
        assert "<td" in result
        assert "padding:0 0 10px 0" in result

    def test_multiline_text_splits_to_td_rows(self) -> None:
        """Multi-line TEXT -> multiple <td> elements joined by </tr><tr>."""
        node = DesignNode(
            id="t1",
            name="Multi",
            type=DesignNodeType.TEXT,
            text_content="Line one\nLine two\nLine three",
            y=0,
        )
        result = node_to_email_html(node)
        assert "<p" not in result
        assert result.count("<td") >= 3
        assert "</tr><tr>" in result

    def test_button_renders_bulletproof(self) -> None:
        """COMPONENT in button_ids -> <a> button with VML fallback."""
        node = DesignNode(
            id="btn1",
            name="CTA Button",
            type=DesignNodeType.COMPONENT,
            width=200,
            height=48,
            fill_color="#0066cc",
            children=[
                DesignNode(
                    id="btn1_text",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Shop Now",
                    text_color="#ffffff",
                    font_size=16.0,
                    y=0,
                ),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert '<a href="#"' in result
        assert "Shop Now" in result
        assert "v:roundrect" in result
        assert 'role="presentation"' in result
        assert "background-color:#0066cc" in result

    def test_button_min_height_44(self) -> None:
        """Button with small height gets clamped to 44px touch target."""
        node = DesignNode(
            id="btn1",
            name="Small Btn",
            type=DesignNodeType.COMPONENT,
            width=120,
            height=30,
            fill_color="#333333",
            children=[
                DesignNode(
                    id="btn1_text",
                    name="Label",
                    type=DesignNodeType.TEXT,
                    text_content="Go",
                    text_color="#ffffff",
                    font_size=14.0,
                    y=0,
                ),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(button_ids={"btn1"}))
        assert "height:44px" in result

    def test_button_not_in_ids_renders_as_table(self) -> None:
        """COMPONENT not in button_ids -> normal table rendering."""
        node = DesignNode(
            id="comp1",
            name="Card",
            type=DesignNodeType.COMPONENT,
            width=300,
            children=[
                DesignNode(
                    id="t1",
                    name="Text",
                    type=DesignNodeType.TEXT,
                    text_content="Not a button",
                    y=0,
                ),
            ],
        )
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(button_ids=set()))
        assert "v:roundrect" not in result
        assert "<table" in result

    def test_heading_has_mso_line_height(self) -> None:
        """Headings with line-height get mso-line-height-rule:exactly."""
        node = DesignNode(
            id="t1",
            name="H1",
            type=DesignNodeType.TEXT,
            text_content="Heading",
            font_size=32.0,
            line_height_px=38.0,
            y=0,
        )
        text_meta = {
            "t1": TextBlock(
                node_id="t1",
                content="Heading",
                font_size=32.0,
                is_heading=True,
            ),
        }
        props_map = {"t1": _NodeProps(line_height_px=38.0)}
        result = node_to_email_html(
            node,
            RenderContext.from_legacy_kwargs(
                text_meta=text_meta, body_font_size=16.0, props_map=props_map
            ),
        )
        assert "mso-line-height-rule:exactly" in result
        assert "<h1" not in result
        assert "<td" in result
        assert "Heading" in result


class TestDetermineHeadingLevel:
    """Unit tests for _determine_heading_level."""

    def test_h1_at_2x(self) -> None:
        assert _determine_heading_level(32.0, 16.0) == 1

    def test_h2_at_1_5x(self) -> None:
        assert _determine_heading_level(24.0, 16.0) == 2

    def test_h3_at_1_2x(self) -> None:
        assert _determine_heading_level(20.0, 16.0) == 3

    def test_body_below_1_2x(self) -> None:
        assert _determine_heading_level(16.0, 16.0) is None

    def test_zero_body_returns_none(self) -> None:
        assert _determine_heading_level(32.0, 0.0) is None


class TestButtonContrastValidation:
    """Tests for button contrast warning."""

    def test_low_contrast_logs_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        _validate_button_contrast("#cccccc", "#dddddd", 16)
        captured = capsys.readouterr()
        assert "button_contrast_low" in captured.out

    def test_high_contrast_no_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        _validate_button_contrast("#000000", "#ffffff", 16)
        captured = capsys.readouterr()
        assert "button_contrast_low" not in captured.out


class TestGradientNodeRendering:
    """Tests for gradient rendering in node_to_email_html."""

    def test_gradient_node_has_bgcolor_fallback(self) -> None:
        """Gradient node renders bgcolor="{fallback}"."""
        node = DesignNode(
            id="frame1",
            name="hero-bg",
            type=DesignNodeType.FRAME,
            width=600,
            height=300,
        )
        grad = ExtractedGradient(
            name="hero-bg",
            type="linear",
            angle=180.0,
            stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#800080",
        )
        html = node_to_email_html(
            node, RenderContext.from_legacy_kwargs(gradients_map={"hero-bg": grad})
        )
        assert 'bgcolor="#800080"' in html

    def test_gradient_node_has_css_background(self) -> None:
        """Style contains linear-gradient(...)."""
        node = DesignNode(
            id="frame1",
            name="hero-bg",
            type=DesignNodeType.FRAME,
            width=600,
            height=300,
        )
        grad = ExtractedGradient(
            name="hero-bg",
            type="linear",
            angle=90.0,
            stops=(("#FF0000", 0.0), ("#00FF00", 0.5), ("#0000FF", 1.0)),
            fallback_hex="#808080",
        )
        html = node_to_email_html(
            node, RenderContext.from_legacy_kwargs(gradients_map={"hero-bg": grad})
        )
        assert "linear-gradient(90.0deg" in html
        assert "#FF0000 0.0%" in html
        assert "#0000FF 100.0%" in html


# ── Phase 38.4 Tests ──


class TestSanitizeCssValuePhase384:
    """Bug 20: CSS sanitizer must preserve balanced parens for rgb/hsl/calc."""

    def test_rgb_preserved(self) -> None:
        assert _sanitize_css_value("rgb(255, 0, 0)") == "rgb(255, 0, 0)"

    def test_rgba_preserved(self) -> None:
        assert _sanitize_css_value("rgba(0, 0, 0, 0.5)") == "rgba(0, 0, 0, 0.5)"

    def test_hsl_preserved(self) -> None:
        assert _sanitize_css_value("hsl(120, 50%, 50%)") == "hsl(120, 50%, 50%)"

    def test_calc_preserved(self) -> None:
        assert _sanitize_css_value("calc(100% - 20px)") == "calc(100% - 20px)"

    def test_expression_blocked(self) -> None:
        result = _sanitize_css_value("expression(alert(1))")
        assert "expression" not in result.lower()

    def test_url_javascript_blocked(self) -> None:
        result = _sanitize_css_value("url(javascript:alert(1))")
        assert "javascript" not in result.lower()

    def test_url_data_html_blocked(self) -> None:
        result = _sanitize_css_value("url(data:text/html,<script>)")
        assert "data:text/html" not in result.lower()

    def test_moz_binding_blocked(self) -> None:
        result = _sanitize_css_value("-moz-binding: url(evil)")
        assert "-moz-binding" not in result.lower()


class TestHeadingMsoLineHeight:
    """Bug 26: Headings must include mso-line-height-rule:exactly."""

    def test_heading_has_mso_line_height(self) -> None:
        node = DesignNode(
            id="t1",
            name="Title",
            type=DesignNodeType.TEXT,
            text_content="Hello",
            font_size=32.0,
        )
        tb = TextBlock(node_id="t1", content="Hello", font_size=32.0, is_heading=True)
        result = node_to_email_html(node, RenderContext.from_legacy_kwargs(text_meta={"t1": tb}))
        assert "mso-line-height-rule:exactly" in result


class TestFalsyPaddingConverter:
    """Bug 21: padding=0.0 must not be treated as falsy."""

    def test_zero_padding_not_dropped(self) -> None:
        node = DesignNode(
            id="f1",
            name="Frame",
            type=DesignNodeType.FRAME,
            width=600,
            padding_top=0.0,
            padding_right=10.0,
            padding_bottom=0.0,
            padding_left=10.0,
            children=[
                DesignNode(id="t1", name="T", type=DesignNodeType.TEXT, text_content="Hi"),
            ],
        )
        result = node_to_email_html(node)
        # padding_top=0 should be present as 0px, not dropped to some default
        assert "padding:0px 10px 0px 10px" in result
