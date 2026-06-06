"""Column-text typography fidelity (Phase 52.x — col_N gap).

Multi-column text renders via ``_build_column_fill_html`` (real fixtures hit
this) and the round-robin fallback in ``_build_column_fills``. Both delegate to
the shared ``_column_text_row`` helper, which must emit the design's alignment,
weight, line-height, letter-spacing, transform, decoration, and font-family —
and must drop malformed values exactly like ``_typography_overrides``.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _build_column_fill_html,
    _build_column_fills,
    _column_text_row,
    _cta_label_typography,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    EmailSection,
    EmailSectionType,
    TextBlock,
)


def _styled_text(**overrides: object) -> TextBlock:
    """A column TextBlock with non-default typography (overridable per-field)."""
    defaults: dict[str, object] = {
        "node_id": "t1",
        "content": "Hello column",
        "is_heading": True,
        "font_size": 22.0,
        "font_family": "Georgia",
        "font_weight": 700,
        "line_height": 28.0,
        "letter_spacing": 1.5,
        "text_color": "#112233",
        "text_align": "center",
        "text_transform": "uppercase",
        "text_decoration": "underline",
    }
    defaults.update(overrides)
    return TextBlock(**defaults)  # type: ignore[arg-type]


# ── Helper renders every design property ─────────────────────────


def test_column_row_emits_all_design_properties() -> None:
    row = _column_text_row(_styled_text(), is_heading=True)
    assert "text-align:center" in row
    assert "font-weight:700" in row
    assert "line-height:28px" in row  # round(px), matches _typography_overrides
    assert "letter-spacing:1.50px" in row
    assert "text-transform:uppercase" in row
    assert "text-decoration:underline" in row
    assert "font-family:Georgia,sans-serif" in row  # web-safe fallback appended
    assert "font-size:22px" in row
    assert "color:#112233" in row
    # Structure rules: <td> only, padding + mso line-height rule preserved.
    assert row.startswith("<tr><td style=")
    assert "<p" not in row and "<h1" not in row
    assert "mso-line-height-rule:exactly" in row
    assert "padding:0 0 8px" in row


def test_column_row_keeps_explicit_font_family_with_stack() -> None:
    row = _column_text_row(
        _styled_text(font_family="Helvetica, Arial, sans-serif"), is_heading=True
    )
    # Already a stack — no extra fallback appended.
    assert "font-family:Helvetica, Arial, sans-serif" in row


def test_column_row_justify_align_allowed() -> None:
    assert "text-align:justify" in _column_text_row(
        _styled_text(text_align="justify"), is_heading=False
    )


# ── Fallbacks when design omits a property ───────────────────────


def test_column_row_heading_fallbacks() -> None:
    bare = TextBlock(node_id="t", content="Title", is_heading=True)
    row = _column_text_row(bare, is_heading=True)
    assert "font-family:Arial,sans-serif" in row
    assert "font-weight:bold" in row
    assert "line-height:1.3" in row  # unitless heading default (no px)
    assert "font-size:18px" in row
    assert "color:#333333" in row  # _safe_color fallback
    assert "text-align" not in row  # absent → omitted
    assert "letter-spacing" not in row
    assert "text-transform" not in row


def test_column_row_body_fallbacks() -> None:
    bare = TextBlock(node_id="t", content="Body", is_heading=False)
    row = _column_text_row(bare, is_heading=False)
    assert "font-weight" not in row  # body has no weight default
    assert "line-height:1.5" in row
    assert "font-size:14px" in row


# ── Malformed values are rejected (defence in depth) ─────────────


def test_column_row_rejects_injection_and_garbage() -> None:
    evil = _styled_text(
        text_color="red;}body{display:none",  # not hex → _safe_color fallback
        text_align="middle; color:red",  # not in allowlist → dropped
        text_transform="uppercase;color:red",  # not in allowlist → dropped
        text_decoration="blink",  # not in allowlist → dropped
    )
    row = _column_text_row(evil, is_heading=True)
    assert "color:#333333" in row  # fell back, no injected hex
    assert "red" not in row
    assert "display:none" not in row
    assert "text-align" not in row
    assert "text-transform" not in row
    assert "text-decoration" not in row


def test_column_row_skips_zero_letter_spacing() -> None:
    row = _column_text_row(_styled_text(letter_spacing=0.0), is_heading=True)
    assert "letter-spacing" not in row  # 0.0 is the no-op default


def test_column_row_escapes_font_family() -> None:
    """A font name must not break out of the style attribute (CSS injection)."""
    evil = _styled_text(font_family='Arial" onmouseover="x')
    row = _column_text_row(evil, is_heading=True)
    style = row.split('style="', 1)[1].split('">', 1)[0]
    assert '" onmouseover' not in style  # the breakout quote is neutralised
    assert "&quot;" in row


# ── Both call sites honour the design (no drift) ─────────────────


def test_build_column_fill_html_renders_design() -> None:
    group = ColumnGroup(
        column_idx=1,
        node_id="c1",
        node_name="Column 1",
        texts=[_styled_text(content="Designed heading")],
    )
    html = _build_column_fill_html(group)
    assert "text-align:center" in html
    assert "font-weight:700" in html
    assert "line-height:28px" in html
    assert "letter-spacing:1.50px" in html
    assert "text-transform:uppercase" in html
    assert "font-family:Georgia,sans-serif" in html


def test_build_column_fills_roundrobin_renders_design() -> None:
    # No column_groups / child_content_groups → exercises the round-robin path.
    section = EmailSection(
        section_type=EmailSectionType.HERO,
        node_id="s1",
        node_name="Two column",
        texts=[
            _styled_text(node_id="a", content="Left heading", text_align="left"),
            _styled_text(node_id="b", content="Right heading", text_align="right"),
        ],
        column_count=2,
    )
    assert not section.column_groups and not section.child_content_groups
    fills = {f.slot_id: f.value for f in _build_column_fills(section)}
    assert "text-align:left" in fills["col_1"]
    assert "text-align:right" in fills["col_2"]
    # Round-robin previously emitted NO font-size; helper now does.
    assert "font-size:22px" in fills["col_1"]
    assert "font-weight:700" in fills["col_1"]
    assert "line-height:28px" in fills["col_1"]


# ── CTA label typography (Phase 52.4b) ──────────────────────────


def _styled_button(**overrides: object) -> ButtonElement:
    """A ButtonElement whose label carries non-default design typography."""
    defaults: dict[str, object] = {
        "node_id": "b1",
        "text": "Shop now",
        "fill_color": "#DB291B",
        "text_color": "#ffffff",
        "url": "#",
        "font_size": 18.0,
        "font_weight": 400,
        "font_family": "Geist Mono",
    }
    defaults.update(overrides)
    return ButtonElement(**defaults)  # type: ignore[arg-type]


def test_cta_label_typography_emits_design() -> None:
    css = _cta_label_typography(_styled_button())
    assert "font-family:Geist Mono,sans-serif" in css  # web-safe fallback appended
    assert "font-size:18px" in css  # coerced to int
    assert "font-weight:400" in css  # raw design weight, not forced bold


def test_cta_label_typography_falls_back_to_legacy_defaults() -> None:
    css = _cta_label_typography(_styled_button(font_size=None, font_weight=None, font_family=None))
    assert "font-family:" not in css  # no font-family when design has none
    assert "font-size:14px" in css  # pre-52.4b default
    assert "font-weight:bold" in css  # pre-52.4b default


def test_cta_label_typography_escapes_font_family() -> None:
    """A CTA font name must not break out of the style attribute."""
    css = _cta_label_typography(_styled_button(font_family='Arial" onmouseover="x'))
    assert '" onmouseover' not in css
    assert "&quot;" in css


def test_build_column_fill_html_styles_cta_label() -> None:
    """The column CTA <a> carries the button's design typography (not 14/bold)."""
    group = ColumnGroup(
        column_idx=1,
        node_id="c1",
        node_name="Column 1",
        buttons=[_styled_button()],
    )
    html = _build_column_fill_html(group)
    assert "font-family:Geist Mono,sans-serif" in html
    assert "font-size:18px" in html
    assert "font-weight:400" in html
    assert "font-size:14px;font-weight:bold" not in html  # the old hardcode is gone
