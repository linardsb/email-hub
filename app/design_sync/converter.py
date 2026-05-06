"""Convert design elements to email-safe HTML and design system tokens (provider-agnostic)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from app.core.logging import get_logger
from app.design_sync.protocol import (
    DesignNode,
    DesignNodeType,
    ExtractedGradient,
    StyleRun,
    _NodeProps,
)
from app.design_sync.render_context import RenderContext

# ── Deprecated re-exports ────────────────────────────────────────────────
# These symbols moved to dedicated modules during 08c part 1. The aliases
# below let existing importers (notably `app/design_sync/tests/*`) keep
# working until 08c parts 2 & 4 migrate or delete those callsites. The
# aliases — and this entire file — go away in part 4.
from app.design_sync.sanitizers import (  # noqa: F401  (re-exports)
    _has_visible_content,
    _sanitize_css_value,
    sanitize_web_tags_for_email,
)
from app.design_sync.token_transforms import (  # noqa: F401  (re-exports)
    convert_colors_to_palette,
    convert_spacing,
    convert_typography,
)
from app.shared.color import contrast_ratio as _contrast_ratio
from app.shared.color import relative_luminance as _relative_luminance

# Re-exports must be explicit for strict type-checkers.
__all__ = [
    "_NodeProps",
    "_contrast_ratio",
    "_has_visible_content",
    "_relative_luminance",
    "_sanitize_css_value",
    "convert_colors_to_palette",
    "convert_spacing",
    "convert_typography",
    # Symbols still defined in this file (kept for tests until parts 3-4):
    "node_to_email_html",
    "sanitize_web_tags_for_email",
]

if TYPE_CHECKING:
    from app.design_sync.figma.layout_analyzer import EmailSection

logger = get_logger(__name__)

# ── YAML-backed font fallback data ──
_FONT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "email_client_fonts.yaml"
_FONT_DATA: dict[str, Any] = (
    yaml.safe_load(_FONT_DATA_PATH.read_text()) if _FONT_DATA_PATH.exists() else {}
)
_FALLBACK_MAP: dict[str, list[str]] = _FONT_DATA.get("fallback_map", {})

# Figma text property maps
_TEXT_CASE_MAP: dict[str, str] = {
    "UPPER": "uppercase",
    "LOWER": "lowercase",
    "TITLE": "capitalize",
}
_TEXT_DEC_MAP: dict[str, str] = {"UNDERLINE": "underline", "STRIKETHROUGH": "line-through"}

# Design node type → HTML element mapping for email
_NODE_HTML_MAP: dict[DesignNodeType, str] = {
    DesignNodeType.FRAME: "table",
    DesignNodeType.TEXT: "td",
    DesignNodeType.IMAGE: "img",
    DesignNodeType.GROUP: "table",
    # VECTOR: skipped — vectors/SVGs are not email-safe (returns "" below)
}


def _is_inline_row(children: list[DesignNode]) -> bool:
    """Detect rows where inline rendering is better than multi-column ghost tables.

    Returns True for small inline content like nav items (TEXT + small icon).
    """
    if len(children) < 2 or len(children) > 4:
        return False
    has_text = any(c.type == DesignNodeType.TEXT for c in children)
    all_small_or_text = all(
        c.type == DesignNodeType.TEXT
        or (
            c.type == DesignNodeType.IMAGE
            and (c.width if c.width is not None else 0) <= 30
            and (c.height if c.height is not None else 0) <= 30
        )
        for c in children
    )
    return has_text and all_small_or_text


def _font_stack(family: str) -> str:
    """Build email-safe CSS font stack using data/email_client_fonts.yaml."""
    family_clean = family.strip("'\"").strip()
    if "," in family_clean:
        return family_clean
    # Look up YAML fallback map (case-insensitive)
    for mapped_name, chain in _FALLBACK_MAP.items():
        if mapped_name.strip("'\"").lower() == family_clean.lower():
            return f"{family_clean}, {', '.join(str(f) for f in chain)}"
    # Generic family keywords
    if family_clean.lower() in {"sans-serif", "serif", "monospace", "cursive", "fantasy"}:
        return family_clean
    # Unknown font — default sans-serif chain
    return f"{family_clean}, Arial, Helvetica, sans-serif"


_GENERIC_LAYER_NAMES: frozenset[str] = frozenset(
    {
        "image",
        "frame",
        "group",
        "rectangle",
        "vector",
        "ellipse",
        "component",
        "instance",
        "mask",
        "slice",
    }
)

_LAYER_PREFIX_RE = re.compile(
    r"^(mj-|figma-|frame-|group-|image-|img-|pic-|photo-)",
    re.IGNORECASE,
)


def _meaningful_alt(
    node_name: str | None,
    *,
    section: EmailSection | None = None,
) -> str:
    """Derive accessible alt text from node name with smart fallbacks."""
    name = (node_name or "").strip()
    cleaned = _LAYER_PREFIX_RE.sub("", name).strip()
    # Node name is meaningful
    if cleaned and cleaned.lower() not in _GENERIC_LAYER_NAMES:
        return html.escape(cleaned)
    # Derive from section heading
    if section and section.texts:
        heading = next((t for t in section.texts if t.is_heading), None)
        if heading and heading.content:
            return html.escape(heading.content[:80])
    # Derive from section type
    if section:
        label = section.section_type.value.replace("_", " ").title()
        return f"{label} image"
    return "Email image"


def _is_safe_url(url: str) -> bool:
    """Only allow http/https and internal API URLs for background images."""
    return url.startswith(("http://", "https://", "/api/"))


def _contrasting_text_color(bg_hex: str) -> str:
    """Return white or black text depending on background luminance."""
    return "#ffffff" if _relative_luminance(bg_hex) < 0.5 else "#000000"


def _gradient_to_css(gradient: ExtractedGradient) -> str:
    """Convert ExtractedGradient to CSS linear-gradient() value."""
    stops_css = ", ".join(
        f"{_sanitize_css_value(hex_val)} {round(pos * 100, 1)}%" for hex_val, pos in gradient.stops
    )
    return f"linear-gradient({gradient.angle}deg, {stops_css})"


def _determine_heading_level(
    font_size: float,
    body_font_size: float,
) -> int | None:
    """Return heading level (1-3) based on font size ratio, or None for body text."""
    if body_font_size <= 0:
        return None
    ratio = font_size / body_font_size
    if ratio >= 2.0:
        return 1
    if ratio >= 1.5:
        return 2
    if ratio >= 1.2:
        return 3
    return None


def _next_slot_name(counter: dict[str, int], slot_type: str) -> str:
    """Generate unique slot name: 'body', 'body_2', 'body_3', etc."""
    count = counter.get(slot_type, 0) + 1
    counter[slot_type] = count
    return slot_type if count == 1 else f"{slot_type}_{count}"


def _render_semantic_text(
    *,
    content: str,
    font_family: str,
    extra_style: str,
    mso_alt: str,
    pad: str,
    is_heading: bool,
    heading_level: int | None,
    slot_counter: dict[str, int] | None = None,
) -> str:
    """Render a TEXT node directly inside <td> with inline styles.

    All text styling is applied to the <td> element — no <p> or <h> wrapper
    tags. This ensures consistent rendering across all email clients.
    """
    if is_heading and heading_level is not None:
        slot_attr = ""
        if slot_counter is not None:
            slot_attr = f' data-slot-name="{_next_slot_name(slot_counter, "heading")}"'
        td_style = f"font-family:{font_family};mso-line-height-rule:exactly;{mso_alt}{extra_style}"
        return f'{pad}<td{slot_attr} style="{td_style}">{content}</td>'

    # Body text — split multi-line on \n into separate <td> rows
    lines = content.split("\n") if "\n" in content else [content]
    if len(lines) == 1:
        slot_attr = ""
        if slot_counter is not None:
            slot_attr = f' data-slot-name="{_next_slot_name(slot_counter, "body")}"'
        td_style = f"padding:0 0 10px 0;font-family:{font_family};mso-line-height-rule:exactly;{mso_alt}{extra_style}"
        return f'{pad}<td{slot_attr} style="{td_style}">{content}</td>'

    # Multi-line -> separate <td> elements joined by </tr><tr>
    td_style = f"padding:0 0 10px 0;font-family:{font_family};mso-line-height-rule:exactly;{mso_alt}{extra_style}"
    td_parts: list[str] = []
    for line in lines:
        if line.strip():
            slot_attr = ""
            if slot_counter is not None:
                slot_attr = f' data-slot-name="{_next_slot_name(slot_counter, "body")}"'
            td_parts.append(f'<td{slot_attr} style="{td_style}">{line}</td>')
    return f"{pad}{'</tr><tr>'.join(td_parts)}"


def _validate_button_contrast(
    bg_hex: str,
    text_hex: str,
    font_size_px: int,
) -> None:
    """Log a warning if button text/background contrast is below WCAG AA."""
    try:
        bg_lum = _relative_luminance(bg_hex)
        text_lum = _relative_luminance(text_hex)
        ratio = _contrast_ratio(bg_lum, text_lum)
    except (ValueError, TypeError):
        return
    threshold = 3.0 if font_size_px >= 18 else 4.5
    if ratio < threshold:
        logger.warning(
            "design_sync.button_contrast_low",
            bg=bg_hex,
            text=text_hex,
            ratio=round(ratio, 2),
            threshold=threshold,
        )


def _render_style_runs(text: str, runs: tuple[StyleRun, ...]) -> str:
    """Render rich text with inline style runs (bold, italic, color, links).

    Each segment of the text is HTML-escaped individually. Style runs wrap
    segments with appropriate HTML tags.
    """
    if not runs:
        return html.escape(text)

    # Build segments: before first run, between runs, and after last run
    parts: list[str] = []
    last_end = 0
    for run in sorted(runs, key=lambda r: r.start):
        # Text before this run
        if run.start > last_end:
            parts.append(html.escape(text[last_end : run.start]))
        # The styled segment
        segment = html.escape(text[run.start : run.end])
        if run.bold:
            segment = f"<strong>{segment}</strong>"
        if run.italic:
            segment = f"<em>{segment}</em>"
        if run.underline:
            segment = f'<span style="text-decoration:underline;">{segment}</span>'
        if run.strikethrough:
            segment = f"<s>{segment}</s>"
        if run.color_hex:
            segment = f'<span style="color:{html.escape(run.color_hex)};">{segment}</span>'
        if run.link_url:
            escaped_url = html.escape(run.link_url, quote=True)
            segment = f'<a href="{escaped_url}" style="color:inherit;">{segment}</a>'
        parts.append(segment)
        last_end = run.end

    # Remaining text after last run
    if last_end < len(text):
        parts.append(html.escape(text[last_end:]))

    return "".join(parts)


def _render_button(
    node: DesignNode,
    *,
    pad: str,
    props: _NodeProps | None,
    slot_counter: dict[str, int] | None = None,
) -> str:
    """Render a button-like COMPONENT/FRAME as a bulletproof <a> with VML fallback."""
    text_children = [c for c in node.children if c.type == DesignNodeType.TEXT and c.text_content]
    if not text_children:
        return ""
    button_text = html.escape(text_children[0].text_content or "")

    width = int(node.width) if node.width else 200
    height = max(int(node.height) if node.height else 44, 44)

    raw_bg = node.fill_color if node.fill_color is not None else (props.bg_color if props else None)
    bg_color = _sanitize_css_value(raw_bg) if raw_bg is not None else ""
    if not bg_color:
        bg_color = "#0066cc"

    raw_text_color = (
        text_children[0].text_color
        if text_children[0].text_color is not None
        else _contrasting_text_color(bg_color)
    )
    text_color = _sanitize_css_value(raw_text_color) if raw_text_color else ""
    if not text_color:
        text_color = "#ffffff"

    font_family = "Arial,Helvetica,sans-serif"
    child_props_font = text_children[0].font_family
    if child_props_font:
        font_family = _font_stack(_sanitize_css_value(child_props_font) or "Arial")

    font_size = int(text_children[0].font_size if text_children[0].font_size is not None else 16)

    _validate_button_contrast(bg_color, text_color, font_size)

    # Corner radius: use design value, fall back to 4px
    radius_px = int(node.corner_radius) if node.corner_radius else 4
    border_radius = f"{radius_px}px"
    shortest_side = min(width, height)
    arcsize_pct = round((radius_px / shortest_side) * 100) if shortest_side > 0 else 8

    # Hyperlink: use design value, fall back to "#"
    btn_href = html.escape(node.hyperlink or "#", quote=True)

    v_pad = max(8, (height - font_size) // 2)
    h_pad = 24

    slot_attr = ""
    if slot_counter is not None:
        slot_attr = f' data-slot-name="{_next_slot_name(slot_counter, "cta")}"'

    parts = [
        f'{pad}<td align="center">',
        f"{pad}  <!--[if mso]>",
        (
            f'{pad}  <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"'
            f' style="width:{width}px;height:{height}px;"'
            f' arcsize="{arcsize_pct}%"'
            f' fillcolor="{bg_color}" stroke="false">'
        ),
        (f'{pad}    <v:textbox inset="0,0,0,0" style="mso-fit-shape-to-text:true;">'),
        (
            f'{pad}      <center style="font-family:Arial,sans-serif;'
            f"font-size:{font_size}px;"
            f'color:{text_color};">{button_text}</center>'
        ),
        f"{pad}    </v:textbox>",
        f"{pad}  </v:roundrect>",
        f"{pad}  <![endif]-->",
        f"{pad}  <!--[if !mso]><!-->",
        (
            f"{pad}  "
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
            ' style="border-collapse:collapse;'
            'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
        ),
        f"{pad}    <tr>",
        (f'{pad}      <td style="border-radius:{border_radius};background-color:{bg_color};">'),
        (
            f'{pad}        <a href="{btn_href}"{slot_attr} style="display:inline-block;'
            f"padding:{v_pad}px {h_pad}px;"
            f"font-family:{font_family};font-size:{font_size}px;"
            f"color:{text_color};text-decoration:none;"
            f'mso-line-height-rule:exactly;">{button_text}</a>'
        ),
        f"{pad}      </td>",
        f"{pad}    </tr>",
        f"{pad}  </table>",
        f"{pad}  <!--<![endif]-->",
        f"{pad}</td>",
    ]
    return "\n".join(parts)


@dataclass(frozen=True)
class _FrameStyle:
    """Computed frame styling: bgcolor, gradient, border, font, MSO VML wrapper."""

    bgcolor_attr: str
    style_parts: list[str]
    effective_bg: str | None
    effective_font: str | None
    bg_vml_open: str
    bg_vml_close: str


@dataclass(frozen=True)
class _FramePadding:
    """Computed frame inner-td padding."""

    has_padding: bool
    padding_css: str


def _text_style_from_props(
    props: _NodeProps, node_name: str, ctx: RenderContext
) -> tuple[str, str]:
    """Resolve font-family + accumulated inline style suffix from text props."""
    font_family = ""
    extra_style = ""
    if props.font_family:
        safe_family = _sanitize_css_value(props.font_family)
        if safe_family:
            font_family = _font_stack(safe_family)
    if props.font_size:
        extra_style += f"font-size:{int(props.font_size)}px;"
    if props.font_weight:
        try:
            weight_num = int(props.font_weight)
            mapped = "bold" if weight_num >= 500 else "normal"
        except (ValueError, TypeError):
            mapped = "bold" if str(props.font_weight).lower() == "bold" else "normal"
        extra_style += f"font-weight:{mapped};"
    if props.line_height_px:
        lh = round(props.line_height_px)
        extra_style += f"line-height:{lh}px;mso-line-height-rule:exactly;"
    if props.letter_spacing_px:
        if ctx.compat:
            ctx.compat.check_and_warn("letter-spacing", context=f"Text node '{node_name}'")
        ls = round(props.letter_spacing_px, 1)
        extra_style += f"letter-spacing:{ls}px;"
    if props.text_transform:
        extra_style += f"text-transform:{_sanitize_css_value(props.text_transform)};"
    if props.text_decoration:
        extra_style += f"text-decoration:{_sanitize_css_value(props.text_decoration)};"
    return font_family, extra_style


def _render_text_node(node: DesignNode, ctx: RenderContext) -> str:
    """Render a TEXT node as a semantic <td> with inline styles.

    Resolves font-family/size/weight/line-height/letter-spacing/transform/decoration
    from optional props, then maps text-align and color, computes the MSO font-alt
    fallback, and decides heading level from the layout analyzer's text_meta.
    """
    pad = "  " * ctx.indent
    props = ctx.props_map.get(node.id) if ctx.props_map else None
    raw_text = node.text_content or ""
    content = (
        _render_style_runs(raw_text, node.style_runs) if node.style_runs else html.escape(raw_text)
    )
    font_family = ctx.parent_font or "Arial,Helvetica,sans-serif"
    extra_style = ""
    if props:
        prop_font, extra_style = _text_style_from_props(props, node.name or "", ctx)
        if prop_font:
            font_family = prop_font
    if node.text_align and node.text_align != "left":
        extra_style += f"text-align:{node.text_align};"
    if node.text_color:
        safe_text_color = _sanitize_css_value(node.text_color)
        if safe_text_color:
            extra_style += f"color:{safe_text_color};"
    elif ctx.parent_bg:
        extra_style += f"color:{_contrasting_text_color(ctx.parent_bg)};"
    mso_alt = ""
    if font_family:
        primary = font_family.split(",")[0].strip().strip("'\"")
        for mapped_name, chain in _FALLBACK_MAP.items():
            if mapped_name.strip("'\"").lower() == primary.lower() and chain:
                mso_alt = f"mso-font-alt:{chain[0]};"
                break
    if "line-height:" in extra_style and "mso-line-height-rule" not in extra_style:
        extra_style += "mso-line-height-rule:exactly;"

    is_heading = False
    heading_level: int | None = None
    if ctx.text_meta and node.id in ctx.text_meta:
        is_heading = ctx.text_meta[node.id].is_heading
    if is_heading:
        font_size_val = props.font_size if props else None
        if font_size_val is None:
            font_size_val = node.font_size if node.font_size is not None else 16.0
        heading_level = _determine_heading_level(font_size_val, ctx.body_font_size)
        if heading_level is None:
            heading_level = 3

    return _render_semantic_text(
        content=content,
        font_family=font_family,
        extra_style=extra_style,
        mso_alt=mso_alt,
        pad=pad,
        is_heading=is_heading,
        heading_level=heading_level,
        slot_counter=ctx.slot_counter,
    )


def _render_image_node(node: DesignNode, ctx: RenderContext) -> str:
    """Render an IMAGE node as <img> with placeholder src and accessible alt."""
    pad = "  " * ctx.indent
    w_val = int(node.width) if node.width else None
    h_val = int(node.height) if node.height else None
    w = f' width="{w_val}"' if w_val else ""
    h = f' height="{h_val}"' if h_val else ""
    alt = _meaningful_alt(node.name, section=ctx.current_section)
    node_id_attr = f' data-node-id="{html.escape(node.id)}"'
    slot_attr = ""
    if ctx.slot_counter is not None:
        slot_attr = f' data-slot-name="{_next_slot_name(ctx.slot_counter, "image")}"'
    max_w = f"max-width:{w_val}px;" if w_val else ""
    return (
        f'{pad}<img src="" alt="{alt}"{node_id_attr}{slot_attr}{w}{h}'
        f' style="display:block;border:0;outline:none;text-decoration:none;'
        f'-ms-interpolation-mode:bicubic;width:100%;{max_w}height:auto;" />'
    )


def _render_image_only_frame_node(node: DesignNode, ctx: RenderContext) -> str:
    """Render a childless FRAME with image_ref as a standalone <img>."""
    pad = "  " * ctx.indent
    w_val = int(node.width) if node.width else None
    h_val = int(node.height) if node.height else None
    w = f' width="{w_val}"' if w_val else ""
    h = f' height="{h_val}"' if h_val else ""
    alt = _meaningful_alt(node.name, section=ctx.current_section)
    max_w = f"max-width:{w_val}px;" if w_val else ""
    return (
        f'{pad}<img src="{html.escape(node.image_ref or "")}" alt="{alt}"'
        f' data-node-id="{html.escape(node.id)}"{w}{h}'
        f' style="display:block;border:0;outline:none;text-decoration:none;'
        f'-ms-interpolation-mode:bicubic;width:100%;{max_w}height:auto;" />'
    )


def _frame_styling(node: DesignNode, ctx: RenderContext, props: _NodeProps | None) -> _FrameStyle:
    """Compute background, gradient, border, radius and font for a frame."""
    pad = "  " * ctx.indent
    bgcolor_attr = ""
    style_parts: list[str] = [
        "border-collapse:collapse",
        "mso-table-lspace:0pt",
        "mso-table-rspace:0pt",
    ]
    effective_bg = ctx.parent_bg

    if node.fill_color:
        bgcolor_attr = f' bgcolor="{html.escape(node.fill_color)}"'
        effective_bg = node.fill_color
    if props and props.bg_color:
        bgcolor_attr = f' bgcolor="{html.escape(props.bg_color)}"'
        effective_bg = props.bg_color

    if ctx.gradients_map and node.name in ctx.gradients_map:
        grad = ctx.gradients_map[node.name]
        gradient_css = _gradient_to_css(grad)
        if not bgcolor_attr:
            bgcolor_attr = f' bgcolor="{html.escape(grad.fallback_hex)}"'
        style_parts.append(f"background:{gradient_css}")

    if node.stroke_weight and node.stroke_color:
        stroke_w = int(node.stroke_weight)
        safe_stroke = _sanitize_css_value(node.stroke_color)
        if safe_stroke:
            style_parts.append(f"border:{stroke_w}px solid {safe_stroke}")

    if node.corner_radius:
        style_parts.append(f"border-radius:{int(node.corner_radius)}px")

    bg_vml_open = ""
    bg_vml_close = ""
    if node.image_ref and node.children and _is_safe_url(node.image_ref):
        safe_url = html.escape(node.image_ref)
        style_parts.append(f"background-image:url('{safe_url}')")
        style_parts.append("background-size:cover")
        style_parts.append("background-position:center")
        style_parts.append("background-repeat:no-repeat")
        bg_w = int(node.width) if node.width else 600
        bg_h = int(node.height) if node.height else 300
        bg_vml_open = (
            f"{pad}<!--[if gte mso 9]>\n"
            f'{pad}<v:rect xmlns:v="urn:schemas-microsoft-com:vml"'
            f' fill="true" stroke="false"'
            f' style="width:{bg_w}px;height:{bg_h}px;">\n'
            f'{pad}<v:fill type="frame" src="{safe_url}" />\n'
            f'{pad}<v:textbox inset="0,0,0,0">\n'
            f"{pad}<![endif]-->"
        )
        bg_vml_close = f"{pad}<!--[if gte mso 9]>\n{pad}</v:textbox></v:rect>\n{pad}<![endif]-->"

    effective_font = ctx.parent_font
    if props and props.font_family:
        safe_family = _sanitize_css_value(props.font_family)
        if safe_family:
            effective_font = f"{safe_family},Arial,Helvetica,sans-serif"

    return _FrameStyle(
        bgcolor_attr=bgcolor_attr,
        style_parts=style_parts,
        effective_bg=effective_bg,
        effective_font=effective_font,
        bg_vml_open=bg_vml_open,
        bg_vml_close=bg_vml_close,
    )


def _frame_padding(node: DesignNode, props: _NodeProps | None) -> _FramePadding:
    """Compute the inner-td padding string from node + props padding values."""
    pad_top = (
        node.padding_top if node.padding_top is not None else (props.padding_top if props else 0)
    )
    pad_right = (
        node.padding_right
        if node.padding_right is not None
        else (props.padding_right if props else 0)
    )
    pad_bottom = (
        node.padding_bottom
        if node.padding_bottom is not None
        else (props.padding_bottom if props else 0)
    )
    pad_left = (
        node.padding_left if node.padding_left is not None else (props.padding_left if props else 0)
    )
    has_padding = any(v > 0 for v in (pad_top, pad_right, pad_bottom, pad_left))
    padding_css = (
        f"padding:{int(pad_top)}px {int(pad_right)}px {int(pad_bottom)}px {int(pad_left)}px"
        if has_padding
        else ""
    )
    return _FramePadding(has_padding=has_padding, padding_css=padding_css)


def _render_frame_flat_fallback(
    node: DesignNode, ctx: RenderContext, child_ctx: RenderContext
) -> str:
    """Flatten frame children when nesting depth >6. Avoids Outlook crashes."""
    pad = "  " * ctx.indent
    logger.warning(
        "design_sync.nesting_depth_exceeded",
        node_id=node.id,
        node_name=node.name,
        depth=ctx.depth,
    )
    flat_lines: list[str] = []
    for child in node.children:
        child_html = node_to_email_html(child, child_ctx)
        is_button = bool(ctx.button_ids and child.id in ctx.button_ids)
        if child.type != DesignNodeType.TEXT and not is_button:
            flat_lines.append(f"{pad}<tr><td>{child_html}</td></tr>")
        else:
            flat_lines.append(f"{pad}<tr>{child_html}</tr>")
    return "\n".join(flat_lines) if flat_lines else ""


def _render_inline_row(
    row: list[DesignNode],
    ctx: RenderContext,
    style: _FrameStyle,
    inner_indent: int,
) -> list[str]:
    """Render a row of TEXT/IMAGE children as inline content within one <td>."""
    pad = "  " * ctx.indent
    inner_pad = "  " * inner_indent
    td_font = style.effective_font or "Arial,Helvetica,sans-serif"
    lines: list[str] = [f'{pad}    <tr><td style="vertical-align:middle;font-family:{td_font};">']
    for child in row:
        if child.type == DesignNodeType.TEXT:
            text = html.escape(child.text_content or "")
            if not text:
                continue
            child_props = ctx.props_map.get(child.id) if ctx.props_map else None
            font = td_font
            child_style_parts: list[str] = []
            if child_props:
                if child_props.font_family:
                    sf = _sanitize_css_value(child_props.font_family)
                    if sf:
                        font = _font_stack(sf)
                if child_props.font_size:
                    child_style_parts.append(f"font-size:{int(child_props.font_size)}px")
                if child_props.font_weight:
                    try:
                        wn = int(child_props.font_weight)
                        mw = "bold" if wn >= 500 else "normal"
                    except (ValueError, TypeError):
                        s = str(child_props.font_weight).lower()
                        mw = "bold" if s == "bold" else "normal"
                    child_style_parts.append(f"font-weight:{mw}")
            child_style_parts.insert(0, f"font-family:{font}")
            if child.text_color:
                sc = _sanitize_css_value(child.text_color)
                if sc:
                    child_style_parts.append(f"color:{sc}")
            elif style.effective_bg:
                child_style_parts.append(f"color:{_contrasting_text_color(style.effective_bg)}")
            css = ";".join(child_style_parts)
            lines.append(f'{inner_pad}<span style="{css}">{text}</span>')
        elif child.type == DesignNodeType.IMAGE:
            w = str(int(child.width)) if child.width else ""
            h = str(int(child.height)) if child.height else ""
            alt = _meaningful_alt(child.name, section=ctx.current_section)
            w_attr = f' width="{w}"' if w else ""
            h_attr = f' height="{h}"' if h else ""
            lines.append(
                f'{inner_pad}<img src="" alt="{alt}"'
                f' data-node-id="{child.id}"'
                f"{w_attr}{h_attr}"
                f' style="vertical-align:middle;border:0;" />'
            )
    lines.append(f"{pad}    </td></tr>")
    return lines


def _render_single_col_row(
    row: list[DesignNode],
    ctx: RenderContext,
    style: _FrameStyle,
    *,
    has_padding: bool,
    layout_dir: str | None,
    gap: float,
    cross_gap: float,
    section: EmailSection | None,
) -> list[str]:
    """Render a single-column row (or short row of inline children)."""
    pad = "  " * ctx.indent
    lines: list[str] = [f"{pad}    <tr>"]
    child_indent = ctx.indent + (4 if has_padding else 2)
    for cell_idx, child in enumerate(row):
        child_ctx = ctx.with_child(
            indent=child_indent,
            parent_bg=style.effective_bg,
            parent_font=style.effective_font,
            section=section,
        )
        child_html = node_to_email_html(child, child_ctx)
        is_button = bool(ctx.button_ids and child.id in ctx.button_ids)
        if child.type != DesignNodeType.TEXT and not is_button:
            td_styles: list[str] = []
            if style.effective_font:
                td_styles.append(f"font-family:{style.effective_font}")
            if layout_dir == "row" and cell_idx > 0 and gap > 0:
                td_styles.append(f"padding-left:{int(gap)}px")
            if cross_gap > 0:
                if layout_dir == "row":
                    td_styles.append(f"padding-top:{int(cross_gap)}px")
                elif layout_dir == "column":
                    td_styles.append(f"padding-left:{int(cross_gap)}px")
            td_style = f' style="{";".join(td_styles)}"' if td_styles else ""
            lines.append(f"{pad}      <td{td_style}>")
            lines.append(child_html)
            lines.append(f"{pad}      </td>")
        else:
            lines.append(child_html)
    lines.append(f"{pad}    </tr>")
    return lines


def _render_frame_rows(
    rows: list[list[DesignNode]],
    ctx: RenderContext,
    style: _FrameStyle,
    *,
    has_padding: bool,
    layout_dir: str | None,
    gap: float,
    cross_gap: float,
    effective_width: int,
    section: EmailSection | None,
) -> list[str]:
    """Iterate rows, dispatching to inline / multi-column / single-column renderers."""
    pad = "  " * ctx.indent
    lines: list[str] = []
    gap_px = int(gap)
    inner_indent = ctx.indent + (3 if has_padding else 2)
    mc_indent = ctx.indent + (2 if has_padding else 1)

    for row_idx, row in enumerate(rows):
        if row_idx > 0 and gap > 0 and layout_dir in ("column", None):
            lines.append(
                f'{pad}    <tr><td style="height:{gap_px}px;'
                f"font-size:1px;line-height:1px;"
                f'mso-line-height-rule:exactly;" '
                f'aria-hidden="true">&nbsp;</td></tr>'
            )

        if len(row) > 1 and _is_inline_row(row):
            lines.extend(_render_inline_row(row, ctx, style, inner_indent))
            continue

        if len(row) > 1:
            col_widths = _calculate_column_widths(row, effective_width, gap=gap_px)
            mc_ctx = ctx.with_child(
                indent=mc_indent,
                depth_delta=0,
                parent_bg=style.effective_bg,
                parent_font=style.effective_font,
                section=section,
                container_width=effective_width,
            )
            lines.extend(
                _render_multi_column_row(
                    row,
                    column_widths=col_widths,
                    gap=gap_px,
                    indent=mc_indent,
                    ctx=mc_ctx,
                )
            )
            continue

        lines.extend(
            _render_single_col_row(
                row,
                ctx,
                style,
                has_padding=has_padding,
                layout_dir=layout_dir,
                gap=gap,
                cross_gap=cross_gap,
                section=section,
            )
        )
    return lines


def _resolve_frame_layout(
    node: DesignNode, props: _NodeProps | None
) -> tuple[str | None, float, float, list[list[DesignNode]]]:
    """Pick layout direction, gaps, and row groupings for a frame's children."""
    layout_dir = props.layout_direction if props else None
    if node.layout_mode == "HORIZONTAL":
        layout_dir = "row"
    elif node.layout_mode == "VERTICAL":
        layout_dir = "column"

    gap = (
        props.item_spacing if props else (node.item_spacing if node.item_spacing is not None else 0)
    )
    cross_gap = (
        props.counter_axis_spacing
        if props
        else (node.counter_axis_spacing if node.counter_axis_spacing is not None else 0)
    )

    if layout_dir == "row":
        rows = [node.children]
    elif layout_dir == "column":
        rows = [[child] for child in node.children]
    else:
        rows = _group_into_rows(node.children, parent_width=node.width)
    return layout_dir, gap, cross_gap, rows


def _render_frame_node(node: DesignNode, ctx: RenderContext) -> str:
    """Render a FRAME/GROUP/COMPONENT/INSTANCE as a <table> with rows."""
    pad = "  " * ctx.indent
    props = ctx.props_map.get(node.id) if ctx.props_map else None

    section = ctx.current_section
    if ctx.section_map and node.id in ctx.section_map:
        section = ctx.section_map[node.id]

    style = _frame_styling(node, ctx, props)
    pad_info = _frame_padding(node, props)

    if ctx.depth > 6:
        flat_ctx = ctx.with_child(
            parent_bg=style.effective_bg,
            parent_font=style.effective_font,
            section=section,
        )
        return _render_frame_flat_fallback(node, ctx, flat_ctx)

    style_attr = f' style="{";".join(style.style_parts)}"'
    component_attr = ""
    if ctx.depth == 0 and ctx.slot_counter is not None:
        component_attr = f' data-component-name="{html.escape(node.name or "")}"'

    lines: list[str] = []
    if style.bg_vml_open:
        lines.append(style.bg_vml_open)
    lines.append(
        f'{pad}<table width="100%"{style.bgcolor_attr}{component_attr}{style_attr}'
        f' cellpadding="0" cellspacing="0" border="0" role="presentation">'
    )

    if not node.children:
        if pad_info.has_padding:
            lines.append(f'{pad}  <tr><td style="{pad_info.padding_css}">&nbsp;</td></tr>')
        else:
            lines.append(f"{pad}  <tr><td>&nbsp;</td></tr>")
    else:
        layout_dir, gap, cross_gap, rows = _resolve_frame_layout(node, props)
        effective_width = int(node.width) if node.width else ctx.container_width

        if pad_info.has_padding:
            lines.append(f'{pad}  <tr><td style="{pad_info.padding_css}">')
            lines.append(
                f'{pad}    <table width="100%" cellpadding="0" cellspacing="0"'
                f' border="0" role="presentation"'
                f' style="border-collapse:collapse;'
                f'mso-table-lspace:0pt;mso-table-rspace:0pt;">'
            )

        lines.extend(
            _render_frame_rows(
                rows,
                ctx,
                style,
                has_padding=pad_info.has_padding,
                layout_dir=layout_dir,
                gap=gap,
                cross_gap=cross_gap,
                effective_width=effective_width,
                section=section,
            )
        )

        if pad_info.has_padding:
            lines.append(f"{pad}    </table>")
            lines.append(f"{pad}  </td></tr>")
    lines.append(f"{pad}</table>")
    if style.bg_vml_close:
        lines.append(style.bg_vml_close)
    return "\n".join(lines)


_FRAME_TYPES: frozenset[DesignNodeType] = frozenset(
    {
        DesignNodeType.FRAME,
        DesignNodeType.GROUP,
        DesignNodeType.COMPONENT,
        DesignNodeType.INSTANCE,
    }
)


def node_to_email_html(node: DesignNode, ctx: RenderContext | None = None) -> str:
    """Convert a DesignNode tree to email-safe HTML (table layout).

    Converts flex/grid frames to table rows/cells. Produces a structural
    skeleton — the Scaffolder fills content. Pass ``ctx`` to thread inherited
    render state (parent bg/font, section map, button ids, etc.) through the
    recursion; defaults are valid for top-level calls without layout analysis.
    """
    if ctx is None:
        ctx = RenderContext()

    if node.type == DesignNodeType.TEXT:
        return _render_text_node(node, ctx)
    if node.type == DesignNodeType.IMAGE:
        return _render_image_node(node, ctx)
    if node.id in ctx.button_ids:
        props = ctx.props_map.get(node.id) if ctx.props_map else None
        return _render_button(
            node,
            pad="  " * ctx.indent,
            props=props,
            slot_counter=ctx.slot_counter,
        )
    if node.type in _FRAME_TYPES:
        if node.image_ref and not node.children and _is_safe_url(node.image_ref):
            return _render_image_only_frame_node(node, ctx)
        return _render_frame_node(node, ctx)
    return ""


def _group_into_rows(
    nodes: list[DesignNode],
    tolerance: float = 20.0,
    *,
    parent_width: float | None = None,
) -> list[list[DesignNode]]:
    """Group sibling nodes into rows based on y-position proximity.

    Handles three cases for y-position data:
    - All y=None: treat as single horizontal row (auto-layout without positions).
    - All y known: sort+group by y-position proximity (tolerance default 20px).
    - Mixed: group y-known nodes normally, append y=None nodes to last row.

    Hero image detection: a single IMAGE node spanning >=80% of
    the parent width gets its own row regardless of y-tolerance.
    """
    if not nodes:
        return []

    # Partition into y-known and y-unknown
    y_known = [n for n in nodes if n.y is not None]
    y_unknown = [n for n in nodes if n.y is None]

    # All y=None → single horizontal row (auto-layout assumption)
    if not y_known:
        return [nodes]

    sorted_nodes = sorted(
        y_known,
        key=lambda n: (n.y if n.y is not None else 0, n.x if n.x is not None else 0),
    )
    rows: list[list[DesignNode]] = [[sorted_nodes[0]]]

    for node in sorted_nodes[1:]:
        last_row_y = rows[-1][0].y if rows[-1][0].y is not None else 0
        node_y = node.y if node.y is not None else 0
        if abs(node_y - last_row_y) <= tolerance:
            rows[-1].append(node)
        else:
            rows.append([node])

    # Mixed: append y-unknown nodes to the last row
    if y_unknown:
        rows[-1].extend(y_unknown)

    # Sort each row by x-position (left to right)
    for row in rows:
        row.sort(key=lambda n: n.x if n.x is not None else 0)

    # Hero image detection: split wide images into their own rows
    if parent_width and parent_width > 0:
        threshold = parent_width * 0.8
        final_rows: list[list[DesignNode]] = []
        for row in rows:
            hero_nodes: list[DesignNode] = []
            other_nodes: list[DesignNode] = []
            for n in row:
                if (
                    n.type == DesignNodeType.IMAGE
                    and n.width is not None
                    and n.width >= threshold
                    and len(row) > 1
                ):
                    hero_nodes.append(n)
                else:
                    other_nodes.append(n)
            for hero in hero_nodes:
                final_rows.append([hero])
            if other_nodes:
                final_rows.append(other_nodes)
        rows = final_rows

    return rows


def _calculate_column_widths(
    children: list[DesignNode],
    container_width: float,
    gap: float = 0,
) -> list[int]:
    """Calculate proportional pixel widths for multi-column children.

    Args:
        children: Column child nodes (must have len >= 1).
        container_width: Available parent width in pixels.
        gap: Gap between columns in pixels.

    Returns:
        List of integer pixel widths, one per child. Last column absorbs rounding.
    """
    n = len(children)
    if n == 0:
        return []
    if n == 1:
        return [int(container_width)]

    total_gap = gap * (n - 1)
    avail = max(container_width - total_gap, n)  # at least 1px per column

    known = [(i, c.width) for i, c in enumerate(children) if c.width is not None]
    unknown_indices = [i for i, c in enumerate(children) if c.width is None]

    widths = [0] * n

    if len(known) == n:
        # All children have widths — proportional distribution
        total_child_w = sum(w for _, w in known)
        if total_child_w > 0:
            # B4: Sparse layout detection — when children are small relative to
            # container, keep natural widths instead of stretching to fill
            if total_child_w < container_width * 0.6:
                for i, w in known:
                    widths[i] = int(w)
                return widths
            for i, w in known:
                widths[i] = round(avail * (w / total_child_w))
        else:
            per = int(avail / n)
            widths = [per] * n
    elif not known:
        # No children have widths — equal distribution
        per = int(avail / n)
        widths = [per] * n
    else:
        # Mixed: proportional for known, split remainder for unknown
        total_known_w = sum(w for _, w in known)
        if total_known_w > 0:
            for i, w in known:
                widths[i] = round(avail * (w / total_known_w) * (len(known) / n))
        used = sum(widths[i] for i, _ in known)
        remainder = int(avail) - used
        if unknown_indices:
            per_unknown = remainder // len(unknown_indices)
            for i in unknown_indices:
                widths[i] = per_unknown

    # Last column absorbs rounding error
    widths[-1] = int(avail) - sum(widths[:-1])

    return widths


def _col_padding(col_index: int, col_count: int, gutter: float = 8.0) -> str:
    """Asymmetric gutter padding for multi-column layouts (G11 pattern)."""
    if col_count <= 1:
        return "0"
    if col_index == 0:
        return f"0 {gutter}px 0 0"
    if col_index == col_count - 1:
        return f"0 0 0 {gutter}px"
    half = gutter / 2
    return f"0 {half}px 0 {half}px"


def _render_multi_column_row(
    children: list[DesignNode],
    *,
    column_widths: list[int],
    gap: int,
    indent: int,
    ctx: RenderContext,
) -> list[str]:
    """Render a multi-column row using hybrid inline-block + MSO ghost table.

    Returns a list of HTML lines forming a single ``<tr>`` with columns rendered
    as ``display:inline-block`` divs for modern clients and an MSO ghost table
    for Outlook. ``ctx`` carries the inherited render state for child recursion.
    """
    pad = "  " * indent
    inner_pad = "  " * (indent + 1)
    col_pad = "  " * (indent + 2)
    lines: list[str] = []

    if ctx.compat:
        ctx.compat.check_and_warn(
            "display",
            value="inline-block",
            context="Multi-column layout",
        )

    lines.append(f"{pad}<tr>")
    lines.append(
        f'{inner_pad}<td style="font-size:0;text-align:center;mso-line-height-rule:exactly;">'
    )

    lines.append(
        f"{inner_pad}<!--[if mso]>"
        f'<table role="presentation" width="{ctx.container_width}"'
        f' cellpadding="0" cellspacing="0" border="0"'
        f' style="border-collapse:collapse;mso-table-lspace:0pt;'
        f'mso-table-rspace:0pt;">'
        f"<tr><![endif]-->"
    )

    for col_idx, (child, col_width) in enumerate(zip(children, column_widths, strict=True)):
        if col_idx > 0 and gap > 0:
            lines.append(f'{inner_pad}<!--[if mso]><td width="{gap}"></td><![endif]-->')
        lines.extend(
            _render_mso_column(
                child,
                ctx=ctx,
                col_idx=col_idx,
                col_count=len(children),
                col_width=col_width,
                indent=indent,
                inner_pad=inner_pad,
                col_pad=col_pad,
            )
        )

    lines.append(f"{inner_pad}<!--[if mso]></tr></table><![endif]-->")
    lines.append(f"{inner_pad}</td>")
    lines.append(f"{pad}</tr>")

    return lines


def _render_mso_column(
    child: DesignNode,
    *,
    ctx: RenderContext,
    col_idx: int,
    col_count: int,
    col_width: int,
    indent: int,
    inner_pad: str,
    col_pad: str,
) -> list[str]:
    """Render one column of a multi-column row (MSO ghost cell + responsive div)."""
    lines: list[str] = [
        f'{inner_pad}<!--[if mso]><td width="{col_width}" valign="top"><![endif]-->',
        # G-REF-1: <div class="column"> matches golden components and enables
        # mobile stacking via CSS .column { display: block !important; }
        f'{inner_pad}<div class="column"'
        f' style="display:inline-block;max-width:{col_width}px;'
        f'width:100%;vertical-align:top;">',
        f'{col_pad}<table role="presentation" width="100%"'
        f' cellpadding="0" cellspacing="0" border="0"'
        f' style="border-collapse:collapse;mso-table-lspace:0pt;'
        f'mso-table-rspace:0pt;">',
    ]
    child_ctx = ctx.with_child(indent=indent + 2, container_width=col_width)
    child_html = node_to_email_html(child, child_ctx)
    if not child_html or not child_html.strip():
        lines.append(f"{col_pad}</table>")
        lines.append(f"{inner_pad}</div>")
        lines.append(f"{inner_pad}<!--[if mso]></td><![endif]-->")
        return lines
    padding = _col_padding(col_idx, col_count)
    lines.append(f'{col_pad}<tr><td style="padding:{padding};">{child_html}</td></tr>')
    lines.append(f"{col_pad}</table>")
    lines.append(f"{inner_pad}</div>")
    lines.append(f"{inner_pad}<!--[if mso]></td><![endif]-->")
    return lines
