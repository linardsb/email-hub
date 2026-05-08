"""HTML/CSS sanitisers for design_sync converter pipeline.

Splits out from ``converter.py`` the small pure helpers that strip dangerous
CSS values, detect visible content, and rewrite web-only HTML tags into the
``<table>`` / ``<td>`` structure that email clients render reliably.
"""

from __future__ import annotations

import re

from app.design_sync.protocol import DesignNode, DesignNodeType

_DANGEROUS_CSS_RE = re.compile(
    r"expression\s*\(|url\s*\(\s*javascript\s*:|url\s*\(\s*data\s*:\s*text/html"
    r"|-moz-binding\s*:",
    re.IGNORECASE,
)

_LAYOUT_CSS_RE = re.compile(
    r"(?:^|;)\s*(?:width|max-width|float|display\s*:\s*(?:inline-block|flex|grid))",
    re.IGNORECASE,
)

_DIV_TOKEN_RE = re.compile(r"(<div(?:\s[^>]*)?>|</div>)", re.IGNORECASE)
_TD_TAG_RE = re.compile(r"</?td[\s>]", re.IGNORECASE)


def _has_visible_content(node: DesignNode) -> bool:
    """Return True if node or any descendant has visible content (text/image)."""
    if node.type in (DesignNodeType.TEXT, DesignNodeType.IMAGE):
        return True
    return any(_has_visible_content(c) for c in (node.children or []))


def _sanitize_css_value(value: str) -> str:
    """Strip characters that could break out of a CSS property value.

    Removes semicolons, braces, angle brackets, and other injection vectors.
    Preserves balanced parentheses for safe CSS functions (rgb, hsl, calc).
    Returns empty string if the value is entirely unsafe.
    """
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    sanitized = _DANGEROUS_CSS_RE.sub("", sanitized)
    sanitized = re.sub(r'[;<>{}\'"\\]+', "", sanitized)
    return sanitized.strip()


def _is_inside_td(html_str: str, pos: int) -> bool:
    """Check whether *pos* is inside a ``<td>`` cell (handles nested tables)."""
    depth = 0
    for m in _TD_TAG_RE.finditer(html_str, 0, pos):
        if m.group().startswith("</"):
            depth -= 1
        else:
            depth += 1
    return depth > 0


def sanitize_web_tags_for_email(html_str: str) -> str:
    """Clean web tags for email-safe output.

    Rules:
    - MSO conditional comments: preserved untouched.
    - ``<p>`` tags: stripped everywhere — content kept, styles merged into
      parent ``<td>`` when inside one, ``<br><br>`` separators when outside.
    - ``<h1>``-``<h6>`` tags: stripped everywhere — same merge/unwrap logic.
    - ``<div>`` with layout CSS (width/max-width/flex/float/inline-block):
      converted to ``<table role="presentation"><tr><td>`` wrapper.
    - ``<div>`` simple wrapper inside ``<td>`` (e.g. text-align): preserved.
    - ``<div>`` outside ``<td>`` with no layout CSS: unwrapped.
    """
    mso_blocks: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        mso_blocks.append(m.group(0))
        return f"__MSO_{len(mso_blocks) - 1}__"

    html_str = re.compile(r"<!--\[if\s[^\]]*\]>.*?<!\[endif\]-->", re.DOTALL).sub(_stash, html_str)

    ph_re = re.compile(r"<(p|h[1-6])(\s[^>]*)?>(.+?)</\1>", re.DOTALL)
    matches = list(ph_re.finditer(html_str))
    for i, m in enumerate(reversed(matches)):
        idx_from_end = i  # 0 = last match
        attrs = m.group(2) or ""
        inner_content = m.group(3)
        if _is_inside_td(html_str, m.start()):
            extra_td_attrs: list[str] = []
            for attr_name in ("data-slot", "data-slot-name", "class"):
                attr_match = re.search(rf'{attr_name}=["\']([^"\']*)["\']', attrs)
                if attr_match:
                    extra_td_attrs.append(attr_match.group(0))

            style_match = re.search(r'style=["\']([^"\']*)["\']', attrs)
            inner_style = style_match.group(1) if style_match else ""
            inner_style = re.sub(r"\bmargin\b", "padding", inner_style)

            td_before = html_str[: m.start()].rfind("<td")
            if td_before >= 0:
                td_end = html_str.index(">", td_before) + 1
                td_tag = html_str[td_before:td_end]

                if inner_style:
                    td_style_match = re.search(r'style=["\']([^"\']*)["\']', td_tag)
                    if td_style_match:
                        merged = td_style_match.group(1).rstrip(";") + ";" + inner_style
                        td_tag = (
                            td_tag[: td_style_match.start(1)]
                            + merged
                            + td_tag[td_style_match.end(1) :]
                        )
                    else:
                        td_tag = td_tag[:-1] + f' style="{inner_style}">'

                for attr_str in extra_td_attrs:
                    attr_key = attr_str.split("=")[0]
                    if attr_key not in td_tag:
                        td_tag = td_tag[:-1] + f" {attr_str}>"

                new_html = (
                    html_str[:td_before]
                    + td_tag
                    + html_str[td_end : m.start()]
                    + inner_content
                    + html_str[m.end() :]
                )
                html_str = new_html
            else:
                html_str = html_str[: m.start()] + inner_content + html_str[m.end() :]
        else:
            suffix = "" if idx_from_end == 0 else "<br><br>"
            html_str = html_str[: m.start()] + inner_content + suffix + html_str[m.end() :]

    tokens = list(_DIV_TOKEN_RE.finditer(html_str))

    pairs: list[tuple[str, str, int, int]] = []
    stack: list[int] = []
    for ti, tok in enumerate(tokens):
        if tok.group().startswith("</"):
            if stack:
                open_idx = stack.pop()
                open_tok = tokens[open_idx]
                attrs_match = re.match(r"<div(\s[^>]*)?>", open_tok.group(), re.IGNORECASE)
                attrs = attrs_match.group(1) if attrs_match and attrs_match.group(1) else ""
                style_match = re.search(r'style=["\']([^"\']*)["\']', attrs)
                style_val = style_match.group(1) if style_match else ""

                if 'class="column"' in attrs:
                    action = "preserve"
                elif _LAYOUT_CSS_RE.search(style_val):
                    action = "convert"
                elif _is_inside_td(html_str, open_tok.start()):
                    action = "preserve"
                else:
                    action = "unwrap"
                pairs.append((action, style_val, open_idx, ti))
        else:
            stack.append(ti)

    all_replacements: list[tuple[int, int, str]] = []
    for action, style_val, open_idx, close_idx in pairs:
        open_tok = tokens[open_idx]
        close_tok = tokens[close_idx]

        if action == "convert":
            safe_style = (
                style_val.replace('"', "").replace("'", "").replace("<", "").replace(">", "")
            )
            safe_style = _DANGEROUS_CSS_RE.sub("", safe_style)
            table_open = (
                '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
                f'<tr><td style="{safe_style}">'
            )
            all_replacements.append((open_tok.start(), open_tok.end(), table_open))
            all_replacements.append((close_tok.start(), close_tok.end(), "</td></tr></table>"))
        elif action == "preserve":
            pass
        else:  # unwrap
            all_replacements.append((open_tok.start(), open_tok.end(), ""))
            all_replacements.append((close_tok.start(), close_tok.end(), ""))

    for start, end, replacement in sorted(all_replacements, key=lambda r: r[0], reverse=True):
        html_str = html_str[:start] + replacement + html_str[end:]

    for i, block in enumerate(mso_blocks):
        cleaned = ph_re.sub(r"\3", block)
        html_str = html_str.replace(f"__MSO_{i}__", cleaned)

    return html_str
