"""Pure FRAME-tree rules — codified detection rules 8, 10, 11.

Codifies rules from docs/architecture/opus-figma-to-html-process.md §8.3.
Each rule is a pure function: takes Figma node data, returns a structured
result indicating whether the rule fires and what action to take. No I/O,
no PNG sampling — these rules read FRAME-tree fields directly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.design_sync.protocol import DesignNode, DesignNodeType


@dataclass(frozen=True)
class CornerRadiusSpec:
    """Output of Rule 8 / Rule 10."""

    scalar: float | None
    per_corner: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class CardWidthSpec:
    """Output of Rule 11."""

    fixed_width_px: int
    use_class: str = "wf"


def rule_8_corner_radius(node: DesignNode) -> CornerRadiusSpec:
    """Border-radius from cornerRadius / rectangleCornerRadii — never heuristic.

    Missing or zero → square corners. Don't apply 'looks like pill therefore
    round it'.
    """
    raw_per_corner = node.corner_radii
    if raw_per_corner and len(raw_per_corner) == 4 and any(c > 0 for c in raw_per_corner):
        tl, tr, br, bl = raw_per_corner
        return CornerRadiusSpec(scalar=None, per_corner=(tl, tr, br, bl))

    scalar = node.corner_radius
    if scalar is not None and scalar > 0:
        return CornerRadiusSpec(scalar=scalar, per_corner=None)

    return CornerRadiusSpec(scalar=None, per_corner=None)


def rule_10_image_corner_radii(image_frame: DesignNode) -> CornerRadiusSpec:
    """Image per-corner border-radius from rectangleCornerRadii.

    Same logic as ``rule_8_corner_radius``; the only difference is *who calls
    it* (image FRAME vs pill / tag).
    """
    return rule_8_corner_radius(image_frame)


def rule_11_card_width_from_dominant_image(
    card_frame: DesignNode,
) -> CardWidthSpec | None:
    """Inner card width must match its image children's max-width.

    Fires when 2+ direct image children share the same width (the dominant
    width pattern). Returns ``None`` for cards with 0-1 images or no
    dominant width.
    """
    image_widths: list[int] = []
    for child in card_frame.children:
        if not _is_image_frame(child) or child.width is None:
            continue
        image_widths.append(int(child.width))

    if len(image_widths) < 2:
        return None

    if len(set(image_widths)) == 1:
        return CardWidthSpec(fixed_width_px=image_widths[0])

    counts = Counter(image_widths)
    most_common, count = counts.most_common(1)[0]
    if count >= 2:
        return CardWidthSpec(fixed_width_px=int(most_common))

    return None


def _is_image_frame(node: DesignNode) -> bool:
    """A node that renders as an image: IMAGE type or FRAME with image fill."""
    if node.type == DesignNodeType.IMAGE:
        return True
    return node.type == DesignNodeType.FRAME and node.image_ref is not None
