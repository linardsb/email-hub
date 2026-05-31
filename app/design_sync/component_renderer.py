"""Render EmailSections using pre-built component HTML templates with slot filling."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.design_sync.component_matcher import ComponentMatch, SlotFill, TokenOverride
from app.design_sync.sibling_detector import RepeatingGroup

logger = get_logger(__name__)

_PLACEHOLDER_IN_OUTPUT_RE = re.compile(
    r'data-slot="([^"]*)"[^>]*>'
    r"\s*(?:Section Heading|Editorial heading|Image caption|Lorem ipsum)",
    re.IGNORECASE,
)

# Lazy-loaded to avoid circular imports
_seed_cache: dict[str, dict[str, Any]] | None = None


def _load_seeds() -> dict[str, dict[str, Any]]:
    """Load component seeds by slug. Cached on first call."""
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache

    from app.components.data.seeds import COMPONENT_SEEDS

    _seed_cache = {seed["slug"]: seed for seed in COMPONENT_SEEDS}
    return _seed_cache


@dataclass(frozen=True)
class RenderedSection:
    """A rendered component section ready for assembly."""

    html: str
    component_slug: str
    section_idx: int
    dark_mode_classes: tuple[str, ...] = ()
    images: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    propagated_bgcolor: str | None = None


@dataclass(frozen=True)
class _GroupSpacing:
    """Resolved padding for items within a repeating group."""

    first_top: int
    subsequent_top: int
    horizontal: int


def _resolve_item_spacing(group: RepeatingGroup) -> _GroupSpacing:
    """Derive item spacing from group metadata or section padding."""
    if group.container_padding is not None:
        top, right, _bottom, _left = group.container_padding
        return _GroupSpacing(first_top=int(top), subsequent_top=int(top), horizontal=int(right))

    # Infer from first section's padding
    first = group.sections[0]
    top = int(first.padding_top if first.padding_top is not None else 20)
    _horiz_candidate = (
        first.padding_right
        if first.padding_right is not None
        else (first.padding_left if first.padding_left is not None else 24)
    )
    horiz = int(_horiz_candidate)
    subsequent = int(first.item_spacing if first.item_spacing is not None else 16)
    return _GroupSpacing(first_top=top, subsequent_top=subsequent, horizontal=horiz)


# --- Token override element-type expansion (49.4) ---

# Heading-like data-slot values
_HEADING_SLOTS = r"heading|headline|title"
# Body-like data-slot values
_BODY_SLOTS = r"body|body_text|description|caption|subtext"

# Heading-like semantic CSS classes
_HEADING_CLASSES = (
    "hero-title",
    "textblock-heading",
    "artcard-heading",
    "product-title",
    "col-icon-heading",
    "event-name",
)
# Body-like semantic CSS classes
_BODY_CLASSES = (
    "hero-subtitle",
    "textblock-body",
    "artcard-body",
    "product-desc",
    "col-icon-body",
    "event-detail",
    "imgblock-caption",
)

_HEADING_CLASS_ALT = "|".join(re.escape(c) for c in _HEADING_CLASSES)
_BODY_CLASS_ALT = "|".join(re.escape(c) for c in _BODY_CLASSES)

# Pass 1: data-slot match (covers all heading/body slot naming variants)
_HEADING_SLOT_FONT_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_HEADING_SLOTS})"[^>]*style="[^"]*?)'
    r"font-family:\s*[^;\"]+([;\"\'])"
)
_BODY_SLOT_FONT_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_BODY_SLOTS})"[^>]*style="[^"]*?)'
    r"font-family:\s*[^;\"]+([;\"\'])"
)
_HEADING_SLOT_COLOR_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_HEADING_SLOTS})"[^>]*style="[^"]*?)'
    r"(?<!-)color:\s*[^;\"]+([;\"\'])"
)
_BODY_SLOT_COLOR_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_BODY_SLOTS})"[^>]*style="[^"]*?)'
    r"(?<!-)color:\s*[^;\"]+([;\"\'])"
)
_HEADING_SLOT_SIZE_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_HEADING_SLOTS})"[^>]*style="[^"]*?)'
    r"font-size:\s*[^;\"]+([;\"\'])"
)
_BODY_SLOT_SIZE_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_BODY_SLOTS})"[^>]*style="[^"]*?)'
    r"font-size:\s*[^;\"]+([;\"\'])"
)

# Pass 2: semantic class match (elements without data-slot)
_HEADING_CLASS_FONT_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_HEADING_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"font-family:\s*[^;\"]+([;\"\'])"
)
_BODY_CLASS_FONT_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_BODY_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"font-family:\s*[^;\"]+([;\"\'])"
)
_HEADING_CLASS_COLOR_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_HEADING_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"(?<!-)color:\s*[^;\"]+([;\"\'])"
)
_BODY_CLASS_COLOR_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_BODY_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"(?<!-)color:\s*[^;\"]+([;\"\'])"
)
_HEADING_CLASS_SIZE_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_HEADING_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"font-size:\s*[^;\"]+([;\"\'])"
)
_BODY_CLASS_SIZE_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_BODY_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"font-size:\s*[^;\"]+([;\"\'])"
)

# text-align replace + inject (Gap 11 / Phase 50.6). Seeds rarely declare
# ``text-align`` on the heading/body cell, so each target needs a two-pass
# replace-or-inject like the ``_inner`` background helpers.
_HEADING_SLOT_ALIGN_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_HEADING_SLOTS})"[^>]*style="[^"]*?)'
    r"text-align:\s*[^;\"]+([;\"\'])"
)
_BODY_SLOT_ALIGN_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_BODY_SLOTS})"[^>]*style="[^"]*?)'
    r"text-align:\s*[^;\"]+([;\"\'])"
)
_HEADING_CLASS_ALIGN_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_HEADING_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"text-align:\s*[^;\"]+([;\"\'])"
)
_BODY_CLASS_ALIGN_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_BODY_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"text-align:\s*[^;\"]+([;\"\'])"
)
_HEADING_SLOT_ALIGN_INSERT_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_HEADING_SLOTS})"[^>]*style=")'
    r'(?![^"]*text-align:)'
)
_BODY_SLOT_ALIGN_INSERT_RE = re.compile(
    rf'(<td\b[^>]*data-slot="(?:{_BODY_SLOTS})"[^>]*style=")'
    r'(?![^"]*text-align:)'
)
_HEADING_CLASS_ALIGN_INSERT_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_HEADING_CLASS_ALT})[^"]*"[^>]*style=")'
    r'(?![^"]*text-align:)'
)
_BODY_CLASS_ALIGN_INSERT_RE = re.compile(
    rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{_BODY_CLASS_ALT})[^"]*"[^>]*style=")'
    r'(?![^"]*text-align:)'
)

# Allowed text-align values — defends the renderer against CSS injection even
# though the matcher already constrains the emitted override.
_ALLOWED_TEXT_ALIGN = frozenset({"left", "center", "right", "justify"})


@dataclass(frozen=True)
class _PropRegexSet:
    """Replace + inject regex pair for one CSS prop on heading or body targets.

    Phase 52.4 typography helpers. ``slot_replace``/``class_replace`` rewrite an
    existing declaration; ``slot_insert``/``class_insert`` add one when absent,
    guarded by a negative lookahead so a cell matched by both ``data-slot`` and
    ``class`` is never injected twice.
    """

    slot_replace: re.Pattern[str]
    class_replace: re.Pattern[str]
    slot_insert: re.Pattern[str]
    class_insert: re.Pattern[str]


def _prop_regex_set(prop: str, *, slot_alt: str, class_alt: str) -> _PropRegexSet:
    """Build the replace-or-inject regex set for ``prop`` on one target group.

    Mirrors the hand-written ``text-align`` machinery (slot replace, class
    replace, slot insert, class insert) so the typography props reuse one
    parametrised builder instead of four literal regexes each.
    """
    p = re.escape(prop)
    return _PropRegexSet(
        slot_replace=re.compile(
            rf'(<td\b[^>]*data-slot="(?:{slot_alt})"[^>]*style="[^"]*?)'
            rf"{p}:\s*[^;\"]+([;\"\'])"
        ),
        class_replace=re.compile(
            rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{class_alt})[^"]*"[^>]*style="[^"]*?)'
            rf"{p}:\s*[^;\"]+([;\"\'])"
        ),
        slot_insert=re.compile(
            rf'(<td\b[^>]*data-slot="(?:{slot_alt})"[^>]*style=")' rf'(?![^"]*{p}:)'
        ),
        class_insert=re.compile(
            rf'(<(?:td|th|a|span)\b[^>]*class="[^"]*(?:{class_alt})[^"]*"[^>]*style=")'
            rf'(?![^"]*{p}:)'
        ),
    )


# Typography props applied to heading/body cells (Phase 52.4). Each maps to a
# replace-or-inject regex set per target group, built once at import time.
_TYPOGRAPHY_PROPS = (
    "font-weight",
    "line-height",
    "letter-spacing",
    "text-transform",
    "text-decoration",
)
_HEADING_PROP_RE: dict[str, _PropRegexSet] = {
    prop: _prop_regex_set(prop, slot_alt=_HEADING_SLOTS, class_alt=_HEADING_CLASS_ALT)
    for prop in _TYPOGRAPHY_PROPS
}
_BODY_PROP_RE: dict[str, _PropRegexSet] = {
    prop: _prop_regex_set(prop, slot_alt=_BODY_SLOTS, class_alt=_BODY_CLASS_ALT)
    for prop in _TYPOGRAPHY_PROPS
}

# Validators for the 52.4 typography props. ``font-weight``/``line-height`` are
# unsigned; ``letter-spacing`` may be negative (e.g. ``-0.32px`` from tight
# tracking). Enum props use allowlists. A value failing its check is dropped so
# malformed design data can never reach rendered CSS.
_FONT_WEIGHT_VALUE_RE = re.compile(r"^[1-9]\d{0,3}$")
_LINE_HEIGHT_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?px$")
_LETTER_SPACING_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?px$")
_ALLOWED_TEXT_TRANSFORM = frozenset({"uppercase", "lowercase", "capitalize", "none"})
_ALLOWED_TEXT_DECORATION = frozenset({"underline", "line-through", "none", "overline"})

# Background container classes on outer <table>
_BG_CLASSES = (
    "textblock-bg",
    "artcard-bg",
    "col2-bg",
    "col3-bg",
    "col4-bg",
    "revcol-bg",
    "header-bg",
    "footer-bg",
    "navbar-bg",
    "logoheader-bg",
    "social-bg",
    "preheader-bg",
)
_BG_CLASS_ALT = "|".join(re.escape(c) for c in _BG_CLASSES)
_BG_CLASS_BGCOLOR_RE = re.compile(
    rf'(<(?:table|td)\b[^>]*class="[^"]*(?:{_BG_CLASS_ALT})[^"]*"[^>]*style="[^"]*?)'
    r"background-color:\s*[^;\"]+([;\"\'])"
)

# Outer/inner card surface targeting (Phase 50.4) — matches class="_outer" or
# class="_inner" exactly to avoid accidental matches against other tokens.
# Whitespace tokenisation lets the class share a slot with siblings.
_OUTER_CLASS_PRESENT_RE = re.compile(r'<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_outer(?:\s[^"]*)?"')
_OUTER_CLASS_BGCOLOR_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_outer(?:\s[^"]*)?"[^>]*style="[^"]*?)'
    r"background-color:\s*[^;\"]+([;\"\'])"
)
_OUTER_CLASS_BG_INSERT_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_outer(?:\s[^"]*)?"[^>]*style=")'
    r'(?![^"]*background-color:)'
)
_INNER_CLASS_BGCOLOR_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style="[^"]*?)'
    r"background-color:\s*[^;\"]+([;\"\'])"
)
_INNER_CLASS_BG_INSERT_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style=")'
    r'(?![^"]*background-color:)'
)
_INNER_CLASS_RADIUS_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style="[^"]*?)'
    r"border-radius:\s*[^;\"]+([;\"\'])"
)
_INNER_CLASS_RADIUS_INSERT_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style=")'
    r'(?![^"]*border-radius:)'
)
# Rule 11 (Phase 50.5) — width / align attr / class-add helpers on ``_inner``.
_INNER_CLASS_WIDTH_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style="[^"]*?)'
    r"(?<!max-)(?<!min-)width:\s*[^;\"]+([;\"\'])"
)
_INNER_CLASS_WIDTH_INSERT_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*style=")'
    r'(?![^"]*(?<!max-)(?<!min-)width:)'
)
_INNER_CLASS_ELEMENT_RE = re.compile(
    r'(<(?:table|td)\b)((?:(?!\balign=)[^>])*?\bclass="(?:[^"]*\s)?_inner(?:\s[^"]*)?")'
    r"((?:(?!\balign=)[^>])*?)(/?>)"
)
_INNER_CLASS_ALIGN_REPLACE_RE = re.compile(
    r'(<(?:table|td)\b[^>]*class="(?:[^"]*\s)?_inner(?:\s[^"]*)?"[^>]*?)'
    r'\balign="[^"]*"'
)
_INNER_CLASS_ATTR_RE = re.compile(
    r'(<(?:table|td)\b[^>]*\bclass=")((?:[^"]*\s)?_inner(?:\s[^"]*)?)(")'
)

_SLOT_ATTR_RE = re.compile(r'data-slot="([^"]+)"')


def _validate_slot_fill_rate(
    template_html: str,
    slot_fills: list[SlotFill],
) -> tuple[float, list[str]]:
    """Check what fraction of template slots were filled.

    Returns (fill_rate, warnings). Warns if < 50% of slots are filled.
    """
    slot_ids = set(_SLOT_ATTR_RE.findall(template_html))
    total = len(slot_ids)
    if total == 0:
        return 1.0, []
    filled = sum(1 for f in slot_fills if f.slot_id in slot_ids)
    rate = filled / total
    warnings: list[str] = []
    if rate < 0.5:
        warnings.append(f"Low slot fill rate ({filled}/{total} = {rate:.0%})")
    return rate, warnings


class ComponentRenderer:
    """Render matched sections using component seed HTML templates."""

    def __init__(self, container_width: int = 600) -> None:
        self._container_width = container_width
        self._templates: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        """Load component templates from COMPONENT_SEEDS."""
        if self._loaded:
            return
        seeds = _load_seeds()
        for slug, seed in seeds.items():
            html_source = seed.get("html_source", "")
            if html_source:
                self._templates[slug] = html_source
        self._loaded = True

    def render_section(self, match: ComponentMatch) -> RenderedSection:
        """Render a single matched section using its component template."""
        if not self._loaded:
            self.load()

        template_html = self._templates.get(match.component_slug)
        if template_html is None:
            logger.warning(
                "design_sync.component_renderer_missing_template",
                slug=match.component_slug,
            )
            return self._fallback_render(match)

        result_html = template_html

        # 1. Fill slots with Figma content
        result_html = self._fill_slots(result_html, match.slot_fills, match.component_slug)

        # 1b. Validate slot fill rate
        _fill_rate, fill_warnings = _validate_slot_fill_rate(template_html, match.slot_fills)
        for warn in fill_warnings:
            logger.warning(
                "design_sync.low_slot_fill_rate",
                slug=match.component_slug,
                section_idx=match.section_idx,
                message=warn,
            )

        # 2. Apply token overrides (inline style replacement)
        result_html = self._apply_token_overrides(result_html, match.token_overrides)

        # 3. Update MSO table widths to match container width
        result_html = self._update_mso_widths(result_html, self._container_width)

        # 4. Strip remaining placeholder URLs
        result_html = self._strip_placeholder_urls(result_html)

        # 5. Add builder annotations
        result_html = self._add_annotations(result_html, match)

        # 6. Extract dark mode classes and image metadata
        dark_classes = self._extract_dark_mode_classes(result_html)
        images = self._extract_images(result_html)

        # Stamp a dark-mode-class hook so Track 41.3's text-color inversion
        # can see the wrapper fill on the section. Phase 50.4 applies the
        # actual bgcolor via the ``_outer`` token override path; the class
        # name keeps the existing inversion contract working.
        container_bg = match.section.container_bg
        if container_bg:
            safe = container_bg.lstrip("#").upper()
            dark_classes.append(f"bgcolor-{safe}")

        return RenderedSection(
            html=result_html,
            component_slug=match.component_slug,
            section_idx=match.section_idx,
            dark_mode_classes=tuple(dark_classes),
            images=images,
        )

    def render_all(self, matches: list[ComponentMatch]) -> list[RenderedSection]:
        """Render all matched sections."""
        if not self._loaded:
            self.load()
        return [self.render_section(m) for m in matches]

    def render_repeating_group(
        self,
        group: RepeatingGroup,
        matches: list[ComponentMatch],
    ) -> RenderedSection:
        """Render a repeating group as N instances wrapped in a container table."""
        if not self._loaded:
            self.load()

        if not matches:
            return RenderedSection(
                html="",
                component_slug="repeating-group",
                section_idx=0,
                dark_mode_classes=(),
                images=[],
            )

        # Single-section group: render without wrapper
        if len(matches) == 1:
            return self.render_section(matches[0])

        # Render each inner section individually
        rendered_items: list[RenderedSection] = []
        for match in matches:
            rendered_items.append(self.render_section(match))

        # Determine spacing
        item_spacing = _resolve_item_spacing(group)

        # Build inner rows
        rows: list[str] = []
        all_dark_classes: set[str] = set()
        all_images: list[dict[str, str]] = []

        for i, rendered in enumerate(rendered_items):
            top_px = item_spacing.first_top if i == 0 else item_spacing.subsequent_top
            padding = f"{top_px}px {item_spacing.horizontal}px 0"
            rows.append(
                f'<tr>\n  <td style="padding:{padding}">\n    {rendered.html}\n  </td>\n</tr>'
            )
            all_dark_classes.update(rendered.dark_mode_classes)
            all_images.extend(rendered.images)

        rows_html = "\n".join(rows)

        # Container bgcolor
        bgcolor = group.container_bgcolor or ""
        bgcolor_attr = f' bgcolor="{bgcolor}"' if bgcolor else ""
        bgcolor_style = f"background-color:{bgcolor};" if bgcolor else ""

        # Dark mode class for container bgcolor
        container_dm_class = ""
        if bgcolor:
            safe = bgcolor.lstrip("#").upper()
            container_dm_class = f"bgcolor-{safe}"
            all_dark_classes.add(container_dm_class)

        class_attr = f' class="{container_dm_class}"' if container_dm_class else ""

        # Container width
        container_width = self._container_width

        # Build wrapped HTML with MSO ghost table
        wrapped = (
            f"<!--[if mso]>\n"
            f'<table role="presentation" width="{container_width}" align="center" '
            f'cellpadding="0" cellspacing="0" border="0"><tr><td>\n'
            f"<![endif]-->\n"
            f'<table role="presentation"{class_attr} width="100%" '
            f'cellpadding="0" cellspacing="0" border="0" '
            f'style="{bgcolor_style}"{bgcolor_attr}>\n'
            f"{rows_html}\n"
            f"</table>\n"
            f"<!--[if mso]>\n"
            f"</td></tr></table>\n"
            f"<![endif]-->"
        )

        return RenderedSection(
            html=wrapped,
            component_slug="repeating-group",
            section_idx=matches[0].section_idx,
            dark_mode_classes=tuple(sorted(all_dark_classes)),
            images=all_images,
        )

    def _fill_slots(
        self,
        template_html: str,
        fills: list[SlotFill],
        slug: str,
    ) -> str:
        """Fill data-slot elements with content using regex-based replacement.

        Uses regex instead of lxml to preserve MSO conditional comments
        which lxml would strip.
        """
        result = template_html

        for fill in fills:
            slot_id = fill.slot_id

            # Special: spacer_height modifies style attributes, not text content
            if slug == "spacer" and slot_id == "spacer_height":
                result = self._fill_spacer_height(result, fill.value)
                continue

            # Special: hero_image modifies background-image URL + VML src
            if slug == "hero-block" and slot_id == "hero_image":
                result = self._fill_hero_image(result, fill.value)
                continue

            # Special: image-block has no data-slot attrs — replace placeholder src directly
            if slug == "image-block" and slot_id == "image_url":
                safe_url = html.escape(fill.value)
                result = re.sub(
                    r'(<img\b[^>]*\bsrc=")[^"]*(")',
                    rf"\g<1>{safe_url}\g<2>",
                    result,
                    count=1,
                )
                continue
            if slug == "image-block" and slot_id == "image_alt":
                safe_alt = html.escape(fill.value)
                result = re.sub(
                    r'(<img\b[^>]*\balt=")[^"]*(")',
                    rf"\g<1>{safe_alt}\g<2>",
                    result,
                    count=1,
                )
                continue

            if fill.slot_type == "image":
                result = self._fill_image_slot(result, slot_id, fill)
            elif fill.slot_type == "cta":
                result = self._fill_cta_slot(result, slot_id, fill)
            else:
                result = self._fill_text_slot(result, slot_id, fill)

        # Warn on known placeholder patterns surviving in output
        for m in _PLACEHOLDER_IN_OUTPUT_RE.finditer(result):
            logger.warning(
                "design_sync.renderer.placeholder_in_output",
                slot_id=m.group(1),
                component_slug=slug,
            )

        return result

    def _fill_text_slot(self, html_str: str, slot_id: str, fill: SlotFill) -> str:
        """Replace text content of a data-slot element.

        Extracts the tag name from the opening element and matches the
        corresponding closing tag so that nested child elements (e.g.
        ``<a>`` inside a ``<td>``) don't cause a premature match.
        """
        # Step 1: find the opening tag with data-slot to learn the tag name
        open_pattern = rf'<(\w+)\b[^>]*\bdata-slot="{re.escape(slot_id)}"[^>]*>'
        open_match = re.search(open_pattern, html_str)
        if not open_match:
            # Fallback: try <span data-slot="..."> (for nested cta_text spans)
            span_pattern = (
                rf'(<span\b[^>]*\bdata-slot="{re.escape(slot_id)}"[^>]*>)'
                r"(.*?)"
                r"(</span>)"
            )
            return re.sub(
                span_pattern,
                rf"\g<1>{fill.value}\g<3>",
                html_str,
                count=1,
                flags=re.DOTALL,
            )

        tag_name = open_match.group(1)
        # Step 2: match opening tag → content → matching closing tag
        pattern = (
            rf'(<{tag_name}\b[^>]*\bdata-slot="{re.escape(slot_id)}"[^>]*>)'
            rf"(.*?)"
            rf"(</{tag_name}>)"
        )
        replacement = rf"\g<1>{fill.value}\g<3>"
        return re.sub(pattern, replacement, html_str, count=1, flags=re.DOTALL)

    def _fill_image_slot(self, html_str: str, slot_id: str, fill: SlotFill) -> str:
        """Update src (and optionally width/height/alt) on a data-slot image element."""
        # Find the img tag with this data-slot
        pattern = rf'(<img\b[^>]*\bdata-slot="{re.escape(slot_id)}"[^>]*/?>)'
        match = re.search(pattern, html_str)
        if not match:
            return html_str

        img_tag = match.group(1)
        new_tag = img_tag

        # Replace src
        new_tag = re.sub(r'\bsrc="[^"]*"', f'src="{html.escape(fill.value)}"', new_tag)

        # Apply attr_overrides — update existing attributes or insert new ones
        for attr, val in fill.attr_overrides.items():
            if re.search(rf'\b{attr}="[^"]*"', new_tag):
                new_tag = re.sub(rf'\b{attr}="[^"]*"', f'{attr}="{html.escape(val)}"', new_tag)
            else:
                # Insert the attribute before the closing /> or >
                new_tag = re.sub(r"(\s*/?>)$", f' {attr}="{html.escape(val)}"\\1', new_tag)

        return html_str.replace(img_tag, new_tag, 1)

    def _fill_cta_slot(self, html_str: str, slot_id: str, fill: SlotFill) -> str:
        """Update href on a data-slot link element."""
        # Match: <a data-slot="slot_id" href="..." ...>
        pattern = rf'(<a\b[^>]*\bdata-slot="{re.escape(slot_id)}"[^>]*>)'
        match = re.search(pattern, html_str)
        if not match:
            return html_str

        a_tag = match.group(1)
        new_tag = re.sub(r'\bhref="[^"]*"', f'href="{html.escape(fill.value)}"', a_tag)
        return html_str.replace(a_tag, new_tag, 1)

    def _fill_spacer_height(self, html_str: str, height: str) -> str:
        """Update spacer height in both MSO table and non-MSO div."""
        h = int(height) if height.isdigit() else 32
        # MSO: height="N" and style="...height:Npx..."
        result = re.sub(r'height="32"', f'height="{h}"', html_str)
        # Non-MSO div: style with height/line-height
        result = re.sub(r"height:\s*32px", f"height:{h}px", result)
        result = re.sub(r"line-height:\s*32px", f"line-height:{h}px", result)
        return result

    def _fill_hero_image(self, html_str: str, image_url: str) -> str:
        """Update hero background image URL in both CSS and VML."""
        safe_url = html.escape(image_url)
        # CSS: background-image: url('...')
        result = re.sub(
            r"background-image:\s*url\('[^']*'\)",
            f"background-image: url('{safe_url}')",
            html_str,
        )
        # VML: <v:fill ... src="..." />
        result = re.sub(
            r'(<v:fill\b[^>]*\bsrc=")[^"]*(")',
            rf"\g<1>{safe_url}\g<2>",
            result,
        )
        return result

    def _apply_token_overrides(
        self,
        html_str: str,
        overrides: list[TokenOverride],
    ) -> str:
        """Apply design token overrides to inline styles."""
        result = html_str

        for override in overrides:
            prop = override.css_property
            val = override.value
            target = override.target_class

            if target == "_outer":
                if prop == "background-color" and _OUTER_CLASS_PRESENT_RE.search(result):
                    # Phase 50.4 component HTML with explicit _outer class —
                    # avoid the legacy "first style block" heuristic which
                    # would otherwise overwrite the inner card's bg.
                    result = self._replace_outer_bg_color(result, val)
                    result = self._replace_bg_class_color(result, val)
                else:
                    # Legacy components without _outer class
                    result = self._replace_first_css_prop(result, prop, val)
                    if prop == "background-color":
                        result = self._replace_bg_class_color(result, val)
            elif target == "_inner":
                if prop == "background-color":
                    result = self._replace_inner_bg_color(result, val)
                elif prop == "border-radius":
                    result = self._replace_inner_radius(result, val)
                elif prop == "width":
                    result = self._replace_inner_width(result, val)
                elif prop == "__html_attr_align":
                    result = self._set_inner_align_attr(result, val)
                elif prop == "__html_attr_class_add":
                    result = self._add_inner_class(result, val)
            elif (
                target.startswith("_image_")
                and prop.startswith("border-")
                and prop.endswith("-radius")
            ):
                node_id = target[len("_image_") :]
                result = self._apply_image_corner_radius(result, node_id, prop, val)
            elif target == "_heading" and prop == "font-family":
                result = self._replace_heading_font(result, val)
            elif target == "_heading" and prop == "color":
                result = self._replace_heading_color(result, val)
            elif target == "_body" and prop == "font-family":
                result = self._replace_body_font(result, val)
            elif target == "_body" and prop == "color":
                result = self._replace_body_color(result, val)
            elif target == "_heading" and prop == "font-size":
                result = self._replace_heading_size(result, val)
            elif target == "_body" and prop == "font-size":
                result = self._replace_body_size(result, val)
            elif target == "_heading" and prop == "text-align":
                result = self._replace_heading_align(result, val)
            elif target == "_body" and prop == "text-align":
                result = self._replace_body_align(result, val)
            elif target in ("_heading", "_body") and prop in _TYPOGRAPHY_PROPS:
                result = self._apply_typography_prop(result, target, prop, val)
            elif target == "_cell":
                # Replace padding on the first td with padding
                result = self._replace_first_css_prop(result, prop, val)
            elif target == "_cta":
                if prop == "background-color":
                    result = self._replace_cta_background_color(result, val)
                    result = self._replace_cta_bgcolor_attr(result, val)
                    result = self._replace_cta_fillcolor(result, val)
                elif prop == "color":
                    result = self._replace_cta_text_color(result, val)
                elif prop == "border-radius":
                    result = self._replace_cta_css_prop(result, "border-radius", val)
                    # Only cta-button.html emits <v:roundrect>, at most one per
                    # component — global update is acceptable.
                    result = self._update_vml_arcsize(result, val)
                elif prop == "border-color":
                    result = self._replace_cta_css_prop(result, "border-color", val)
                    result = self._replace_cta_strokecolor(result, val)
                elif prop == "border-width":
                    result = self._replace_cta_css_prop(result, "border-width", val)

        return result

    def _replace_first_css_prop(self, html_str: str, prop: str, value: str) -> str:
        """Replace the first occurrence of a CSS property in a style attribute."""
        pattern = rf'(style="[^"]*?){re.escape(prop)}:\s*[^;"]+(;?)'
        return re.sub(pattern, rf"\g<1>{prop}:{value}\g<2>", html_str, count=1)

    def _replace_heading_font(self, html_str: str, font: str) -> str:
        """Replace font-family on heading elements (data-slot or semantic class)."""
        safe = html.escape(font, quote=True)
        repl = rf"\g<1>font-family:{safe}\g<2>"
        result = _HEADING_SLOT_FONT_RE.sub(repl, html_str)
        return _HEADING_CLASS_FONT_RE.sub(repl, result)

    def _replace_body_font(self, html_str: str, font: str) -> str:
        """Replace font-family on body elements (data-slot or semantic class)."""
        safe = html.escape(font, quote=True)
        repl = rf"\g<1>font-family:{safe}\g<2>"
        result = _BODY_SLOT_FONT_RE.sub(repl, html_str)
        return _BODY_CLASS_FONT_RE.sub(repl, result)

    def _replace_heading_color(self, html_str: str, color: str) -> str:
        """Replace color on heading elements (data-slot or semantic class).

        Uses negative lookbehind to avoid matching background-color:.
        """
        safe = html.escape(color, quote=True)
        repl = rf"\g<1>color:{safe}\g<2>"
        result = _HEADING_SLOT_COLOR_RE.sub(repl, html_str)
        return _HEADING_CLASS_COLOR_RE.sub(repl, result)

    def _replace_body_color(self, html_str: str, color: str) -> str:
        """Replace color on body elements (data-slot or semantic class).

        Uses negative lookbehind to avoid matching background-color:.
        """
        safe = html.escape(color, quote=True)
        repl = rf"\g<1>color:{safe}\g<2>"
        result = _BODY_SLOT_COLOR_RE.sub(repl, html_str)
        return _BODY_CLASS_COLOR_RE.sub(repl, result)

    def _replace_heading_size(self, html_str: str, size: str) -> str:
        """Replace font-size on heading elements (data-slot or semantic class)."""
        safe = html.escape(size, quote=True)
        repl = rf"\g<1>font-size:{safe}\g<2>"
        result = _HEADING_SLOT_SIZE_RE.sub(repl, html_str)
        return _HEADING_CLASS_SIZE_RE.sub(repl, result)

    def _replace_body_size(self, html_str: str, size: str) -> str:
        """Replace font-size on body elements (data-slot or semantic class)."""
        safe = html.escape(size, quote=True)
        repl = rf"\g<1>font-size:{safe}\g<2>"
        result = _BODY_SLOT_SIZE_RE.sub(repl, html_str)
        return _BODY_CLASS_SIZE_RE.sub(repl, result)

    def _replace_heading_align(self, html_str: str, align: str) -> str:
        """Apply text-align to heading elements (data-slot or semantic class).

        Two-pass per element type: replace an existing inline ``text-align:``
        when present, otherwise inject one into the ``style=`` attribute. The
        slot pass runs before the class pass; the insert lookahead skips any
        element that already carries ``text-align:`` so a cell matched by both
        ``data-slot`` and ``class`` is not injected twice. Invalid values are
        rejected (defence-in-depth against CSS injection).
        """
        align = align.lower()
        if align not in _ALLOWED_TEXT_ALIGN:
            return html_str
        result = _HEADING_SLOT_ALIGN_RE.sub(rf"\g<1>text-align:{align}\g<2>", html_str)
        result = _HEADING_CLASS_ALIGN_RE.sub(rf"\g<1>text-align:{align}\g<2>", result)
        result = _HEADING_SLOT_ALIGN_INSERT_RE.sub(rf"\g<1>text-align:{align};", result)
        return _HEADING_CLASS_ALIGN_INSERT_RE.sub(rf"\g<1>text-align:{align};", result)

    def _replace_body_align(self, html_str: str, align: str) -> str:
        """Apply text-align to body elements (data-slot or semantic class).

        Mirrors :meth:`_replace_heading_align` — replace-or-inject across the
        slot and class element sets, double-inject-safe via the lookahead, with
        value validation.
        """
        align = align.lower()
        if align not in _ALLOWED_TEXT_ALIGN:
            return html_str
        result = _BODY_SLOT_ALIGN_RE.sub(rf"\g<1>text-align:{align}\g<2>", html_str)
        result = _BODY_CLASS_ALIGN_RE.sub(rf"\g<1>text-align:{align}\g<2>", result)
        result = _BODY_SLOT_ALIGN_INSERT_RE.sub(rf"\g<1>text-align:{align};", result)
        return _BODY_CLASS_ALIGN_INSERT_RE.sub(rf"\g<1>text-align:{align};", result)

    @staticmethod
    def _validate_typography_value(prop: str, value: str) -> str | None:
        """Sanitise a typography prop value; return ``None`` to drop it.

        Defence-in-depth against CSS injection even though the matcher already
        constrains emission. ``letter-spacing`` accepts a leading ``-``.
        """
        if prop == "font-weight":
            return value if _FONT_WEIGHT_VALUE_RE.match(value) else None
        if prop == "line-height":
            return value if _LINE_HEIGHT_VALUE_RE.match(value) else None
        if prop == "letter-spacing":
            return value if _LETTER_SPACING_VALUE_RE.match(value) else None
        if prop == "text-transform":
            lowered = value.lower()
            return lowered if lowered in _ALLOWED_TEXT_TRANSFORM else None
        if prop == "text-decoration":
            lowered = value.lower()
            return lowered if lowered in _ALLOWED_TEXT_DECORATION else None
        return None

    def _apply_typography_prop(
        self,
        html_str: str,
        target: str,
        prop: str,
        value: str,
    ) -> str:
        """Replace-or-inject a typography prop on heading/body cells (Phase 52.4).

        Generalises the ``text-align`` four-pass (slot replace, class replace,
        slot insert, class insert) over the typography prop set. The insert
        passes carry a negative lookahead so a cell matched by both ``data-slot``
        and ``class`` is never double-injected. Invalid values are dropped.
        """
        safe = self._validate_typography_value(prop, value)
        if safe is None:
            return html_str
        escaped = html.escape(safe, quote=True)
        regexes = _HEADING_PROP_RE[prop] if target == "_heading" else _BODY_PROP_RE[prop]
        result = regexes.slot_replace.sub(rf"\g<1>{prop}:{escaped}\g<2>", html_str)
        result = regexes.class_replace.sub(rf"\g<1>{prop}:{escaped}\g<2>", result)
        result = regexes.slot_insert.sub(rf"\g<1>{prop}:{escaped};", result)
        return regexes.class_insert.sub(rf"\g<1>{prop}:{escaped};", result)

    def _replace_bg_class_color(self, html_str: str, color: str) -> str:
        """Replace background-color on elements with background container classes."""
        safe = html.escape(color, quote=True)
        repl = rf"\g<1>background-color:{safe}\g<2>"
        return _BG_CLASS_BGCOLOR_RE.sub(repl, html_str)

    def _replace_outer_bg_color(self, html_str: str, color: str) -> str:
        """Apply background-color to elements carrying ``class="_outer"`` (Phase 50.4).

        Two-pass: replace inline ``background-color:`` if present, otherwise
        inject one. Stamps ``bgcolor`` attribute when missing for Outlook.
        """
        safe = html.escape(color, quote=True)
        result = _OUTER_CLASS_BGCOLOR_RE.sub(rf"\g<1>background-color:{safe}\g<2>", html_str)
        result = _OUTER_CLASS_BG_INSERT_RE.sub(rf"\g<1>background-color:{safe};", result)
        bgcolor_pattern = re.compile(
            r'(<(?:table|td)\b)((?:(?!\bbgcolor=)[^>])*?\bclass="(?:[^"]*\s)?_outer'
            r'(?:\s[^"]*)?"(?:(?!\bbgcolor=)[^>])*?)(/?>)'
        )
        return bgcolor_pattern.sub(rf'\g<1>\g<2> bgcolor="{safe}"\g<3>', result)

    def _replace_inner_bg_color(self, html_str: str, color: str) -> str:
        """Apply background-color to elements carrying ``class="_inner"``.

        Two-pass:
        * If an inline ``background-color:`` already exists on the ``_inner``
          element, replace it.
        * Otherwise, inject a ``background-color:`` declaration into the
          existing style attribute.

        Also stamps a matching ``bgcolor=`` attribute when none is present —
        Outlook reads the attribute, modern clients prefer the inline style.
        """
        safe = html.escape(color, quote=True)
        result = _INNER_CLASS_BGCOLOR_RE.sub(rf"\g<1>background-color:{safe}\g<2>", html_str)
        # Inject when the _inner element has a style attr but no background-color
        result = _INNER_CLASS_BG_INSERT_RE.sub(rf"\g<1>background-color:{safe};", result)
        # Stamp bgcolor attribute on the same element when missing (Outlook)
        bgcolor_pattern = re.compile(
            r'(<(?:table|td)\b)((?:(?!\bbgcolor=)[^>])*?\bclass="(?:[^"]*\s)?_inner'
            r'(?:\s[^"]*)?"(?:(?!\bbgcolor=)[^>])*?)(/?>)'
        )
        return bgcolor_pattern.sub(rf'\g<1>\g<2> bgcolor="{safe}"\g<3>', result)

    def _replace_inner_radius(self, html_str: str, value: str) -> str:
        """Apply border-radius to elements carrying ``class="_inner"``.

        Replaces an existing inline ``border-radius:`` when present; otherwise
        injects one alongside ``border-collapse:separate; overflow:hidden;`` so
        rounded corners actually clip in clients that support them.
        """
        safe = html.escape(value, quote=True)
        result = _INNER_CLASS_RADIUS_RE.sub(rf"\g<1>border-radius:{safe}\g<2>", html_str)
        result = _INNER_CLASS_RADIUS_INSERT_RE.sub(
            rf"\g<1>border-radius:{safe};border-collapse:separate;overflow:hidden;",
            result,
        )
        return result

    def _replace_inner_width(self, html_str: str, value: str) -> str:
        """Apply width to elements carrying ``class="_inner"`` (Rule 11)."""
        safe = html.escape(value, quote=True)
        result = _INNER_CLASS_WIDTH_RE.sub(rf"\g<1>width:{safe}\g<2>", html_str)
        result = _INNER_CLASS_WIDTH_INSERT_RE.sub(rf"\g<1>width:{safe};", result)
        return result

    def _set_inner_align_attr(self, html_str: str, value: str) -> str:
        """Set ``align="<value>"`` attribute on the ``_inner`` element (Rule 11)."""
        if value not in ("left", "center", "right"):
            return html_str
        safe = html.escape(value, quote=True)
        result, replaced = _INNER_CLASS_ALIGN_REPLACE_RE.subn(
            rf'\g<1>align="{safe}"',
            html_str,
        )
        if replaced:
            return result
        return _INNER_CLASS_ELEMENT_RE.sub(
            rf'\g<1>\g<2> align="{safe}"\g<3>\g<4>',
            html_str,
        )

    def _add_inner_class(self, html_str: str, value: str) -> str:
        """Append a class token to ``class="_inner ..."`` (Rule 11 ``wf`` add)."""
        token = value.strip()
        if not token:
            return html_str
        safe = html.escape(token, quote=True)

        def _replace(match: re.Match[str]) -> str:
            existing = match.group(2)
            tokens = existing.split()
            if safe in tokens:
                return match.group(0)
            return f"{match.group(1)}{existing} {safe}{match.group(3)}"

        return _INNER_CLASS_ATTR_RE.sub(_replace, html_str)

    def _apply_image_corner_radius(
        self,
        html_str: str,
        node_id: str,
        prop: str,
        value: str,
    ) -> str:
        """Apply per-corner border-radius to ``<img data-node-id="X">`` (Rule 10).

        Per-corner longhand survives more legacy renderers (Outlook 2016, AOL)
        than the shorthand. Also stamps ``overflow:hidden`` on the parent
        ``<td>`` so WebKit clients clip the corners.
        """
        safe_prop = re.escape(prop)
        safe_val = html.escape(value, quote=True)
        safe_node = re.escape(node_id)

        # Merge the longhand into the matching <img>'s own style attribute,
        # regardless of whether ``style=`` precedes or follows ``data-node-id``
        # (attribute order varies by template). Operating on the whole tag is
        # what prevents emitting a second ``style=`` attribute — the prior
        # ``data-node-id"[^>]*style="`` form silently missed when ``style``
        # came first and fell through to appending a duplicate attribute.
        img_tag = re.compile(rf'<img\b[^>]*\bdata-node-id="{safe_node}"[^>]*?/?>')
        style_decl = re.compile(r'(style=")([^"]*)(")')
        prop_in_style = re.compile(rf'{safe_prop}:\s*[^;"]+;?')

        def _merge_into_img(m: re.Match[str]) -> str:
            tag = m.group(0)
            sm = style_decl.search(tag)
            if sm is None:
                # No style attr at all — add one before the closing > / />
                return re.sub(r"(/?>)\Z", rf' style="{prop}:{safe_val};"\g<1>', tag, count=1)
            body = sm.group(2)
            if prop_in_style.search(body):
                new_body = prop_in_style.sub(f"{prop}:{safe_val};", body, count=1)
            else:
                sep = "" if (body == "" or body.rstrip().endswith(";")) else ";"
                new_body = f"{body}{sep}{prop}:{safe_val};"
            return tag[: sm.start(2)] + new_body + tag[sm.end(2) :]

        result = img_tag.sub(_merge_into_img, html_str)

        # Stamp overflow:hidden on the wrapping <td> when missing
        td_pattern = re.compile(
            rf'(<td\b[^>]*style=")((?:(?!overflow:)[^"])*)(")'
            rf'((?:(?!<td\b)(?!</td>).)*?<img\b[^>]*\bdata-node-id="{safe_node}")',
            re.DOTALL,
        )
        result = td_pattern.sub(
            r"\g<1>\g<2>overflow:hidden;\g<3>\g<4>",
            result,
        )
        return result

    _CTA_LINK_COLOR_RE = re.compile(
        r'(<a\b[^>]*data-slot="cta_url"[^>]*style="[^"]*?)(?<!background-)color:\s*[^;"]+(;?)'
    )

    def _replace_cta_text_color(self, html_str: str, color: str) -> str:
        """Replace color on <a> elements with data-slot='cta_url'."""
        safe = html.escape(color, quote=True)
        result = self._CTA_LINK_COLOR_RE.sub(rf"\g<1>color:{safe}\g<2>", html_str)
        # Also update VML center text color
        result = re.sub(
            r'(<center\s+style="[^"]*?)color:\s*[^;"]+(;?)',
            rf"\g<1>color:{safe}\g<2>",
            result,
        )
        return result

    # CTA-scoped CSS property replacement.
    #
    # Matches a CSS declaration inside the style attribute of either:
    #   (a) an element carrying class="cta-btn" or "cta-ghost"
    #       (used by the standalone button / cta-button templates)
    #   (b) <a data-slot="cta_url"> (used by inline CTAs inside card
    #       templates like event-card, product-card, pricing-*)
    #
    # Both rely on `class`/`data-slot` appearing before `style` on the same
    # tag — verified across all 150 component templates today. A future
    # reorder would silently skip the override; the defensive regression
    # test `test_cta_override_skips_style_before_data_slot_regression`
    # locks that down.
    _CTA_CLASS_STYLE_RE_TEMPLATE = (
        r'(<[^>]*\bclass="(?:[^"]*\s)?cta-(?:btn|ghost)(?:\s[^"]*)?"[^>]*style="[^"]*?)'
        r'{prop}:\s*[^;"]+(;?)'
    )
    _CTA_LINK_STYLE_RE_TEMPLATE = (
        r'(<a\b[^>]*data-slot="cta_url"[^>]*style="[^"]*?)'
        r'{prop}:\s*[^;"]+(;?)'
    )

    def _replace_cta_css_prop(self, html_str: str, prop: str, value: str) -> str:
        """Replace a CSS property on CTA elements only (cta-btn/cta-ghost class or data-slot='cta_url')."""
        safe_prop = re.escape(prop)
        safe_value = html.escape(value, quote=True)
        repl = rf"\g<1>{prop}:{safe_value}\g<2>"
        class_pattern = self._CTA_CLASS_STYLE_RE_TEMPLATE.format(prop=safe_prop)
        slot_pattern = self._CTA_LINK_STYLE_RE_TEMPLATE.format(prop=safe_prop)
        result = re.sub(class_pattern, repl, html_str)
        return re.sub(slot_pattern, repl, result)

    _CTA_CLASS_BG_RE = re.compile(
        r'(<[^>]*\bclass="(?:[^"]*\s)?cta-(?:btn|ghost)(?:\s[^"]*)?"[^>]*style="[^"]*?)'
        r'background-color:\s*[^;"]+(;?)'
    )
    _CTA_LINK_BG_RE = re.compile(
        r'(<a\b[^>]*data-slot="cta_url"[^>]*style="[^"]*?)background-color:\s*[^;"]+(;?)'
    )

    def _replace_cta_background_color(self, html_str: str, color: str) -> str:
        """Replace background-color on CTA elements only."""
        safe = html.escape(color, quote=True)
        repl = rf"\g<1>background-color:{safe}\g<2>"
        result = self._CTA_CLASS_BG_RE.sub(repl, html_str)
        return self._CTA_LINK_BG_RE.sub(repl, result)

    _CTA_BGCOLOR_ATTR_RE = re.compile(
        r'(<[^>]*\bclass="(?:[^"]*\s)?cta-(?:btn|ghost)(?:\s[^"]*)?"[^>]*)\bbgcolor="[^"]*"'
    )
    _CTA_FILLCOLOR_RE = re.compile(r'(<v:roundrect\b[^>]*)\bfillcolor="[^"]*"')
    _CTA_STROKECOLOR_RE = re.compile(r'(<v:roundrect\b[^>]*)\bstrokecolor="[^"]*"')

    def _replace_cta_bgcolor_attr(self, html_str: str, color: str) -> str:
        """Replace bgcolor="..." on tags carrying cta-btn/cta-ghost class."""
        safe = html.escape(color, quote=True)
        return self._CTA_BGCOLOR_ATTR_RE.sub(rf'\g<1>bgcolor="{safe}"', html_str)

    def _replace_cta_fillcolor(self, html_str: str, color: str) -> str:
        """Replace fillcolor on <v:roundrect> (Outlook VML button fallback)."""
        safe = html.escape(color, quote=True)
        return self._CTA_FILLCOLOR_RE.sub(rf'\g<1>fillcolor="{safe}"', html_str)

    def _replace_cta_strokecolor(self, html_str: str, color: str) -> str:
        """Replace strokecolor on <v:roundrect>."""
        safe = html.escape(color, quote=True)
        return self._CTA_STROKECOLOR_RE.sub(rf'\g<1>strokecolor="{safe}"', html_str)

    _VML_ARCSIZE_RE = re.compile(r'arcsize="\d+%"')

    def _update_vml_arcsize(self, html_str: str, radius_val: str) -> str:
        """Convert border-radius px to VML arcsize percentage."""
        # Extract numeric px value
        match = re.match(r"(\d+)", radius_val)
        if not match:
            return html_str
        radius_px = int(match.group(1))
        # Default button height ~48px; arcsize = radius / (height/2) * 100
        arcsize = min(round(radius_px / 48 * 100), 50)
        return self._VML_ARCSIZE_RE.sub(f'arcsize="{arcsize}%"', html_str)

    _PLACEHOLDER_URL_RE = re.compile(
        r'(src|href)="https?://(?:via\.placeholder\.com|placehold\.co|placeholder\.com)[^"]*"'
    )

    def _strip_placeholder_urls(self, html_str: str) -> str:
        """Replace remaining placeholder URLs with empty defaults."""
        return self._PLACEHOLDER_URL_RE.sub(r'\1=""', html_str)

    def _update_mso_widths(self, html_str: str, width: int) -> str:
        """Update MSO conditional table widths to match container width."""

        # Replace width="600" in MSO conditional blocks
        # Only replace within <!--[if mso]> ... <![endif]--> blocks
        def _replace_mso_width(match: re.Match[str]) -> str:
            block = match.group(0)
            return re.sub(r'width="600"', f'width="{width}"', block)

        return re.sub(
            r"<!--\[if mso\]>.*?<!\[endif\]-->",
            _replace_mso_width,
            html_str,
            flags=re.DOTALL,
        )

    def _add_annotations(self, html_str: str, match: ComponentMatch) -> str:
        """Add builder annotations for visual builder sync."""
        result = html_str

        # Add data-section-id on the outermost element
        section_id = f"section_{match.section_idx}"
        # Wrap in a comment-based section marker (preserves MSO conditionals)
        result = f"<!-- section:{section_id} -->\n{result}\n<!-- /section:{section_id} -->"

        # Add data-component-name on the first <table element
        component_name = html.escape(match.section.node_name, quote=True)
        result = re.sub(
            r"(<table\b)",
            rf'\g<1> data-component-name="{component_name}"',
            result,
            count=1,
        )

        return result

    def _extract_dark_mode_classes(self, html_str: str) -> list[str]:
        """Extract dark mode CSS classes from the rendered HTML."""
        classes: set[str] = set()
        # Find all class="..." attributes
        for match in re.finditer(r'class="([^"]*)"', html_str):
            for cls in match.group(1).split():
                if any(
                    cls.endswith(suffix)
                    for suffix in (
                        "-bg",
                        "-text",
                        "-link",
                        "-btn",
                        "-ghost",
                        "-line",
                        "-caption",
                        "-overlay",
                    )
                ):
                    classes.add(cls)
        return sorted(classes)

    def _extract_images(self, html_str: str) -> list[dict[str, str]]:
        """Extract image metadata from rendered HTML."""
        images: list[dict[str, str]] = []
        for match in re.finditer(r"<img\b([^>]*)>", html_str):
            attrs = match.group(1)
            src_match = re.search(r'src="([^"]*)"', attrs)
            alt_match = re.search(r'alt="([^"]*)"', attrs)
            if src_match:
                images.append(
                    {
                        "src": src_match.group(1),
                        "alt": alt_match.group(1) if alt_match else "",
                    }
                )
        return images

    def _fallback_render(self, match: ComponentMatch) -> RenderedSection:
        """Fallback: render section as a plain text-block with raw content."""
        texts = " ".join(t.content for t in match.section.texts)
        escaped = html.escape(texts) if texts else "&nbsp;"

        fallback_html = (
            f"<!--[if mso]>\n"
            f'<table role="presentation" width="{self._container_width}" align="center" '
            f'cellpadding="0" cellspacing="0" border="0"><tr><td>\n'
            f"<![endif]-->\n"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="background-color:#ffffff;">\n'
            f"  <tr>\n"
            f'    <td style="padding:24px;font-family:Arial,sans-serif;font-size:16px;'
            f'color:#333333;line-height:1.6;">\n'
            f"      {escaped}\n"
            f"    </td>\n"
            f"  </tr>\n"
            f"</table>\n"
            f"<!--[if mso]>\n"
            f"</td></tr></table>\n"
            f"<![endif]-->"
        )

        return RenderedSection(
            html=fallback_html,
            component_slug="text-block",
            section_idx=match.section_idx,
        )
