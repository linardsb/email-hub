r"""Multi-line cell text -> ``<br>`` (Track G · G7 / 51.5, Mechanism 2).

Figma stores stacked value/label text (``617\nPieces``) and 2-line labels
(``The Place: \u2028The Nevada desert.``) as ONE ``TEXT`` node with a hard line
separator and a uniform font. ``_safe_text`` alone HTML-escapes but leaves the
separator, which collapses to whitespace in email clients — the design's two
lines render as one. The 51.5 "splitter" reduces to normalizing hard breaks
(``\n``, ``\r\n``, ``U+2028``, ``U+2029``) to ``<br />`` in the column-text
renderer; there is no per-line font weight in the data, so no node splitting.
"""

from __future__ import annotations

from app.design_sync.component_matcher import _column_text_row, _multiline_to_br
from app.design_sync.figma.layout_analyzer import TextBlock


def _text(content: str) -> TextBlock:
    return TextBlock(node_id="t", content=content, font_size=12.0)


# ── helper: every hard separator becomes <br />, escaping first ──────────────


def test_newline_becomes_br() -> None:
    assert _multiline_to_br("617\nPieces") == "617<br />Pieces"


def test_line_separator_u2028_becomes_br() -> None:
    # The c7 '+260' spec cell uses U+2028, NOT \n — a \n-only replace drops it.
    assert _multiline_to_br("+260\u2028Insiders") == "+260<br />Insiders"


def test_crlf_and_u2029_become_br() -> None:
    assert _multiline_to_br("a\r\nb") == "a<br />b"
    assert _multiline_to_br("a\u2029b") == "a<br />b"


def test_escapes_before_inserting_br() -> None:
    # HTML-escape happens first; the <br /> we add is trusted markup.
    assert _multiline_to_br("<b>\nx") == "&lt;b&gt;<br />x"


def test_plain_text_unchanged() -> None:
    assert _multiline_to_br("no breaks here") == "no breaks here"


# ── integration: _column_text_row emits the <br> (RED pre-fix) ───────────────


def test_column_text_row_renders_stacked_value_label() -> None:
    row = _column_text_row(_text("617\nPieces"), is_heading=False)
    assert "617<br />Pieces" in row
    assert "617\nPieces" not in row


def test_column_text_row_renders_u2028_label() -> None:
    row = _column_text_row(_text("+260\u2028LEGO Insiders Points"), is_heading=False)
    assert "+260<br />LEGO Insiders Points" in row
