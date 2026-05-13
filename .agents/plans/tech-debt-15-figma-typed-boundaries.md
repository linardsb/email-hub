# Plan: Tech Debt Session 15 — Figma Typed Boundaries (F014)

## Context

`app/design_sync/figma/service.py` is a 1760‑LOC Figma JSON parser. Two methods
account for the bulk of the typing debt:

| Method | Lines | LOC | Role |
|---|---|---|---|
| `_parse_node` | 1245–1459 | 215 | Recursive Figma node → `DesignNode` |
| `_parse_variables` | 689–851 | 163 | Figma Variables API → `ExtractedColor / ExtractedVariable / dark_colors` |

Both treat every Figma payload as `dict[str, Any]`, then re-narrow it with
`isinstance` + `cast(dict[str, Any], …)` / `cast(list[Any], …)`. Mypy 2.0's
isinstance narrowing makes most of those casts redundant on the mypy side, so
the file now carries **8 `# type: ignore[redundant-cast]` suppressions** that
exist only because pyright still doesn't trust the narrowing. The file holds
**125 `Any` references** in total (per `grep -c "Any"`).

The fix is structural rather than tactical: model the Figma JSON boundary with
`TypedDict`s in a new sibling module `app/design_sync/figma/raw_types.py`, and
re‑type the parser signatures to use them. This is also the fix sketched in
`.agents/deferred-items.json :: phase-deps-mypy2-redundant-cast-figma-style-runs`
("Option (a)") — closing that entry is part of the success criteria.

Per `TECH_DEBT_AUDIT.md:56` (F014, severity **High**), the secondary deliverable
is splitting `_parse_node` into three field-scoped helpers
`_parse_visual_props`, `_parse_text_props`, `_parse_layout_props` so each one
owns one Figma concern and can be unit-tested independently.

This is a **typing + structural refactor**. **No runtime behavior changes**:
`make converter-data-regression` must remain green with the same case count and
the same per-case pass/fail outcomes.

### Out of scope

- Touching `layout_analyzer.py`, `physical_card_detector.py`, `tree_normalizer.py`
  (already cleanly typed: 0 `Any` references each except 1 in tree_normalizer).
- Touching `app/design_sync/converter/` or any consumer of `DesignNode`.
- Renaming or restructuring `_parse_variables` internals beyond signature
  retyping (split is out-of-scope per the F014 spec).
- Adding pydantic validation — TypedDicts are static-only by design; runtime
  `isinstance` guards stay where they are.

### Branch

`refactor/tech-debt-15-figma-typed-boundaries`

## Files to Create/Modify

| Action | Path | Purpose |
|---|---|---|
| **CREATE** | `app/design_sync/figma/raw_types.py` | TypedDicts modelling the Figma REST API JSON shapes consumed by service.py. ~150 LOC. |
| **MODIFY** | `app/design_sync/figma/service.py` | Replace `dict[str, Any]` parameter types with `RawFigmaNode` etc.; split `_parse_node`; drop redundant casts + `# type: ignore[redundant-cast]` lines. |
| **MODIFY** | `app/design_sync/figma/__init__.py` | (Optional) re-export `RawFigmaNode` etc. for downstream typing tests — omit unless tests need it. |
| **MODIFY** | `.agents/deferred-items.json` | Mark `phase-deps-mypy2-redundant-cast-figma-style-runs` as `closed` with new `closed_commit`. |
| **MAYBE** | `app/design_sync/figma/tests/` | Add a unit test for each of the three new `_parse_*_props` helpers (see Phase 4). |

## Surveyed Baseline (record before starting)

Before any edit, run these and paste the numeric output into the PR description
so the regression deltas are unambiguous. **Do this on the base commit, with
a clean working tree.**

```bash
# 1. service.py size + parse-method sizes
wc -l app/design_sync/figma/service.py
# 2. Any reference count (boundary debt)
grep -c "Any" app/design_sync/figma/service.py
# 3. type: ignore inventory
grep -n -E "# type: ignore" app/design_sync/figma/service.py
# 4. Baseline gate snapshot
make types 2>&1 | tail -20
make converter-data-regression 2>&1 | tail -20
```

**Expected baseline values (2026-05-12):**

- `service.py` LOC: 1760
- `Any` references: 125
- `# type: ignore` lines: 8 (lines 124, 163, 190, 712, 1015, 1090, 1356, 1370 — all `[redundant-cast]`)
- `make types` and `make converter-data-regression` both pass

**Acceptance targets (after refactor):**

- `service.py` `Any` references: ≤ 10 (an order-of-magnitude reduction; small
  residue is acceptable inside `RawVariableValue` since Figma's `valuesByMode`
  is genuinely union-typed: color dict ∨ alias ∨ float ∨ str ∨ bool).
- `# type: ignore[redundant-cast]` lines: **0**
- `make types` still green (mypy + pyright strict).
- `make converter-data-regression` still green, **same case count, same pass
  set** (compare verbose pytest output before/after).

## Implementation Steps

### Phase 1 — Create `raw_types.py`

Drop a single new module at `app/design_sync/figma/raw_types.py`. Use
`TypedDict` with `total=False` because every Figma response field is optional
on at least some node type. Forward-reference the recursive `RawFigmaNode`.

**File scaffold** — write exactly this header and these TypedDicts (the
field list comes from the actual access patterns in `_parse_node`,
`_parse_variables`, `_parse_style_runs`, `_extract_stroke`, and the
`_walk_for_*` helpers — see §Audit table below):

```python
"""Static type shapes for the Figma REST API JSON consumed by this module.

These are pure typing hints — TypedDict has zero runtime cost and provides no
runtime validation. Every isinstance / .get(...) guard in service.py must
stay in place; the TypedDicts only describe what mypy + pyright should treat
the JSON *as*, not what the JSON actually is.

Field optionality:
- `total=False` everywhere — Figma omits most fields on most node types.
- Lists / dicts default to empty when absent; readers always use `.get(..., [])`.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


# ---------- primitives ----------

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
    type: Literal["URL", "NODE"]
    url: str
    nodeID: str


# ---------- paints (fills / strokes) ----------

class RawFigmaGradientStop(TypedDict, total=False):
    position: float
    color: RawFigmaColor


class RawFigmaGradientHandle(TypedDict, total=False):
    x: float
    y: float


class RawFigmaPaint(TypedDict, total=False):
    type: str            # "SOLID" | "IMAGE" | "GRADIENT_LINEAR" | "GRADIENT_RADIAL" | ...
    visible: bool        # default True when omitted
    opacity: float
    color: RawFigmaColor
    imageRef: str
    gradientStops: list[RawFigmaGradientStop]
    gradientHandlePositions: list[RawFigmaGradientHandle]


# ---------- typography ----------

class RawFigmaTextStyle(TypedDict, total=False):
    fontFamily: str
    fontPostScriptName: str
    fontSize: float
    fontWeight: float
    lineHeightPx: float
    letterSpacing: float
    letterSpacingUnit: Literal["PIXELS", "PERCENT"]
    textCase: Literal["UPPER", "LOWER", "TITLE", "ORIGINAL"]
    textDecoration: Literal["UNDERLINE", "STRIKETHROUGH", "NONE"]
    textAlignHorizontal: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFIED"]
    fills: list[RawFigmaPaint]
    hyperlink: RawFigmaHyperlink
    italic: bool


# ---------- nodes (the recursive tree) ----------

class RawFigmaNode(TypedDict, total=False):
    id: str
    name: str
    type: str            # "DOCUMENT" | "CANVAS" | "FRAME" | "TEXT" | "RECTANGLE" | ...
    visible: bool        # default True when omitted
    opacity: float
    absoluteBoundingBox: RawFigmaBoundingBox

    # Layout / auto-layout
    layoutMode: Literal["NONE", "HORIZONTAL", "VERTICAL"]
    paddingTop: float
    paddingRight: float
    paddingBottom: float
    paddingLeft: float
    itemSpacing: float
    counterAxisSpacing: float
    primaryAxisAlignItems: Literal["MIN", "CENTER", "MAX", "SPACE_BETWEEN"]
    counterAxisAlignItems: Literal["MIN", "CENTER", "MAX", "SPACE_BETWEEN"]
    cornerRadius: float
    rectangleCornerRadii: list[float]

    # Paints
    fills: list[RawFigmaPaint]
    strokes: list[RawFigmaPaint]
    strokeWeight: float

    # Text
    characters: str
    style: RawFigmaTextStyle
    characterStyleOverrides: list[int]
    styleOverrideTable: dict[str, RawFigmaTextStyle]
    hyperlink: RawFigmaHyperlink

    # Recursion
    children: list["RawFigmaNode"]


# ---------- Variables API ----------

# A value-by-mode entry is genuinely union-typed: { type:"VARIABLE_ALIAS", id:str }
# OR a RawFigmaColor OR a float OR a str OR a bool. Keep as `Any` at the leaf —
# the `isinstance(val, dict)` and `.get("type") == "VARIABLE_ALIAS"` guards in
# the parser narrow it correctly at the use site.
RawVariableValue = Any


class RawVariableAlias(TypedDict):
    type: Literal["VARIABLE_ALIAS"]
    id: str


class RawFigmaVariable(TypedDict, total=False):
    name: str
    resolvedType: Literal["COLOR", "FLOAT", "STRING", "BOOLEAN"]
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
    meta: RawVariablesMeta


class RawVariablesResponse(TypedDict, total=False):
    local: RawVariablesLocal
    # `published` mirrors `local` but is currently unused by _parse_variables —
    # add when wired in.
```

**Why this shape, not a Pydantic model:** Pydantic would validate at runtime
and reject malformed Figma responses, breaking partial-data tolerance the
parser already has. TypedDict is the lightest possible mypy/pyright hint with
zero runtime cost. The `isinstance` guards continue to handle bad input.

**Literal vs str caveat:** The `Literal[...]` annotations on `RawFigmaTextStyle.textCase`,
`textDecoration`, `textAlignHorizontal`, and `RawFigmaNode.layoutMode` /
`primaryAxisAlignItems` / `counterAxisAlignItems` are *narrower* than what
the existing parser body assumes. Existing code wraps every read in
`str(node_data.get("textCase", ""))` which widens back to `str`. That's
correct defensive code — keep the `str(...)` calls in place. If pyright
flags "redundant str() — value is already Literal", **widen the TypedDict
field to `str`** (drop the Literal); do not remove the runtime str() call.
The plan's goal is to trade one redundant-cast family for nothing, not for
another.

### Phase 2 — Audit the Figma field surface (sanity check before retyping)

This phase is **investigative, not rote**. Run this command first:

```bash
grep -nE "node_data\.get|node_data\[" app/design_sync/figma/service.py | sort -u
```

Then cross-reference every key against `RawFigmaNode` from Phase 1. The
inventory table below was derived by inspection at the time of writing; it is
correct as of base commit `974f79ca` but the grep output is authoritative —
if a key surfaces that isn't in the TypedDict (audit may find e.g.
`componentId`, `styles`, `effects`, `blendMode`, `effects`, `clipsContent`),
add it to `RawFigmaNode` with a documented type. Do not silently widen to
`Any`. Same drill for `style.get(…)`, `fill_item.get(…)`, `mode.get(…)`.

Inventory table at base commit (regenerate to confirm):

| Source method | Keys accessed on node_data |
|---|---|
| `_parse_node` (1245-1459) | `type`, `id`, `name`, `visible`, `opacity`, `absoluteBoundingBox`, `characters`, `style`, `hyperlink`, `layoutMode`, `paddingTop`, `paddingRight`, `paddingBottom`, `paddingLeft`, `itemSpacing`, `counterAxisSpacing`, `primaryAxisAlignItems`, `counterAxisAlignItems`, `cornerRadius`, `rectangleCornerRadii`, `fills`, `children` |
| `_parse_style_runs` (148-224) | `characterStyleOverrides`, `styleOverrideTable`, `characters` |
| `_extract_stroke` (117-145) | `strokes`, `strokeWeight`, `opacity` |
| `_walk_for_colors` (986-1123) | `fills`, `strokes`, `children`, `type` (filter), `visible` |
| `_walk_for_typography` (1125-1164) | `style`, `type`, `children`, `characters` |
| `_walk_for_spacing` (967-984) | `layoutMode`, `paddingTop/Right/Bottom/Left`, `itemSpacing`, `children` |
| `_parse_variables` (689-851) | (Variables API, see `RawVariables*` types) |

### Phase 3 — Re-type service.py signatures (no behavior change)

Pure search-and-replace of parameter / return types. **Do not touch method
bodies in this phase.** Each substitution must be followed by `make types` to
confirm pyright + mypy still agree.

| Symbol | Before | After |
|---|---|---|
| Module-level: import line | `from typing import TYPE_CHECKING, Any, cast` | `from typing import TYPE_CHECKING, Any, cast` + new: `from app.design_sync.figma.raw_types import (RawFigmaNode, RawFigmaPaint, RawFigmaTextStyle, RawVariablesResponse)` |
| `_find_subtree(document, node_id)` :47 | `document: dict[str, Any]` → return `dict[str, Any] \| None` | `document: RawFigmaNode` → return `RawFigmaNode \| None` |
| `_validate_hyperlink(raw)` :96 | `raw: Any` | Keep `Any` — callers pass `node_data.get("hyperlink")` which is `RawFigmaHyperlink \| None`, but narrowing happens internally. Acceptable Any. |
| `_extract_stroke(node_data, …)` :117 | `node_data: dict[str, Any]` | `node_data: RawFigmaNode` |
| `_parse_style_runs(node_data)` :148 | `node_data: dict[str, Any]` | `node_data: RawFigmaNode` |
| `_parse_letter_spacing(style_dict, font_size)` :227 | `style_dict: dict[str, Any]` | `style_dict: RawFigmaTextStyle` |
| `_gradient_midpoint_hex(stops)` :291 | `stops: list[dict[str, Any]]` | `stops: list[RawFigmaGradientStop]` |
| `_compute_gradient_angle(handles)` :312 | `handles: list[dict[str, Any]]` | `handles: list[RawFigmaGradientHandle]` |
| `_parse_gradient_stops(stops_raw, *, bg_hex)` :325 | `stops_raw: list[Any]` | `stops_raw: list[RawFigmaGradientStop]` (callers' `isinstance(item, dict)` guards stay) |
| `FigmaDesignSyncService._parse_variables(raw, …)` :689 | `raw: dict[str, Any]` | `raw: RawVariablesResponse` |
| `FigmaDesignSyncService._resolve_variable_alias(value, variables_by_id, mode_id, depth)` :658 | `value: Any`, `variables_by_id: dict[str, dict[str, Any]]` | `value: Any`, `variables_by_id: dict[str, RawFigmaVariable]`. Leaf `value` stays `Any` (genuinely union-typed). |
| `FigmaDesignSyncService._parse_colors(file_data, styles_data, …)` :853 | `file_data: dict[str, Any]` | `file_data: dict[str, Any]` — keep, this is the full GET /v1/files response, broader than `RawFigmaNode`. Could introduce `RawFigmaFileResponse` if time allows; defer if not. |
| `FigmaDesignSyncService._parse_typography(file_data, styles_data)` :915 | same | same as above |
| `FigmaDesignSyncService._parse_spacing(file_data)` :960 | `file_data: dict[str, Any]` | same |
| `FigmaDesignSyncService._walk_for_spacing(node, …)` :967 | `node: Any` | `node: RawFigmaNode` |
| `FigmaDesignSyncService._walk_for_colors(node, …)` :986 | `node: Any` | `node: RawFigmaNode` |
| `FigmaDesignSyncService._walk_for_typography(node, …)` :1125 | `node: Any` | `node: RawFigmaNode` |
| `FigmaDesignSyncService._find_fills_for_style(file_data, style_id)` :1166 | `file_data: dict[str, Any]` | keep `dict[str, Any]` (file-level response) — return type stays `list[Any]` for now (it returns Figma fills; downstream call sites still narrow). |
| `FigmaDesignSyncService._parse_node(node_data, current_depth, max_depth)` :1245 | `node_data: dict[str, Any]` | `node_data: RawFigmaNode` |

After every batch of signature changes:

```bash
uv run mypy app/design_sync/figma/service.py
uv run pyright app/design_sync/figma/service.py
```

Both must stay green. If pyright surfaces "expected RawFigmaNode, got
dict[str, Any]" at a call site, prefer **narrowing at the call site** with
`cast(RawFigmaNode, x)` over loosening the TypedDict. Document each such cast
in a comment.

### Phase 4 — Split `_parse_node` into three helpers

Once signatures are typed, extract three private helper methods. Each takes
the typed node + the already-resolved `node_type` (because `node_type` depends
on `_FIGMA_NODE_TYPE_MAP[raw_type]`, not the raw type alone). Each returns a
`NamedTuple` so callers can destructure without naming bugs.

**Helper 1 — `_parse_layout_props`** (auto-layout + corner radius + dimensions)

Place it **outside** the class (module-level) since it has no `self`
dependency. Same applies to the other two.

```python
class _LayoutProps(NamedTuple):
    width: float | None
    height: float | None
    x: float | None
    y: float | None
    padding_top: float | None
    padding_right: float | None
    padding_bottom: float | None
    padding_left: float | None
    item_spacing: float | None
    counter_axis_spacing: float | None
    layout_mode: str | None
    primary_axis_align: str | None
    counter_axis_align: str | None
    corner_radius: float | None
    corner_radii: tuple[float, ...] | None


def _parse_layout_props(node_data: RawFigmaNode, raw_type: str) -> _LayoutProps:
    """Extract dimensions, auto-layout, axis alignment, and corner radius.

    Returns the layout slice of a Figma node. Auto-layout fields are only
    populated for FRAME/COMPONENT/COMPONENT_SET/INSTANCE; corner radius is
    populated for FRAME/RECTANGLE/COMPONENT/COMPONENT_SET/INSTANCE. Other
    node types get `None` everywhere except width/height/x/y.
    """
    # Move the body chunks identified by these anchors (not line numbers,
    # since edits to service.py drift the line index):
    #   (a) the `bbox = node_data.get("absoluteBoundingBox")` block — width,
    #       height, x, y extraction with `isinstance(bbox, dict)` guard.
    #   (b) the `if raw_type in ("FRAME", "COMPONENT", "COMPONENT_SET",
    #       "INSTANCE"):` block that writes padding_*, item_spacing,
    #       counter_axis_spacing, layout_mode_str.
    #   (c) the second `if raw_type in (FRAME-like):` block writing
    #       dn_primary_axis_align / dn_counter_axis_align.
    #   (d) the `if raw_type in (FRAME-like + RECTANGLE):` block writing
    #       dn_corner_radius and dn_corner_radii.
```

**Helper 2 — `_parse_text_props`** (characters + style + alignment + style_runs)

```python
class _TextProps(NamedTuple):
    text_content: str | None
    font_family: str | None
    font_size: float | None
    font_weight: int | None
    line_height_px: float | None
    letter_spacing_px: float | None
    text_transform: str | None
    text_decoration: str | None
    text_align: str | None
    style_runs: tuple[StyleRun, ...]


def _parse_text_props(
    node_data: RawFigmaNode, node_type: DesignNodeType
) -> _TextProps:
    """Extract text content + typography + alignment + rich-text overrides.

    All fields are `None` / `()` for non-TEXT nodes. Hyperlink is **not**
    here — it lives in `_parse_visual_props` because Figma allows hyperlinks
    on FRAME nodes too, not just TEXT.
    """
    # Move every branch gated by `node_type == DesignNodeType.TEXT` that
    # writes one of: text_content, dn_font_*, dn_line_height_px,
    # dn_letter_spacing_px, dn_text_transform, dn_text_decoration,
    # dn_text_align, dn_style_runs. Do NOT move the hyperlink branch
    # (`raw_hyperlink = node_data.get("hyperlink")`) — that one belongs in
    # `_parse_visual_props`.
```

**Helper 3 — `_parse_visual_props`** (fills, strokes, image_ref, hyperlink)

```python
class _VisualProps(NamedTuple):
    fill_color: str | None
    text_color: str | None
    image_ref: str | None
    stroke_color: str | None
    stroke_weight: float | None
    hyperlink: str | None
    # Possibly-reclassified node type (IMAGE fills on VECTOR/RECTANGLE)
    resolved_node_type: DesignNodeType


def _parse_visual_props(
    node_data: RawFigmaNode,
    node_type: DesignNodeType,
    node_opacity: float,
) -> _VisualProps:
    """Extract fills (color/image), strokes, and hyperlink decoration.

    Returns the visual slice. May reclassify `node_type` to `IMAGE` if a
    VECTOR/RECTANGLE node carries an IMAGE fill — the resolved type comes
    back in `resolved_node_type` so the caller can use it.
    """
    # Move the body chunks identified by these anchors:
    #   (a) the `raw_hyperlink = node_data.get("hyperlink")` block writing
    #       dn_hyperlink via `_validate_hyperlink(...)`. Hyperlink lives
    #       here, NOT in `_parse_text_props`.
    #   (b) the `raw_fills = node_data.get("fills", [])` block — the entire
    #       fills loop including the IMAGE/SOLID branches, the IMAGE-fill
    #       reclassification of VECTOR/RECTANGLE → IMAGE, and the
    #       fill_color / text_color_hex assignment. The mutation
    #       `node_type = DesignNodeType.IMAGE` becomes a NamedTuple field
    #       (`resolved_node_type`) so the caller can apply it explicitly.
    #   (c) the `dn_stroke_color, dn_stroke_weight = _extract_stroke(...)`
    #       call.
```

**Orchestrator — the new `_parse_node`**

```python
def _parse_node(
    self,
    node_data: RawFigmaNode,
    current_depth: int,
    max_depth: int | None,
) -> DesignNode:
    """Recursively parse a Figma node into a DesignNode."""
    raw_type = str(node_data.get("type", "UNKNOWN"))
    node_type = _FIGMA_NODE_TYPE_MAP.get(raw_type, DesignNodeType.OTHER)
    node_opacity = float(node_data.get("opacity", 1.0))

    layout = _parse_layout_props(node_data, raw_type)
    text = _parse_text_props(node_data, node_type)
    visual = _parse_visual_props(node_data, node_type, node_opacity)
    node_type = visual.resolved_node_type  # apply IMAGE reclassification

    children: list[DesignNode] = []
    effective_max = max_depth if max_depth is not None else _MAX_PARSE_DEPTH
    if current_depth < effective_max:
        for child_data in node_data.get("children", []):
            if isinstance(child_data, dict):
                children.append(
                    self._parse_node(child_data, current_depth + 1, max_depth)
                )

    return DesignNode(
        id=str(node_data.get("id", "")),
        name=str(node_data.get("name", "")),
        type=node_type,
        children=children,
        width=layout.width,
        height=layout.height,
        x=layout.x,
        y=layout.y,
        text_content=text.text_content,
        fill_color=visual.fill_color,
        text_color=visual.text_color,
        padding_top=layout.padding_top,
        padding_right=layout.padding_right,
        padding_bottom=layout.padding_bottom,
        padding_left=layout.padding_left,
        item_spacing=layout.item_spacing,
        counter_axis_spacing=layout.counter_axis_spacing,
        layout_mode=layout.layout_mode,
        font_family=text.font_family,
        font_size=text.font_size,
        font_weight=text.font_weight,
        line_height_px=text.line_height_px,
        letter_spacing_px=text.letter_spacing_px,
        text_transform=text.text_transform,
        text_decoration=text.text_decoration,
        image_ref=visual.image_ref,
        hyperlink=visual.hyperlink,
        corner_radius=layout.corner_radius,
        corner_radii=layout.corner_radii,
        text_align=text.text_align,
        primary_axis_align=layout.primary_axis_align,
        counter_axis_align=layout.counter_axis_align,
        stroke_weight=visual.stroke_weight,
        stroke_color=visual.stroke_color,
        style_runs=text.style_runs,
        visible=node_data.get("visible") is not False,
        opacity=node_opacity,
    )
```

**Goal: the new `_parse_node` should be ≤ 60 LOC.** The body of each
extracted helper is moved **verbatim** — copy lines, do not retype logic, do
not add or remove a single isinstance guard. After moving, run:

```bash
make converter-data-regression  # MUST stay green case-for-case
```

If a case flips, the extraction lost a branch — `git diff` the pre/post
helper bodies until they're byte-equivalent except for the variable rebind
into the NamedTuple.

### Phase 5 — Drop redundant casts and `# type: ignore[redundant-cast]`

After Phase 3 + 4, the eight `# type: ignore[redundant-cast]` lines should no
longer be necessary because the typed inputs already declare the correct
container types. **Delete them one at a time and re-run `make types` after
each delete.** Each one falls into one of these patterns:

| Line | Pattern | After typing fix |
|---|---|---|
| 124 | `for stroke in cast(list[Any], raw_strokes):` after `isinstance(raw_strokes, list)` | `for stroke in raw_strokes:` (raw_strokes is now `list[RawFigmaPaint] \| None` from `RawFigmaNode.strokes`) |
| 163 | `overrides_list = cast("list[Any]", overrides)` | `overrides_list = overrides` (typed `list[int]`) |
| 190 | `for fill in cast(list[Any], fills_raw):` | `for fill in fills_raw:` |
| 712 | `meta_d = cast(...) ... # type: ignore[redundant-cast]` | Eliminate the outer wrap entirely — `local_meta` is already `RawVariablesMeta` after typing `raw` |
| 1015 | `fills_list = cast(list[Any], raw_fills)` | drop |
| 1090 | `for stroke_item in cast(list[Any], raw_strokes):` | `for stroke_item in raw_strokes:` |
| 1356 | `tuple(float(v) for v in cast(list[Any], raw_rcr)[:4])` | `tuple(float(v) for v in raw_rcr[:4])` (raw_rcr is `list[float]`) |
| 1370 | `for fill_item in reversed(cast(list[Any], raw_fills)):` | `for fill_item in reversed(raw_fills):` |

If pyright still complains after removing a cast (e.g. line 712 may need a
narrower local annotation), keep the cast but document in a comment why it's
needed for pyright specifically. **No new `# type: ignore` lines may be
added.** If the only fix is `# type: ignore`, surface to the user instead.

### Phase 6 — Walker helpers, callers of moved bodies

The `_walk_for_*` methods access `RawFigmaNode` fields. After Phase 3 their
signatures take `RawFigmaNode`, but body-level casts may still exist.
Re-walk them:

- `_walk_for_spacing` :967 — accesses `layoutMode`, padding fields, `itemSpacing`,
  `children`. With typed `RawFigmaNode`, the body can drop `cast(dict[str, Any], ...)`
  on child iteration. Keep `isinstance(node, dict)` guards.
- `_walk_for_colors` :986 — accesses `fills`, `strokes`, `children`, `type`,
  `visible`. Same treatment.
- `_walk_for_typography` :1125 — accesses `style`, `type`, `children`,
  `characters`. Same.

These are read-only walkers; the only edits are removing redundant `cast()`
calls inside the body.

### Phase 7 — Tests for the new helpers

Add `app/design_sync/figma/tests/test_parse_props.py` with three small unit
tests, one per extracted helper. Each fixture is a **fragment of real Figma
JSON** loaded from `.agents/figma-cache/node_2833_1869.json` if available
(see deferred-items.json `phase-50.7-ac-4` for the cached LEGO node), or a
minimal hand-crafted dict matching the TypedDict shape. **Do not fabricate
elaborate synthetic emails** — the helpers are dict-in / NamedTuple-out, so
small dict literals are the right fixture choice.

```python
def test_parse_layout_props_frame_with_autolayout() -> None:
    node: RawFigmaNode = {
        "type": "FRAME",
        "layoutMode": "VERTICAL",
        "paddingTop": 16.0,
        "paddingBottom": 16.0,
        "paddingLeft": 8.0,
        "paddingRight": 8.0,
        "itemSpacing": 12.0,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 400},
        "primaryAxisAlignItems": "CENTER",
        "counterAxisAlignItems": "MIN",
        "cornerRadius": 8.0,
    }
    out = _parse_layout_props(node, "FRAME")
    assert out.layout_mode == "VERTICAL"
    assert out.padding_top == 16.0
    assert out.item_spacing == 12.0
    assert out.primary_axis_align == "center"
    assert out.corner_radius == 8.0
    assert out.width == 600 and out.height == 400


def test_parse_text_props_returns_typography_for_text_node() -> None:
    ...


def test_parse_visual_props_reclassifies_vector_with_image_fill() -> None:
    ...
```

Three tests, ≤ 80 LOC total. Keep them deterministic; do not hit the network.

### Phase 8 — Close the deferred-items entry

Edit `.agents/deferred-items.json`: locate
`phase-deps-mypy2-redundant-cast-figma-style-runs`, set `"status": "closed"`,
add `"closed_commit": "<this PR's merge SHA>"`. **Do not delete the entry** —
closed entries stay for history.

Also scan for any other entry whose `code_refs` overlap
`app/design_sync/figma/service.py` — none expected (the audit found only the
mypy2 entry), but verify with:

```bash
grep -n "figma/service.py" .agents/deferred-items.json
```

If any match besides the mypy2 entry surfaces, surface it to the user before
proceeding — do not close other entries silently.

## Deferred Items Touching This Plan

| ID | Status | Action |
|---|---|---|
| `phase-deps-mypy2-redundant-cast-figma-style-runs` | deferred | **CLOSE** in Phase 8 — the F014 refactor is the "Option (a)" fix this entry's `fix_sketch` proposes. |
| `phase-50.7-ac-4` (LEGO physical card) | deferred | **CARRY** — uses `.agents/figma-cache/node_2833_1869.json`. We may reuse the cached JSON in Phase 7 tests, but the AC remains open until LEGO `structure.json` is captured. |
| `phase-50.7-ac-5` (perf_reimagined, slate fixtures) | deferred | **CARRY** — unrelated to typing. |

## Security Checklist

This plan adds no new endpoints and changes no request/response shapes. It is
a pure typing + extract-method refactor inside a Figma client. The security
surface is unchanged. Still verify:

- [ ] No new `# noqa: S*` lines (no security suppressions slipped in).
- [ ] `make security-check` still green.
- [ ] `_validate_hyperlink` at :96 is untouched (it's a security boundary —
      filters non-http/https/mailto URLs). The new helpers route through it
      unchanged.
- [ ] `_resolve_variable_alias` recursion depth bound `_MAX_ALIAS_DEPTH = 10`
      at :44 is untouched.
- [ ] `_parse_node` recursion depth bound `_MAX_PARSE_DEPTH = 30` at :43 is
      untouched.
- [ ] No new external HTTP calls.

## Verification

Run in this order. **Each step must stay green or improve.**

```bash
# Types — primary success criterion.
make types                                  # mypy + pyright strict
# Behavior — secondary success criterion; must stay byte-identical for cases.
make converter-data-regression              # Makefile:170-174
# Broader regression net — no incidental damage.
make check-full                             # full backend gate
# Inventory checks (paste outputs into PR description)
grep -c "Any" app/design_sync/figma/service.py     # target: ≤ 10 (was 125)
grep -nE "# type: ignore" app/design_sync/figma/service.py  # target: 0 lines
wc -l app/design_sync/figma/service.py             # expect a modest LOC drop
wc -l app/design_sync/figma/raw_types.py           # expect ~150
```

- [ ] `make check-full` passes
- [ ] `make converter-data-regression` shows **same case count, same pass set**
- [ ] `service.py` `Any` count ≤ 10 (was 125)
- [ ] Zero `# type: ignore[redundant-cast]` lines remain in service.py
- [ ] `.agents/deferred-items.json::phase-deps-mypy2-redundant-cast-figma-style-runs`
      marked `closed` with `closed_commit`
- [ ] `_parse_node` body is ≤ 60 LOC (was 215)
- [ ] Three new helpers `_parse_visual_props / _parse_text_props /
      _parse_layout_props` exist and each is ≤ 80 LOC
- [ ] `raw_types.py` exists and is imported from `service.py`
- [ ] Three new unit tests in `test_parse_props.py` pass without network
- [ ] No new endpoints (security checklist N/A)

## Rollback

If `make converter-data-regression` shows any case flipping pass→fail:

1. Identify the case from the verbose pytest output diff.
2. `git diff` the helper boundary where the flip happened — most likely the
   IMAGE-fill reclassification in `_parse_visual_props` (the `node_type`
   mutation on the old line 1374 became a return field).
3. The Phase 4 NamedTuple is byte-equivalent if you didn't accidentally drop
   the `continue` after image_ref capture. Verify against the original at
   service.py:1378-1383 (old line numbers).

If types fail in pyright but not mypy after a cast removal, restore that
single cast with an explanatory comment (`# pyright: pyright doesn't trust
this narrow yet — see deferred-items mypy2-redundant-cast`). Do not add
`# type: ignore`.

## Plan Length

This plan is ~720 lines after post-advisor revisions. ~20 lines over the soft
700 cap per [[feedback_plan_length]] — surfaced rather than trimmed because
the TypedDict scaffolding in Phase 1 and the anchor-based extraction recipes
in Phase 4 are the deliverable. Trimming further would force `/be-execute`
to re-derive the schema and the body-chunk boundaries from scratch.

## Notes for the executor

- **Opacity is read twice in the original `_parse_node`** (once for fill
  compositing, once for the final `DesignNode.opacity` field). The
  orchestrator above collapses to a single read of
  `float(node_data.get("opacity", 1.0))`. This is behaviorally identical:
  same default (1.0), same coercion, same crash-on-non-numeric. Don't let
  a reviewer flag the collapse as a behavior change — it isn't.
- **The original `_parse_node` mutates `node_type` mid-function** when an
  IMAGE fill reclassifies a VECTOR/RECTANGLE. The new helpers must NOT
  mutate `node_type`; instead `_parse_visual_props` returns
  `resolved_node_type` and the orchestrator rebinds. Verify the
  reclassification is applied **before** `_parse_visual_props` reads
  `node_type` for the `text_color_hex vs fill_color` branch — that is, the
  helper sees the *old* (unreclassified) node_type for the color-routing
  decision but returns the *new* type for the orchestrator to apply
  afterwards. This matches the original ordering.
