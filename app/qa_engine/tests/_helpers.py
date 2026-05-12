"""Shared helpers for QA-engine per-check test files.

Relocated from `test_checks.py::_valid_html` during the Part C split (F067).
Each per-check test file imports `valid_html` to build structurally complete
email HTML with configurable omissions.
"""


def valid_html(
    *,
    doctype: bool = True,
    charset: bool = True,
    viewport: bool = True,
    title: str = "Email",
    head_extra: str = "",
    body: str = '<table role="presentation"><tr><td>Hello</td></tr></table>',
) -> str:
    """Build structurally complete email HTML with configurable omissions."""
    parts: list[str] = []
    if doctype:
        parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    if charset:
        parts.append('<meta charset="utf-8">')
    if viewport:
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    if title:
        parts.append(f"<title>{title}</title>")
    parts.append(head_extra)
    parts.append("</head>")
    parts.append(f"<body>{body}</body>")
    parts.append("</html>")
    return "\n".join(parts)
