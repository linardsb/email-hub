"""Pure helpers for serializing/deserializing design nodes.

Shared by ``ConnectionService`` (sync caching) and ``AssetsService``
(structure read paths). Carved out of the original ``DesignSyncService``
methods of the same names — no state dependencies.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final, cast

from app.design_sync.protocol import DesignNode, DesignNodeType, StyleRun
from app.design_sync.schemas import DesignNodeResponse

_THUMBNAIL_NODE_TYPES: Final[set[str]] = {
    "FRAME",
    "COMPONENT",
    "INSTANCE",
    "GROUP",
    "SECTION",
}
_MAX_THUMBNAIL_CACHE: Final[int] = 100  # Single Figma API call (100 IDs per batch)


def serialize_node(node: DesignNode) -> dict[str, Any]:
    """Serialize a DesignNode to a JSON-safe dict for caching."""
    d: dict[str, Any] = {
        "id": node.id,
        "name": node.name,
        "type": str(node.type),
        "children": [serialize_node(c) for c in node.children],
        "width": node.width,
        "height": node.height,
        "x": node.x,
        "y": node.y,
        "text_content": node.text_content,
    }
    if node.fill_color is not None:
        d["fill_color"] = node.fill_color
    if node.text_color is not None:
        d["text_color"] = node.text_color
    if node.padding_top is not None:
        d["padding_top"] = node.padding_top
    if node.padding_right is not None:
        d["padding_right"] = node.padding_right
    if node.padding_bottom is not None:
        d["padding_bottom"] = node.padding_bottom
    if node.padding_left is not None:
        d["padding_left"] = node.padding_left
    if node.item_spacing is not None:
        d["item_spacing"] = node.item_spacing
    if node.counter_axis_spacing is not None:
        d["counter_axis_spacing"] = node.counter_axis_spacing
    if node.layout_mode is not None:
        d["layout_mode"] = node.layout_mode
    if node.font_family is not None:
        d["font_family"] = node.font_family
    if node.font_size is not None:
        d["font_size"] = node.font_size
    if node.font_weight is not None:
        d["font_weight"] = node.font_weight
    if node.line_height_px is not None:
        d["line_height_px"] = node.line_height_px
    if node.letter_spacing_px is not None:
        d["letter_spacing_px"] = node.letter_spacing_px
    if node.text_transform is not None:
        d["text_transform"] = node.text_transform
    if node.text_decoration is not None:
        d["text_decoration"] = node.text_decoration
    if node.line_height_relative is not None:
        d["line_height_relative"] = node.line_height_relative
    if node.image_ref is not None:
        d["image_ref"] = node.image_ref
    if node.hyperlink is not None:
        d["hyperlink"] = node.hyperlink
    if node.corner_radius is not None:
        d["corner_radius"] = node.corner_radius
    if node.corner_radii is not None:
        d["corner_radii"] = list(node.corner_radii)
    if node.text_align is not None:
        d["text_align"] = node.text_align
    if node.primary_axis_align is not None:
        d["primary_axis_align"] = node.primary_axis_align
    if node.counter_axis_align is not None:
        d["counter_axis_align"] = node.counter_axis_align
    if node.stroke_weight is not None:
        d["stroke_weight"] = node.stroke_weight
    if node.stroke_color is not None:
        d["stroke_color"] = node.stroke_color
    if node.style_runs:
        d["style_runs"] = [dataclasses.asdict(sr) for sr in node.style_runs]
    if not node.visible:
        d["visible"] = False
    if node.opacity != 1.0:
        d["opacity"] = node.opacity
    return d


def collect_top_frame_ids(pages: list[dict[str, Any]]) -> list[str]:
    """Collect frame IDs from cached structure, prioritising top-level email sections."""
    scored: list[tuple[float, str]] = []

    def walk(node: dict[str, Any], depth: int) -> None:
        ntype = str(node.get("type", ""))
        if ntype in _THUMBNAIL_NODE_TYPES:
            area = float(node.get("width", 0)) * float(node.get("height", 0))
            score = 0.0
            if depth == 0:
                score += 1000
            score += min(200.0, area / 1000)
            score += max(0.0, 50 - depth * 10)
            scored.append((score, str(node.get("id", ""))))
        for child in node.get("children", []):
            if isinstance(child, dict):
                walk(cast(dict[str, Any], child), depth + 1)

    for page in pages:
        if isinstance(page, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            for child in page.get("children", []):
                if isinstance(child, dict):
                    walk(cast(dict[str, Any], child), 0)

    scored.sort(key=lambda x: x[0], reverse=True)
    return [sid for _, sid in scored[:_MAX_THUMBNAIL_CACHE]]


def node_to_response(node: DesignNode) -> DesignNodeResponse:
    """Recursively convert protocol DesignNode to response schema."""
    return DesignNodeResponse(
        id=node.id,
        name=node.name,
        type=str(node.type),
        children=[node_to_response(c) for c in node.children],
        width=node.width,
        height=node.height,
        x=node.x,
        y=node.y,
        text_content=node.text_content,
    )


def deserialize_node(data: dict[str, Any]) -> DesignNodeResponse:
    """Deserialize a cached node dict to DesignNodeResponse."""
    children_data = cast(
        list[dict[str, Any]],
        [c for c in data.get("children", []) if isinstance(c, dict)],
    )
    return DesignNodeResponse(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        type=str(data.get("type", "OTHER")),
        children=[deserialize_node(c) for c in children_data],
        width=data.get("width"),
        height=data.get("height"),
        x=data.get("x"),
        y=data.get("y"),
        text_content=data.get("text_content"),
    )


def cached_dict_to_node(data: dict[str, Any]) -> DesignNode:
    """Convert a cached node dict back to a protocol DesignNode."""
    raw_type = str(data.get("type", "OTHER"))
    try:
        node_type = DesignNodeType(raw_type)
    except ValueError:
        node_type = DesignNodeType.OTHER

    raw_fw = data.get("font_weight")
    children_data = cast(
        list[dict[str, Any]],
        [c for c in data.get("children", []) if isinstance(c, dict)],
    )
    raw_radii = cast(list[float] | None, data.get("corner_radii"))
    raw_runs = cast(
        list[dict[str, Any]],
        [sr for sr in data.get("style_runs", []) if isinstance(sr, dict)],
    )
    return DesignNode(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        type=node_type,
        children=[cached_dict_to_node(c) for c in children_data],
        width=data.get("width"),
        height=data.get("height"),
        x=data.get("x"),
        y=data.get("y"),
        text_content=data.get("text_content"),
        fill_color=data.get("fill_color"),
        text_color=data.get("text_color"),
        padding_top=data.get("padding_top"),
        padding_right=data.get("padding_right"),
        padding_bottom=data.get("padding_bottom"),
        padding_left=data.get("padding_left"),
        item_spacing=data.get("item_spacing"),
        counter_axis_spacing=data.get("counter_axis_spacing"),
        layout_mode=data.get("layout_mode"),
        font_family=data.get("font_family"),
        font_size=data.get("font_size"),
        font_weight=int(raw_fw) if isinstance(raw_fw, (int, float)) else None,
        line_height_px=data.get("line_height_px"),
        line_height_relative=data.get("line_height_relative"),
        letter_spacing_px=data.get("letter_spacing_px"),
        text_transform=data.get("text_transform"),
        text_decoration=data.get("text_decoration"),
        image_ref=data.get("image_ref"),
        hyperlink=data.get("hyperlink"),
        corner_radius=data.get("corner_radius"),
        corner_radii=tuple(raw_radii) if raw_radii else None,
        text_align=data.get("text_align"),
        primary_axis_align=data.get("primary_axis_align"),
        counter_axis_align=data.get("counter_axis_align"),
        stroke_weight=data.get("stroke_weight"),
        stroke_color=data.get("stroke_color"),
        style_runs=tuple(StyleRun(**sr) for sr in raw_runs),
        visible=bool(data.get("visible", True)),
        opacity=float(data.get("opacity", 1.0)),
    )
