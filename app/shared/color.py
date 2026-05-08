"""WCAG colour math — relative luminance and contrast ratio.

Lives outside ``app.design_sync`` because it has no design-system dependencies
and is reused by the scaffolder agent and other consumers that should not
import from ``design_sync``.
"""

from __future__ import annotations


def relative_luminance(hex_color: str) -> float:
    """Calculate WCAG relative luminance of a hex colour (0=black, 1=white)."""
    hex_clean = hex_color.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) != 6:
        return 0.0
    try:
        r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
    except ValueError:
        return 0.0

    def _linearize(val: int) -> float:
        srgb = val / 255.0
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(lum1: float, lum2: float) -> float:
    """WCAG contrast ratio between two luminances."""
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)
