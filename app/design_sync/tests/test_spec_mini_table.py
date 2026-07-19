r"""Spec mini-table pairing in the column builder (Track G · G7 / 51.4, Mechanism 1).

c7 product cards carry a spec run inside one column — ``[name, icon16, '617\n
Pieces', icon26, '+260 Insiders', CTA]`` in F10 ``content_order``. The design
lays each ``[icon | value/label]`` pair side-by-side (a mini-table); the pre-G7
builder emits every icon and every label as its own full-width ``<tr>``.
``_group_spec_pairs`` detects a run of >=2 adjacent ``(icon <=30px, text <40 chars)``
pairs and ``_spec_minitable_row`` renders them as ONE centered horizontal row,
leaving the name/CTA as their own rows. Matcher-only, direct HTML — no composite
seam.
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _build_column_fill_html,
    _group_spec_pairs,
    _ordered_column_elements,
    _spec_minitable_row,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ImagePlaceholder,
    TextBlock,
)


def _img(nid: str, w: float) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=nid, node_name="icon", width=w, height=w)


def _txt(nid: str, content: str) -> TextBlock:
    return TextBlock(node_id=nid, content=content, font_size=11.0)


def _spec_group() -> ColumnGroup:
    """A product-card column: name, 2 icon/value pairs, CTA — F10 order."""
    name = _txt("name", "Halloween Wreath")
    i1, v1 = _img("i1", 26), _txt("v1", "617\nPieces")
    i2, v2 = _img("i2", 30), _txt("v2", "+260 Insiders")
    cta = ButtonElement(node_id="b", text="Shop now")
    order = ("name", "i1", "v1", "i2", "v2", "b")
    return ColumnGroup(
        column_idx=1,
        node_id="col",
        node_name="col",
        width=270.0,
        texts=[name, v1, v2],
        images=[i1, i2],
        buttons=[cta],
        content_order=order,
    )


# ── _group_spec_pairs ────────────────────────────────────────────────────────


def test_groups_two_adjacent_icon_text_pairs() -> None:
    seq = _ordered_column_elements(_spec_group())
    grouped = _group_spec_pairs(seq)
    # name (passthrough) · spec-run (list of 2 pairs) · cta (passthrough)
    assert isinstance(grouped[0], TextBlock) and grouped[0].content == "Halloween Wreath"
    assert isinstance(grouped[1], list) and len(grouped[1]) == 2
    assert isinstance(grouped[-1], ButtonElement)


def test_single_pair_is_not_a_run() -> None:
    grouped = _group_spec_pairs([_img("i", 26), _txt("v", "617")])
    assert not any(isinstance(g, list) for g in grouped)  # <2 pairs -> passthrough


def test_wide_icon_is_not_a_spec_pair() -> None:
    # c9's 34px icons must NOT trigger the mini-table.
    grouped = _group_spec_pairs(
        [_img("i1", 34), _txt("v1", "The Place"), _img("i2", 34), _txt("v2", "The Temp")]
    )
    assert not any(isinstance(g, list) for g in grouped)


def test_long_text_is_not_a_label() -> None:
    grouped = _group_spec_pairs(
        [_img("i1", 26), _txt("v1", "x" * 45), _img("i2", 26), _txt("v2", "y" * 45)]
    )
    assert not any(isinstance(g, list) for g in grouped)


# ── _spec_minitable_row markup ───────────────────────────────────────────────


def test_minitable_row_is_one_centered_row_with_cells() -> None:
    pairs = [(_img("i1", 26), _txt("v1", "617\nPieces")), (_img("i2", 30), _txt("v2", "+260 X"))]
    row = _spec_minitable_row(pairs, None)
    assert row.count('valign="middle"') == 4  # 2 icon cells + 2 label cells, one row
    assert 'align="center"' in row  # centered mini-table
    assert row.count("<img") == 2  # both icons
    assert "617<br />Pieces" in row  # stacked value/label via _multiline_to_br
    assert 'width="26"' in row and 'width="30"' in row  # icons at native width


# ── integration: _build_column_fill_html ─────────────────────────────────────


def test_build_column_fill_collapses_spec_rows_to_one_minitable() -> None:
    html = _build_column_fill_html(_spec_group())
    # name row + one mini-table row + cta row — the 2 icons/2 values no longer
    # each get their own full-width row.
    assert "Halloween Wreath" in html
    assert "617<br />Pieces" in html
    assert "Shop now" in html
    assert 'align="center"' in html  # the mini-table


def test_non_spec_column_unchanged() -> None:
    # heading + body + cta, no icon pairs -> no mini-table wrapper.
    g = ColumnGroup(
        column_idx=1,
        node_id="c",
        node_name="c",
        width=250.0,
        texts=[_txt("h", "Heading"), _txt("b", "Body copy")],
        buttons=[ButtonElement(node_id="b", text="Go")],
        content_order=("h", "b", "b"),
    )
    html = _build_column_fill_html(g)
    assert 'align="center"' not in html  # no mini-table introduced
