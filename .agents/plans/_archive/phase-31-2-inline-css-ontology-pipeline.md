# Plan: 31.2 — Inline CSS Compilation via Ontology Pipeline

## Context

After 31.1 adds Maizzle passthrough, pre-compiled email HTML skips `render()` but its inline `style=""` attributes (~90% of CSS) bypass ALL optimization. The sidecar's PostCSS plugin only processes `<style>` blocks. The Python compiler's `_process_css_block()` splits on `:` which breaks on `url(https://...)` and `rgb()` values. Shorthand properties (`font`, `padding`, `margin`) pass through unexpanded, degrading token extraction in 31.6.

Three layers fix this: **A** (sidecar inline optimization via PostCSS synthetic stylesheet), **B** (Python compiler upgrade to Lightning CSS parsing), **C** (design system token mapping for imports).

**Depends on:** 31.1 (passthrough detection + flag). Plan assumes `isPreCompiledEmail()` and `passthrough` flag already exist.

## Files to Create/Modify

| File | Action | What |
|------|--------|------|
| `services/maizzle-builder/index.js` | Modify | Add `optimizeInlineStyles()` with synthetic stylesheet approach |
| `services/maizzle-builder/postcss-email-optimize.js` | Modify | Add shorthand expansion visitor + media query extraction |
| `services/maizzle-builder/package.json` | Modify | Add `htmlparser2` dependency |
| `services/maizzle-builder/index.test.js` | Modify | Tests for inline optimization + shorthand expansion |
| `app/email_engine/css_compiler/compiler.py` | Modify | Replace `_process_css_block()` string splitting with Lightning CSS; add `_expand_shorthands()` |
| `app/email_engine/css_compiler/shorthand.py` | Create | Shorthand expansion utility using Lightning CSS |
| `app/email_engine/service.py` | Modify | Run Python compiler validation on passthrough HTML |
| `app/email_engine/tests/test_css_compiler.py` | Modify | Tests for Lightning CSS parsing + shorthand expansion |
| `app/templates/upload/design_system_mapper.py` | Create | `DesignSystemMapper` for token mapping against project design system |
| `app/templates/upload/font_optimizer.py` | Create | `EmailClientFontOptimizer` for email-client-specific font stacks |
| `app/templates/upload/service.py` | Modify | Integrate CSS compilation + design system mapping in upload flow |
| `app/templates/upload/schemas.py` | Modify | Add `CSSOptimizationPreview`, `TokenDiffPreview` to `AnalysisPreview` |
| `app/templates/upload/tests/test_design_system_mapper.py` | Create | Tests for token mapping |
| `app/templates/upload/tests/test_font_optimizer.py` | Create | Tests for font stack optimization |
| `data/email_client_fonts.yaml` | Create | Email client font support matrix |

## Implementation Steps

### Step 1: Sidecar — Add `htmlparser2` dependency

In `services/maizzle-builder/package.json`, add to `dependencies`:
```json
"htmlparser2": "^9.1.0"
```

Run `cd services/maizzle-builder && npm install`.

### Step 2: Sidecar — Shorthand expansion PostCSS visitor

In `services/maizzle-builder/postcss-email-optimize.js`, add a shorthand expansion phase **before** the Declaration handler. This is a custom visitor (no npm dependency needed — PostCSS can manipulate declarations directly).

Add function `expandShorthands(root)` that walks declarations matching known shorthands:

| Shorthand | Longhands |
|-----------|-----------|
| `font` | `font-style`, `font-variant`, `font-weight`, `font-size`, `line-height`, `font-family` |
| `padding` | `padding-top/right/bottom/left` |
| `margin` | `margin-top/right/bottom/left` |
| `border` | `border-width`, `border-style`, `border-color` |
| `background` | `background-color`, `background-image`, `background-repeat`, `background-position` |

For `font` parsing: use regex `^(italic|oblique)?\s*(small-caps)?\s*(\d+|bold|normal|lighter|bolder)?\s*(\d+[\w%]+)\s*(?:\/\s*(\d+[\w%]+))?\s+(.+)$`. For `padding`/`margin`: split by whitespace, expand 1→4, 2→4, 3→4, 4→4 values. For `border`: split into width/style/color tokens. For `background`: extract `url()` as image, hex/rgb as color, keywords as repeat/position.

Call `expandShorthands(root)` in the plugin's `Once(root)` hook, before `Declaration` processing. Track count in `result.emailOptimization.shorthand_expansions`.

### Step 3: Sidecar — Media query extraction

In `postcss-email-optimize.js`, add to the `AtRule` handler: when `atRule.name === 'media'`, instead of removing, extract breakpoint from params (regex: `max-width:\s*(\d+px)`), collect mobile overrides (font-size, padding, width changes, `display: none`), and add to `result.emailOptimization.responsive`. Preserve the `@media` rule in output (don't remove it).

### Step 4: Sidecar — `optimizeInlineStyles()` function

In `services/maizzle-builder/index.js`, add after `optimizeCss()`:

```javascript
const { Parser, DomHandler, DomUtils } = require('htmlparser2');
const { default: render } = require('dom-serializer');

async function optimizeInlineStyles(html, targetClients) {
  // 1. Parse HTML into DOM
  const handler = new DomHandler();
  const parser = new Parser(handler, { decodeEntities: false });
  parser.write(html);
  parser.end();
  const dom = handler.dom;

  // 2. Collect inline styles into synthetic stylesheet
  const elements = [];
  let index = 0;
  DomUtils.filter((node) => {
    if (node.attribs && node.attribs.style) {
      elements.push({ node, index });
      index++;
    }
    return false;
  }, dom);

  if (elements.length === 0) {
    return { html, inline_removed: [], inline_conversions: [], shorthand_expansions: 0 };
  }

  // 3. Build synthetic stylesheet
  const rules = elements.map(({ node, index: i }) =>
    `.__inline_${i} { ${node.attribs.style} }`
  ).join('\n');

  // 4. Run through PostCSS with ontology plugin
  const postcss = require('postcss');
  const emailOptimize = require('./postcss-email-optimize');
  const result = await postcss([emailOptimize({ targetClients })])
    .process(rules, { from: 'inline-styles.css' });

  // 5. Extract processed declarations back to elements
  result.root.walkRules((rule) => {
    const match = rule.selector.match(/__inline_(\d+)/);
    if (!match) return;
    const idx = parseInt(match[1], 10);
    const el = elements.find(e => e.index === idx);
    if (!el) return;
    const decls = [];
    rule.walkDecls((decl) => decls.push(`${decl.prop}: ${decl.value}`));
    el.node.attribs.style = decls.join('; ');
  });

  // 6. Serialize back to HTML
  const optimizedHtml = render(dom, { decodeEntities: false });
  const opt = result.emailOptimization || {};

  return {
    html: optimizedHtml,
    inline_removed: opt.removed || [],
    inline_conversions: opt.conversions || [],
    shorthand_expansions: opt.shorthand_expansions || 0,
  };
}
```

Wire into `/build` and `/preview` handlers: after `optimizeCss()`, if passthrough, call `optimizeInlineStyles()`. Merge inline optimization metadata into the response `optimization` object.

### Step 5: Python compiler — Replace `_process_css_block()` with Lightning CSS

In `app/email_engine/css_compiler/compiler.py`, replace `_process_css_block()` (lines 227–273):

**New approach:** Wrap CSS text in a dummy rule, parse with `lightningcss.process_stylesheet()`, then walk the declarations. This correctly handles colons in URLs, `calc()`, `rgb()`, complex values.

```python
def _process_css_block(self, css_text: str) -> tuple[str, list[str], list[CSSConversion], list[str]]:
    removed: list[str] = []
    conversions: list[CSSConversion] = []
    warnings: list[str] = []

    if self._css_variables:
        css_text = resolve_css_variables(css_text, self._css_variables)

    # Expand shorthands first
    css_text = expand_shorthands(css_text)

    # Parse with Lightning CSS via dummy rule wrapper
    wrapped = f".__dummy {{ {css_text} }}"
    try:
        parser_flags = lightningcss.calc_parser_flags(nesting=True)
        parsed = lightningcss.process_stylesheet(
            wrapped, filename="block.css", parser_flags=parser_flags, minify=False,
        )
        # Extract declarations from parsed output
        inner = re.sub(r"__dummy\s*\{(.*)\}", r"\1", parsed, flags=re.DOTALL).strip()
    except Exception:
        inner = css_text  # Fallback to original on parse error

    # Process each declaration through ontology
    lines: list[str] = []
    for line in inner.split(";"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        prop, val = line.split(":", 1)
        prop, val = prop.strip(), val.strip()

        if should_remove_property(prop, val, self._target_clients, self.registry):
            removed.append(f"{prop}: {val}")
            continue

        prop_conversions = get_conversions_for_property(prop, val, self._target_clients, self.registry)
        if prop_conversions:
            conversions.extend(prop_conversions)
            first = prop_conversions[0]
            replacement = f"{first.replacement_property}: {first.replacement_value}" if first.replacement_value else f"{first.replacement_property}: {val}"
            lines.append(replacement)
        else:
            lines.append(f"{prop}: {val}")

    return "; ".join(lines), removed, conversions, warnings
```

Key improvement: Lightning CSS correctly parses `background: url(https://example.com) no-repeat` without breaking on the colon. The `split(":", 1)` after Lightning CSS only sees individual longhands (not shorthands).

### Step 6: Python compiler — Shorthand expansion utility

Create `app/email_engine/css_compiler/shorthand.py`:

Pure-Python shorthand expansion for `font`, `padding`, `margin`, `border`, `background`. Uses regex parsing (no external dependency beyond Lightning CSS for validation). Same logic as sidecar Step 2 but in Python.

Key function: `expand_shorthands(css_text: str) -> str` — takes semicolon-delimited declarations, expands known shorthands to longhands, returns expanded declarations. Callable independently by token extractor (31.6).

Expansion rules match Step 2 table. `font` shorthand is the most complex — use a state machine that parses tokens left-to-right: optional style, optional variant, optional weight, required size, optional `/line-height`, required family (everything after size/line-height).

Export from `__init__.py`.

### Step 7: Python compiler — Integrate into `_process_inline_styles()`

In `compiler.py`, the existing `_process_inline_styles()` (lines 275–294) already delegates to `_process_css_block()`, which now uses Lightning CSS + shorthand expansion. No changes needed to `_process_inline_styles()` itself — the fix flows through automatically.

Update `_INLINE_STYLE_RE` to also match single-quoted styles:
```python
_INLINE_STYLE_RE = re.compile(r'''style\s*=\s*["']([^"']*)["']''', re.IGNORECASE)
```

### Step 8: Email engine service — Passthrough validation pass

In `app/email_engine/service.py`, modify `build()` (around line 73) and `preview()` (around line 133):

After `_call_builder()` returns with `passthrough=True`, run a lightweight Python compiler validation:
```python
if passthrough:
    compiler = EmailCSSCompiler(target_clients=target_clients)
    validation = compiler.optimize_css(compiled_html)
    compiled_html = validation.html
    # Merge validation metadata (removals/conversions Python caught that sidecar missed)
```

This acts as a defense-in-depth second pass — the sidecar handles the heavy lifting (Layer A), Python catches edge cases.

### Step 9: Design system token mapper

Create `app/templates/upload/design_system_mapper.py`:

```python
@dataclass(frozen=True)
class TokenDiff:
    property: str       # "font-family", "font-size", "spacing"
    role: str           # "heading", "body", "section"
    imported_value: str  # "Inter, sans-serif"
    design_system_value: str  # "Montserrat, sans-serif"
    action: str         # "will_replace", "compatible", "no_override"
```

`DesignSystemMapper` class:
- `__init__(design_system: DesignSystem | None)` — resolves all maps via `resolve_font_map()`, `resolve_font_size_map()`, `resolve_spacing_map()`, `resolve_color_map()`
- `map_tokens(extracted: DefaultTokens) -> DefaultTokens` — for each role in extracted tokens, find the design system equivalent:
  - **Fonts:** Compare extracted `heading`/`body` fonts against `resolve_font_map()`. If different, the *extracted* value stays in `DefaultTokens` (it's the "find" value for assembler's find-replace). The design system value goes into `DesignTokens` at build time.
  - **Font sizes:** For each extracted role, find nearest design system size by numeric proximity (`abs(int(extracted) - int(ds_size))`). Map to same role.
  - **Spacing:** Same nearest-match approach against `resolve_spacing_map()`.
  - **Colors:** Already handled by assembler's palette replacement (Phase 11.25). No change needed.
- `generate_diff(extracted: DefaultTokens, mapped: DefaultTokens) -> list[TokenDiff]`
  - Compare each role across all token categories
  - `"will_replace"` if values differ, `"compatible"` if same, `"no_override"` if design system lacks that role
- If `design_system is None`: return extracted tokens unchanged, empty diff list.

### Step 10: Email client font optimizer

Create `app/templates/upload/font_optimizer.py`:

`EmailClientFontOptimizer` class:
- Loads font support data from `data/email_client_fonts.yaml`
- `optimize_font_stack(font_family: str, target_clients: list[str]) -> str`:
  - Parse stack: `"Inter, sans-serif"` → `["Inter", "sans-serif"]`
  - For each target client, check if primary font is in supported list
  - If unsupported: ensure visually similar system font in fallback stack
  - Font similarity map (hardcoded): `Inter→Arial`, `Roboto→Arial`, `Montserrat→Verdana`, `Playfair Display→Georgia`, `Open Sans→Arial`, `Lato→Arial`, `Merriweather→Georgia`
  - Add `mso-font-alt` for Outlook targets
  - Return optimized stack string
- `inject_mso_font_alt(html: str, font_map: dict[str, str]) -> str`:
  - For elements with web fonts in inline styles, inject `mso-font-alt: {safe_font}` into the style attribute
  - Use `_INLINE_STYLE_RE` to find and augment style attributes

### Step 11: Font support data file

Create `data/email_client_fonts.yaml`:

```yaml
# Email client font support matrix
# "system" = only pre-installed system fonts
# "*" = all fonts (via <link> or @import)
# list = specific supported fonts
clients:
  outlook_2016_win: &outlook_desktop
    type: system
    fonts: [Arial, Helvetica, Georgia, "Times New Roman", Verdana, Tahoma,
            "Trebuchet MS", "Courier New", "Comic Sans MS", Impact, "Lucida Console"]
    requires_mso_font_alt: true
  outlook_2019_win: *outlook_desktop
  outlook_365_win: *outlook_desktop
  outlook_mac:
    type: all
    requires_mso_font_alt: false
  gmail_web:
    type: all
    requires_link_tag: true
  gmail_ios: { type: all }
  gmail_android: { type: all }
  apple_mail: { type: all }
  yahoo_web: { type: all }
  yahoo_mobile: { type: system }
  samsung_mail: { type: system_plus_google }
  thunderbird: { type: all }

fallback_map:
  Inter: [Arial, Helvetica, sans-serif]
  Roboto: [Arial, Helvetica, sans-serif]
  "Open Sans": [Arial, Helvetica, sans-serif]
  Lato: [Arial, Helvetica, sans-serif]
  Montserrat: [Verdana, Geneva, sans-serif]
  "Playfair Display": [Georgia, "Times New Roman", serif]
  Merriweather: [Georgia, "Times New Roman", serif]
  Poppins: [Arial, Helvetica, sans-serif]
  Raleway: [Verdana, Geneva, sans-serif]
  "Source Sans Pro": [Arial, Helvetica, sans-serif]
```

### Step 12: Upload service integration

Modify `app/templates/upload/service.py` — `upload_and_analyze()`:

After sanitization (line 78), before analysis (line 81):
1. Load project's target clients (from project if `project_id` provided, else default)
2. Run `EmailCSSCompiler(target_clients=target_clients).compile(sanitized)` → get `CompilationResult` with expanded shorthands
3. Use `compilation_result.html` as the input for analysis (replaces raw `sanitized`)
4. After token extraction (line 83):
   - Load `DesignSystem` if `project_id` provided
   - Run `DesignSystemMapper(design_system).map_tokens(tokens)` → `mapped_tokens`
   - Run `DesignSystemMapper.generate_diff(tokens, mapped_tokens)` → `token_diff`
5. Add `css_optimization` and `token_diff` to `analysis_dict`

### Step 13: Upload schemas

Modify `app/templates/upload/schemas.py`:

```python
class CSSConversionPreview(BaseModel):
    original: str
    replacement: str
    reason: str

class CSSOptimizationPreview(BaseModel):
    removed_properties: list[str] = Field(default_factory=list)
    conversions: list[CSSConversionPreview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    shorthand_expansions: int = 0
    responsive_breakpoints: list[str] = Field(default_factory=list)

class TokenDiffPreview(BaseModel):
    property: str
    role: str
    imported_value: str
    design_system_value: str
    action: str  # "will_replace", "compatible", "no_override"
```

Add to `AnalysisPreview`:
```python
css_optimization: CSSOptimizationPreview | None = None
token_diff: list[TokenDiffPreview] = Field(default_factory=list)
```

### Step 14: Tests

**Sidecar tests** (`services/maizzle-builder/index.test.js`):
- Shorthand expansion: `font: 700 32px/40px Inter, sans-serif` → 4 longhands
- Shorthand expansion: `padding: 16px 32px` → 4 longhands
- Inline style optimization: element with `display: flex` in `style=""` → removed for Outlook targets
- Colon in URL: `background: url(https://example.com)` → not broken
- Media query extraction: `@media (max-width: 600px)` → breakpoint extracted, rule preserved
- Passthrough path runs inline optimization

**Python compiler tests** (`app/email_engine/tests/test_css_compiler.py`):
- Lightning CSS parsing: `url(https://...)` value not split on colon
- Shorthand expansion: `font`, `padding`, `margin`, `border`, `background`
- Single-quoted styles now captured by regex
- Integration: load golden template, compile, verify no regressions vs current behavior

**Design system mapper tests** (`app/templates/upload/tests/test_design_system_mapper.py`):
- Font mapping: extracted `Inter` + DS `Montserrat` → diff shows `will_replace`
- Size mapping: extracted `32px` + DS sizes `{heading: "28px"}` → nearest match
- No design system: tokens unchanged, empty diff
- Compatible values: extracted matches DS → `compatible` action

**Font optimizer tests** (`app/templates/upload/tests/test_font_optimizer.py`):
- Outlook target: `Inter, sans-serif` → `Inter, Arial, Helvetica, sans-serif`
- Apple Mail target: no change (all fonts supported)
- MSO font-alt injection for Outlook targets
- Unknown font: kept as-is, warning logged

Use real golden templates from `app/ai/templates/library/*.html` for integration/regression tests. Use minimal synthetic HTML only for narrow unit tests.

## Security Checklist

| Check | Status |
|-------|--------|
| No new HTTP endpoints | N/A — no new routes |
| PostCSS + Lightning CSS are deterministic parsers | Safe — no eval/code execution from CSS |
| `htmlparser2` is well-audited (Cheerio dependency) | Safe — streaming parser, no eval |
| Ontology data is static JSON | Safe — no user input reaches it |
| Output still passes through `sanitize_html_xss()` | Preserved — stage 7 unchanged |
| Font support YAML is static data | Safe — loaded once at startup |
| No new input vectors | Same HTML from upload/build pipeline |

## Verification

- [ ] `cd services/maizzle-builder && npm test` passes
- [ ] `make test` passes (all backend unit tests)
- [ ] `make types` passes (mypy + pyright)
- [ ] `make lint` passes (ruff)
- [ ] Import email with `font: 700 32px/40px Inter, sans-serif` → 4 expanded properties
- [ ] Import email with `url(https://...)` → colon doesn't break parser
- [ ] Import email with `display: flex` inline → removed for Outlook targets
- [ ] Import into project with design system → token diff shows mapping
- [ ] Import into project without design system → tokens stored as-is
- [ ] Passthrough emails get inline CSS optimization
- [ ] Non-passthrough emails: no regression (existing behavior preserved)
- [ ] `make check` passes (full pipeline)
