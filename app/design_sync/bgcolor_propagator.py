"""Adjacent-section background color propagation for visual continuity (Phase 41.2).

When a full-width-image section is adjacent to a text/heading/CTA section,
sample the facing edge of the image. If a solid color is detected, inject
``bgcolor`` on the adjacent content section's outermost ``<table>``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from PIL import Image

from app.core.logging import get_logger
from app.design_sync.image_sampler import sample_edge_color
from app.shared.color import relative_luminance
from app.shared.imaging import safe_image_open

if TYPE_CHECKING:
    from app.design_sync.component_matcher import ComponentMatch
    from app.design_sync.figma.layout_analyzer import EmailSection

logger = get_logger(__name__)

# ── Section boundary classification (Phase 50.2) ──

BoundaryRelation = Literal[
    "continuous_with_above",
    "continuous_with_below",
    "hard_break",
    "unknown",
]

# Per-channel RGB delta below which two edge colors are "continuous"
_DEFAULT_DELTA_THRESHOLD = 5

# Pixel band height sampled at each section's top/bottom
_BOUNDARY_SAMPLE_BAND = 5

# Minimum uniformity required for a band's dominant color to be reported
_BOUNDARY_MIN_UNIFORMITY = 0.80

# Tolerance for the boundary band's dominant-color clustering
_BOUNDARY_CLUSTER_TOLERANCE = 10


@dataclass(frozen=True)
class SectionBoundary:
    """Per-section boundary classification."""

    section_node_id: str
    boundary_above: BoundaryRelation
    boundary_below: BoundaryRelation
    sampled_top_color: str | None  # hex
    sampled_bottom_color: str | None


def classify_section_boundaries(
    sections: list[EmailSection],
    *,
    global_design_image: bytes | None,
    delta_threshold: int = _DEFAULT_DELTA_THRESHOLD,
) -> dict[str, SectionBoundary]:
    """Sample top + bottom edges of each section in the global PNG and classify boundaries.

    Walks sections in y-position order; for each consecutive pair samples a
    5px band at the previous section's bottom and the next section's top.
    When per-channel RGB delta is within ``delta_threshold`` the boundary is
    flagged ``continuous`` (paired direction); otherwise ``hard_break``.

    Returns a dict keyed by ``section.node_id``. Sections with no PNG, no
    geometry, or out-of-bounds y-coordinates receive ``unknown`` for both
    boundaries.
    """
    if not sections:
        return {}

    # No PNG → unknown for everything
    if global_design_image is None:
        return {
            s.node_id: SectionBoundary(
                section_node_id=s.node_id,
                boundary_above="unknown",
                boundary_below="unknown",
                sampled_top_color=None,
                sampled_bottom_color=None,
            )
            for s in sections
        }

    try:
        img = safe_image_open(io.BytesIO(global_design_image)).convert("RGB")
    except Exception as exc:
        logger.warning("design_sync.boundary_classifier.open_failed", error=str(exc))
        return {
            s.node_id: SectionBoundary(
                section_node_id=s.node_id,
                boundary_above="unknown",
                boundary_below="unknown",
                sampled_top_color=None,
                sampled_bottom_color=None,
            )
            for s in sections
        }

    img_w, img_h = img.size
    ordered = sorted(
        sections,
        key=lambda s: s.y_position if s.y_position is not None else 0.0,
    )

    # Pre-sample top + bottom colors for each section (or None when geometry missing)
    sampled_top: dict[str, str | None] = {}
    sampled_bottom: dict[str, str | None] = {}
    for sec in ordered:
        top, bottom = _sample_section_edges(sec, img, img_w, img_h)
        sampled_top[sec.node_id] = top
        sampled_bottom[sec.node_id] = bottom

    # Initialize all boundaries as unknown — pair walk overwrites where pairs are valid
    above: dict[str, BoundaryRelation] = {s.node_id: "unknown" for s in ordered}
    below: dict[str, BoundaryRelation] = {s.node_id: "unknown" for s in ordered}

    for i in range(len(ordered) - 1):
        curr = ordered[i]
        nxt = ordered[i + 1]
        bottom = sampled_bottom[curr.node_id]
        top = sampled_top[nxt.node_id]
        if bottom is None or top is None:
            below[curr.node_id] = "unknown"
            above[nxt.node_id] = "unknown"
            continue

        if _max_channel_delta(bottom, top) <= delta_threshold:
            below[curr.node_id] = "continuous_with_below"
            above[nxt.node_id] = "continuous_with_above"
        else:
            below[curr.node_id] = "hard_break"
            above[nxt.node_id] = "hard_break"

    return {
        s.node_id: SectionBoundary(
            section_node_id=s.node_id,
            boundary_above=above[s.node_id],
            boundary_below=below[s.node_id],
            sampled_top_color=sampled_top[s.node_id],
            sampled_bottom_color=sampled_bottom[s.node_id],
        )
        for s in ordered
    }


def _sample_section_edges(
    section: EmailSection,
    img: Image.Image,
    img_w: int,
    img_h: int,
) -> tuple[str | None, str | None]:
    """Sample top and bottom edge colors for a section against the global PNG.

    Returns ``(top_hex, bottom_hex)`` — either entry is ``None`` when the
    section's y-extent falls outside the PNG or geometry is missing.
    """
    if section.y_position is None or section.height is None:
        return None, None

    y_top = int(section.y_position)
    y_bottom = int(section.y_position + section.height)

    # Out of bounds — bail before clamping turns into a no-op band
    if y_top < 0 or y_bottom > img_h or y_top >= y_bottom or img_w == 0:
        return None, None

    band = _BOUNDARY_SAMPLE_BAND
    top_band = _crop_band(img, 0, max(0, y_top), img_w, min(img_h, y_top + band))
    bottom_band = _crop_band(img, 0, max(0, y_bottom - band), img_w, min(img_h, y_bottom))

    top_color = _band_dominant_color(top_band) if top_band is not None else None
    bottom_color = _band_dominant_color(bottom_band) if bottom_band is not None else None
    return top_color, bottom_color


def _crop_band(img: Image.Image, x0: int, y0: int, x1: int, y1: int) -> Image.Image | None:
    """Return PIL crop or None when the band is empty."""
    if y1 <= y0 or x1 <= x0:
        return None
    return img.crop((x0, y0, x1, y1))


def _band_dominant_color(band: Image.Image) -> str | None:
    """Return hex of dominant color in a PIL band image, or None when noisy."""
    pixels: np.ndarray = np.array(band).reshape(-1, 3)
    if len(pixels) == 0:
        return None
    return _dominant_hex(
        pixels,
        tolerance=_BOUNDARY_CLUSTER_TOLERANCE,
        min_uniformity=_BOUNDARY_MIN_UNIFORMITY,
    )


def _dominant_hex(
    pixels: np.ndarray,
    *,
    tolerance: int,
    min_uniformity: float,
) -> str | None:
    """Greedy single-pass clustering — mirrors image_sampler._dominant_color."""
    clusters: list[tuple[np.ndarray, int]] = []
    for px in pixels:
        assigned = False
        for i, (rgb_sum, count) in enumerate(clusters):
            centroid = rgb_sum / count
            if np.all(np.abs(px.astype(np.int16) - centroid.astype(np.int16)) <= tolerance):
                clusters[i] = (rgb_sum + px.astype(np.int64), count + 1)
                assigned = True
                break
        if not assigned:
            clusters.append((px.astype(np.int64).copy(), 1))

    if not clusters:
        return None
    best_sum, best_count = max(clusters, key=lambda c: c[1])
    if best_count / len(pixels) < min_uniformity:
        return None
    centroid = (best_sum / best_count).astype(np.uint8)
    return f"#{int(centroid[0]):02X}{int(centroid[1]):02X}{int(centroid[2]):02X}"


def _max_channel_delta(hex_a: str, hex_b: str) -> int:
    """Return the maximum per-channel RGB delta between two hex colors."""
    ar, ag, ab = _hex_to_rgb(hex_a)
    br, bg, bb = _hex_to_rgb(hex_b)
    return max(abs(ar - br), abs(ag - bg), abs(ab - bb))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# Component slugs that receive propagated bgcolor
_TEXT_LIKE_SLUGS: frozenset[str] = frozenset(
    {
        "text-block",
        "heading-block",
        "hero-text",
        "hero-block",
        "cta-button",
        "article-card",
        "button-block",
        "text-link",
        "product-card",
        "category-nav",
    }
)

# Luminance threshold below which a background is considered "dark"
_DARK_LUMINANCE_THRESHOLD = 0.4

# Matches inline ``color:#hex`` styles (but not ``background-color:``)
_INLINE_COLOR_RE = re.compile(
    r"(?<!background-)(?<!background)(color\s*:\s*)(#[0-9a-fA-F]{3,6})",
    re.IGNORECASE,
)

# Regex to match the first <table ...> opening tag in section HTML
_FIRST_TABLE_RE = re.compile(r"(<table\b)([^>]*)(>)", re.IGNORECASE)


def propagate_adjacent_bgcolor(
    matches: list[ComponentMatch],
    rendered_parts: list[str],
    *,
    connection_id: str | None = None,
    image_dir: Path | None = None,
) -> list[str]:
    """Scan adjacent (image, text) pairs and propagate edge color as bgcolor.

    Args:
        matches: Ordered ComponentMatch objects (one per section).
        rendered_parts: Parallel HTML strings (may include interleaved spacers).
        connection_id: Design connection ID for resolving local asset paths.
        image_dir: Override directory for image assets (useful in tests).

    Returns:
        Copy of *rendered_parts* with ``bgcolor`` injected where applicable.
    """
    if len(matches) < 2:
        return rendered_parts

    asset_dir = _resolve_asset_dir(connection_id, image_dir)
    if asset_dir is None:
        return rendered_parts

    result = list(rendered_parts)
    part_indices = _build_part_index(matches, result)

    for i in range(len(matches) - 1):
        m_curr = matches[i]
        m_next = matches[i + 1]

        # Image above → text below: sample bottom edge
        if (
            m_curr.component_slug == "full-width-image"
            and m_next.component_slug in _TEXT_LIKE_SLUGS
        ):
            color = _sample_edge(m_curr, asset_dir, "bottom")
            if color:
                idx = part_indices.get(i + 1)
                if idx is not None:
                    result[idx] = _inject_bgcolor(result[idx], color)
                    result[idx] = _invert_text_colors(result[idx], color)
                    logger.info(
                        "design_sync.bgcolor_propagated",
                        source_section=m_curr.section_idx,
                        target_section=m_next.section_idx,
                        color=color,
                        direction="down",
                    )

        # Text above → image below: sample top edge
        if (
            m_next.component_slug == "full-width-image"
            and m_curr.component_slug in _TEXT_LIKE_SLUGS
        ):
            color = _sample_edge(m_next, asset_dir, "top")
            if color:
                idx = part_indices.get(i)
                if idx is not None:
                    result[idx] = _inject_bgcolor(result[idx], color)
                    result[idx] = _invert_text_colors(result[idx], color)
                    logger.info(
                        "design_sync.bgcolor_propagated",
                        source_section=m_next.section_idx,
                        target_section=m_curr.section_idx,
                        color=color,
                        direction="up",
                    )

    return result


def _resolve_asset_dir(
    connection_id: str | None,
    image_dir: Path | None,
) -> Path | None:
    """Resolve the directory containing downloaded image assets."""
    if image_dir is not None:
        return image_dir
    if connection_id is None:
        return None
    from app.core.config import get_settings

    path = Path(get_settings().design_sync.asset_storage_path) / str(connection_id)
    if path.is_dir():
        return path
    return None


def _sanitize_node_id(node_id: str) -> str:
    """Convert Figma node ID (e.g. '1:2') to filesystem-safe string ('1_2')."""
    return node_id.replace(":", "_")


def _get_image_path(match: ComponentMatch, asset_dir: Path) -> Path | None:
    """Get local file path for the first image in a section."""
    if not match.section.images:
        return None
    node_id = match.section.images[0].node_id
    safe_id = _sanitize_node_id(node_id)
    for ext in ("png", "jpg", "jpeg"):
        path = asset_dir / f"{safe_id}.{ext}"
        if path.is_file():
            return path
    return None


def _sample_edge(
    match: ComponentMatch,
    asset_dir: Path,
    edge: Literal["top", "bottom"],
) -> str | None:
    """Sample the specified edge of the first image in a section."""
    path = _get_image_path(match, asset_dir)
    if path is None:
        return None
    return sample_edge_color(path, edge)


def _build_part_index(
    matches: list[ComponentMatch],
    parts: list[str],
) -> dict[int, int]:
    """Map match index → rendered_parts index.

    ``rendered_parts`` interleaves section HTML with optional MSO spacer
    blocks.  Spacers start with ``<!--[if mso]>`` whereas real section
    HTML starts with ``<table``, so we distinguish by the leading content.
    """
    index: dict[int, int] = {}
    match_idx = 0
    for part_idx, part in enumerate(parts):
        # Spacers start with the MSO conditional comment; section HTML
        # starts with <table (possibly after whitespace).
        stripped = part.lstrip()
        if stripped.startswith("<!--[if mso]>"):
            continue
        if match_idx < len(matches):
            index[match_idx] = part_idx
            match_idx += 1
    return index


def _invert_text_colors(section_html: str, bgcolor: str) -> str:
    """Override dark text/link colors to white when bgcolor is dark.

    Scans inline ``color:`` styles in the section HTML.  If the text color
    has low luminance (dark-on-dark), replaces it with ``#ffffff``.
    Leaves light text colors untouched (they already contrast).
    """
    bg_lum = relative_luminance(bgcolor)
    if bg_lum >= _DARK_LUMINANCE_THRESHOLD:
        return section_html

    def _replace_dark_color(m: re.Match[str]) -> str:
        prefix = m.group(1)  # "color:" (with optional whitespace)
        hex_val = m.group(2)
        text_lum = relative_luminance(hex_val)
        if text_lum < _DARK_LUMINANCE_THRESHOLD:
            return f"{prefix}#ffffff"
        return m.group(0)

    return _INLINE_COLOR_RE.sub(_replace_dark_color, section_html)


def _inject_bgcolor(html: str, color: str) -> str:
    """Inject ``bgcolor`` on the first ``<table>`` that lacks one."""

    def _replace(m: re.Match[str]) -> str:
        tag_start = m.group(1)
        attrs = m.group(2)
        tag_end = m.group(3)
        if "bgcolor" in attrs.lower():
            return m.group(0)
        return f'{tag_start} bgcolor="{color}"{attrs}{tag_end}'

    return _FIRST_TABLE_RE.sub(_replace, html, count=1)
