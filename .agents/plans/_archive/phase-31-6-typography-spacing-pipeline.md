# Plan: 31.6 Enriched Typography & Spacing Token Pipeline

## Context

Three fidelity gaps in the typography/spacing pipeline:
- **(a)** Assembler ignores `DefaultTokens.font_sizes` and `.spacing` — no replacement steps for font-size, line-height, font-weight, or spacing
- **(b)** Figma spacing data lost — `DesignNode` only has `width/height/x/y`; Figma auto-layout `paddingTop/itemSpacing/layoutMode` never reaches the data model
- **(c)** `TextBlock.font_size` set to `node.height` (bounding box), not actual font size — `layout_analyzer.py:335`

After 31.2, inline CSS shorthands are expanded (`font: 700 32px/40px Inter` → individual properties), so token extraction can use simple regex on longhands.

## Files to Modify

| File | Change |
|------|--------|
| `app/design_sync/protocol.py` | Add 12 fields to `DesignNode` (auto-layout + typography) |
| `app/design_sync/figma/service.py` | Extract auto-layout + TEXT typography in `_parse_node` |
| `app/design_sync/penpot/service.py` | Extract auto-layout + TEXT typography in `_obj_to_node` |
| `app/design_sync/figma/layout_analyzer.py` | Fix `TextBlock.font_size`, add typography/spacing fields to `TextBlock`/`EmailSection`/`DesignLayoutDescription`, add `generate_spacing_map()` |
| `app/templates/upload/analyzer.py` | Add font-weight/line-height/letter-spacing/responsive extraction to `_extract_tokens()`, extend `TokenInfo` |
| `app/templates/upload/token_extractor.py` | Add `_resolve_font_weights()`, `_resolve_line_heights()`, `_resolve_letter_spacings()`, `_resolve_responsive()`, enrich `_resolve_colors()` |
| `app/ai/templates/models.py` | Add `font_weights`, `line_heights`, `letter_spacings`, `responsive`, `responsive_breakpoints` to `DefaultTokens` |
| `app/ai/agents/schemas/build_plan.py` | Mirror new fields on `DesignTokens` |
| `app/ai/agents/scaffolder/assembler.py` | Add steps 3b–3f: font-size, line-height, spacing, font-weight, responsive replacement |
| `app/templates/upload/design_system_mapper.py` | Map font_weights, line_heights, letter_spacings, responsive tokens |
| `app/design_sync/spacing_bridge.py` | **New file** — `figma_spacing_to_tokens()`, `figma_typography_to_tokens()` |

### Test Files to Modify/Create

| File | Change |
|------|--------|
| `app/design_sync/tests/test_layout_analyzer.py` | Tests for new spacing/typography fields, font_size fix |
| `app/templates/upload/tests/test_extractors.py` | Tests for new token extraction (font-weight, line-height, responsive) |
| `app/templates/upload/tests/test_design_system_mapper.py` | Tests for new field mapping |
| `app/ai/agents/scaffolder/tests/test_assembler_typography.py` | **New** — tests for steps 3b–3f |
| `app/design_sync/tests/test_spacing_bridge.py` | **New** — tests for spacing/typography bridge |

## Implementation Steps

### Step 1: Extend `DesignNode` data model (`protocol.py`)

Add to `DesignNode` frozen dataclass (after `text_color` field, line 76):

```python
# Auto-layout spacing (Figma/Penpot frames)
padding_top: float | None = None
padding_right: float | None = None
padding_bottom: float | None = None
padding_left: float | None = None
item_spacing: float | None = None
counter_axis_spacing: float | None = None
layout_mode: str | None = None  # "HORIZONTAL", "VERTICAL", or None

# Typography (TEXT nodes — actual values, not bounding box)
font_family: str | None = None
font_size: float | None = None
font_weight: int | None = None
line_height_px: float | None = None
letter_spacing_px: float | None = None
```

### Step 2: Extract auto-layout + typography in Figma `_parse_node` (`figma/service.py`)

In `_parse_node()` (line 483), after text content extraction (line 513) and before fill color extraction (line 515), add:

```python
# Auto-layout properties (frames with auto-layout)
padding_top: float | None = None
padding_right: float | None = None
padding_bottom: float | None = None
padding_left: float | None = None
item_spacing: float | None = None
counter_axis_spacing: float | None = None
layout_mode_str: str | None = None
if raw_type == "FRAME":
    layout_mode_str = node_data.get("layoutMode")  # "HORIZONTAL"/"VERTICAL"/None
    if layout_mode_str and layout_mode_str != "NONE":
        padding_top = _float_or_none(node_data.get("paddingTop"))
        padding_right = _float_or_none(node_data.get("paddingRight"))
        padding_bottom = _float_or_none(node_data.get("paddingBottom"))
        padding_left = _float_or_none(node_data.get("paddingLeft"))
        item_spacing = _float_or_none(node_data.get("itemSpacing"))
        counter_axis_spacing = _float_or_none(node_data.get("counterAxisSpacing"))

# TEXT node typography
dn_font_family: str | None = None
dn_font_size: float | None = None
dn_font_weight: int | None = None
dn_line_height_px: float | None = None
dn_letter_spacing_px: float | None = None
if node_type == DesignNodeType.TEXT:
    style = node_data.get("style", {})
    if isinstance(style, dict):
        dn_font_family = style.get("fontFamily")
        raw_fs = style.get("fontSize")
        dn_font_size = float(raw_fs) if isinstance(raw_fs, (int, float)) else None
        raw_fw = style.get("fontWeight")
        dn_font_weight = int(raw_fw) if isinstance(raw_fw, (int, float)) else None
        raw_lh = style.get("lineHeightPx")
        dn_line_height_px = float(raw_lh) if isinstance(raw_lh, (int, float)) else None
        raw_ls = style.get("letterSpacing")
        dn_letter_spacing_px = float(raw_ls) if isinstance(raw_ls, (int, float)) else None
```

Pass all new fields to `DesignNode(...)` constructor at end of method.

Add helper at module level:
```python
def _float_or_none(val: Any) -> float | None:
    return float(val) if isinstance(val, (int, float)) else None
```

### Step 3: Extract auto-layout + typography in Penpot `_obj_to_node` (`penpot/service.py`)

In `_obj_to_node()` (line 290), after text content extraction and before fill color extraction:

```python
# Auto-layout spacing
padding_top = padding_right = padding_bottom = padding_left = None
item_spacing_val = counter_axis_spacing_val = None
layout_mode_val: str | None = None
layout = obj.get("layout")
if layout in ("flex", "grid"):
    pad = obj.get("layout-padding", {})
    padding_top = _float_or_none(pad.get("p1"))   # Penpot uses p1/p2/p3/p4
    padding_right = _float_or_none(pad.get("p2"))
    padding_bottom = _float_or_none(pad.get("p3"))
    padding_left = _float_or_none(pad.get("p4"))
    gap = obj.get("layout-gap", {})
    item_spacing_val = _float_or_none(gap.get("row-gap"))
    counter_axis_spacing_val = _float_or_none(gap.get("column-gap"))
    flex_dir = obj.get("layout-flex-dir", "column")
    layout_mode_val = "VERTICAL" if flex_dir == "column" else "HORIZONTAL"

# TEXT node typography
dn_font_family = dn_font_size = dn_font_weight = dn_line_height_px = dn_letter_spacing_px = None
if node_type_str == "text":
    content = obj.get("content", {})
    paragraphs = content.get("children", []) if isinstance(content, dict) else []
    # Use first span's style as representative
    for para in paragraphs:
        for span in para.get("children", []):
            dn_font_family = dn_font_family or span.get("font-family")
            raw_fs = span.get("font-size")
            if raw_fs is not None and dn_font_size is None:
                dn_font_size = float(raw_fs)
            raw_fw = span.get("font-weight")
            if raw_fw is not None and dn_font_weight is None:
                dn_font_weight = int(float(raw_fw)) if isinstance(raw_fw, (int, float, str)) else None
            raw_lh = span.get("line-height")
            if raw_lh is not None and dn_line_height_px is None:
                dn_line_height_px = float(raw_lh) if isinstance(raw_lh, (int, float)) else None
```

Pass all new fields to `DesignNode(...)` constructor. Add module-level `_float_or_none` helper.

**Note:** Penpot padding keys may be `p1/p2/p3/p4` or `top/right/bottom/left` depending on version — verify against actual API response in tests. Use `pad.get("p1") or pad.get("top")` pattern.

### Step 4: Fix `TextBlock` & extend `EmailSection` (`layout_analyzer.py`)

**4a. Extend `TextBlock`** (line 36):
```python
@dataclass(frozen=True)
class TextBlock:
    node_id: str
    content: str
    font_size: float | None = None
    is_heading: bool = False
    font_family: str | None = None
    font_weight: int | None = None
    line_height: float | None = None
    letter_spacing: float | None = None
```

**4b. Extend `EmailSection`** (line 66) — add after `bg_color`:
```python
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None
    item_spacing: float | None = None
    element_gaps: tuple[float, ...] = ()
```

**4c. Add `spacing_map` to `DesignLayoutDescription`** (line 85):
```python
    spacing_map: dict[str, dict[str, float]] = field(default_factory=dict)
```

**4d. Fix `_walk_for_texts`** (line 327) — use actual font_size, populate typography:
```python
def _walk_for_texts(node: DesignNode, results: list[TextBlock]) -> None:
    if node.type == DesignNodeType.TEXT and node.text_content:
        results.append(
            TextBlock(
                node_id=node.id,
                content=node.text_content,
                font_size=node.font_size if node.font_size is not None else node.height,
                is_heading=False,
                font_family=node.font_family,
                font_weight=node.font_weight,
                line_height=node.line_height_px,
                letter_spacing=node.letter_spacing_px,
            )
        )
    for child in node.children:
        _walk_for_texts(child, results)
```

**4e. Populate `EmailSection` spacing** in `analyze_layout()` (inside the section-building loop, ~line 155):
```python
sections.append(
    EmailSection(
        ...existing fields...,
        bg_color=node.fill_color,
        padding_top=node.padding_top,
        padding_right=node.padding_right,
        padding_bottom=node.padding_bottom,
        padding_left=node.padding_left,
        item_spacing=node.item_spacing,
    )
)
```

**4f. Compute element_gaps** — after `_calculate_spacing`, add element gap computation:
```python
def _compute_element_gaps(section: EmailSection) -> tuple[float, ...]:
    """Compute gaps between consecutive text/image/button elements by y-position."""
    # Collect all child y-positions + heights (from texts primarily)
    # If section has item_spacing from auto-layout, return uniform tuple
    if section.item_spacing is not None:
        n_children = len(section.texts) + len(section.images) + len(section.buttons)
        if n_children > 1:
            return tuple(section.item_spacing for _ in range(n_children - 1))
    return ()
```

**4g. Generate spacing map** — add `generate_spacing_map()`:
```python
def generate_spacing_map(sections: list[EmailSection]) -> dict[str, dict[str, float]]:
    """Build per-section spacing specification from layout analysis."""
    result: dict[str, dict[str, float]] = {}
    for section in sections:
        entry: dict[str, float] = {}
        if section.padding_top is not None:
            entry["padding_top"] = section.padding_top
        if section.padding_right is not None:
            entry["padding_right"] = section.padding_right
        if section.padding_bottom is not None:
            entry["padding_bottom"] = section.padding_bottom
        if section.padding_left is not None:
            entry["padding_left"] = section.padding_left
        if section.item_spacing is not None:
            entry["item_spacing"] = section.item_spacing
        if section.spacing_after is not None:
            entry["spacing_after"] = section.spacing_after
        if entry:
            result[section.node_id] = entry
    return result
```

Call at end of `analyze_layout()`, set on `DesignLayoutDescription`.

### Step 5: Extend `DefaultTokens` and `DesignTokens`

**5a. `app/ai/templates/models.py` — `DefaultTokens`** (line 61):
```python
@dataclass(frozen=True)
class DefaultTokens:
    colors: dict[str, str] = field(default_factory=dict)
    fonts: dict[str, str] = field(default_factory=dict)
    font_sizes: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, str] = field(default_factory=dict)
    font_weights: dict[str, str] = field(default_factory=dict)
    line_heights: dict[str, str] = field(default_factory=dict)
    letter_spacings: dict[str, str] = field(default_factory=dict)
    responsive: dict[str, str] = field(default_factory=dict)
    responsive_breakpoints: tuple[str, ...] = ()
```

**5b. `app/ai/agents/schemas/build_plan.py` — `DesignTokens`** (line 32):
Add matching fields after `spacing`:
```python
    font_weights: dict[str, str] = field(default_factory=dict)
    line_heights: dict[str, str] = field(default_factory=dict)
    letter_spacings: dict[str, str] = field(default_factory=dict)
    responsive: dict[str, str] = field(default_factory=dict)
```

All fields have defaults — backward compatible, no migration needed.

### Step 6: Extend HTML token extraction (`analyzer.py`)

**6a. Extend `TokenInfo`** (line 42):
```python
@dataclass
class TokenInfo:
    colors: dict[str, list[str]] = field(default_factory=dict)
    fonts: dict[str, list[str]] = field(default_factory=dict)
    font_sizes: dict[str, list[str]] = field(default_factory=dict)
    spacing: dict[str, list[str]] = field(default_factory=dict)
    font_weights: dict[str, list[str]] = field(default_factory=dict)
    line_heights: dict[str, list[str]] = field(default_factory=dict)
    letter_spacings: dict[str, list[str]] = field(default_factory=dict)
    color_roles: dict[str, list[str]] = field(default_factory=dict)
    responsive: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    responsive_breakpoints: list[str] = field(default_factory=list)
```

**6b. Extend `_extract_tokens()`** (line 408) — add patterns and collection:

After existing patterns (line 413), add:
```python
font_weight_pattern = re.compile(r"font-weight:\s*(\d{3}|bold|normal|lighter|bolder)")
line_height_pattern = re.compile(r"line-height:\s*([\d.]+(?:px|em|rem|%)?)")
letter_spacing_pattern = re.compile(r"letter-spacing:\s*(-?[\d.]+(?:px|em|rem)?)")
padding_side_pattern = re.compile(r"padding-(top|right|bottom|left):\s*(\d+(?:px|em|rem))")
```

Add collection lists:
```python
font_weights_heading: list[str] = []
font_weights_body: list[str] = []
line_heights_heading: list[str] = []
line_heights_body: list[str] = []
letter_spacings_all: list[str] = []
color_roles: dict[str, list[str]] = {"link": [], "heading_text": [], "muted": [], "accent": []}
```

Inside the element loop, after existing extractions:
```python
# Font weights — classify by tag
for match in font_weight_pattern.finditer(style):
    val = match.group(1)
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        font_weights_heading.append(val)
    else:
        font_weights_body.append(val)

# Line heights
for match in line_height_pattern.finditer(style):
    val = match.group(1)
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        line_heights_heading.append(val)
    else:
        line_heights_body.append(val)

# Letter spacing
for match in letter_spacing_pattern.finditer(style):
    letter_spacings_all.append(match.group(1))

# Per-side padding (longhand from 31.2 expansion)
for match in padding_side_pattern.finditer(style):
    spacings.append(match.group(2))

# Color roles by element context
if tag == "a":
    for m in hex_pattern.finditer(style):
        if "color" in style.lower()[:m.start()]:
            color_roles["link"].append(m.group().upper())
```

**6c. Add responsive extraction** — after the element loop, extract `@media` from `<style>` blocks:

```python
responsive: dict[str, dict[str, list[str]]] = {}
breakpoints: list[str] = []
media_pattern = re.compile(
    r"@media[^{]*max-width:\s*(\d+px)[^{]*\{(.*?)\}", re.DOTALL
)
for style_el in tree.iter("style"):
    text = style_el.text or ""
    for m in media_pattern.finditer(text):
        bp = m.group(1)
        if bp not in breakpoints:
            breakpoints.append(bp)
        block = m.group(2)
        bp_tokens: dict[str, list[str]] = responsive.setdefault(bp, {})
        for fs_m in font_size_pattern.finditer(block):
            bp_tokens.setdefault("font_sizes", []).append(fs_m.group(1))
        for sp_m in padding_pattern.finditer(block):
            bp_tokens.setdefault("spacing", []).append(sp_m.group(1))
```

Include all new fields in the returned `TokenInfo`.

### Step 7: Extend `TokenExtractor` (`token_extractor.py`)

Add new resolution methods and enrich `extract()`:

```python
def extract(self, token_info: TokenInfo) -> DefaultTokens:
    colors = self._resolve_colors(token_info)
    fonts = self._resolve_fonts(token_info)
    font_sizes = self._resolve_font_sizes(token_info)
    spacing = self._resolve_spacing(token_info)
    font_weights = self._resolve_font_weights(token_info)
    line_heights = self._resolve_line_heights(token_info)
    letter_spacings = self._resolve_letter_spacings(token_info)
    responsive, breakpoints = self._resolve_responsive(token_info)
    return DefaultTokens(
        colors=colors, fonts=fonts, font_sizes=font_sizes, spacing=spacing,
        font_weights=font_weights, line_heights=line_heights,
        letter_spacings=letter_spacings, responsive=responsive,
        responsive_breakpoints=breakpoints,
    )
```

**`_resolve_font_weights`**: Counter on heading/body lists → `{"heading": "700", "body": "400"}`.

**`_resolve_line_heights`**: Counter on heading/body lists → `{"heading": "40px", "body": "26px"}`.

**`_resolve_letter_spacings`**: Counter → `{"heading": "0.5px"}` (if any present).

**`_resolve_responsive`**: For each breakpoint in `token_info.responsive`, flatten to `{"mobile_heading_size": "24px", "mobile_body_size": "14px", "breakpoint": "600px"}`. Return `(flat_dict, tuple_of_breakpoints)`.

**Enrich `_resolve_colors`**: Add `link`, `heading_text`, `muted`, `accent` roles from `token_info.color_roles` using Counter most-common.

### Step 8: Create spacing bridge (`design_sync/spacing_bridge.py`)

**New file** that converts `DesignLayoutDescription` spacing/typography data into `DefaultTokens`-compatible format:

```python
"""Bridge Figma/Penpot layout spacing to DefaultTokens format."""
from __future__ import annotations
from collections import Counter
from app.design_sync.figma.layout_analyzer import DesignLayoutDescription, TextBlock

def figma_spacing_to_tokens(layout: DesignLayoutDescription) -> dict[str, str]:
    """Convert per-section spacing map → DefaultTokens.spacing format."""
    # Most common values become defaults
    ...  # Counter on padding_top/right/bottom/left across sections
    # Returns {"section_padding": "32px", "element_gap": "16px", ...}

def figma_typography_to_tokens(layout: DesignLayoutDescription) -> tuple[
    dict[str, str],  # font_sizes
    dict[str, str],  # fonts
    dict[str, str],  # font_weights
    dict[str, str],  # line_heights
]:
    """Extract typography tokens from layout TextBlocks (actual values)."""
    # Collect all TextBlocks across sections
    # Heading = largest font_size from is_heading=True blocks
    # Body = most common non-heading font_size
    # Use TextBlock.font_family, .font_weight, .line_height (now actual values)
```

### Step 9: Assembler typography/spacing replacement steps (`assembler.py`)

Add 5 new methods after `_apply_font_replacement` (line 259). All follow the same pattern as existing palette/font replacement: match `property: {default}` → replace with design system value.

**Step 3b: `_apply_font_size_replacement(html, defaults, tokens)`**
- For each role in `defaults.font_sizes`, find `font-size:\s*{default}` in inline `style=""` attributes, replace with `tokens.font_sizes[role]`.
- Use `re.sub(r'(font-size:\s*)' + re.escape(default), r'\1' + client, html)`.

**Step 3c: `_apply_line_height_replacement(html, defaults, tokens)`**
- Same pattern for `line-height:`.
- **Proportional safety**: if no explicit line-height in tokens, compute proportional from font-size ratio: `new_lh = default_lh * (new_fs / default_fs)`.

**Step 3d: `_apply_spacing_replacement(html, defaults, tokens)`**
- Match `padding-top:\s*{default}`, `padding-right:\s*{default}`, etc.
- Conservative: only replace exact matches of extracted default values.

**Step 3e: `_apply_font_weight_replacement(html, defaults, tokens)`**
- Match `font-weight:\s*{default}` → replace with design system value.

**Step 3f: `_apply_responsive_replacement(html, defaults, tokens)`**
- Find `<style>` blocks, locate `@media` at-rules.
- Inside `@media` blocks only, apply same font-size/line-height/spacing replacements using `defaults.responsive` → `tokens.responsive`.
- If `tokens.responsive` has overrides but HTML has no `@media`, inject a new `<style>` block.

In `assemble()`, add calls after existing step 3 (font replacement, ~line 70):
```python
if template.default_tokens and plan.design_tokens:
    html = self._apply_font_size_replacement(html, template.default_tokens, plan.design_tokens)
    html = self._apply_line_height_replacement(html, template.default_tokens, plan.design_tokens)
    html = self._apply_spacing_replacement(html, template.default_tokens, plan.design_tokens)
    html = self._apply_font_weight_replacement(html, template.default_tokens, plan.design_tokens)
    html = self._apply_responsive_replacement(html, template.default_tokens, plan.design_tokens)
```

Guard: skip each step if the relevant `defaults` field is empty or `tokens` field is missing.

### Step 10: Extend `DesignSystemMapper` (`design_system_mapper.py`)

**10a.** Add `resolve_font_weight_map`, `resolve_line_height_map` imports from `app.projects.design_system` (or compute inline if those helpers don't exist).

**10b.** In `map_tokens()`, add mapping for new fields:
```python
mapped_font_weights = dict(extracted.font_weights)
mapped_line_heights = dict(extracted.line_heights)
# ... same nearest-match pattern as existing font_sizes/spacing
```

**10c.** In `generate_diff()`, add diff rows for font-weight, line-height, letter-spacing.

**10d.** Return `DefaultTokens(...)` with all new fields populated.

### Step 11: Wire spacing bridge into import pipeline

In `app/design_sync/import_service.py` → `_build_design_context()` (line 344):
- After layout analysis, call `generate_spacing_map()` on the sections
- Include `spacing_map` in the design context dict so the Scaffolder can pass it to the assembler

In the design sync service flow that creates `GoldenTemplate` from Figma import:
- Call `figma_spacing_to_tokens()` and `figma_typography_to_tokens()` from the spacing bridge
- Merge results into the template's `DefaultTokens`

### Step 12: Tests

**12a. `test_layout_analyzer.py`** — add tests:
- `TextBlock` uses actual `font_size` from `DesignNode.font_size` (not height)
- `TextBlock` populates `font_family`, `font_weight`, `line_height`
- `EmailSection` captures padding and item_spacing from `DesignNode`
- `generate_spacing_map()` produces correct per-section dict
- Backward compat: `DesignNode` without new fields → `TextBlock.font_size` falls back to `height`

**12b. `test_extractors.py`** — add tests:
- HTML with `font-weight: 700` on headings → `font_weights: {"heading": "700"}`
- HTML with `line-height: 40px` → `line_heights: {"heading": "40px"}`
- HTML with `@media (max-width: 600px)` containing font-size overrides → `responsive` populated
- HTML with `<a style="color: #0066cc">` → `color_roles["link"]` populated

**12c. `test_assembler_typography.py`** (new) — test each replacement step:
- Font-size: template with `32px` heading + design system `28px` → output has `28px`
- Line-height: proportional computation when no explicit override
- Spacing: `padding-top: 32px` → replaced with `24px` from design tokens
- Font-weight: `700` → `600` replacement
- Responsive: `@media` block updated; new `@media` block injected when none exists
- Guard: steps skipped when `DefaultTokens` fields empty

**12d. `test_spacing_bridge.py`** (new):
- Layout with uniform padding → `spacing["section_padding"]` = most common value
- Layout with varying padding → per-section overrides captured
- Typography from TextBlocks → correct heading/body size detection

**12e. `test_design_system_mapper.py`** — extend:
- New fields (font_weights, line_heights) mapped through nearest-match
- `generate_diff()` includes new field types

## Security Checklist

- No new API endpoints — all changes are internal pipeline logic
- No user input reaches regex patterns — default values are hex/numeric from sanitized HTML
- Media query parsing is read-only string extraction — no CSS injection surface
- All string replacements are deterministic find-replace on already-sanitized HTML
- No `eval()`, `subprocess`, or dynamic execution anywhere

## Verification

- [ ] `make check` passes (lint, types, tests, security)
- [ ] `TextBlock.font_size` uses actual font size, not bounding box height
- [ ] Import email with `font: 700 32px/40px Inter` → tokens capture all 4 properties correctly (depends on 31.2 expansion)
- [ ] Figma import with auto-layout padding → `DesignNode` carries padding/itemSpacing → spacing map generated
- [ ] Assembler replaces font-size/line-height/font-weight/spacing with design system values
- [ ] Responsive `@media` rules updated; new `@media` injected when Figma mobile frame detected
- [ ] Color roles: `<a>` link colors → `link` role, not generic `text`
- [ ] Backward compat: existing templates without new fields work unchanged (all defaults empty)
