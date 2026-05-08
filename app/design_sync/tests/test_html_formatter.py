"""Tests for email-safe HTML formatter (Phase 33 — HTML output quality)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from app.design_sync.html_formatter import format_email_html

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _indent_of(line: str) -> int:
    """Return the number of leading spaces on *line*."""
    return len(line) - len(line.lstrip(" "))


def _find_line(output: str, substring: str) -> str:
    """Return the first line in *output* containing *substring*."""
    for line in output.splitlines():
        if substring in line:
            return line
    raise AssertionError(f"No line contains {substring!r} in:\n{output}")


class _TagBalanceChecker(HTMLParser):
    """Validate that non-void tags are properly opened/closed."""

    VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in self.VOID:
            self.stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tl = tag.lower()
        if tl in self.VOID:
            return
        if self.stack and self.stack[-1] == tl:
            self.stack.pop()
        else:
            self.errors.append(f"Unexpected </{tl}>, stack={self.stack}")


def _check_balance(html: str) -> list[str]:
    """Strip MSO comments, then check tag balance."""
    cleaned = re.sub(r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", "", html, flags=re.DOTALL)
    checker = _TagBalanceChecker()
    checker.feed(cleaned)
    return checker.errors


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------


class TestBasicStructure:
    def test_empty_input(self) -> None:
        assert format_email_html("") == ""
        assert format_email_html("   ") == "   "

    def test_whitespace_only(self) -> None:
        assert format_email_html("\n\n  \n") == "\n\n  \n"

    def test_basic_document_structure(self) -> None:
        html = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"></head><body></body></html>'
        )
        result = format_email_html(html)
        lines = result.strip().splitlines()
        assert lines[0] == "<!DOCTYPE html>"
        assert lines[1] == '<html lang="en">'
        assert _indent_of(_find_line(result, "<head>")) == 2
        assert _indent_of(_find_line(result, "<meta")) == 4
        assert _indent_of(_find_line(result, "</head>")) == 2
        assert _indent_of(_find_line(result, "<body>")) == 2
        assert _indent_of(_find_line(result, "</body>")) == 2
        assert _indent_of(_find_line(result, "</html>")) == 0

    def test_trailing_newline(self) -> None:
        html = "<html><body></body></html>"
        result = format_email_html(html)
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# Block element indentation
# ---------------------------------------------------------------------------


class TestBlockIndentation:
    def test_table_tr_td_nesting(self) -> None:
        html = "<table><tr><td>content</td></tr></table>"
        result = format_email_html(html)
        assert _indent_of(_find_line(result, "<table>")) == 0
        assert _indent_of(_find_line(result, "<tr>")) == 2
        assert _indent_of(_find_line(result, "<td>")) == 4
        assert _indent_of(_find_line(result, "</td>")) == 4
        assert _indent_of(_find_line(result, "</tr>")) == 2
        assert _indent_of(_find_line(result, "</table>")) == 0

    def test_nested_tables(self) -> None:
        html = "<table><tr><td><table><tr><td>inner</td></tr></table></td></tr></table>"
        result = format_email_html(html)
        # Inner table should be at indent 6 (table=0 > tr=2 > td=4 > table=6)
        lines_with_table = [ln for ln in result.splitlines() if "<table>" in ln]
        assert _indent_of(lines_with_table[0]) == 0
        assert _indent_of(lines_with_table[1]) == 6

    def test_div_is_block(self) -> None:
        html = '<td><div class="column">content</div></td>'
        result = format_email_html(html)
        assert _indent_of(_find_line(result, "<div")) == 2
        assert _indent_of(_find_line(result, "</div>")) == 2


# ---------------------------------------------------------------------------
# Inline leaf elements
# ---------------------------------------------------------------------------


class TestInlineLeaf:
    def test_h3_single_line(self) -> None:
        html = '<td><h3 style="margin:0;font-size:18px;">Hello World</h3></td>'
        result = format_email_html(html)
        h3_line = _find_line(result, "<h3")
        assert "<h3" in h3_line and "</h3>" in h3_line and "Hello World" in h3_line

    def test_paragraph_single_line(self) -> None:
        html = '<td><p style="margin:0 0 10px 0;">Body text</p></td>'
        result = format_email_html(html)
        p_line = _find_line(result, "<p")
        assert "<p" in p_line and "</p>" in p_line and "Body text" in p_line

    def test_anchor_single_line(self) -> None:
        html = '<td><a href="#" style="display:inline-block;">Click me</a></td>'
        result = format_email_html(html)
        a_line = _find_line(result, "<a ")
        assert "<a " in a_line and "</a>" in a_line and "Click me" in a_line

    def test_h1_through_h6(self) -> None:
        for level in range(1, 7):
            html = f"<td><h{level}>Heading {level}</h{level}></td>"
            result = format_email_html(html)
            line = _find_line(result, f"<h{level}")
            assert f"</h{level}>" in line

    def test_nested_inline_in_anchor(self) -> None:
        html = '<a href="#"><span>text</span></a>'
        result = format_email_html(html)
        # Should stay on one line since <a> accumulates until </a>
        a_line = _find_line(result, "<a ")
        assert "<span>" in a_line and "</span>" in a_line and "</a>" in a_line

    def test_center_tag_inline(self) -> None:
        html = '<center style="font-size:18px;">Button Text</center>'
        result = format_email_html(html)
        line = _find_line(result, "<center")
        assert "</center>" in line and "Button Text" in line


# ---------------------------------------------------------------------------
# Void elements
# ---------------------------------------------------------------------------


class TestVoidElements:
    def test_img_self_closing(self) -> None:
        html = '<td><img src="logo.png" width="200" height="50" style="display:block;" /></td>'
        result = format_email_html(html)
        img_line = _find_line(result, "<img")
        assert "/>" in img_line
        # img should be inside td (indented deeper)
        assert _indent_of(img_line) > _indent_of(_find_line(result, "<td>"))

    def test_meta_tag(self) -> None:
        html = (
            '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>'
        )
        result = format_email_html(html)
        meta_lines = [ln for ln in result.splitlines() if "<meta" in ln]
        assert len(meta_lines) == 2
        for ml in meta_lines:
            assert _indent_of(ml) == 2  # inside <head>


# ---------------------------------------------------------------------------
# Style block
# ---------------------------------------------------------------------------


class TestStyleBlock:
    def test_style_content_preserved(self) -> None:
        html = "<head><style>\nbody { margin: 0; }\ntable { border-collapse: collapse; }\n</style></head>"
        result = format_email_html(html)
        assert "body { margin: 0; }" in result
        assert "table { border-collapse: collapse; }" in result

    def test_style_content_indented(self) -> None:
        html = "<head><style>\nbody { margin: 0; }\n</style></head>"
        result = format_email_html(html)
        style_line = _find_line(result, "<style>")
        body_rule = _find_line(result, "body {")
        close_style = _find_line(result, "</style>")
        # <style> and </style> at same level; content indented 1 deeper
        assert _indent_of(style_line) == _indent_of(close_style)
        assert _indent_of(body_rule) == _indent_of(style_line) + 2

    def test_media_query_inside_style(self) -> None:
        html = "<style>\n@media (prefers-color-scheme: dark) {\n  body { background: #000; }\n}\n</style>"
        result = format_email_html(html)
        assert "@media (prefers-color-scheme: dark)" in result
        assert "body { background: #000; }" in result


# ---------------------------------------------------------------------------
# MSO conditional comments
# ---------------------------------------------------------------------------


class TestMSOComments:
    def test_self_contained_no_indent_change(self) -> None:
        html = (
            "<table><tr><td>"
            '<!--[if mso]><td width="200" valign="top"><![endif]-->'
            "<div>content</div>"
            "<!--[if mso]></td><![endif]-->"
            "</td></tr></table>"
        )
        result = format_email_html(html)
        mso_line = _find_line(result, '<!--[if mso]><td width="200"')
        div_line = _find_line(result, "<div>")
        # Both should be at the same indent level (inside <td>)
        assert _indent_of(mso_line) == _indent_of(div_line)

    def test_multi_line_mso_block_is_opaque(self) -> None:
        """Multi-line MSO block (open + content + close) is one comment token."""
        html = (
            "<!--[if mso]>\n"
            "<table><tr><td>\n"
            "<![endif]-->\n"
            "<div>content</div>\n"
            "<!--[if mso]>\n"
            "</td></tr></table>\n"
            "<![endif]-->"
        )
        result = format_email_html(html)
        # The entire <!--[if mso]>...<![endif]--> block is one token,
        # so it stays as-is at the same indent level — no indent change.
        assert "<!--[if mso]>" in result
        assert "<![endif]-->" in result
        assert "<div>" in result

    def test_mso_wrapper_skeleton(self) -> None:
        """Full EMAIL_SKELETON-style MSO wrapper."""
        html = (
            "<!--[if mso]>\n"
            '<table role="presentation" width="640" align="center" '
            'cellpadding="0" cellspacing="0" border="0"><tr><td>\n'
            "<![endif]-->\n"
            '<table role="presentation" width="640"><tr><td>Main</td></tr></table>\n'
            "<!--[if mso]>\n"
            "</td></tr></table>\n"
            "<![endif]-->"
        )
        result = format_email_html(html)
        assert "<!--[if mso]>" in result
        assert "<![endif]-->" in result
        # The main <table> should be at indent 0 (same as <!--[if mso]>)
        # because it's a sibling, not inside the MSO block
        assert '<table role="presentation" width="640">' in result


# ---------------------------------------------------------------------------
# VML elements
# ---------------------------------------------------------------------------


class TestVMLElements:
    def test_vml_roundrect(self) -> None:
        html = (
            '<td align="center">'
            '<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
            'style="width:200px;height:48px;" arcsize="8%" fillcolor="#0066CC" stroke="f">'
            '<v:textbox inset="0,0,0,0" style="mso-fit-shape-to-text:true;">'
            '<center style="font-family:Arial;font-size:18px;color:#ffffff;">Click</center>'
            "</v:textbox>"
            "</v:roundrect>"
            "</td>"
        )
        result = format_email_html(html)
        assert "<v:roundrect" in result
        assert "</v:roundrect>" in result
        # v:roundrect is a block element — should be indented inside <td>
        vml_line = _find_line(result, "<v:roundrect")
        td_line = _find_line(result, "<td")
        assert _indent_of(vml_line) > _indent_of(td_line)


# ---------------------------------------------------------------------------
# Multi-column ghost table pattern
# ---------------------------------------------------------------------------


class TestMultiColumn:
    def test_ghost_table_pattern(self) -> None:
        """Full multi-column hybrid pattern from _render_multi_column_row."""
        html = (
            '<tr><td style="font-size:0;text-align:center;">'
            '<!--[if mso]><table role="presentation" width="600" cellpadding="0" '
            'cellspacing="0" border="0"><tr><![endif]-->'
            '<!--[if mso]><td width="288" valign="top"><![endif]-->'
            '<div class="column" style="display:inline-block;max-width:288px;">'
            '<table role="presentation" width="100%"><tr><td>'
            '<p style="margin:0;">Column 1</p>'
            "</td></tr></table></div>"
            "<!--[if mso]></td><![endif]-->"
            '<!--[if mso]><td width="288" valign="top"><![endif]-->'
            '<div class="column" style="display:inline-block;max-width:288px;">'
            '<table role="presentation" width="100%"><tr><td>'
            '<p style="margin:0;">Column 2</p>'
            "</td></tr></table></div>"
            "<!--[if mso]></td><![endif]-->"
            "<!--[if mso]></tr></table><![endif]-->"
            "</td></tr>"
        )
        result = format_email_html(html)
        # Self-contained MSO comments should stay on one line
        for mso_line in [ln for ln in result.splitlines() if "<!--[if mso]>" in ln]:
            assert "<![endif]-->" in mso_line
        # Both columns' content should be present
        assert "Column 1" in result
        assert "Column 2" in result
        # Tag balance (after stripping MSO)
        errors = _check_balance(result)
        assert errors == [], f"Balance errors: {errors}"


# ---------------------------------------------------------------------------
# Spacer rows
# ---------------------------------------------------------------------------


class TestSpacerRow:
    def test_spacer_row_formatted(self) -> None:
        html = (
            '<tr><td style="height:20px;font-size:1px;line-height:1px;'
            'mso-line-height-rule:exactly;" aria-hidden="true">&nbsp;</td></tr>'
        )
        result = format_email_html(html)
        assert "height:20px" in result
        assert "&nbsp;" in result

    def test_nbsp_not_standalone_line(self) -> None:
        """&nbsp; inside a td should be indented, not orphaned at level 0."""
        html = '<table><tr><td style="height:12px;">&nbsp;</td></tr></table>'
        result = format_email_html(html)
        nbsp_line = _find_line(result, "&nbsp;")
        assert _indent_of(nbsp_line) > 0


# ---------------------------------------------------------------------------
# Empty elements
# ---------------------------------------------------------------------------


class TestEmptyElements:
    def test_empty_td(self) -> None:
        html = "<table><tr><td></td></tr></table>"
        result = format_email_html(html)
        assert "<td>" in result
        assert "</td>" in result


# ---------------------------------------------------------------------------
# Idempotency and parameters
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_idempotent(self) -> None:
        html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            "<style>body { margin: 0; }</style></head>"
            '<body><table><tr><td><h1 style="margin:0;">Hello</h1></td></tr>'
            "</table></body></html>"
        )
        once = format_email_html(html)
        twice = format_email_html(once)
        assert once == twice

    def test_indent_size_4(self) -> None:
        html = "<html><body><table></table></body></html>"
        result = format_email_html(html, indent_size=4)
        assert _indent_of(_find_line(result, "<body>")) == 4
        assert _indent_of(_find_line(result, "<table>")) == 8


# ---------------------------------------------------------------------------
# Full email round-trip
# ---------------------------------------------------------------------------


class TestFullEmailRoundTrip:
    def test_converter_output_well_formed(self) -> None:
        """Build a mini email via DesignConverterService, verify formatting."""
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.email_design_document import EmailDesignDocument
        from app.design_sync.protocol import (
            DesignFileStructure,
            DesignNode,
            DesignNodeType,
            ExtractedTokens,
        )

        structure = DesignFileStructure(
            file_name="test.fig",
            pages=[
                DesignNode(
                    id="page1",
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
                                    text_content="Welcome",
                                    font_size=32.0,
                                    y=0,
                                ),
                                DesignNode(
                                    id="t2",
                                    name="Body",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello world",
                                    font_size=16.0,
                                    y=50,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        document = EmailDesignDocument.from_legacy(structure, ExtractedTokens())
        result = DesignConverterService().convert_document(document)
        html = result.html

        # Basic structure present
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

        # Indentation is consistent: every line uses multiples of 2 spaces
        for line in html.strip().splitlines():
            leading = len(line) - len(line.lstrip(" "))
            if line.strip():  # skip empty lines
                assert leading % 2 == 0, f"Odd indent ({leading}) on: {line!r}"

        # Tag balance after stripping MSO
        errors = _check_balance(html)
        assert errors == [], f"Balance errors: {errors}"

    def test_formatted_output_is_idempotent(self) -> None:
        """Converter output should already be formatted (format is idempotent)."""
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.email_design_document import EmailDesignDocument
        from app.design_sync.protocol import (
            DesignFileStructure,
            DesignNode,
            DesignNodeType,
            ExtractedTokens,
        )

        structure = DesignFileStructure(
            file_name="test.fig",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="frame1",
                            name="Section",
                            type=DesignNodeType.FRAME,
                            width=600,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="Text",
                                    type=DesignNodeType.TEXT,
                                    text_content="Test",
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
        assert format_email_html(result.html) == result.html
