"""Detect physical-card-surface FRAMEs (Rule 9 identity exception, Phase 50.7).

A physical card is a FRAME that visually represents a real plastic card —
membership card, boarding pass, loyalty card, credit-card-style coupon. Rule 9
(Phase 52.7) flips dark-mode for nested coloured surfaces, but physical cards
must remain white because they depict a physical object.

Identified by ``>= _MIN_SIGNALS`` of 4 FRAME-tree signals:

1. Aspect ratio matches ID-1 (1.586:1), loyalty (2:1), or boarding-pass (4:3)
2. Contains a barcode strip (descendant image with width:height >= 4:1)
3. Contains a logo on a perfectly white field (parent FRAME #ffffff,
   image area <= 60% of parent)
4. Has its own ``cornerRadius >= 16`` distinct from sibling sections

Pure FRAME-tree read — no I/O, no PNG sampling.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.design_sync.protocol import DesignNode, DesignNodeType

# Aspect ratio targets (with +/- _RATIO_TOLERANCE)
_ID_1_RATIO = 1.586  # Credit card / driver's license (ISO/IEC 7810 ID-1)
_LOYALTY_RATIO = 2.0  # Many membership / loyalty cards
_BOARDING_PASS_RATIO = 4 / 3
_RATIO_TOLERANCE = 0.05  # +/- 5%

# Barcode strip aspect threshold
_BARCODE_MIN_RATIO = 4.0  # width / height >= 4:1

# Logo-on-white threshold
_LOGO_MAX_FILL_RATIO = 0.6  # image area <= 60% of white parent

# Distinct corner radius threshold
_CARD_MIN_RADIUS = 16.0

# White-field tolerance (case-insensitive hex match against #ffffff)
_WHITE_HEXES = frozenset({"#ffffff", "#fff"})

# Number of signals required to opt OUT of dark-mode flip
_MIN_SIGNALS = 2


@dataclass(frozen=True)
class PhysicalCardDetection:
    """Result of physical-card detection on a single section frame."""

    is_physical: bool
    signals: tuple[str, ...]


# Subtree-walk depth — bounded to keep traversal cheap on deep wrappers.
_SUBTREE_MAX_DEPTH = 4


def detect_physical_card_surface(
    card_frame: DesignNode,
    *,
    sibling_radii: list[float] | None = None,
    min_signals: int = _MIN_SIGNALS,
) -> PhysicalCardDetection:
    """Return whether ``card_frame`` represents a physical card surface.

    Args:
        card_frame: The FRAME being evaluated (typically the section's own node
            once 50.4 has detected an ``inner_bg``).
        sibling_radii: Corner radii of immediate sibling sections. When
            provided, signal 4 fires only if the card's radius is *not* in this
            set. When ``None``, signal 4 fires solely on ``radius >= 16``.
        min_signals: Number of signals required to flag as physical. Defaults
            to ``_MIN_SIGNALS`` (2). Plumbed through so the wiring layer can
            override from config.
    """
    signals: list[str] = []

    # Signal 1: aspect ratio matches a known physical card.
    aspect = _aspect_ratio_signal(card_frame)
    if aspect is not None:
        signals.append(aspect)

    # Signal 2: barcode descendant.
    if _has_barcode_child(card_frame):
        signals.append("barcode_child")

    # Signal 3: logo on a white field.
    if _has_logo_on_white_field(card_frame):
        signals.append("logo_on_white_field")

    # Signal 4: distinct corner radius.
    if _has_distinct_corner_radius(card_frame, sibling_radii):
        signals.append("distinct_corner_radius")

    return PhysicalCardDetection(
        is_physical=len(signals) >= min_signals,
        signals=tuple(signals),
    )


def find_physical_card_in_subtree(
    root: DesignNode,
    *,
    max_depth: int = _SUBTREE_MAX_DEPTH,
    min_signals: int = _MIN_SIGNALS,
) -> PhysicalCardDetection | None:
    """Search ``root``'s descendants for a physical-card surface.

    Used as a fallback when ``analyze_layout`` cannot detect an ``inner_bg``
    on the top-level section but the card lives nested inside a wrapper
    (e.g. LEGO's ``mj-wrapper`` → ``mj-section`` chain). Walks bounded by
    ``max_depth`` (root itself is depth 0, root's direct children depth 1)
    and returns the first descendant whose detection passes ``min_signals``.

    A nested candidate must additionally carry a corner radius ``>= 16`` —
    aspect_ratio + barcode_child can both fire coincidentally on plain hero
    sections (wide container + a banner strip image), so the visual hallmark
    of a card (rounded corners) is required when running the fallback.

    Sibling radii are computed per-candidate from the candidate's immediate
    parent so that ``distinct_corner_radius`` reflects local structure
    rather than the top-level section's siblings.
    """
    queue: list[tuple[DesignNode, DesignNode, int]] = [(root, child, 1) for child in root.children]
    while queue:
        parent, node, depth = queue.pop(0)
        radius = _resolve_corner_radius(node)
        if radius is not None and radius >= _CARD_MIN_RADIUS:
            sibling_radii = collect_sibling_radii(
                parent.children,
                exclude_node_id=node.id,
            )
            detection = detect_physical_card_surface(
                node,
                sibling_radii=sibling_radii,
                min_signals=min_signals,
            )
            if detection.is_physical:
                return detection
        if depth < max_depth:
            queue.extend((node, child, depth + 1) for child in node.children)
    return None


# ── Signal predicates ──────────────────────────────────────────────────────


def _aspect_ratio_signal(node: DesignNode) -> str | None:
    if node.width is None or node.height is None or node.height <= 0:
        return None
    ratio = node.width / node.height
    if _is_within(ratio, _ID_1_RATIO, _RATIO_TOLERANCE):
        return "aspect_ratio_id_1"
    if _is_within(ratio, _LOYALTY_RATIO, _RATIO_TOLERANCE):
        return "aspect_ratio_loyalty"
    if _is_within(ratio, _BOARDING_PASS_RATIO, _RATIO_TOLERANCE):
        return "aspect_ratio_boarding_pass"
    return None


def _has_barcode_child(card: DesignNode) -> bool:
    for child in _walk_image_descendants(card):
        if child.width is None or child.height is None or child.height <= 0:
            continue
        if (child.width / child.height) >= _BARCODE_MIN_RATIO:
            return True
    return False


def _has_logo_on_white_field(card: DesignNode) -> bool:
    """Detect an image inside a parent FRAME with #ffffff fill, image area <= 60%."""
    for child in card.children:
        if not _has_white_fill(child):
            continue
        parent_area = _area(child)
        if parent_area <= 0:
            continue
        # The image may be the white frame itself (single-image white card) or
        # nested one level deeper (image inside white wrapper).
        for candidate in _iter_self_and_children(child):
            if candidate is child:
                continue
            if not _is_image_node(candidate):
                continue
            child_area = _area(candidate)
            if 0 < child_area <= parent_area * _LOGO_MAX_FILL_RATIO:
                return True
    return False


def _has_distinct_corner_radius(
    card: DesignNode,
    sibling_radii: list[float] | None,
) -> bool:
    radius = _resolve_corner_radius(card)
    if radius is None or radius < _CARD_MIN_RADIUS:
        return False
    if sibling_radii is None:
        return True
    return not _is_in_sibling_set(radius, sibling_radii)


def _resolve_corner_radius(node: DesignNode) -> float | None:
    """Mirror ``layout_analyzer._resolve_corner_radius``: prefer per-corner max.

    Figma exports populate ``corner_radii`` (TL/TR/BR/BL) for any node with
    explicit per-corner radii, often leaving ``corner_radius`` as ``None``.
    """
    if node.corner_radii:
        return max(node.corner_radii)
    return node.corner_radius


# ── Helpers ────────────────────────────────────────────────────────────────


def _is_within(value: float, target: float, tolerance: float) -> bool:
    if target == 0:
        return value == 0
    return abs(value - target) / target <= tolerance


def _walk_image_descendants(node: DesignNode) -> list[DesignNode]:
    """Depth-first walk yielding every descendant that carries image content."""
    out: list[DesignNode] = []
    stack: list[DesignNode] = list(node.children)
    while stack:
        current = stack.pop()
        if _is_image_node(current):
            out.append(current)
        stack.extend(current.children)
    return out


def _iter_self_and_children(node: DesignNode) -> list[DesignNode]:
    return [node, *node.children]


def _is_image_node(node: DesignNode) -> bool:
    """True for IMAGE nodes and FRAME nodes carrying an image fill."""
    if node.type == DesignNodeType.IMAGE:
        return True
    return node.image_ref is not None


def _has_white_fill(node: DesignNode) -> bool:
    if node.fill_color is None:
        return False
    return node.fill_color.lower() in _WHITE_HEXES


def _area(node: DesignNode) -> float:
    if node.width is None or node.height is None:
        return 0.0
    return float(node.width) * float(node.height)


def _is_in_sibling_set(radius: float, sibling_radii: list[float]) -> bool:
    """A sibling radius matches when it differs by less than 1px (Figma rounding)."""
    return any(abs(radius - sib) < 1.0 for sib in sibling_radii)


def collect_sibling_radii(
    nodes: list[DesignNode],
    *,
    exclude_node_id: str,
) -> list[float]:
    """Collect ``corner_radius`` values from siblings, excluding ``exclude_node_id``.

    Used by the layout-analyzer wiring layer to feed sibling context into
    ``detect_physical_card_surface``.
    """
    return [
        n.corner_radius for n in nodes if n.id != exclude_node_id and n.corner_radius is not None
    ]
