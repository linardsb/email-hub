"""Shared fixtures for design_sync tests."""

from __future__ import annotations

import dataclasses
from typing import Any

from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    StyleRun,
)


def make_design_node(
    id: str = "node1",
    name: str = "Frame",
    type: DesignNodeType = DesignNodeType.FRAME,
    children: list[DesignNode] | None = None,
    **overrides: Any,
) -> DesignNode:
    """Build a DesignNode with sensible defaults — override any field via kwargs."""
    defaults: dict[str, Any] = {
        "id": id,
        "name": name,
        "type": type,
        "children": children or [],
        "width": 600.0,
        "height": 400.0,
        "x": 0.0,
        "y": 0.0,
        "visible": True,
        "opacity": 1.0,
    }
    defaults.update(overrides)
    return DesignNode(**defaults)


def make_file_structure(
    *frames: DesignNode,
    file_name: str = "test",
) -> DesignFileStructure:
    """Wrap frames into a single-page DesignFileStructure."""
    page = make_design_node(
        id="page1",
        name="Page",
        type=DesignNodeType.PAGE,
        children=list(frames),
    )
    return DesignFileStructure(file_name=file_name, pages=[page])


def make_full_design_node() -> DesignNode:
    """A DesignNode carrying a distinct, non-default value on EVERY field.

    Distinct values make a silently-dropped field surface as ``got != node``
    (the loader falls the field back to None / its default).
    """
    child = DesignNode(id="child-1", name="child", type=DesignNodeType.TEXT, text_content="c")
    return DesignNode(
        id="node-diag-1",
        name="diag-node",
        type=DesignNodeType.TEXT,
        children=[child],
        width=520.0,
        height=44.0,
        x=12.0,
        y=34.0,
        text_content="Hello diagnose",
        fill_color="#112233",
        text_color="#445566",
        padding_top=1.0,
        padding_right=2.0,
        padding_bottom=3.0,
        padding_left=4.0,
        item_spacing=8.0,
        counter_axis_spacing=6.0,
        layout_mode="HORIZONTAL",
        font_family="Noto Sans",
        font_size=14.0,
        font_weight=700,
        line_height_px=20.0,
        line_height_relative=1.4,  # the 52.5 field the loader dropped
        letter_spacing_px=0.5,
        text_transform="uppercase",
        text_decoration="underline",
        image_ref="ref-hash-abc",
        hyperlink="https://example.com/x",
        corner_radius=25.0,
        corner_radii=(4.0, 4.0, 12.0, 12.0),
        text_align="center",
        primary_axis_align="space-between",
        counter_axis_align="center",
        stroke_weight=2.0,
        stroke_color="#778899",
        style_runs=(StyleRun(start=0, end=5, bold=True, color_hex="#000000"),),
        visible=False,
        opacity=0.5,
        scale_mode="FILL",
        rotation=1.5,
        effects_summary="1:DROP_SHADOW",
        layout_sizing_horizontal="FILL",
        layout_sizing_vertical="HUG",
        layout_grow=1.0,
        layout_align="STRETCH",
        layout_positioning="ABSOLUTE",
        layout_wrap="WRAP",
        min_width=120.0,
        max_width=480.0,
    )


def non_default_field_names(node: DesignNode) -> set[str]:
    """Names of the fields on ``node`` that differ from their declared default.

    A field with no default at all (``id``, ``name``, ``type``) always counts.
    """
    names: set[str] = set()
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if f.default is not dataclasses.MISSING:
            if value != f.default:
                names.add(f.name)
        elif f.default_factory is not dataclasses.MISSING:
            if value != f.default_factory():
                names.add(f.name)
        else:
            names.add(f.name)
    return names
