"""Tests for the three _parse_node extraction helpers (Phase 4, F014).

Each test exercises one helper in isolation with a small dict literal that
matches the RawFigmaNode TypedDict shape. The orchestrator (_parse_node) is
already covered end-to-end by test_parse_node_fidelity.py and
test_parse_real_fixtures.py.
"""

from __future__ import annotations

from app.design_sync.figma.raw_types import RawFigmaNode
from app.design_sync.figma.service import (
    _parse_layout_props,
    _parse_text_props,
    _parse_visual_props,
)
from app.design_sync.protocol import DesignNodeType


def test_parse_layout_props_frame_with_autolayout() -> None:
    node: RawFigmaNode = {
        "type": "FRAME",
        "layoutMode": "VERTICAL",
        "paddingTop": 16.0,
        "paddingBottom": 16.0,
        "paddingLeft": 8.0,
        "paddingRight": 8.0,
        "itemSpacing": 12.0,
        "counterAxisSpacing": 4.0,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 400},
        "primaryAxisAlignItems": "CENTER",
        "counterAxisAlignItems": "MIN",
        "cornerRadius": 8.0,
    }
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_mode == "VERTICAL"
    assert out.padding_top == 16.0
    assert out.padding_left == 8.0
    assert out.item_spacing == 12.0
    assert out.counter_axis_spacing == 4.0
    assert out.primary_axis_align == "center"
    assert out.counter_axis_align == "start"
    assert out.corner_radius == 8.0
    assert out.width == 600
    assert out.height == 400


def test_parse_text_props_returns_typography_for_text_node() -> None:
    node: RawFigmaNode = {
        "type": "TEXT",
        "characters": "Hello world",
        "style": {
            "fontFamily": "Inter",
            "fontSize": 24.0,
            "fontWeight": 700,
            "lineHeightPx": 32.0,
            "textCase": "UPPER",
            "textDecoration": "UNDERLINE",
            "textAlignHorizontal": "CENTER",
        },
    }
    out = _parse_text_props(node, DesignNodeType.TEXT)
    assert out.text_content == "Hello world"
    assert out.font_family == "Inter"
    assert out.font_size == 24.0
    assert out.font_weight == 700
    assert out.line_height_px == 32.0
    assert out.text_transform == "uppercase"
    assert out.text_decoration == "underline"
    assert out.text_align == "center"

    # Non-TEXT nodes return all-None / empty tuple
    empty = _parse_text_props({"type": "FRAME"}, DesignNodeType.FRAME)
    assert empty.text_content is None
    assert empty.font_family is None
    assert empty.style_runs == ()


def test_parse_visual_props_reclassifies_vector_with_image_fill() -> None:
    node: RawFigmaNode = {
        "type": "VECTOR",
        "fills": [
            {"type": "IMAGE", "visible": True, "imageRef": "img-123"},
        ],
    }
    out = _parse_visual_props(node, DesignNodeType.VECTOR, node_opacity=1.0)
    assert out.resolved_node_type == DesignNodeType.IMAGE
    assert out.image_ref == "img-123"  # F8: reclassify now also captures the fill's ref
    assert out.fill_color is None

    # An IMAGE fill without an imageRef still reclassifies; the ref stays None.
    no_ref: RawFigmaNode = {"type": "VECTOR", "fills": [{"type": "IMAGE", "visible": True}]}
    no_ref_out = _parse_visual_props(no_ref, DesignNodeType.VECTOR, node_opacity=1.0)
    assert no_ref_out.resolved_node_type == DesignNodeType.IMAGE
    assert no_ref_out.image_ref is None

    # FRAME with IMAGE fill extracts image_ref, no reclassification
    frame_node: RawFigmaNode = {
        "type": "FRAME",
        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "hero-img"}],
    }
    frame_out = _parse_visual_props(frame_node, DesignNodeType.FRAME, node_opacity=1.0)
    assert frame_out.resolved_node_type == DesignNodeType.FRAME
    assert frame_out.image_ref == "hero-img"

    # TEXT with SOLID fill routes color to text_color, not fill_color
    text_node: RawFigmaNode = {
        "type": "TEXT",
        "fills": [
            {"type": "SOLID", "visible": True, "color": {"r": 1.0, "g": 0, "b": 0, "a": 1.0}}
        ],
    }
    text_out = _parse_visual_props(text_node, DesignNodeType.TEXT, node_opacity=1.0)
    assert text_out.text_color == "#FF0000"
    assert text_out.fill_color is None


# ── CE-6 (#424): auto-layout child sizing ──


def test_parse_layout_props_reads_all_sizing_fields_on_autolayout_frame() -> None:
    node: RawFigmaNode = {
        "type": "FRAME",
        "layoutMode": "HORIZONTAL",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "layoutGrow": 1,
        "layoutAlign": "STRETCH",
        "layoutPositioning": "ABSOLUTE",
        "layoutWrap": "WRAP",
        "minWidth": 120,
        "maxWidth": 480,
    }
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_sizing_horizontal == "FILL"
    assert out.layout_sizing_vertical == "HUG"
    assert out.layout_grow == 1.0
    assert out.layout_align == "STRETCH"
    assert out.layout_positioning == "ABSOLUTE"
    assert out.layout_wrap == "WRAP"
    assert out.min_width == 120.0
    assert out.max_width == 480.0


def test_parse_layout_props_reads_sizing_on_non_frame_node() -> None:
    node: RawFigmaNode = {
        "type": "TEXT",
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
        "layoutGrow": 1,
        "layoutAlign": "STRETCH",
    }
    out = _parse_layout_props(node, "TEXT")
    assert out.layout_sizing_horizontal == "FILL"
    assert out.layout_sizing_vertical == "HUG"
    assert out.layout_grow == 1.0
    assert out.layout_align == "STRETCH"
    assert out.layout_wrap is None


def test_parse_layout_props_non_autolayout_frame_keeps_sizing_without_wrap() -> None:
    node: RawFigmaNode = {
        "type": "FRAME",
        "layoutMode": "NONE",
        "layoutSizingHorizontal": "FIXED",
        "layoutWrap": "NO_WRAP",
    }
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_sizing_horizontal == "FIXED"
    assert out.layout_wrap is None


def test_parse_layout_props_rejects_unknown_sizing_values() -> None:
    node: RawFigmaNode = {
        "type": "FRAME",
        "layoutMode": "VERTICAL",
        "layoutSizingHorizontal": "BOGUS",
        "layoutSizingVertical": "fill",
        "layoutAlign": "BOGUS",
        "layoutPositioning": "BOGUS",
        "layoutWrap": "BOGUS",
        "minWidth": "120px",
        "maxWidth": None,
    }
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_sizing_horizontal is None
    assert out.layout_sizing_vertical is None
    assert out.layout_align is None
    assert out.layout_positioning is None
    assert out.layout_wrap is None
    assert out.min_width is None
    assert out.max_width is None


def test_parse_layout_props_absent_sizing_fields_are_none() -> None:
    node: RawFigmaNode = {"type": "FRAME", "layoutMode": "VERTICAL"}
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_sizing_horizontal is None
    assert out.layout_sizing_vertical is None
    assert out.layout_grow is None
    assert out.layout_align is None
    assert out.layout_positioning is None
    assert out.layout_wrap is None
    assert out.min_width is None
    assert out.max_width is None
