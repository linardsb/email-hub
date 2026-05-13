# Plan: 31.3 — Preserve Wrapper Table Metadata in Section Analyzer

## Context

Email HTML universally uses an outer wrapper table for centering: `<table width="600" align="center">` wrapping inner section tables. The `TemplateAnalyzer._detect_sections()` method (analyzer.py:162-167) correctly identifies inner tables as sections when it finds the single-wrapper pattern, but discards the wrapper entirely. Without the wrapper metadata (width, align, bgcolor, cellpadding, etc.), reassembled HTML lacks centering — emails render full-width, left-aligned. This is the primary cause of "template not centered" after import.

The fix preserves the wrapper as structured metadata on `AnalysisResult` so downstream assembly (future 31.4) can reconstruct the centering context.

## Files to Modify

- `app/templates/upload/analyzer.py` — Add `WrapperInfo` dataclass, extract wrapper metadata in `_detect_sections()`, add to `AnalysisResult`
- `app/templates/upload/schemas.py` — Add `WrapperPreview` Pydantic model, add to `AnalysisPreview`
- `app/templates/upload/service.py` — Serialize/deserialize `WrapperInfo` in `_serialize_analysis()` and `_build_preview()`
- `app/templates/upload/tests/test_analyzer.py` — Add `TestWrapperPreservation` test class

## Implementation Steps

### Step 1: Add `WrapperInfo` dataclass to `analyzer.py`

Add after the `ComplexityInfo` class (line 75, before `AnalysisResult`):

```python
@dataclass
class WrapperInfo:
    """Preserved metadata from the outer centering wrapper table."""

    tag: str  # "table" or "div"
    width: str | None = None
    align: str | None = None
    style: str | None = None
    bgcolor: str | None = None
    cellpadding: str | None = None
    cellspacing: str | None = None
    border: str | None = None
    role: str | None = None
    inner_td_style: str | None = None
    mso_wrapper: str | None = None
```

### Step 2: Add `wrapper` field to `AnalysisResult`

Modify the `AnalysisResult` dataclass (line 78) to add:

```python
@dataclass
class AnalysisResult:
    """Complete analysis output."""

    sections: list[SectionInfo]
    slots: list[SlotInfo]
    tokens: TokenInfo
    esp_platform: str | None
    complexity: ComplexityInfo
    layout_type: str
    wrapper: WrapperInfo | None = None
```

### Step 3: Add MSO wrapper regex constant

Add after `_DIVIDER_KEYWORDS` (line 109):

```python
_MSO_WRAPPER_RE = re.compile(
    r"(<!--\[if\s+mso\]>.*?<table[^>]*>.*?<tr>.*?<td[^>]*>.*?<!\[endif\]-->)",
    re.DOTALL | re.IGNORECASE,
)
```

### Step 4: Modify `TemplateAnalyzer.analyze()` to accept raw HTML and pass wrapper through

The `analyze()` method (line 115) needs access to the raw HTML string for MSO comment extraction (lxml strips HTML comments). It already receives `sanitized_html` as a string, so pass it to `_detect_sections`.

Change:
```python
def analyze(self, sanitized_html: str) -> AnalysisResult:
    """Run full analysis pipeline."""
    tree = lxml_html.fromstring(sanitized_html)
    sections = self._detect_sections(tree)
```

To:
```python
def analyze(self, sanitized_html: str) -> AnalysisResult:
    """Run full analysis pipeline."""
    tree = lxml_html.fromstring(sanitized_html)
    sections, wrapper_info = self._detect_sections(tree, sanitized_html)
```

And update the return statement (line 132) to include `wrapper=wrapper_info`.

### Step 5: Modify `_detect_sections()` to extract and return wrapper metadata

Change the signature:
```python
def _detect_sections(self, tree: HtmlElement, raw_html: str) -> tuple[list[SectionInfo], WrapperInfo | None]:
```

In the single-wrapper branch (lines 162-167), before replacing `candidates`, extract the wrapper:

```python
# If we found a single wrapper table, look inside it for nested tables as sections
if len(candidates) == 1 and candidates[0].tag == "table":
    wrapper = candidates[0]
    inner_tables = wrapper.findall(".//tr/td/table")
    if len(inner_tables) >= 2:
        # Extract wrapper metadata before discarding
        wrapper_info = self._extract_wrapper_info(wrapper, raw_html)
        candidates = inner_tables
```

Initialize `wrapper_info: WrapperInfo | None = None` at the top of the method. Return `(sections, wrapper_info)` instead of just `sections`.

Also update the fallback at the end (line 183) — the return should be `(sections, wrapper_info)`.

### Step 6: Add `_extract_wrapper_info()` method

Add as a new method on `TemplateAnalyzer`, after `_detect_sections()`:

```python
def _extract_wrapper_info(self, wrapper: HtmlElement, raw_html: str) -> WrapperInfo:
    """Extract centering metadata from wrapper table before discarding it."""
    # Get attributes from the wrapper element
    tag = wrapper.tag

    # Find the <td> child that contains the inner tables
    inner_td = wrapper.find(".//tr/td")
    inner_td_style = inner_td.get("style") if inner_td is not None else None

    # Search for MSO conditional wrapper in raw HTML (lxml strips comments)
    mso_match = _MSO_WRAPPER_RE.search(raw_html)
    mso_wrapper = mso_match.group(1) if mso_match else None

    return WrapperInfo(
        tag=tag,
        width=wrapper.get("width"),
        align=wrapper.get("align"),
        style=wrapper.get("style"),
        bgcolor=wrapper.get("bgcolor"),
        cellpadding=wrapper.get("cellpadding"),
        cellspacing=wrapper.get("cellspacing"),
        border=wrapper.get("border"),
        role=wrapper.get("role"),
        inner_td_style=inner_td_style,
        mso_wrapper=mso_wrapper,
    )
```

### Step 7: Add `WrapperPreview` to `schemas.py`

Add before `AnalysisPreview` (line 48):

```python
class WrapperPreview(BaseModel):
    """Preserved metadata from the outer centering wrapper table."""

    tag: str
    width: str | None = None
    align: str | None = None
    style: str | None = None
    bgcolor: str | None = None
    cellpadding: str | None = None
    cellspacing: str | None = None
    border: str | None = None
    role: str | None = None
    inner_td_style: str | None = None
    mso_wrapper: str | None = None
```

Add field to `AnalysisPreview`:

```python
wrapper: WrapperPreview | None = None
```

### Step 8: Update `_serialize_analysis()` in `service.py`

Add wrapper serialization to the returned dict (after the `"suggested_description"` key, ~line 326):

```python
"wrapper": (
    {
        "tag": analysis.wrapper.tag,
        "width": analysis.wrapper.width,
        "align": analysis.wrapper.align,
        "style": analysis.wrapper.style,
        "bgcolor": analysis.wrapper.bgcolor,
        "cellpadding": analysis.wrapper.cellpadding,
        "cellspacing": analysis.wrapper.cellspacing,
        "border": analysis.wrapper.border,
        "role": analysis.wrapper.role,
        "inner_td_style": analysis.wrapper.inner_td_style,
        "mso_wrapper": analysis.wrapper.mso_wrapper,
    }
    if analysis.wrapper
    else None
),
```

Also add `WrapperPreview` to the schema import block (line 27-36).

### Step 9: Update `_build_preview()` in `service.py`

Add wrapper deserialization (after `token_diff`, ~line 333):

```python
wrapper_data = data.get("wrapper")
wrapper = WrapperPreview(**wrapper_data) if wrapper_data else None
```

Pass `wrapper=wrapper` into the `AnalysisPreview(...)` constructor.

### Step 10: Add tests in `test_analyzer.py`

Add a new test class and HTML fixture:

```python
WRAPPER_WITH_ATTRS_HTML = """
<html>
<body>
<table width="600" align="center" bgcolor="#ffffff" cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width: 600px;">
  <tr><td style="max-width: 600px; margin: 0 auto;">
    <table width="600">
      <tr><td><img src="logo.png" width="150" height="50"></td></tr>
    </table>
    <table width="600">
      <tr><td>
        <h1 style="font-size: 24px;">Hello World</h1>
        <p style="font-size: 14px;">Some body text content here for testing.</p>
      </td></tr>
    </table>
    <table width="600">
      <tr><td style="font-size: 12px;">
        <p>Footer with unsubscribe link. &copy; 2026 Company</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""

NO_WRAPPER_HTML = """
<html>
<body>
<table width="600">
  <tr><td><img src="logo.png" width="150" height="50"></td></tr>
</table>
<table width="600">
  <tr><td>
    <h1 style="font-size: 24px;">Hello World</h1>
  </td></tr>
</table>
</body>
</html>
"""

MSO_WRAPPER_HTML = """
<html>
<body>
<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table width="600" align="center" cellpadding="0" cellspacing="0" border="0">
  <tr><td>
    <table width="600">
      <tr><td><img src="logo.png" width="150" height="50"></td></tr>
    </table>
    <table width="600">
      <tr><td>
        <h1 style="font-size: 24px;">Content heading here</h1>
        <p style="font-size: 14px;">Some body text content here for testing.</p>
      </td></tr>
    </table>
  </td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</body>
</html>
"""


class TestWrapperPreservation:
    def test_wrapper_attrs_preserved(self, analyzer: TemplateAnalyzer) -> None:
        result = analyzer.analyze(WRAPPER_WITH_ATTRS_HTML)
        assert result.wrapper is not None
        assert result.wrapper.tag == "table"
        assert result.wrapper.width == "600"
        assert result.wrapper.align == "center"
        assert result.wrapper.bgcolor == "#ffffff"
        assert result.wrapper.cellpadding == "0"
        assert result.wrapper.cellspacing == "0"
        assert result.wrapper.border == "0"
        assert result.wrapper.role == "presentation"

    def test_wrapper_inner_td_style_preserved(self, analyzer: TemplateAnalyzer) -> None:
        result = analyzer.analyze(WRAPPER_WITH_ATTRS_HTML)
        assert result.wrapper is not None
        assert result.wrapper.inner_td_style is not None
        assert "max-width" in result.wrapper.inner_td_style

    def test_no_wrapper_when_multiple_top_level_tables(self, analyzer: TemplateAnalyzer) -> None:
        result = analyzer.analyze(NO_WRAPPER_HTML)
        assert result.wrapper is None

    def test_mso_wrapper_captured(self, analyzer: TemplateAnalyzer) -> None:
        result = analyzer.analyze(MSO_WRAPPER_HTML)
        assert result.wrapper is not None
        assert result.wrapper.mso_wrapper is not None
        assert "<!--[if mso]>" in result.wrapper.mso_wrapper
        assert "width=\"600\"" in result.wrapper.mso_wrapper

    def test_wrapper_style_attr_preserved(self, analyzer: TemplateAnalyzer) -> None:
        result = analyzer.analyze(WRAPPER_WITH_ATTRS_HTML)
        assert result.wrapper is not None
        assert result.wrapper.style is not None
        assert "max-width" in result.wrapper.style

    def test_sections_still_detected_with_wrapper(self, analyzer: TemplateAnalyzer) -> None:
        """Wrapper extraction must not break section detection."""
        result = analyzer.analyze(WRAPPER_WITH_ATTRS_HTML)
        assert len(result.sections) >= 2
```

## Security Checklist

**No new endpoints** are added by this change. This is a read-only metadata extraction from already-sanitized HTML.

- **Auth/RBAC:** N/A — no new routes
- **Rate limiting:** N/A — no new routes
- **Input validation:** The `WrapperInfo` fields are extracted from `sanitized_html` which has already been passed through `sanitize_html_xss(profile="import_annotator")`. The `mso_wrapper` field is extracted from the same sanitized HTML via regex. No new user input paths.
- **SQL injection:** N/A — no new queries
- **XSS:** `WrapperPreview` is a read-only Pydantic model returned as JSON. The `mso_wrapper` field contains raw MSO conditional HTML from the sanitized source — it's served as a JSON string value, not rendered.
- **Error leakage:** N/A — no new error paths
- **Secrets:** N/A — no secrets involved

## Verification

- [ ] `make check` passes (includes lint, types, tests, frontend, security-check)
- [ ] Upload email with `<table width="600" align="center">` wrapper → `wrapper.width="600"`, `wrapper.align="center"`
- [ ] Upload email with `<td style="max-width: 600px; margin: 0 auto;">` → `wrapper.inner_td_style` captured
- [ ] Upload email with MSO conditional wrapper → `wrapper.mso_wrapper` contains the `<!--[if mso]>` block
- [ ] Upload email with multiple top-level tables (no wrapper) → `wrapper` is null
- [ ] Existing tests in `test_analyzer.py` still pass (no regressions)
