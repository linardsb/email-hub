"""Post-conversion quality contracts for design_sync.

Three pure, synchronous checks that catch regressions:
- Contrast: WCAG AA text/background contrast validation
- Completeness: section and button count verification
- Placeholders: leaked placeholder text detection
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from lxml import html as lxml_html

from app.design_sync.component_matcher import _PLACEHOLDER_PATTERNS
from app.shared.color import contrast_ratio, relative_luminance

# Regex to extract inline CSS color properties
_COLOR_RE = re.compile(r"(?:^|;)\s*color\s*:\s*(#[0-9a-fA-F]{3,6})\b", re.IGNORECASE)
_BG_COLOR_RE = re.compile(
    r"(?:^|;)\s*background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})\b", re.IGNORECASE
)
_FONT_SIZE_RE = re.compile(r"(?:^|;)\s*font-size\s*:\s*(\d+)", re.IGNORECASE)
_FONT_WEIGHT_RE = re.compile(r"(?:^|;)\s*font-weight\s*:\s*(bold|[7-9]\d{2})\b", re.IGNORECASE)

# Section marker pattern: <!-- section:NODE_ID --> or <!-- section:NODE_ID:TYPE -->
_SECTION_MARKER_RE = re.compile(r"<!--\s*section:[^\s]+\s*-->")

# WCAG AA thresholds
_NORMAL_TEXT_RATIO = 4.5
_LARGE_TEXT_RATIO = 3.0
_LARGE_TEXT_PX = 18
_LARGE_BOLD_PX = 14


@dataclass(frozen=True)
class QualityWarning:
    """Single quality contract violation."""

    category: Literal["contrast", "completeness", "placeholder", "image_bgcolor"]
    severity: Literal["error", "warning", "info"]
    message: str
    context: dict[str, str | int | float] = field(
        default_factory=lambda: dict[str, str | int | float]()
    )


def _is_large_text(font_size_px: int | None, is_bold: bool) -> bool:
    """Check if text qualifies as 'large' under WCAG 2.1."""
    if font_size_px is None:
        return False
    if font_size_px >= _LARGE_TEXT_PX:
        return True
    return is_bold and font_size_px >= _LARGE_BOLD_PX


def _find_ancestor_bg(element: lxml_html.HtmlElement) -> str | None:
    """Walk up the DOM to find the nearest ancestor with a background color."""
    current = element.getparent()
    while current is not None:
        style = current.get("style", "")
        if style:
            match = _BG_COLOR_RE.search(style)
            if match:
                return match.group(1)
        current = current.getparent()
    return None


def check_contrast(html: str) -> list[QualityWarning]:
    """Check WCAG AA contrast ratio for text/background color pairs."""
    warnings: list[QualityWarning] = []
    try:
        doc = lxml_html.document_fromstring(html)
    except Exception:
        return warnings

    for element in doc.iter():
        style = element.get("style", "")
        if not style:
            continue

        color_match = _COLOR_RE.search(style)
        if not color_match:
            continue

        text_color = color_match.group(1)

        # Find background: check own style first, then walk ancestors
        bg_match = _BG_COLOR_RE.search(style)
        bg_color = bg_match.group(1) if bg_match else _find_ancestor_bg(element)
        if not bg_color:
            continue

        text_lum = relative_luminance(text_color)
        bg_lum = relative_luminance(bg_color)
        ratio = contrast_ratio(text_lum, bg_lum)

        # Determine if large text (lower threshold)
        size_match = _FONT_SIZE_RE.search(style)
        font_size_px = int(size_match.group(1)) if size_match else None
        weight_match = _FONT_WEIGHT_RE.search(style)
        is_bold = bool(weight_match)
        large = _is_large_text(font_size_px, is_bold)
        threshold = _LARGE_TEXT_RATIO if large else _NORMAL_TEXT_RATIO

        if ratio < threshold:
            tag = str(element.tag)
            element_id: str = element.get("class", "") or element.get("id", "") or tag
            warnings.append(
                QualityWarning(
                    category="contrast",
                    severity="warning",
                    message=(
                        f"Low contrast {ratio:.1f}:1 "
                        f"(need {threshold:.1f}:1) — "
                        f"{text_color} on {bg_color}"
                    ),
                    context={
                        "text_color": text_color,
                        "bg_color": bg_color,
                        "ratio": round(ratio, 2),
                        "threshold": threshold,
                        "element": element_id,
                    },
                )
            )
    return warnings


def check_completeness(
    html: str,
    input_section_count: int = 0,
    input_button_count: int = 0,
) -> list[QualityWarning]:
    """Check that output HTML preserves expected sections and buttons."""
    warnings: list[QualityWarning] = []

    # Count section markers
    if input_section_count > 0:
        found_sections = len(_SECTION_MARKER_RE.findall(html))
        if found_sections < input_section_count:
            missing = input_section_count - found_sections
            warnings.append(
                QualityWarning(
                    category="completeness",
                    severity="warning",
                    message=f"{missing} section(s) missing from output",
                    context={
                        "expected": input_section_count,
                        "found": found_sections,
                        "type": "section",
                    },
                )
            )

    # Count buttons (CTA links + MSO VML buttons)
    if input_button_count > 0:
        try:
            doc = lxml_html.document_fromstring(html)
            # Count <a> tags that look like buttons (inside v:roundrect or with
            # button-like inline styles: display:inline-block + padding + background)
            button_links = 0
            for a_tag in doc.iter("a"):
                style = a_tag.get("style", "")
                if "display:inline-block" in style and "padding:" in style:
                    button_links += 1
            # Also count MSO v:roundrect patterns
            vml_buttons = len(re.findall(r"v:roundrect", html))
            # Each button produces one <a> + one v:roundrect; take the max
            found_buttons = max(button_links, vml_buttons)
        except Exception:
            found_buttons = 0

        if found_buttons < input_button_count:
            missing = input_button_count - found_buttons
            warnings.append(
                QualityWarning(
                    category="completeness",
                    severity="warning",
                    message=f"{missing} button(s) missing from output",
                    context={
                        "expected": input_button_count,
                        "found": found_buttons,
                        "type": "button",
                    },
                )
            )

    return warnings


def check_placeholders(html: str) -> list[QualityWarning]:
    """Detect leaked placeholder text in the output HTML."""
    warnings: list[QualityWarning] = []
    try:
        doc = lxml_html.document_fromstring(html)
    except Exception:
        return warnings

    seen: set[str] = set()
    for element in doc.iter():
        text = element.text
        if not text:
            continue
        text = text.strip()
        if not text:
            continue

        match = _PLACEHOLDER_PATTERNS.search(text)
        if match:
            matched_text = match.group(0)
            # Deduplicate identical matches
            key = matched_text.lower()
            if key in seen:
                continue
            seen.add(key)

            # Truncate long text for the message
            snippet = text[:80] + "..." if len(text) > 80 else text
            warnings.append(
                QualityWarning(
                    category="placeholder",
                    severity="warning",
                    message=f"Placeholder text detected: {snippet!r}",
                    context={
                        "text": snippet,
                        "pattern": matched_text.lower(),
                    },
                )
            )

    return warnings


def check_image_container_bgcolor(html: str) -> list[QualityWarning]:
    """Flag background-color on elements containing <img> tags.

    Images exported from Figma should be self-contained (frame background baked
    in). Adding CSS background-color to image containers creates visual
    mismatches.
    """
    warnings: list[QualityWarning] = []
    try:
        doc = lxml_html.document_fromstring(html)
    except Exception:
        return warnings

    for img in doc.iter("img"):
        parent = img.getparent()
        if parent is None:
            continue
        tag = str(parent.tag).lower()
        if tag not in ("td", "div", "a"):
            continue
        style = parent.get("style", "")
        bgcolor_attr = parent.get("bgcolor", "")
        css_match = _BG_COLOR_RE.search(style)
        if bgcolor_attr or css_match:
            color = bgcolor_attr or (css_match.group(1) if css_match else "")
            warnings.append(
                QualityWarning(
                    category="image_bgcolor",
                    severity="warning",
                    message=(
                        f"Image container <{tag}> has background-color "
                        f"{color} — images should be self-contained"
                    ),
                    context={
                        "tag": tag,
                        "color": color,
                        "img_src": img.get("src", "")[:80],
                    },
                )
            )
    return warnings


def run_quality_contracts(
    html: str,
    input_section_count: int = 0,
    input_button_count: int = 0,
) -> list[QualityWarning]:
    """Run all post-conversion quality contracts. Pure, sync, no I/O."""
    if not html:
        return []
    results: list[QualityWarning] = []
    results.extend(check_contrast(html))
    results.extend(check_completeness(html, input_section_count, input_button_count))
    results.extend(check_placeholders(html))
    results.extend(check_image_container_bgcolor(html))
    return results
