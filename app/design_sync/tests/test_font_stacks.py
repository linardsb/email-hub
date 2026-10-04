# pyright: reportPrivateUsage=false
"""Font fallback stacks by category (CE-7, #425).

The builder classifies a design font by name and appends the matching
category stack, so a client without the design font falls back to the same
kind of face (mono stays mono, serif stays serif).
"""

from __future__ import annotations

import re

import pytest

from app.design_sync.component_matcher import (
    TokenOverride,
    _build_token_overrides,
    _card_text_row,
    _column_text_row,
    _cta_label_typography,
    _footer_editorial_row,
    _spec_label_style,
    _text_node_overrides,
    _vml_button_spec,
    match_section,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.converter_service import DesignConverterService
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    TextBlock,
)
from app.design_sync.font_stacks import (
    _CATEGORY_STACK,
    FontCategory,
    font_category,
    font_stack,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedTokens,
    ExtractedTypography,
)
from app.design_sync.tests.content_checks import converted_html, font_family_values, strip_mso

_MONO = [
    "Geist Mono",
    "Courier New",
    "Roboto Mono",
    "Noto Sans Mono",
    "Fira Code",
    "JetBrains Mono",
]
_SANS = [
    "Helvetica",
    "Arial",
    "Roboto",
    "Noto Sans",
    "Inter",
    "Nunito",
    "Merriweather Sans",
    "Space Grotesk",
]
_SERIF = [
    "Georgia",
    "Times New Roman",
    "Noto Serif",
    "Lora",
    "Playfair Display",
    "Roboto Slab",
    "EB Garamond",
]
_MONO_STACK = "'Geist Mono', 'Courier New', Courier, monospace"


def test_category_stack_covers_enum() -> None:
    assert set(_CATEGORY_STACK) == set(FontCategory)


@pytest.mark.parametrize(
    ("family", "category"),
    [
        *[(f, FontCategory.MONO) for f in _MONO],
        *[(f, FontCategory.SANS) for f in _SANS],
        *[(f, FontCategory.SERIF) for f in _SERIF],
        ("Brandname Display", FontCategory.SANS),  # unknown → sans
        ("Consolas", FontCategory.MONO),  # prefix match
        ("Source Code Pro", FontCategory.MONO),  # whole token "code"
        # "mono"/"code" are whole tokens, not prefixes (PR #472 F1)
        ("Codec Pro", FontCategory.SANS),
        ("Monotype Corsiva", FontCategory.SANS),
        ("Monoton", FontCategory.SANS),
        ("Monofett", FontCategory.SANS),
        ("Monotype Garamond", FontCategory.SERIF),
    ],
)
def test_font_category(family: str, category: FontCategory) -> None:
    assert font_category(family) is category


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("Geist Mono", _MONO_STACK),
        ("Courier New", "'Courier New', Courier, monospace"),
        ("Arial", "Arial, Helvetica, sans-serif"),
        ("Helvetica", "Helvetica, Arial, sans-serif"),
        ("Lora", "Lora, Georgia, 'Times New Roman', serif"),
        ("JetBrains Mono", "'JetBrains Mono', 'Courier New', Courier, monospace"),
    ],
)
def test_font_stack_exact(family: str, expected: str) -> None:
    assert font_stack(family) == expected


def test_generic_terminated_list_is_unchanged() -> None:
    assert font_stack("Georgia, serif") == "Georgia, serif"


def test_list_without_generic_gets_first_familys_stack() -> None:
    assert font_stack("'Helvetica Neue', Arial") == "'Helvetica Neue', Arial, Helvetica, sans-serif"


@pytest.mark.parametrize("family", [*_MONO, *_SANS, *_SERIF, "Brandname Display"])
def test_font_stack_is_idempotent(family: str) -> None:
    once = font_stack(family)
    assert font_stack(once) == once


def test_sanitises_attribute_breakout() -> None:
    out = font_stack('Arial" onmouseover="x')
    for ch in ('"', "<", ">", "&", "=", ";", "\\"):
        assert ch not in out
    assert out.endswith("sans-serif")


@pytest.mark.parametrize("family", ['"Geist Mono"', "'Geist Mono'"])
def test_quoted_input_equals_bare(family: str) -> None:
    assert font_stack(family) == font_stack("Geist Mono")


@pytest.mark.parametrize("family", ["", "  ", "'\";"])
def test_empty_gives_sans_stack(family: str) -> None:
    assert font_stack(family) == "Helvetica, Arial, sans-serif"


def test_digit_leading_token_is_quoted() -> None:
    assert font_stack("3Dumb Sans").startswith("'3Dumb Sans', ")
    assert font_stack("3Dumb").startswith("'3Dumb', ")


def test_non_latin_family_survives() -> None:
    assert font_stack("ヒラギノ角ゴ") == "ヒラギノ角ゴ, Helvetica, Arial, sans-serif"
    assert font_stack("ヒラギノ 角ゴ").startswith("'ヒラギノ 角ゴ', ")


def test_underscore_is_kept() -> None:
    assert font_stack("Brand_Sans").startswith("Brand_Sans, ")


# ── Category invariant ───────────────────────────────────────────


def _families(value: str) -> list[str]:
    return [
        f.replace("!important", "").strip().strip("'\"").strip()
        for f in value.split(",")
        if f.strip()
    ]


def category_violations(html: str) -> list[str]:
    """``font-family`` values whose last family is not the first family's generic."""
    out: list[str] = []
    for value in font_family_values(html):
        fams = _families(value)
        if not fams or fams[-1].lower() != font_category(fams[0]).value:
            out.append(value)
    return out


# ── Matcher sites ────────────────────────────────────────────────


def _text(**overrides: object) -> TextBlock:
    fields: dict[str, object] = {"node_id": "t1", "content": "Hello", "font_family": "Lora"}
    fields.update(overrides)
    return TextBlock(**fields)  # type: ignore[arg-type]


def _button(**overrides: object) -> ButtonElement:
    fields: dict[str, object] = {
        "node_id": "b1",
        "text": "Shop now",
        "fill_color": "#DB291B",
        "text_color": "#ffffff",
        "url": "#",
        "font_family": "Geist Mono",
    }
    fields.update(overrides)
    return ButtonElement(**fields)  # type: ignore[arg-type]


def test_column_text_row_uses_category_stack() -> None:
    row = _column_text_row(_text(font_family="Georgia"), is_heading=True)
    assert "font-family:Georgia, 'Times New Roman', serif" in row


def test_cta_label_typography_uses_category_stack() -> None:
    assert f"font-family:{_MONO_STACK}" in _cta_label_typography(_button())


def test_vml_button_spec_uses_category_stack() -> None:
    spec = _vml_button_spec(
        _button(),
        fill="#DB291B",
        text_color="#ffffff",
        stroke_color=None,
        stroke_weight_px=None,
        max_width=600,
    )
    assert spec.font_family == _MONO_STACK


def test_card_text_row_uses_category_stack() -> None:
    assert "font-family:Lora, Georgia, 'Times New Roman', serif" in _card_text_row(
        _text(), "#ffffff"
    )


def test_spec_label_style_uses_category_stack() -> None:
    assert "font-family:Lora, Georgia, 'Times New Roman', serif" in _spec_label_style(_text())


def test_footer_editorial_row_uses_category_stack() -> None:
    assert "font-family:Lora, Georgia, 'Times New Roman', serif" in _footer_editorial_row(
        _text(), 8
    )


def test_text_node_overrides_emit_stack() -> None:
    overrides = _text_node_overrides(_text(font_family="Geist Mono"))
    assert TokenOverride("font-family", "_text_t1", _MONO_STACK) in overrides


def test_build_token_overrides_emit_stack() -> None:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s1",
        node_name="Section",
        texts=[
            _text(node_id="h1", is_heading=True, font_family="Geist Mono"),
            _text(node_id="p1", font_family="Geist Mono"),
        ],
    )
    overrides = _build_token_overrides(section)
    assert TokenOverride("font-family", "_heading", _MONO_STACK) in overrides
    assert TokenOverride("font-family", "_body", _MONO_STACK) in overrides


# ── Renderer guard and second write ──────────────────────────────


def test_second_font_write_leaves_one_clean_declaration() -> None:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s1",
        node_name="Section",
        column_layout=ColumnLayout.SINGLE,
        texts=[
            _text(node_id="h1", content="Heading", is_heading=True, font_family="Inter"),
            _text(node_id="p1", content="First paragraph", font_family="Courier New"),
            _text(node_id="p2", content="Second paragraph", font_family="Geist Mono"),
        ],
    )
    renderer = ComponentRenderer()
    html = renderer.render_section(match_section(section, 0)).html
    assert 'data-node-id="p1"' in html  # per-node anchors exist, so the test is not vacuous

    html = renderer._apply_token_overrides(
        html, [TokenOverride("font-family", "_text_p1", "Geist Mono")]
    )
    tag = re.search(r'<td\b[^>]*data-node-id="p1"[^>]*>', html)
    assert tag is not None
    decls = re.findall(r"font-family:([^;\"]+)", tag.group(0))
    assert decls == [_MONO_STACK]
    assert "&#x27;" not in html
    assert "Courier New'" not in html.replace("'Courier New'", "")


# ── Pipeline ─────────────────────────────────────────────────────


def _text_node(node_id: str, content: str, family: str, size: float) -> DesignNode:
    return DesignNode(
        id=node_id,
        name="Text",
        type=DesignNodeType.TEXT,
        text_content=content,
        font_family=family,
        font_size=size,
        y=0,
    )


def _frame(node_id: str, children: list[DesignNode]) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=node_id,
        type=DesignNodeType.FRAME,
        width=600,
        height=200,
        layout_mode="VERTICAL",
        padding_top=24,
        padding_bottom=24,
        children=children,
    )


def test_minimal_tree_every_font_matches_category() -> None:
    # The first frame classifies as the header and the last as the footer, so the
    # fonts under test sit in the frames between them.
    page = DesignNode(
        id="page1",
        name="Page",
        type=DesignNodeType.PAGE,
        children=[
            _frame("lead", [_text_node("lead_b", "Lead copy.", "Roboto", 16.0)]),
            _frame(
                "section_0",
                [
                    _text_node("s0_h", "Release notes", "JetBrains Mono", 28.0),
                    _text_node("s0_b", "A short paragraph of body copy.", "Lora", 16.0),
                ],
            ),
            _frame("section_1", [_text_node("s1_b", "More body copy here.", "Roboto", 16.0)]),
            _frame("tail", [_text_node("tail_b", "Tail copy.", "Roboto", 16.0)]),
        ],
    )
    tokens = ExtractedTokens(
        colors=[
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text Color", hex="#333333"),
        ],
        typography=[
            ExtractedTypography(
                name="Body", family="Inter", weight="400", size=16.0, line_height=24.0
            ),
        ],
    )
    document = EmailDesignDocument.from_legacy(
        DesignFileStructure(file_name="Test.fig", pages=[page]), tokens
    )
    html = DesignConverterService().convert_document(document, output_format="html").html

    assert category_violations(html) == []
    values = font_family_values(html)
    assert any(v.startswith("'JetBrains Mono'") and v.endswith("monospace") for v in values)
    assert any(v.startswith("Lora") and v.endswith(", serif") for v in values)


# ── Corpus ───────────────────────────────────────────────────────


@pytest.mark.parametrize("case", ["5", "6", "7", "8", "9", "10", "reframe"])
def test_corpus_fonts_match_category(case: str) -> None:
    html = converted_html(case)
    if html is None:
        pytest.skip(f"case {case}: structure.json/tokens.json not present")
    assert category_violations(html) == []
    # Outside MSO blocks no font value is HTML-escaped: an escaped quote's ";"
    # ends the renderer's font-family match on a second write. The VML <center>
    # inside <!--[if mso]> is escaped by vml_button and never rewritten.
    assert "font-family:&#x27;" not in strip_mso(html)
