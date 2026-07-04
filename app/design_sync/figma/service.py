"""Figma design sync provider — calls the Figma REST API."""

from __future__ import annotations

import asyncio
import contextlib
import math
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.exceptions import SyncFailedError
from app.design_sync.figma.raw_types import (
    RawFigmaGradientHandle,
    RawFigmaGradientStop,
    RawFigmaNode,
    RawFigmaTextStyle,
    RawFigmaVariable,
    RawVariablesResponse,
)
from app.design_sync.protocol import (
    DesignComponent,
    DesignFile,
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExportedImage,
    ExtractedColor,
    ExtractedGradient,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
    ExtractedVariable,
    StyleRun,
)

if TYPE_CHECKING:
    from app.design_sync.email_design_document import EmailDesignDocument
    from app.design_sync.token_transforms import TokenWarning

logger = get_logger(__name__)

_FIGMA_FILE_KEY_RE = re.compile(r"figma\.com/(?:design|file|proto|board|embed)/([a-zA-Z0-9]+)")
_FIGMA_API = "https://api.figma.com"
_TIMEOUT = 60.0
_MAX_WALK_DEPTH = 500
_MAX_PARSE_DEPTH = 30  # Hard ceiling for _parse_node recursion (Figma rarely exceeds ~15)
_MAX_ALIAS_DEPTH = 10


def _find_subtree(document: RawFigmaNode, node_id: str) -> RawFigmaNode | None:
    """Find a node by ID in the Figma document tree, returning the full subtree."""
    if str(document.get("id", "")) == node_id:
        return document
    for child in document.get("children", []):
        if isinstance(child, dict):
            result = _find_subtree(cast(RawFigmaNode, child), node_id)
            if result is not None:
                return result
    return None


_FIGMA_NODE_TYPE_MAP: dict[str, DesignNodeType] = {
    "DOCUMENT": DesignNodeType.OTHER,
    "CANVAS": DesignNodeType.PAGE,
    "FRAME": DesignNodeType.FRAME,
    "GROUP": DesignNodeType.GROUP,
    "COMPONENT": DesignNodeType.COMPONENT,
    "COMPONENT_SET": DesignNodeType.COMPONENT,
    "INSTANCE": DesignNodeType.INSTANCE,
    "TEXT": DesignNodeType.TEXT,
    "RECTANGLE": DesignNodeType.VECTOR,
    "ELLIPSE": DesignNodeType.VECTOR,
    "LINE": DesignNodeType.VECTOR,
    "VECTOR": DesignNodeType.VECTOR,
    "BOOLEAN_OPERATION": DesignNodeType.VECTOR,
    "STAR": DesignNodeType.VECTOR,
    "REGULAR_POLYGON": DesignNodeType.VECTOR,
}

# Figma text property maps
_TEXT_CASE_MAP: dict[str, str] = {"UPPER": "uppercase", "LOWER": "lowercase", "TITLE": "capitalize"}
_TEXT_DEC_MAP: dict[str, str] = {"UNDERLINE": "underline", "STRIKETHROUGH": "line-through"}
_TEXT_ALIGN_MAP: dict[str, str] = {
    "LEFT": "left",
    "CENTER": "center",
    "RIGHT": "right",
    "JUSTIFIED": "justify",
}
_AXIS_ALIGN_MAP: dict[str, str] = {
    "MIN": "start",
    "CENTER": "center",
    "MAX": "end",
    "SPACE_BETWEEN": "space-between",
    "SPACE_AROUND": "space-around",
}
_HYPERLINK_SCHEMES = frozenset({"http", "https", "mailto"})


def _validate_hyperlink(raw: Any) -> str | None:
    """Extract and validate hyperlink URL. Reject javascript: etc."""
    if isinstance(raw, dict):
        url = cast(dict[str, Any], raw).get("url", "")
    elif isinstance(raw, str):
        url = raw
    else:
        return None
    if not url or not isinstance(url, str):
        return None
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _HYPERLINK_SCHEMES:
        return None
    return str(url)


def _extract_stroke(
    node_data: RawFigmaNode, node_opacity: float, bg_hex: str = "#FFFFFF"
) -> tuple[str | None, float | None]:
    """Extract first SOLID stroke color and weight from a Figma node."""
    raw_strokes = node_data.get("strokes", [])
    for stroke in raw_strokes:
        if not isinstance(stroke, dict):
            continue
        s_d = cast(dict[str, Any], stroke)
        if s_d.get("visible") is False:
            continue
        if s_d.get("type") != "SOLID":
            continue
        c = s_d.get("color")
        if not isinstance(c, dict):
            continue
        c_d = cast(dict[str, Any], c)
        hex_val = _rgba_to_hex_with_opacity(
            float(c_d.get("r", 0)),
            float(c_d.get("g", 0)),
            float(c_d.get("b", 0)),
            fill_alpha=float(c_d.get("a", 1.0)),
            node_opacity=node_opacity,
            bg_hex=bg_hex,
        )
        weight = _float_or_none(node_data.get("strokeWeight"))
        return hex_val, weight
    return None, None


def _parse_style_runs(node_data: RawFigmaNode) -> tuple[StyleRun, ...]:
    """Parse Figma characterStyleOverrides + styleOverrideTable into StyleRun tuple."""
    overrides_list = node_data.get("characterStyleOverrides", [])
    table_d = node_data.get("styleOverrideTable", {})
    if not overrides_list or not table_d:
        return ()

    characters = node_data.get("characters", "")
    if not characters:
        return ()

    # Group contiguous runs by override ID
    runs: list[StyleRun] = []
    i = 0
    while i < len(overrides_list):
        override_id: int = int(overrides_list[i])
        if override_id == 0:
            i += 1
            continue
        start = i
        while i < len(overrides_list) and int(overrides_list[i]) == override_id:
            i += 1
        end = i

        style_key = str(override_id)
        style_data = table_d.get(style_key)
        if not isinstance(style_data, dict):
            continue
        sd = cast(RawFigmaTextStyle, style_data)

        fw = sd.get("fontWeight")
        is_bold = isinstance(fw, (int, float)) and int(fw) >= 700
        italic_name = str(sd.get("fontPostScriptName", ""))
        is_italic = "italic" in italic_name.lower() or sd.get("italic") is True

        color_hex: str | None = None
        fills_raw = sd.get("fills", [])
        for fill in fills_raw:
            if not isinstance(fill, dict):
                continue
            f_d = cast(dict[str, Any], fill)
            if f_d.get("type") == "SOLID":
                c = f_d.get("color")
                if isinstance(c, dict):
                    c_d = cast(dict[str, Any], c)
                    color_hex = _rgba_to_hex(
                        float(c_d.get("r", 0)),
                        float(c_d.get("g", 0)),
                        float(c_d.get("b", 0)),
                    )
                break

        link_url: str | None = None
        raw_link = sd.get("hyperlink")
        if raw_link:
            link_url = _validate_hyperlink(raw_link)

        font_size = _float_or_none(sd.get("fontSize"))

        runs.append(
            StyleRun(
                start=start,
                end=end,
                bold=is_bold,
                italic=is_italic,
                underline=str(sd.get("textDecoration", "")).upper() == "UNDERLINE",
                strikethrough=str(sd.get("textDecoration", "")).upper() == "STRIKETHROUGH",
                color_hex=color_hex,
                font_size=font_size,
                link_url=link_url,
            )
        )

    return tuple(runs)


def _parse_letter_spacing(style_dict: RawFigmaTextStyle, font_size: float) -> float | None:
    """Parse Figma letterSpacing to px value."""
    raw: Any = style_dict.get("letterSpacing", {})
    if isinstance(raw, dict):
        raw_dict = cast(dict[str, Any], raw)
        if raw_dict.get("unit") == "PIXELS":
            val = raw_dict.get("value")
            return float(val) if isinstance(val, (int, float)) else None
        if raw_dict.get("unit") == "PERCENT" and font_size:
            return round(font_size * float(raw_dict.get("value", 0)) / 100, 1)
    elif isinstance(raw, (int, float)):
        return float(raw)
    return None


def extract_file_key(url: str) -> str:
    """Extract the Figma file key from a URL.

    Raises:
        SyncFailedError: If the URL doesn't contain a valid file key.
    """
    m = _FIGMA_FILE_KEY_RE.search(url)
    if not m:
        raise SyncFailedError(
            "Invalid Figma URL. Expected format: figma.com/design/<file_key>/... "
            "(also accepts /file/, /proto/, /board/, /embed/ paths)"
        )
    return m.group(1)


def _rgba_to_hex(r: float, g: float, b: float) -> str:
    """Convert Figma RGBA floats (0-1) to hex string."""
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _rgba_to_hex_with_opacity(
    r: float,
    g: float,
    b: float,
    fill_alpha: float = 1.0,
    node_opacity: float = 1.0,
    bg_hex: str = "#FFFFFF",
) -> str:
    """Convert RGBA + node opacity to composited hex against a background."""
    eff_alpha = fill_alpha * node_opacity
    if eff_alpha >= 0.999:
        return _rgba_to_hex(r, g, b)
    # Parse background hex (fall back to white on malformed input)
    try:
        _bg_r = int(bg_hex[1:3], 16)
        _bg_g = int(bg_hex[3:5], 16)
        _bg_b = int(bg_hex[5:7], 16)
    except (ValueError, IndexError):
        _bg_r, _bg_g, _bg_b = 255, 255, 255
    bg_r = _bg_r / 255.0
    bg_g = _bg_g / 255.0
    bg_b = _bg_b / 255.0
    # Alpha-composite each channel
    final_r = r * eff_alpha + bg_r * (1 - eff_alpha)
    final_g = g * eff_alpha + bg_g * (1 - eff_alpha)
    final_b = b * eff_alpha + bg_b * (1 - eff_alpha)
    return _rgba_to_hex(final_r, final_g, final_b)


def _gradient_midpoint_hex(gradient_stops: list[RawFigmaGradientStop]) -> str | None:
    """Average RGB of first and last gradient stop. Returns None if < 2 stops."""
    if len(gradient_stops) < 2:
        return None
    first = gradient_stops[0].get("color")
    last = gradient_stops[-1].get("color")
    if not isinstance(first, dict) or not isinstance(last, dict):
        return None
    first_d = cast(dict[str, Any], first)
    last_d = cast(dict[str, Any], last)
    avg_r = (float(first_d.get("r", 0)) + float(last_d.get("r", 0))) / 2
    avg_g = (float(first_d.get("g", 0)) + float(last_d.get("g", 0))) / 2
    avg_b = (float(first_d.get("b", 0)) + float(last_d.get("b", 0))) / 2
    return _rgba_to_hex(avg_r, avg_g, avg_b)


def _float_or_none(val: Any) -> float | None:
    """Convert a value to float if numeric, otherwise None."""
    return float(val) if isinstance(val, (int, float)) else None


def _compute_gradient_angle(handles: list[RawFigmaGradientHandle]) -> float:
    """Compute CSS gradient angle from Figma handle positions."""
    if len(handles) < 2:
        return 180.0  # default top-to-bottom
    h1 = handles[0]
    h2 = handles[1]
    dx = float(h2.get("x", 0)) - float(h1.get("x", 0))
    dy = float(h2.get("y", 0)) - float(h1.get("y", 0))
    # Figma: (0,0)=top-left. CSS: 0deg=to-top, 180deg=to-bottom
    angle = math.degrees(math.atan2(dx, -dy)) % 360
    return round(angle, 1)


def _parse_gradient_stops(
    stops_raw: list[Any], *, bg_hex: str = "#FFFFFF"
) -> list[tuple[str, float]]:
    """Parse Figma gradientStops into (hex, position) tuples."""
    result: list[tuple[str, float]] = []
    for stop_raw in stops_raw:
        if not isinstance(stop_raw, dict):
            continue
        stop = cast(dict[str, Any], stop_raw)
        color_raw = stop.get("color")
        pos = float(stop.get("position", 0))
        if isinstance(color_raw, dict):
            c = cast(dict[str, Any], color_raw)
            hex_val = _rgba_to_hex_with_opacity(
                float(c.get("r", 0)),
                float(c.get("g", 0)),
                float(c.get("b", 0)),
                fill_alpha=float(c.get("a", 1.0)),
                bg_hex=bg_hex,
            )
            result.append((hex_val, round(pos, 3)))
    return result


# ── _parse_node extraction helpers (Phase 4) ──
#
# `_parse_node` historically owned every Figma-node-to-DesignNode concern in
# one 200+ LOC function. The three helpers below slice it into layout, text,
# and visual concerns so each can be unit-tested in isolation. Each one is
# module-level (no ``self``), takes a typed ``RawFigmaNode``, and returns a
# NamedTuple. Helper bodies are line-equivalent to the original; the only
# behaviour change is the IMAGE-fill reclassification, which is now returned
# in ``_VisualProps.resolved_node_type`` instead of mutating ``node_type``.


class _LayoutProps(NamedTuple):
    width: float | None
    height: float | None
    x: float | None
    y: float | None
    padding_top: float | None
    padding_right: float | None
    padding_bottom: float | None
    padding_left: float | None
    item_spacing: float | None
    counter_axis_spacing: float | None
    layout_mode: str | None
    primary_axis_align: str | None
    counter_axis_align: str | None
    corner_radius: float | None
    corner_radii: tuple[float, ...] | None


def _parse_layout_props(node_data: RawFigmaNode, raw_type: str) -> _LayoutProps:
    """Extract dimensions, auto-layout, axis alignment, and corner radius."""
    # Dimensions from absoluteBoundingBox
    bbox = node_data.get("absoluteBoundingBox")
    width: float | None = None
    height: float | None = None
    x: float | None = None
    y: float | None = None
    if isinstance(bbox, dict):
        bbox_d = cast(dict[str, Any], bbox)
        raw_w, raw_h = bbox_d.get("width"), bbox_d.get("height")
        raw_x, raw_y = bbox_d.get("x"), bbox_d.get("y")
        width = float(raw_w) if isinstance(raw_w, (int, float)) else None
        height = float(raw_h) if isinstance(raw_h, (int, float)) else None
        x = float(raw_x) if isinstance(raw_x, (int, float)) else None
        y = float(raw_y) if isinstance(raw_y, (int, float)) else None

    # Auto-layout (FRAME-like only, and only when layoutMode is set/non-NONE)
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None
    item_spacing: float | None = None
    counter_axis_spacing: float | None = None
    layout_mode_str: str | None = None
    if raw_type in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE"):
        layout_mode_str = node_data.get("layoutMode")
        if layout_mode_str and layout_mode_str != "NONE":
            padding_top = _float_or_none(node_data.get("paddingTop"))
            padding_right = _float_or_none(node_data.get("paddingRight"))
            padding_bottom = _float_or_none(node_data.get("paddingBottom"))
            padding_left = _float_or_none(node_data.get("paddingLeft"))
            item_spacing = _float_or_none(node_data.get("itemSpacing"))
            counter_axis_spacing = _float_or_none(node_data.get("counterAxisSpacing"))

    # Axis alignment (FRAME-like)
    primary_axis_align: str | None = None
    counter_axis_align: str | None = None
    if raw_type in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE"):
        primary_axis_align = _AXIS_ALIGN_MAP.get(str(node_data.get("primaryAxisAlignItems", "")))
        counter_axis_align = _AXIS_ALIGN_MAP.get(str(node_data.get("counterAxisAlignItems", "")))

    # Corner radius (FRAME-like + RECTANGLE)
    corner_radius: float | None = None
    corner_radii: tuple[float, ...] | None = None
    if raw_type in ("FRAME", "RECTANGLE", "COMPONENT", "COMPONENT_SET", "INSTANCE"):
        corner_radius = _float_or_none(node_data.get("cornerRadius"))
        raw_rcr = node_data.get("rectangleCornerRadii", [])
        if len(raw_rcr) >= 4:
            with contextlib.suppress(TypeError, ValueError):
                corner_radii = tuple(float(v) for v in raw_rcr[:4])

    return _LayoutProps(
        width=width,
        height=height,
        x=x,
        y=y,
        padding_top=padding_top,
        padding_right=padding_right,
        padding_bottom=padding_bottom,
        padding_left=padding_left,
        item_spacing=item_spacing,
        counter_axis_spacing=counter_axis_spacing,
        layout_mode=layout_mode_str,
        primary_axis_align=primary_axis_align,
        counter_axis_align=counter_axis_align,
        corner_radius=corner_radius,
        corner_radii=corner_radii,
    )


class _TextProps(NamedTuple):
    text_content: str | None
    font_family: str | None
    font_size: float | None
    font_weight: int | None
    line_height_px: float | None
    line_height_relative: float | None
    letter_spacing_px: float | None
    text_transform: str | None
    text_decoration: str | None
    text_align: str | None
    style_runs: tuple[StyleRun, ...]


def _parse_text_props(node_data: RawFigmaNode, node_type: DesignNodeType) -> _TextProps:
    """Extract text content + typography + alignment + rich-text overrides.

    All fields are ``None``/``()`` for non-TEXT nodes. Hyperlink is **not**
    here — it lives in ``_parse_visual_props`` because Figma allows hyperlinks
    on FRAME nodes too, not just TEXT.
    """
    if node_type != DesignNodeType.TEXT:
        return _TextProps(
            text_content=None,
            font_family=None,
            font_size=None,
            font_weight=None,
            line_height_px=None,
            line_height_relative=None,
            letter_spacing_px=None,
            text_transform=None,
            text_decoration=None,
            text_align=None,
            style_runs=(),
        )

    # Text content
    text_content: str | None = None
    raw_chars = node_data.get("characters")
    if isinstance(raw_chars, str) and raw_chars.strip():
        text_content = raw_chars.strip()

    # Typography from style dict
    font_family: str | None = None
    font_size: float | None = None
    font_weight: int | None = None
    line_height_px: float | None = None
    line_height_relative: float | None = None
    letter_spacing_px: float | None = None
    text_transform: str | None = None
    text_decoration: str | None = None
    style_raw: Any = node_data.get("style", {})
    if isinstance(style_raw, dict):
        style = cast(RawFigmaTextStyle, style_raw)
        raw_ff = style.get("fontFamily")
        font_family = str(raw_ff) if isinstance(raw_ff, str) else None
        raw_fs = style.get("fontSize")
        font_size = float(raw_fs) if isinstance(raw_fs, (int, float)) else None
        raw_fw = style.get("fontWeight")
        font_weight = int(raw_fw) if isinstance(raw_fw, (int, float)) else None
        raw_lh = style.get("lineHeightPx")
        line_height_px = float(raw_lh) if isinstance(raw_lh, (int, float)) else None
        if line_height_px is None:
            # AUTO/% line height (52.5): prefer percent-of-font-size, fall back
            # to legacy percent-of-default (1.2 ≈ "normal", matching the
            # _walk_for_typography convention).
            raw_pfs = style.get("lineHeightPercentFontSize")
            raw_pct = style.get("lineHeightPercent")
            if isinstance(raw_pfs, (int, float)):
                line_height_relative = round(float(raw_pfs) / 100, 3)
            elif isinstance(raw_pct, (int, float)):
                line_height_relative = round(float(raw_pct) / 100 * 1.2, 3)
        letter_spacing_px = _parse_letter_spacing(
            style, font_size if font_size is not None else 16.0
        )
        text_transform = _TEXT_CASE_MAP.get(str(style.get("textCase", "")))
        text_decoration = _TEXT_DEC_MAP.get(str(style.get("textDecoration", "")))

    # Text alignment (read style a second time, mirroring the original
    # _parse_node — both reads return the same dict; the duplication is
    # preserved for byte-identical behaviour).
    text_align: str | None = None
    style_for_align: Any = node_data.get("style", {})
    if isinstance(style_for_align, dict):
        sa_d = cast(dict[str, Any], style_for_align)
        text_align = _TEXT_ALIGN_MAP.get(str(sa_d.get("textAlignHorizontal", "")))

    # Style runs (rich text overrides)
    style_runs = _parse_style_runs(node_data)

    return _TextProps(
        text_content=text_content,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
        line_height_px=line_height_px,
        line_height_relative=line_height_relative,
        letter_spacing_px=letter_spacing_px,
        text_transform=text_transform,
        text_decoration=text_decoration,
        text_align=text_align,
        style_runs=style_runs,
    )


class _VisualProps(NamedTuple):
    fill_color: str | None
    text_color: str | None
    image_ref: str | None
    stroke_color: str | None
    stroke_weight: float | None
    hyperlink: str | None
    # Possibly-reclassified node type (IMAGE fills on VECTOR/RECTANGLE).
    resolved_node_type: DesignNodeType


def _parse_visual_props(
    node_data: RawFigmaNode,
    node_type: DesignNodeType,
    node_opacity: float,
    bg_hex: str = "#FFFFFF",
) -> _VisualProps:
    """Extract fills (color/image), strokes, and hyperlink decoration.

    ``bg_hex`` is the nearest ancestor's resolved fill — translucent fills and
    strokes composite against it instead of assuming a white backdrop (52.5).

    May reclassify ``node_type`` to ``IMAGE`` if a VECTOR/RECTANGLE node
    carries an IMAGE fill. The resolved type comes back in
    ``resolved_node_type`` so the caller can rebind. The color-routing branch
    uses the *original* ``node_type`` (text_color vs fill_color), matching
    the original ``_parse_node`` ordering — see the executor note in
    ``.agents/plans/tech-debt-15-figma-typed-boundaries.md``.
    """
    # Hyperlink (TEXT and FRAME nodes — node_type agnostic)
    hyperlink: str | None = None
    raw_hyperlink = node_data.get("hyperlink")
    if raw_hyperlink:
        hyperlink = _validate_hyperlink(raw_hyperlink)

    # Fills (image_ref + fill_color/text_color + possible reclassification)
    fill_color: str | None = None
    text_color: str | None = None
    image_ref: str | None = None
    resolved_node_type = node_type
    raw_fills = node_data.get("fills", [])
    for fill_item in reversed(raw_fills):
        if not isinstance(fill_item, dict):
            continue
        fi_d = cast(dict[str, Any], fill_item)
        if fi_d.get("visible") is False:
            continue
        fill_type = fi_d.get("type")
        # Reclassify VECTOR/RECTANGLE with IMAGE fill as IMAGE
        if fill_type == "IMAGE" and resolved_node_type in (
            DesignNodeType.VECTOR,
            DesignNodeType.IMAGE,
        ):
            resolved_node_type = DesignNodeType.IMAGE
            # Capture the fill's imageRef too (mirrors the FRAME-background
            # branch below). Assets resolve by node-id today so output is
            # unchanged, but this closes the latent trap under the FRAME-bg
            # gate (layout_analyzer.py) before 53.3 builds on it.
            raw_ref = fi_d.get("imageRef")
            if isinstance(raw_ref, str) and raw_ref:
                image_ref = raw_ref
            continue
        # Extract IMAGE fill reference on FRAME nodes (hero/section backgrounds)
        if fill_type == "IMAGE" and resolved_node_type == DesignNodeType.FRAME:
            raw_ref = fi_d.get("imageRef")
            if isinstance(raw_ref, str) and raw_ref:
                image_ref = raw_ref
            continue
        if fill_type != "SOLID":
            continue
        c = fi_d.get("color", {})
        if isinstance(c, dict):
            c_d = cast(dict[str, Any], c)
            hex_val = _rgba_to_hex_with_opacity(
                float(c_d.get("r", 0)),
                float(c_d.get("g", 0)),
                float(c_d.get("b", 0)),
                fill_alpha=float(c_d.get("a", 1.0)),
                node_opacity=node_opacity,
                bg_hex=bg_hex,
            )
            if resolved_node_type == DesignNodeType.TEXT:
                text_color = hex_val
            else:
                fill_color = hex_val
            break

    # Strokes
    stroke_color, stroke_weight = _extract_stroke(node_data, node_opacity, bg_hex=bg_hex)

    return _VisualProps(
        fill_color=fill_color,
        text_color=text_color,
        image_ref=image_ref,
        stroke_color=stroke_color,
        stroke_weight=stroke_weight,
        hyperlink=hyperlink,
        resolved_node_type=resolved_node_type,
    )


class FigmaDesignSyncService:
    """Real Figma API integration."""

    async def list_files(self, access_token: str) -> list[DesignFile]:
        """List recent Figma files using GET /v1/me/files/recents."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_FIGMA_API}/v1/me/files/recents",
                headers={"X-Figma-Token": access_token},
            )
        if resp.status_code == 403:
            raise SyncFailedError("Figma access denied. Check your Personal Access Token.")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            raise SyncFailedError(
                f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
            )
        if resp.status_code != 200:
            logger.warning("design_sync.figma.list_files_failed", status=resp.status_code)
            return []

        data: dict[str, Any] = resp.json()
        files: list[DesignFile] = []
        for item in data.get("files", []):
            if not isinstance(item, dict):
                continue
            item_d = cast(dict[str, Any], item)
            file_key = str(item_d.get("key", ""))
            name = str(item_d.get("name", "Untitled"))
            thumbnail = item_d.get("thumbnail_url")
            last_modified_raw = item_d.get("last_modified")
            last_modified: datetime | None = None
            if isinstance(last_modified_raw, str):
                with contextlib.suppress(ValueError):
                    last_modified = datetime.fromisoformat(last_modified_raw)
            files.append(
                DesignFile(
                    file_id=file_key,
                    name=name,
                    url=f"https://www.figma.com/design/{file_key}",
                    thumbnail_url=str(thumbnail) if thumbnail else None,
                    last_modified=last_modified,
                    folder=str(item_d.get("folder", {}).get("name"))
                    if isinstance(item_d.get("folder"), dict)
                    else None,
                )
            )

        logger.info("design_sync.figma.files_listed", count=len(files))
        return files

    async def validate_connection(self, file_ref: str, access_token: str) -> bool:
        """Check that the PAT can access the file."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}",
                headers={"X-Figma-Token": access_token},
                params={"depth": 1},
            )
        if resp.status_code == 403:
            raise SyncFailedError("Figma access denied. Check your Personal Access Token.")
        if resp.status_code == 404:
            raise SyncFailedError("Figma file not found. Check the file URL.")
        if resp.status_code == 429:
            # Rate-limited but token/file may be valid — allow connection creation
            # so the user isn't blocked. Sync will verify access later.
            logger.warning(
                "design_sync.figma.validate_rate_limited",
                file_ref=file_ref,
                retry_after=resp.headers.get("Retry-After", "unknown"),
            )
            return True
        if resp.status_code != 200:
            raise SyncFailedError(f"Figma API error (HTTP {resp.status_code})")
        return True

    async def sync_tokens(
        self, file_ref: str, access_token: str, *, target_node_id: str | None = None
    ) -> ExtractedTokens:
        """Fetch styles from Figma and parse into design tokens."""
        tokens, _ = await self.sync_tokens_and_structure(
            file_ref, access_token, target_node_id=target_node_id
        )
        return tokens

    async def sync_tokens_and_structure(
        self, file_ref: str, access_token: str, *, target_node_id: str | None = None
    ) -> tuple[ExtractedTokens, DesignFileStructure]:
        """Fetch file once and extract both tokens and structure from the same response."""
        headers = {"X-Figma-Token": access_token}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Fetch file for document tree (auto-layout spacing)
            file_resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}",
                headers=headers,
            )
            if file_resp.status_code == 429:
                retry_after = file_resp.headers.get("Retry-After", "60")
                raise SyncFailedError(
                    f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
                )
            if file_resp.status_code != 200:
                raise SyncFailedError(f"Figma file API error (HTTP {file_resp.status_code})")

            # Fetch published styles
            styles_resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}/styles",
                headers=headers,
            )

        file_data: dict[str, Any] = file_resp.json()
        styles_data: dict[str, Any] = styles_resp.json() if styles_resp.status_code == 200 else {}

        from app.design_sync.tuning import OPACITY_COMPOSITE_BG

        settings = get_settings()
        bg_hex = OPACITY_COMPOSITE_BG

        # Scope token extraction to target frame subtree (Phase 49.6)
        token_scoping = settings.design_sync.token_scoping_enabled and target_node_id is not None
        document_root = file_data.get("document", {})
        if token_scoping and target_node_id is not None:
            subtree = _find_subtree(document_root, target_node_id)
            walk_root = subtree if subtree is not None else document_root
            if subtree is None:
                logger.warning(
                    "design_sync.figma.token_scoping_target_not_found",
                    target_node_id=target_node_id,
                )
        else:
            walk_root = document_root

        # Build scoped file_data for parse methods (they expect {"document": ..., "styles": ...})
        scoped_file_data: dict[str, Any] = {
            "document": walk_root,
            "styles": file_data.get("styles", {}),
        }

        # Variables-first token extraction
        var_colors: list[ExtractedColor] = []
        var_variables: list[ExtractedVariable] = []
        var_modes: dict[str, str] = {}
        var_dark_colors: list[ExtractedColor] = []
        variables_source = False

        if settings.design_sync.figma_variables_enabled:
            try:
                raw_vars = await self._fetch_variables(file_ref, access_token)
                if raw_vars is not None:
                    var_colors, _var_typography, var_variables, var_modes, var_dark_colors = (
                        self._parse_variables(raw_vars, bg_hex=bg_hex)
                    )
                    if var_colors:
                        variables_source = True
            except SyncFailedError:
                raise
            except Exception:
                logger.warning("design_sync.figma.variables_parse_failed", exc_info=True)

        # Styles/node-walk fallback (or supplement)
        gradients: list[ExtractedGradient] = []
        if variables_source:
            colors = var_colors
            stroke_colors: list[ExtractedColor] = []
            # Always walk for gradients even in variables_source mode
            grad_list: list[ExtractedGradient] = []
            self._walk_for_colors(walk_root, [], set(), gradients=grad_list, bg_hex=bg_hex)
            gradients = grad_list
        else:
            colors, stroke_colors, gradients = self._parse_colors(
                scoped_file_data, styles_data, bg_hex=bg_hex
            )

        typography = self._parse_typography(scoped_file_data, styles_data)
        spacing = self._parse_spacing(scoped_file_data)

        logger.info(
            "design_sync.figma.tokens_extracted",
            colors=len(colors),
            dark_colors=len(var_dark_colors),
            typography=len(typography),
            spacing=len(spacing),
            gradients=len(gradients),
            variables_source=variables_source,
        )

        if token_scoping:
            logger.info(
                "design_sync.figma.tokens_scoped",
                target_node_id=target_node_id,
                colors=len(colors),
                typography=len(typography),
                spacing=len(spacing),
            )

        tokens = ExtractedTokens(
            colors=colors,
            typography=typography,
            spacing=spacing,
            variables_source=variables_source,
            modes=var_modes or None,
            stroke_colors=stroke_colors if not variables_source else [],
            variables=var_variables,
            dark_colors=var_dark_colors if variables_source else [],
            gradients=gradients,
        )

        # Parse file structure from the same response (no extra API call)
        file_name = str(file_data.get("name", "Untitled"))
        document = file_data.get("document", {})
        pages: list[DesignNode] = []
        for page_data in document.get("children", []):
            if isinstance(page_data, dict):
                pages.append(
                    self._parse_node(cast(RawFigmaNode, page_data), current_depth=0, max_depth=None)
                )

        # Full-design PNG fetch (Phase 50.1) — only when a target frame is selected
        # so token-only callers don't pay an extra API roundtrip.
        design_image: bytes | None = None
        if target_node_id and settings.design_sync.full_design_png_enabled:
            design_image = await self._export_full_frame_png(file_ref, access_token, target_node_id)

        structure = DesignFileStructure(file_name=file_name, pages=pages, design_image=design_image)

        return tokens, structure

    async def build_document(
        self,
        file_ref: str,
        access_token: str,
        *,
        selected_nodes: list[str] | None = None,
        connection_config: dict[str, Any] | None = None,
        target_clients: list[str] | None = None,
    ) -> tuple[EmailDesignDocument, ExtractedTokens, list[TokenWarning], DesignFileStructure]:
        """Build a complete EmailDesignDocument from a Figma file.

        Encapsulates: API fetch -> token extraction -> validation ->
        tree normalization -> layout analysis -> document assembly.
        """
        from app.design_sync.email_design_document import EmailDesignDocument
        from app.design_sync.figma.tree_normalizer import normalize_tree
        from app.design_sync.token_transforms import (
            validate_and_transform,
        )

        tokens, structure = await self.sync_tokens_and_structure(
            file_ref,
            access_token,
            target_node_id=selected_nodes[0] if selected_nodes else None,
        )
        tokens, token_warnings = validate_and_transform(tokens, target_clients=target_clients)
        structure, _stats = normalize_tree(structure)
        document = EmailDesignDocument.from_legacy(
            structure,
            tokens,
            selected_nodes=selected_nodes,
            connection_config=connection_config,
            source_provider="figma",
            _pre_normalized=True,
        )

        logger.info(
            "design_sync.figma.build_document_completed",
            file_ref=file_ref,
            sections=len(document.sections),
            token_warnings=len(token_warnings),
        )
        return document, tokens, token_warnings, structure

    async def _fetch_variables(
        self, file_ref: str, access_token: str
    ) -> RawVariablesResponse | None:
        """Fetch local and published variables from the Figma Variables API."""
        headers = {"X-Figma-Token": access_token}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            local_resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}/variables/local",
                headers=headers,
            )
            if local_resp.status_code == 403:
                logger.info("design_sync.figma.variables_not_available", reason="403")
                return None
            if local_resp.status_code == 429:
                retry_after = local_resp.headers.get("Retry-After", "60")
                raise SyncFailedError(
                    f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
                )
            if local_resp.status_code != 200:
                logger.warning(
                    "design_sync.figma.variables_fetch_failed",
                    status=local_resp.status_code,
                )
                return None

            pub_resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}/variables/published",
                headers=headers,
            )
            if pub_resp.status_code == 429:
                retry_after = pub_resp.headers.get("Retry-After", "60")
                raise SyncFailedError(
                    f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
                )

        local_json: dict[str, Any] = local_resp.json()
        pub_json: dict[str, Any] = pub_resp.json() if pub_resp.status_code == 200 else {}
        return cast(RawVariablesResponse, {"local": local_json, "published": pub_json})

    def _resolve_variable_alias(
        self,
        value: Any,
        variables_by_id: dict[str, RawFigmaVariable],
        mode_id: str,
        depth: int = 0,
    ) -> Any:
        """Walk alias chain to resolve a variable value."""
        if depth >= _MAX_ALIAS_DEPTH:
            logger.warning("design_sync.figma.alias_depth_exceeded", depth=depth)
            return None
        if not isinstance(value, dict):
            return value
        value_d = cast(dict[str, Any], value)
        if value_d.get("type") != "VARIABLE_ALIAS":
            return value_d
        target_id = str(value_d.get("id", ""))
        target_var = variables_by_id.get(target_id)
        if not target_var:
            return None
        values_by_mode: dict[str, Any] = target_var.get("valuesByMode", {})
        resolved = values_by_mode.get(mode_id)
        if resolved is None:
            # Fall back to first available mode
            for v in values_by_mode.values():
                resolved = v
                break
        if resolved is None:
            return None
        return self._resolve_variable_alias(resolved, variables_by_id, mode_id, depth + 1)

    def _parse_variables(
        self, raw: RawVariablesResponse, bg_hex: str = "#FFFFFF"
    ) -> tuple[
        list[ExtractedColor],
        list[ExtractedTypography],
        list[ExtractedVariable],
        dict[str, str],
        list[ExtractedColor],
    ]:
        """Parse Variables API response into colors, typography, variables, modes, dark_colors."""
        colors: list[ExtractedColor] = []
        seen_hex: set[str] = set()
        variables: list[ExtractedVariable] = []
        global_modes: dict[str, str] = {}

        local_raw: Any = raw.get("local", {})
        meta_d: dict[str, Any] = (
            cast(dict[str, Any], local_raw).get("meta", {}) if isinstance(local_raw, dict) else {}
        )
        collections: dict[str, Any] = cast(dict[str, Any], meta_d.get("variableCollections", {}))
        all_variables: dict[str, Any] = cast(dict[str, Any], meta_d.get("variables", {}))

        # Build mode name lookup from collections
        mode_name_map: dict[str, str] = {}  # mode_id -> mode_name
        for coll_raw in collections.values():
            if not isinstance(coll_raw, dict):
                continue
            coll_d = cast(dict[str, Any], coll_raw)
            for mode in cast(list[Any], coll_d.get("modes", [])):
                if isinstance(mode, dict):
                    mode_d = cast(dict[str, Any], mode)
                    mid = str(mode_d.get("modeId", ""))
                    mname = str(mode_d.get("name", mid))
                    mode_name_map[mid] = mname

        # Use first collection's modes as global_modes
        for coll_raw in collections.values():
            if isinstance(coll_raw, dict):
                coll_d = cast(dict[str, Any], coll_raw)
                for mode in cast(list[Any], coll_d.get("modes", [])):
                    if isinstance(mode, dict):
                        mode_d = cast(dict[str, Any], mode)
                        mid = str(mode_d.get("modeId", ""))
                        mname = str(mode_d.get("name", mid))
                        global_modes[mname] = mid
                break

        # Default mode: first in global_modes
        default_mode_id = next(iter(global_modes.values()), "")

        # Detect dark mode: any mode name containing "dark", "night", or "dim"
        _DARK_MODE_PATTERNS = ("dark", "night", "dim")
        dark_mode_id: str | None = None
        for mode_name, mode_id in global_modes.items():
            if any(p in mode_name.lower() for p in _DARK_MODE_PATTERNS):
                dark_mode_id = mode_id
                break

        for var_id, var_data_raw in all_variables.items():
            if not isinstance(var_data_raw, dict):
                continue
            var_data = cast(dict[str, Any], var_data_raw)
            var_name = str(var_data.get("name", var_id))
            resolved_type = str(var_data.get("resolvedType", ""))
            collection_id = str(var_data.get("variableCollectionId", ""))
            coll_name = ""
            coll_data = collections.get(collection_id)
            if isinstance(coll_data, dict):
                coll_name = str(cast(dict[str, Any], coll_data).get("name", ""))

            values_by_mode_raw: dict[str, Any] = cast(
                dict[str, Any], var_data.get("valuesByMode", {})
            )
            resolved_values: dict[str, Any] = {}
            is_alias = False
            alias_path: str | None = None

            for mid, val in values_by_mode_raw.items():
                mname = mode_name_map.get(mid, mid)
                if (
                    isinstance(val, dict)
                    and cast(dict[str, Any], val).get("type") == "VARIABLE_ALIAS"
                ):
                    is_alias = True
                    target_id_str = str(cast(dict[str, Any], val).get("id", ""))
                    target_var_raw = all_variables.get(target_id_str)
                    if isinstance(target_var_raw, dict):
                        alias_path = str(
                            cast(dict[str, Any], target_var_raw).get("name", target_id_str)
                        )
                resolved = self._resolve_variable_alias(val, all_variables, mid)
                resolved_values[mname] = resolved

            # Strip leading "color/" prefix from display name
            display_name = var_name
            if display_name.lower().startswith("color/"):
                display_name = display_name[6:]

            variables.append(
                ExtractedVariable(
                    name=display_name,
                    collection=coll_name,
                    type=resolved_type,
                    values_by_mode=resolved_values,
                    is_alias=is_alias,
                    alias_path=alias_path,
                )
            )

            # COLOR variables → extract into colors palette
            if resolved_type == "COLOR":
                default_val = self._resolve_variable_alias(
                    values_by_mode_raw.get(default_mode_id), all_variables, default_mode_id
                )
                if isinstance(default_val, dict):
                    dv = cast(dict[str, Any], default_val)
                    r = float(dv.get("r", 0))
                    g = float(dv.get("g", 0))
                    b = float(dv.get("b", 0))
                    a = float(dv.get("a", 1.0))
                    hex_val = _rgba_to_hex_with_opacity(r, g, b, fill_alpha=a, bg_hex=bg_hex)
                    if hex_val not in seen_hex:
                        seen_hex.add(hex_val)
                        colors.append(ExtractedColor(name=display_name, hex=hex_val, opacity=a))

        # Dark color extraction from dark mode
        dark_colors: list[ExtractedColor] = []
        if dark_mode_id:
            seen_dark_hex: set[str] = set()
            for var_id, var_data_raw in all_variables.items():
                if not isinstance(var_data_raw, dict):
                    continue
                var_data = cast(dict[str, Any], var_data_raw)
                resolved_type = str(var_data.get("resolvedType", ""))
                if resolved_type != "COLOR":
                    continue
                var_name = str(var_data.get("name", var_id))
                display_name = var_name
                if display_name.lower().startswith("color/"):
                    display_name = display_name[6:]

                values_by_mode_raw = cast(dict[str, Any], var_data.get("valuesByMode", {}))
                dark_val = self._resolve_variable_alias(
                    values_by_mode_raw.get(dark_mode_id), all_variables, dark_mode_id
                )
                if isinstance(dark_val, dict):
                    dv = cast(dict[str, Any], dark_val)
                    r = float(dv.get("r", 0))
                    g = float(dv.get("g", 0))
                    b = float(dv.get("b", 0))
                    a = float(dv.get("a", 1.0))
                    hex_val = _rgba_to_hex_with_opacity(r, g, b, fill_alpha=a, bg_hex=bg_hex)
                    if hex_val not in seen_dark_hex:
                        seen_dark_hex.add(hex_val)
                        dark_colors.append(
                            ExtractedColor(name=display_name, hex=hex_val, opacity=a)
                        )

        # Typography from Variables is future work (33.3)
        return colors, [], variables, global_modes, dark_colors

    def _parse_colors(
        self,
        file_data: dict[str, Any],
        styles_data: dict[str, Any],  # noqa: ARG002
        *,
        bg_hex: str = "#FFFFFF",
    ) -> tuple[list[ExtractedColor], list[ExtractedColor], list[ExtractedGradient]]:
        """Extract colour tokens from published styles + node walk fallback.

        Returns (fill_colors, stroke_colors, gradients).
        """
        colors: list[ExtractedColor] = []
        seen_hex: set[str] = set()
        stroke_colors: list[ExtractedColor] = []
        seen_stroke_hex: set[str] = set()
        gradients: list[ExtractedGradient] = []

        # Phase 1: Published styles (better names, take priority)
        raw_styles = file_data.get("styles", {})
        if isinstance(raw_styles, dict):
            styles = cast(dict[str, Any], raw_styles)
            for style_id, style_meta in styles.items():
                if not isinstance(style_meta, dict):
                    continue
                style_meta_d = cast(dict[str, Any], style_meta)
                if style_meta_d.get("styleType") != "FILL":
                    continue
                name = str(style_meta_d.get("name", f"Color-{style_id}"))
                raw_fills = self._find_fills_for_style(file_data, str(style_id))
                # _find_fills_for_style returns [node["fills"]] where fills is a list
                fills_list: list[Any] = raw_fills[0] if raw_fills else []
                if fills_list:
                    fill: Any = fills_list[0]
                    if isinstance(fill, dict) and "color" in fill:
                        fill_d = cast(dict[str, Any], fill)
                        color_raw = fill_d["color"]
                        if isinstance(color_raw, dict):
                            c = cast(dict[str, Any], color_raw)
                            opacity = float(c.get("a", 1.0))
                            hex_val = _rgba_to_hex_with_opacity(
                                float(c.get("r", 0)),
                                float(c.get("g", 0)),
                                float(c.get("b", 0)),
                                fill_alpha=opacity,
                                bg_hex=bg_hex,
                            )
                            seen_hex.add(hex_val)
                            colors.append(ExtractedColor(name=name, hex=hex_val, opacity=opacity))

        # Phase 2: Node walk (picks up unstyled colors, skips duplicates via seen_hex)
        self._walk_for_colors(
            file_data.get("document", {}),
            colors,
            seen_hex,
            stroke_colors=stroke_colors,
            seen_stroke_hex=seen_stroke_hex,
            bg_hex=bg_hex,
            gradients=gradients,
        )

        return colors, stroke_colors, gradients

    def _parse_typography(
        self,
        file_data: dict[str, Any],
        styles_data: dict[str, Any],  # noqa: ARG002
    ) -> list[ExtractedTypography]:
        """Extract typography tokens from published styles + node walk fallback."""
        typography: list[ExtractedTypography] = []
        seen_keys: set[tuple[str, str, float]] = set()

        # Phase 1: Published styles (better names, take priority)
        raw_styles = file_data.get("styles", {})
        if isinstance(raw_styles, dict):
            styles = cast(dict[str, Any], raw_styles)
            for style_id, style_meta in styles.items():
                if not isinstance(style_meta, dict):
                    continue
                style_meta_d = cast(dict[str, Any], style_meta)
                if style_meta_d.get("styleType") != "TEXT":
                    continue
                name = str(style_meta_d.get("name", f"Type-{style_id}"))
                type_props = self._find_type_style_for_style(file_data, str(style_id))
                if type_props and isinstance(type_props, dict):
                    tp = cast(RawFigmaTextStyle, type_props)
                    family = str(tp.get("fontFamily", "Unknown"))
                    weight = str(tp.get("fontWeight", "400"))
                    size = float(tp.get("fontSize", 16))
                    seen_keys.add((family, weight, size))
                    typography.append(
                        ExtractedTypography(
                            name=name,
                            family=family,
                            weight=weight,
                            size=size,
                            line_height=float(tp.get("lineHeightPx", 24)),
                            letter_spacing=_parse_letter_spacing(tp, size),
                            text_transform=_TEXT_CASE_MAP.get(str(tp.get("textCase", ""))),
                            text_decoration=_TEXT_DEC_MAP.get(str(tp.get("textDecoration", ""))),
                        )
                    )

        # Phase 2: Node walk (picks up unstyled typography, skips duplicates via seen_keys)
        self._walk_for_typography(file_data.get("document", {}), typography, seen_keys)

        return typography

    def _parse_spacing(self, file_data: dict[str, Any]) -> list[ExtractedSpacing]:
        """Extract spacing from auto-layout frames in the document tree."""
        spacing: list[ExtractedSpacing] = []
        seen: set[float] = set()
        self._walk_for_spacing(file_data.get("document", {}), spacing, seen)
        return sorted(spacing, key=lambda s: s.value)

    def _walk_for_spacing(
        self,
        node: Any,
        spacing: list[ExtractedSpacing],
        seen: set[float],
        depth: int = 0,
    ) -> None:
        if depth >= _MAX_WALK_DEPTH or not isinstance(node, dict):
            return
        node_d = cast(dict[str, Any], node)
        # Auto-layout frames expose itemSpacing / paddingLeft etc.
        for key in ("itemSpacing", "paddingLeft", "paddingTop"):
            val: Any = node_d.get(key)
            if isinstance(val, (int, float)) and val > 0 and val not in seen:
                seen.add(float(val))
                spacing.append(ExtractedSpacing(name=f"spacing-{int(val)}", value=float(val)))
        for child in cast(list[Any], node_d.get("children", [])):
            self._walk_for_spacing(child, spacing, seen, depth + 1)

    def _walk_for_colors(
        self,
        node: Any,
        colors: list[ExtractedColor],
        seen_hex: set[str],
        depth: int = 0,
        *,
        stroke_colors: list[ExtractedColor] | None = None,
        seen_stroke_hex: set[str] | None = None,
        bg_hex: str = "#FFFFFF",
        gradients: list[ExtractedGradient] | None = None,
    ) -> None:
        """Recursively extract fill/stroke colors from every node."""
        if depth >= _MAX_WALK_DEPTH or not isinstance(node, dict):
            return
        node_d = cast(RawFigmaNode, node)
        node_opacity = float(node_d.get("opacity", 1.0))
        node_name = str(node_d.get("name", ""))

        if stroke_colors is None:
            stroke_colors = []
        if seen_stroke_hex is None:
            seen_stroke_hex = set()

        # Children composite against this node's own solid fill when it has one,
        # otherwise inherit the ancestor backdrop (52.5).
        child_bg = bg_hex

        # Fills — extract all gradient midpoints, then topmost visible solid
        fills_list = node_d.get("fills", [])
        if fills_list:
            # Pass 1: gradient midpoints (all of them)
            for fill_item in fills_list:
                if not isinstance(fill_item, dict):
                    continue
                fill_d = cast(dict[str, Any], fill_item)
                if fill_d.get("visible") is False:
                    continue
                gradient_type = fill_d.get("type", "")
                if gradient_type in (
                    "GRADIENT_LINEAR",
                    "GRADIENT_RADIAL",
                    "GRADIENT_ANGULAR",
                    "GRADIENT_DIAMOND",
                ):
                    stops: list[Any] = fill_d.get("gradientStops", [])
                    if len(stops) >= 2:
                        midpoint = _gradient_midpoint_hex(cast(list[RawFigmaGradientStop], stops))
                        if midpoint and midpoint not in seen_hex:
                            seen_hex.add(midpoint)
                            gname = f"{node_name} (gradient midpoint)" if node_name else midpoint
                            colors.append(ExtractedColor(name=gname, hex=midpoint, opacity=1.0))

                        if gradients is not None:
                            if gradient_type == "GRADIENT_LINEAR":
                                handles: list[Any] = fill_d.get("gradientHandlePositions", [])
                                angle = _compute_gradient_angle(handles)
                                g_type = "linear"
                            else:
                                angle = 0.0
                                g_type = "radial"
                            parsed_stops = _parse_gradient_stops(stops, bg_hex=bg_hex)
                            fallback = midpoint or "#808080"
                            gradients.append(
                                ExtractedGradient(
                                    name=node_name or f"gradient-{len(gradients)}",
                                    type=g_type,
                                    angle=angle,
                                    stops=tuple(parsed_stops),
                                    fallback_hex=fallback,
                                    node_id=str(node_d.get("id", "")) or None,
                                )
                            )

            # Pass 2: topmost visible solid (last in array = topmost in Figma)
            for fill_item in reversed(fills_list):
                if not isinstance(fill_item, dict):
                    continue
                fill_d = cast(dict[str, Any], fill_item)
                if fill_d.get("visible") is False:
                    continue
                if fill_d.get("type") != "SOLID":
                    continue
                color_raw = fill_d.get("color")
                if not isinstance(color_raw, dict):
                    continue
                c = cast(dict[str, Any], color_raw)
                fill_alpha = float(c.get("a", 1.0))
                if fill_alpha * node_opacity < 0.01:
                    continue
                hex_val = _rgba_to_hex_with_opacity(
                    float(c.get("r", 0)),
                    float(c.get("g", 0)),
                    float(c.get("b", 0)),
                    fill_alpha=fill_alpha,
                    node_opacity=node_opacity,
                    bg_hex=bg_hex,
                )
                if hex_val not in seen_hex:
                    seen_hex.add(hex_val)
                    colors.append(ExtractedColor(name=hex_val, hex=hex_val, opacity=fill_alpha))
                # Children composite against this node's resolved fill (52.5)
                child_bg = hex_val
                break  # Topmost visible solid only

        # Strokes — separate list
        raw_strokes = node_d.get("strokes", [])
        for stroke_item in raw_strokes:
            if not isinstance(stroke_item, dict):
                continue
            stroke_d = cast(dict[str, Any], stroke_item)
            if stroke_d.get("type") != "SOLID":
                continue
            color_raw = stroke_d.get("color")
            if not isinstance(color_raw, dict):
                continue
            c = cast(dict[str, Any], color_raw)
            alpha = float(c.get("a", 1.0))
            if alpha < 0.01:
                continue
            hex_val = _rgba_to_hex_with_opacity(
                float(c.get("r", 0)),
                float(c.get("g", 0)),
                float(c.get("b", 0)),
                fill_alpha=alpha,
                node_opacity=node_opacity,
                bg_hex=bg_hex,
            )
            if hex_val not in seen_stroke_hex:
                seen_stroke_hex.add(hex_val)
                stroke_colors.append(ExtractedColor(name=hex_val, hex=hex_val, opacity=alpha))

        for child in node_d.get("children", []):
            self._walk_for_colors(
                child,
                colors,
                seen_hex,
                depth + 1,
                stroke_colors=stroke_colors,
                seen_stroke_hex=seen_stroke_hex,
                bg_hex=child_bg,
                gradients=gradients,
            )

    def _walk_for_typography(
        self,
        node: Any,
        typography: list[ExtractedTypography],
        seen_keys: set[tuple[str, str, float]],
        depth: int = 0,
    ) -> None:
        """Recursively extract typography from TEXT nodes."""
        if depth >= _MAX_WALK_DEPTH or not isinstance(node, dict):
            return
        node_d = cast(dict[str, Any], node)

        if str(node_d.get("type", "")) == "TEXT":
            style = node_d.get("style")
            if isinstance(style, dict):
                s = cast(RawFigmaTextStyle, style)
                family = str(s.get("fontFamily", ""))
                weight = str(s.get("fontWeight", "400"))
                size = float(s.get("fontSize", 0))
                if family and size > 0:
                    key = (family, weight, size)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        line_height = float(s.get("lineHeightPx", size * 1.2))
                        name = f"{family} {weight} {int(size)}px"
                        typography.append(
                            ExtractedTypography(
                                name=name,
                                family=family,
                                weight=weight,
                                size=size,
                                line_height=line_height,
                                letter_spacing=_parse_letter_spacing(s, size),
                                text_transform=_TEXT_CASE_MAP.get(str(s.get("textCase", ""))),
                                text_decoration=_TEXT_DEC_MAP.get(str(s.get("textDecoration", ""))),
                            )
                        )

        for child in node_d.get("children", []):
            self._walk_for_typography(child, typography, seen_keys, depth + 1)

    def _find_fills_for_style(self, file_data: dict[str, Any], style_id: str) -> list[Any]:
        """Walk document tree looking for a node that references this style."""
        return self._walk_for_style_property(file_data.get("document", {}), style_id, "fills")

    def _find_type_style_for_style(self, file_data: dict[str, Any], style_id: str) -> Any:
        """Walk document tree looking for a node with this text style."""
        results = self._walk_for_style_property(file_data.get("document", {}), style_id, "style")
        return results[0] if results else None

    def _walk_for_style_property(self, node: Any, style_id: str, prop: str) -> list[Any]:
        """Recursively search for a node referencing the given style ID."""
        if not isinstance(node, dict):
            return []
        node_d = cast(dict[str, Any], node)
        node_styles = node_d.get("styles", {})
        if isinstance(node_styles, dict):
            node_styles_d = cast(dict[str, Any], node_styles)
            for sid in node_styles_d.values():
                if str(sid) == style_id and prop in node_d:
                    return [node_d[prop]]
        results: list[Any] = []
        for child in cast(list[Any], node_d.get("children", [])):
            results.extend(self._walk_for_style_property(child, style_id, prop))
            if results:
                return results
        return results

    # ── Phase 12.1: File Structure, Components, Image Export ──

    async def get_file_structure(
        self, file_ref: str, access_token: str, *, depth: int | None = 2
    ) -> DesignFileStructure:
        """Fetch and parse Figma file structure into a normalised tree."""
        params: dict[str, Any] = {}
        if depth is not None:
            # Figma depth param: 1=pages only, 2=pages+frames, etc.
            # We add 1 because Figma counts from the DOCUMENT root
            params["depth"] = depth + 1

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}",
                headers={"X-Figma-Token": access_token},
                params=params,
            )
        if resp.status_code == 403:
            raise SyncFailedError("Figma access denied. Check your Personal Access Token.")
        if resp.status_code == 404:
            raise SyncFailedError("Figma file not found. Check the file URL.")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            raise SyncFailedError(
                f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
            )
        if resp.status_code != 200:
            raise SyncFailedError(f"Figma API error (HTTP {resp.status_code})")

        data: dict[str, Any] = resp.json()
        file_name = str(data.get("name", "Untitled"))
        document = data.get("document", {})
        pages: list[DesignNode] = []

        max_depth = depth  # None means unlimited
        for page_data in document.get("children", []):
            if isinstance(page_data, dict):
                pages.append(
                    self._parse_node(
                        cast(RawFigmaNode, page_data), current_depth=0, max_depth=max_depth
                    )
                )

        logger.info(
            "design_sync.figma.file_structure_fetched",
            file_ref=file_ref,
            pages=len(pages),
        )

        return DesignFileStructure(file_name=file_name, pages=pages)

    def _parse_node(
        self,
        node_data: RawFigmaNode,
        current_depth: int,
        max_depth: int | None,
        parent_bg: str = "#FFFFFF",
    ) -> DesignNode:
        """Recursively parse a Figma node into a DesignNode.

        ``parent_bg`` is the nearest ancestor's resolved fill — threaded down
        so translucent fills composite against the real backdrop (52.5).
        """
        raw_type = str(node_data.get("type", "UNKNOWN"))
        node_type = _FIGMA_NODE_TYPE_MAP.get(raw_type, DesignNodeType.OTHER)
        node_opacity = float(node_data["opacity"]) if "opacity" in node_data else 1.0

        layout = _parse_layout_props(node_data, raw_type)
        text = _parse_text_props(node_data, node_type)
        visual = _parse_visual_props(node_data, node_type, node_opacity, bg_hex=parent_bg)
        node_type = visual.resolved_node_type  # apply IMAGE reclassification

        children: list[DesignNode] = []
        effective_max = max_depth if max_depth is not None else _MAX_PARSE_DEPTH
        if current_depth < effective_max:
            child_bg = visual.fill_color if visual.fill_color is not None else parent_bg
            for child_data in node_data.get("children", []):
                if isinstance(child_data, dict):
                    children.append(
                        self._parse_node(
                            cast(RawFigmaNode, child_data),
                            current_depth + 1,
                            max_depth,
                            parent_bg=child_bg,
                        )
                    )

        return DesignNode(
            id=str(node_data.get("id", "")),
            name=str(node_data.get("name", "")),
            type=node_type,
            children=children,
            width=layout.width,
            height=layout.height,
            x=layout.x,
            y=layout.y,
            text_content=text.text_content,
            fill_color=visual.fill_color,
            text_color=visual.text_color,
            padding_top=layout.padding_top,
            padding_right=layout.padding_right,
            padding_bottom=layout.padding_bottom,
            padding_left=layout.padding_left,
            item_spacing=layout.item_spacing,
            counter_axis_spacing=layout.counter_axis_spacing,
            layout_mode=layout.layout_mode,
            font_family=text.font_family,
            font_size=text.font_size,
            font_weight=text.font_weight,
            line_height_px=text.line_height_px,
            line_height_relative=text.line_height_relative,
            letter_spacing_px=text.letter_spacing_px,
            text_transform=text.text_transform,
            text_decoration=text.text_decoration,
            image_ref=visual.image_ref,
            hyperlink=visual.hyperlink,
            corner_radius=layout.corner_radius,
            corner_radii=layout.corner_radii,
            text_align=text.text_align,
            primary_axis_align=layout.primary_axis_align,
            counter_axis_align=layout.counter_axis_align,
            stroke_weight=visual.stroke_weight,
            stroke_color=visual.stroke_color,
            style_runs=text.style_runs,
            visible=node_data.get("visible") is not False,
            opacity=node_opacity,
        )

    async def list_components(self, file_ref: str, access_token: str) -> list[DesignComponent]:
        """Fetch published components from a Figma file."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_FIGMA_API}/v1/files/{file_ref}/components",
                headers={"X-Figma-Token": access_token},
            )
        if resp.status_code == 403:
            raise SyncFailedError("Figma access denied. Check your Personal Access Token.")
        if resp.status_code == 404:
            raise SyncFailedError("Figma file not found. Check the file URL.")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            raise SyncFailedError(
                f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
            )
        if resp.status_code != 200:
            raise SyncFailedError(f"Figma components API error (HTTP {resp.status_code})")

        data: dict[str, Any] = resp.json()
        error = data.get("error")
        if error:
            raise SyncFailedError(f"Figma API error: {error}")

        components: list[DesignComponent] = []
        meta = data.get("meta", {})
        raw_components = meta.get("components", [])

        for comp in raw_components:
            if not isinstance(comp, dict):
                continue
            comp_d = cast(dict[str, Any], comp)
            containing_frame = comp_d.get("containing_frame")
            containing_page: str | None = None
            if isinstance(containing_frame, dict):
                raw_page = cast(dict[str, Any], containing_frame).get("pageName")
                containing_page = str(raw_page) if raw_page is not None else None
            thumbnail = comp_d.get("thumbnail_url")
            components.append(
                DesignComponent(
                    component_id=str(comp_d.get("node_id", "")),
                    name=str(comp_d.get("name", "")),
                    description=str(comp_d.get("description", "")),
                    thumbnail_url=str(thumbnail) if thumbnail is not None else None,
                    containing_page=containing_page,
                )
            )

        logger.info(
            "design_sync.figma.components_listed",
            file_ref=file_ref,
            count=len(components),
        )

        return components

    async def export_images(
        self,
        file_ref: str,
        access_token: str,
        node_ids: list[str],
        *,
        format: str = "png",
        scale: float = 2.0,
    ) -> list[ExportedImage]:
        """Export Figma nodes as images, auto-batching in groups of 100."""
        if not node_ids:
            return []

        # Validate format
        valid_formats = {"png", "jpg", "svg", "pdf"}
        if format not in valid_formats:
            raise SyncFailedError(
                f"Invalid export format '{format}'. Valid: {', '.join(sorted(valid_formats))}"
            )

        # Clamp scale to Figma's supported range
        scale = max(0.01, min(scale, 4.0))

        # Batch into groups of 100 (Figma API limit)
        batches: list[list[str]] = [node_ids[i : i + 100] for i in range(0, len(node_ids), 100)]

        headers = {"X-Figma-Token": access_token}
        expires_at = datetime.now(tz=UTC) + timedelta(days=14)
        all_images: list[ExportedImage] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:

            async def _fetch_batch(batch: list[str]) -> dict[str, Any]:
                resp = await client.get(
                    f"{_FIGMA_API}/v1/images/{file_ref}",
                    headers=headers,
                    params={
                        "ids": ",".join(batch),
                        "format": format,
                        "scale": str(scale),
                    },
                )
                if resp.status_code == 403:
                    raise SyncFailedError("Figma access denied.")
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "60")
                    raise SyncFailedError(
                        f"Figma API rate limit exceeded. Try again in {retry_after} seconds."
                    )
                if resp.status_code != 200:
                    raise SyncFailedError(f"Figma images API error (HTTP {resp.status_code})")
                result: dict[str, Any] = resp.json()
                return result

            results = await asyncio.gather(*[_fetch_batch(b) for b in batches])

        for result in results:
            images_map = result.get("images", {})
            if not isinstance(images_map, dict):
                continue
            images_map_d = cast(dict[str, Any], images_map)
            for nid, url in images_map_d.items():
                if url is not None:
                    all_images.append(
                        ExportedImage(
                            node_id=str(nid),
                            url=str(url),
                            format=format,
                            expires_at=expires_at,
                        )
                    )

        logger.info(
            "design_sync.figma.images_exported",
            file_ref=file_ref,
            requested=len(node_ids),
            exported=len(all_images),
            format=format,
        )

        return all_images

    async def download_image_bytes(self, exported: ExportedImage) -> bytes:
        """Download image bytes from a Figma CDN URL.

        Args:
            exported: An ExportedImage with a CDN URL from export_images().

        Returns:
            Raw PNG/JPG bytes from the CDN.
        """
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(exported.url)
            resp.raise_for_status()
            content: bytes = resp.content
            logger.info(
                "design_sync.figma.image_downloaded",
                node_id=exported.node_id,
                size_bytes=len(content),
            )
            return content

    async def _export_full_frame_png(
        self,
        file_ref: str,
        access_token: str,
        target_node_id: str,
    ) -> bytes | None:
        """Export the root frame as a 2x PNG for global visual context (Phase 50.1).

        Returns ``None`` on any failure — never raises — so the conversion
        pipeline degrades gracefully when Figma is unreachable or the node
        cannot be exported.
        """
        try:
            exported = await self.export_images(
                file_ref,
                access_token,
                [target_node_id],
                format="png",
                scale=2.0,
            )
            img = next((e for e in exported if e.node_id == target_node_id), None)
            if img is None:
                return None
            return await self.download_image_bytes(img)
        except Exception:
            logger.warning(
                "design_sync.figma.full_frame_png_failed",
                node_id=target_node_id,
                exc_info=True,
            )
            return None

    async def export_frame_screenshots(
        self,
        file_key: str,
        access_token: str,
        node_ids: list[str],
        *,
        scale: float = 2.0,
    ) -> dict[str, bytes]:
        """Export and download PNG screenshots for multiple frames in one call.

        Batches node_ids in groups of 100 (Figma API limit via export_images),
        then downloads all CDN images concurrently.  Missing or failed nodes
        are silently omitted from the result.
        """
        if not node_ids:
            return {}

        exported = await self.export_images(
            file_key,
            access_token,
            node_ids,
            format="png",
            scale=scale,
        )
        if not exported:
            return {}

        async def _download_safe(img: ExportedImage) -> tuple[str, bytes | None]:
            try:
                data = await self.download_image_bytes(img)
            except Exception:
                logger.warning(
                    "design_sync.figma.frame_download_failed",
                    node_id=img.node_id,
                    exc_info=True,
                )
                return (img.node_id, None)
            else:
                return (img.node_id, data)

        results = await asyncio.gather(*[_download_safe(img) for img in exported])

        out: dict[str, bytes] = {node_id: data for node_id, data in results if data is not None}

        logger.info(
            "design_sync.figma.frame_screenshots_exported",
            file_key=file_key,
            requested=len(node_ids),
            downloaded=len(out),
        )
        return out

    # ── Webhook management ──

    async def register_webhook(
        self,
        access_token: str,
        *,
        team_id: str,
        endpoint: str,
        passcode: str,
    ) -> str:
        """Register a FILE_UPDATE webhook with Figma. Returns the webhook ID."""
        from app.design_sync.exceptions import WebhookRegistrationError

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_FIGMA_API}/v2/webhooks",
                headers={"X-Figma-Token": access_token},
                json={
                    "event_type": "FILE_UPDATE",
                    "team_id": team_id,
                    "endpoint": endpoint,
                    "passcode": passcode,
                },
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "design_sync.figma.webhook_register_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
                raise WebhookRegistrationError(
                    f"Figma webhook registration failed (HTTP {resp.status_code})"
                )
            data: dict[str, Any] = resp.json()
            raw_id = data.get("id")
            if raw_id is None:
                raise WebhookRegistrationError("Figma webhook response missing 'id' field")
            webhook_id = str(raw_id)
            logger.info("design_sync.figma.webhook_registered", webhook_id=webhook_id)
            return webhook_id

    async def delete_webhook(self, access_token: str, webhook_id: str) -> None:
        """Delete a registered Figma webhook."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{_FIGMA_API}/v2/webhooks/{webhook_id}",
                headers={"X-Figma-Token": access_token},
            )
            if resp.status_code not in (200, 204):
                logger.warning(
                    "design_sync.figma.webhook_delete_failed",
                    status=resp.status_code,
                    webhook_id=webhook_id,
                )
            else:
                logger.info("design_sync.figma.webhook_deleted", webhook_id=webhook_id)
