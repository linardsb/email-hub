"""Gradient → CSS conversion for dark-mode token output.

Extracted from `app/design_sync/converter.py` during 08c part 4.
"""

from __future__ import annotations

from app.design_sync.protocol import ExtractedGradient
from app.design_sync.sanitizers import _sanitize_css_value


def gradient_to_css(gradient: ExtractedGradient) -> str:
    """Convert ExtractedGradient to a CSS ``linear-gradient()`` value."""
    stops_css = ", ".join(
        f"{_sanitize_css_value(hex_val)} {round(pos * 100, 1)}%" for hex_val, pos in gradient.stops
    )
    return f"linear-gradient({gradient.angle}deg, {stops_css})"


# Legacy alias kept for the dark-mode token tests (which still import from
# the old name). Drop in a follow-up if those tests are updated.
_gradient_to_css = gradient_to_css
