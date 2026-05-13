# Plan: Phase 29.2 — Penpot CSS-to-Email Converter Integration

## Context

The Penpot converter (`app/design_sync/penpot/converter.py`) has working functions — `convert_colors_to_palette()`, `convert_typography()`, `node_to_email_html()`, `_group_into_rows()` — but `DesignImportService.run_conversion()` never calls them. All providers go through the generic brief → Scaffolder path. This subtask wires the Penpot converter as an optional pre-processing step that produces initial HTML for the Scaffolder to enhance.

**Key discovery:** `ScaffolderRequest` does NOT have `initial_html`. But `BlueprintRunRequest` does (`app/ai/blueprints/schemas.py:13`), and `BlueprintEngine.run()` accepts it (`engine.py:151`). The Scaffolder wraps blueprints via `ScaffolderService.process() → BlueprintService.run()`. We need to add `initial_html` to `ScaffolderRequest` and pipe it through.

## Files to Create

| File | Purpose |
|------|---------|
| `app/design_sync/penpot/converter_service.py` | `PenpotConverterService` — orchestrates converter functions into full email skeleton |
| `app/design_sync/penpot/tests/test_converter_integration.py` | Integration tests for the converter service + import pipeline integration |

## Files to Modify

| File | Change |
|------|--------|
| `app/core/config.py` | Add `penpot_converter_enabled: bool = False` to `DesignSyncConfig` |
| `app/design_sync/penpot/converter.py` | Enhance `node_to_email_html()` — INSTANCE handling, fills/bg extraction, padding, border |
| `app/design_sync/import_service.py` | Inject Penpot converter step before Scaffolder call |
| `app/ai/agents/scaffolder/schemas.py` | Add `initial_html: str = ""` field to `ScaffolderRequest` |
| `app/ai/agents/scaffolder/service.py` | Pipe `initial_html` through to `BlueprintRunRequest` |
| `app/design_sync/tests/test_penpot_converter.py` | Extend with INSTANCE/COMPONENT, fills, padding tests |

## Implementation Steps

### Step 1: Config flag

In `app/core/config.py`, class `DesignSyncConfig` (line 321), add after `penpot_request_timeout`:

```python
penpot_converter_enabled: bool = False  # DESIGN_SYNC__PENPOT_CONVERTER_ENABLED
```

No migration needed — config only.

### Step 2: Enhance `node_to_email_html()` in `converter.py`

Current handling: TEXT, IMAGE, FRAME/GROUP/COMPONENT, VECTOR/other. Missing: INSTANCE, fills/bg, padding, border.

**2a. Add INSTANCE to the FRAME/GROUP/COMPONENT branch** (line 132-136):

Add `DesignNodeType.INSTANCE` to the tuple check. INSTANCE nodes are component usages — structurally identical to frames.

**2b. Add fill/background extraction helper:**

```python
def _extract_fill_style(node: DesignNode) -> str:
    """Extract background color from node fills (if available via structure_json)."""
    # DesignNode is frozen and doesn't carry fills — this data comes from
    # the raw Penpot object. The converter_service passes it via a lookup dict.
    return ""
```

Actually, `DesignNode` (protocol.py:62-74) is a frozen dataclass with only: id, name, type, children, width, height, x, y, text_content. It does NOT carry fills, padding, font info, or layout properties. These are lost during `PenpotDesignSyncService._obj_to_node()` normalization.

**Revised approach:** Rather than modifying the frozen protocol `DesignNode` (which affects all providers), the `PenpotConverterService` will work with both the `DesignNode` tree AND a supplementary properties dict extracted from the raw Penpot file data. This keeps the protocol clean.

**2b-revised. Add `_NodeProps` dataclass and extraction:**

In `converter.py`, add:

```python
@dataclass(frozen=True)
class _NodeProps:
    """Supplementary visual properties not carried by DesignNode."""
    bg_color: str | None = None
    font_family: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    padding_top: float = 0
    padding_right: float = 0
    padding_bottom: float = 0
    padding_left: float = 0
    border_color: str | None = None
    border_width: float = 0
    layout_direction: str | None = None  # "row" | "column" | None
```

**2c. Update `node_to_email_html()` signature:**

```python
def node_to_email_html(
    node: DesignNode,
    *,
    indent: int = 0,
    props_map: dict[str, _NodeProps] | None = None,
) -> str:
```

Add optional `props_map` (node.id → `_NodeProps`). When present, apply:

- **TEXT nodes:** Use `props.font_family` and `props.font_size` for inline style instead of hardcoded Arial. Fall back to current behaviour when no props.
- **FRAME/GROUP/COMPONENT/INSTANCE:** Add `bgcolor` attr from `props.bg_color`. Add `style` with padding from props. Pass `props_map` to recursive calls.
- **Add INSTANCE** to the frame branch tuple.

Existing tests continue to work (they pass no `props_map`, so behaviour unchanged).

**2d. Improve `_group_into_rows()` — overlapping elements:**

Add z-ordering for overlapping elements (same y-band). When multiple nodes overlap significantly (>50% area overlap), sort by z-index (their order in the children list, which Penpot stores in paint order). Current implementation already handles this implicitly since `sorted_nodes` preserves insertion order for same-y nodes.

Add hero image detection: if a single IMAGE node spans ≥80% of its parent width, it gets its own row regardless of y-tolerance.

### Step 3: Create `PenpotConverterService` (`converter_service.py`)

```python
"""Service layer for Penpot design-to-email HTML conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.design_sync.penpot.converter import (
    _NodeProps,
    convert_colors_to_palette,
    convert_typography,
    node_to_email_html,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedTokens,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class PenpotConversionResult:
    """Result of converting a Penpot design tree to email HTML."""
    html: str
    sections_count: int
    warnings: list[str]


class PenpotConverterService:
    """Orchestrates Penpot design tree → email HTML conversion."""

    def convert(
        self,
        structure: DesignFileStructure,
        tokens: ExtractedTokens,
        *,
        raw_file_data: dict[str, Any] | None = None,
        selected_nodes: list[str] | None = None,
    ) -> PenpotConversionResult:
        ...
```

**Core logic of `convert()`:**

1. Walk `structure.pages` → collect top-level frames (FRAME/COMPONENT nodes at page level)
2. Filter by `selected_nodes` if provided
3. Build `props_map` from `raw_file_data` if available (calls `_build_props_map()`)
4. For each frame: call `node_to_email_html(frame, props_map=props_map)` → section HTML
5. Assemble into email skeleton:

```python
EMAIL_SKELETON = '''<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<!--[if mso]>
<noscript><xml>
<o:OfficeDocumentSettings>
<o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml></noscript>
<![endif]-->
{style_block}
</head>
<body style="margin:0;padding:0;word-spacing:normal;background-color:{bg_color};">
<div role="article" aria-roledescription="email" lang="en" style="text-size-adjust:100%;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
<!--[if mso]>
<table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td>
<![endif]-->
<table role="presentation" style="margin:0 auto;max-width:600px;width:100%;" cellpadding="0" cellspacing="0" border="0">
{sections}
</table>
<!--[if mso]>
</td></tr></table>
<![endif]-->
</div>
</body>
</html>'''
```

6. Apply token-derived values:
   - `bg_color` from `convert_colors_to_palette(tokens.colors).background`
   - `style_block` with `<style>` containing body font from `convert_typography(tokens.typography).body_font`
7. Track warnings (SVG nodes stripped, unsupported vector types, etc.)
8. Return `PenpotConversionResult(html=skeleton, sections_count=len(frames), warnings=warnings)`

**`_build_props_map()`** — extracts `_NodeProps` from raw Penpot file data:

```python
def _build_props_map(self, file_data: dict[str, Any]) -> dict[str, _NodeProps]:
    """Extract visual properties from raw Penpot objects."""
    props: dict[str, _NodeProps] = {}
    pages_index = file_data.get("data", {}).get("pages-index", {})
    for _page_id, page_data in pages_index.items():
        for obj_id, obj in page_data.get("objects", {}).items():
            bg = self._extract_bg(obj)
            font = obj.get("font-family")
            size = obj.get("font-size")
            weight = str(obj.get("font-weight", "")) or None
            padding = obj.get("layout-padding", {})
            props[str(obj_id)] = _NodeProps(
                bg_color=bg,
                font_family=font,
                font_size=float(size) if size else None,
                font_weight=weight,
                padding_top=float(padding.get("p1", 0)),
                padding_right=float(padding.get("p2", 0)),
                padding_bottom=float(padding.get("p3", 0)),
                padding_left=float(padding.get("p4", 0)),
                layout_direction=obj.get("layout-flex-dir"),
            )
    return props
```

**`_extract_bg()`** — first solid fill color from Penpot fills array:

```python
@staticmethod
def _extract_bg(obj: dict[str, Any]) -> str | None:
    fills = obj.get("fills", [])
    for fill in fills:
        if fill.get("fill-color"):
            return str(fill["fill-color"])
    return None
```

### Step 4: Add `initial_html` to `ScaffolderRequest`

In `app/ai/agents/scaffolder/schemas.py`, add to `ScaffolderRequest` (after `design_context`):

```python
initial_html: str = Field(
    default="",
    description="Pre-generated HTML skeleton for the Scaffolder to enhance (e.g. from Penpot converter)",
)
```

### Step 5: Pipe `initial_html` through Scaffolder → Blueprint

In `app/ai/agents/scaffolder/service.py`, find where `ScaffolderService.process()` (inherited from `BaseAgentService`) or `generate()` creates the `BlueprintRunRequest`. The Scaffolder uses `BlueprintService.run()`.

Search for how `ScaffolderRequest` fields map to `BlueprintRunRequest`:

The `ScaffolderService` inherits from `BaseAgentService`. The `process()` method in the base creates a `BlueprintRunRequest`. We need to check the base to understand the mapping.

**Key chain:** `ScaffolderService.generate()` → `self.process(request)` → base creates `BlueprintRunRequest(brief=..., initial_html=...)` → `BlueprintService.run()` → `BlueprintEngine.run(brief, initial_html)`.

In `app/ai/agents/scaffolder/service.py`, find where `ScaffolderRequest` maps to blueprint request. The `_call_scaffolder` in import_service.py creates `ScaffolderRequest` and calls `service.generate()`. Inside `generate()` → `process()`, the request fields are read.

Look for the `_build_blueprint_request` or similar method in the scaffolder service. The scaffolder pipeline (`ScaffolderPipeline`) receives the brief and config.

**Actually:** Looking at `import_service.py:233-240`, the `_call_scaffolder` creates a `ScaffolderRequest(brief=brief, design_context=design_context)` and calls `service.generate()`. The scaffolder service's `generate()` just calls `self.process(request)`.

The `process()` in the base agent service builds a prompt and calls the LLM. But for "structured" mode, it goes through the blueprint engine which accepts `initial_html`.

We need to trace exactly how `initial_html` gets from `ScaffolderRequest` to the blueprint. Since `BlueprintRunRequest.initial_html` already exists (schemas.py:13), and `BlueprintService.run()` uses `request.initial_html` (service.py:385), and the scaffolder creates a `BlueprintRunRequest` somewhere — we just need to pass it through.

**Implementation:** In `ScaffolderService`, find where it creates `BlueprintRunRequest` and add `initial_html=request.initial_html`.

### Step 6: Modify `import_service.py` — inject converter step

In `DesignImportService.run_conversion()`, between step 5 (build design context) and step 6 (call Scaffolder):

```python
# 5.5 Penpot converter pre-processing (optional)
initial_html = ""
if (
    conn.provider == "penpot"
    and get_settings().design_sync.penpot_converter_enabled
):
    try:
        from app.design_sync.penpot.converter_service import PenpotConverterService

        converter = PenpotConverterService()
        structure = DesignFileStructure(
            file_name=layout_response.file_name,
            pages=self._layout_to_design_nodes(layout_response),
        )
        conversion = converter.convert(
            structure,
            self._tokens_to_protocol(tokens) if tokens else ExtractedTokens(),
            raw_file_data=design_import.structure_json,
            selected_nodes=design_import.selected_node_ids or None,
        )
        initial_html = conversion.html
        logger.info(
            "design_sync.penpot_converter_completed",
            import_id=import_id,
            sections=conversion.sections_count,
            warnings_count=len(conversion.warnings),
        )
    except Exception:
        logger.warning(
            "design_sync.penpot_converter_failed",
            import_id=import_id,
            exc_info=True,
        )
        # Fall back to brief-only path
```

Then modify the `_call_scaffolder` call to pass `initial_html`:

```python
scaffolder_response = await self._call_scaffolder(
    brief=design_import.generated_brief or "",
    design_context=design_context,
    run_qa=run_qa,
    output_mode=output_mode,
    initial_html=initial_html,
)
```

Update `_call_scaffolder` signature to accept `initial_html: str = ""` and pass it to `ScaffolderRequest`.

**Helper methods needed** in `DesignImportService`:

- `_layout_to_design_nodes(layout: LayoutAnalysisResponse) -> list[DesignNode]` — reconstruct `DesignNode` tree from layout analysis response sections. Each `AnalyzedSectionResponse` becomes a FRAME node with child TEXT/IMAGE nodes.
- `_tokens_to_protocol(tokens: DesignTokensResponse) -> ExtractedTokens` — convert response schema back to protocol dataclass.

These are thin adapters (~15 lines each).

### Step 7: Update template description for Penpot imports

In `_create_template()` (import_service.py:262), change hardcoded "Imported from Figma design" to use the provider:

```python
description=f"Imported from {conn.provider.title()} design"
```

This requires passing `provider_name` through. Add it as a parameter to `_create_template()`.

### Step 8: Tests

**8a. Extend `test_penpot_converter.py`** (currently 10 tests → add 6):

| Test | What |
|------|------|
| `test_instance_node` | INSTANCE type renders as table (same as FRAME) |
| `test_component_node_with_children` | COMPONENT with nested nodes renders recursively |
| `test_props_map_font_override` | TEXT node with `props_map` uses custom font |
| `test_props_map_bg_color` | FRAME with `props_map` bg_color gets bgcolor attr |
| `test_props_map_padding` | FRAME with padding props gets padding style |
| `test_hero_image_own_row` | Wide IMAGE (≥80% parent width) gets its own row |

All tests use `DesignNode` fixtures (same pattern as existing tests).

**8b. Create `test_converter_integration.py`** (15 tests):

| Test | What |
|------|------|
| `test_simple_frame_to_html` | Single frame → valid email HTML with table layout |
| `test_text_node_inline_styles` | Text node → `<td>` with inline font from tokens |
| `test_image_node_attributes` | Image → `<img>` with width/height |
| `test_grouped_elements_multi_column` | 3 nodes at same y → multi-cell `<tr>` |
| `test_auto_layout_column_widths` | Penpot flex-dir column → stacked rows |
| `test_tokens_applied_colors` | Palette colors appear in inline styles |
| `test_tokens_applied_typography` | Font family from tokens in style block |
| `test_mso_conditionals_present` | Output contains `<!--[if mso]>` wrappers |
| `test_email_skeleton_structure` | DOCTYPE, html, head, body, wrapper table present |
| `test_converter_disabled_no_initial_html` | Config off → `_call_scaffolder` gets `initial_html=""` |
| `test_converter_enabled_produces_html` | Config on + Penpot → `initial_html` is non-empty |
| `test_figma_provider_skips_converter` | Figma connection → converter not called |
| `test_converter_failure_falls_back` | Converter raises → logged warning, brief-only path |
| `test_selected_nodes_filter` | Only selected frames converted |
| `test_svg_stripped_with_warning` | VECTOR node → stripped with warning in result |

For import pipeline integration tests (last 5): mock `DesignSyncService` and `ScaffolderService` (same pattern as `test_import_service.py`). Assert `ScaffolderRequest.initial_html` contains table HTML when converter enabled.

## Security Checklist

No new endpoints — this is internal pipeline enhancement only.

- **XSS:** Converter output is string concatenation from design node data. Node names and text content could contain malicious strings. The converter output goes through the Scaffolder (which sanitizes) and the existing `sanitize_html_xss()` in post-processing. Add explicit sanitization of `text_content` in `node_to_email_html()`: HTML-escape text content via `html.escape()`.
- **Input validation:** `raw_file_data` is the stored `structure_json` from DB — already validated at import creation time.
- **No external calls:** All conversion is local string manipulation.
- **Feature flag:** Off by default (`penpot_converter_enabled: bool = False`).

## Verification

- [ ] `make test` passes — existing 10 converter tests still pass
- [ ] `make types` passes — all new code has complete type annotations
- [ ] `make lint` passes
- [ ] New tests: 6 in `test_penpot_converter.py`, 15 in `test_converter_integration.py`
- [ ] Converter off → import pipeline unchanged (brief-only)
- [ ] Converter on + Penpot → initial HTML piped to Scaffolder
- [ ] Converter on + Figma → converter skipped
- [ ] Converter failure → graceful fallback with warning log
- [ ] Text content HTML-escaped in converter output
