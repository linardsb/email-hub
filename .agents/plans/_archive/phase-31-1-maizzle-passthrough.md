# Plan: 31.1 — Maizzle Passthrough for Pre-Compiled HTML

## Context

When a user imports or pastes a fully-built email HTML template (exported from another tool, hand-coded, or from a client), the Maizzle `render()` pipeline double-processes it. Juice re-inlines `<style>` CSS into elements that already have inline styles, producing duplicated/conflicting attributes. Maizzle transformers modify URLs, reformat structure, and prettification introduces whitespace that breaks email client rendering.

Pre-compiled HTML should skip Maizzle's `render()` entirely but still pass through CSS optimization (PostCSS ontology plugin + Lightning CSS minification on `<style>` blocks). The sidecar decides passthrough; the Python backend just reads and logs the flag.

## Files to Create/Modify

| File | Action | What |
|------|--------|------|
| `services/maizzle-builder/index.js` | Modify | Add `isPreCompiledEmail()` detection + passthrough logic in `/build` and `/preview` |
| `services/maizzle-builder/index.test.js` | Create | Tests for `isPreCompiledEmail()` heuristic + `/build` and `/preview` passthrough |
| `app/email_engine/schemas.py` | Modify | Add `passthrough: bool = False` to `BuildResponse` and `PreviewResponse` |
| `app/email_engine/service.py` | Modify | Read `passthrough` from sidecar response, log it, pass to response schemas |
| `app/email_engine/tests/test_passthrough.py` | Create | Python unit tests for passthrough flag propagation |

## Implementation Steps

### Step 1: Add `isPreCompiledEmail()` to sidecar

In `services/maizzle-builder/index.js`, add the detection function **before** the `app.get("/health")` line (after the `optimizeCss` function, around line 74):

```javascript
/**
 * Detect pre-compiled email HTML that should bypass Maizzle's render() pipeline.
 * All 4 heuristics must pass for passthrough to activate.
 */
function isPreCompiledEmail(source) {
  // 1. No Maizzle template syntax
  const MAIZZLE_TAGS = /<(extends|block|component|x-[a-z]|fetch|outlook)\b/i;
  if (MAIZZLE_TAGS.test(source)) return false;

  // 2. Has inline styles (≥3 elements with style="...")
  const inlineStyleCount = (source.match(/\sstyle\s*=\s*"/gi) || []).length;
  if (inlineStyleCount < 3) return false;

  // 3. Has table-based layout (≥2 tables with presentation role or layout attrs)
  const TABLE_LAYOUT = /<table\b[^>]*(?:role\s*=\s*"presentation"|cellpadding|cellspacing|width\s*=|align\s*=)[^>]*>/gi;
  const tableCount = (source.match(TABLE_LAYOUT) || []).length;
  if (tableCount < 2) return false;

  // 4. Has document shell (DOCTYPE or html+body)
  const hasDoctype = /<!DOCTYPE/i.test(source);
  const hasHtmlBody = /<html\b/i.test(source) && /<body\b/i.test(source);
  if (!hasDoctype && !hasHtmlBody) return false;

  return true;
}
```

### Step 2: Modify `/build` handler for passthrough

In `services/maizzle-builder/index.js`, replace the `/build` handler (lines 79–106) with passthrough logic. The key change: after CSS optimization, check `isPreCompiledEmail()` and skip `render()` if true:

```javascript
app.post("/build", async (req, res) => {
  const start = Date.now();
  const { source, config = {}, production = false, target_clients } = req.body;
  if (!source) return res.status(400).json({ error: "source is required" });

  try {
    let html = source;
    let optimization = null;
    if (ontologyVersion && target_clients?.length) {
      const r = await optimizeCss(html, target_clients);
      html = r.optimizedHtml;
      optimization = r.optimization;
    }

    const passthrough = isPreCompiledEmail(html);

    if (passthrough) {
      // Pre-compiled HTML: skip Maizzle render(), return CSS-optimized HTML as-is
      res.json({
        html,
        build_time_ms: Date.now() - start,
        passthrough: true,
        ...(optimization && { optimization }),
      });
      return;
    }

    const maizzleConfig = { ...config, build: { content: [], ...(config.build || {}) } };
    if (production) {
      maizzleConfig.inlineCSS = { enabled: true };
      maizzleConfig.prettify = false;
      maizzleConfig.minify = { collapseWhitespace: true, removeComments: true };
    }

    const rendered = await render(html, { maizzle: maizzleConfig });
    res.json({
      html: rendered.html,
      build_time_ms: Date.now() - start,
      passthrough: false,
      ...(optimization && { optimization }),
    });
  } catch (err) {
    console.error("Build failed:", err.message);
    res.status(500).json({ error: "Build failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});
```

### Step 3: Modify `/preview` handler for passthrough

Same pattern — replace lines 108–128:

```javascript
app.post("/preview", async (req, res) => {
  const start = Date.now();
  const { source, config = {}, target_clients } = req.body;
  if (!source) return res.status(400).json({ error: "source is required" });

  try {
    let html = source;
    let optimization = null;
    if (ontologyVersion && target_clients?.length) {
      const r = await optimizeCss(html, target_clients);
      html = r.optimizedHtml;
      optimization = r.optimization;
    }

    const passthrough = isPreCompiledEmail(html);

    if (passthrough) {
      res.json({
        html,
        build_time_ms: Date.now() - start,
        passthrough: true,
        ...(optimization && { optimization }),
      });
      return;
    }

    const rendered = await render(html, { maizzle: { ...config, inlineCSS: { enabled: true }, prettify: true } });
    res.json({
      html: rendered.html,
      build_time_ms: Date.now() - start,
      passthrough: false,
      ...(optimization && { optimization }),
    });
  } catch (err) {
    console.error("Preview failed:", err.message);
    res.status(500).json({ error: "Preview failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});
```

### Step 4: Create sidecar tests

Create `services/maizzle-builder/index.test.js` using vitest (matches existing `postcss-email-optimize.test.js` pattern):

```javascript
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Import the detection function — need to export it from index.js first.
// We'll test via the exported function (see Step 4a below).

// Alternatively, test the heuristics inline since index.js is an Express server.
// Best approach: extract isPreCompiledEmail to a separate module.

// Load a real golden template for test fixtures.
const TEMPLATE_DIR = resolve(__dirname, '../../app/ai/templates/library');
function loadTemplate(name) {
  return readFileSync(resolve(TEMPLATE_DIR, `${name}.html`), 'utf-8');
}

describe('isPreCompiledEmail', () => {
  // We import from the extracted module (see Step 4a)
  let isPreCompiledEmail;

  beforeAll(async () => {
    const mod = await import('./precompiled-detect.js');
    isPreCompiledEmail = mod.isPreCompiledEmail;
  });

  it('detects golden templates as pre-compiled', () => {
    const html = loadTemplate('promotional_hero');
    expect(isPreCompiledEmail(html)).toBe(true);
  });

  it('detects multiple golden templates as pre-compiled', () => {
    for (const name of ['newsletter_2col', 'transactional_receipt', 'minimal_text']) {
      expect(isPreCompiledEmail(loadTemplate(name))).toBe(true);
    }
  });

  it('rejects Maizzle template source', () => {
    const maizzle = `<extends src="layouts/default.html"><block name="content"><p>Hello</p></block></extends>`;
    expect(isPreCompiledEmail(maizzle)).toBe(false);
  });

  it('rejects HTML with <x- custom tags', () => {
    const source = `<!DOCTYPE html><html><body><x-header>Logo</x-header></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects plain HTML without inline styles', () => {
    const source = `<!DOCTYPE html><html><body><table role="presentation"><tr><td>Hi</td></tr></table><table role="presentation"><tr><td>Bye</td></tr></table></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects HTML fragment without document shell', () => {
    const source = `<table role="presentation" cellpadding="0"><tr><td style="color:red">A</td></tr></table><table role="presentation" cellpadding="0"><tr><td style="padding:10px">B</td></tr></table><p style="margin:0">C</p>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects HTML without table layout', () => {
    const source = `<!DOCTYPE html><html><body><div style="color:red">A</div><div style="padding:10px">B</div><p style="margin:0">C</p></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });
});
```

### Step 4a: Extract detection function to importable module

To make the function testable without starting the Express server, extract it to `services/maizzle-builder/precompiled-detect.js`:

```javascript
/**
 * Detect pre-compiled email HTML that should bypass Maizzle's render() pipeline.
 * All 4 heuristics must pass for passthrough to activate.
 */
export function isPreCompiledEmail(source) {
  // 1. No Maizzle template syntax
  const MAIZZLE_TAGS = /<(extends|block|component|x-[a-z]|fetch|outlook)\b/i;
  if (MAIZZLE_TAGS.test(source)) return false;

  // 2. Has inline styles (≥3 elements with style="...")
  const inlineStyleCount = (source.match(/\sstyle\s*=\s*"/gi) || []).length;
  if (inlineStyleCount < 3) return false;

  // 3. Has table-based layout (≥2 tables with presentation role or layout attrs)
  const TABLE_LAYOUT = /<table\b[^>]*(?:role\s*=\s*"presentation"|cellpadding|cellspacing|width\s*=|align\s*=)[^>]*>/gi;
  const tableCount = (source.match(TABLE_LAYOUT) || []).length;
  if (tableCount < 2) return false;

  // 4. Has document shell (DOCTYPE or html+body)
  const hasDoctype = /<!DOCTYPE/i.test(source);
  const hasHtmlBody = /<html\b/i.test(source) && /<body\b/i.test(source);
  if (!hasDoctype && !hasHtmlBody) return false;

  return true;
}
```

Then in `index.js`, replace the inline function with an import:

```javascript
import { isPreCompiledEmail } from "./precompiled-detect.js";
```

### Step 5: Add `passthrough` to Python response schemas

In `app/email_engine/schemas.py`, add `passthrough` field to both response schemas:

**`BuildResponse`** (line 25) — add after `is_production` field:

```python
passthrough: bool = False
```

**`PreviewResponse`** (line 40) — add after `build_time_ms` field:

```python
passthrough: bool = False
```

### Step 6: Modify `_call_builder()` to return passthrough flag

In `app/email_engine/service.py`, change `_call_builder()` return type from `tuple[str, dict[str, Any] | None]` to `tuple[str, dict[str, Any] | None, bool]`:

```python
async def _call_builder(
    self,
    source_html: str,
    config_overrides: dict[str, object] | None,
    is_production: bool,
    target_clients: list[str] | None = None,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Call the Maizzle builder sidecar. Returns (html, optimization_metadata, passthrough)."""
    payload: dict[str, object] = {
        "source": source_html,
        "config": config_overrides or {},
        "production": is_production,
    }
    if target_clients:
        payload["target_clients"] = target_clients

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{MAIZZLE_BUILDER_URL}/build", json=payload)
            response.raise_for_status()
            result = response.json()
            return str(result["html"]), result.get("optimization"), bool(result.get("passthrough", False))
    except httpx.ConnectError as exc:
        raise BuildServiceUnavailableError("Cannot connect to maizzle-builder service") from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "email_engine.builder_http_error",
            status_code=exc.response.status_code,
        )
        raise BuildFailedError("Email build failed") from exc
```

### Step 7: Update `build()` and `preview()` to propagate passthrough

**`build()` method** — update the `_call_builder` call (line ~67) to unpack the third element and log it:

```python
compiled, optimization, passthrough = await self._call_builder(
    data.source_html,
    data.config_overrides,
    data.is_production,
    target_clients=settings.email_engine.css_compiler_target_clients,
)
compiled = sanitize_html_xss(compiled)
if optimization:
    logger.info(
        "email_engine.css_optimized",
        removed_count=len(optimization.get("removed_properties", [])),
        conversion_count=len(optimization.get("conversions", [])),
    )
if passthrough:
    logger.info("email_engine.build_passthrough", build_id=build.id)
```

The `BuildResponse` is populated from the ORM model via `model_validate(build)`. The `passthrough` field isn't on the DB model — it's a transient response field. So set it explicitly after validation:

```python
response = BuildResponse.model_validate(build)
response.passthrough = passthrough
return response
```

**`preview()` method** — update similarly:

```python
compiled, _optimization, passthrough = await self._call_builder(
    data.source_html,
    data.config_overrides,
    is_production=False,
    target_clients=settings.email_engine.css_compiler_target_clients,
)
compiled = sanitize_html_xss(compiled)
elapsed = (time.monotonic() - start) * 1000
logger.info("email_engine.preview_completed", build_time_ms=elapsed, passthrough=passthrough)
return PreviewResponse(compiled_html=compiled, build_time_ms=round(elapsed, 2), passthrough=passthrough)
```

### Step 8: Create Python tests for passthrough propagation

Create `app/email_engine/tests/test_passthrough.py`:

```python
"""Tests for Maizzle passthrough flag propagation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.email_engine.schemas import BuildRequest, PreviewResponse
from app.email_engine.service import EmailEngineService


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _mock_httpx_response(*, passthrough: bool, html: str = "<html></html>") -> MagicMock:
    """Create a mock httpx response with the given passthrough flag."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "html": html,
        "build_time_ms": 42,
        "passthrough": passthrough,
        "optimization": {"removed_properties": [], "conversions": [], "warnings": []},
    }
    return resp


class TestPassthroughPropagation:
    """Verify passthrough flag flows from sidecar response to Python schemas."""

    @pytest.mark.asyncio
    async def test_call_builder_returns_passthrough_true(self, mock_db: AsyncMock) -> None:
        service = EmailEngineService(mock_db)
        mock_resp = _mock_httpx_response(passthrough=True)

        with patch("app.email_engine.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            _html, _opt, passthrough = await service._call_builder("src", None, False)
            assert passthrough is True

    @pytest.mark.asyncio
    async def test_call_builder_returns_passthrough_false(self, mock_db: AsyncMock) -> None:
        service = EmailEngineService(mock_db)
        mock_resp = _mock_httpx_response(passthrough=False)

        with patch("app.email_engine.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            _html, _opt, passthrough = await service._call_builder("src", None, False)
            assert passthrough is False

    @pytest.mark.asyncio
    async def test_call_builder_missing_passthrough_defaults_false(self, mock_db: AsyncMock) -> None:
        service = EmailEngineService(mock_db)
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"html": "<html></html>", "build_time_ms": 10}

        with patch("app.email_engine.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            _html, _opt, passthrough = await service._call_builder("src", None, False)
            assert passthrough is False

    def test_preview_response_schema_has_passthrough(self) -> None:
        resp = PreviewResponse(compiled_html="<html></html>", build_time_ms=10.0, passthrough=True)
        assert resp.passthrough is True

    def test_preview_response_schema_defaults_false(self) -> None:
        resp = PreviewResponse(compiled_html="<html></html>", build_time_ms=10.0)
        assert resp.passthrough is False
```

## Security Checklist

| Check | Status | Notes |
|-------|--------|-------|
| **No new endpoints** | N/A | No new routes — only modifying internal behavior |
| **Auth preserved** | OK | Existing `Depends(get_current_user)` on `/build` and `/preview` routes unchanged |
| **XSS sanitization** | OK | `sanitize_html_xss(compiled)` still runs in Python after sidecar returns, regardless of passthrough |
| **Input validation** | OK | Existing `source` field validation unchanged; `isPreCompiledEmail()` is read-only string analysis |
| **No eval/exec** | OK | Detection uses regex only — no `eval()`, no dynamic code execution |
| **Rate limiting** | OK | Existing rate limits on email engine routes unchanged |
| **Error messages** | OK | No new error responses; passthrough is informational metadata only |
| **SQL injection** | N/A | No database queries modified |

## Verification

- [ ] `cd services/maizzle-builder && npm test` — sidecar tests pass (postcss-email-optimize + new passthrough tests)
- [ ] `make test` — Python tests pass (including new `test_passthrough.py`)
- [ ] `make lint` — ruff format + lint pass
- [ ] `make types` — mypy + pyright pass (new tuple[str, dict | None, bool] return type)
- [ ] Golden template HTML (`promotional_hero.html`) detected as pre-compiled → `passthrough: true`
- [ ] Maizzle template syntax (`<extends>`, `<block>`) → `passthrough: false`
- [ ] CSS optimization still applies on passthrough (unsupported properties removed from `<style>` blocks)
- [ ] `make check` passes (full lint + types + tests + security)
