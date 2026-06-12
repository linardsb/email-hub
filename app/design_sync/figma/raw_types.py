"""Static type shapes for the Figma REST API JSON consumed by this module.

These are pure typing hints — TypedDict has zero runtime cost and provides no
runtime validation. Every isinstance / .get(...) guard in service.py must
stay in place; the TypedDicts only describe what mypy + pyright should treat
the JSON *as*, not what the JSON actually is.

Field optionality:
- ``total=False`` everywhere — Figma omits most fields on most node types.
- Lists / dicts default to empty when absent; readers always use ``.get(..., [])``.
"""

from __future__ import annotations

from typing import Any, TypedDict

# ── Primitives ──


class RawFigmaColor(TypedDict, total=False):
    r: float
    g: float
    b: float
    a: float


class RawFigmaBoundingBox(TypedDict, total=False):
    x: float
    y: float
    width: float
    height: float


class RawFigmaHyperlink(TypedDict, total=False):
    type: str  # "URL" | "NODE"
    url: str
    nodeID: str


# ── Paints (fills / strokes) ──


class RawFigmaGradientStop(TypedDict, total=False):
    position: float
    color: RawFigmaColor


class RawFigmaGradientHandle(TypedDict, total=False):
    x: float
    y: float


class RawFigmaPaint(TypedDict, total=False):
    type: str  # "SOLID" | "IMAGE" | "GRADIENT_LINEAR" | "GRADIENT_RADIAL" | ...
    visible: bool  # default True when omitted
    opacity: float
    color: RawFigmaColor
    imageRef: str
    gradientStops: list[RawFigmaGradientStop]
    gradientHandlePositions: list[RawFigmaGradientHandle]


# ── Typography ──


class RawFigmaTextStyle(TypedDict, total=False):
    fontFamily: str
    fontPostScriptName: str
    fontSize: float
    fontWeight: float
    lineHeightPx: float
    lineHeightPercent: float  # legacy: % of the font's default line height
    lineHeightPercentFontSize: float  # % of font size
    # letterSpacing / hyperlink / fills are checked with isinstance at the use
    # site — keep as Any/list[Any] so the runtime guards remain "necessary"
    # under pyright strict mode.
    letterSpacing: Any
    textCase: str  # "UPPER" | "LOWER" | "TITLE" | "ORIGINAL"
    textDecoration: str  # "UNDERLINE" | "STRIKETHROUGH" | "NONE"
    textAlignHorizontal: str  # "LEFT" | "CENTER" | "RIGHT" | "JUSTIFIED"
    fills: list[Any]
    hyperlink: Any
    italic: bool


# ── Nodes (the recursive tree) ──


class RawFigmaNode(TypedDict, total=False):
    """The shape this module *expects* from a Figma node payload.

    Fields that the parser validates with ``isinstance`` at each use site are
    typed as ``Any``/``list[Any]``/``dict[str, Any]`` so the runtime guards
    remain "necessary" under pyright strict mode. This mirrors the
    ``RawVariableValue = Any`` idiom used for variable values.
    """

    id: str
    name: str
    type: str  # "DOCUMENT" | "CANVAS" | "FRAME" | "TEXT" | "RECTANGLE" | ...
    visible: bool  # default True when omitted
    opacity: float
    absoluteBoundingBox: Any  # dict-checked at use site

    # Layout / auto-layout
    layoutMode: str  # "NONE" | "HORIZONTAL" | "VERTICAL"
    paddingTop: float
    paddingRight: float
    paddingBottom: float
    paddingLeft: float
    itemSpacing: float
    counterAxisSpacing: float
    primaryAxisAlignItems: str  # "MIN" | "CENTER" | "MAX" | "SPACE_BETWEEN" | "SPACE_AROUND"
    counterAxisAlignItems: str
    cornerRadius: float
    # Typed as list[Any] so the parser's per-item ``isinstance(item, dict)``
    # guards remain necessary; the entry-level ``isinstance(field, list)``
    # checks are unnecessary under this typing and have been removed.
    rectangleCornerRadii: list[Any]
    fills: list[Any]
    strokes: list[Any]
    strokeWeight: float

    # Text
    characters: str
    style: Any  # dict-checked at use site
    characterStyleOverrides: list[Any]
    styleOverrideTable: dict[str, Any]
    hyperlink: Any  # dict-or-str, _validate_hyperlink narrows

    # Recursion — children may contain non-dict entries; iter with isinstance
    children: list[Any]


# ── Variables API ──


# A value-by-mode entry is genuinely union-typed: {type:"VARIABLE_ALIAS", id:str}
# OR a RawFigmaColor OR a float OR a str OR a bool. Keep as Any at the leaf —
# isinstance(val, dict) and .get("type") == "VARIABLE_ALIAS" guards in the
# parser narrow it correctly at the use site.
RawVariableValue = Any


class RawVariableAlias(TypedDict):
    type: str  # "VARIABLE_ALIAS"
    id: str


class RawFigmaVariable(TypedDict, total=False):
    name: str
    resolvedType: str  # "COLOR" | "FLOAT" | "STRING" | "BOOLEAN"
    variableCollectionId: str
    valuesByMode: dict[str, RawVariableValue]


class RawFigmaVariableMode(TypedDict, total=False):
    modeId: str
    name: str


class RawFigmaVariableCollection(TypedDict, total=False):
    name: str
    modes: list[RawFigmaVariableMode]


class RawVariablesMeta(TypedDict, total=False):
    variableCollections: dict[str, RawFigmaVariableCollection]
    variables: dict[str, RawFigmaVariable]


class RawVariablesLocal(TypedDict, total=False):
    # meta is dict-checked with isinstance — keep Any to preserve the guard
    meta: Any


class RawVariablesResponse(TypedDict, total=False):
    # local/published are dict-checked at use site — keep Any to preserve guards
    local: Any
    published: Any
