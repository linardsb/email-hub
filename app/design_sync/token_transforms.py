"""Email-safe token validation and transformation layer.

Sits between extraction (figma/penpot providers) and consumption
(converter, Scaffolder, design system). Ensures all tokens are
email-safe before downstream use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

if TYPE_CHECKING:
    from app.design_sync.caniemail import CanieMailData

from app.core.logging import get_logger
from app.design_sync.protocol import (
    ExtractedColor,
    ExtractedGradient,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
)
from app.projects.design_system import BrandPalette, Typography
from app.shared.color import contrast_ratio, relative_luminance

logger = get_logger(__name__)


# ── YAML-backed font fallback data (08c part 4 — moved from converter.py) ──
_FONT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "email_client_fonts.yaml"
_FONT_DATA: dict[str, Any] = (
    yaml.safe_load(_FONT_DATA_PATH.read_text()) if _FONT_DATA_PATH.exists() else {}
)
_FALLBACK_MAP: dict[str, list[str]] = _FONT_DATA.get("fallback_map", {})


def _font_stack(family: str) -> str:
    """Build email-safe CSS font stack using data/email_client_fonts.yaml."""
    family_clean = family.strip("'\"").strip()
    if "," in family_clean:
        return family_clean
    for mapped_name, chain in _FALLBACK_MAP.items():
        if mapped_name.strip("'\"").lower() == family_clean.lower():
            return f"{family_clean}, {', '.join(str(f) for f in chain)}"
    if family_clean.lower() in {"sans-serif", "serif", "monospace", "cursive", "fantasy"}:
        return family_clean
    return f"{family_clean}, Arial, Helvetica, sans-serif"


@dataclass(frozen=True)
class TokenWarning:
    """A validation warning or auto-fix applied to a design token."""

    level: Literal["info", "warning", "error"]
    field: str
    message: str
    original_value: str | None = None
    fixed_value: str | None = None


# ── CSS Color Level 4 named-color → 6-digit hex map (148 entries) ──

CSS_NAMED_COLORS: dict[str, str] = {
    "aliceblue": "#F0F8FF",
    "antiquewhite": "#FAEBD7",
    "aqua": "#00FFFF",
    "aquamarine": "#7FFFD4",
    "azure": "#F0FFFF",
    "beige": "#F5F5DC",
    "bisque": "#FFE4C4",
    "black": "#000000",
    "blanchedalmond": "#FFEBCD",
    "blue": "#0000FF",
    "blueviolet": "#8A2BE2",
    "brown": "#A52A2A",
    "burlywood": "#DEB887",
    "cadetblue": "#5F9EA0",
    "chartreuse": "#7FFF00",
    "chocolate": "#D2691E",
    "coral": "#FF7F50",
    "cornflowerblue": "#6495ED",
    "cornsilk": "#FFF8DC",
    "crimson": "#DC143C",
    "cyan": "#00FFFF",
    "darkblue": "#00008B",
    "darkcyan": "#008B8B",
    "darkgoldenrod": "#B8860B",
    "darkgray": "#A9A9A9",
    "darkgreen": "#006400",
    "darkgrey": "#A9A9A9",
    "darkkhaki": "#BDB76B",
    "darkmagenta": "#8B008B",
    "darkolivegreen": "#556B2F",
    "darkorange": "#FF8C00",
    "darkorchid": "#9932CC",
    "darkred": "#8B0000",
    "darksalmon": "#E9967A",
    "darkseagreen": "#8FBC8F",
    "darkslateblue": "#483D8B",
    "darkslategray": "#2F4F4F",
    "darkslategrey": "#2F4F4F",
    "darkturquoise": "#00CED1",
    "darkviolet": "#9400D3",
    "deeppink": "#FF1493",
    "deepskyblue": "#00BFFF",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1E90FF",
    "firebrick": "#B22222",
    "floralwhite": "#FFFAF0",
    "forestgreen": "#228B22",
    "fuchsia": "#FF00FF",
    "gainsboro": "#DCDCDC",
    "ghostwhite": "#F8F8FF",
    "gold": "#FFD700",
    "goldenrod": "#DAA520",
    "gray": "#808080",
    "green": "#008000",
    "greenyellow": "#ADFF2F",
    "grey": "#808080",
    "honeydew": "#F0FFF0",
    "hotpink": "#FF69B4",
    "indianred": "#CD5C5C",
    "indigo": "#4B0082",
    "ivory": "#FFFFF0",
    "khaki": "#F0E68C",
    "lavender": "#E6E6FA",
    "lavenderblush": "#FFF0F5",
    "lawngreen": "#7CFC00",
    "lemonchiffon": "#FFFACD",
    "lightblue": "#ADD8E6",
    "lightcoral": "#F08080",
    "lightcyan": "#E0FFFF",
    "lightgoldenrodyellow": "#FAFAD2",
    "lightgray": "#D3D3D3",
    "lightgreen": "#90EE90",
    "lightgrey": "#D3D3D3",
    "lightpink": "#FFB6C1",
    "lightsalmon": "#FFA07A",
    "lightseagreen": "#20B2AA",
    "lightskyblue": "#87CEFA",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "lightsteelblue": "#B0C4DE",
    "lightyellow": "#FFFFE0",
    "lime": "#00FF00",
    "limegreen": "#32CD32",
    "linen": "#FAF0E6",
    "magenta": "#FF00FF",
    "maroon": "#800000",
    "mediumaquamarine": "#66CDAA",
    "mediumblue": "#0000CD",
    "mediumorchid": "#BA55D3",
    "mediumpurple": "#9370DB",
    "mediumseagreen": "#3CB371",
    "mediumslateblue": "#7B68EE",
    "mediumspringgreen": "#00FA9A",
    "mediumturquoise": "#48D1CC",
    "mediumvioletred": "#C71585",
    "midnightblue": "#191970",
    "mintcream": "#F5FFFA",
    "mistyrose": "#FFE4E1",
    "moccasin": "#FFE4B5",
    "navajowhite": "#FFDEAD",
    "navy": "#000080",
    "oldlace": "#FDF5E6",
    "olive": "#808000",
    "olivedrab": "#6B8E23",
    "orange": "#FFA500",
    "orangered": "#FF4500",
    "orchid": "#DA70D6",
    "palegoldenrod": "#EEE8AA",
    "palegreen": "#98FB98",
    "paleturquoise": "#AFEEEE",
    "palevioletred": "#DB7093",
    "papayawhip": "#FFEFD5",
    "peachpuff": "#FFDAB9",
    "peru": "#CD853F",
    "pink": "#FFC0CB",
    "plum": "#DDA0DD",
    "powderblue": "#B0E0E6",
    "purple": "#800080",
    "rebeccapurple": "#663399",
    "red": "#FF0000",
    "rosybrown": "#BC8F8F",
    "royalblue": "#4169E1",
    "saddlebrown": "#8B4513",
    "salmon": "#FA8072",
    "sandybrown": "#F4A460",
    "seagreen": "#2E8B57",
    "seashell": "#FFF5EE",
    "sienna": "#A0522D",
    "silver": "#C0C0C0",
    "skyblue": "#87CEEB",
    "slateblue": "#6A5ACD",
    "slategray": "#708090",
    "slategrey": "#708090",
    "snow": "#FFFAFA",
    "springgreen": "#00FF7F",
    "steelblue": "#4682B4",
    "tan": "#D2B48C",
    "teal": "#008080",
    "thistle": "#D8BFD8",
    "tomato": "#FF6347",
    "transparent": "#000000",
    "turquoise": "#40E0D0",
    "violet": "#EE82EE",
    "wheat": "#F5DEB3",
    "white": "#FFFFFF",
    "whitesmoke": "#F5F5F5",
    "yellow": "#FFFF00",
    "yellowgreen": "#9ACD32",
}


# ── Hex validation helpers ──

_HEX6_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_HEX3_RE = re.compile(r"^#[0-9A-Fa-f]{3}$")
_RGBA_RE = re.compile(
    r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+))?\s*\)$",
    re.IGNORECASE,
)
_HSL_RE = re.compile(
    r"^hsla?\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*(?:,\s*([0-9.]+))?\s*\)$",
    re.IGNORECASE,
)

_VALID_WEIGHTS = {"100", "200", "300", "400", "500", "600", "700", "800", "900"}
_WEIGHT_KEYWORDS = {"normal": "400", "bold": "700"}


def _normalize_hex(value: str) -> str | None:
    """Try to normalize a color string to 6-digit uppercase hex. Return None if unparseable."""
    value = value.strip()

    # Already valid 6-digit hex
    if _HEX6_RE.match(value):
        return value.upper()

    # 3-digit shorthand -> expand
    if _HEX3_RE.match(value):
        r, g, b = value[1], value[2], value[3]
        return f"#{r}{r}{g}{g}{b}{b}".upper()

    # Named CSS color
    lower = value.lower()
    if lower in CSS_NAMED_COLORS:
        return CSS_NAMED_COLORS[lower]

    # rgba(r, g, b[, a]) -- ignore alpha, convert RGB channels
    m = _RGBA_RE.match(value)
    if m:
        r_i = min(255, max(0, int(m.group(1))))
        g_i = min(255, max(0, int(m.group(2))))
        b_i = min(255, max(0, int(m.group(3))))
        return f"#{r_i:02X}{g_i:02X}{b_i:02X}"

    # hsl(h, s%, l%) -> convert to RGB -> hex
    m = _HSL_RE.match(value)
    if m:
        return _hsl_to_hex(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    return None


def _hsl_to_hex(h: int, s: int, lightness: int) -> str:
    """Convert HSL to 6-digit hex. h=0-360, s/lightness=0-100."""
    s_f = s / 100.0
    l_f = lightness / 100.0
    c = (1 - abs(2 * l_f - 1)) * s_f
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l_f - c / 2
    if h < 60:
        r_f, g_f, b_f = c, x, 0.0
    elif h < 120:
        r_f, g_f, b_f = x, c, 0.0
    elif h < 180:
        r_f, g_f, b_f = 0.0, c, x
    elif h < 240:
        r_f, g_f, b_f = 0.0, x, c
    elif h < 300:
        r_f, g_f, b_f = x, 0.0, c
    else:
        r_f, g_f, b_f = c, 0.0, x
    r_i = round((r_f + m) * 255)
    g_i = round((g_f + m) * 255)
    b_i = round((b_f + m) * 255)
    return f"#{r_i:02X}{g_i:02X}{b_i:02X}"


# ── Per-type validation ──


def _validate_color(color: ExtractedColor, warnings: list[TokenWarning]) -> ExtractedColor:
    """Validate and normalize a single ExtractedColor."""
    hex_val = color.hex
    opacity = color.opacity

    # Normalize hex
    normalized = _normalize_hex(hex_val)
    if normalized is None:
        warnings.append(
            TokenWarning(
                level="error",
                field=f"colors[{color.name}].hex",
                message=f"Unparseable color value: {hex_val}",
                original_value=hex_val,
            )
        )
        normalized = hex_val  # keep original unchanged
    elif normalized != hex_val.upper():
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"colors[{color.name}].hex",
                message=f"Color normalized from '{hex_val}' to '{normalized}'",
                original_value=hex_val,
                fixed_value=normalized,
            )
        )

    # Check for "transparent" named color
    if hex_val.strip().lower() == "transparent":
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"colors[{color.name}].hex",
                message="Fully transparent color mapped to #000000",
                original_value=hex_val,
                fixed_value=normalized,
            )
        )

    # Clamp opacity
    clamped_opacity = max(0.0, min(1.0, opacity))
    if clamped_opacity != opacity:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"colors[{color.name}].opacity",
                message=f"Opacity clamped from {opacity} to {clamped_opacity}",
                original_value=str(opacity),
                fixed_value=str(clamped_opacity),
            )
        )

    # Warn on fully transparent
    if clamped_opacity < 0.01:
        warnings.append(
            TokenWarning(
                level="info",
                field=f"colors[{color.name}].opacity",
                message="Fully transparent color (opacity < 0.01)",
            )
        )

    return replace(color, hex=normalized, opacity=clamped_opacity)


def _validate_typography(
    typo: ExtractedTypography, warnings: list[TokenWarning]
) -> ExtractedTypography:
    """Validate and normalize a single ExtractedTypography."""
    family = typo.family
    size = typo.size
    weight = typo.weight
    line_height = typo.line_height

    # Empty family
    if not family or not family.strip():
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].family",
                message="Empty font family, defaulting to Arial",
                original_value=family,
                fixed_value="Arial",
            )
        )
        family = "Arial"

    # Size validation
    if size <= 0:
        warnings.append(
            TokenWarning(
                level="error",
                field=f"typography[{typo.name}].size",
                message=f"Invalid font size: {size}",
                original_value=str(size),
            )
        )
    elif size > 200:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].size",
                message=f"Unusually large font size: {size}px",
                original_value=str(size),
            )
        )

    # Weight validation
    weight_lower = weight.strip().lower()
    if weight_lower in _WEIGHT_KEYWORDS:
        weight = _WEIGHT_KEYWORDS[weight_lower]
    elif weight.strip() in _VALID_WEIGHTS:
        weight = weight.strip()
    else:
        # Try to parse as numeric and snap to nearest valid weight
        try:
            numeric = int(weight.strip())
            valid_ints = sorted(int(w) for w in _VALID_WEIGHTS)
            nearest = min(valid_ints, key=lambda v: abs(v - numeric))
            warnings.append(
                TokenWarning(
                    level="warning",
                    field=f"typography[{typo.name}].weight",
                    message=f"Weight '{weight}' mapped to nearest valid: {nearest}",
                    original_value=weight,
                    fixed_value=str(nearest),
                )
            )
            weight = str(nearest)
        except ValueError:
            warnings.append(
                TokenWarning(
                    level="warning",
                    field=f"typography[{typo.name}].weight",
                    message=f"Invalid weight '{weight}', defaulting to 400",
                    original_value=weight,
                    fixed_value="400",
                )
            )
            weight = "400"

    # Line height validation
    if line_height <= 0:
        default_lh = size * 1.5
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].line_height",
                message=f"Invalid line-height {line_height}, defaulting to {default_lh}",
                original_value=str(line_height),
                fixed_value=str(default_lh),
            )
        )
        line_height = default_lh
    elif line_height < 5.0 and line_height < size:
        # Unitless ratio — multiply by font size
        converted = line_height * size
        warnings.append(
            TokenWarning(
                level="info",
                field=f"typography[{typo.name}].line_height",
                message=f"Unitless line-height ratio {line_height} converted to {converted}px",
                original_value=str(line_height),
                fixed_value=str(converted),
            )
        )
        line_height = converted

    # Letter spacing validation
    letter_spacing = typo.letter_spacing
    if letter_spacing is not None and abs(letter_spacing) > 50:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].letter_spacing",
                message=f"Letter spacing {letter_spacing}px seems extreme",
                original_value=str(letter_spacing),
                fixed_value=str(max(-50.0, min(50.0, letter_spacing))),
            )
        )
        letter_spacing = max(-50.0, min(50.0, letter_spacing))

    # Text transform validation
    text_transform = typo.text_transform
    _VALID_TRANSFORMS = {"uppercase", "lowercase", "capitalize"}
    if text_transform is not None and text_transform not in _VALID_TRANSFORMS:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].text_transform",
                message=f"Unknown text-transform '{text_transform}', dropping",
                original_value=text_transform,
                fixed_value="None",
            )
        )
        text_transform = None

    # Text decoration validation
    text_decoration = typo.text_decoration
    _VALID_DECORATIONS = {"underline", "line-through"}
    if text_decoration is not None and text_decoration not in _VALID_DECORATIONS:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"typography[{typo.name}].text_decoration",
                message=f"Unknown text-decoration '{text_decoration}', dropping",
                original_value=text_decoration,
                fixed_value="None",
            )
        )
        text_decoration = None

    return replace(
        typo,
        family=family,
        weight=weight,
        line_height=line_height,
        letter_spacing=letter_spacing,
        text_transform=text_transform,
        text_decoration=text_decoration,
    )


def _validate_spacing(spacing: ExtractedSpacing, warnings: list[TokenWarning]) -> ExtractedSpacing:
    """Validate a single ExtractedSpacing."""
    value = spacing.value

    if value < 0:
        warnings.append(
            TokenWarning(
                level="error",
                field=f"spacing[{spacing.name}].value",
                message=f"Negative spacing: {value}",
                original_value=str(value),
                fixed_value="0",
            )
        )
        value = 0
    elif value > 500:
        warnings.append(
            TokenWarning(
                level="warning",
                field=f"spacing[{spacing.name}].value",
                message=f"Unusually large spacing: {value}px",
                original_value=str(value),
            )
        )

    return replace(spacing, value=value)


# ── Gradient & dark mode validation ──


_MAGIC_COLOR_MAP: dict[str, str] = {
    "#000000": "#010101",  # Prevent Outlook auto-inversion of pure black
    "#FFFFFF": "#FEFEFE",  # Prevent Outlook auto-inversion of pure white
}


def _apply_magic_colors(color: ExtractedColor) -> ExtractedColor:
    """Replace pure black/white with magic values for Outlook dark mode safety."""
    replacement = _MAGIC_COLOR_MAP.get(color.hex.upper())
    if replacement:
        return replace(color, hex=replacement)
    return color


def _validate_gradient(
    gradient: ExtractedGradient, warnings: list[TokenWarning]
) -> ExtractedGradient:
    """Validate gradient: clamp angle 0-360, validate stop hex values."""
    angle = gradient.angle % 360
    if angle != gradient.angle:
        warnings.append(
            TokenWarning(
                level="info",
                field=f"gradients[{gradient.name}].angle",
                message=f"Angle clamped from {gradient.angle} to {angle}",
            )
        )
    validated_stops: list[tuple[str, float]] = []
    for hex_val, pos in gradient.stops:
        norm = _normalize_hex(hex_val)
        if norm is None:
            warnings.append(
                TokenWarning(
                    level="error",
                    field=f"gradients[{gradient.name}].stops",
                    message=f"Unparseable gradient stop color: {hex_val}",
                    original_value=hex_val,
                )
            )
        validated_stops.append((norm or hex_val, max(0.0, min(1.0, pos))))
    norm_fallback = _normalize_hex(gradient.fallback_hex)
    return replace(
        gradient,
        angle=angle,
        stops=tuple(validated_stops),
        fallback_hex=norm_fallback or gradient.fallback_hex,
    )


def _validate_dark_mode_contrast(
    dark_colors: list[ExtractedColor],
    warnings: list[TokenWarning],
) -> None:
    """Warn if dark mode text/background pairs fail WCAG AA (4.5:1)."""
    dark_by_name = {c.name.lower(): c for c in dark_colors}
    dark_bg = (
        dark_by_name.get("background") or dark_by_name.get("bg") or dark_by_name.get("surface")
    )
    dark_text = (
        dark_by_name.get("text") or dark_by_name.get("body") or dark_by_name.get("foreground")
    )
    if dark_bg and dark_text:
        from app.shared.color import contrast_ratio, relative_luminance

        bg_lum = relative_luminance(dark_bg.hex)
        text_lum = relative_luminance(dark_text.hex)
        ratio = contrast_ratio(bg_lum, text_lum)
        if ratio < 4.5:
            warnings.append(
                TokenWarning(
                    level="warning",
                    field="dark_colors",
                    message=f"Dark mode text/bg contrast ratio {ratio:.1f}:1 < 4.5:1 WCAG AA",
                )
            )


# ── Deduplication ──


def _dedup_colors(
    colors: list[ExtractedColor], warnings: list[TokenWarning]
) -> list[ExtractedColor]:
    """Remove duplicate colors (same name + hex)."""
    seen: set[tuple[str, str]] = set()
    result: list[ExtractedColor] = []
    for c in colors:
        key = (c.name, c.hex)
        if key in seen:
            warnings.append(
                TokenWarning(
                    level="info",
                    field="colors",
                    message=f"Duplicate color removed: {c.name} ({c.hex})",
                )
            )
            continue
        seen.add(key)
        result.append(c)
    return result


def _dedup_typography(
    typography: list[ExtractedTypography], warnings: list[TokenWarning]
) -> list[ExtractedTypography]:
    """Remove duplicate typography (same name + family + size)."""
    seen: set[tuple[str, str, float]] = set()
    result: list[ExtractedTypography] = []
    for t in typography:
        key = (t.name, t.family, t.size)
        if key in seen:
            warnings.append(
                TokenWarning(
                    level="info",
                    field="typography",
                    message=f"Duplicate typography removed: {t.name} ({t.family} {t.size})",
                )
            )
            continue
        seen.add(key)
        result.append(t)
    return result


def _dedup_spacing(
    spacing: list[ExtractedSpacing], warnings: list[TokenWarning]
) -> list[ExtractedSpacing]:
    """Remove duplicate spacing (same name + value)."""
    seen: set[tuple[str, float]] = set()
    result: list[ExtractedSpacing] = []
    for s in spacing:
        key = (s.name, s.value)
        if key in seen:
            warnings.append(
                TokenWarning(
                    level="info",
                    field="spacing",
                    message=f"Duplicate spacing removed: {s.name} ({s.value})",
                )
            )
            continue
        seen.add(key)
        result.append(s)
    return result


# ── Main entry point ──


_SYSTEM_FONTS: set[str] = {
    "arial",
    "helvetica",
    "times new roman",
    "times",
    "georgia",
    "verdana",
    "tahoma",
    "trebuchet ms",
    "courier new",
    "courier",
    "impact",
    "comic sans ms",
    "lucida console",
    "lucida sans unicode",
    "palatino linotype",
    "book antiqua",
    "palatino",
}


def _is_system_font(family: str) -> bool:
    """Check if font is a widely-available system font."""
    primary = family.split(",")[0].strip().strip("'\"").lower()
    return primary in _SYSTEM_FONTS


def validate_and_transform(
    tokens: ExtractedTokens,
    *,
    target_clients: list[str] | None = None,
    caniemail_data: CanieMailData | None = None,
) -> tuple[ExtractedTokens, list[TokenWarning]]:
    """Validate and transform extracted tokens to email-safe values.

    Returns a new ExtractedTokens with fixes applied, plus a list of warnings.
    """
    warnings: list[TokenWarning] = []

    # Per-token validation
    colors = [_validate_color(c, warnings) for c in tokens.colors]
    typography = [_validate_typography(t, warnings) for t in tokens.typography]
    spacing = [_validate_spacing(s, warnings) for s in tokens.spacing]

    # Deduplicate
    colors = _dedup_colors(colors, warnings)
    typography = _dedup_typography(typography, warnings)
    spacing = _dedup_spacing(spacing, warnings)

    # Client-aware compatibility checks
    compat = None
    if target_clients:
        from app.design_sync.compatibility import ConverterCompatibility
        from app.knowledge.ontology import SupportLevel

        compat = ConverterCompatibility(
            target_clients=target_clients, caniemail_data=caniemail_data
        )

        # Client-aware color warnings
        for c in colors:
            if c.opacity < 1.0:
                level = compat.check_property("opacity")
                if level != SupportLevel.FULL:
                    unsupported = compat.unsupported_clients("opacity")
                    if unsupported:
                        warnings.append(
                            TokenWarning(
                                level="info",
                                field="color.opacity",
                                message=(
                                    f"Color '{c.name}' uses opacity ({c.opacity}) — "
                                    f"not supported in {', '.join(unsupported[:3])}"
                                ),
                                original_value=str(c.opacity),
                                fixed_value=str(c.opacity),
                            )
                        )

        # Client-aware typography warnings
        for t in typography:
            if t.family and not _is_system_font(t.family):
                unsupported = compat.unsupported_clients("@font-face")
                if unsupported:
                    warnings.append(
                        TokenWarning(
                            level="info",
                            field="typography.family",
                            message=(
                                f"Font '{t.family}' requires @font-face — "
                                f"fallback used in {', '.join(unsupported[:3])}"
                            ),
                            original_value=t.family,
                            fixed_value=t.family,
                        )
                    )

            if t.letter_spacing is not None and t.letter_spacing < 0:
                word_clients = [
                    cid for cid in target_clients if compat.client_engine(cid) == "word"
                ]
                if word_clients:
                    warnings.append(
                        TokenWarning(
                            level="info",
                            field="typography.letter_spacing",
                            message=(
                                f"Negative letter-spacing ({t.letter_spacing}px) "
                                f"ignored in {', '.join(word_clients[:2])} (Word engine)"
                            ),
                            original_value=str(t.letter_spacing),
                            fixed_value=str(t.letter_spacing),
                        )
                    )

    # Cross-token warnings
    if not colors:
        warnings.append(
            TokenWarning(level="warning", field="colors", message="No colors extracted")
        )
    if not typography:
        warnings.append(
            TokenWarning(
                level="warning", field="typography", message="No typography styles extracted"
            )
        )

    # Dark color validation: same as light colors + magic color replacement
    dark_colors = [_validate_color(c, warnings) for c in tokens.dark_colors]
    dark_colors = _dedup_colors(dark_colors, warnings)
    dark_colors = [_apply_magic_colors(c) for c in dark_colors]

    # Gradient validation
    gradients = [_validate_gradient(g, warnings) for g in tokens.gradients]

    # WCAG AA contrast check for dark color pairs
    _validate_dark_mode_contrast(dark_colors, warnings)

    # Also validate stroke_colors (same rules as colors)
    stroke_colors = [_validate_color(c, warnings) for c in tokens.stroke_colors]
    stroke_colors = _dedup_colors(stroke_colors, warnings)

    # Log summary
    error_count = sum(1 for w in warnings if w.level == "error")
    warn_count = sum(1 for w in warnings if w.level == "warning")
    if error_count or warn_count:
        logger.info(
            "design_sync.token_validation",
            errors=error_count,
            warnings=warn_count,
            total_issues=len(warnings),
        )

    validated = ExtractedTokens(
        colors=colors,
        typography=typography,
        spacing=spacing,
        variables_source=tokens.variables_source,
        modes=tokens.modes,
        stroke_colors=stroke_colors,
        variables=tokens.variables,
        dark_colors=dark_colors,
        gradients=gradients,
    )
    return validated, warnings


# ── Token → design-system mappers (moved from converter.py during 08c part 1) ──


def convert_colors_to_palette(colors: list[ExtractedColor]) -> BrandPalette:
    """Map extracted design colors to BrandPalette.

    Heuristic: match color names to palette roles (primary, secondary, accent,
    background, text, link). Falls back to positional assignment.
    Ensures adequate contrast between text and background.
    """
    role_map: dict[str, str] = {}
    name_hints: dict[str, list[str]] = {
        "primary": ["primary", "brand", "main"],
        "secondary": ["secondary", "accent-2"],
        "accent": ["accent", "highlight", "cta"],
        "background": ["background", "bg", "surface"],
        "text": ["text", "body", "foreground", "fg"],
        "link": ["link", "url", "anchor"],
    }

    for color in colors:
        lower_name = color.name.lower()
        for role, hints in name_hints.items():
            if role not in role_map and any(h in lower_name for h in hints):
                role_map[role] = color.hex
                break

    unmatched = [c for c in colors if c.hex not in role_map.values()]
    for role in ("primary", "secondary", "accent"):
        if role not in role_map and unmatched:
            role_map[role] = unmatched.pop(0).hex

    bg_hex = role_map.get("background", "#ffffff")
    text_hex = role_map.get("text", "#000000")
    bg_lum = relative_luminance(bg_hex)
    text_lum = relative_luminance(text_hex)
    if contrast_ratio(bg_lum, text_lum) < 3.0:
        role_map["text"] = "#ffffff" if bg_lum < 0.5 else "#000000"
        logger.info(
            "design_sync.contrast_fix",
            bg=bg_hex,
            original_text=text_hex,
            fixed_text=role_map["text"],
        )

    link_hex = role_map.get("link", "#0000ee")
    link_lum = relative_luminance(link_hex)
    if contrast_ratio(bg_lum, link_lum) < 3.0:
        role_map["link"] = "#99ccff" if bg_lum < 0.5 else "#0000ee"

    return BrandPalette(
        primary=role_map.get("primary", "#333333"),
        secondary=role_map.get("secondary", "#666666"),
        accent=role_map.get("accent", "#0066cc"),
        background=role_map.get("background", "#ffffff"),
        text=role_map.get("text", "#000000"),
        link=role_map.get("link", "#0000ee"),
    )


def convert_typography(styles: list[ExtractedTypography]) -> Typography:
    """Map extracted typography to Typography design system model.

    Heuristic: largest font_size → heading, most common family → body.
    """
    if not styles:
        return Typography()

    heading_style = None
    for s in styles:
        if any(kw in s.name.lower() for kw in ("heading", "title", "h1", "h2")):
            heading_style = s
            break
    if heading_style is None:
        heading_style = max(styles, key=lambda s: s.size)

    body_style = None
    for s in styles:
        if any(kw in s.name.lower() for kw in ("body", "paragraph", "text", "regular")):
            body_style = s
            break
    if body_style is None:
        body_style = min(styles, key=lambda s: s.size)

    def _px_or_none(val: float | None) -> str | None:
        if val is None:
            return None
        return f"{round(val)}px"

    def _spacing_px_or_none(val: float | None) -> str | None:
        if val is None or val == 0.0:
            return None
        return f"{round(val, 1)}px"

    return Typography(
        heading_font=_font_stack(heading_style.family),
        body_font=_font_stack(body_style.family),
        base_size=f"{int(body_style.size)}px",
        heading_line_height=_px_or_none(heading_style.line_height),
        body_line_height=_px_or_none(body_style.line_height),
        heading_letter_spacing=_spacing_px_or_none(heading_style.letter_spacing),
        body_letter_spacing=_spacing_px_or_none(body_style.letter_spacing),
        heading_text_transform=heading_style.text_transform,
    )


_SPACING_SCALE: dict[int, str] = {
    4: "2xs",
    8: "xs",
    12: "sm",
    16: "md",
    20: "md-lg",
    24: "lg",
    32: "xl",
    40: "xl-2",
    48: "2xl",
    64: "3xl",
}


def convert_spacing(spacing: list[ExtractedSpacing]) -> dict[str, float]:
    """Convert extracted spacing tokens to a named spacing scale.

    Maps numeric spacing values to semantic names. Values that align to
    the standard 4px/8px scale get standard names (xs, sm, md, lg, xl).
    Non-standard values keep their original name.

    Returns:
        Mapping of semantic name → pixel value.
    """
    result: dict[str, float] = {}
    for token in spacing:
        px = token.value
        int_px = int(px)
        if int_px in _SPACING_SCALE:
            name = _SPACING_SCALE[int_px]
        else:
            name = token.name.lower().removeprefix("spacing-").removeprefix("space-")
            if not name:
                name = f"{int_px}px"
        if name not in result:
            result[name] = px
    return result
