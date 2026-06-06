"""Bridge design-sync ComponentMatch output to EmailTree (Phase 48.6 schema)."""

from __future__ import annotations

import re

from app.components.tree_schema import (
    ButtonSlot,
    EmailTree,
    HtmlSlot,
    ImageSlot,
    SlotValue,
    TextSlot,
    TreeMetadata,
    TreeSection,
)
from app.core.logging import get_logger
from app.design_sync.component_matcher import ComponentMatch, SlotFill, TokenOverride
from app.design_sync.figma.layout_analyzer import (
    DesignLayoutDescription,
    EmailSection,
    EmailSectionType,
)
from app.design_sync.protocol import ExtractedTokens
from app.design_sync.sibling_detector import RepeatingGroup

logger = get_logger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Hex color pattern for validation
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def build_email_tree(
    layout: DesignLayoutDescription,
    matches: list[ComponentMatch],
    tokens: ExtractedTokens,
    *,
    groups: list[EmailSection | RepeatingGroup] | None = None,  # noqa: ARG001
    group_map: dict[int, RepeatingGroup] | None = None,
    subject: str = "",
) -> EmailTree:
    """Convert design-sync matches into an EmailTree for TreeCompiler."""
    preheader = _extract_preheader(layout)
    design_tokens = _build_design_tokens(tokens)

    metadata = TreeMetadata(
        subject=subject or "Untitled",
        preheader=preheader,
        design_tokens=design_tokens,
    )

    sections: list[TreeSection] = []
    rendered_group_ids: set[int] = set()

    for flat_idx, match in enumerate(matches):
        group = group_map.get(flat_idx) if group_map else None

        if group is not None:
            if id(group) in rendered_group_ids:
                continue
            rendered_group_ids.add(id(group))

            # Collect all matches belonging to this group
            children: list[TreeSection] = []
            for inner_idx, inner_match in enumerate(matches):
                if group_map and group_map.get(inner_idx) is group:
                    children.append(_match_to_tree_section(inner_match))

            # Wrapper section with children
            style_overrides: dict[str, str] = {}
            if group.container_bgcolor:
                style_overrides["background-color"] = group.container_bgcolor

            # Use the first child's slug as the wrapper slug
            wrapper_slug = children[0].component_slug if children else "__custom__"
            sections.append(
                TreeSection(
                    component_slug=wrapper_slug,
                    style_overrides=style_overrides,
                    children=children,
                )
            )
        else:
            sections.append(_match_to_tree_section(match))

    if not sections:
        logger.warning("tree_bridge.empty_sections", msg="No sections to build tree from")
        # EmailTree requires min_length=1, create a placeholder
        sections = [
            TreeSection(
                component_slug="__custom__",
                custom_html="<!-- empty design -->",
            )
        ]

    return EmailTree(metadata=metadata, sections=sections)


def _match_to_tree_section(match: ComponentMatch) -> TreeSection:
    """Convert a single ComponentMatch into a TreeSection."""
    return TreeSection(
        component_slug=match.component_slug,
        slot_fills=_convert_slot_fills(match.slot_fills, match.section),
        style_overrides=_convert_token_overrides(match.token_overrides),
    )


def _convert_slot_fills(
    fills: list[SlotFill],
    section: EmailSection,
) -> dict[str, SlotValue]:
    """Map SlotFill list to typed SlotValue dict keyed by slot_id.

    ``{stem}_alt`` fills are folded into the paired image fill's
    ``attr_overrides["alt"]`` rather than emitted as standalone slots:
    ``TreeCompiler`` scans ``data-slot="..."`` only, so emitting
    ``image_alt`` / ``logo_alt`` as independent slots would fail manifest
    cross-validation. Merging them upstream keeps a single ``ImageSlot`` per
    image with the correct alt attribute.
    """
    alt_by_target: dict[str, str] = {}
    id_to_fill: dict[str, SlotFill] = {f.slot_id: f for f in fills}
    skipped_alt_ids: set[str] = set()

    for fill in fills:
        if not fill.slot_id.endswith("_alt"):
            continue
        paired_id = _paired_image_slot_id(fill.slot_id, id_to_fill)
        if paired_id is None:
            continue
        alt_by_target[paired_id] = fill.value
        skipped_alt_ids.add(fill.slot_id)

    result: dict[str, SlotValue] = {}
    for fill in fills:
        if fill.slot_id in skipped_alt_ids:
            continue
        if fill.slot_id in alt_by_target and fill.slot_type == "image":
            merged_attrs = {**fill.attr_overrides, "alt": alt_by_target[fill.slot_id]}
            fill = SlotFill(fill.slot_id, fill.value, fill.slot_type, merged_attrs)
        slot_value = _fill_to_slot_value(fill, section)
        if slot_value is not None:
            result[fill.slot_id] = slot_value
    return result


_ALT_PAIR_SUFFIXES: tuple[str, ...] = ("_url", "_image")


def _paired_image_slot_id(
    alt_slot_id: str,
    id_to_fill: dict[str, SlotFill],
) -> str | None:
    """Resolve an ``{stem}_alt`` slot to its paired image slot id.

    Returns ``None`` when no paired image slot is present or when the paired
    slot's type is not ``image``.
    """
    stem = alt_slot_id[: -len("_alt")]
    for suffix in _ALT_PAIR_SUFFIXES:
        candidate = stem + suffix
        paired = id_to_fill.get(candidate)
        if paired is not None and paired.slot_type == "image":
            return candidate
    return None


def _fill_to_slot_value(fill: SlotFill, section: EmailSection) -> SlotValue | None:
    """Convert a single SlotFill to its typed SlotValue."""
    if fill.slot_type == "text":
        text = _HTML_TAG_RE.sub("", fill.value).strip()
        if not text:
            text = fill.value.strip() or "text"
        return TextSlot(text=text)

    if fill.slot_type == "image":
        width = _clamp_dimension(fill.attr_overrides.get("width", "600"))
        height = _clamp_dimension(fill.attr_overrides.get("height", "400"))
        return ImageSlot(
            src=fill.value,
            alt=fill.attr_overrides.get("alt", ""),
            width=width,
            height=height,
        )

    if fill.slot_type == "cta":
        text = _extract_cta_text(fill, section)
        bg_color = _extract_button_color(fill, section)
        text_color = _extract_button_text_color(fill, section)
        return ButtonSlot(
            text=text,
            href=fill.value or "https://example.com",
            bg_color=bg_color,
            text_color=text_color,
        )

    if fill.slot_type == "attr":
        if fill.value.strip():
            return HtmlSlot(html=fill.value)
        return None

    # Unknown slot type — log and use HtmlSlot fallback
    logger.warning(
        "tree_bridge.unknown_slot_type",
        slot_type=fill.slot_type,
        slot_id=fill.slot_id,
    )
    if fill.value.strip():
        return HtmlSlot(html=fill.value)
    return None


def _extract_cta_text(fill: SlotFill, section: EmailSection) -> str:
    """Extract button text from attr_overrides, section buttons, or fallback."""
    text = fill.attr_overrides.get("text", "")
    if text:
        return text
    if section.buttons:
        return section.buttons[0].text or "Click here"
    return "Click here"


def _extract_button_color(fill: SlotFill, section: EmailSection) -> str:
    """Extract button background color from attr_overrides or section buttons."""
    color = fill.attr_overrides.get("bg_color", "")
    if color and _HEX_COLOR_RE.match(color):
        return color
    if section.buttons and section.buttons[0].fill_color:
        fc = section.buttons[0].fill_color
        if _HEX_COLOR_RE.match(fc):
            return fc
    return "#000000"


def _extract_button_text_color(fill: SlotFill, section: EmailSection) -> str:
    """Extract button text color from attr_overrides or fallback."""
    color = fill.attr_overrides.get("text_color", "")
    if color and _HEX_COLOR_RE.match(color):
        return color
    if section.buttons and section.buttons[0].text_color:
        tc = section.buttons[0].text_color
        if _HEX_COLOR_RE.match(tc):
            return tc
    return "#FFFFFF"


def _convert_token_overrides(overrides: list[TokenOverride]) -> dict[str, str]:
    """Convert TokenOverride list to style_overrides dict (last wins)."""
    return {o.css_property: o.value for o in overrides}


def _build_design_tokens(tokens: ExtractedTokens) -> dict[str, dict[str, str]]:
    """Build design_tokens dict for TreeMetadata."""
    result: dict[str, dict[str, str]] = {}

    colors = {c.name: c.hex for c in tokens.colors if c.name and c.hex}
    if colors:
        result["colors"] = colors

    typography = {t.name: t.family for t in tokens.typography if t.name and t.family}
    if typography:
        result["typography"] = typography

    dark_palette = {c.name: c.hex for c in tokens.dark_colors if c.name and c.hex}
    if dark_palette:
        result["dark_palette"] = dark_palette

    return result


def _extract_preheader(layout: DesignLayoutDescription) -> str:
    """Extract preheader text from the first PREHEADER section."""
    for section in layout.sections:
        if section.section_type == EmailSectionType.PREHEADER and section.texts:
            return section.texts[0].content[:250]
    return ""


def _clamp_dimension(value: str | int | float) -> int:
    """Parse and clamp a dimension value to 1-2000."""
    try:
        n = int(float(str(value)))
    except (ValueError, TypeError):
        return 600
    return max(1, min(2000, n))
