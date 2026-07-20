# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
"""JSON serialization and dump/load utilities for diagnostic reports."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, cast

from app.design_sync.diagnose.models import DiagnosticReport
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedGradient,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
    ExtractedVariable,
)


def report_to_dict(report: DiagnosticReport) -> dict[str, Any]:
    """Serialize DiagnosticReport to JSON-safe dict."""
    result: dict[str, Any] = _dataclass_to_dict(report)
    return result


def report_to_json(report: DiagnosticReport, *, indent: int = 2) -> str:
    """Serialize to JSON string."""
    return json.dumps(report_to_dict(report), indent=indent, default=str)


def dump_structure_to_json(structure: DesignFileStructure, path: Path) -> None:
    """Dump DesignFileStructure to JSON for offline diagnostic re-runs."""
    data = _structure_to_dict(structure)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_structure_from_json(path: Path) -> DesignFileStructure:
    """Load DesignFileStructure from a JSON dump file."""
    data = json.loads(path.read_text())
    return _dict_to_structure(data)


def dump_tokens_to_json(tokens: ExtractedTokens, path: Path) -> None:
    """Dump ExtractedTokens to JSON for offline use."""
    data = _dataclass_to_dict(tokens)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_tokens_from_json(path: Path) -> ExtractedTokens:
    """Load ExtractedTokens from a JSON dump file."""
    data = json.loads(path.read_text())
    return _dict_to_tokens(data)


# ── Serialization helpers ──


def _dataclass_to_dict(obj: Any) -> Any:  # noqa: ANN401
    """Recursively convert dataclasses to dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = _dataclass_to_dict(value)
        return result
    if isinstance(obj, (list, tuple)):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, DesignNodeType):
        return obj.value
    return obj


def _structure_to_dict(structure: DesignFileStructure) -> dict[str, Any]:
    """Convert DesignFileStructure to dict with node type serialization."""
    result = _dataclass_to_dict(structure)
    return cast(dict[str, Any], result)  # guaranteed dict for dataclass input


def _node_from_dict(data: dict[str, Any]) -> DesignNode:
    """Reconstruct a DesignNode from a dict."""
    children = [_node_from_dict(c) for c in data.get("children", [])]
    raw_style_runs = data.get("style_runs", ())
    style_runs: tuple[Any, ...] = ()
    if raw_style_runs:
        from app.design_sync.protocol import StyleRun

        style_runs = tuple(StyleRun(**sr) if isinstance(sr, dict) else sr for sr in raw_style_runs)
    raw_radii = data.get("corner_radii")
    corner_radii: tuple[float, ...] | None = tuple(raw_radii) if raw_radii else None
    return DesignNode(
        id=data["id"],
        name=data["name"],
        type=DesignNodeType(data["type"]),
        children=children,
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
        font_weight=data.get("font_weight"),
        line_height_px=data.get("line_height_px"),
        line_height_relative=data.get("line_height_relative"),
        letter_spacing_px=data.get("letter_spacing_px"),
        text_transform=data.get("text_transform"),
        text_decoration=data.get("text_decoration"),
        image_ref=data.get("image_ref"),
        hyperlink=data.get("hyperlink"),
        corner_radius=data.get("corner_radius"),
        corner_radii=corner_radii,
        text_align=data.get("text_align"),
        primary_axis_align=data.get("primary_axis_align"),
        counter_axis_align=data.get("counter_axis_align"),
        stroke_weight=data.get("stroke_weight"),
        stroke_color=data.get("stroke_color"),
        style_runs=style_runs,
        visible=data.get("visible", True),
        opacity=data.get("opacity", 1.0),
        scale_mode=data.get("scale_mode"),
        rotation=data.get("rotation"),
        effects_summary=data.get("effects_summary"),
    )


def _dict_to_structure(data: dict[str, Any]) -> DesignFileStructure:
    """Reconstruct a DesignFileStructure from a dict."""
    pages = [_node_from_dict(p) for p in data.get("pages", [])]
    return DesignFileStructure(file_name=data["file_name"], pages=pages)


def _dict_to_tokens(data: dict[str, Any]) -> ExtractedTokens:
    """Reconstruct ExtractedTokens from a dict."""
    return ExtractedTokens(
        colors=[ExtractedColor(**c) for c in data.get("colors", [])],
        typography=[ExtractedTypography(**t) for t in data.get("typography", [])],
        spacing=[ExtractedSpacing(**s) for s in data.get("spacing", [])],
        variables_source=data.get("variables_source", False),
        modes=data.get("modes"),
        stroke_colors=[ExtractedColor(**c) for c in data.get("stroke_colors", [])],
        variables=[ExtractedVariable(**v) for v in data.get("variables", [])],
        dark_colors=[ExtractedColor(**c) for c in data.get("dark_colors", [])],
        gradients=[
            ExtractedGradient(
                name=g["name"],
                type=g["type"],
                angle=g["angle"],
                stops=tuple(tuple(s) for s in g["stops"]),
                fallback_hex=g["fallback_hex"],
            )
            for g in data.get("gradients", [])
        ],
    )
