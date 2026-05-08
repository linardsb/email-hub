"""Generate Scaffolder-compatible campaign briefs from layout analysis — pure computation."""

from __future__ import annotations

from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    DesignLayoutDescription,
    EmailSection,
)
from app.design_sync.protocol import ExtractedTokens
from app.design_sync.token_transforms import convert_colors_to_palette
from app.shared.color import relative_luminance

_MAX_BRIEF_LENGTH = 4000


def generate_brief(
    layout: DesignLayoutDescription,
    *,
    tokens: ExtractedTokens | None = None,
    asset_url_prefix: str = "",
    connection_id: int | None = None,  # noqa: ARG001
) -> str:
    """Transform a layout analysis into a structured markdown brief.

    Args:
        layout: The analyzed design layout.
        tokens: Optional extracted design tokens for the token summary.
        asset_url_prefix: URL prefix for image asset references.
        connection_id: Connection ID (unused, kept for API compat).

    Returns:
        Structured markdown string suitable for the Scaffolder agent (max 4000 chars).
    """
    parts: list[str] = []

    # Header
    parts.append("# Campaign Email Brief\n")

    # Layout summary
    width_str = f"{layout.overall_width:.0f}px wide" if layout.overall_width else "unknown width"
    section_types = [s.section_type.value for s in layout.sections]
    layout_summary = ", ".join(section_types) if section_types else "no sections"
    parts.append(f"## Layout\n{width_str}, {len(layout.sections)} sections: {layout_summary}\n")

    # Sections
    if layout.sections:
        parts.append("## Sections\n")
        for i, section in enumerate(layout.sections, 1):
            section_md = _format_section(section, i, asset_url_prefix)
            parts.append(section_md)

    # Design tokens
    if tokens:
        token_md = _format_tokens(tokens)
        if token_md:
            parts.append(token_md)

    # Section spacing
    spacing_md = _format_spacing(layout.sections)
    if spacing_md:
        parts.append(spacing_md)

    full = "\n".join(parts)

    # Truncate intelligently if over limit
    if len(full) > _MAX_BRIEF_LENGTH:
        full = _truncate_brief(parts)

    return full


def _format_section(section: EmailSection, index: int, asset_url_prefix: str) -> str:
    """Format a single section as markdown."""
    lines: list[str] = []
    section_label = _section_label(section, index)
    lines.append(f"### {section_label}")
    lines.append(f"- Layout: {_describe_layout(section)}")
    if section.height:
        lines.append(f"- Height: {section.height:.0f}px")
    if section.bg_color:
        lines.append(f"- Background: {section.bg_color}")
        is_dark = relative_luminance(section.bg_color) < 0.5
        lines.append(
            f"- Theme: {'dark background — use light/white text' if is_dark else 'light background'}"
        )

    # Images
    for img in section.images:
        dims = ""
        if img.width and img.height:
            dims = f" {img.width:.0f}x{img.height:.0f}"
        if asset_url_prefix:
            # Use sanitized node_id as filename (matches asset storage convention)
            safe_id = img.node_id.replace(":", "_")
            lines.append(f"- Image: [{img.node_name}]({asset_url_prefix}/{safe_id}.png){dims}")
        else:
            lines.append(f"- Image: {img.node_name}{dims}")

    # Text content
    for text in section.texts:
        if text.is_heading:
            lines.append(f'- Heading: "{_truncate_text(text.content, 80)}"')
        else:
            lines.append(f'- Text: "{_truncate_text(text.content, 120)}"')

    # Buttons
    for btn in section.buttons:
        lines.append(f'- Button: "{btn.text}"')

    return "\n".join(lines) + "\n"


_SECTION_DISPLAY_NAMES: dict[str, str] = {
    "header": "Header / Navigation",
    "preheader": "Pre-header",
    "hero": "Hero Section",
    "content": "Content Module",
    "cta": "CTA Module",
    "footer": "Footer",
    "social": "Social Links",
    "divider": "Divider",
    "spacer": "Spacer",
    "nav": "Navigation Bar",
    "unknown": "Section",
}


def _section_label(section: EmailSection, index: int) -> str:
    """Build a human-readable section label like '1. Hero Section' or '3. Content Module 2'."""
    display = _SECTION_DISPLAY_NAMES.get(section.section_type.value, "Section")

    # Use the original node name if it's meaningful (not generic like "mj-wrapper")
    raw_name = section.node_name.lower().strip()
    generic_names = {
        "mj-wrapper",
        "mj-section",
        "mj-column",
        "mj-body",
        "mj-hero",
        "wrapper",
        "frame",
        "group",
        "section",
        "component",
        "row",
        "container",
    }
    if raw_name not in generic_names and not raw_name.startswith("frame "):
        # Node has a meaningful name from the designer — prefer it
        display = section.node_name

    return f"{index}. {display}"


def _describe_layout(section: EmailSection) -> str:
    """Describe the column layout of a section."""
    if section.column_layout == ColumnLayout.SINGLE:
        return "single column"
    if section.column_layout == ColumnLayout.TWO_COLUMN:
        return "2-column"
    if section.column_layout == ColumnLayout.THREE_COLUMN:
        return "3-column"
    return f"{section.column_count}-column"


def _format_tokens(tokens: ExtractedTokens) -> str:
    """Format design tokens as markdown with color role annotations."""
    lines: list[str] = ["## Design Tokens"]

    if tokens.colors:
        palette = convert_colors_to_palette(tokens.colors)
        lines.append(f"- Background: {palette.background}")
        lines.append(f"- Text: {palette.text}")
        lines.append(f"- Primary: {palette.primary}")
        lines.append(f"- Accent/CTA: {palette.accent}")
        lines.append(f"- Link: {palette.link}")
        # Also list raw colors for reference
        color_strs = [f"{c.name} {c.hex}" for c in tokens.colors[:6]]
        lines.append(f"- All colors: {', '.join(color_strs)}")

    if tokens.typography:
        type_strs = [f"{t.family} {t.size:.0f}px ({t.name})" for t in tokens.typography[:4]]
        lines.append(f"- Typography: {', '.join(type_strs)}")

    if tokens.spacing:
        spacing_strs = [f"{s.value:.0f}px" for s in tokens.spacing[:6]]
        lines.append(f"- Spacing: {', '.join(spacing_strs)}")

    if len(lines) == 1:
        return ""  # No tokens to show
    return "\n".join(lines) + "\n"


def _format_spacing(sections: list[EmailSection]) -> str:
    """Format section spacing as markdown. Omits section when all values are zero."""
    pairs: list[str] = []
    for i in range(len(sections) - 1):
        spacing = sections[i].spacing_after
        if spacing is not None and spacing > 0:
            from_name = sections[i].section_type.value.title()
            to_name = sections[i + 1].section_type.value.title()
            pairs.append(f"- {from_name} → {to_name}: {spacing:.0f}px")

    if not pairs:
        return ""
    return "## Section Spacing\n" + "\n".join(pairs) + "\n"


def _truncate_text(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _truncate_brief(parts: list[str]) -> str:
    """Intelligently truncate brief to fit within limit.

    Strategy: keep header + layout + section headers, trim body text progressively.
    """
    # First try: just join and hard-truncate body text sections
    # Keep first 2 parts (header + layout) always
    essential = "\n".join(parts[:2]) + "\n"
    remaining = _MAX_BRIEF_LENGTH - len(essential) - 50  # buffer for truncation note

    truncated_parts: list[str] = []
    budget = remaining

    for part in parts[2:]:
        if len(part) <= budget:
            truncated_parts.append(part)
            budget -= len(part) + 1  # +1 for newline join
        else:
            # Take what we can — prefer section headers over body
            lines = part.split("\n")
            kept: list[str] = []
            for line in lines:
                if len(line) + 1 <= budget:
                    kept.append(line)
                    budget -= len(line) + 1
                else:
                    break
            if kept:
                truncated_parts.append("\n".join(kept))
            break

    result = essential + "\n".join(truncated_parts)
    if len(result) < _MAX_BRIEF_LENGTH - 30:
        result += "\n\n*[Brief truncated for length]*"
    return result[:_MAX_BRIEF_LENGTH]
