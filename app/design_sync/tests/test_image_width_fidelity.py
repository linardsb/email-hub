"""F3 (RC-F3): design width threaded through every image emission.

Both directions are covered: a small icon/decoration renders at its design
size instead of ballooning to the column/cell width, while a genuinely
full-bleed image keeps the responsive ``width:100%`` behaviour.
"""

from __future__ import annotations

import re

import pytest

from app.design_sync.component_matcher import (
    ComponentMatch,
    SlotFill,
    _build_column_fill_html,
    _fills_image_block,
    _fills_image_grid,
    _image_fills_column,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ColumnGroup,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    _walk_for_images,
)
from app.design_sync.protocol import DesignNode, DesignNodeType


def _img(node_id: str, w: float | None, h: float | None = 40.0) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name=node_id, width=w, height=h)


def _img_tag(html: str) -> str:
    """Return the single ``<img>`` tag from an HTML fragment (not the wrapping table)."""
    m = re.search(r"<img[^>]*>", html)
    assert m is not None
    return m.group(0)


def _make_match(slug: str, fills: list[SlotFill]) -> ComponentMatch:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT, node_id="frame_1", node_name="Sec"
    )
    return ComponentMatch(
        section_idx=0,
        section=section,
        component_slug=slug,
        slot_fills=fills,
        token_overrides=[],
    )


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


# ── _image_fills_column predicate (the width decision) ──────────────────


class TestColumnFillPredicate:
    def test_small_icon_is_not_column_filling(self) -> None:
        # 34px pin in a 270px column (c9 slate) — must be pinned, not stretched.
        assert _image_fills_column(34.0, 270.0) is False

    def test_icon_guard_under_64_regardless_of_column(self) -> None:
        # ≤64px never stretches, even when the column width is unknown.
        assert _image_fills_column(64.0, None) is False
        assert _image_fills_column(48.0, 600.0) is False

    def test_column_filling_image_stays_responsive(self) -> None:
        # 260px image in a 260px column (c10 product) — keep width:100%.
        assert _image_fills_column(260.0, 260.0) is True

    def test_unknown_width_keeps_responsive_default(self) -> None:
        assert _image_fills_column(None, 270.0) is True

    def test_large_image_unknown_column_keeps_responsive(self) -> None:
        # >64px with no column width: only the icon guard can shrink, so this
        # keeps the pre-F3 default (avoids wrongly shrinking a full-bleed image).
        assert _image_fills_column(300.0, None) is True


# ── Column path: _column_image_row via _build_column_fill_html ──────────


class TestColumnImageWidth:
    def test_small_icon_pinned_to_design_width(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            images=[_img("2833:2094", 34.0, 46.0)],
            width=270.0,
        )
        tag = _img_tag(_build_column_fill_html(group))
        assert 'width="34"' in tag
        assert "width:34px" in tag
        assert "max-width:34px" in tag
        assert "width:100%" not in tag  # the giant-icon defect is gone

    def test_column_filling_image_keeps_full_bleed(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            images=[_img("2833:1179", 260.0, 260.0)],
            width=260.0,
        )
        tag = _img_tag(_build_column_fill_html(group))
        assert "width:100%" in tag  # responsive bannerimg behaviour preserved
        assert "max-width" not in tag
        assert "width=" not in tag  # no fixed width attr

    def test_missing_width_keeps_full_bleed(self) -> None:
        group = ColumnGroup(
            column_idx=1,
            node_id="c1",
            node_name="Col 1",
            images=[_img("nodim", None, None)],
            width=270.0,
        )
        tag = _img_tag(_build_column_fill_html(group))
        assert "width:100%" in tag


# ── Single-image builders + renderer clamp ──────────────────────────────


class TestBuilderWidthOverride:
    def test_image_grid_emits_design_width_override(self) -> None:
        section = EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id="frame_1",
            node_name="Grid",
            images=[_img("2833:2143", 48.0, 24.0)],
        )
        fills = _fills_image_grid(section, 600)
        image_fill = next(f for f in fills if f.slot_id == "image_1")
        assert image_fill.attr_overrides["width"] == "48"

    def test_image_block_emits_design_width_override(self) -> None:
        section = EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id="frame_1",
            node_name="Block",
            images=[_img("2833:9999", 40.0, 40.0)],
        )
        fills = _fills_image_block(section, 600)
        image_fill = next(f for f in fills if f.slot_id == "image_url")
        assert image_fill.attr_overrides["width"] == "40"


class TestRendererClamp:
    def test_small_grid_image_clamped(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "image-grid",
            [
                SlotFill(
                    "image_1",
                    "/api/v1/design-sync/assets/2833:2143.png",
                    slot_type="image",
                    attr_overrides={"width": "48", "data-node-id": "2833:2143"},
                ),
            ],
        )
        html = renderer.render_section(match).html
        assert re.search(r"max-width:\s*48px", html)  # the stretched-arrow defect is gone

    def test_small_image_block_clamped(self, renderer: ComponentRenderer) -> None:
        # Exercises the image-block delegation to _fill_image_slot.
        match = _make_match(
            "image-block",
            [
                SlotFill(
                    "image_url",
                    "/api/v1/design-sync/assets/2833:9999.png",
                    slot_type="image",
                    attr_overrides={"width": "40", "data-node-id": "2833:9999"},
                ),
            ],
        )
        html = renderer.render_section(match).html
        assert re.search(r"max-width:\s*40px", html)

    def test_full_bleed_image_stays_600(self, renderer: ComponentRenderer) -> None:
        match = _make_match(
            "full-width-image",
            [
                SlotFill(
                    "image_url",
                    "/api/v1/design-sync/assets/banner.png",
                    slot_type="image",
                    attr_overrides={"width": "600", "data-node-id": "banner"},
                ),
            ],
        )
        html = renderer.render_section(match).html
        img = re.search(r"<img[^>]*banner\.png[^>]*>", html)
        assert img is not None
        assert "width: 100%" in img.group(0)  # full-bleed responsiveness kept
        assert re.search(r"max-width:\s*600px", img.group(0)) is not None


# ── Ingest: _walk_for_images frame-wrap decoration width (item 2) ────────
#
# phase-53f-decorative-image-flag: a small decoration wrapped in a
# column-width frame must export at its OWN dims. Exporting the wide frame
# into a child-width <img> scales the whole PNG down (a 268px arrow-frame
# baked into <img width="28"> renders the arrow ~3px). Width + export target
# move together: for a non-cropped child, export_node_id falls back to
# node_id (== child id), so the effective export target is the child.


def _wrap(
    frame_id: str,
    frame_w: float,
    img_id: str,
    img_w: float,
    img_h: float = 40.0,
    *,
    corner_radii: tuple[float, ...] | None = None,
    fill_color: str | None = None,
    image_ref: str | None = None,
    effects_summary: str | None = None,
) -> DesignNode:
    """A FRAME wrapping a single IMAGE child (the frame-wrap branch shape)."""
    child = DesignNode(id=img_id, name="deco", type=DesignNodeType.IMAGE, width=img_w, height=img_h)
    return DesignNode(
        id=frame_id,
        name="wrapper",
        type=DesignNodeType.FRAME,
        children=[child],
        width=frame_w,
        height=frame_w,
        corner_radii=corner_radii,
        fill_color=fill_color,
        image_ref=image_ref,
        effects_summary=effects_summary,
    )


def _only(node: DesignNode) -> ImagePlaceholder:
    results: list[ImagePlaceholder] = []
    _walk_for_images(node, results)
    assert len(results) == 1, [r.node_id for r in results]
    return results[0]


class TestFrameWrapDecorationWidth:
    def test_small_decoration_exports_child_at_child_width(self) -> None:
        # c10 nav arrow: 28px image inside a 268px column-width wrapper. The
        # wrapper carries no bg-fill / image-ref / effects, so it's decoration.
        ph = _only(_wrap("F268", 268.0, "I28", 28.0))
        assert ph.width == 28.0  # was 268 (frame) — the ballooning defect is gone
        # node_id stays the child (both branches); export falls back to it.
        assert ph.node_id == "I28"
        assert ph.export_node_id != "F268"  # no longer exporting the wide frame
        assert (ph.export_node_id or ph.node_id) == "I28"  # effective export == child

    def test_radius_only_wrapper_still_child_exports_and_keeps_radius(self) -> None:
        # c7 LEGO user-info icon: 30px image in a 60px frame whose ONLY styling
        # is corner_radii. Radius must NOT block child-export (it rides the
        # child <img> via CSS by Rule 10) and must survive on the placeholder.
        ph = _only(_wrap("F60", 60.0, "I30", 30.0, corner_radii=(6.0, 0.0, 0.0, 6.0)))
        assert ph.width == 30.0
        assert (ph.export_node_id or ph.node_id) == "I30"
        assert ph.corner_radius_spec is not None  # radius preserved through child-export

    def test_over_cap_image_keeps_frame_export(self) -> None:
        # 65px > 64 cap: mid-size content, not a small decoration → frame path.
        ph = _only(_wrap("F600", 600.0, "I65", 65.0))
        assert ph.width == 600.0  # frame width (today's behaviour, unchanged)
        assert ph.export_node_id == "F600"

    def test_fill_sized_image_keeps_frame_export(self) -> None:
        # img == frame (600 in 600): genuine full-bleed FILL, never a decoration.
        ph = _only(_wrap("F600", 600.0, "I600", 600.0))
        assert ph.width == 600.0
        assert ph.export_node_id == "F600"

    def test_styled_wrapper_keeps_frame_export(self) -> None:
        # Baked bg-fill on the wrapper is worth exporting (the original Rule-10
        # reason this branch exists) — a small child does NOT override it.
        ph = _only(_wrap("F200", 200.0, "I24", 24.0, fill_color="#123456"))
        assert ph.width == 200.0
        assert ph.export_node_id == "F200"


class TestClampHelper:
    def test_replaces_existing_max_width(self) -> None:
        tag = '<img style="display:block;width:100%;max-width:600px;" />'
        out = ComponentRenderer._clamp_img_max_width(tag, 48)
        assert "max-width:48px" in out
        assert "600px" not in out

    def test_inserts_when_absent(self) -> None:
        tag = '<img style="display:block;width:100%;height:auto;" />'
        out = ComponentRenderer._clamp_img_max_width(tag, 48)
        assert "max-width:48px" in out

    def test_noop_when_already_equal(self) -> None:
        tag = '<img style="display: block; width: 100%; max-width: 600px;" />'
        assert ComponentRenderer._clamp_img_max_width(tag, 600) == tag

    def test_noop_without_style(self) -> None:
        tag = '<img src="x.png" width="600" />'
        assert ComponentRenderer._clamp_img_max_width(tag, 48) == tag
