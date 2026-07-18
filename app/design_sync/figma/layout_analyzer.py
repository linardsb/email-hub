"""Layout analysis for design file structures — pure computation, no I/O."""

from __future__ import annotations

import dataclasses
import re
import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.figma.physical_card_detector import (
    collect_sibling_radii,
    detect_physical_card_surface,
    find_physical_card_in_subtree,
)
from app.design_sync.frame_rules import (
    CornerRadiusSpec,
    rule_8_corner_radius,
    rule_10_image_corner_radii,
    rule_11_card_width_from_dominant_image,
)
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType, StyleRun
from app.design_sync.tuning import (
    NESTED_CARD_PERCEPTUAL_THRESHOLD,
    PHYSICAL_CARD_MIN_SIGNALS,
    VLM_CLASSIFICATION_CONFIDENCE_THRESHOLD,
)

if TYPE_CHECKING:
    from app.design_sync.vlm_classifier import VLMSectionClassification

logger = get_logger(__name__)


class EmailSectionType(StrEnum):
    """Recognised email section types."""

    HEADER = "header"
    PREHEADER = "preheader"
    HERO = "hero"
    CONTENT = "content"
    CTA = "cta"
    FOOTER = "footer"
    SOCIAL = "social"
    DIVIDER = "divider"
    SPACER = "spacer"
    NAV = "nav"
    UNKNOWN = "unknown"


class ColumnLayout(StrEnum):
    """Column layout detected in a section."""

    SINGLE = "single"
    TWO_COLUMN = "two-column"
    THREE_COLUMN = "three-column"
    MULTI_COLUMN = "multi-column"


class NamingConvention(StrEnum):
    """Detected naming convention used in the design file."""

    MJML = "mjml"
    DESCRIPTIVE = "descriptive"
    GENERIC = "generic"
    CUSTOM = "custom"


@dataclass(frozen=True)
class TextBlock:
    """A text element extracted from the design."""

    node_id: str
    content: str
    font_size: float | None = None
    is_heading: bool = False
    font_family: str | None = None
    font_weight: int | None = None
    line_height: float | None = None
    letter_spacing: float | None = None
    text_color: str | None = None
    text_align: str | None = None  # left|center|right|justify
    hyperlink: str | None = None
    style_runs: tuple[StyleRun, ...] = ()
    text_transform: str | None = None  # uppercase|lowercase|capitalize
    text_decoration: str | None = None  # underline|line-through
    source_frame_id: str | None = None  # Parent frame that contains this text
    role_hint: str | None = None  # "heading" | "body" | "label" | "cta"
    # Rule 7 (Phase 50.5) — alignment derived from x-offset against parent column.
    # Populated only when the text was identified as a tag/pill candidate.
    layout_align: str | None = None  # "left" | "center" | "right" | None


@dataclass(frozen=True)
class ImagePlaceholder:
    """An image placeholder detected in the design."""

    node_id: str
    node_name: str
    width: float | None = None
    height: float | None = None
    is_background: bool = False
    export_node_id: str | None = None  # Frame node to export (includes bg fills)
    # Rule 10 (Phase 50.5) — per-corner radii from rectangleCornerRadii.
    corner_radius_spec: CornerRadiusSpec | None = None
    # Non-button border (52.5) — captured losslessly; rendering lands in 53.3.
    stroke_color: str | None = None
    stroke_weight: float | None = None


@dataclass(frozen=True)
class ButtonElement:
    """A CTA button detected in the design."""

    node_id: str
    text: str
    width: float | None = None
    height: float | None = None
    fill_color: str | None = None
    url: str | None = None
    border_radius: float | None = None
    text_color: str | None = None
    stroke_color: str | None = None
    stroke_weight: float | None = None
    icon_node_id: str | None = None
    # Label typography from the button's text child (Phase 52.4b) — lets the
    # column/text CTA render the designed font instead of a hardcoded 14px/bold.
    font_size: float | None = None
    font_weight: int | None = None
    font_family: str | None = None
    # Rule 8 (Phase 50.5) — per-corner radii on tag/pill non-CTA frames.
    corner_radius_spec: CornerRadiusSpec | None = None
    # Auto-layout padding (Track G · G3) — the button frame's designed box
    # geometry, captured so the renderer emits it instead of a hardcode.
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None


@dataclass(frozen=True)
class ColumnGroup:
    """Content grouped by column, preserving design structure."""

    column_idx: int
    node_id: str
    node_name: str
    texts: list[TextBlock] = field(default_factory=list[TextBlock])
    images: list[ImagePlaceholder] = field(default_factory=list[ImagePlaceholder])
    buttons: list[ButtonElement] = field(default_factory=list[ButtonElement])
    width: float | None = None
    # F10 — node ids of the extracted content in design tree (pre-order) order.
    # The three category lists above lose the interleave; this restores it at
    # render time. Empty on groups built before the field existed (older
    # persisted documents) → callers fall back to category order.
    content_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentGroup:
    """A visually distinct content block within a section.

    Preserves the parent-child grouping of text, images, and buttons
    that belong together (e.g., one "reason" block with icon + heading + body).
    """

    frame_node_id: str
    frame_name: str
    texts: list[TextBlock] = field(default_factory=list[TextBlock])
    images: list[ImagePlaceholder] = field(default_factory=list[ImagePlaceholder])
    buttons: list[ButtonElement] = field(default_factory=list[ButtonElement])


@dataclass(frozen=True)
class EmailSection:
    """A detected email section with its content."""

    section_type: EmailSectionType
    node_id: str
    node_name: str
    y_position: float | None = None
    # D3 follow-up — design-space x of the source frame. Needed to order
    # peeled same-row siblings left-to-right (their y values can differ by a
    # few px, so the global y-sort alone may flip them).
    x_position: float | None = None
    width: float | None = None
    height: float | None = None
    column_layout: ColumnLayout = ColumnLayout.SINGLE
    column_count: int = 1
    texts: list[TextBlock] = field(default_factory=list[TextBlock])
    images: list[ImagePlaceholder] = field(default_factory=list[ImagePlaceholder])
    buttons: list[ButtonElement] = field(default_factory=list[ButtonElement])
    spacing_after: float | None = None
    bg_color: str | None = None
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None
    item_spacing: float | None = None
    element_gaps: tuple[float, ...] = ()
    column_groups: list[ColumnGroup] = field(default_factory=list[ColumnGroup])
    # A8 (Phase 53 D2) — normalized per-column width fractions measured from
    # the design's column frames; ``()`` when any column width is missing.
    # The renderer redistributes the column seed's per-<td>/div widths by
    # these so asymmetric splits aren't forced to equal-width columns.
    column_width_fractions: tuple[float, ...] = ()
    classification_confidence: float | None = None
    vlm_classification: str | None = None
    vlm_confidence: float | None = None
    content_roles: tuple[str, ...] = ()
    child_content_groups: list[ContentGroup] = field(default_factory=list[ContentGroup])
    # Section-boundary classification (Phase 50.2) — populated by
    # ``classify_section_boundaries`` when a global design PNG is available.
    boundary_above: str | None = None
    boundary_below: str | None = None
    sampled_top_color: str | None = None
    sampled_bottom_color: str | None = None
    # Wrapper unwrap pre-pass (Phase 50.3, Gap 1) — populated when a coloured
    # ``mj-wrapper`` is expanded into its child sections; ``container_bg`` is
    # the wrapper's own fill propagated to each child, and ``parent_wrapper_id``
    # records the source wrapper node id for downstream Rule 1 logic.
    container_bg: str | None = None
    parent_wrapper_id: str | None = None
    # Nested-card background (Phase 50.4, Gap 10) — when the section sits on a
    # coloured wrapper but has its own card surface (e.g. white card on lime
    # wrapper), ``inner_bg`` carries the card's own fill and ``inner_radius``
    # carries its border radius. Renderer emits these on a ``_inner`` table.
    inner_bg: str | None = None
    inner_radius: float | None = None
    # Rule 11 (Phase 50.5) — when all direct image children share the same
    # max-width, the inner card pins its width to that dominant image width.
    inner_card_fixed_width: int | None = None
    # Physical-card identity exception (Phase 50.7, Rule 9 prep) — when the
    # nested card visually depicts a real plastic card (membership card,
    # boarding pass, loyalty card), Rule 9's dark-mode flip must skip it.
    # ``physical_card_signals`` records which heuristics fired (telemetry).
    is_physical_card_surface: bool = False
    physical_card_signals: tuple[str, ...] = ()
    # Non-button border (52.5) — captured losslessly; rendering lands in 53.3.
    stroke_color: str | None = None
    stroke_weight: float | None = None
    # D3 follow-up — peeled same-row siblings share a row id so the renderer
    # composes them side-by-side (the design lays them out horizontally) while
    # each still COUNTS as its own section for the A2 target gate.
    peel_row_id: str | None = None
    # 53.3b — source node id of a gradient fill captured at 52.5. The matcher
    # resolves it against ``tokens.gradients[*].node_id`` to emit the
    # background-image override; ``None`` when the section carries no gradient.
    gradient_ref: str | None = None
    # 53.3a — dropped visual effects on this section's subtree, as
    # ``"<count>:<TYPE,...>"`` (e.g. ``"2:DROP_SHADOW,LAYER_BLUR"``). Shadows/
    # blurs/blends are not reproducible in email HTML (ceiling doc §2); this
    # carries the loss into conversion warnings instead of silence.
    effects_summary: str | None = None


@dataclass(frozen=True)
class DesignLayoutDescription:
    """Complete layout analysis result."""

    file_name: str
    overall_width: float | None = None
    sections: list[EmailSection] = field(default_factory=list[EmailSection])
    total_text_blocks: int = 0
    total_images: int = 0
    spacing_map: dict[str, dict[str, float]] = field(default_factory=dict[str, dict[str, float]])


# ── Name-based section detection ──

_SECTION_PATTERNS: dict[EmailSectionType, list[str]] = {
    EmailSectionType.PREHEADER: ["preheader", "pre-header", "preview"],
    EmailSectionType.HEADER: ["header", "top-bar", "topbar", "logo-bar", "logo-header"],
    EmailSectionType.HERO: ["hero", "banner", "masthead", "feature", "mj-hero"],
    EmailSectionType.CONTENT: ["content", "body", "main", "article", "text", "product"],
    EmailSectionType.CTA: ["cta", "call-to-action", "button", "action"],
    EmailSectionType.FOOTER: ["footer", "bottom", "legal", "unsubscribe"],
    EmailSectionType.SOCIAL: ["social", "follow", "connect", "mj-social"],
    EmailSectionType.DIVIDER: ["divider", "separator", "hr", "line", "mj-divider"],
    EmailSectionType.SPACER: ["spacer", "gap", "padding", "mj-spacer"],
    EmailSectionType.NAV: ["nav", "navigation", "menu", "links", "mj-navbar"],
}

# MJML → EmailSectionType mapping
_MJ_SECTION_MAP: dict[str, EmailSectionType] = {
    "mj-section": EmailSectionType.CONTENT,
    "mj-wrapper": EmailSectionType.CONTENT,
    "mj-hero": EmailSectionType.HERO,
    "mj-navbar": EmailSectionType.NAV,
}

# MJML → content role mapping
_MJ_CONTENT_ROLES: dict[str, str] = {
    "mj-image": "image",
    "mj-text": "text",
    "mj-button": "button",
    "mj-column": "column",
    "mj-section": "section",
    "mj-wrapper": "wrapper",
    "mj-divider": "divider",
    "mj-spacer": "spacer",
    "mj-social": "social",
    "mj-navbar": "nav",
}

_FRAME_TYPES = frozenset({DesignNodeType.FRAME, DesignNodeType.GROUP, DesignNodeType.COMPONENT})

_GENERIC_NAME_RE = re.compile(r"(?i)^(frame|group|rectangle|ellipse|vector|text|instance)\s*\d*$")

_Y_TOLERANCE = 10.0  # pixels tolerance for column detection


def analyze_layout(
    structure: DesignFileStructure,
    *,
    naming_convention: str = "auto",
    section_name_map: dict[str, str] | None = None,
    button_name_hints: list[str] | None = None,
    vlm_classifications: dict[str, VLMSectionClassification] | None = None,
    global_design_image: bytes | None = None,
    gradient_node_ids: frozenset[str] | None = None,
) -> DesignLayoutDescription:
    """Analyze a design file structure and detect email sections.

    Algorithm:
    1. Find the primary page (first page, or page named "email"/"design")
    2. Get top-level frames as section candidates
    3. Auto-detect or use provided naming convention
    4. Classify each frame by convention-specific strategy
    5. Detect column layouts (structure-first, position-fallback)
    6. Extract text, images, buttons from each section
    7. Calculate spacing between sections
    8. Sort sections by y-position (top to bottom)
    """
    if not structure.pages:
        return DesignLayoutDescription(file_name=structure.file_name)

    page = _find_primary_page(structure.pages)
    raw_candidates = _get_section_candidates(page)

    if not raw_candidates:
        return DesignLayoutDescription(file_name=structure.file_name)

    # Detect naming convention from raw frames so the wrapper-unwrap pre-pass
    # can gate on it. Naming detection is keyword-pattern-based and unaffected
    # by whether wrappers have been expanded.
    if naming_convention == "auto":
        convention = _detect_naming_convention(raw_candidates)
    elif naming_convention == "custom" and section_name_map:
        convention = NamingConvention.CUSTOM
    else:
        try:
            convention = NamingConvention(naming_convention)
        except ValueError:
            convention = _detect_naming_convention(raw_candidates)

    # Wrapper unwrap pre-pass (Phase 50.3) — expand coloured ``mj-wrapper``s
    # with ≥2 section children into per-child sections, propagating the
    # wrapper fill. Gated to MJML naming + ``wrapper_unwrap_enabled`` flag.
    candidates = _expand_container_wrappers(raw_candidates, convention)
    # Band wrapper frame extents (Track G G1, M1) — the wrapper's own
    # coloured padding lives INSIDE the band, so inter-band spacing measures
    # to the frame edge, not the first/last child bbox.
    wrapper_bounds = _wrapper_frame_bounds(raw_candidates, convention)

    # Determine overall width from the widest top-level frame
    overall_width = max(
        (node.width for node, _, _, _ in candidates if node.width is not None),
        default=None,
    )

    # Build sections
    sections: list[EmailSection] = []
    total = len(candidates)
    vlm_threshold = VLM_CLASSIFICATION_CONFIDENCE_THRESHOLD if vlm_classifications else 0.0
    frame_export_fallback = get_settings().design_sync.frame_export_fallback_enabled
    for idx, (node, container_bg, parent_wrapper_id, peel_row_id) in enumerate(candidates):
        section_type, classification_confidence = _classify_section(
            node,
            convention,
            idx,
            total,
            section_name_map=section_name_map,
        )

        # VLM hybrid merge (Phase 41.7)
        vlm_type_str: str | None = None
        vlm_conf: float | None = None
        if vlm_classifications and node.id in vlm_classifications:
            rule_type_before = section_type.value
            vlm = vlm_classifications[node.id]
            vlm_type_str = vlm.section_type
            vlm_conf = vlm.confidence
            threshold = vlm_threshold

            if classification_confidence > 0.9:
                pass  # High-confidence rule result — keep it
            elif section_type == EmailSectionType.UNKNOWN and vlm_conf >= threshold:
                try:
                    section_type = EmailSectionType(vlm_type_str)
                    classification_confidence = vlm_conf
                except ValueError:
                    pass  # Invalid VLM type — keep rule result
            elif vlm_conf >= threshold and vlm_conf > classification_confidence:
                try:
                    section_type = EmailSectionType(vlm_type_str)
                    classification_confidence = vlm_conf
                except ValueError:
                    pass

            if vlm_type_str == section_type.value and vlm_type_str != rule_type_before:
                logger.debug(
                    "design_sync.vlm_merge.override",
                    node_id=node.id,
                    original_type=rule_type_before,
                    vlm_type=vlm_type_str,
                    vlm_confidence=vlm_conf,
                    rule_confidence=classification_confidence,
                )

        # 53.3d — a subtree the fixed-seed renderer cannot reproduce (rotation,
        # overlapping siblings) renders as ONE exported image of the whole
        # section frame instead of mis-extracted content. Flag-gated, default
        # off; the fork-(c) escape hatch seam.
        if frame_export_fallback:
            raster_reason = _unreproducible_reason(node)
            if raster_reason is not None:
                logger.info(
                    "design_sync.frame_export_fallback",
                    node_id=node.id,
                    reason=raster_reason,
                )
                sections.append(
                    EmailSection(
                        section_type=section_type,
                        node_id=node.id,
                        node_name=node.name,
                        y_position=node.y,
                        x_position=node.x,
                        width=node.width,
                        height=node.height,
                        images=[
                            ImagePlaceholder(
                                node_id=node.id,
                                node_name=node.name,
                                width=node.width,
                                height=node.height,
                                export_node_id=node.id,
                            )
                        ],
                        bg_color=node.fill_color,
                        classification_confidence=classification_confidence,
                        vlm_classification=vlm_type_str,
                        vlm_confidence=vlm_conf,
                        content_roles=("image",),
                        container_bg=container_bg,
                        parent_wrapper_id=parent_wrapper_id,
                        peel_row_id=peel_row_id,
                        effects_summary=_collect_effects_summary(node),
                    )
                )
                continue

        col_layout, col_count, col_groups = _detect_column_layout_with_groups(node, convention)
        buttons = _extract_buttons(node, extra_hints=button_name_hints)
        button_node_ids = _collect_button_node_ids(buttons)
        texts = _detect_content_hierarchy(_extract_texts(node, exclude_node_ids=button_node_ids))
        images = _extract_images(node)
        roles = _compute_content_roles(texts, images, buttons)

        # Extract child content groups (preserves parent-child structure)
        child_groups = _extract_content_groups(node, button_name_hints=button_name_hints)

        # Nested-card surface detection (Phase 50.4, Gap 10)
        inner_bg, inner_radius = _detect_inner_bg(
            node,
            container_bg=container_bg,
            global_design_image=global_design_image,
        )

        # Rule 11 (Phase 50.5) — pin inner card width to dominant image width.
        # Only meaningful when a nested card was actually detected.
        inner_card_fixed_width: int | None = None
        if inner_bg is not None and get_settings().design_sync.frame_rules_enabled:
            card_spec = rule_11_card_width_from_dominant_image(node)
            if card_spec is not None:
                inner_card_fixed_width = card_spec.fixed_width_px

        # Physical-card identity exception (Phase 50.7) — runs on sections that
        # already carry a card surface (inner_bg). Phase 50.8 adds a bounded
        # subtree-walk fallback for nested cards (e.g. LEGO ``mj-wrapper`` →
        # ``mj-section``) where ``_detect_inner_bg`` cannot reach the card.
        # Rule 9 (Phase 52.7) reads ``is_physical_card_surface`` to skip the
        # dark-mode flip.
        is_physical_card_surface = False
        physical_card_signals: tuple[str, ...] = ()
        ds_cfg = get_settings().design_sync
        if ds_cfg.physical_card_detection_enabled:
            if inner_bg is not None:
                sibling_radii = collect_sibling_radii(
                    [n for n, _, _, _ in candidates],
                    exclude_node_id=node.id,
                )
                detection = detect_physical_card_surface(
                    node,
                    sibling_radii=sibling_radii,
                    min_signals=PHYSICAL_CARD_MIN_SIGNALS,
                )
                is_physical_card_surface = detection.is_physical
                physical_card_signals = detection.signals
            else:
                nested = find_physical_card_in_subtree(
                    node,
                    min_signals=PHYSICAL_CARD_MIN_SIGNALS,
                )
                if nested is not None:
                    is_physical_card_surface = True
                    physical_card_signals = ("nested_card", *nested.signals)

        # 53.3b — reattach a captured gradient fill: the section node (or the
        # wrapper it was unwrapped from) is the node whose fill produced a
        # ``tokens.gradients`` entry at 52.5.
        gradient_ref: str | None = None
        if gradient_node_ids:
            if node.id in gradient_node_ids:
                gradient_ref = node.id
            elif parent_wrapper_id and parent_wrapper_id in gradient_node_ids:
                gradient_ref = parent_wrapper_id

        # 53.5 — divider rule recovery: the visible rule of an ``mj-divider``
        # is the stroke of a zero-area LINE child, not the section frame's own
        # (usually empty) stroke. Adopt it so the matcher can thread colour +
        # thickness into the divider seed.
        stroke_color = node.stroke_color
        stroke_weight = node.stroke_weight
        if section_type == EmailSectionType.DIVIDER and stroke_color is None:
            line_stroke = _zero_area_vector_stroke(node)
            if line_stroke is not None:
                stroke_color, stroke_weight = line_stroke

        sections.append(
            EmailSection(
                section_type=section_type,
                node_id=node.id,
                node_name=node.name,
                y_position=node.y,
                x_position=node.x,
                width=node.width,
                height=node.height,
                column_layout=col_layout,
                column_count=col_count,
                texts=texts,
                images=images,
                buttons=buttons,
                bg_color=node.fill_color,
                padding_top=node.padding_top,
                padding_right=node.padding_right,
                padding_bottom=node.padding_bottom,
                padding_left=node.padding_left,
                item_spacing=node.item_spacing,
                column_groups=col_groups,
                column_width_fractions=compute_column_width_fractions(col_groups),
                classification_confidence=classification_confidence,
                vlm_classification=vlm_type_str,
                vlm_confidence=vlm_conf,
                content_roles=roles,
                child_content_groups=child_groups,
                container_bg=container_bg,
                parent_wrapper_id=parent_wrapper_id,
                inner_bg=inner_bg,
                inner_radius=inner_radius,
                inner_card_fixed_width=inner_card_fixed_width,
                is_physical_card_surface=is_physical_card_surface,
                physical_card_signals=physical_card_signals,
                stroke_color=stroke_color,
                stroke_weight=stroke_weight,
                peel_row_id=peel_row_id,
                gradient_ref=gradient_ref,
                effects_summary=_collect_effects_summary(node),
            )
        )

    # Sort by y-position (top to bottom)
    sections.sort(key=lambda s: s.y_position if s.y_position is not None else 0.0)

    # Calculate spacing between sections
    sections = _calculate_spacing(sections, wrapper_bounds)

    # Boundary classification (Phase 50.2) — needs the y-sorted sections
    if global_design_image is not None:
        from app.design_sync.bgcolor_propagator import classify_section_boundaries

        boundaries = classify_section_boundaries(
            sections,
            global_design_image=global_design_image,
        )
        sections = [
            dataclasses.replace(
                s,
                boundary_above=boundaries[s.node_id].boundary_above,
                boundary_below=boundaries[s.node_id].boundary_below,
                sampled_top_color=boundaries[s.node_id].sampled_top_color,
                sampled_bottom_color=boundaries[s.node_id].sampled_bottom_color,
            )
            if s.node_id in boundaries
            else s
            for s in sections
        ]

    total_text_blocks = sum(len(s.texts) for s in sections)
    total_images = sum(len(s.images) for s in sections)

    spacing_map = generate_spacing_map(sections)

    return DesignLayoutDescription(
        file_name=structure.file_name,
        overall_width=overall_width,
        sections=sections,
        total_text_blocks=total_text_blocks,
        total_images=total_images,
        spacing_map=spacing_map,
    )


def _find_primary_page(pages: list[DesignNode]) -> DesignNode:
    """Find the primary page — prefer one named 'email' or 'design'."""
    for page in pages:
        lower_name = page.name.lower()
        if "email" in lower_name or "design" in lower_name:
            return page
    return pages[0]


def _get_section_candidates(page: DesignNode) -> list[DesignNode]:
    """Get top-level frames from a page as section candidates.

    When a single large wrapper frame is found (e.g. a full email design),
    use its children as section candidates instead of treating the wrapper
    as one section.
    """
    top_frames = [child for child in page.children if child.type in _FRAME_TYPES]

    # If there's exactly one tall frame with multiple children, unwrap it —
    # it's likely a full-email wrapper (e.g. "EmailLove" containing mj-wrappers)
    if len(top_frames) == 1:
        wrapper = top_frames[0]
        inner = [child for child in wrapper.children if child.type in _FRAME_TYPES]
        if len(inner) >= 2:
            return inner

    return top_frames


def _expand_container_wrappers(
    candidates: list[DesignNode],
    naming: NamingConvention,
) -> list[tuple[DesignNode, str | None, str | None, str | None]]:
    """Wrapper unwrap pre-pass (Phase 50.3, Gap 1).

    A ``mj-wrapper`` (or any FRAME with a coloured fill plus ≥2 ``mj-section``
    children) is treated as one ``EmailSection`` by ``analyze_layout`` today;
    that collapses heading + cards / heading + product rows into a single
    component. This pass replaces such a wrapper with its children, propagating
    the wrapper's fill as ``container_bg`` and recording the wrapper's id as
    ``parent_wrapper_id``.

    Gated to MJML-named files for now — descriptive naming is deferred to
    Phase 51 — and behind ``DESIGN_SYNC__WRAPPER_UNWRAP_ENABLED`` so the
    behaviour change can be rolled out per the master plan risks table.

    Returns a list of ``(section_node, container_bg, parent_wrapper_id)``
    tuples. When unchanged, ``container_bg`` and ``parent_wrapper_id`` are
    ``None`` so existing downstream code sees the same shape it always has.
    """
    if naming != NamingConvention.MJML:
        return [(node, None, None, None) for node in candidates]

    if not get_settings().design_sync.wrapper_unwrap_enabled:
        return [(node, None, None, None) for node in candidates]

    peel_enabled = get_settings().design_sync.semantic_peel_enabled

    expanded: list[tuple[DesignNode, str | None, str | None, str | None]] = []
    for node in candidates:
        if _is_container_wrapper(node):
            wrapper_bg = node.fill_color
            for child in node.children:
                if _is_section_child(child):
                    expanded.append((child, wrapper_bg, node.id, None))
        elif peel_enabled and (grandkids := _peelable_grandkids(node)) is not None:
            # Phase 53 D3: constrained one-level peel. Grandkids surface as
            # solo sections (no parent_wrapper_id — they must COUNT as
            # sections, not regroup into one band); the wrapper fill still
            # propagates so card surfaces keep their background. Same-row
            # siblings share a peel_row_id so the renderer can compose them
            # side-by-side without collapsing the section count.
            rows = _peel_rows(grandkids)
            logger.info(
                "design_sync.semantic_peel_applied",
                wrapper_id=node.id,
                peeled_count=len(grandkids),
                row_count=len(rows),
            )
            for row_idx, row in enumerate(rows):
                row_id = f"{node.id}:r{row_idx}" if len(row) > 1 else None
                for grandkid in row:
                    expanded.append((grandkid, node.fill_color, None, row_id))
        else:
            expanded.append((node, None, None, None))
    return expanded


def _wrapper_frame_bounds(
    candidates: list[DesignNode],
    naming: NamingConvention,
) -> dict[str, tuple[float, float]]:
    """Map each band wrapper id → ``(frame_top, frame_bottom)`` (Track G G1, M1).

    A band's visual y-extent is the wrapper FRAME (its fill + internal
    padding), not the bounding box of its child sections. ``_calculate_spacing``
    would otherwise measure the gap to a band from its first child's top —
    which sits ``paddingTop`` below the frame — turning the wrapper's own
    coloured top/bottom padding into a phantom white ``spacing_after`` gap
    between bands (the 20px slits in M1).

    Mirrors the gating and ``_is_container_wrapper`` predicate of
    :func:`_expand_container_wrappers` so the two agree on exactly which frames
    became bands; returns ``{}`` when unwrap is off (no section carries a
    ``parent_wrapper_id`` then, so the map is never consulted).
    """
    if naming != NamingConvention.MJML:
        return {}
    if not get_settings().design_sync.wrapper_unwrap_enabled:
        return {}
    bounds: dict[str, tuple[float, float]] = {}
    for node in candidates:
        if _is_container_wrapper(node) and node.y is not None and node.height is not None:
            bounds[node.id] = (node.y, node.y + node.height)
    return bounds


def _peel_rows(grandkids: list[DesignNode]) -> list[list[DesignNode]]:
    """Group peeled grandkids into visual rows by y-proximity, left-to-right.

    Same-row members can sit a few px apart in y (observed 6px on the
    starbucks card pair), so rows close over ``_Y_TOLERANCE`` against the
    row's first member rather than requiring exact y equality.
    """
    ordered = sorted(
        grandkids,
        key=lambda g: (
            g.y if g.y is not None else 0.0,
            g.x if g.x is not None else 0.0,
        ),
    )
    rows: list[list[DesignNode]] = []
    for grandkid in ordered:
        gy = grandkid.y if grandkid.y is not None else 0.0
        if rows:
            head = rows[-1][0]
            hy = head.y if head.y is not None else 0.0
            if abs(gy - hy) <= _Y_TOLERANCE:
                rows[-1].append(grandkid)
                continue
        rows.append([grandkid])
    for row in rows:
        row.sort(key=lambda g: g.x if g.x is not None else 0.0)
    return rows


def _is_container_wrapper(node: DesignNode) -> bool:
    """A container wrapper has a non-default fill AND ≥2 section children."""
    if not node.fill_color:
        return False
    section_children = [c for c in node.children if _is_section_child(c)]
    return len(section_children) >= 2


# Column height below which an image-free grandkid row reads as one atomic
# data row (stat numbers, fine print) rather than content cards. Sits between
# observed stat rows (~30px) and the smallest peel-worthy content row
# (icon+label nav, ~64px); content-scale, never fixture-keyed.
_PEEL_MIN_CARD_HEIGHT = 48.0


def _peelable_grandkids(node: DesignNode) -> list[DesignNode] | None:
    """Constrained one-level peel target check (Phase 53 D3, spike §C2b).

    The under-segmenter shape is ``mj-wrapper → single mj-section → N column
    grandkids``: the ≥2-section-child unwrap predicate sees one direct child,
    so the grandkid cards never surface. By MJML semantics that shape is ONE
    section — whether it should instead count as N sections is decided by what
    the columns *mean* (53.1 gate: proven semantic, no structural rule).

    Returns the grandkid frames when the wrapper matches the shape AND the
    content-scale heuristic classifies them as content cards (``peel``);
    ``None`` for keep or any shape mismatch.
    """
    name_lower = (node.name or "").lower()
    if "mj-wrapper" not in name_lower:
        return None
    section_children = [c for c in node.children if _is_section_child(c)]
    if len(section_children) != 1:
        return None
    child = section_children[0]
    grandkids = [g for g in child.children if g.type in _FRAME_TYPES]
    if len(grandkids) < 2:
        return None
    if not _grandkids_are_cards(grandkids):
        return None
    return grandkids


def _grandkids_are_cards(grandkids: list[DesignNode]) -> bool:
    """Content-scale peel/keep discriminator (Phase 53 D3).

    ``peel`` (True) when any column carries imagery or card-scale height —
    product cards, icon+label nav items, image+text feature cards. ``keep``
    (False) when every column is a short, image-free text cell: that reads as
    one atomic data row (stat numbers), which MJML semantics already count
    correctly as a single section.
    """
    for grandkid in grandkids:
        if _subtree_has_image(grandkid):
            return True
        if grandkid.height is not None and grandkid.height >= _PEEL_MIN_CARD_HEIGHT:
            return True
    return False


def _subtree_has_image(node: DesignNode) -> bool:
    """True when the subtree contains any IMAGE node."""
    if node.type == DesignNodeType.IMAGE:
        return True
    return any(_subtree_has_image(c) for c in node.children)


def _is_section_child(node: DesignNode) -> bool:
    """An ``mj-section``/``mj-wrapper`` child of a container, by name or shape.

    Matches name convention first (``mj-section``/``mj-wrapper`` substring).
    Falls back to a structural check: a FRAME/GROUP/COMPONENT with at least
    one content child of its own — that is what an MJML section looks like
    after the Figma plugin has flattened the column layer.
    """
    name_lower = (node.name or "").lower()
    if "mj-section" in name_lower or "mj-wrapper" in name_lower:
        return True
    return node.type in _FRAME_TYPES and bool(node.children)


def _detect_naming_convention(candidates: list[DesignNode]) -> NamingConvention:
    """Auto-detect which naming convention the design uses."""
    names: list[str] = []
    for c in candidates:
        names.append(c.name.lower())
        for child in c.children:
            names.append(child.name.lower())

    total = max(len(names), 1)
    mj_count = sum(1 for n in names if n.startswith("mj-"))
    pattern_count = sum(
        1
        for n in names
        for patterns in _SECTION_PATTERNS.values()
        for p in patterns
        if p in n and not p.startswith("mj-")
    )
    generic_count = sum(1 for n in names if _is_generic_name(n))

    if mj_count / total > 0.3:
        return NamingConvention.MJML
    if pattern_count / total > 0.2:
        return NamingConvention.DESCRIPTIVE
    if generic_count / total > 0.5:
        return NamingConvention.GENERIC
    return NamingConvention.DESCRIPTIVE


def _is_generic_name(name: str) -> bool:
    """Check if name is Figma auto-generated (Frame 1, Group 2, etc.)."""
    return bool(_GENERIC_NAME_RE.match(name.strip()))


def _classify_section(
    node: DesignNode,
    convention: NamingConvention,
    index: int,
    total: int,
    *,
    section_name_map: dict[str, str] | None = None,
) -> tuple[EmailSectionType, float]:
    """Classify a section using the detected naming convention.

    Returns (section_type, confidence) where confidence reflects how
    certain the classification is (1.0 = custom map, 0.30 = unknown).
    """
    # Custom map checked first — highest confidence
    if section_name_map:
        mapped = section_name_map.get(node.name.lower().strip())
        if mapped:
            try:
                return EmailSectionType(mapped), 1.0
            except ValueError:
                pass

    if convention == NamingConvention.MJML:
        return _classify_mj_section(node, index, total)

    # Descriptive and generic both try name first, then fall back
    section_type, confidence = _classify_by_name(node.name)
    if section_type != EmailSectionType.UNKNOWN:
        return section_type, confidence

    # When name matching fails, always try content-based heuristics
    # before falling back to position-only.  This handles frames with
    # ambiguous names (e.g. "Section") that have clear content signals.
    texts = _extract_texts(node)
    images = _extract_images(node)
    buttons = _extract_buttons(node)
    return _classify_by_content(node, texts, images, buttons, index, total)


def _classify_mj_section(
    node: DesignNode,
    index: int,
    total: int,
) -> tuple[EmailSectionType, float]:
    """Classify a section using MJML naming conventions.

    Returns (section_type, confidence) where MJML classification yields
    0.85-0.95 confidence for role-based matches.
    """
    name = node.name.lower().strip()

    # Walk children first to infer type from content roles — child roles
    # take priority over generic mj-section/mj-wrapper direct mapping
    child_roles: set[str] = set()
    for child in _walk_mj_children(node):
        role = _get_mj_role(child.name)
        if role:
            child_roles.add(role)

    # Also detect by node type (IMAGE nodes without mj-* names)
    for child in _walk_mj_children(node):
        if child.type == DesignNodeType.IMAGE:
            child_roles.add("image")
        elif child.type == DesignNodeType.TEXT and child.text_content:
            child_roles.add("text")

    # Filter out structural roles — only use content roles for classification
    _STRUCTURAL_ROLES = {"section", "column", "wrapper"}
    content_roles = child_roles - _STRUCTURAL_ROLES

    # Specific content roles override the generic mj-section/mj-wrapper mapping
    if content_roles == {"image"} and _has_large_image_child(node):
        return EmailSectionType.HERO, 0.95
    if "social" in content_roles:
        return EmailSectionType.SOCIAL, 0.95
    if "nav" in content_roles:
        return EmailSectionType.NAV, 0.95
    if content_roles == {"divider"} or (content_roles == {"divider", "text"}):
        return EmailSectionType.DIVIDER, 0.95
    if content_roles == {"spacer"}:
        return EmailSectionType.SPACER, 0.95

    # Image-only at top → HERO
    if content_roles == {"image"} and index <= 1:
        return EmailSectionType.HERO, 0.90

    # Text + button + image → rich content
    if "image" in content_roles and "text" in content_roles and "button" in content_roles:
        return EmailSectionType.CONTENT, 0.85
    if "button" in content_roles and "text" in content_roles and "image" not in content_roles:
        # Many texts with short content → likely NAV
        texts = _extract_texts(node)
        if len(texts) >= 4 and all(len(t.content) <= 30 for t in texts):
            return EmailSectionType.NAV, 0.85
        return EmailSectionType.CONTENT, 0.85

    # Last section with only text → FOOTER
    if index == total - 1 and content_roles <= {"text"}:
        return EmailSectionType.FOOTER, 0.85

    # Direct mj-* type mapping (for mj-hero, mj-navbar, etc.)
    if name in _MJ_SECTION_MAP:
        return _MJ_SECTION_MAP[name], 0.95

    # Fall back to descriptive name matching, then position
    section_type, confidence = _classify_by_name(node.name)
    if section_type != EmailSectionType.UNKNOWN:
        return section_type, confidence
    return _classify_by_position(node, index, total, _has_large_image_child(node))


def _walk_mj_children(node: DesignNode, max_depth: int = 5) -> list[DesignNode]:
    """Walk up to max_depth levels to find mj-* named children.

    MJML designs nest content 3-4 levels deep:
    mj-wrapper > mj-section > mj-column > mj-image-Frame > mj-image
    So we need to walk deeper than 2 levels.
    """
    result: list[DesignNode] = []

    def _recurse(n: DesignNode, depth: int) -> None:
        if depth > max_depth:
            return
        for child in n.children:
            result.append(child)
            _recurse(child, depth + 1)

    _recurse(node, 0)
    return result


def _get_mj_role(name: str) -> str | None:
    """Get content role from mj-* name (checking both exact and prefix match)."""
    lower = name.lower().strip()
    if lower in _MJ_CONTENT_ROLES:
        return _MJ_CONTENT_ROLES[lower]
    for prefix, role in _MJ_CONTENT_ROLES.items():
        if lower.startswith(prefix):
            return role
    return None


_SOCIAL_URL_RE = re.compile(
    r"(?i)(?:facebook|twitter|x|instagram|linkedin|youtube|tiktok|pinterest)\.com",
)

_LEGAL_TEXT_RE = re.compile(r"©|copyright|\ball rights reserved\b", re.IGNORECASE)

_UNSUBSCRIBE_RE = re.compile(r"\bunsubscribe\b", re.IGNORECASE)


def _classify_by_content(
    node: DesignNode,
    texts: list[TextBlock],
    images: list[ImagePlaceholder],
    buttons: list[ButtonElement],
    index: int,
    total: int,
) -> tuple[EmailSectionType, float]:
    """Infer section type from content when names are unhelpful.

    Returns (section_type, confidence) where content-based confidence
    is 0.65-0.85 depending on signal strength.
    """
    has_images = len(images) > 0
    has_texts = len(texts) > 0
    has_buttons = len(buttons) > 0
    all_text = " ".join(t.content for t in texts) if has_texts else ""

    # Full-width image near top → hero (strong signal)
    if _has_large_image_child(node) and not has_texts and index <= 1:
        return EmailSectionType.HERO, 0.85

    # Large image + text overlay near top (tall section) → hero
    if _has_large_image_child(node) and has_texts and index <= 1:
        height = node.height if node.height is not None else 0
        if height >= 300:
            return EmailSectionType.HERO, 0.85

    # Text + button near top with large heading → hero
    if has_texts and has_buttons and not has_images and index <= 2:
        heading_sizes = [t.font_size for t in texts if t.font_size and t.font_size > 20]
        if heading_sizes:
            return EmailSectionType.HERO, 0.75

    # Section with ©/copyright/unsubscribe text near bottom → footer (strong signal)
    if (
        has_texts
        and (_LEGAL_TEXT_RE.search(all_text) or _UNSUBSCRIBE_RE.search(all_text))
        and index >= total - 2
    ):
        return EmailSectionType.FOOTER, 0.85

    # Social platform URLs → social (strong signal)
    if has_texts and _SOCIAL_URL_RE.search(all_text):
        return EmailSectionType.SOCIAL, 0.75

    # Button-only section → CTA
    if has_buttons and not has_texts and not has_images:
        return EmailSectionType.CTA, 0.70

    # Many short texts → navigation
    if len(texts) >= 4 and all(len(t.content) < 30 for t in texts):
        return EmailSectionType.NAV, 0.70

    # Small text at bottom → footer (weaker signal)
    if index >= total - 2 and has_texts and not has_images:
        avg_size = sum(t.font_size if t.font_size is not None else 14 for t in texts) / len(texts)
        if avg_size <= 13:
            return EmailSectionType.FOOTER, 0.65

    return _classify_by_position(node, index, total, _has_large_image_child(node))


def _classify_by_name(name: str) -> tuple[EmailSectionType, float]:
    """Match frame name against known email section patterns (word-boundary)."""
    lower = name.lower().strip()
    for section_type, patterns in _SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern)}\b", lower):
                return section_type, 0.90
    return EmailSectionType.UNKNOWN, 0.30


def _classify_by_position(
    node: DesignNode,
    index: int,
    total: int,
    has_large_image: bool,
) -> tuple[EmailSectionType, float]:
    """Fallback: classify by position + dimensions when name doesn't match.

    Uses height, position, and child content to infer section type.
    Returns (section_type, confidence) where confidence is 0.40-0.55.
    """
    height = node.height if node.height is not None else 0

    # Very short sections are spacers/dividers — but only when the height
    # is explicitly set.  Nodes with missing dimensions (height=None) that
    # contain children should fall through to content-based classification
    # rather than being mislabelled as spacers.
    if node.height is not None and height <= 30:
        return EmailSectionType.SPACER, 0.55
    if node.height is not None and 30 < height <= 60:
        return EmailSectionType.DIVIDER, 0.55

    # Position-based heuristics only apply when there are multiple sections.
    # A single section should default to CONTENT, not HEADER or FOOTER.
    if total > 1:
        # First section is header/nav
        if index == 0:
            return EmailSectionType.HEADER, 0.55

        # Last section is footer
        if index == total - 1:
            return EmailSectionType.FOOTER, 0.55

    # Second-to-last short section is often social links
    if index == total - 2 and height <= 150:
        return EmailSectionType.SOCIAL, 0.50

    # Tall section near the top with or without large image → hero
    if index == 1 and height >= 300:
        return EmailSectionType.HERO, 0.50
    if has_large_image and height >= 300:
        return EmailSectionType.HERO, 0.50

    # Short section with button-sized height → CTA only if button-like content
    if 60 < height <= 150:
        # Check children for button-like frames (small frame with short text child)
        has_button_child = any(
            c.type in _FRAME_TYPES
            and c.height is not None
            and c.height <= 80
            and any(
                gc.type == DesignNodeType.TEXT and gc.text_content and len(gc.text_content) <= 30
                for gc in c.children
            )
            for c in node.children
        )
        if has_button_child:
            return EmailSectionType.CTA, 0.50

    return EmailSectionType.CONTENT, 0.40


def _detect_column_layout(node: DesignNode) -> tuple[ColumnLayout, int]:
    """Detect column layout from children's positions (backward-compat wrapper)."""
    layout, count, _groups = _detect_column_layout_with_groups(node)
    return layout, count


def _detect_column_layout_with_groups(
    node: DesignNode,
    convention: NamingConvention = NamingConvention.GENERIC,
) -> tuple[ColumnLayout, int, list[ColumnGroup]]:
    """Detect column layout using structure first, position fallback.

    Returns (layout_type, column_count, column_groups).
    """
    # Strategy 1: MJML — look for mj-column children
    if convention == NamingConvention.MJML:
        columns = _detect_mj_columns(node)
        if columns:
            return _layout_from_count(len(columns)), len(columns), columns

    # Strategy 2: Auto-layout HORIZONTAL means children are columns
    if node.layout_mode == "HORIZONTAL":
        frame_children = [
            c
            for c in node.children
            if c.type in _FRAME_TYPES and c.width is not None and c.width > 40
        ]
        if len(frame_children) >= 2:
            columns = _build_column_groups(frame_children)
            return _layout_from_count(len(columns)), len(columns), columns

    # Strategy 3: Position-based — group by Y-position (existing logic)
    columns = _detect_position_columns(node)
    count = len(columns) if columns else 1
    return _layout_from_count(count), count, columns


def _layout_from_count(count: int) -> ColumnLayout:
    """Map column count to ColumnLayout enum."""
    if count >= 4:
        return ColumnLayout.MULTI_COLUMN
    if count == 3:
        return ColumnLayout.THREE_COLUMN
    if count == 2:
        return ColumnLayout.TWO_COLUMN
    return ColumnLayout.SINGLE


def _column_content_order(
    node: DesignNode,
    texts: list[TextBlock],
    images: list[ImagePlaceholder],
    buttons: list[ButtonElement],
) -> tuple[str, ...]:
    """Node ids of a column's extracted content in design tree order (F10).

    The per-category extractors each walk the column subtree pre-order, so
    every list is internally ordered but the cross-category interleave is
    lost. One more pre-order walk restores it: the returned tuple lets
    ``_build_column_fill_html`` emit rows in design vertical order (a tag
    pill above the heading, a product name above its spec-icon rows) instead
    of images→texts→buttons buckets. Ids the walk doesn't reach (e.g. a
    wrapped image's frame exported under a different id) simply stay out of
    the tuple — the consumer keeps them in category order.
    """
    wanted = (
        {text.node_id for text in texts}
        | {img.node_id for img in images}
        | {btn.node_id for btn in buttons}
    )
    order: list[str] = []

    def visit(current: DesignNode) -> None:
        if current.id in wanted:
            order.append(current.id)
        for child in current.children:
            visit(child)

    visit(node)
    return tuple(order)


def _detect_mj_columns(node: DesignNode) -> list[ColumnGroup]:
    """Find mj-column children and extract their content."""
    # Walk one level to find mj-section, then its mj-column children
    section_node = node
    for child in node.children:
        if child.name.lower().startswith("mj-section"):
            section_node = child
            break

    all_columns: list[ColumnGroup] = []
    col_idx = 0
    for child in section_node.children:
        if child.name.lower().startswith("mj-column"):
            buttons = _extract_buttons(child)
            btn_ids = _collect_button_node_ids(buttons)
            texts = _extract_texts(child, exclude_node_ids=btn_ids)
            images = _extract_images(child)

            # Skip spacer-only columns (e.g., mj-column containing only mj-spacer)
            has_content = bool(texts or images or buttons)
            if not has_content:
                # Check if all children are spacers
                is_spacer = all(
                    c.name.lower().startswith("mj-spacer") or c.name.lower().startswith("spacer")
                    for c in child.children
                )
                if is_spacer:
                    continue

            col_idx += 1
            all_columns.append(
                ColumnGroup(
                    column_idx=col_idx,
                    node_id=child.id,
                    node_name=child.name,
                    texts=texts,
                    images=images,
                    buttons=buttons,
                    width=child.width,
                    content_order=_column_content_order(child, texts, images, buttons),
                )
            )
    return all_columns


def _build_column_groups(frame_children: list[DesignNode]) -> list[ColumnGroup]:
    """Build ColumnGroup from a list of frame children (auto-layout columns)."""
    groups: list[ColumnGroup] = []
    for idx, child in enumerate(frame_children, 1):
        buttons = _extract_buttons(child)
        btn_ids = _collect_button_node_ids(buttons)
        texts = _extract_texts(child, exclude_node_ids=btn_ids)
        images = _extract_images(child)
        groups.append(
            ColumnGroup(
                column_idx=idx,
                node_id=child.id,
                node_name=child.name,
                texts=texts,
                images=images,
                buttons=buttons,
                width=child.width,
                content_order=_column_content_order(child, texts, images, buttons),
            )
        )
    return groups


def compute_column_width_fractions(groups: list[ColumnGroup]) -> tuple[float, ...]:
    """Normalize measured column widths into fractions summing to 1.0.

    A8 (Phase 53 D2): returns ``()`` unless every column has a positive
    measured width — missing data falls back to the seed's equal widths.
    """
    if len(groups) < 2:
        return ()
    widths: list[float] = []
    for group in groups:
        if group.width is None or group.width <= 0:
            return ()
        widths.append(group.width)
    total = sum(widths)
    return tuple(w / total for w in widths)


def _detect_position_columns(node: DesignNode) -> list[ColumnGroup]:
    """Position-based column detection (Y-grouping, deterministic)."""
    frame_children = [
        c for c in node.children if c.type in _FRAME_TYPES and c.x is not None and c.y is not None
    ]

    if len(frame_children) < 2:
        return []

    # Sort by Y first (then X) for deterministic grouping
    frame_children.sort(
        key=lambda c: (c.y if c.y is not None else 0.0, c.x if c.x is not None else 0.0)
    )

    # Group by y-position (greedy non-overlapping bands)
    y_groups: list[list[DesignNode]] = []
    for child in frame_children:
        if child.y is None:
            continue
        placed = False
        for group in y_groups:
            ref_y = group[0].y
            if ref_y is not None and abs(child.y - ref_y) <= _Y_TOLERANCE:
                group.append(child)
                placed = True
                break
        if not placed:
            y_groups.append([child])

    if not y_groups:
        return []

    max_group = max(y_groups, key=len)
    if len(max_group) < 2:
        return []

    # Sort each row by x-position
    max_group.sort(key=lambda c: c.x if c.x is not None else 0.0)
    return _build_column_groups(max_group)


def _extract_texts(
    node: DesignNode,
    *,
    exclude_node_ids: set[str] | None = None,
) -> list[TextBlock]:
    """Recursively extract text blocks from TEXT nodes."""
    results: list[TextBlock] = []
    _walk_for_texts(node, results, exclude_node_ids=exclude_node_ids)
    return results


def _walk_for_texts(
    node: DesignNode,
    results: list[TextBlock],
    *,
    exclude_node_ids: set[str] | None = None,
) -> None:
    """Walk tree collecting TEXT nodes, skipping excluded subtrees."""
    if exclude_node_ids and node.id in exclude_node_ids:
        return
    if node.type == DesignNodeType.TEXT and node.text_content:
        # Use actual font_size from design tool; fall back to bounding box height
        results.append(
            TextBlock(
                node_id=node.id,
                content=node.text_content,
                font_size=node.font_size if node.font_size is not None else node.height,
                is_heading=False,
                font_family=node.font_family,
                font_weight=node.font_weight,
                line_height=node.line_height_px,
                letter_spacing=node.letter_spacing_px,
                text_color=node.text_color,
                text_align=node.text_align,
                hyperlink=node.hyperlink,
                style_runs=node.style_runs,
                text_transform=node.text_transform,
                text_decoration=node.text_decoration,
            )
        )
    for child in node.children:
        _walk_for_texts(child, results, exclude_node_ids=exclude_node_ids)


def _extract_images(node: DesignNode) -> list[ImagePlaceholder]:
    """Identify IMAGE nodes and FRAMEs containing only an IMAGE child."""
    results: list[ImagePlaceholder] = []
    _walk_for_images(node, results)
    return results


def _crop_export_id(node: DesignNode) -> str | None:
    """Export the node itself when its IMAGE fill carries a crop (53.3c).

    A ``scaleMode`` other than the ``FILL`` default (FIT/CROP/TILE) is a crop
    instruction the HTML ``<img>`` can't express — exporting the node makes
    the Figma render bake the crop into the bitmap (the frame-wrapping-image
    path below already gets this for free by exporting the wrapper).
    """
    if node.scale_mode is not None and node.scale_mode != "FILL":
        return node.id
    return None


# 53.5 — standalone-vector recovery bounds. A dimension at or under the
# epsilon marks an mj-divider-class LINE (rule, not artwork); anything under
# the minimum on either axis is an export artifact, not an icon.
_ZERO_AREA_EPS = 1.0
_MIN_VECTOR_PX = 8.0


def _zero_area_vector_stroke(node: DesignNode) -> tuple[str, float | None] | None:
    """Stroke of the first zero-area stroked VECTOR in a subtree (53.5).

    The ``mj-divider`` shape: a LINE with height (or width) ≈ 0 whose visible
    rule IS its stroke. Rasterizing a 0-px PNG is useless — the parent divider
    section adopts the stroke instead, so the divider seed renders the real
    rule colour/thickness.
    """
    if (
        node.type == DesignNodeType.VECTOR
        and node.visible
        and node.stroke_color is not None
        and (
            (node.height is not None and node.height <= _ZERO_AREA_EPS)
            or (node.width is not None and node.width <= _ZERO_AREA_EPS)
        )
    ):
        return (node.stroke_color, node.stroke_weight)
    for child in node.children:
        found = _zero_area_vector_stroke(child)
        if found is not None:
            return found
    return None


def _rasterizable_vector(node: DesignNode) -> bool:
    """Whether a standalone VECTOR should rasterize via node export (53.5).

    Icons/logomarks with real area (at least 8x8 px). Zero-area LINEs are the
    divider shape (recovered as a section stroke, not a PNG); sub-8px
    fragments are artifacts.
    """
    return (
        node.type == DesignNodeType.VECTOR
        and node.visible
        and node.width is not None
        and node.height is not None
        and node.width >= _MIN_VECTOR_PX
        and node.height >= _MIN_VECTOR_PX
    )


def _walk_for_images(
    node: DesignNode,
    results: list[ImagePlaceholder],
    *,
    skip_vectors: bool = False,
) -> None:
    """Collect IMAGE nodes, IMAGE-filled FRAMEs, and standalone vectors (53.5).

    ``skip_vectors`` suppresses vector collection inside a subtree that is
    already exported as an image (the frame's node render bakes its children
    in — collecting the vector again would double-capture it).
    """
    if node.type == DesignNodeType.IMAGE:
        results.append(
            ImagePlaceholder(
                node_id=node.id,
                node_name=node.name,
                width=node.width,
                height=node.height,
                export_node_id=_crop_export_id(node),
                corner_radius_spec=_corner_spec_or_none(rule_10_image_corner_radii(node)),
                stroke_color=node.stroke_color,
                stroke_weight=node.stroke_weight,
            )
        )
    elif node.type == DesignNodeType.FRAME and node.image_ref:
        # Frame with IMAGE fill → treat as background image
        results.append(
            ImagePlaceholder(
                node_id=node.id,
                node_name=node.name,
                width=node.width,
                height=node.height,
                is_background=True,
                export_node_id=_crop_export_id(node),
                corner_radius_spec=_corner_spec_or_none(rule_10_image_corner_radii(node)),
                stroke_color=node.stroke_color,
                stroke_weight=node.stroke_weight,
            )
        )
        # Still recurse into children (frame has content over the bg) — but
        # the bg export renders the whole frame, so vectors are already baked.
        for child in node.children:
            _walk_for_images(child, results, skip_vectors=True)
    elif (
        node.type in (DesignNodeType.FRAME, DesignNodeType.GROUP)
        and len(node.children) == 1
        and node.children[0].type == DesignNodeType.IMAGE
    ):
        # Frame wrapping a single image — export the FRAME (includes bg fills).
        # Rule 10 reads radius from the frame (where Figma sets corner radii on
        # the wrapper, not the inner image).
        img = node.children[0]
        results.append(
            ImagePlaceholder(
                node_id=img.id,
                node_name=img.name,
                width=node.width,  # Use frame dimensions (includes padding/bg)
                height=node.height,
                export_node_id=node.id,  # Export the frame, not just the image fill
                corner_radius_spec=_corner_spec_or_none(rule_10_image_corner_radii(node)),
                # Border lives on the wrapper frame (like Rule 10's radii)
                stroke_color=node.stroke_color,
                stroke_weight=node.stroke_weight,
            )
        )
    elif not skip_vectors and _rasterizable_vector(node):
        # 53.5 — standalone icon/logomark vector: the Figma image API
        # rasterizes the node (BOOLEAN_OPERATION subtrees composite in the
        # render), so downstream export/URL/alt plumbing works unchanged.
        # No recursion — the export bakes the whole subtree.
        results.append(
            ImagePlaceholder(
                node_id=node.id,
                node_name=node.name,
                width=node.width,
                height=node.height,
                export_node_id=node.id,
                stroke_color=node.stroke_color,
                stroke_weight=node.stroke_weight,
            )
        )
    else:
        for child in node.children:
            _walk_for_images(child, results, skip_vectors=skip_vectors)


def _corner_spec_or_none(spec: CornerRadiusSpec) -> CornerRadiusSpec | None:
    """Drop the no-radius case so downstream callers can ``if spec:``."""
    if spec.scalar is None and spec.per_corner is None:
        return None
    return spec


# 53.3d — reproducibility classifier bounds. Boring and conservative (raster
# only when certain): visible rotation beyond ±1° or sibling pairs whose
# bboxes clearly overlap (≥25% of the smaller box; near-parent-sized backdrop
# layers excluded).
_ROTATION_TOLERANCE_DEG = 1.0
_OVERLAP_MIN_RATIO = 0.25
_BACKDROP_COVERAGE = 0.95


def _overlapping_children(node: DesignNode) -> tuple[str, str] | None:
    """First clearly-overlapping visible child pair, if any (53.3d)."""
    boxes: list[tuple[str, float, float, float, float]] = []
    parent_area: float | None = None
    if node.width is not None and node.height is not None:
        parent_area = node.width * node.height
    for child in node.children:
        if not child.visible:
            continue
        if child.x is None or child.y is None or child.width is None or child.height is None:
            continue
        area = child.width * child.height
        if parent_area is not None and area >= _BACKDROP_COVERAGE * parent_area:
            continue  # backdrop layer (hero image under text), not a content overlap
        boxes.append((child.id, child.x, child.y, child.width, child.height))
    for i, (a_id, ax, ay, aw, ah) in enumerate(boxes):
        for b_id, bx, by, bw, bh in boxes[i + 1 :]:
            ix = min(ax + aw, bx + bw) - max(ax, bx)
            iy = min(ay + ah, by + bh) - max(ay, by)
            if ix <= 0.0 or iy <= 0.0:
                continue
            smaller = min(aw * ah, bw * bh)
            if smaller > 0.0 and ix * iy >= _OVERLAP_MIN_RATIO * smaller:
                return (a_id, b_id)
    return None


def _unreproducible_reason(node: DesignNode) -> str | None:
    """Why the fixed-seed renderer cannot reproduce this subtree (53.3d).

    ``None`` when the subtree is reproducible. THIS is the reproducibility
    classifier — z-order/overlap and rotation are the two properties the
    table renderer cannot express (ceiling doc §2), so the section falls back
    to one exported image of the whole frame when the flag is on.
    """
    if not node.visible:
        return None
    if node.rotation is not None and abs(node.rotation) > _ROTATION_TOLERANCE_DEG:
        return f"rotation:{node.id}"
    overlap = _overlapping_children(node)
    if overlap is not None:
        return f"overlap:{overlap[0]}+{overlap[1]}"
    for child in node.children:
        reason = _unreproducible_reason(child)
        if reason is not None:
            return reason
    return None


def _is_reproducible(node: DesignNode) -> bool:
    """Whether the fixed-seed renderer can reproduce this subtree (53.3d)."""
    return _unreproducible_reason(node) is None


def _collect_effects_summary(node: DesignNode) -> str | None:
    """Aggregate dropped-effect summaries across a section subtree (53.3a).

    Per-node ``DesignNode.effects_summary`` values (``"<count>:<TYPE,...>"``)
    are merged into one section-level summary of the same shape so the
    converter can surface the loss as a warning. ``None`` when the subtree
    carries no effects.
    """
    total = 0
    types: set[str] = set()

    def _walk(n: DesignNode) -> None:
        nonlocal total
        if n.effects_summary:
            count_str, _, type_csv = n.effects_summary.partition(":")
            try:
                total += int(count_str)
            except ValueError:
                total += 1
            types.update(t for t in type_csv.split(",") if t)
        for child in n.children:
            _walk(child)

    _walk(node)
    if total == 0:
        return None
    return f"{total}:{','.join(sorted(types))}"


def validate_image_dimensions(
    placeholder: ImagePlaceholder,
    exported_width: int,
    exported_height: int,
    scale: float = 2.0,
) -> str | None:
    """Return warning if exported dims don't match expected (within 1px tolerance).

    Compares exported image dimensions against the Figma node's design bounds
    (adjusted for export scale).
    """
    if placeholder.width is None or placeholder.height is None:
        return None
    expected_w = int(placeholder.width * scale)
    expected_h = int(placeholder.height * scale)
    if abs(exported_width - expected_w) > 1 or abs(exported_height - expected_h) > 1:
        return (
            f"Image {placeholder.node_id} dimension mismatch: "
            f"exported {exported_width}\u00d7{exported_height}, "
            f"expected {expected_w}\u00d7{expected_h} (@{scale}x)"
        )
    return None


def _extract_buttons(
    node: DesignNode,
    *,
    extra_hints: list[str] | None = None,
) -> list[ButtonElement]:
    """Detect buttons: small frames with a TEXT child containing short text."""
    results: list[ButtonElement] = []
    _walk_for_buttons(node, results, extra_hints=extra_hints)
    return results


_DEFAULT_BUTTON_HINTS = ("button", "btn", "cta", "action", "link", "mj-button")


def _collect_button_node_ids(buttons: list[ButtonElement]) -> set[str]:
    """Collect node IDs of detected buttons for text extraction exclusion."""
    return {b.node_id for b in buttons}


def _walk_for_buttons(
    node: DesignNode,
    results: list[ButtonElement],
    *,
    extra_hints: list[str] | None = None,
) -> None:
    """Walk tree looking for button-like elements."""
    # A button is a small FRAME/COMPONENT with a TEXT child that has short text
    if node.type in (DesignNodeType.FRAME, DesignNodeType.COMPONENT, DesignNodeType.INSTANCE):
        text_children = [
            c for c in node.children if c.type == DesignNodeType.TEXT and c.text_content
        ]
        if (
            len(text_children) == 1
            and text_children[0].text_content
            and len(text_children[0].text_content) <= 30
            and node.height is not None
            and node.height <= 80
        ):
            # Check if name also hints at button/CTA
            lower_name = node.name.lower()
            hints: tuple[str, ...] = _DEFAULT_BUTTON_HINTS
            if extra_hints:
                hints = (*_DEFAULT_BUTTON_HINTS, *extra_hints)
            is_button_name = any(h in lower_name for h in hints)
            # Accept if name hints (covers ghost/outline buttons) OR visible fill
            has_fill = bool(
                node.fill_color and node.fill_color.upper() not in ("#FFFFFF", "#FFF", "")
            )
            # Ghost buttons: accept by name even without fill (outline-style CTAs)
            if is_button_name or has_fill:
                # Resolve hyperlink: prefer frame hyperlink, fall back to text child
                btn_url = node.hyperlink or text_children[0].hyperlink
                btn_text_color = text_children[0].text_color
                # Detect icon child: small RECTANGLE/VECTOR/FRAME named "icon"
                icon_node_id: str | None = None
                for child in node.children:
                    if (
                        child.type
                        in (DesignNodeType.VECTOR, DesignNodeType.FRAME, DesignNodeType.IMAGE)
                        and "icon" in child.name.lower()
                        and child.width is not None
                        and child.height is not None
                        and child.width <= 64
                        and child.height <= 64
                    ):
                        icon_node_id = child.id
                        break
                results.append(
                    ButtonElement(
                        node_id=node.id,
                        text=text_children[0].text_content,
                        width=node.width,
                        height=node.height,
                        fill_color=node.fill_color,
                        url=btn_url,
                        # Absent Figma cornerRadius = square; normalize None→0.0
                        # so square buttons render square (not the 4px fallback).
                        border_radius=(
                            node.corner_radius if node.corner_radius is not None else 0.0
                        ),
                        text_color=btn_text_color,
                        stroke_color=node.stroke_color,
                        stroke_weight=node.stroke_weight,
                        icon_node_id=icon_node_id,
                        font_size=text_children[0].font_size,
                        font_weight=text_children[0].font_weight,
                        font_family=text_children[0].font_family,
                        corner_radius_spec=_corner_spec_or_none(rule_8_corner_radius(node)),
                        padding_top=node.padding_top,
                        padding_right=node.padding_right,
                        padding_bottom=node.padding_bottom,
                        padding_left=node.padding_left,
                    )
                )
                return  # Don't recurse into button internals

    for child in node.children:
        _walk_for_buttons(child, results, extra_hints=extra_hints)


def _has_large_image_child(node: DesignNode, *, _depth: int = 0) -> bool:
    """Check if node has a large IMAGE child (recurse up to 2 levels)."""
    if node.width is None or node.width == 0:
        return False

    for child in node.children:
        if (
            child.type == DesignNodeType.IMAGE
            and child.width is not None
            and child.width / node.width > 0.6
        ):
            return True
        if (
            _depth < 1
            and child.type in _FRAME_TYPES
            and _has_large_image_child(child, _depth=_depth + 1)
        ):
            return True

    return False


def _compute_content_roles(
    texts: list[TextBlock],
    images: list[ImagePlaceholder],
    buttons: list[ButtonElement],
) -> tuple[str, ...]:
    """Derive content role hints from section content (design-agnostic)."""
    roles: list[str] = []
    has_icon = any(
        img.width is not None and img.width <= 64 and img.height is not None and img.height <= 64
        for img in images
    )
    if texts and not images and not buttons:
        roles.append("text-only")
    if has_icon and texts:
        roles.append("text-with-icon")
    if images and texts:
        large_imgs = [i for i in images if i.width is not None and i.width > 200]
        if large_imgs:
            roles.append("editorial")
    # Event-like: multiple short labeled lines
    short_labeled = [t for t in texts if len(t.content) < 80 and ":" in t.content]
    if len(short_labeled) >= 2:
        roles.append("event-info")
    return tuple(roles)


def _assign_role_hints(texts: list[TextBlock], frame_id: str) -> list[TextBlock]:
    """Assign role_hint and source_frame_id to text blocks within a group."""
    if not texts:
        return texts
    sizes = [t.font_size for t in texts if t.font_size is not None]
    if not sizes:
        return [dataclasses.replace(t, source_frame_id=frame_id, role_hint="body") for t in texts]

    max_size = max(sizes)
    median_size = statistics.median(sizes)
    label_threshold = min(14.0, median_size * 0.7)

    result: list[TextBlock] = []
    for t in texts:
        hint = "body"
        if t.font_size is not None:
            if t.font_size >= max_size and t.font_size > median_size * 1.2:
                hint = "heading"
            elif t.font_size <= label_threshold:
                hint = "label"
        result.append(dataclasses.replace(t, source_frame_id=frame_id, role_hint=hint))
    return result


_GROUPABLE_TYPES = frozenset(
    {
        DesignNodeType.FRAME,
        DesignNodeType.GROUP,
        DesignNodeType.COMPONENT,
    }
)

# G2 (M2) — absolute heading floor for uniform-size sections, where the
# relative 1.3x-median rule has no signal. 24px sits between the corpus's
# largest uniform body copy (20px) and smallest uniform display text (24px).
_UNIFORM_HEADING_MIN_PX = 24.0


def _extract_content_groups(
    node: DesignNode,
    *,
    button_name_hints: list[str] | None = None,
) -> list[ContentGroup]:
    """Extract content groups from direct child frames of a section node.

    Each direct child FRAME/GROUP/COMPONENT that contains at least one TEXT or IMAGE
    node becomes a ContentGroup.  This preserves the parent-child relationship that
    flat extraction loses.

    Only produces groups when the section has 2+ qualifying child frames — if there's
    only one child frame (or all content is at the root level), returns empty list
    to signal the caller should use flat extraction.
    """
    groups: list[ContentGroup] = []
    for child in node.children:
        if child.type not in _GROUPABLE_TYPES:
            continue

        buttons = _extract_buttons(child, extra_hints=button_name_hints)
        button_ids = _collect_button_node_ids(buttons)
        texts = _extract_texts(child, exclude_node_ids=button_ids)
        images = _extract_images(child)

        if not texts and not images and not buttons:
            continue

        texts = _assign_role_hints(texts, child.id)

        groups.append(
            ContentGroup(
                frame_node_id=child.id,
                frame_name=child.name,
                texts=texts,
                images=images,
                buttons=buttons,
            )
        )

    if len(groups) < 2:
        return []
    return groups


def _detect_content_hierarchy(texts: list[TextBlock]) -> list[TextBlock]:
    """Mark headings based on relative font size (1.3x median = heading).

    Uniform-size sections (including single-text banners) carry no relative
    signal, so the median rule never fired and 30px display text landed in
    the body slot while the seed heading slot ghosted empty (Track G G2, M2).
    For those, an absolute heading-scale floor decides: >=24px is a heading
    (validated against all 6 corpus fixtures — the largest uniform body copy
    is 20px, the smallest uniform display text 24px).
    """
    if not texts:
        return texts

    sizes = [t.font_size for t in texts if t.font_size is not None]
    if not sizes:
        return texts

    if len(set(sizes)) == 1:
        if sizes[0] < _UNIFORM_HEADING_MIN_PX:
            return texts
        return [
            dataclasses.replace(t, is_heading=True) if t.font_size is not None else t for t in texts
        ]

    median_size = statistics.median(sizes)
    threshold = median_size * 1.3

    return [
        dataclasses.replace(t, is_heading=True)
        if t.font_size is not None and t.font_size >= threshold
        else t
        for t in texts
    ]


def _calculate_spacing(
    sections: list[EmailSection],
    wrapper_bounds: dict[str, tuple[float, float]] | None = None,
) -> list[EmailSection]:
    """Calculate spacing between consecutive sections.

    A band's y-extent is the wrapper FRAME, not its child sections (Track G
    G1, M1). When a section ends or begins a band, its facing edge is taken
    from ``wrapper_bounds`` (the frame's top/bottom) rather than the child
    bbox, so the wrapper's own coloured padding stays inside the band instead
    of surfacing as a white ``spacing_after`` gap between adjacent bands.
    Sections that share a ``parent_wrapper_id`` keep child-based spacing —
    intra-band gaps are absorbed by ``group_by_wrapper`` and never emitted.
    """
    if len(sections) < 2:
        return sections

    bounds = wrapper_bounds or {}
    result: list[EmailSection] = []
    for i, section in enumerate(sections):
        spacing: float | None = None
        if i < len(sections) - 1:
            nxt = sections[i + 1]
            same_band = (
                section.parent_wrapper_id is not None
                and section.parent_wrapper_id == nxt.parent_wrapper_id
            )
            current_bottom = _section_bottom(section)
            next_top = nxt.y_position
            if not same_band:
                curr_frame = bounds.get(section.parent_wrapper_id or "")
                if curr_frame is not None:
                    current_bottom = curr_frame[1]  # band frame bottom
                next_frame = bounds.get(nxt.parent_wrapper_id or "")
                if next_frame is not None:
                    next_top = next_frame[0]  # band frame top
            if current_bottom is not None and next_top is not None:
                spacing = max(0.0, next_top - current_bottom)

        result.append(
            dataclasses.replace(
                section,
                spacing_after=spacing,
                element_gaps=_compute_element_gaps(section),
            )
        )
    return result


def _compute_element_gaps(section: EmailSection) -> tuple[float, ...]:
    """Compute gaps between consecutive elements using auto-layout item_spacing."""
    if section.item_spacing is not None:
        n_children = len(section.texts) + len(section.images) + len(section.buttons)
        if n_children > 1:
            return tuple(section.item_spacing for _ in range(n_children - 1))
    return ()


def generate_spacing_map(sections: list[EmailSection]) -> dict[str, dict[str, float]]:
    """Build per-section spacing specification from layout analysis."""
    result: dict[str, dict[str, float]] = {}
    for section in sections:
        entry: dict[str, float] = {}
        if section.padding_top is not None:
            entry["padding_top"] = section.padding_top
        if section.padding_right is not None:
            entry["padding_right"] = section.padding_right
        if section.padding_bottom is not None:
            entry["padding_bottom"] = section.padding_bottom
        if section.padding_left is not None:
            entry["padding_left"] = section.padding_left
        if section.item_spacing is not None:
            entry["item_spacing"] = section.item_spacing
        if section.spacing_after is not None:
            entry["spacing_after"] = section.spacing_after
        if entry:
            result[section.node_id] = entry
    return result


def _section_bottom(section: EmailSection) -> float | None:
    """Get the bottom y-coordinate of a section."""
    if section.y_position is None or section.height is None:
        return None
    return section.y_position + section.height


# ── Nested-card surface detection (Phase 50.4, Gap 10) ──


def _detect_inner_bg(
    node: DesignNode,
    *,
    container_bg: str | None,
    global_design_image: bytes | None,
) -> tuple[str | None, float | None]:
    """Detect the section's own card-surface bg + radius distinct from the wrapper.

    Two paths:

    * **Direct**: ``node.fill_color`` is non-default and differs from
      ``container_bg`` — the section carries its own fill (e.g. white card on
      lime wrapper).
    * **Indirect (PNG-sampled)**: ``node.fill_color`` is empty but the global
      design PNG shows a perceptually distinct color at the section's interior
      centroid versus the wrapper bg. Used when the design tool stores the
      card background as a child rectangle the analyzer hasn't promoted into
      ``fill_color``.

    Returns ``(inner_bg, inner_radius)`` or ``(None, None)`` when no nested
    card is detected. Gated by ``DESIGN_SYNC__NESTED_CARD_DETECTION_ENABLED``.
    """
    cfg = get_settings().design_sync
    if not cfg.nested_card_detection_enabled:
        return None, None

    # Nested-card detection is only meaningful when the section sits inside
    # a coloured wrapper (``container_bg``). Without one, the section's own
    # ``bg_color`` keeps the Phase 49 contract of mapping to ``_outer``.
    if container_bg is None:
        return None, None

    # Direct: section has its own fill that differs from the container.
    if node.fill_color and _hex_max_channel_delta(node.fill_color, container_bg) > 0:
        return node.fill_color, _resolve_corner_radius(node)

    # Indirect: PNG centroid sample — covers the case where the section's own
    # fill is empty but the rendered design shows a distinct surface colour.
    if global_design_image is not None:
        sampled = _sample_section_centroid(node, global_design_image)
        if sampled and _hex_max_channel_delta(sampled, container_bg) > (
            NESTED_CARD_PERCEPTUAL_THRESHOLD
        ):
            return sampled, _resolve_corner_radius(node)

    return None, None


def _resolve_corner_radius(node: DesignNode) -> float | None:
    """Return the section's corner radius, preferring the per-corner max."""
    if node.corner_radii:
        return max(node.corner_radii)
    return node.corner_radius


def _sample_section_centroid(node: DesignNode, image_bytes: bytes) -> str | None:
    """Sample the dominant color of a 5x5 block at the section's geometric centre."""
    if (
        node.x is None
        or node.y is None
        or node.width is None
        or node.height is None
        or node.width <= 0
        or node.height <= 0
    ):
        return None
    cx = int(node.x + node.width / 2)
    cy = int(node.y + node.height / 2)

    from app.design_sync.image_sampler import sample_centroid_color

    return sample_centroid_color(image_bytes, cx=cx, cy=cy)


def _hex_max_channel_delta(hex_a: str, hex_b: str) -> int:
    """Return the maximum per-channel RGB delta between two hex colors."""
    ar, ag, ab = _hex_to_rgb(hex_a)
    br, bg, bb = _hex_to_rgb(hex_b)
    return max(abs(ar - br), abs(ag - bg), abs(ab - bb))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
