"""Email-safe HTML formatter with 2-space indentation.

Produces clean, consistently indented HTML while preserving:
- MSO conditional comments (<!--[if mso]>...<![endif]-->)
- VML elements (<v:roundrect>, <v:textbox>, etc.)
- Inline content inside leaf elements (<h1>-<h6>, <p>, <a>, <center>)
- <style> block content (re-indented but structure preserved)
- Self-closing tags (<img />, <meta>, etc.)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Tag classification sets
# ---------------------------------------------------------------------------

# Block-level elements that get their own line and increase indent for children.
_BLOCK_TAGS: frozenset[str] = frozenset(
    {
        "html",
        "head",
        "body",
        "table",
        "tr",
        "td",
        "th",
        "noscript",
        "xml",
        "div",
        "thead",
        "tbody",
        "tfoot",
    }
)

# Tags whose text content stays on the same line as the opening tag.
_INLINE_LEAF_TAGS: frozenset[str] = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "a",
        "span",
        "center",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "title",
    }
)

# Void (self-closing) elements — never have children.
_VOID_TAGS: frozenset[str] = frozenset(
    {
        "meta",
        "img",
        "br",
        "hr",
        "link",
        "input",
    }
)

# VML / Office namespace block elements (Outlook).
_VML_TAGS: frozenset[str] = frozenset(
    {
        "v:roundrect",
        "v:textbox",
        "v:fill",
        "v:stroke",
        "o:officedocumentsettings",
        "o:pixelsperinch",
    }
)

# Combined set for fast "is block?" lookups.
_ALL_BLOCK_TAGS: frozenset[str] = _BLOCK_TAGS | _VML_TAGS

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Splits HTML into tags, comments, and interstitial text.
# Group 1 captures: full comments (<!--...-->), orphan <![endif]-->,
# other <! directives, and regular tags (<...>).
_TOKEN_RE: re.Pattern[str] = re.compile(
    r"(<!--.*?-->|<!\[endif\]-->|<![^>]*>|<[^>]+>)",
    re.DOTALL,
)

_OPEN_TAG_RE: re.Pattern[str] = re.compile(r"^<\s*([a-zA-Z][a-zA-Z0-9:._-]*)")
_CLOSE_TAG_RE: re.Pattern[str] = re.compile(r"^<\s*/\s*([a-zA-Z][a-zA-Z0-9:._-]*)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_email_html(html: str, indent_size: int = 2) -> str:
    """Format email HTML with consistent indentation.

    Args:
        html: Raw HTML string.
        indent_size: Number of spaces per indent level (default 2).

    Returns:
        Formatted HTML string with trailing newline.
    """
    if not html or not html.strip():
        return html

    tokens = _TOKEN_RE.split(html)
    lines: list[str] = []
    level = 0
    in_style = False

    # Inline-leaf accumulation state.
    inline_parts: list[str] | None = None
    inline_depth = 0
    inline_level = 0  # indent level when inline accumulation started
    inline_glued = False  # inline leaf abuts the previous text with no whitespace

    # Text and inline leaves that touch with no whitespace between them in the
    # source stay on one line: a line break there renders as a space ("here ."
    # instead of "here.").
    prev_flow = False  # last emitted line ends with text or an inline leaf
    prev_raw = ""

    for token in tokens:
        stripped = token.strip()
        if not stripped:
            if token:
                prev_raw = token
            continue
        touches = prev_flow and not prev_raw[-1:].isspace() and not token[:1].isspace()
        prev_raw = token
        prev_flow = False

        # ── Style block handling ──────────────────────────────────────
        if in_style:
            if stripped.lower() == "</style>":
                in_style = False
                level = max(0, level - 1)
                lines.append(f"{_pad(level, indent_size)}</style>")
            else:
                # Re-indent each non-empty line of CSS at level.
                for sline in stripped.splitlines():
                    sl = sline.strip()
                    if sl:
                        lines.append(f"{_pad(level, indent_size)}{sl}")
            continue

        # ── Inline-leaf accumulation ──────────────────────────────────
        if inline_parts is not None:
            if _is_close_tag(stripped):
                tag_name = _get_close_tag_name(stripped)
                if tag_name and tag_name.lower() in _INLINE_LEAF_TAGS:
                    inline_depth -= 1
                    if inline_depth <= 0:
                        inline_parts.append(stripped)
                        combined = "".join(inline_parts)
                        if inline_glued:
                            lines[-1] += combined
                        else:
                            lines.append(f"{_pad(inline_level, indent_size)}{combined}")
                        inline_parts = None
                        inline_depth = 0
                        prev_flow = True
                        continue
                inline_parts.append(stripped)
            elif _is_open_tag(stripped):
                tag_name = _get_open_tag_name(stripped)
                if (
                    tag_name
                    and tag_name.lower() in _INLINE_LEAF_TAGS
                    and not _is_self_closing(stripped)
                ):
                    inline_depth += 1
                inline_parts.append(stripped)
            else:
                inline_parts.append(stripped)
            continue

        # ── DOCTYPE ───────────────────────────────────────────────────
        if stripped.lower().startswith("<!doctype"):
            lines.append(stripped)
            continue

        # ── MSO conditional comments ──────────────────────────────────
        if stripped.startswith("<!--[if"):
            # Self-contained: <!--[if mso]><td ...><![endif]-->
            is_self_contained = "<!--[if" in stripped and "<![endif]-->" in stripped
            lines.append(f"{_pad(level, indent_size)}{stripped}")
            if not is_self_contained:
                level += 1
            continue

        if stripped == "<![endif]-->" or stripped.startswith("<![endif]"):
            level = max(0, level - 1)
            lines.append(f"{_pad(level, indent_size)}{stripped}")
            continue

        # ── Regular comments ──────────────────────────────────────────
        if stripped.startswith("<!--"):
            lines.append(f"{_pad(level, indent_size)}{stripped}")
            continue

        # ── Closing tags ──────────────────────────────────────────────
        if _is_close_tag(stripped):
            tag_name = _get_close_tag_name(stripped)
            if tag_name and tag_name.lower() in _ALL_BLOCK_TAGS:
                level = max(0, level - 1)
            lines.append(f"{_pad(level, indent_size)}{stripped}")
            continue

        # ── Opening tags ──────────────────────────────────────────────
        if _is_open_tag(stripped):
            tag_name = _get_open_tag_name(stripped)
            if tag_name:
                tl = tag_name.lower()

                # Void / self-closing: emit at current level, no indent change.
                if tl in _VOID_TAGS or _is_self_closing(stripped):
                    lines.append(f"{_pad(level, indent_size)}{stripped}")
                    continue

                # Style block: open as block, content will be re-indented.
                if tl == "style":
                    lines.append(f"{_pad(level, indent_size)}{stripped}")
                    level += 1
                    in_style = True
                    continue

                # Inline leaf: start accumulating tokens until closing tag.
                if tl in _INLINE_LEAF_TAGS:
                    inline_parts = [stripped]
                    inline_depth = 1
                    inline_level = level
                    inline_glued = touches
                    continue

                # Block element: emit + indent children.
                if tl in _ALL_BLOCK_TAGS:
                    lines.append(f"{_pad(level, indent_size)}{stripped}")
                    level += 1
                    continue

            # Unknown opening tag — emit at current level.
            lines.append(f"{_pad(level, indent_size)}{stripped}")
            continue

        # ── Plain text ────────────────────────────────────────────────
        if touches:
            lines[-1] += stripped
        else:
            lines.append(f"{_pad(level, indent_size)}{stripped}")
        prev_flow = True

    # Flush any remaining inline parts (unclosed inline leaf — defensive).
    if inline_parts:
        combined = "".join(inline_parts)
        lines.append(f"{_pad(inline_level, indent_size)}{combined}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pad(level: int, size: int) -> str:
    """Return ``level * size`` spaces."""
    return " " * (level * size)


def _is_open_tag(token: str) -> bool:
    return token.startswith("<") and not token.startswith("</") and not token.startswith("<!")


def _is_close_tag(token: str) -> bool:
    return token.startswith("</")


def _is_self_closing(token: str) -> bool:
    return token.rstrip().endswith("/>")


def _get_open_tag_name(token: str) -> str | None:
    m = _OPEN_TAG_RE.match(token)
    return m.group(1) if m else None


def _get_close_tag_name(token: str) -> str | None:
    m = _CLOSE_TAG_RE.match(token)
    return m.group(1) if m else None
