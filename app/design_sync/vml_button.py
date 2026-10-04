"""VML rounded-button builder (CE-11).

Classic Outlook (Word engine) ignores ``border-radius``, so an HTML button
renders as a square box. :func:`render_vml_button` puts a ``<v:roundrect>``
inside ``<!--[if mso]>`` and hides the HTML twin from Outlook with
``<!--[if !mso]><!-->…<!--<![endif]-->``.

Markup follows ``email-templates/components/golden-references/
vml-rounded-button-variants.html`` and the jsx-email ``Button`` component
(``<w:anchorlock/>`` + ``<center>``; ``fill="f"`` / ``stroke="f"`` when absent).

The module does not depend on converter types, so the MJML path (CE-19) can
reuse it.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VmlButton:
    """Design values for one VML button. ``fill``/``stroke_color`` ``None`` = absent."""

    href: str
    label: str
    width_px: int
    height_px: int
    radius_px: float
    fill: str | None
    text_color: str
    stroke_color: str | None
    stroke_weight_px: int | None
    font_family: str
    font_size_px: int
    font_weight: str


def arcsize_pct(radius: float, width: int, height: int) -> int:
    """Corner radius as a VML ``arcsize`` percentage, clamped to 0-50.

    ``floor(radius / min(width, height) * 100)``, as in jsx-email. The MS VML
    reference defines arcsize as a fraction of half the shorter side, which
    would give twice this value. A classic-Outlook render measured in
    vivid-planet/dextinity PR #6296 matches this formula instead (536x268 at
    19% drew a 50 px corner), and so do the golden variants (10/50/8%).
    """
    short = min(width, height)
    if short <= 0 or radius <= 0:
        return 0
    return min(50, math.floor(radius / short * 100))


def _attr(value: str) -> str:
    return html.escape(value, quote=True)


def render_vml_button(spec: VmlButton, twin_html: str) -> str:
    """Return the Outlook VML button followed by ``twin_html`` hidden from Outlook."""
    if spec.stroke_color and spec.stroke_weight_px:
        stroke = (
            f'strokecolor="{_attr(spec.stroke_color)}" strokeweight="{spec.stroke_weight_px}px"'
        )
    else:
        stroke = 'stroke="f"'
    fill = f'fillcolor="{_attr(spec.fill)}"' if spec.fill else 'fill="f"'
    arcsize = arcsize_pct(spec.radius_px, spec.width_px, spec.height_px)
    roundrect = (
        '<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" '
        f'href="{_attr(spec.href)}" '
        f'style="height:{spec.height_px}px;v-text-anchor:middle;width:{spec.width_px}px;" '
        f'arcsize="{arcsize}%" {stroke} {fill}>'
        "<w:anchorlock/>"
        f'<center style="color:{_attr(spec.text_color)};font-family:{_attr(spec.font_family)};'
        f'font-size:{spec.font_size_px}px;font-weight:{_attr(spec.font_weight)};">'
        f"{html.escape(spec.label, quote=False)}</center>"
        "</v:roundrect>"
    )
    return f"<!--[if mso]>{roundrect}<![endif]--><!--[if !mso]><!-->{twin_html}<!--<![endif]-->"
