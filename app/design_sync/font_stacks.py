r"""Font fallback stacks by category (CE-7, #425).

:func:`font_stack` returns the design family followed by a web-safe stack of
the same category, so a client without the design font falls back to a
similar face instead of the browser default serif.

Figma exposes no generic family for a font (text styles carry only
``fontFamily``/``fontPostScriptName``/size/style/weight), so the category is
inferred from the family name: mono keywords first (``Noto Sans Mono`` stays
mono), then sans keywords (``Merriweather Sans`` stays sans), then serif
keywords and known serif names, else sans.

The output is attribute-safe without escaping: each family keeps only word
characters plus `` .-``, so no ``"``, ``<``, ``>``, ``&``, ``;`` or ``\``
survives. Callers must not ``html.escape`` it: ``'`` would become ``&#x27;``,
whose ``;`` ends the renderer's ``font-family:[^;"]+`` matches on a second
write.
"""

from __future__ import annotations

import re
from enum import StrEnum


class FontCategory(StrEnum):
    """Font category; the value is the CSS generic family that ends its stack."""

    SANS = "sans-serif"
    SERIF = "serif"
    MONO = "monospace"


_CATEGORY_STACK: dict[FontCategory, tuple[str, ...]] = {
    FontCategory.SANS: ("Helvetica", "Arial", "sans-serif"),
    FontCategory.SERIF: ("Georgia", "Times New Roman", "serif"),
    FontCategory.MONO: ("Courier New", "Courier", "monospace"),
}

# Same set as content_checks.GENERIC_FAMILIES.
_GENERIC = frozenset(
    {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
    }
)

# Token prefixes, so "Consolas" matches "consol".
_MONO_PREFIXES = ("mono", "code", "courier", "consol", "menlo", "monaco")
_SANS_PREFIXES = ("sans", "grotesk", "grotesque")
# Whole tokens, so "EB Garamond" matches "garamond".
_SERIF_TOKENS = frozenset(
    {
        "serif",
        "slab",
        "georgia",
        "times",
        "garamond",
        "baskerville",
        "bodoni",
        "didot",
        "caslon",
        "playfair",
        "merriweather",
        "lora",
        "cambria",
        "palatino",
        "cormorant",
        "crimson",
        "spectral",
        "domine",
    }
)

_UNSAFE_RE = re.compile(r"[^\w .-]")
_TOKEN_SPLIT_RE = re.compile(r"[\s-]+")


def _clean(name: str) -> str:
    r"""Drop every character outside ``\w`` and `` .-`` and collapse spaces."""
    return " ".join(_UNSAFE_RE.sub("", name).split())


def _split(value: str) -> list[str]:
    """Split a ``font-family`` value into cleaned family names, dropping empties."""
    return [name for name in (_clean(part) for part in value.split(",")) if name]


def font_category(family: str) -> FontCategory:
    """Category of one family name, inferred from its tokens."""
    tokens = _TOKEN_SPLIT_RE.split(_clean(family).lower())
    if any(t.startswith(p) for t in tokens for p in _MONO_PREFIXES):
        return FontCategory.MONO
    if any(t.startswith(p) for t in tokens for p in _SANS_PREFIXES):
        return FontCategory.SANS
    if any(t in _SERIF_TOKENS for t in tokens):
        return FontCategory.SERIF
    return FontCategory.SANS


def _render(name: str) -> str:
    """CSS form of one family: generics bare and lower-case; spaces or digit-leading tokens quoted."""
    if name.lower() in _GENERIC:
        return name.lower()
    if " " in name or any(t[:1].isdigit() for t in name.split()):
        return f"'{name}'"
    return name


def font_stack(family: str) -> str:
    """``font-family`` value for a design family or family list.

    A single family gets its category stack appended. A list ending in a
    generic family is returned normalised but otherwise unchanged, so the
    function is idempotent. A list without one keeps every family and gets the
    first family's stack. Duplicates are dropped ignoring case and quotes.
    """
    names = _split(family)
    if names and names[-1].lower() in _GENERIC:
        return ", ".join(_render(n) for n in names)
    category = font_category(names[0]) if names else FontCategory.SANS
    out: list[str] = []
    seen: set[str] = set()
    for name in [*names, *_CATEGORY_STACK[category]]:
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return ", ".join(_render(n) for n in out)
