"""Tests for the card-with-N-children composite (51.2 / Rule 1 + Rule 11, Track G · G6).

Covers the render helper (``render_card_table``), the fill builder (``_fills_card``),
and the detection predicate that routes a physical card-shell to the ``td`` seed
instead of the ``image-gallery`` seed (which dropped the identity TEXT).
"""

from __future__ import annotations

from app.design_sync.component_matcher import (
    _fills_card,
    match_section,
    render_card_table,
)
from app.design_sync.figma.layout_analyzer import (
    ColumnGroup,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)

# Node ids mirror the real LEGO membership card (raw frame 2833:2057).
_LOGO = "2833:2060"
_TEXT = "2833:2062"
_BARCODE = "2833:2064"
_SHAPE = "2833:2066"


def _card_section(
    *,
    is_physical: bool = True,
    with_text: bool = True,
    with_content_order: bool = True,
    column_layout: ColumnLayout = ColumnLayout.SINGLE,
) -> EmailSection:
    """A physical membership card-shell section (one column, mixed children)."""
    logo = ImagePlaceholder(node_id=_LOGO, node_name="logo", width=440, height=114)
    barcode = ImagePlaceholder(node_id=_BARCODE, node_name="barcode", width=440, height=90)
    shape = ImagePlaceholder(node_id=_SHAPE, node_name="shape", width=440, height=44)
    text = TextBlock(
        node_id=_TEXT,
        content="Andy\nemail@brand.emaillove.com",
        font_family="Noto Sans",
        font_size=16.0,
        line_height=21.0,
        font_weight=600,
        text_color="#000000",
    )
    images = [logo, barcode, shape]
    texts = [text] if with_text else []
    order = (_LOGO, _TEXT, _BARCODE, _SHAPE) if with_content_order else ()
    cg = ColumnGroup(
        column_idx=1,
        node_id="col",
        node_name="col",
        texts=texts,
        images=images,
        content_order=order,
    )
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="2833:2057",
        node_name="mj-section",
        texts=texts,
        images=images,
        column_layout=column_layout,
        width=440.0,
        height=369.0,
        bg_color="#F4F4F4",
        column_groups=[cg],
        is_physical_card_surface=is_physical,
        inner_bg="#FFFFFF",
        inner_radius=18.0,
    )


# ── render_card_table ───────────────────────────────────────────────────────


def test_render_card_table_wrapper_attrs() -> None:
    html = render_card_table(["<tr><td>x</td></tr>"], width=440, bg="#FFFFFF", radius=18)
    assert 'width="440"' in html
    assert 'align="center"' in html
    assert 'bgcolor="#FFFFFF"' in html
    assert "border-radius:18px" in html
    assert "border-collapse:separate" in html
    assert "overflow:hidden" in html
    assert "<tr><td>x</td></tr>" in html


def test_render_card_table_no_inline_background_color() -> None:
    """The white surface rides on the ``bgcolor`` ATTR only — an inline
    ``background-color`` would be clobbered by the section container-bg override."""
    html = render_card_table(["<tr><td>x</td></tr>"], width=440, bg="#FFFFFF", radius=18)
    assert "background-color:" not in html


# ── _fills_card ─────────────────────────────────────────────────────────────


def test_fills_card_returns_single_content_text_fill() -> None:
    fills = _fills_card(_card_section(), 600)
    assert len(fills) == 1
    assert fills[0].slot_id == "content"
    assert fills[0].slot_type == "text"


def test_fills_card_restores_dropped_identity_text() -> None:
    """The regression this feature fixes: image-gallery dropped the TEXT node."""
    value = _fills_card(_card_section(), 600)[0].value
    assert "Andy" in value
    assert "email@brand.emaillove.com" in value
    assert "<br />" in value  # the \n in the identity text becomes a line break


def test_fills_card_rows_follow_content_order() -> None:
    value = _fills_card(_card_section(), 600)[0].value
    # y-order: logo image, identity text, barcode image, bottom shape.
    positions = [value.index(f"{_LOGO}.png"), value.index("Andy"), value.index(f"{_BARCODE}.png")]
    assert positions == sorted(positions)
    assert value.count("<tr>") == 4  # four stacked child rows


def test_fills_card_width_from_dominant_image_not_100pct() -> None:
    """Rule 11: card width = dominant child-image native width (440), not 100%."""
    value = _fills_card(_card_section(), 600)[0].value
    assert 'width="440"' in value
    assert "border-radius:18px" in value
    assert 'bgcolor="#FFFFFF"' in value


def test_fills_card_no_inline_bg_and_no_node_id() -> None:
    """Regression guards: an inline card bg is clobbered by the container-bg
    override; a ``data-node-id`` on the image would attract the Rule-10 per-corner
    radius override. Neither may appear in the card fill."""
    value = _fills_card(_card_section(), 600)[0].value
    assert "background-color:" not in value
    assert "data-node-id" not in value
    assert "border-top-left-radius" not in value


def test_fills_card_no_dark_mode_class() -> None:
    """Rule 9 by construction: no dark class → the physical card never flips."""
    value = _fills_card(_card_section(), 600)[0].value
    assert "dark" not in value.lower()


def test_fills_card_content_order_empty_falls_back() -> None:
    """Absent ``content_order``, fall back to images-then-texts without crashing."""
    fills = _fills_card(_card_section(with_content_order=False), 600)
    assert len(fills) == 1
    value = fills[0].value
    assert "Andy" in value
    assert value.count("<tr>") == 4


# ── detection / routing ─────────────────────────────────────────────────────


def test_card_shell_routes_to_td_seed() -> None:
    match = match_section(_card_section(), 0)
    assert match.component_slug == "td"


def test_plain_gallery_still_routes_to_image_gallery() -> None:
    """A non-physical 3-image, no-text section stays an image gallery."""
    imgs = [
        ImagePlaceholder(node_id=f"g{i}", node_name="g", width=200, height=200) for i in range(3)
    ]
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="g",
        node_name="gallery",
        images=imgs,
        column_layout=ColumnLayout.SINGLE,
        width=600.0,
    )
    assert match_section(section, 0).component_slug == "image-gallery"


def test_physical_card_without_text_does_not_route_to_td_seed() -> None:
    """The predicate requires surviving text — an image-only card is out of scope."""
    match = match_section(_card_section(with_text=False), 0)
    assert match.component_slug != "td"


def test_card_detection_requires_single_column() -> None:
    """A multi-column physical section is a column layout, not a card-shell (the
    column override handles it) — the predicate must not fire."""
    match = match_section(_card_section(column_layout=ColumnLayout.TWO_COLUMN), 0)
    assert match.component_slug != "td"


# ── HTML-email correctness / hardening ──────────────────────────────────────


def test_card_text_row_carries_mso_and_font_props() -> None:
    """CLAUDE.md HTML-email rule: every text <td> needs font-family/size/color/
    line-height + mso-line-height-rule:exactly."""
    value = _fills_card(_card_section(), 600)[0].value
    for prop in (
        "font-family:",
        "font-size:",
        "color:",
        "line-height:",
        "mso-line-height-rule:exactly",
    ):
        assert prop in value, f"missing {prop} on the card text cell"


def test_card_font_family_escaped_with_fallback() -> None:
    """H1 regression: a design font name can't break out of the style attr, and a
    web-safe fallback is appended when the value has no comma."""
    from app.design_sync.component_matcher import _card_text_row

    evil = TextBlock(node_id="t", content="X", font_family='Arial;" onmouseover="x')
    row = _card_text_row(evil, "#FFFFFF")
    assert '" onmouseover="' not in row  # not a live attribute
    assert "&quot;" in row  # the double-quote was escaped
    # a plain multi-word family gets the web-safe fallback appended
    plain = _card_text_row(TextBlock(node_id="t", content="X", font_family="Noto Sans"), "#FFFFFF")
    assert "font-family:Noto Sans,sans-serif" in plain


def test_fills_card_renders_all_children_with_stale_content_order() -> None:
    """L1: a content_order referencing unknown ids must not drop children — every
    image and text still renders (order falls back to stored order)."""
    section = _card_section()
    # Overwrite the column group's content_order with stale ids.
    stale_cg = ColumnGroup(
        column_idx=1,
        node_id="col",
        node_name="col",
        texts=section.texts,
        images=section.images,
        content_order=("bogus-1", "bogus-2"),
    )
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id=section.node_id,
        node_name=section.node_name,
        texts=section.texts,
        images=section.images,
        column_layout=ColumnLayout.SINGLE,
        width=440.0,
        bg_color="#F4F4F4",
        column_groups=[stale_cg],
        is_physical_card_surface=True,
        inner_bg="#FFFFFF",
        inner_radius=18.0,
    )
    value = _fills_card(section, 600)[0].value
    assert "Andy" in value
    assert value.count("<tr>") == 4  # 3 images + 1 text, none dropped
