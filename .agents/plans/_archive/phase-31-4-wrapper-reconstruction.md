# Plan: 31.4 — Wrapper Reconstruction on Template Assembly

## Context

Phase 31.3 captures wrapper metadata (`WrapperInfo`) during import analysis — width, align, bgcolor, MSO conditional block, etc. This metadata is serialized into `analysis_json` and surfaced as `WrapperPreview` in the API response. However, nothing currently *uses* it during template assembly.

The problem: when the analyzer finds a single wrapper table containing ≥2 inner section tables, it "unwraps" by replacing `candidates` with the inner tables (analyzer.py:190-196). The `sanitized_html` stored on `TemplateUpload` still contains the wrapper (the analyzer is metadata-only, it doesn't modify HTML). So when `TemplateBuilder.build()` stores the HTML into `GoldenTemplate`, the wrapper is present. The real gap is:

1. **No wrapper metadata on `GoldenTemplate`** — downstream consumers (preview, export, design sync) can't know what width/centering was originally intended.
2. **Reconstructability** — if a user pastes section HTML into the workspace editor (assembled from sections, missing wrapper), the centering is lost. We need `wrapper_utils.py` to detect and inject centering.

This plan adds:
- `wrapper_metadata` field on `GoldenTemplate` for persistence
- `wrapper_utils.py` with `detect_centering()` and `inject_centering_wrapper()` utilities
- `ensure_wrapper()` on `TemplateBuilder` that applies wrapper if missing
- Tests for all paths

## Files to Create/Modify

- `app/ai/templates/models.py` — Add `wrapper_metadata` field to `GoldenTemplate`
- `app/templates/upload/wrapper_utils.py` — **New file**: `detect_centering()`, `inject_centering_wrapper()`
- `app/templates/upload/template_builder.py` — Accept `WrapperInfo`, call `ensure_wrapper()`, store metadata
- `app/templates/upload/service.py` — Pass wrapper from analysis to builder in `confirm()`
- `app/templates/upload/tests/test_wrapper_utils.py` — **New file**: tests for wrapper utilities
- `app/templates/upload/tests/test_template_builder.py` — Add wrapper-related tests

## Implementation Steps

### Step 1: Add `wrapper_metadata` field to `GoldenTemplate`

In `app/ai/templates/models.py`, add a field after `optimization_metadata` (line 86):

```python
@dataclass(frozen=True)
class GoldenTemplate:
    """A pre-validated email template skeleton."""

    metadata: TemplateMetadata
    html: str
    slots: tuple[TemplateSlot, ...]
    maizzle_source: str = ""
    default_tokens: DefaultTokens | None = None
    source: Literal["builtin", "uploaded"] = "builtin"
    project_id: int | None = None  # project scope (None = global)
    # Precompilation (26.3)
    optimized_html: str | None = None
    optimized_at: datetime | None = None
    optimized_for_clients: tuple[str, ...] = ()
    optimization_metadata: dict[str, object] = field(default_factory=dict)
    # Wrapper reconstruction (31.4)
    wrapper_metadata: dict[str, str | None] | None = None
```

The field is `dict[str, str | None] | None` (not `WrapperInfo`) to keep `models.py` decoupled from the upload pipeline. Keys mirror `WrapperInfo` fields: `tag`, `width`, `align`, `style`, `bgcolor`, `cellpadding`, `cellspacing`, `border`, `role`, `inner_td_style`, `mso_wrapper`.

### Step 2: Create `app/templates/upload/wrapper_utils.py`

```python
"""Centering wrapper detection and injection for email HTML."""

from __future__ import annotations

import re

from lxml import html as lxml_html
from lxml.html import HtmlElement

_CENTERING_TABLE_RE = re.compile(
    r'<table[^>]*\balign\s*=\s*["\']?center["\']?[^>]*>',
    re.IGNORECASE,
)
_MAX_WIDTH_MARGIN_RE = re.compile(
    r"max-width\s*:\s*\d+px\s*;\s*margin\s*:\s*0\s+auto",
    re.IGNORECASE,
)
_MSO_WRAPPER_RE = re.compile(
    r"<!--\[if\s+mso\]>.*?<table[^>]*>.*?<tr>.*?<td[^>]*>.*?<!\[endif\]-->",
    re.DOTALL | re.IGNORECASE,
)


def detect_centering(html: str) -> bool:
    """Check if HTML body content has a centering wrapper.

    Looks for:
    - <table ... align="center"> at the top level
    - <div style="max-width: Npx; margin: 0 auto;">
    - MSO conditional wrapper table before body content
    """
    tree = lxml_html.fromstring(html)
    body = tree.find(".//body")
    root = body if body is not None else tree

    for child in root:
        if not isinstance(child, HtmlElement):
            continue
        if child.tag == "table":
            align = (child.get("align") or "").lower()
            if align == "center":
                return True
            style = child.get("style") or ""
            if _MAX_WIDTH_MARGIN_RE.search(style):
                return True
        elif child.tag == "div":
            style = child.get("style") or ""
            if _MAX_WIDTH_MARGIN_RE.search(style):
                return True
        elif child.tag == "center":
            return True

    # Check for MSO conditional wrapper in raw HTML
    if _MSO_WRAPPER_RE.search(html):
        return True

    return False


def inject_centering_wrapper(
    html: str,
    width: int = 600,
    mso_wrapper: str | None = None,
) -> str:
    """Wrap body content in a standard email centering pattern if not already centered.

    Args:
        html: Full HTML string (with <html>/<body> tags).
        width: Container width in pixels.
        mso_wrapper: Original MSO conditional block to use verbatim.
                     If None, generates a standard one.

    Returns:
        HTML with centering wrapper added, or unchanged if already centered.
    """
    if detect_centering(html):
        return html

    tree = lxml_html.fromstring(html)
    body = tree.find(".//body")
    root = body if body is not None else tree

    # Serialize body children as HTML fragments
    from lxml import etree

    fragments: list[str] = []
    if root.text:
        fragments.append(root.text)
    for child in root:
        fragments.append(
            etree.tostring(child, encoding="unicode", method="html")  # noqa: S320
        )
    inner_html = "\n".join(fragments)

    # Build MSO block
    if mso_wrapper is None:
        mso_open = (
            f'<!--[if mso]>\n'
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'width="{width}" align="center"><tr><td>\n'
            f'<![endif]-->'
        )
        mso_close = (
            '<!--[if mso]>\n'
            '</td></tr></table>\n'
            '<![endif]-->'
        )
    else:
        mso_open = mso_wrapper
        # Derive closing from the opening — standard pattern
        mso_close = (
            '<!--[if mso]>\n'
            '</td></tr></table>\n'
            '<![endif]-->'
        )

    wrapper = (
        f'{mso_open}\n'
        f'<div style="max-width: {width}px; margin: 0 auto;">\n'
        f'{inner_html}\n'
        f'</div>\n'
        f'{mso_close}'
    )

    # Replace body content
    for child in list(root):
        root.remove(child)
    root.text = None

    # We need to insert raw HTML, so re-serialize the whole document
    # with the wrapper injected as body content
    head = tree.find(".//head")
    head_html = ""
    if head is not None:
        head_html = etree.tostring(head, encoding="unicode", method="html")  # noqa: S320

    return (
        f"<html>\n"
        f"{head_html}\n"
        f"<body>\n"
        f"{wrapper}\n"
        f"</body>\n"
        f"</html>"
    )
```

### Step 3: Modify `TemplateBuilder.build()` to accept wrapper and apply it

In `app/templates/upload/template_builder.py`:

```python
"""Assemble GoldenTemplate from analysis results."""

from __future__ import annotations

import hashlib

from app.ai.templates.models import (
    DefaultTokens,
    GoldenTemplate,
    TemplateMetadata,
    TemplateSlot,
)
from app.templates.upload.analyzer import WrapperInfo
from app.templates.upload.wrapper_utils import detect_centering, inject_centering_wrapper


class TemplateBuilder:
    """Constructs a GoldenTemplate from upload analysis + user overrides."""

    def build(
        self,
        sanitized_html: str,
        slots: tuple[TemplateSlot, ...],
        tokens: DefaultTokens,
        layout_type: str,
        column_count: int,
        sections: list[str],
        name: str | None = None,
        description: str | None = None,
        wrapper: WrapperInfo | None = None,
    ) -> GoldenTemplate:
        """Create GoldenTemplate with uploaded_ namespace prefix."""
        # Ensure centering wrapper is present if metadata says one existed
        if wrapper is not None:
            sanitized_html = self._ensure_wrapper(sanitized_html, wrapper)

        # Generate name from content hash if not provided
        html_hash = hashlib.sha256(sanitized_html.encode()).hexdigest()[:6]
        template_name = name or f"uploaded_{layout_type}_{html_hash}"

        # Ensure uploaded_ prefix
        if not template_name.startswith("uploaded_"):
            template_name = f"uploaded_{template_name}"

        display_name = template_name.replace("_", " ").replace("uploaded ", "Uploaded ").title()
        desc = description or f"Uploaded {layout_type} template with {len(slots)} slots"

        has_hero = any(s.slot_type == "image" and s.required for s in slots)

        metadata = TemplateMetadata(
            name=template_name,
            display_name=display_name,
            layout_type=layout_type,  # type: ignore[arg-type]
            column_count=column_count,
            has_hero_image=has_hero,
            has_navigation=False,
            has_social_links=any(s.slot_type == "social" for s in slots),
            sections=tuple(sections),
            ideal_for=("uploaded",),
            description=desc,
        )

        # Serialize wrapper info for storage
        wrapper_metadata: dict[str, str | None] | None = None
        if wrapper is not None:
            wrapper_metadata = {
                "tag": wrapper.tag,
                "width": wrapper.width,
                "align": wrapper.align,
                "style": wrapper.style,
                "bgcolor": wrapper.bgcolor,
                "cellpadding": wrapper.cellpadding,
                "cellspacing": wrapper.cellspacing,
                "border": wrapper.border,
                "role": wrapper.role,
                "inner_td_style": wrapper.inner_td_style,
                "mso_wrapper": wrapper.mso_wrapper,
            }

        return GoldenTemplate(
            metadata=metadata,
            html=sanitized_html,
            slots=slots,
            default_tokens=tokens,
            source="uploaded",
            project_id=None,
            wrapper_metadata=wrapper_metadata,
        )

    @staticmethod
    def _ensure_wrapper(html: str, wrapper: WrapperInfo) -> str:
        """Ensure centering wrapper is present in HTML.

        If the HTML already has centering (detected by wrapper_utils),
        returns it unchanged. Otherwise, injects a centering wrapper
        using the metadata from the original import.
        """
        if detect_centering(html):
            return html

        width = int(wrapper.width) if wrapper.width and wrapper.width.isdigit() else 600
        return inject_centering_wrapper(
            html,
            width=width,
            mso_wrapper=wrapper.mso_wrapper,
        )
```

### Step 4: Pass wrapper to builder in `service.py` `confirm()` method

In `app/templates/upload/service.py`, modify the `confirm()` method. After re-analyzing (line 190-192), extract wrapper from analysis and pass to builder:

```python
# Build GoldenTemplate
section_names = [s.component_name for s in analysis.sections]
template = self._builder.build(
    sanitized_html=upload.sanitized_html,
    slots=slots,
    tokens=tokens,
    layout_type=stored.get("layout_type", analysis.layout_type),
    column_count=stored.get("column_count", analysis.complexity.column_count),
    sections=section_names,
    name=name,
    description=description,
    wrapper=analysis.wrapper,
)
```

This is the only change to `service.py` — add `wrapper=analysis.wrapper` to the `self._builder.build()` call at line ~209.

### Step 5: Create `app/templates/upload/tests/test_wrapper_utils.py`

```python
"""Tests for wrapper detection and injection utilities."""

from __future__ import annotations

from app.templates.upload.wrapper_utils import detect_centering, inject_centering_wrapper

# ── Fixtures ──

CENTERED_TABLE_HTML = """
<html>
<body>
<table width="600" align="center" cellpadding="0" cellspacing="0" border="0">
  <tr><td>
    <table width="600">
      <tr><td><h1 style="font-size: 24px;">Hello</h1></td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""

CENTERED_DIV_HTML = """
<html>
<body>
<div style="max-width: 600px; margin: 0 auto;">
  <table width="600">
    <tr><td><h1 style="font-size: 24px;">Hello</h1></td></tr>
  </table>
</div>
</body>
</html>
"""

CENTERED_CENTER_TAG_HTML = """
<html>
<body>
<center>
  <table width="600">
    <tr><td><h1 style="font-size: 24px;">Hello</h1></td></tr>
  </table>
</center>
</body>
</html>
"""

MSO_CENTERED_HTML = """
<html>
<body>
<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0"><tr><td><![endif]-->
<div style="max-width: 600px; margin: 0 auto;">
  <table width="600">
    <tr><td><h1 style="font-size: 24px;">Hello</h1></td></tr>
  </table>
</div>
<!--[if mso]></td></tr></table><![endif]-->
</body>
</html>
"""

UNCENTERED_HTML = """
<html>
<body>
<table width="600">
  <tr><td><h1 style="font-size: 24px;">Hello</h1></td></tr>
</table>
<table width="600">
  <tr><td><p style="margin:0 0 10px 0;">Body text content here for testing purposes.</p></td></tr>
</table>
</body>
</html>
"""


class TestDetectCentering:
    def test_centered_table(self) -> None:
        assert detect_centering(CENTERED_TABLE_HTML) is True

    def test_centered_div(self) -> None:
        assert detect_centering(CENTERED_DIV_HTML) is True

    def test_centered_center_tag(self) -> None:
        assert detect_centering(CENTERED_CENTER_TAG_HTML) is True

    def test_mso_centered(self) -> None:
        assert detect_centering(MSO_CENTERED_HTML) is True

    def test_uncentered(self) -> None:
        assert detect_centering(UNCENTERED_HTML) is False


class TestInjectCenteringWrapper:
    def test_injects_wrapper_on_uncentered(self) -> None:
        result = inject_centering_wrapper(UNCENTERED_HTML, width=600)
        assert "max-width: 600px" in result
        assert "margin: 0 auto" in result
        assert "<!--[if mso]>" in result

    def test_no_double_wrap_on_centered(self) -> None:
        result = inject_centering_wrapper(CENTERED_TABLE_HTML, width=600)
        assert result == CENTERED_TABLE_HTML

    def test_custom_width(self) -> None:
        result = inject_centering_wrapper(UNCENTERED_HTML, width=700)
        assert "max-width: 700px" in result
        assert 'width="700"' in result

    def test_preserves_mso_wrapper_verbatim(self) -> None:
        mso = '<!--[if mso]><table role="presentation" width="640" align="center"><tr><td><![endif]-->'
        result = inject_centering_wrapper(UNCENTERED_HTML, width=640, mso_wrapper=mso)
        assert 'width="640"' in result
        assert mso in result

    def test_preserves_body_content(self) -> None:
        result = inject_centering_wrapper(UNCENTERED_HTML, width=600)
        assert "Hello" in result
        assert "Body text content" in result
```

### Step 6: Add wrapper tests to `test_template_builder.py`

Add at the end of the existing `TestTemplateBuilder` class:

```python
    def test_wrapper_metadata_stored(self) -> None:
        """Wrapper metadata is persisted on GoldenTemplate."""
        from app.templates.upload.analyzer import WrapperInfo

        wrapper = WrapperInfo(
            tag="table",
            width="600",
            align="center",
            bgcolor="#ffffff",
        )
        tmpl = TemplateBuilder().build(
            sanitized_html="<html><body><table width='600'><tr><td>Hi</td></tr></table></body></html>",
            slots=self._make_slots(),
            tokens=self._make_tokens(),
            layout_type="promotional",
            column_count=1,
            sections=["hero"],
            wrapper=wrapper,
        )
        assert tmpl.wrapper_metadata is not None
        assert tmpl.wrapper_metadata["width"] == "600"
        assert tmpl.wrapper_metadata["align"] == "center"
        assert tmpl.wrapper_metadata["bgcolor"] == "#ffffff"

    def test_no_wrapper_metadata_when_none(self) -> None:
        """No wrapper → wrapper_metadata is None."""
        tmpl = TemplateBuilder().build(
            sanitized_html="<html><body>Test</body></html>",
            slots=self._make_slots(),
            tokens=self._make_tokens(),
            layout_type="newsletter",
            column_count=1,
            sections=["body"],
        )
        assert tmpl.wrapper_metadata is None

    def test_ensure_wrapper_adds_centering(self) -> None:
        """HTML without centering gets wrapper injected."""
        from app.templates.upload.analyzer import WrapperInfo

        wrapper = WrapperInfo(tag="table", width="600", align="center")
        html = "<html><body><table width='600'><tr><td>Content</td></tr></table></body></html>"
        tmpl = TemplateBuilder().build(
            sanitized_html=html,
            slots=(),
            tokens=self._make_tokens(),
            layout_type="promotional",
            column_count=1,
            sections=["content"],
            wrapper=wrapper,
        )
        assert "max-width: 600px" in tmpl.html
        assert "margin: 0 auto" in tmpl.html

    def test_ensure_wrapper_no_double_wrap(self) -> None:
        """HTML that already has centering is not double-wrapped."""
        from app.templates.upload.analyzer import WrapperInfo

        wrapper = WrapperInfo(tag="table", width="600", align="center")
        html = (
            '<html><body>'
            '<table width="600" align="center"><tr><td>'
            '<table width="600"><tr><td>Content</td></tr></table>'
            '</td></tr></table>'
            '</body></html>'
        )
        tmpl = TemplateBuilder().build(
            sanitized_html=html,
            slots=(),
            tokens=self._make_tokens(),
            layout_type="promotional",
            column_count=1,
            sections=["content"],
            wrapper=wrapper,
        )
        # Should not add a second wrapper
        assert tmpl.html.count("margin: 0 auto") <= 1
```

## Security Checklist

**No new endpoints** are added. This is internal template assembly logic.

- **Auth/RBAC:** N/A — no new routes
- **Rate limiting:** N/A — no new routes
- **Input validation:** `WrapperInfo` fields come from `AnalysisResult` which analyzed already-sanitized HTML (`sanitize_html_xss(profile="import_annotator")`). The `mso_wrapper` field is raw MSO conditional HTML from sanitized source. `inject_centering_wrapper()` uses hardcoded centering patterns — no user input in wrapper structure. Width value is parsed via `int()` with fallback to 600.
- **SQL injection:** N/A — no new queries
- **XSS:** `wrapper_metadata` is a dict stored on an in-memory dataclass, not rendered. The wrapper HTML injected by `inject_centering_wrapper()` uses hardcoded structural elements only (table, div, MSO conditionals) — no scripts, no event handlers. Output still passes through `sanitize_html_xss()` in the upload flow.
- **Error leakage:** N/A — no new error paths
- **Secrets:** N/A

## Verification

- [ ] `make check` passes (includes lint, types, tests, frontend, security-check)
- [ ] Import email with `width="600" align="center"` wrapper → `GoldenTemplate.wrapper_metadata` has width=600, align=center
- [ ] Import email without centering → `ensure_wrapper()` adds `max-width: 600px; margin: 0 auto` + MSO ghost table
- [ ] Import email with MSO conditional wrapper → original MSO block used verbatim in reconstruction
- [ ] Import email that already has centering → no double-wrapping (count of `margin: 0 auto` ≤ 1)
- [ ] `wrapper_metadata` is `None` for templates built without wrapper
- [ ] Existing template builder tests still pass (backward-compatible `wrapper=None` default)
