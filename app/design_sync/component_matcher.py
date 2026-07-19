"""Match layout-analyzed EmailSections to pre-built component slugs and extract slot fills."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeGuard

from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ColumnLayout,
    ContentGroup,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)

if TYPE_CHECKING:
    from app.design_sync.protocol import ExtractedGradient
    from app.projects.design_system import DesignSystem

logger = get_logger(__name__)


@dataclass(frozen=True)
class SlotFill:
    """A value to inject into a component template slot."""

    slot_id: str
    value: str
    slot_type: str = "text"  # "text" | "image" | "cta" | "attr" | "composite"
    attr_overrides: dict[str, str] = field(default_factory=dict[str, str])
    # Extra ``<tr>`` rows to splice around this slot's own row at render time.
    # F1 (RC-F1): a multi-image section fills its seed's single image slot with
    # the largest image and carries the remaining images here as ready-to-inject
    # ``<tr><td><img>`` rows — those preceding the primary in tree order in
    # ``stacked_before`` (rendered above), those following in ``stacked_after``
    # (below); consumed by ``_fill_image_slot``. F6 (RC-F6): the text-block / hero
    # heading fill carries pre-heading eyebrow ``<tr><td data-node-id>`` rows in
    # ``stacked_before``, spliced above the heading row by ``_fill_text_slot``.
    # Empty for every other fill. Render-time only (never serialised) — no bridge sites.
    stacked_before: str = ""
    stacked_after: str = ""
    # 51.1 composite-slot infra: set only when ``slot_type == "composite"``. Carries a
    # rendered sub-component (e.g. own-row CTA) spliced as its own ``<tr>`` after the
    # reference slot's row. LAST field so the positional rebuild in ``tree_bridge``
    # (image-alt only) is unaffected. Render-time only — never serialised (§NOTES A).
    composite: CompositeSlot | None = None


@dataclass(frozen=True)
class CompositeSlot:
    """A rendered sub-component spliced as its own row (51.1 composite-slot infra).

    ``children`` are rendered in order and joined by ``child_separator``, then
    wrapped in one centered ``<tr><td>`` row. A child whose ``slot_type`` is
    ``"composite"`` re-enters :func:`render_composite` at ``depth+1`` (recursion is
    inherent, depth-capped); a terminal child contributes its ``value``. The
    own-row CTA (51.1's first consumer) exercises depth 1 with terminal
    pre-built ``<a>`` anchor children.
    """

    children: tuple[SlotFill, ...]
    after_slot: str  # data-slot id whose <tr> the composite splices after
    cell_style: str = ""  # inline style for the wrapping <td>
    align: str = "center"
    child_separator: str = ""  # joins rendered children (own-row CTA uses "\n")


@dataclass(frozen=True)
class TokenOverride:
    """A design token override for inline style replacement."""

    css_property: str
    target_class: str  # CSS class on the target element (e.g. "textblock-heading")
    value: str


@dataclass(frozen=True)
class ComponentMatch:
    """Result of matching an EmailSection to a component template."""

    section_idx: int
    section: EmailSection
    component_slug: str
    slot_fills: list[SlotFill]
    token_overrides: list[TokenOverride]
    spacing_after: float | None = None
    confidence: float = 1.0
    mjml_template: str | None = None


def match_section(
    section: EmailSection,
    idx: int,
    *,
    container_width: int = 600,
    image_urls: dict[str, str] | None = None,
    global_design_image: bytes | None = None,  # noqa: ARG001  Phase 50.1 pass-through; consumed in 50.5
    gradients: list[ExtractedGradient] | None = None,
    design_system: DesignSystem | None = None,
) -> ComponentMatch:
    """Match a single EmailSection to a component slug with slot fills."""
    # Column layouts override section type for CONTENT sections
    if section.column_layout != ColumnLayout.SINGLE:
        slug = _match_column_layout(section)
        fills = _build_column_fills(section, image_urls=image_urls)
        overrides = _build_token_overrides(section, gradients=gradients)
        return ComponentMatch(
            section_idx=idx,
            section=section,
            component_slug=slug,
            slot_fills=fills,
            token_overrides=overrides,
            spacing_after=section.spacing_after,
        )

    slug, confidence = _match_by_type(section)
    fills = _build_slot_fills(
        slug, section, container_width, image_urls=image_urls, design_system=design_system
    )
    overrides = _build_token_overrides(section, gradients=gradients)

    return ComponentMatch(
        section_idx=idx,
        section=section,
        component_slug=slug,
        slot_fills=fills,
        token_overrides=overrides,
        spacing_after=section.spacing_after,
        confidence=confidence,
    )


def match_all(
    sections: list[EmailSection],
    *,
    container_width: int = 600,
    image_urls: dict[str, str] | None = None,
    global_design_image: bytes | None = None,
    gradients: list[ExtractedGradient] | None = None,
    design_system: DesignSystem | None = None,
) -> list[ComponentMatch]:
    """Match all sections in order."""
    return [
        match_section(
            section,
            idx,
            container_width=container_width,
            image_urls=image_urls,
            global_design_image=global_design_image,
            gradients=gradients,
            design_system=design_system,
        )
        for idx, section in enumerate(sections)
    ]


async def match_section_with_vlm_fallback(
    section: EmailSection,
    idx: int,
    *,
    container_width: int = 600,
    image_urls: dict[str, str] | None = None,
    screenshot: bytes | None = None,
    candidate_types: list[str] | None = None,
    gradients: list[ExtractedGradient] | None = None,
    design_system: DesignSystem | None = None,
) -> ComponentMatch:
    """Match section with optional VLM fallback for low-confidence matches.

    Wraps :func:`match_section` and, when the heuristic confidence falls below
    ``low_match_confidence_threshold``, calls the VLM classifier to attempt a
    better classification from the section screenshot.

    Args:
        section: The email section to match.
        idx: Section index in the email.
        container_width: Container width for slot fill calculation.
        image_urls: Mapping of node IDs to image URLs.
        screenshot: PNG bytes of the section screenshot (required for VLM).
        candidate_types: Component type slugs from the manifest (required for VLM).
        gradients: Extracted gradients for ``gradient_ref`` resolution (53.3b).
        design_system: Project DesignSystem threaded to slot builders (G8 / 51.6).

    Returns:
        ComponentMatch — either the original heuristic match or a VLM-improved one.
    """
    from app.core.config import get_settings
    from app.design_sync.tuning import LOW_MATCH_CONFIDENCE_THRESHOLD

    match = match_section(
        section,
        idx,
        container_width=container_width,
        image_urls=image_urls,
        gradients=gradients,
        design_system=design_system,
    )

    threshold = LOW_MATCH_CONFIDENCE_THRESHOLD
    settings = get_settings()

    if (
        match.confidence >= threshold
        or screenshot is None
        or candidate_types is None
        or not settings.design_sync.vlm_fallback_enabled
    ):
        return match

    from app.design_sync.vlm_classifier import vlm_classify_section

    vlm_result = await vlm_classify_section(screenshot, candidate_types)
    if vlm_result is None:
        return match

    # Rebuild match with VLM-classified component type
    new_slug = vlm_result.component_type
    fills = _build_slot_fills(
        new_slug, section, container_width, image_urls=image_urls, design_system=design_system
    )
    overrides = _build_token_overrides(section, gradients=gradients)

    return ComponentMatch(
        section_idx=idx,
        section=section,
        component_slug=new_slug,
        slot_fills=fills,
        token_overrides=overrides,
        spacing_after=section.spacing_after,
        confidence=vlm_result.confidence,
    )


# ── Private helpers ──


def _match_column_layout(section: EmailSection) -> str:
    """Map ColumnLayout to a column component slug."""
    mapping = {
        ColumnLayout.TWO_COLUMN: "column-layout-2",
        ColumnLayout.THREE_COLUMN: "column-layout-3",
        ColumnLayout.MULTI_COLUMN: "column-layout-4",
    }
    return mapping.get(section.column_layout, "column-layout-2")


def _match_by_type(section: EmailSection) -> tuple[str, float]:
    """Map EmailSectionType to component slug + confidence."""
    st = section.section_type
    has_images = bool(section.images)
    has_texts = bool(section.texts)
    has_buttons = bool(section.buttons)
    has_headings = any(t.is_heading for t in section.texts)

    if st == EmailSectionType.PREHEADER:
        return "preheader", 1.0

    if st == EmailSectionType.HEADER:
        if has_images:
            return "logo-header", 1.0
        if len(section.texts) > 2:
            return "email-header", 1.0
        return "email-header", 0.9

    if st == EmailSectionType.HERO:
        if has_images and (has_texts or has_buttons):
            # Subtitle+title pair: 2+ headings -> hero-text (richer slots)
            heading_count = sum(1 for t in section.texts if t.is_heading)
            if heading_count >= 2:
                return "hero-text", 1.0
            return "hero-block", 1.0
        if has_images:
            return "full-width-image", 1.0
        return "hero-block", 0.8

    if st == EmailSectionType.CONTENT:
        slug, confidence = _score_candidates(
            section, has_images, has_texts, has_buttons, has_headings
        )
        ext_slug, ext_confidence = _score_extended_candidates(section, has_texts)
        # Extended types use specific content signals (regex, aspect ratio,
        # quote chars) that are always more specific than base heuristics.
        if ext_confidence > 0:
            return ext_slug, ext_confidence
        return slug, confidence

    if st == EmailSectionType.CTA:
        # Two or more buttons -> dual-CTA seed (primary + secondary slots).
        # B8: a single button keeps the standalone cta-button seed.
        if len(section.buttons) >= 2:
            return "cta-pair", 1.0
        return "cta-button", 1.0

    if st == EmailSectionType.FOOTER:
        return "email-footer", 1.0

    if st == EmailSectionType.SOCIAL:
        return "social-icons", 1.0

    if st == EmailSectionType.DIVIDER:
        return "divider", 1.0

    if st == EmailSectionType.SPACER:
        return "spacer", 1.0

    if st == EmailSectionType.NAV:
        # Vertical nav: stacked items (no column groups) -> nav-hamburger
        if not section.column_groups and len(section.texts) >= 3:
            return "nav-hamburger", 0.95
        return "navigation-bar", 1.0

    # UNKNOWN fallback
    if has_images and has_texts:
        return "article-card", 0.7
    if has_images:
        return "image-block", 0.7
    return "text-block", 0.7


def _all_images_are_icons(section: EmailSection, threshold: float = 30.0) -> bool:
    """Check if all images in a section are tiny icons (<= threshold px)."""
    if not section.images:
        return False
    return all(
        (img.width is not None and img.width <= threshold)
        and (img.height is not None and img.height <= threshold)
        for img in section.images
    )


def _score_candidates(
    section: EmailSection,
    has_images: bool,
    has_texts: bool,
    _has_buttons: bool,
    _has_headings: bool,
) -> tuple[str, float]:
    """Score all candidate components and return the best match.

    Replaces the first-match ``_match_content`` with multi-candidate scoring
    so that product grids, image galleries, and category navs are correctly
    distinguished from generic article-cards.
    """
    candidates: list[tuple[str, float]] = []

    img_count = len(section.images)
    text_count = len(section.texts)
    col_groups = section.column_groups or []
    groups_with_mixed = sum(1 for g in col_groups if g.images and g.texts)

    # card-with-N-children (51.2 / Rule 1 + Rule 11): a physical card frame
    # (white fill + corner radius) whose heterogeneous children — logo, identity
    # TEXT, barcode, shape — must collapse to ONE rounded white table with the
    # children stacked as rows at the dominant image width, not a 3-across image
    # gallery that drops the TEXT. Probe-proven unique to the LEGO membership
    # card across the corpus; scored above image-gallery/editorial-2. Hosted by
    # the ``td`` (Table Cell) seed — a clean single ``content`` slot, no seed-
    # default mustache (``cell`` leaves ``{{ align || … }}`` unresolved) — no new seed.
    if (
        section.is_physical_card_surface
        and section.inner_bg
        and section.images
        and section.texts
        and section.column_layout == ColumnLayout.SINGLE
    ):
        candidates.append(("td", 0.99))

    # product-grid: 2+ column groups each with image + text
    if len(col_groups) >= 2 and groups_with_mixed >= 2:
        candidates.append(("product-grid", 0.95))

    # navigation-bar: tiny icons paired with text
    if has_images and has_texts and _all_images_are_icons(section):
        candidates.append(("navigation-bar", 0.9))

    # image-gallery: 3+ images, minimal text
    if img_count >= 3 and text_count <= 1:
        candidates.append(("image-gallery", 0.88))

    # image-grid: exactly 2 images, minimal text
    if img_count == 2 and text_count <= 1:
        candidates.append(("image-grid", 0.85))

    # editorial-2: needs genuine two-column structure, not just one col_group
    # with mixed content. Two signals: (a) >=2 col_groups each contributing content,
    # or (b) 1 col_group that is narrow enough to be a real column (<70% of section width).
    if len(col_groups) >= 2:
        groups_with_content = sum(1 for g in col_groups if (g.images or g.texts))
        if groups_with_content >= 2:
            candidates.append(("editorial-2", 0.92))
    elif len(col_groups) == 1 and col_groups[0].images and col_groups[0].texts:
        cg = col_groups[0]
        section_w = section.width if section.width is not None else 600
        cg_is_narrow = cg.width is None or cg.width < section_w * 0.7
        if cg_is_narrow:
            candidates.append(("editorial-2", 0.92))

    # article-card: 1 image + text, single column (no multi-column groups)
    if img_count == 1 and text_count >= 1 and len(col_groups) <= 1:
        candidates.append(("article-card", 0.9))

    # category-nav: 3+ short texts, few images, no headings (more specific than text-block)
    has_any_heading = any(t.is_heading for t in section.texts)
    short_texts = [t for t in section.texts if len(t.content) < 20]
    is_category_nav = len(short_texts) >= 3 and img_count <= 1 and not has_any_heading
    if is_category_nav:
        candidates.append(("category-nav", 0.7))

    # full-width-image vs image-block: differentiate by image width relative to section
    if img_count == 1 and not has_texts:
        img = section.images[0]
        section_w = section.width if section.width is not None else 600
        if img.width is not None and img.width >= section_w * 0.8:
            candidates.append(("full-width-image", 1.0))
        else:
            candidates.append(("image-block", 1.0))

    # text-block: generic text-only fallback (skip when category-nav is more specific)
    if has_texts and not has_images and not is_category_nav:
        candidates.append(("text-block", 1.0))

    if not candidates:
        return ("text-block", 0.5) if has_texts else ("spacer", 0.5)

    # Highest score wins
    candidates.sort(key=lambda c: c[1], reverse=True)
    best_slug, best_score = candidates[0]

    if best_score < 0.5:
        return ("text-block", 0.5)

    return (best_slug, best_score)


# ── Extended component detection patterns ──

_DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2})\b",
    re.IGNORECASE,
)
_EVENT_KEYWORD_PATTERN = re.compile(
    r"\b(?:date|time|location|venue|where|when|address|doors?\s+open)\s*:",
    re.IGNORECASE,
)
_TIME_OF_DAY_PATTERN = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\b")


def _score_extended_candidates(
    section: EmailSection,
    has_texts: bool,
) -> tuple[str, float]:
    """Score extended component types that have a fill builder.

    Returns the best (slug, confidence) among event-card and col-icon — the only
    extended types with a ``_build_slot_fills`` builder. Returns
    ``("text-block", 0.0)`` when nothing matches so the caller can safely compare
    against the base scorer.

    F4d (RC-F4) dropped countdown-timer, testimonial, pricing-table,
    video-placeholder, and zigzag-alternating: they scored here but had no
    builder, so a match rendered only seed placeholder text (see
    ``.agents/deferred-items.json``).
    """
    candidates: list[tuple[str, float]] = []

    texts = section.texts
    images = section.images
    all_text = " ".join(t.content for t in texts)

    # event-card: structured event information (date/time/location patterns)
    # False-positive gate: real event cards are text-dense (no hero image) and
    # carry a single RSVP CTA. A hero-style section with multiple buttons
    # (e.g. Mammut "DUVET DAY" with 2 ghost CTAs) must NOT match event-card.
    has_large_image = any(img.width is not None and img.width >= 200 for img in images)
    single_cta = len(section.buttons) <= 1
    event_shape_ok = not has_large_image and single_cta
    # Path A: explicit date pattern — works with or without images
    if event_shape_ok and has_texts and _DATE_PATTERN.search(all_text):
        candidates.append(("event-card", 0.85))
    # Path B: keyword-labeled event details (3+ short lines with event keywords)
    elif event_shape_ok and has_texts and len(texts) >= 3:
        short_texts = [t for t in texts if len(t.content) < 80]
        if len(short_texts) >= 3:
            keyword_hits = sum(
                1
                for t in short_texts
                if _EVENT_KEYWORD_PATTERN.search(t.content)
                or _TIME_OF_DAY_PATTERN.search(t.content)
            )
            if keyword_hits >= 2:
                candidates.append(("event-card", 0.83))

    # col-icon: small icon image + short text group (icon-driven content block)
    if len(images) == 1 and has_texts and 1 <= len(texts) <= 3:
        img = images[0]
        is_icon_sized = (
            img.width is not None
            and img.width <= 64
            and img.height is not None
            and img.height <= 64
        )
        if is_icon_sized:
            candidates.append(("col-icon", 0.92))

    if not candidates:
        return ("text-block", 0.0)

    candidates.sort(key=lambda c: c[1], reverse=True)
    return candidates[0]


def _build_slot_fills(
    slug: str,
    section: EmailSection,
    container_width: int,
    *,
    image_urls: dict[str, str] | None = None,
    design_system: DesignSystem | None = None,
) -> list[SlotFill]:
    """Build slot fills for a given component slug from section content."""
    builders: dict[str, _SlotBuilder] = {
        "preheader": _fills_preheader,
        "email-header": _fills_email_header,
        "logo-header": _fills_logo_header,
        "hero-block": _fills_hero,
        "full-width-image": _fills_full_width_image,
        "text-block": _fills_text_block,
        "article-card": _fills_article_card,
        "image-block": _fills_image_block,
        "image-grid": _fills_image_grid,
        "product-grid": _fills_product_grid,
        "category-nav": _fills_category_nav,
        "image-gallery": _fills_image_gallery,
        "td": _fills_card,  # 51.2 physical card-with-N-children (Rule 1 + 11)
        "cta-button": _fills_cta,
        "email-footer": _fills_footer,
        "spacer": _fills_spacer,
        "social-icons": _fills_social,
        "divider": _fills_divider,
        "navigation-bar": _fills_nav,
        "hero-text": _fills_hero,
        "editorial-2": _fills_article_card,
        "nav-hamburger": _fills_nav,
        # ── Batch A: already had data-slot ──
        "banner": _fills_text_block,
        "col-gutter": _fills_text_block,
        "article-reverse": _fills_article_card,
        # ── Batch C: editorial family ──
        "editorial-1": _fills_article_card,
        "editorial-3": _fills_article_card,
        "editorial-4": _fills_article_card,
        "editorial-5": _fills_article_card,
        # ── Batch D: article variants ──
        "article-2": _fills_article_card,
        "article-3": _fills_article_card,
        "article-4": _fills_article_card,
        # ── Batch E: hero variant ──
        "hero-2cta": _fills_hero,
        # ── Batch F: button/CTA components ──
        "button": _fills_cta,
        "button-filled": _fills_cta,
        "button-ghost": _fills_cta,
        "button-responsive": _fills_cta,
        "cta": _fills_cta,
        "cta-pair": _fills_cta,
        # ── Batch G: content components ──
        "heading": _fills_text_block,
        "paragraph": _fills_text_block,
        "icon": _fills_text_block,
        "list": _fills_text_block,
        "product-card": _fills_article_card,
        "product-showcase": _fills_image_gallery,
        # Event-card family — all 3 variants share the same slot shape
        # (event_name, date, [location], [description], cta_url, cta_text,
        # plus optional image_url on the banner variant).
        "event-card": _fills_event_card,
        "event-card-minimal": _fills_event_card,
        "event-card-banner": _fills_event_card,
        # ── Batch H: footer family ──
        "footer": _fills_footer,
        "footer-menu": _fills_nav,
        "footer-social": _fills_social,
        "footer-unsub": _fills_text_block,
        # ── Batch I: structure ──
        "col-icon": _fills_col_icon,
        "header": _fills_logo_header,
        "app-store": _fills_text_block,
        "section": _fills_image_block,
        # ── Former Tier 3 with fillable content ──
        "image": _fills_image_block,
        "image-responsive": _fills_image_block,
        "text-link": _fills_cta,
        "font-inline": _fills_text_block,
    }
    builder = builders.get(slug)
    if builder:
        fills = builder(
            section,
            container_width,
            image_urls=image_urls,
            slug=slug,
            design_system=design_system,
        )
        _log_default_fills(slug, section, fills)
        return fills
    return []


def _log_default_fills(
    slug: str,
    section: EmailSection,
    fills: list[SlotFill],
) -> None:
    """Log warning when slot fills use default/placeholder values."""
    for fill in fills:
        if _is_placeholder(fill.value):
            logger.warning(
                "design_sync.slot_fill.default_used",
                slot_name=fill.slot_id,
                component_slug=slug,
                section_node_id=section.node_id,
            )


# Type alias for slot builder functions
_SlotBuilder = Callable[..., list[SlotFill]]


def _first_heading(texts: list[TextBlock]) -> TextBlock | None:
    """Return the first heading text block."""
    return next((t for t in texts if t.is_heading), None)


def _body_texts(texts: list[TextBlock]) -> list[TextBlock]:
    """Return all non-heading text blocks."""
    return [t for t in texts if not t.is_heading]


def _safe_text(text: str) -> str:
    """HTML-escape text content."""
    return html.escape(text, quote=False)


# Hard line separators Figma stores inside a single TEXT node: LF, CRLF, and the
# Unicode LINE/PARAGRAPH separators (U+2028/U+2029). The c7 spec value ``+260``
# cell uses U+2028, so a ``\n``-only replace would silently drop it.
_LINE_SEP_RE = re.compile("\r\n|[\n\r\u2028\u2029]")


def _multiline_to_br(text: str) -> str:
    r"""HTML-escape, then convert hard line breaks to ``<br />`` (Track G · G7 / 51.5).

    Figma encodes stacked value/label text (``617\nPieces``) and 2-line labels
    as ONE TEXT node with a hard separator + uniform font; ``_safe_text`` alone
    leaves the separator, which collapses to whitespace in email clients. Escape
    runs first so any markup in the content is neutralised before the trusted
    ``<br />`` is inserted. The 51.5 "multi-line splitter" reduces to this
    normalization — the data carries no per-line font weight, so no node split.
    """
    return _LINE_SEP_RE.sub("<br />", html.escape(text, quote=False))


def _headings_from_groups(groups: list[ContentGroup]) -> list[TextBlock]:
    """Collect heading texts from content groups."""
    result: list[TextBlock] = []
    for g in groups:
        for t in g.texts:
            if t.role_hint == "heading" or t.is_heading:
                result.append(t)
    return result


def _bodies_from_groups(groups: list[ContentGroup]) -> list[TextBlock]:
    """Collect body texts from content groups, skipping placeholders."""
    result: list[TextBlock] = []
    for g in groups:
        for t in g.texts:
            if t.role_hint != "heading" and not t.is_heading and not _is_placeholder(t.content):
                result.append(t)
    return result


_PLACEHOLDER_PATTERNS = re.compile(
    r"(?i)(image caption|describe\s+the\s+image|placeholder|lorem ipsum"
    r"|add\s+your\s+text|your\s+text\s+here|insert\s+text)"
)


def _is_placeholder(text: str) -> bool:
    """Check if text looks like placeholder/template text."""
    return bool(_PLACEHOLDER_PATTERNS.search(text))


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


def _is_white_hex(color: str | None) -> bool:
    """True when *color* is pure white (``#fff``/``#ffffff``), case-insensitive."""
    if not color or not _HEX_COLOR_RE.match(color):
        return False
    h = color.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h == "ffffff"


# Allowlists for typographic enum properties (Phase 52.4). Values outside the
# set are dropped so a malformed ``text_transform``/``text_decoration`` from the
# design can never reach the rendered CSS (defence-in-depth against injection).
_ALLOWED_TEXT_TRANSFORM = frozenset({"uppercase", "lowercase", "capitalize", "none"})
_ALLOWED_TEXT_DECORATION = frozenset({"underline", "line-through", "none", "overline"})


def _safe_color(color: str | None, fallback: str = "#333333") -> str:
    """Validate hex color, returning fallback if malformed."""
    if not color:
        return fallback
    if _HEX_COLOR_RE.match(color):
        return color
    return fallback


def _safe_url(url: str | None) -> str:
    """Validate and return URL, defaulting to '#' for invalid/missing."""
    if not url:
        return "#"
    stripped = url.strip()
    if stripped.startswith(("http://", "https://", "mailto:", "tel:", "/")):
        return stripped
    return "#"


_ALLOWED_TEXT_ALIGN = frozenset({"left", "center", "right", "justify"})


def _column_text_row(text: TextBlock, *, is_heading: bool) -> str:
    """Build a column-text ``<tr><td>…</td></tr>`` row from design properties.

    Shared by ``_build_column_fill_html`` (real fixtures) and the round-robin
    fallback in ``_build_column_fills`` so the two cannot drift. Mirrors the
    validation in ``_typography_overrides`` byte-for-byte (font-weight ``str``,
    line-height ``round(px)``, letter-spacing ``{:.2f}px`` skipping ``0.0``,
    transform/decoration/align ``.lower()`` + allowlist, color ``_safe_color``).
    ``font-family`` is passed through unvalidated — matching the existing
    override path (``_build_token_overrides`` line ~1542) which also emits it
    raw — with only a web-safe fallback appended. Falls back to the pre-52.x
    hardcoded heading/body defaults when a property is absent.
    """
    decls = ["padding:0 0 8px"]

    # font-family — design value with a web-safe fallback appended, else Arial.
    # Escaped (quote=True) so a font name can't break out of the style attr —
    # the override path is escaped equivalently by the renderer (_replace_heading_font).
    if text.font_family:
        family = html.escape(text.font_family, quote=True)
        if "," not in family:
            family = f"{family},sans-serif"
        decls.append(f"font-family:{family}")
    else:
        decls.append("font-family:Arial,sans-serif")

    # font-size — keep the 18/14 heading/body fallback.
    size = int(text.font_size) if text.font_size else (18 if is_heading else 14)
    decls.append(f"font-size:{size}px")

    # font-weight — design value, else heading=bold / body=normal.
    if text.font_weight is not None:
        decls.append(f"font-weight:{text.font_weight}")
    elif is_heading:
        decls.append("font-weight:bold")

    decls.append(f"color:{_safe_color(text.text_color)}")

    # line-height — design value as round(px), else unitless 1.3/1.5 default.
    if text.line_height is not None:
        decls.append(f"line-height:{round(text.line_height)}px")
    else:
        decls.append(f"line-height:{'1.3' if is_heading else '1.5'}")

    # text-align — only the four valid CSS keywords.
    align = text.text_align.lower() if text.text_align else None
    if align in _ALLOWED_TEXT_ALIGN:
        decls.append(f"text-align:{align}")

    # letter-spacing — skip the 0.0 no-op.
    if text.letter_spacing not in (None, 0.0):
        decls.append(f"letter-spacing:{text.letter_spacing:.2f}px")

    # text-transform / text-decoration — allowlist-validated.
    if text.text_transform is not None:
        tt = text.text_transform.lower()
        if tt in _ALLOWED_TEXT_TRANSFORM:
            decls.append(f"text-transform:{tt}")

    if text.text_decoration is not None:
        td = text.text_decoration.lower()
        if td in _ALLOWED_TEXT_DECORATION:
            decls.append(f"text-decoration:{td}")

    decls.append("mso-line-height-rule:exactly")
    style = ";".join(decls) + ";"
    return f'<tr><td style="{style}">{_multiline_to_br(text.content)}</td></tr>'


def _cta_label_typography(btn: ButtonElement) -> str:
    """Build font-family/size/weight CSS for a CTA label from design typography.

    Phase 52.4b — sources the button label's font from its design ``TextBlock``,
    falling back to the pre-52.4b hardcoded ``14px``/``bold`` when a property is
    absent. Mirrors ``_column_text_row``'s validation: font-family is
    ``html.escape``d (quote=True) with a web-safe fallback appended so a font
    name cannot break out of the style attr; font-size is coerced to ``int``;
    font-weight is emitted raw.
    """
    decls: list[str] = []
    if btn.font_family:
        family = html.escape(btn.font_family, quote=True)
        if "," not in family:
            family = f"{family},sans-serif"
        decls.append(f"font-family:{family}")
    size = int(btn.font_size) if btn.font_size else 14
    decls.append(f"font-size:{size}px")
    decls.append(
        f"font-weight:{btn.font_weight}" if btn.font_weight is not None else "font-weight:bold"
    )
    return ";".join(decls) + ";"


def _cta_padding_css(btn: ButtonElement) -> str:
    """Build the CTA ``<a>`` padding shorthand from designed box geometry (G3).

    Prefers the button frame's captured auto-layout ``padding_*`` (collapsing to
    the 2-value shorthand when symmetric, else the 4-value form). When padding is
    absent, derives a vertical value from the button height (SPECULATIVE — no
    corpus fixture lacks padding; covered by a synthetic unit test only), and
    finally falls back to the pre-G3 ``10px 24px`` hardcode.
    """
    pt, pr, pb, pl = btn.padding_top, btn.padding_right, btn.padding_bottom, btn.padding_left
    if pt is not None and pr is not None and pb is not None and pl is not None:
        if pt == pb and pl == pr:
            return f"{pt:.0f}px" if pt == pl else f"{pt:.0f}px {pr:.0f}px"
        return f"{pt:.0f}px {pr:.0f}px {pb:.0f}px {pl:.0f}px"
    if btn.height is not None and btn.font_size is not None:
        v = max(0, round((btn.height - btn.font_size * 1.2) / 2))
        return f"{v}px 24px"
    return "10px 24px"


def _cta_radius_css(btn: ButtonElement) -> str:
    """Build the CTA ``<a>`` border-radius CSS from designed corner geometry (G5).

    Emits the four per-corner longhands when the button frame carries an
    asymmetric ``corner_radius_spec.per_corner`` (Rule 8 — e.g. r12/r18 pills),
    else the scalar ``border-radius`` shorthand. The scalar branch is
    byte-identical to the pre-G5 inline emission (``{r:.0f}px``, legacy ``4``
    fallback when the radius is absent): every corpus button has
    ``corner_radii: null`` so the per-corner branch is defensive plumbing
    exercised only by synthetic tests. Mirrors the image per-corner emitter in
    ``_build_token_overrides`` (Rule 10) — same TL,TR,BR,BL order.
    """
    spec = getattr(btn, "corner_radius_spec", None)
    if spec is not None and spec.per_corner is not None:
        tl, tr, br, bl = spec.per_corner
        return (
            f"border-top-left-radius:{tl:.0f}px;"
            f"border-top-right-radius:{tr:.0f}px;"
            f"border-bottom-right-radius:{br:.0f}px;"
            f"border-bottom-left-radius:{bl:.0f}px"
        )
    r = btn.border_radius if btn.border_radius is not None else 4
    return f"border-radius:{r:.0f}px"


# Figma layer names that leak MJML/element internals as alt text (Phase 53 B5).
# These surface as meaningless screen-reader text (``mj-image, (mjml:mj-image),
# (type: logo)``) and ``mj-image`` is itself a G3-neg generic token.
_GENERIC_ALT_TOKENS = frozenset(
    {"mj-image", "mj-text", "image", "photo", "picture", "img", "frame", "banner"}
)
_FIGMA_NODE_ID_RE = re.compile(r"^\d+[:_]\d+")
# 53.5 — Figma auto-generated layer names ("Vector 3", "Ellipse 12", "Union").
# Rasterized standalone vectors carry these by default; they say nothing about
# the content and must fall back like the lone generic tokens above.
_FIGMA_AUTO_NAME_RE = re.compile(
    r"(?i)^(vector|line|ellipse|star|polygon|rectangle|boolean ?operation"
    r"|frame|group|instance|union|subtract|intersect|exclude)\s*\d*$"
)


def _is_descriptive_alt(name: str | None) -> bool:
    """True when a Figma layer name is usable as alt text (Phase 53 B5).

    Rejects the Mode E-alt leak: empty, a lone G3-neg generic token, a Figma
    auto-generated layer name ("Vector 3" — 53.5), MJML internals
    (``(mjml:`` / ``(type:``), or a raw Figma node-id. A name that passes is
    safe to emit verbatim and clears the G3-neg conformance gate.
    """
    stripped = (name or "").strip()
    lowered = stripped.lower()
    return bool(
        stripped
        and lowered not in _GENERIC_ALT_TOKENS
        and "(mjml:" not in lowered
        and "(type:" not in lowered
        and not _FIGMA_NODE_ID_RE.match(stripped)
        and not _FIGMA_AUTO_NAME_RE.match(stripped)
    )


def _derive_image_alt(img: ImagePlaceholder) -> str:
    """Derive accessible alt text for a converter image (Phase 53 B5).

    Stops the Figma layer-name leak (Mode E-alt): the raw ``node_name`` carries
    MJML internals like ``mj-image, (mjml:mj-image), (type: logo)``. A
    descriptive ``node_name`` is kept verbatim; a non-descriptive one falls back
    to a generic but gate-clean multi-word placeholder. Never returns an empty
    string or a lone generic token, so the G3-neg golden-conformance gate stays
    green. True per-image semantic alt + decorative ``alt=""`` are deferred to
    RC-E (ingest signal) — see ``.agents/plans/53-b5-alt-derivation-decision.md``.
    """
    name = (img.node_name or "").strip()
    if _is_descriptive_alt(name):
        return name
    return "Company logo" if "logo" in name.lower() else "Content image"


# F3 (RC-F3): a column image at or below this design width never stretches to
# fill its column — it renders at natural size (the button-icon precedent).
_ICON_MAX_WIDTH_PX = 64
# An image at least this fraction of its column's width is treated as
# column-filling and keeps the responsive ``width:100%`` behaviour.
_COLUMN_FILL_RATIO = 0.9


def _image_fills_column(img_width: float | None, column_width: float | None) -> bool:
    """Whether a column image should keep the responsive ``width:100%`` fill (F3).

    A column-filling image (as wide as its column — the ``bannerimg`` case)
    keeps ``width:100%``. A small icon/decoration (<=64px, or narrower than 90%
    of its column) is instead pinned to its design width so it renders at
    natural size rather than ballooning to the column edge (RC-F3). Degrades to
    the pre-F3 responsive default when the design width is unknown.
    """
    if img_width is None:
        return True
    if img_width <= _ICON_MAX_WIDTH_PX:
        return False
    if column_width is None:
        return True
    return img_width >= _COLUMN_FILL_RATIO * column_width


def _column_image_row(
    img: ImagePlaceholder,
    image_urls: dict[str, str] | None,
    *,
    column_width: float | None = None,
) -> str:
    """Wrap a column image in its own ``<tr><td>`` row (Phase 53 B2).

    Shared by ``_build_column_fill_html`` and the round-robin fallback in
    ``_build_column_fills`` so the two builders emit byte-identical image markup
    and cannot drift. A column-filling image keeps the responsive ``width:100%``
    fill; a small icon/decoration is pinned to its design width (+ ``max-width``
    clamp) so it renders at natural size instead of filling the column (F3,
    RC-F3).
    """
    url = _resolve_image_url(img.node_id, image_urls)
    if img.width is None or _image_fills_column(img.width, column_width):
        style = "display:block;width:100%;height:auto;border:0;"
        width_attr = ""
    else:
        w = int(img.width)
        style = f"display:block;width:{w}px;max-width:{w}px;height:auto;border:0;"
        width_attr = f' width="{w}"'
    tag = (
        f'<img src="{html.escape(url)}" '
        f'alt="{html.escape(_derive_image_alt(img))}"{width_attr} '
        f'style="{style}" />'
    )
    return f"<tr><td>{tag}</td></tr>"


def _column_cta_row(btn: ButtonElement) -> str:
    """Wrap a column CTA ``<a>`` in its own ``<tr><td>`` row (Phase 53 B2).

    The anchor markup (fill/text color, radius, stroke, design-sourced label
    typography) is unchanged from the pre-B2 bare ``<a>`` — only the enclosing
    ``<tr><td>`` is new.
    """
    btn_url = html.escape(_safe_url(btn.url))
    bg = _safe_color(btn.fill_color, "#0066cc")
    txt_color = _safe_color(btn.text_color, "#ffffff")
    border_css = ""
    if btn.stroke_color and _HEX_COLOR_RE.match(btn.stroke_color):
        sw = f"{btn.stroke_weight:.0f}" if btn.stroke_weight else "1"
        border_css = f"border:{sw}px solid {btn.stroke_color};"
    anchor = (
        f'<a href="{btn_url}" style="display:inline-block;'
        f"padding:{_cta_padding_css(btn)};background-color:{bg};color:{txt_color};"
        f"text-decoration:none;{_cta_label_typography(btn)}"
        f'{_cta_radius_css(btn)};{border_css}">{_safe_text(btn.text)}</a>'
    )
    return f"<tr><td>{anchor}</td></tr>"


_MAX_COMPOSITE_DEPTH = 3


def render_composite(cs: CompositeSlot, depth: int = 1) -> str:
    """Render a composite slot's children into one centered ``<tr>`` row (51.1).

    Recursion is inherent: a child with ``slot_type == "composite"`` re-enters at
    ``depth+1``, capped at ``_MAX_COMPOSITE_DEPTH``. Own-row CTA (51.1's first
    consumer) exercises depth 1 only — children are terminal text fills carrying
    pre-built ``<a>`` anchor HTML. General sub-template child rendering is deferred
    to 51.2. A mislabeled composite child with no payload (``composite is None``)
    degrades to its ``value`` rather than crashing.
    """
    if depth > _MAX_COMPOSITE_DEPTH:
        logger.warning("design_sync.composite.max_depth", depth=depth)
        return ""
    parts: list[str] = []
    for child in cs.children:
        if child.slot_type == "composite" and child.composite is not None:
            parts.append(render_composite(child.composite, depth + 1))
        else:
            parts.append(child.value)
    return (
        f'<tr><td align="{cs.align}" style="{cs.cell_style}">'
        f"{cs.child_separator.join(parts)}</td></tr>"
    )


def _wrap_column_table(rows: list[str]) -> str:
    """Wrap column rows in one inner ``<table>`` (Phase 53 B2).

    Fixes Mode B column collapse: the pre-B2 builders joined bare ``<img>`` /
    ``<a>`` and orphan ``<tr>`` text rows with newlines and **no** enclosing
    table, so the orphan rows collapsed in email clients. Each item is now a
    ``<tr><td>`` inside a single well-formed table. ``role="presentation"``
    satisfies the G1 conformance gate; ``width:100%`` preserves the pre-B2
    full-column image fill. Returns ``""`` for an empty column so the callers'
    truthiness guard still drops the slot.
    """
    if not rows:
        return ""
    inner = "\n".join(rows)
    return (
        '<table cellpadding="0" cellspacing="0" border="0" '
        f'role="presentation" style="width:100%;">\n{inner}\n</table>'
    )


def _ordered_column_elements(
    group: ColumnGroup,
) -> list[ImagePlaceholder | TextBlock | ButtonElement]:
    """Column content in design tree order (F10).

    ``content_order`` (node ids captured pre-order at group construction)
    interleaves the three category lists back into the design's vertical
    order — a tag pill (``ButtonElement``) above the heading, a product name
    above its spec-icon rows. Groups without it (older persisted documents,
    the content-group conversion) keep the legacy images->texts->buttons
    order, as do any ids the tuple doesn't cover (stable sort).
    """
    combined: list[ImagePlaceholder | TextBlock | ButtonElement] = [
        *group.images,
        *group.texts,
        *group.buttons,
    ]
    if not group.content_order:
        return combined
    position = {node_id: i for i, node_id in enumerate(group.content_order)}
    unknown = len(position)
    return sorted(combined, key=lambda element: position.get(element.node_id, unknown))


# Spec mini-table (G7 · 51.4, M4): a run of adjacent (icon <= this wide, label
# shorter than this) pairs inside a column renders as ONE centered horizontal row
# of ``[icon | value/label]`` cells instead of stacked full-width rows. Only c7's
# product-card spec runs match on the corpus (c8 grids are text-only, c9 icons are
# 34px) — see the G7 routing map.
_SPEC_ICON_MAX_WIDTH = 30
_SPEC_LABEL_MAX_CHARS = 40

_SpecPair = tuple[ImagePlaceholder, TextBlock]


def _is_spec_icon(el: ImagePlaceholder | TextBlock | ButtonElement) -> TypeGuard[ImagePlaceholder]:
    return (
        isinstance(el, ImagePlaceholder)
        and el.width is not None
        and el.width <= _SPEC_ICON_MAX_WIDTH
    )


def _is_spec_label(el: ImagePlaceholder | TextBlock | ButtonElement) -> TypeGuard[TextBlock]:
    return isinstance(el, TextBlock) and len(el.content.strip()) < _SPEC_LABEL_MAX_CHARS


def _group_spec_pairs(
    elements: list[ImagePlaceholder | TextBlock | ButtonElement],
) -> list[ImagePlaceholder | TextBlock | ButtonElement | list[_SpecPair]]:
    """Fold adjacent ``(icon, label)`` runs into spec-mini-table groups (51.4).

    Scans the F10-ordered column elements; a maximal run of >=2 consecutive
    ``(icon <= _SPEC_ICON_MAX_WIDTH, text < _SPEC_LABEL_MAX_CHARS)`` pairs becomes
    one ``list[_SpecPair]`` in place (a horizontal mini-table); everything else —
    the product name, the CTA, a lone icon+text — passes through unchanged, so a
    non-spec column is untouched.
    """
    result: list[ImagePlaceholder | TextBlock | ButtonElement | list[_SpecPair]] = []
    i = 0
    n = len(elements)
    while i < n:
        pairs: list[_SpecPair] = []
        j = i
        while j + 1 < n:
            icon = elements[j]
            label = elements[j + 1]
            if not (_is_spec_icon(icon) and _is_spec_label(label)):
                break
            pairs.append((icon, label))  # TypeGuards narrow icon/label above
            j += 2
        if len(pairs) >= 2:
            result.append(pairs)
            i = j
        else:
            result.append(elements[i])
            i += 1
    return result


def _spec_icon_img(img: ImagePlaceholder, image_urls: dict[str, str] | None) -> str:
    """One spec icon ``<img>`` at native width (mirrors ``_column_image_row``'s icon)."""
    url = _resolve_image_url(img.node_id, image_urls)
    if img.width:
        w = int(img.width)
        style = f"display:block;width:{w}px;max-width:{w}px;height:auto;border:0;"
        width_attr = f' width="{w}"'
    else:
        style = "display:block;height:auto;border:0;"
        width_attr = ""
    return (
        f'<img src="{html.escape(url)}" '
        f'alt="{html.escape(_derive_image_alt(img))}"{width_attr} style="{style}" />'
    )


def _spec_label_style(text: TextBlock) -> str:
    """Compact inline typography for a spec value/label cell (mirrors ``_column_text_row``)."""
    decls = ["text-align:left"]
    if text.font_family:
        family = html.escape(text.font_family, quote=True)
        if "," not in family:
            family = f"{family},sans-serif"
        decls.append(f"font-family:{family}")
    else:
        decls.append("font-family:Arial,sans-serif")
    decls.append(f"font-size:{int(text.font_size) if text.font_size else 11}px")
    if text.font_weight is not None:
        decls.append(f"font-weight:{text.font_weight}")
    decls.append(f"color:{_safe_color(text.text_color)}")
    if text.line_height is not None:
        decls.append(f"line-height:{round(text.line_height)}px")
    decls.append("mso-line-height-rule:exactly")
    return ";".join(decls) + ";"


def _spec_minitable_row(pairs: list[_SpecPair], image_urls: dict[str, str] | None) -> str:
    """Render a spec run as ONE centered horizontal ``[icon | value/label]`` row (51.4).

    Each pair is an icon cell (native width) + a value/label cell (stacked via
    :func:`_multiline_to_br`, design typography), in a content-width nested table
    centered inside the column — so the row reads ``[icon] 617/Pieces  [icon]
    +260/Insiders`` like the design instead of four stacked full-width rows.
    """
    cells: list[str] = []
    for idx, (icon, label) in enumerate(pairs):
        gap = "padding-left:16px;" if idx > 0 else ""  # gap between pairs
        cells.append(
            f'<td valign="middle" style="{gap}padding-right:6px;'
            f'font-size:0;line-height:0;">{_spec_icon_img(icon, image_urls)}</td>'
        )
        cells.append(
            f'<td valign="middle" style="{_spec_label_style(label)}">'
            f"{_multiline_to_br(label.content)}</td>"
        )
    inner = (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'align="center"><tr>{"".join(cells)}</tr></table>'
    )
    return f'<tr><td align="center" style="padding:0 0 8px;">{inner}</td></tr>'


def _build_column_fill_html(
    group: ColumnGroup,
    *,
    image_urls: dict[str, str] | None = None,
) -> str:
    """Build structured semantic HTML for a column group (G-REF-5).

    Each image, text and CTA is wrapped as a ``<tr><td>`` row inside one inner
    ``<table>`` (Phase 53 B2) so the column renders as a well-formed nested
    table instead of collapsing orphan rows in email clients. Rows follow the
    design's vertical order via ``content_order`` (F10), not category buckets.
    An adjacent ``(icon, label)`` run collapses to one centered mini-table row
    (G7 · 51.4) instead of stacking each icon and label full-width.
    """
    rows: list[str] = []
    for element in _group_spec_pairs(_ordered_column_elements(group)):
        if isinstance(element, list):
            rows.append(_spec_minitable_row(element, image_urls))
        elif isinstance(element, ImagePlaceholder):
            rows.append(_column_image_row(element, image_urls, column_width=group.width))
        elif isinstance(element, TextBlock):
            if _is_placeholder(element.content):
                continue
            rows.append(_column_text_row(element, is_heading=element.is_heading))
        else:
            if _is_placeholder(element.text):
                continue
            rows.append(_column_cta_row(element))
    return _wrap_column_table(rows)


def _image_node_id_attrs(img: ImagePlaceholder) -> dict[str, str]:
    """Stamp ``data-node-id`` on every image SlotFill (Phase 50.5).

    Lets the per-corner radius handler (Rule 10) locate the rendered ``<img>``
    by node id.
    """
    return {"data-node-id": img.node_id}


def _resolve_image_url(
    node_id: str,
    image_urls: dict[str, str] | None,
) -> str:
    """Resolve image URL from the asset map, falling back to a placeholder."""
    if image_urls:
        url = image_urls.get(node_id)
        if url:
            return url
    # Fallback — will 404 but keeps the node_id for debugging
    return f"/api/v1/design-sync/assets/{node_id}.png"


# F1 (RC-F1) — below this width (0.9x the 600px container) a stacked image
# renders at its natural size instead of stretching to full width, so icons and
# thin decorations aren't blown up. Mirrors the F3 image-width discipline.
_STACK_NATURAL_WIDTH_MAX = 540


def _select_primary_image(images: list[ImagePlaceholder]) -> tuple[int, ImagePlaceholder]:
    """Pick the largest image (by area) as a section's primary slot fill (F1).

    Single-image seeds carry one image slot; when a section has several images
    the largest is the visual anchor (the hero), so it fills that slot instead
    of ``images[0]`` — fixing the "icon-as-hero" swap where a small decoration
    preceded the real hero in tree order. Ties resolve to the earliest image.
    """
    best_idx = 0
    best_area = -1.0
    for idx, img in enumerate(images):
        width = img.width if img.width is not None else 0.0
        height = img.height if img.height is not None else 0.0
        area = width * height
        if area > best_area:
            best_area = area
            best_idx = idx
    return best_idx, images[best_idx]


def _stacked_image_row(img: ImagePlaceholder, image_urls: dict[str, str] | None) -> str:
    """Render one extra section image as a stacked ``<tr><td><img>`` row (F1).

    A full-width-style row (its own ``<tr>``) so multiple section images stack
    vertically. The inline width rule keeps genuinely full-width images
    responsive (``width:100%``) but pins sub-threshold images — icons, thin
    strips — to their natural size so they don't stretch to 600px. ``alt`` via
    :func:`_derive_image_alt`; ``data-node-id`` stamped for parity with the
    primary slot.
    """
    url = _resolve_image_url(img.node_id, image_urls)
    width = int(img.width) if img.width else None
    if width is not None and width < _STACK_NATURAL_WIDTH_MAX:
        size_css = f"width:{width}px;max-width:{width}px;"
    else:
        size_css = "width:100%;max-width:600px;"
    width_attr = f' width="{width}"' if width is not None else ""
    tag = (
        f'<img src="{html.escape(url)}" '
        f'alt="{html.escape(_derive_image_alt(img))}"{width_attr} '
        f'style="display:block;{size_css}height:auto;border:0;" '
        f'data-node-id="{html.escape(img.node_id)}" />'
    )
    return f'<tr><td style="padding:0;text-align:center;font-size:0;line-height:0;">{tag}</td></tr>'


def render_card_table(
    rows: list[str],
    *,
    width: int,
    bg: str,
    radius: int,
    align: str = "center",
) -> str:
    """Wrap card child rows in one rounded, fixed-width table (51.2 / Rule 1 + Rule 11).

    ``rows`` are full ``<tr>…</tr>`` strings (image or text rows) rendered in
    design y-order. ``border-collapse:separate`` + ``overflow:hidden`` clip the
    corners so ``border-radius`` bites (mirrors ``_replace_inner_radius``). The
    card carries NO dark-mode class -> a physical card's white surface never
    flips in dark mode (Rule 9, satisfied by construction). Reusable by the
    later spec-mini-table / footer row composites (G7/G8).

    The white surface is carried by the ``bgcolor`` ATTR only — never an inline
    ``background-color`` — because the section's container-bg override clobbers
    the first inline ``background-color`` in the component (``_replace_first_css_prop``
    when the ``td`` host has no ``_outer`` class). With no inline bg here, that
    override correctly falls through to paint the ``td`` outer (the band). ``bg`` is
    routed through :func:`_safe_color` so this reusable primitive stays hex-safe for
    future (G7/G8) callers, not just the validated ``inner_bg`` this ships with.
    """
    safe_bg = _safe_color(bg, "#FFFFFF")
    body = "".join(rows)
    return (
        f'<table role="presentation" width="{width}" align="{align}" '
        f'cellpadding="0" cellspacing="0" border="0" bgcolor="{safe_bg}" class="wf" '
        f'style="border-radius:{radius}px;'
        f'border-collapse:separate;overflow:hidden;">{body}</table>'
    )


def _card_image_row(img: ImagePlaceholder, image_urls: dict[str, str] | None, padding: str) -> str:
    """One image row inside a card (mirrors ``_stacked_image_row``; per-row padding).

    Reuses the width-pin (Rule 11: sub-``_STACK_NATURAL_WIDTH_MAX`` images render
    at native width, so the 440-wide card images render 440) and the gate-safe
    :func:`_derive_image_alt`. Deliberately omits ``data-node-id`` so the Rule-10
    per-image corner-radius override (``_apply_image_corner_radius``) can't stamp
    individual radii — the card clips its own corners via ``overflow:hidden``.
    """
    url = _resolve_image_url(img.node_id, image_urls)
    width = int(img.width) if img.width else None
    if width is not None and width < _STACK_NATURAL_WIDTH_MAX:
        size_css = f"width:{width}px;max-width:{width}px;"
    else:
        size_css = "width:100%;max-width:600px;"
    width_attr = f' width="{width}"' if width is not None else ""
    tag = (
        f'<img src="{html.escape(url)}" '
        f'alt="{html.escape(_derive_image_alt(img))}"{width_attr} '
        f'style="display:block;{size_css}height:auto;border:0;" />'
    )
    return (
        f'<tr><td style="padding:{padding};text-align:center;'
        f'font-size:0;line-height:0;">{tag}</td></tr>'
    )


def _card_text_row(text: TextBlock, bg: str) -> str:
    r"""One text row inside a card (full inline font props; ``\n`` -> ``<br>``)."""
    content = _safe_text(text.content).replace("\n", "<br />")
    # font-family: escaped (quote=True) so a design font name can't break out of the
    # style attr; web-safe fallback appended when absent (mirrors _column_text_row).
    if text.font_family:
        ff = html.escape(text.font_family, quote=True)
        if "," not in ff:
            ff = f"{ff},sans-serif"
    else:
        ff = "Arial,sans-serif"
    fs = int(text.font_size) if text.font_size else 14
    lh = int(text.line_height) if text.line_height else 19
    fw = text.font_weight if text.font_weight is not None else 600
    tc = _safe_color(text.text_color, "#000000")
    # bgcolor ATTR (not inline background-color) — see render_card_table docstring.
    return (
        f'<tr><td align="center" bgcolor="{_safe_color(bg, "#FFFFFF")}" style="'
        f"padding:10px 24px 0 24px;font-family:{ff};font-size:{fs}px;"
        f"line-height:{lh}px;font-weight:{fw};color:{tc};"
        f'mso-line-height-rule:exactly;">{content}</td></tr>'
    )


def _stacked_image_rows(
    images: list[ImagePlaceholder],
    primary_idx: int,
    image_urls: dict[str, str] | None,
) -> tuple[str, str]:
    """Split a section's non-primary images into rows above/below the primary (F1).

    Images arrive in tree order (== y order for these sections), so images that
    precede the primary render above it and images that follow render below —
    preserving the design's vertical order without a new seed slot.
    """
    before: list[str] = []
    after: list[str] = []
    for idx, img in enumerate(images):
        if idx == primary_idx:
            continue
        row = _stacked_image_row(img, image_urls)
        (before if idx < primary_idx else after).append(row)
    return "".join(before), "".join(after)


def _fills_preheader(
    section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    if section.texts:
        fills.append(SlotFill("preheader_text", _safe_text(section.texts[0].content)))
    return fills


def _fills_email_header(
    _section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    # email-header has no data-slot attributes (fixed nav links template)
    # We return text fills as hints for future slot injection
    return []


def _fills_logo_header(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    if section.images:
        # F1 (RC-F1): largest image is the primary logo, any extras stack below.
        primary_idx, img = _select_primary_image(section.images)
        overrides: dict[str, str] = _image_node_id_attrs(img)
        if img.width:
            overrides["width"] = str(int(img.width))
        if img.height:
            overrides["height"] = str(int(img.height))
        before, after = _stacked_image_rows(section.images, primary_idx, image_urls)
        fills.append(
            SlotFill(
                "logo_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
                stacked_before=before,
                stacked_after=after,
            )
        )
        fills.append(SlotFill("logo_alt", _derive_image_alt(img)))
    return fills


def _fills_hero(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    groups = section.child_content_groups

    # Background image
    if section.images:
        # F1 (RC-F1): largest image is the hero background. Stacked extra-image
        # rows don't apply — hero-block renders the image as a CSS/VML
        # background (no <img> anchor to splice around), and no corpus fixture
        # routes a multi-image section to hero-block. Deferred.
        _primary_idx, img = _select_primary_image(section.images)
        overrides: dict[str, str] = _image_node_id_attrs(img)
        # F3 (RC-F3): thread the design width for parity with the other image
        # builders. Inert for the current hero-block seed (CSS/VML background,
        # no <img> anchor — the renderer's _fill_hero_image ignores it); kept so
        # a future hero seed carrying an <img> sizes correctly.
        if img.width:
            overrides["width"] = str(int(img.width))
        if img.height:
            overrides["height"] = str(int(img.height))
        fills.append(
            SlotFill(
                "hero_image",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
            )
        )
    # Headline + Subtext
    if groups:
        headings = _headings_from_groups(groups)
        bodies = _bodies_from_groups(groups)
        if headings:
            fills.append(SlotFill("headline", _safe_text(headings[0].content)))
        if bodies:
            fills.append(SlotFill("subtext", _safe_text(bodies[0].content)))
    else:
        heading = _first_heading(section.texts)
        # RC-F6: a subtext preceding the headline in source order is an eyebrow —
        # splice it above the headline (stacked_before) rather than into the
        # subtext slot below; the subtext slot then takes the first POST-headline
        # body.
        pre_heading = _pre_heading_body_texts(section)
        pre_ids = {t.node_id for t in pre_heading}
        if heading:
            fills.append(
                SlotFill(
                    "headline",
                    _safe_text(heading.content),
                    stacked_before=_pre_heading_rows_html(pre_heading),
                )
            )
        body = next((b for b in _body_texts(section.texts) if b.node_id not in pre_ids), None)
        if body:
            fills.append(SlotFill("subtext", _safe_text(body.content)))
    # CTA — F4a (RC-F4): emit even without a button so the empty fills blank the
    # seed's "Learn More" placeholder (the B8 empty-fill discipline); the
    # renderer's CTA prune arm then drops the now-empty anchor rather than
    # leaking it.
    btn = section.buttons[0] if section.buttons else None
    fills.append(SlotFill("cta_text", _safe_text(btn.text) if btn else ""))
    fills.append(SlotFill("cta_url", _safe_url(btn.url) if btn else "", slot_type="cta"))
    return fills


def _fills_full_width_image(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    if section.images:
        # F1 (RC-F1): fill the seed's single image slot with the LARGEST image
        # and stack the rest as extra rows in tree order — previously
        # ``images[0]`` won and the real hero (case 7/8) was dropped.
        primary_idx, img = _select_primary_image(section.images)
        overrides: dict[str, str] = _image_node_id_attrs(img)
        if img.width:
            overrides["width"] = str(int(img.width))
        if img.height:
            overrides["height"] = str(int(img.height))
        before, after = _stacked_image_rows(section.images, primary_idx, image_urls)
        fills.append(
            SlotFill(
                "image_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
                stacked_before=before,
                stacked_after=after,
            )
        )
        fills.append(SlotFill("image_alt", _derive_image_alt(img)))
    return fills


def _body_slot_texts(section: EmailSection) -> list[TextBlock]:
    """Text nodes destined for the text-block body slot, placeholders excluded.

    Single source of the body-slot membership rule, shared by
    ``_fills_text_block`` (structure) and ``_build_token_overrides``
    (per-node typography targets) so anchor emission and ``_text_<node_id>``
    targeting cannot drift.
    """
    groups = section.child_content_groups
    if groups:
        return _bodies_from_groups(groups)
    bodies = [b for b in _body_texts(section.texts) if not _is_placeholder(b.content)]
    if bodies:
        return bodies
    if _first_heading(section.texts) is None and section.texts:
        # All texts are headings — first fills the heading slot, rest are body
        return [t for t in section.texts[1:] if not _is_placeholder(t.content)]
    return []


def _pre_heading_body_texts(section: EmailSection) -> list[TextBlock]:
    """Body texts that PRECEDE the first heading in source (tree/y) order (RC-F6).

    An eyebrow/kicker is a small body-classed text sitting above the headline in
    the design; since texts arrive in tree order, it is the run of body nodes
    before the first ``is_heading`` node. Empty for the group/column paths (no
    corpus fixture carries a grouped eyebrow) and when the section has no heading
    (nothing to sit above). Pairs with :func:`_pre_heading_rows_html`, which
    renders these as rows spliced above the heading.
    """
    if section.column_layout != ColumnLayout.SINGLE or section.child_content_groups:
        return []
    texts = section.texts
    first_heading_idx = next((i for i, t in enumerate(texts) if t.is_heading), None)
    if first_heading_idx is None:
        return []
    return [t for t in texts[:first_heading_idx] if not _is_placeholder(t.content)]


def _per_node_body_texts(section: EmailSection) -> list[TextBlock]:
    """Body texts that get per-node ``<td data-node-id>`` anchors (RC-D-prime).

    Only multi-text bodies anchor per node — a single body text keeps the
    plain string fill, where the shared ``_body`` target already carries that
    text's typography. Column layouts render through ``_build_column_fills``
    and never see these anchors.
    """
    if section.column_layout != ColumnLayout.SINGLE:
        return []
    texts = _body_slot_texts(section)
    # RC-F6: once an eyebrow is lifted above the heading, the shared ``_body``
    # target (first-body typography) becomes the eyebrow's, which would mis-style
    # a lone post-heading paragraph — so anchor every body node per-id, not just
    # when there are >=2.
    if _pre_heading_body_texts(section):
        return texts
    return texts if len(texts) >= 2 else []


def _paragraph_gap(text: TextBlock) -> int:
    """Vertical gap below a per-node text row, standing in for ``<br><br>``.

    The joined form rendered one empty line between nodes, whose height is
    the line-height in effect at the break — approximate it from the node's
    own metrics, falling back to a conventional paragraph gap.
    """
    if text.line_height:
        return round(text.line_height)
    if text.font_size:
        return round(text.font_size * 1.2)
    return 16


def _per_node_body_html(texts: list[TextBlock]) -> str:
    """Render body texts as one ``<td data-node-id>`` anchor per node (RC-D-prime).

    The nested table replaces the ``'<br><br>'.join`` so each node is an
    addressable element for its ``_text_<node_id>`` override target. Inner
    cells carry ``mso-line-height-rule:exactly`` plus an explicit
    inter-paragraph gap; the typography itself arrives via the overrides.
    """
    rows: list[str] = []
    last = len(texts) - 1
    for i, text in enumerate(texts):
        pad = f"padding:0 0 {_paragraph_gap(text)}px 0;" if i < last else ""
        node = html.escape(text.node_id, quote=True)
        rows.append(
            f'<tr><td data-node-id="{node}" '
            f'style="{pad}mso-line-height-rule:exactly;">'
            f"{_safe_text(text.content)}</td></tr>"
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        + "".join(rows)
        + "</table>"
    )


def _pre_heading_rows_html(texts: list[TextBlock]) -> str:
    """Render pre-heading eyebrow texts as bare ``<tr><td data-node-id>`` rows (RC-F6).

    The rows are spliced ABOVE the heading row.
    Each ``<td>`` is an addressable anchor for its ``_text_<node_id>`` typography
    override, so per-node styling is preserved. Inter-element spacing uses the
    ``padding-bottom`` LONGHAND, never the ``padding:`` shorthand — the section's
    ``_cell`` padding override replaces the first ``padding:`` shorthand, so a
    shorthand here would be stolen from the heading ``<td>`` that follows.
    """
    rows: list[str] = []
    for text in texts:
        node = html.escape(text.node_id, quote=True)
        rows.append(
            f'<tr><td data-node-id="{node}" '
            f'style="padding-bottom:{_paragraph_gap(text)}px;'
            f'mso-line-height-rule:exactly;">'
            f"{_safe_text(text.content)}</td></tr>"
        )
    return "".join(rows)


def _fills_text_block(
    section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    groups = section.child_content_groups

    # RC-F6: body texts preceding the first heading in source order are eyebrows;
    # they ride the heading fill's stacked_before as data-node-id rows spliced
    # above the heading row (empty for groups / no-heading — see helper).
    pre_heading = _pre_heading_body_texts(section)
    pre_ids = {t.node_id for t in pre_heading}
    pre_rows = _pre_heading_rows_html(pre_heading)

    if groups:
        all_headings = _headings_from_groups(groups)
        if all_headings:
            fills.append(SlotFill("heading", _safe_text(all_headings[0].content)))
    else:
        heading = _first_heading(section.texts)
        if heading:
            fills.append(SlotFill("heading", _safe_text(heading.content), stacked_before=pre_rows))
        elif section.texts and not _body_texts(section.texts):
            # All texts are headings — use first as heading, rest as body
            fills.append(SlotFill("heading", _safe_text(section.texts[0].content)))

    # Body slot carries only the post-heading body texts; the pre-heading
    # eyebrows are spliced above the heading (pre_rows) instead.
    body_blocks = [b for b in _body_slot_texts(section) if b.node_id not in pre_ids]
    if body_blocks:
        if _per_node_body_texts(section):
            # RC-D-prime (phase-52.4b): per-node anchors instead of the
            # '<br><br>'.join, which flattened every run onto the first
            # body's typography (last-write-wins on the shared _body class).
            fills.append(SlotFill("body", _per_node_body_html(body_blocks)))
        else:
            fills.append(
                SlotFill("body", "<br><br>".join(_safe_text(b.content) for b in body_blocks))
            )

    # Append CTA button HTML to body slot (text-block has no dedicated CTA slot).
    # Emit *every* button, not just buttons[0]: a content section can carry a
    # stacked CTA pair (e.g. mammut case 10 "SHOP THE COLLECTION" + "DISCOVER
    # EIGER EXTREME 6.0") inside one column, and taking only the first silently
    # dropped the rest (phase-53-b8-non-cta-multibutton-drop). Render each with
    # its designed text colour + stroke (the model carries both) so outlined
    # buttons — white fill, dark text, coloured border — don't collapse to
    # invisible white-on-white from a hardcoded color:#ffffff.
    cta_parts: list[str] = []
    for btn in section.buttons:
        if _is_placeholder(btn.text):
            continue
        btn_url = html.escape(_safe_url(btn.url))
        bg = _safe_color(btn.fill_color, "#0066cc")
        # Label colour follows the design (F11, phase-53-b8-text-block-solid-
        # cta-text-color): white only when no text_color was extracted,
        # mirroring _column_cta_row. c7's raw_figma Button (white fill, BLACK
        # text fill, 2px inside stroke) settled the b8 open question — extracted
        # text fills are visual intent, not Figma defaults. An *outlined* button
        # (stroke present) additionally renders its border and keeps the darker
        # #1a1a1a absence-fallback so a missing label colour can't collapse to
        # white-on-white on its typically light fill.
        fg = _safe_color(btn.text_color, "#ffffff")
        border = ""
        if btn.stroke_color and btn.stroke_weight:
            stroke = _safe_color(btn.stroke_color, "")
            if stroke:
                fg = _safe_color(btn.text_color, "#1a1a1a")
                border = f"border:{max(1, round(btn.stroke_weight))}px solid {stroke};"
        cta_parts.append(
            f'<a href="{btn_url}" style="display:inline-block;'
            f"padding:{_cta_padding_css(btn)};background-color:{bg};color:{fg};"
            f"text-decoration:none;{_cta_label_typography(btn)}{border}"
            f'{_cta_radius_css(btn)};">{_safe_text(btn.text)}</a>'
        )
    if cta_parts:
        # 51.1 own-row CTA (M8): emit the CTA as a composite row spliced after the
        # body (or heading) row instead of folding the anchors INTO the body <td>
        # (where they inherited the body cell's left padding and hugged the left
        # edge). The wrapping <td align="center"> centers the anchors on their own
        # row like the design. Anchor markup (G3 geometry) is unchanged.
        anchor_slot = (
            "body"
            if any(f.slot_id == "body" for f in fills)
            else "heading"
            if any(f.slot_id == "heading" for f in fills)
            else None
        )
        if anchor_slot is not None:
            fills.append(
                SlotFill(
                    "cta_row",
                    "",
                    slot_type="composite",
                    composite=CompositeSlot(
                        children=tuple(SlotFill("cta_anchor", a) for a in cta_parts),
                        after_slot=anchor_slot,
                        # The reference (body) cell already contributes its own
                        # bottom padding (24px) as the above-CTA gap, matching the
                        # design's body->CTA spacing; so top=0 here avoids doubling
                        # it. 24px sides mirror the body's horizontal padding; 24px
                        # bottom keeps the template's vertical rhythm below the CTA.
                        cell_style="padding:0 24px 24px;",
                        child_separator="\n",  # preserve the old fold's inter-anchor gap
                    ),
                )
            )
        else:
            # Fallback (no text anchor slot — not hit by the corpus): keep the
            # pre-51.1 inline behaviour so a CTA is never dropped.
            fills.append(SlotFill("body", "\n".join(cta_parts)))

    return fills


def _fills_article_card(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    groups = section.child_content_groups

    if section.images:
        # F1 (RC-F1): largest image is the card's primary, rest stack in tree order.
        primary_idx, img = _select_primary_image(section.images)
        before, after = _stacked_image_rows(section.images, primary_idx, image_urls)
        fills.append(
            SlotFill(
                "image_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=_image_node_id_attrs(img),
                stacked_before=before,
                stacked_after=after,
            )
        )
        fills.append(SlotFill("image_alt", _derive_image_alt(img)))
    if groups:
        headings = _headings_from_groups(groups)
        bodies = _bodies_from_groups(groups)
        if headings:
            fills.append(SlotFill("heading", _safe_text(headings[0].content)))
        if bodies:
            body_parts = [_safe_text(b.content) for b in bodies]
            fills.append(SlotFill("body_text", "<br><br>".join(body_parts)))
    else:
        heading = _first_heading(section.texts)
        if heading:
            fills.append(SlotFill("heading", _safe_text(heading.content)))
        bodies = _body_texts(section.texts)
        if bodies:
            body_parts = [_safe_text(b.content) for b in bodies if not _is_placeholder(b.content)]
            if body_parts:
                fills.append(SlotFill("body_text", "<br><br>".join(body_parts)))
    if section.buttons:
        btn = section.buttons[0]
        fills.append(SlotFill("cta_text", _safe_text(btn.text)))
        fills.append(SlotFill("cta_url", _safe_url(btn.url), slot_type="cta"))
    return fills


def _fills_image_block(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill image-block: replace placeholder src + alt on the <img> tag.

    The image-block seed has no data-slot attrs, so we use image_url/image_alt
    slots. The renderer's _fill_image_slot handles src replacement on any
    <img> tag with a matching data-slot, and we also directly replace the
    placeholder URL via a token override.
    """
    fills: list[SlotFill] = []
    if section.images:
        # F1 (RC-F1): pick the largest image (fixes icon-as-primary). Stacked
        # extra-image rows are NOT emitted here — the image-block seed is
        # special-cased in the renderer's _fill_slots (direct src/alt replace,
        # bypassing _fill_image_slot where the splice lives), and no corpus
        # fixture routes a multi-image section to image-block. Deferred.
        _primary_idx, img = _select_primary_image(section.images)
        overrides: dict[str, str] = _image_node_id_attrs(img)
        # F3 (RC-F3): thread the design width; applied via _fill_image_slot (the
        # image-block image_url branch now delegates there).
        if img.width:
            overrides["width"] = str(int(img.width))
        if img.height:
            overrides["height"] = str(int(img.height))
        fills.append(
            SlotFill(
                "image_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
            )
        )
        fills.append(SlotFill("image_alt", _derive_image_alt(img)))
    return fills


def _fills_image_grid(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    fills: list[SlotFill] = []
    for i, img in enumerate(section.images[:2], start=1):
        overrides: dict[str, str] = _image_node_id_attrs(img)
        # F3 (RC-F3): thread the design width; clamped in _fill_image_slot so a
        # small grid image is not stretched to the seed's full cell width.
        if img.width:
            overrides["width"] = str(int(img.width))
        if img.height:
            overrides["height"] = str(int(img.height))
        fills.append(
            SlotFill(
                f"image_{i}",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
            )
        )
    return fills


def _fills_product_grid(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill product-grid: iterate column groups, extract image/title/desc/cta per product."""
    fills: list[SlotFill] = []
    groups = section.column_groups or []
    for i, group in enumerate(groups[:4], 1):
        if group.images:
            img = group.images[0]
            overrides: dict[str, str] = _image_node_id_attrs(img)
            # F3 (RC-F3): thread the design width; clamped in _fill_image_slot.
            if img.width:
                overrides["width"] = str(int(img.width))
            if img.height:
                overrides["height"] = str(int(img.height))
            fills.append(
                SlotFill(
                    f"product_{i}_image",
                    _resolve_image_url(img.node_id, image_urls),
                    slot_type="image",
                    attr_overrides=overrides,
                )
            )
        heading = _first_heading(group.texts)
        if heading:
            fills.append(SlotFill(f"product_{i}_title", _safe_text(heading.content)))
        body = _body_texts(group.texts)
        if body:
            fills.append(SlotFill(f"product_{i}_desc", _safe_text(body[0].content)))
        if group.buttons:
            fills.append(SlotFill(f"product_{i}_cta", _safe_text(group.buttons[0].text)))
    return fills


def _fills_category_nav(
    section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    """Fill category-nav: map short texts to nav_item slots."""
    fills: list[SlotFill] = []
    for i, text in enumerate(section.texts[:6], 1):
        fills.append(SlotFill(f"nav_item_{i}", _safe_text(text.content)))
    return fills


def _fills_col_icon(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill col-icon: per-column icon image + heading (F4b, RC-F4).

    The seed's slots are ``icon_1_url``/``icon_2_url`` (images) and
    ``heading_1``/``heading_2`` (labels). Routing to ``_fills_text_block`` (which
    emits ``heading``/``body``) left all four unfilled by construction, so
    slate's grid leaked ``fakeimg.pl`` placeholders + "Feature icon" alts. Fill
    each column's icon (real src + derived alt) and heading from the section's
    images/texts; unfilled ``icon_N_url`` imgs — and the seed's no-data-slot
    mobile twins — are dropped by ``_strip_placeholder_urls``, and unfilled
    ``heading_N`` cells blank via the post-fill text pass.
    """
    fills: list[SlotFill] = []
    for i, img in enumerate(section.images[:2], start=1):
        overrides = _image_node_id_attrs(img)
        overrides["alt"] = _derive_image_alt(img)
        fills.append(
            SlotFill(
                f"icon_{i}_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=overrides,
            )
        )
    for i, text in enumerate(section.texts[:2], start=1):
        fills.append(SlotFill(f"heading_{i}", _safe_text(text.content)))
    return fills


def _fills_image_gallery(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill image-gallery: map 3+ images to numbered slots."""
    fills: list[SlotFill] = []
    for i, img in enumerate(section.images[:6], start=1):
        fills.append(
            SlotFill(
                f"image_{i}",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=_image_node_id_attrs(img),
            )
        )
    return fills


def _fills_card(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill a physical card-with-N-children (51.2 / Rule 1 + Rule 11).

    Renders the card's heterogeneous children (logo/identity-text/barcode/shape)
    as stacked rows inside ONE white rounded table at the dominant image width,
    instead of the image-gallery seed that lays them out as 3-across tiles and
    drops the identity TEXT. Child order comes from ``content_order`` (the F10
    interleave restorer) — the category lists lose the image↔text interleave.
    Returns a single ``content`` text fill for the ``td`` seed (fill-a-cell,
    not a splice); ``_fill_text_slot`` inserts the table HTML raw.
    """
    images_by_id = {im.node_id: im for im in section.images}
    texts_by_id = {t.node_id: t for t in section.texts}
    # Y-order from content_order (the F10 interleave restorer) filtered to the ids
    # we actually carry, then any remaining images/texts appended in stored order —
    # so every child renders even when content_order is absent or references stale
    # ids (the category lists otherwise lose the image↔text interleave).
    known = tuple(images_by_id) + tuple(texts_by_id)
    content_order = (
        section.column_groups[0].content_order
        if section.column_groups and section.column_groups[0].content_order
        else ()
    )
    order = [nid for nid in content_order if nid in images_by_id or nid in texts_by_id]
    order += [nid for nid in known if nid not in order]

    rows: list[str] = []
    images_seen = 0
    bg = section.inner_bg or "#FFFFFF"
    for node_id in order:
        if node_id in images_by_id:
            # First image carries the card's top inset; the rest sit flush so the
            # rounded corners clip cleanly (design: logo 20px top, others 0).
            padding = "20px 0 0 0" if images_seen == 0 else "0"
            rows.append(_card_image_row(images_by_id[node_id], image_urls, padding))
            images_seen += 1
        elif node_id in texts_by_id:
            rows.append(_card_text_row(texts_by_id[node_id], bg))

    if not rows:  # unreachable (the predicate guarantees images AND texts) — defensive
        return []

    # Rule 11: card width = dominant child-image native width (the nested images
    # aren't direct frame children, so rule_11's ``inner_card_fixed_width`` is
    # None here — read the widths directly).
    width = max((int(im.width) for im in section.images if im.width), default=600)
    return [
        SlotFill(
            "content",
            render_card_table(
                rows,
                width=width,
                bg=bg,
                radius=int(section.inner_radius) if section.inner_radius is not None else 0,
            ),
            slot_type="text",
        )
    ]


def _fills_cta(
    section: EmailSection,
    _cw: int,
    *,
    slug: str = "cta-button",
    **_kw: object,
) -> list[SlotFill]:
    """Fill CTA-family slots, keyed on the seed's slug — not button count.

    The chosen slug decides the slot set because the VLM fallback path can pick
    a slug that disagrees with the button count (a count-keyed filler would
    emit slots the seed doesn't have, silently dropping the labels).
    """
    fills: list[SlotFill] = []
    buttons = section.buttons
    if slug == "cta-pair":
        # B8: cta-pair seed (primary + secondary slots). Only the first two
        # buttons are emitted; the seed has no slot for a third (email layout
        # caps a button row at two). With fewer than two buttons, empty fills
        # blank the seed placeholders instead of leaking them.
        primary = buttons[0] if buttons else None
        secondary = buttons[1] if len(buttons) >= 2 else None
        fills.append(SlotFill("primary_text", _safe_text(primary.text) if primary else ""))
        fills.append(
            SlotFill("primary_url", _safe_url(primary.url) if primary else "", slot_type="cta")
        )
        fills.append(SlotFill("secondary_text", _safe_text(secondary.text) if secondary else ""))
        fills.append(
            SlotFill(
                "secondary_url", _safe_url(secondary.url) if secondary else "", slot_type="cta"
            )
        )
    elif slug == "text-link":
        # F4a (RC-F4): emit even when ``buttons`` is empty so the empty fills
        # blank the seed's link placeholder (the B8 cta-pair empty-fill
        # discipline); the renderer's CTA prune arm then drops the now-empty
        # anchor rather than leaking the seed default.
        btn = buttons[0] if buttons else None
        fills.append(SlotFill("link_text", _safe_text(btn.text) if btn else ""))
        fills.append(SlotFill("link_url", _safe_url(btn.url) if btn else "", slot_type="cta"))
    else:
        btn = buttons[0] if buttons else None
        fills.append(SlotFill("cta_text", _safe_text(btn.text) if btn else ""))
        fills.append(SlotFill("cta_url", _safe_url(btn.url) if btn else "", slot_type="cta"))
    return fills


# ── Footer builders (Track G · G8 / 51.6) ──
# Seed styling reused so converter output stays visually flush with
# ``email-templates/components/email-footer.html``.
_FOOTER_LEGAL_TEXT_STYLE = (
    "padding: 0 0 12px 0; text-align: center; font-family: Arial, sans-serif; "
    "font-size: 12px; color: #666666; line-height: 1.5; mso-line-height-rule: exactly;"
)
_FOOTER_UNSUB_CELL_STYLE = (
    "padding: 0; text-align: center; font-family: Arial, sans-serif; "
    "font-size: 12px; mso-line-height-rule: exactly;"
)
_FOOTER_LINK_STYLE = "color: #0066cc; text-decoration: underline;"
# Collapse runs of adjacent hard breaks (Figma often encodes a single visual
# line break as LF + U+2028) down to one ``<br />`` so footer lines don't
# gain a blank line between them.
_FOOTER_MULTI_BR_RE = re.compile(r"(?:<br />){2,}")
_BR = "<br />"


def _render_text_runs(text: TextBlock) -> str:
    """Render a footer TEXT node, emitting ``<a>`` links from its style runs.

    Walks :attr:`TextBlock.style_runs` in ``start`` order, slicing
    ``content[start:end]`` and wrapping runs that carry a ``link_url`` in an
    anchor styled with the run's colour + underline (falling back to the node
    colour). Hard line breaks are converted to ``<br />`` via
    :func:`_multiline_to_br`; a break landing at a link boundary is hoisted
    outside the anchor and adjacent breaks are collapsed to one. Offsets index
    the raw characters while ``content`` is stripped, so indices are clamped and
    overlapping/backward runs are skipped defensively.
    """
    content = text.content
    runs = text.style_runs
    if not runs:
        return _FOOTER_MULTI_BR_RE.sub(_BR, _multiline_to_br(content))

    n = len(content)
    default_color = _safe_color(text.text_color, "#0066cc")
    parts: list[str] = []
    cursor = 0
    for run in sorted(runs, key=lambda r: r.start):
        start = max(0, min(run.start, n))
        end = max(0, min(run.end, n))
        if end <= start or start < cursor:
            continue
        if cursor < start:
            parts.append(_multiline_to_br(content[cursor:start]))
        segment = _multiline_to_br(content[start:end])
        if run.link_url:
            # Hoist leading/trailing breaks out of the anchor so they collapse
            # with adjacent breaks and the underline never spans a line break.
            leading = ""
            while segment.startswith(_BR):
                leading += _BR
                segment = segment[len(_BR) :]
            trailing = ""
            while segment.endswith(_BR):
                trailing += _BR
                segment = segment[: -len(_BR)]
            color = _safe_color(run.color_hex, default_color)
            decoration = "underline" if run.underline else "none"
            href = html.escape(_safe_url(run.link_url), quote=True)
            parts.append(
                f'{leading}<a href="{href}" style="color: {color}; '
                f'text-decoration: {decoration};">{segment}</a>{trailing}'
            )
        else:
            parts.append(segment)
        cursor = end
    if cursor < n:
        parts.append(_multiline_to_br(content[cursor:]))
    return _FOOTER_MULTI_BR_RE.sub(_BR, "".join(parts))


def _footer_editorial_row(text: TextBlock, pad_bottom: int) -> str:
    """Build one footer editorial ``<tr><td>`` from a TEXT node's design props.

    Mirrors :func:`_column_text_row` typography (font-family escaped + web-safe
    fallback; size ``int`` default 12; weight raw; ``_safe_color``; line-height
    ``round(px)``; align allowlist default centre; letter-spacing skipping
    ``0.0``; transform/decoration allowlist; ``mso-line-height-rule:exactly``)
    but sources content from :func:`_render_text_runs` (style-run links) and
    takes an explicit ``padding-bottom`` for inter-node spacing.
    """
    decls = [f"padding:0 0 {pad_bottom}px 0"]
    if text.font_family:
        family = html.escape(text.font_family, quote=True)
        if "," not in family:
            family = f"{family},sans-serif"
        decls.append(f"font-family:{family}")
    else:
        decls.append("font-family:Arial,sans-serif")

    size = int(text.font_size) if text.font_size else 12
    decls.append(f"font-size:{size}px")

    if text.font_weight is not None:
        decls.append(f"font-weight:{text.font_weight}")

    decls.append(f"color:{_safe_color(text.text_color)}")

    if text.line_height is not None:
        decls.append(f"line-height:{round(text.line_height)}px")
    else:
        decls.append("line-height:1.5")

    align = text.text_align.lower() if text.text_align else "center"
    if align in _ALLOWED_TEXT_ALIGN:
        decls.append(f"text-align:{align}")

    if text.letter_spacing not in (None, 0.0):
        decls.append(f"letter-spacing:{text.letter_spacing:.2f}px")

    if text.text_transform is not None:
        tt = text.text_transform.lower()
        if tt in _ALLOWED_TEXT_TRANSFORM:
            decls.append(f"text-transform:{tt}")

    if text.text_decoration is not None:
        td = text.text_decoration.lower()
        if td in _ALLOWED_TEXT_DECORATION:
            decls.append(f"text-decoration:{td}")

    decls.append("mso-line-height-rule:exactly")
    style = ";".join(decls) + ";"
    return f'<tr><td style="{style}">{_render_text_runs(text)}</td></tr>'


def _footer_editorial_rows(section: EmailSection) -> str:
    """Assemble the ``footer_editorial`` cell as a nested per-node row table.

    One ``<tr><td>`` per :attr:`EmailSection.texts` entry (tree order). Inter-row
    spacing uses the design ``element_gaps`` when a positive value is present,
    else a 12px default matching the seed rhythm; the last row has no
    padding-bottom. Empty when the section carries no text.
    """
    texts = section.texts
    if not texts:
        return ""

    gaps = section.element_gaps
    last = len(texts) - 1
    rows: list[str] = []
    for i, text in enumerate(texts):
        if i == last:
            pad = 0
        elif i < len(gaps) and gaps[i] > 0:
            pad = round(gaps[i])
        else:
            pad = 12
        rows.append(_footer_editorial_row(text, pad))
    inner = "\n".join(rows)
    return (
        '<table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" border="0">\n{inner}\n</table>'
    )


def _footer_legal_text_row(inner_html: str) -> str:
    """Wrap a legal line (copyright / address) in the seed's centred cell."""
    return f'<tr><td class="footer-text" style="{_FOOTER_LEGAL_TEXT_STYLE}">{inner_html}</td></tr>'


def _footer_unsub_row(unsub_label: str) -> str:
    """The compliance unsubscribe ``<tr>`` — ALWAYS emitted (G8 invariant).

    Reconstructs the seed's row-3 link cell verbatim (the ``{{unsubscribeUrl}}``
    / ``{{preferencesUrl}}`` Liquid merge tags and the static privacy link) so a
    working unsubscribe is guaranteed regardless of design content. The merge
    tags are emitted as plain-string literals (never through ``_safe_text``) so
    they survive for downstream Liquid rendering. Only ``unsub_label`` (already
    escaped) varies, from ``FooterConfig.unsubscribe_text``.
    """
    links = (
        '<a href="{{unsubscribeUrl}}" class="footer-link" style="'
        + _FOOTER_LINK_STYLE
        + '">'
        + unsub_label
        + "</a>\n                  &nbsp;|&nbsp;\n"
        '<a href="{{preferencesUrl}}" class="footer-link" style="'
        + _FOOTER_LINK_STYLE
        + '">Manage Preferences</a>\n                  &nbsp;|&nbsp;\n'
        '<a href="https://example.com/privacy" class="footer-link" style="'
        + _FOOTER_LINK_STYLE
        + '">Privacy Policy</a>'
    )
    return f'<tr><td style="{_FOOTER_UNSUB_CELL_STYLE}">{links}</td></tr>'


def _footer_legal_html(design_system: DesignSystem | None) -> str:
    """Build the ``footer_legal`` compliance block (G8 legal policy).

    The unsubscribe row is an invariant. When a project ``DesignSystem`` carries
    a ``FooterConfig`` its ``legal_text``/``company_name`` and ``address``
    populate the legal lines and ``unsubscribe_text`` relabels the unsub link;
    when absent, the seed's placeholder ©/address rows are dropped entirely and
    only the reconstructed unsubscribe row remains (no "Company Name / Business
    Street" leakage, ``{{unsubscribeUrl}}`` still guaranteed).
    """
    footer = design_system.footer if design_system is not None else None
    rows: list[str] = []
    unsub_label = "Unsubscribe"

    if footer is not None:
        if footer.legal_text:
            rows.append(_footer_legal_text_row(_safe_text(footer.legal_text)))
        else:
            rows.append(
                _footer_legal_text_row(
                    f"&copy; {_safe_text(footer.company_name)}. All rights reserved."
                )
            )
        if footer.address:
            rows.append(_footer_legal_text_row(_safe_text(footer.address)))
        if footer.unsubscribe_text:
            unsub_label = _safe_text(footer.unsubscribe_text)

    rows.append(_footer_unsub_row(unsub_label))
    inner = "\n".join(rows)
    return (
        '<table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" border="0">\n{inner}\n</table>'
    )


def _fills_footer(
    section: EmailSection,
    _cw: int,
    *,
    design_system: DesignSystem | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Build the converted footer's editorial + legal content (Track G · G8 / 51.6).

    ``_fills_footer`` is the converter footer's content AND compliance owner:

    * ``footer_editorial`` — one ``<tr><td>`` row per design TEXT node (nested
      ``<table>`` inside the editorial cell), rendered with the node's design
      typography and its per-run ``<a>`` links (:attr:`StyleRun.link_url`), with
      hard line breaks converted to ``<br />``.
    * ``footer_legal`` — a deterministically rebuilt compliance block. The
      ``{{unsubscribeUrl}}`` unsubscribe row is an invariant (always emitted).
      A project :class:`DesignSystem` ``FooterConfig`` substitutes its
      ``company_name``/``legal_text``/``address``; when absent, the seed's
      placeholder ©/address rows are dropped.

    Supersedes RC-F5 (Track F/F5): the builder now actively emits
    ``footer_legal`` instead of relying on slot preservation, so no placeholder
    "Company Name / Business Street" boilerplate leaks and a working unsubscribe
    link is guaranteed even when the design carries none. The design's own
    decorative unsub/preferences links coexist as editorial (ratified "Coexist"
    dedupe policy) — exactly one compliance row, no token rewriting.
    """
    fills: list[SlotFill] = []
    editorial = _footer_editorial_rows(section)
    if editorial:
        fills.append(SlotFill("footer_editorial", editorial))
    fills.append(SlotFill("footer_legal", _footer_legal_html(design_system)))
    return fills


def _fills_spacer(
    section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    height = int(section.height if section.height is not None else 32)
    return [SlotFill("spacer_height", str(height))]


_LOCATION_KEYWORD_RE = re.compile(
    r"\b(?:location|venue|where|address|at\s)",
    re.IGNORECASE,
)


def _fills_event_card(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Fill event-card slots: name, date, location, description, CTA.

    Emits empty strings for fields that don't match a pattern so the renderer
    strips the placeholder default rather than leaking "April 15, 2026" into
    real output.
    """
    fills: list[SlotFill] = []
    texts = section.texts
    consumed_ids: set[int] = set()

    name_source = _first_heading(texts) or (texts[0] if texts else None)
    event_name = _safe_text(name_source.content) if name_source else ""
    if name_source is not None:
        consumed_ids.add(id(name_source))
    fills.append(SlotFill("event_name", event_name))

    body_texts = _body_texts(texts)

    date_value = ""
    for text in body_texts:
        if id(text) in consumed_ids:
            continue
        if _DATE_PATTERN.search(text.content):
            date_value = _safe_text(text.content)
            consumed_ids.add(id(text))
            break
    fills.append(SlotFill("date", date_value))

    location_value = ""
    for text in body_texts:
        if id(text) in consumed_ids:
            continue
        if _LOCATION_KEYWORD_RE.search(text.content):
            location_value = _safe_text(text.content)
            consumed_ids.add(id(text))
            break
    fills.append(SlotFill("location", location_value))

    description_parts = [
        _safe_text(text.content)
        for text in body_texts
        if id(text) not in consumed_ids and not _is_placeholder(text.content)
    ]
    fills.append(SlotFill("description", "<br><br>".join(description_parts)))

    cta_text = ""
    cta_url = "#"
    if section.buttons:
        btn = section.buttons[0]
        if not _is_placeholder(btn.text):
            cta_text = _safe_text(btn.text)
            cta_url = _safe_url(btn.url)
    fills.append(SlotFill("cta_text", cta_text))
    fills.append(SlotFill("cta_url", cta_url, slot_type="cta"))

    if section.images:
        img = section.images[0]
        fills.append(
            SlotFill(
                "image_url",
                _resolve_image_url(img.node_id, image_urls),
                slot_type="image",
                attr_overrides=_image_node_id_attrs(img),
            )
        )
        fills.append(SlotFill("image_alt", _derive_image_alt(img)))

    return fills


def _fills_social(
    section: EmailSection,
    _cw: int,
    *,
    image_urls: dict[str, str] | None = None,
    **_kw: object,
) -> list[SlotFill]:
    """Replace the social row HTML with one ``<td>`` per Figma button.

    The template carries a single ``data-slot="social_links"`` on the outer
    ``<table>``. The text-slot filler replaces the inner rows verbatim, so
    emitting raw HTML here overrides the placeholder ``example.com/link``
    anchors with the real URLs + icons extracted from Figma.
    """
    if not section.buttons and not section.images:
        return []

    cells: list[str] = []
    for idx, btn in enumerate(section.buttons):
        icon_src: str = ""
        if btn.icon_node_id and image_urls:
            icon_src = image_urls.get(btn.icon_node_id) or ""
        if not icon_src and image_urls:
            icon_src = image_urls.get(btn.node_id) or ""
        if not icon_src:
            continue
        href = html.escape(_safe_url(btn.url))
        # html.escape(..., quote=True) — alt goes into an attribute value, so
        # " must be escaped. _safe_text uses quote=False (body-text context).
        alt = html.escape(btn.text or f"Social link {idx + 1}")
        icon_src = html.escape(icon_src)
        cells.append(
            '<td style="padding: 0 8px;">'
            f'<a href="{href}" style="text-decoration: none;">'
            f'<img src="{icon_src}" alt="{alt}" width="32" height="32" '
            'style="display: block; border: 0;" />'
            "</a></td>"
        )

    if not cells:
        # No Figma button icons — fall back to treating raw images as icons
        # with a neutral "#" href. Still better than leaking example.com.
        for img in section.images:
            icon_src = html.escape(_resolve_image_url(img.node_id, image_urls))
            alt = html.escape(
                img.node_name if _is_descriptive_alt(img.node_name) else "Social icon"
            )
            cells.append(
                '<td style="padding: 0 8px;">'
                '<a href="#" style="text-decoration: none;">'
                f'<img src="{icon_src}" alt="{alt}" width="32" height="32" '
                'style="display: block; border: 0;" />'
                "</a></td>"
            )

    if not cells:
        return []

    row_html = "<tr>" + "".join(cells) + "</tr>"
    return [SlotFill("social_links", row_html, slot_type="attr")]


def _fills_divider(
    _section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    return []


def _fills_nav(
    section: EmailSection,
    _cw: int,
    **_kw: object,
) -> list[SlotFill]:
    """Build nav link HTML from section buttons and/or texts.

    Buttons are preferred (they have explicit text labels from the Figma design).
    Falls back to non-heading texts if no buttons are detected.
    The first heading text becomes a label prefix (e.g. "Stores (LaB)").
    """
    if not section.buttons and not section.texts:
        return []

    link_parts: list[str] = []

    # Use buttons as nav links (they have explicit labels)
    if section.buttons:
        for btn in section.buttons:
            escaped = _safe_text(btn.text)
            link_parts.append(
                f'<a class="navbar-link" href="#" style="color:#333333;'
                f'text-decoration:none;padding:0 12px;">{escaped}</a>'
            )
    else:
        # Fallback: use texts as links (skip headings unless ALL are headings)
        body_texts = [t for t in section.texts if not t.is_heading]
        link_texts = body_texts or section.texts
        for text in link_texts:
            escaped = _safe_text(text.content)
            link_parts.append(
                f'<a class="navbar-link" href="#" style="color:#333333;'
                f'text-decoration:none;padding:0 12px;">{escaped}</a>'
            )

    if not link_parts:
        return []

    return [SlotFill("nav_links", "\n      ".join(link_parts))]


def _build_column_fills(
    section: EmailSection,
    *,
    image_urls: dict[str, str] | None = None,
) -> list[SlotFill]:
    """Build slot fills for column layout components (col_1, col_2, etc.)."""
    # Use column_groups when available (structure-aware)
    if section.column_groups:
        return _build_column_fills_from_groups(
            section.column_groups,
            image_urls=image_urls,
        )

    # Use child_content_groups when column_groups are absent (one group per column)
    if section.child_content_groups:
        return _build_column_fills_from_content_groups(
            section.child_content_groups,
            image_urls=image_urls,
        )

    # Fallback: distribute content round-robin across columns
    fills: list[SlotFill] = []
    col_count = section.column_count if section.column_count > 0 else 2

    for col_idx in range(1, col_count + 1):
        col_texts: list[str] = []
        for i, text in enumerate(section.texts):
            if (i % col_count) + 1 == col_idx:
                if _is_placeholder(text.content):
                    continue
                col_texts.append(_column_text_row(text, is_heading=text.is_heading))

        col_images: list[str] = []
        for i, img in enumerate(section.images):
            if (i % col_count) + 1 == col_idx:
                col_images.append(_column_image_row(img, image_urls))

        content = _wrap_column_table(col_images + col_texts)
        if content:
            fills.append(SlotFill(f"col_{col_idx}", content))
    return fills


def _build_column_fills_from_groups(
    groups: list[ColumnGroup],
    *,
    image_urls: dict[str, str] | None = None,
) -> list[SlotFill]:
    """Build column fills from actual column groups (preserves design structure)."""
    fills: list[SlotFill] = []
    for group in groups:
        content = _build_column_fill_html(group, image_urls=image_urls)
        if content:
            fills.append(SlotFill(f"col_{group.column_idx}", content))
    return fills


def _build_column_fills_from_content_groups(
    groups: list[ContentGroup],
    *,
    image_urls: dict[str, str] | None = None,
) -> list[SlotFill]:
    """Build column fills from child content groups (one group per column)."""
    fills: list[SlotFill] = []
    for col_idx, group in enumerate(groups, 1):
        col_group = ColumnGroup(
            column_idx=col_idx,
            node_id=group.frame_node_id,
            node_name=group.frame_name,
            texts=group.texts,
            images=group.images,
            buttons=group.buttons,
        )
        content = _build_column_fill_html(col_group, image_urls=image_urls)
        if content:
            fills.append(SlotFill(f"col_{col_idx}", content))
    return fills


def _typography_overrides(
    texts: list[TextBlock],
    *,
    is_heading: bool,
    target: str,
) -> list[TokenOverride]:
    """Emit the typographic overrides from the first heading/body text.

    Covers font-weight / line-height / letter-spacing / text-transform /
    text-decoration, taken from the first heading- or body-class text that
    declares each property.

    Each property is sourced independently from the first text carrying it
    (mirroring the existing font/color blocks). ``letter-spacing: 0`` is the
    typographic no-op default and is skipped. Numeric values are rounded for
    readability; enum values are allowlist-validated. ``target`` is the slot the
    renderer dispatches on (``_heading`` / ``_body``).
    """
    overrides: list[TokenOverride] = []

    def _first(predicate: Callable[[TextBlock], bool]) -> TextBlock | None:
        return next((t for t in texts if t.is_heading == is_heading and predicate(t)), None)

    weight_text = _first(lambda t: t.font_weight is not None)
    if weight_text is not None and weight_text.font_weight is not None:
        overrides.append(TokenOverride("font-weight", target, str(weight_text.font_weight)))

    lh_text = _first(lambda t: t.line_height is not None)
    if lh_text is not None and lh_text.line_height is not None:
        overrides.append(TokenOverride("line-height", target, f"{round(lh_text.line_height)}px"))

    ls_text = _first(lambda t: t.letter_spacing not in (None, 0.0))
    if ls_text is not None and ls_text.letter_spacing is not None:
        overrides.append(TokenOverride("letter-spacing", target, f"{ls_text.letter_spacing:.2f}px"))

    tt_text = _first(lambda t: t.text_transform is not None)
    if tt_text is not None and tt_text.text_transform is not None:
        value = tt_text.text_transform.lower()
        if value in _ALLOWED_TEXT_TRANSFORM:
            overrides.append(TokenOverride("text-transform", target, value))

    td_text = _first(lambda t: t.text_decoration is not None)
    if td_text is not None and td_text.text_decoration is not None:
        value = td_text.text_decoration.lower()
        if value in _ALLOWED_TEXT_DECORATION:
            overrides.append(TokenOverride("text-decoration", target, value))

    return overrides


def _text_node_overrides(text: TextBlock) -> list[TokenOverride]:
    """Emit one node's own typography onto its ``_text_<node_id>`` anchor.

    RC-D-prime (phase-52.4b): pairs with the per-node ``<td data-node-id>``
    anchors from ``_per_node_body_html``. Validation and formatting mirror
    the shared-target blocks in ``_build_token_overrides`` byte-for-byte so
    the per-node and first-text paths cannot drift.
    """
    target = f"_text_{text.node_id}"
    out: list[TokenOverride] = []
    if text.font_family:
        out.append(TokenOverride("font-family", target, text.font_family))
    if text.font_size:
        out.append(TokenOverride("font-size", target, f"{text.font_size}px"))
    if text.text_color and _HEX_COLOR_RE.match(text.text_color):
        out.append(TokenOverride("color", target, text.text_color))
    align = text.text_align.lower() if text.text_align else None
    if align in ("left", "center", "right", "justify"):
        out.append(TokenOverride("text-align", target, align))
    if text.font_weight is not None:
        out.append(TokenOverride("font-weight", target, str(text.font_weight)))
    if text.line_height is not None:
        out.append(TokenOverride("line-height", target, f"{round(text.line_height)}px"))
    if text.letter_spacing is not None and text.letter_spacing != 0.0:
        out.append(TokenOverride("letter-spacing", target, f"{text.letter_spacing:.2f}px"))
    if text.text_transform is not None and text.text_transform.lower() in _ALLOWED_TEXT_TRANSFORM:
        out.append(TokenOverride("text-transform", target, text.text_transform.lower()))
    if (
        text.text_decoration is not None
        and text.text_decoration.lower() in _ALLOWED_TEXT_DECORATION
    ):
        out.append(TokenOverride("text-decoration", target, text.text_decoration.lower()))
    return out


def _cta_overrides(btn: ButtonElement, target: str) -> list[TokenOverride]:
    """Build CTA color/shape token overrides for a single button.

    Shared by the single-CTA path (``target="_cta"``) and the cta-pair path
    (``_cta_primary``/``_cta_secondary``) so the two cannot drift in which
    button properties they emit. Colors are ``_HEX_COLOR_RE``-guarded against
    CSS injection; numeric dimensions are coerced.
    """
    out: list[TokenOverride] = []
    if btn.fill_color and _HEX_COLOR_RE.match(btn.fill_color):
        out.append(TokenOverride("background-color", target, btn.fill_color))
    if btn.text_color and _HEX_COLOR_RE.match(btn.text_color):
        out.append(TokenOverride("color", target, btn.text_color))
    # Per-corner radius (G5) — mirror the image emitter's 4 longhands; falls back
    # to the scalar shorthand for the corpus (all buttons carry corner_radii:null).
    spec = getattr(btn, "corner_radius_spec", None)
    if spec is not None and spec.per_corner is not None:
        tl, tr, br, bl = spec.per_corner
        out.append(TokenOverride("border-top-left-radius", target, f"{tl:.0f}px"))
        out.append(TokenOverride("border-top-right-radius", target, f"{tr:.0f}px"))
        out.append(TokenOverride("border-bottom-right-radius", target, f"{br:.0f}px"))
        out.append(TokenOverride("border-bottom-left-radius", target, f"{bl:.0f}px"))
    elif btn.border_radius is not None:
        out.append(TokenOverride("border-radius", target, f"{btn.border_radius:.0f}px"))
    if btn.stroke_color and _HEX_COLOR_RE.match(btn.stroke_color):
        out.append(TokenOverride("border-color", target, btn.stroke_color))
    if btn.stroke_weight is not None:
        out.append(TokenOverride("border-width", target, f"{btn.stroke_weight:.0f}px"))
    return out


def _linear_gradient_css(gradient: ExtractedGradient) -> str | None:
    """CSS ``linear-gradient(...)`` for a reattached section gradient (53.3b).

    Linear only — radial/angular/diamond keep the solid fallback (ceiling doc
    §2). Every stop is hex-validated and positions are clamped to 0-100%, so
    the emitted value is CSS-injection-safe (matches the ``_HEX_COLOR_RE``
    guard on colors).
    """
    if gradient.type != "linear" or len(gradient.stops) < 2:
        return None
    stops: list[str] = []
    for hex_color, position in gradient.stops:
        if not _HEX_COLOR_RE.match(hex_color or ""):
            return None
        pct = max(0.0, min(100.0, float(position) * 100))
        stops.append(f"{hex_color} {pct:.0f}%")
    angle = float(gradient.angle) % 360
    return f"linear-gradient({angle:.0f}deg, {', '.join(stops)})"


def _build_token_overrides(
    section: EmailSection,
    *,
    gradients: list[ExtractedGradient] | None = None,
) -> list[TokenOverride]:
    """Extract token overrides from section properties."""
    overrides: list[TokenOverride] = []

    # Outer wrapper background (Phase 50.3 — wrapper-unwrap)
    if section.container_bg:
        overrides.append(TokenOverride("background-color", "_outer", section.container_bg))

    # Inner card background (Phase 50.4 — nested-card surface)
    if section.inner_bg:
        overrides.append(TokenOverride("background-color", "_inner", section.inner_bg))
    elif section.bg_color and not (section.container_bg and _is_white_hex(section.bg_color)):
        # No nested card detected — preserve Phase 49 contract (bg_color -> _outer).
        # Track G G1 (M3): a section's own WHITE fill must not paint over a
        # coloured band. A full-width image (or any section) on a coloured
        # wrapper inherits container_bg — the seed default #ffffff would
        # otherwise slit the band with white. A genuine white card carries
        # inner_bg (branch above), so this only suppresses the leak case.
        overrides.append(TokenOverride("background-color", "_outer", section.bg_color))

    # 53.3b — reattached gradient background (capture landed at 52.5). The
    # solid fallback goes first — it also stamps the MSO ``bgcolor`` attribute
    # (no VML gradient in v1) — then the CSS gradient for supporting clients.
    if section.gradient_ref and gradients:
        gradient = next((g for g in gradients if g.node_id == section.gradient_ref), None)
        if gradient is not None:
            has_solid = bool(section.container_bg or section.bg_color)
            if not has_solid and _HEX_COLOR_RE.match(gradient.fallback_hex or ""):
                overrides.append(TokenOverride("background-color", "_outer", gradient.fallback_hex))
            gradient_css = _linear_gradient_css(gradient)
            if gradient_css:
                overrides.append(TokenOverride("background-image", "_outer", gradient_css))

    # 53.5 — divider rule colour/thickness from the design's zero-area LINE
    # stroke (adopted onto the section by layout analysis). The divider seed
    # renders its rule as ``border-top`` on the ``divider-line`` element.
    if (
        section.section_type == EmailSectionType.DIVIDER
        and section.stroke_color
        and _HEX_COLOR_RE.match(section.stroke_color)
    ):
        weight = (
            section.stroke_weight if section.stroke_weight and section.stroke_weight > 0 else 1.0
        )
        # Sub-pixel design strokes floor to 1px — "0px solid" is an invisible rule.
        weight_px = max(1, round(weight))
        overrides.append(
            TokenOverride("border-top", "_divider", f"{weight_px}px solid {section.stroke_color}")
        )

    # Inner card border radius (Phase 50.4)
    if section.inner_radius is not None:
        overrides.append(TokenOverride("border-radius", "_inner", f"{section.inner_radius:.0f}px"))

    # Rule 11 (Phase 50.5) — fixed width on inner card from dominant image width.
    # Three emissions: width inline style, align="center" attr, class="wf" add.
    if section.inner_card_fixed_width is not None:
        width_px = f"{section.inner_card_fixed_width}px"
        overrides.append(TokenOverride("width", "_inner", width_px))
        overrides.append(TokenOverride("__html_attr_align", "_inner", "center"))
        overrides.append(TokenOverride("__html_attr_class_add", "_inner", "wf"))

    # Rule 10 (Phase 50.5) — per-corner image radii via 4 longhand emissions.
    for img in section.images:
        spec = img.corner_radius_spec
        if spec is None or spec.per_corner is None:
            continue
        tl, tr, br, bl = spec.per_corner
        target = f"_image_{img.node_id}"
        overrides.append(TokenOverride("border-top-left-radius", target, f"{tl:.0f}px"))
        overrides.append(TokenOverride("border-top-right-radius", target, f"{tr:.0f}px"))
        overrides.append(TokenOverride("border-bottom-right-radius", target, f"{br:.0f}px"))
        overrides.append(TokenOverride("border-bottom-left-radius", target, f"{bl:.0f}px"))

    # Pills render via captured text_color/font_weight + column y-order (Rule 8
    # radius, F10 content_order); no separate alignment slot is needed. The inert
    # Rule 7 tag-alignment path (a never-populated ``layout_align``) was retired
    # in G5/51.3 — see phase-53g-g5-tag-pill-slot.

    # Gap 11 (Phase 50.6) — text-align from the text-node's own attribute.
    for text in section.texts:
        align = text.text_align.lower() if text.text_align else None
        if text.is_heading and align in ("left", "center", "right", "justify"):
            overrides.append(TokenOverride("text-align", "_heading", align))
            break

    for text in section.texts:
        align = text.text_align.lower() if text.text_align else None
        if not text.is_heading and align in ("left", "center", "right", "justify"):
            overrides.append(TokenOverride("text-align", "_body", align))
            break

    # Font overrides from first heading text
    for text in section.texts:
        if text.is_heading and text.font_family:
            overrides.append(TokenOverride("font-family", "_heading", text.font_family))
            break

    for text in section.texts:
        if not text.is_heading and text.font_family:
            overrides.append(TokenOverride("font-family", "_body", text.font_family))
            break

    # Font-size overrides from typography
    for text in section.texts:
        if text.is_heading and text.font_size:
            overrides.append(TokenOverride("font-size", "_heading", f"{text.font_size}px"))
            break

    for text in section.texts:
        if not text.is_heading and text.font_size:
            overrides.append(TokenOverride("font-size", "_body", f"{text.font_size}px"))
            break

    # Text color overrides (validate hex to prevent CSS injection)
    for text in section.texts:
        if text.is_heading and text.text_color and _HEX_COLOR_RE.match(text.text_color):
            overrides.append(TokenOverride("color", "_heading", text.text_color))
            break

    for text in section.texts:
        if not text.is_heading and text.text_color and _HEX_COLOR_RE.match(text.text_color):
            overrides.append(TokenOverride("color", "_body", text.text_color))
            break

    # Typography overrides (Phase 52.4) — font-weight / line-height /
    # letter-spacing from the typography trio, plus text-transform /
    # text-decoration. First-heading / first-body targeting mirrors the
    # font/color blocks above; per-run targeting is deferred to 52.4b.
    # Each value is numerically coerced or allowlist-validated to prevent
    # CSS injection, matching the ``_HEX_COLOR_RE`` guard on colors.
    overrides.extend(_typography_overrides(section.texts, is_heading=True, target="_heading"))
    overrides.extend(_typography_overrides(section.texts, is_heading=False, target="_body"))

    # RC-D-prime (phase-52.4b) — per-node typography. _fills_text_block emits one
    # <td data-node-id> anchor per body text when a section carries >=2; these
    # overrides give each node its own typography instead of flattening every
    # run onto the first body's values. The first-match blocks above keep
    # styling the seed's shared heading/body slots.
    for text in _per_node_body_texts(section):
        overrides.extend(_text_node_overrides(text))

    # Padding overrides — 4-side shorthand when fully specified; per-side
    # longhands otherwise (RC-D-prime: the all-or-nothing shorthand silently
    # dropped partial padding, and a <4-part join would mis-assign sides).
    sides = (
        ("padding-top", section.padding_top),
        ("padding-right", section.padding_right),
        ("padding-bottom", section.padding_bottom),
        ("padding-left", section.padding_left),
    )
    present = [(prop, val) for prop, val in sides if val is not None]
    if len(present) == 4:
        overrides.append(
            TokenOverride("padding", "_cell", " ".join(f"{int(val)}px" for _, val in present))
        )
    else:
        for prop, val in present:
            overrides.append(TokenOverride(prop, "_cell", f"{int(val)}px"))

    # CTA button overrides.
    if section.buttons:
        # Single-CTA path keeps the _cta target (cta-button seed). Retained in
        # the dual case too as a harmless no-op fallback: cta-pair routing only
        # fires for EmailSectionType.CTA, so a non-cta-pair seed that happens to
        # carry cta-btn/cta_url markers still gets buttons[0]'s color.
        overrides.extend(_cta_overrides(section.buttons[0], "_cta"))
        if len(section.buttons) >= 2:
            # phase-53-b8-cta-pair-color-fidelity: the cta-pair seed renders two
            # independently-styled buttons (class="cta" + data-slot=
            # primary_url/secondary_url) that the _cta helpers do not match, so
            # the _cta override above is a no-op there. Emit per-button overrides
            # scoped to each button's class so the primary (filled) and secondary
            # (outlined) buttons render in their own Figma colors.
            overrides.extend(_cta_overrides(section.buttons[0], "_cta_primary"))
            overrides.extend(_cta_overrides(section.buttons[1], "_cta_secondary"))

    return overrides
