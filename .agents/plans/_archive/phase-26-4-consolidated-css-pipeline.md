# Plan: Phase 26.4 — Consolidated CSS Pipeline in Maizzle Sidecar

## Context

Currently: Python `optimize_css()` (stages 1-5) → HTTP → Node.js Maizzle/Juice inline. Two processes, two HTTP calls, HTML re-parsed twice. This consolidates into one sidecar call: PostCSS plugin (ontology elimination + conversion) → Lightning CSS minify → Maizzle/Juice inline. Python `EmailCSSCompiler` stays for the standalone API + precompilation (26.3).

## Files to Create

- `services/maizzle-builder/scripts/sync-ontology.js` — YAML→JSON ontology converter
- `services/maizzle-builder/postcss-email-optimize.js` — PostCSS plugin
- `services/maizzle-builder/postcss-email-optimize.test.js` — Plugin tests (vitest)

## Files to Modify

- `services/maizzle-builder/index.js` — Integrate plugin + Lightning CSS + new request/response fields
- `services/maizzle-builder/package.json` — Add deps + scripts
- `services/maizzle-builder/Dockerfile` — Copy new files
- `app/ai/blueprints/nodes/maizzle_build_node.py` — Remove Python CSS opt, pass `target_clients` to sidecar
- `app/email_engine/service.py` — Remove `_optimize_css_for_build()`, update `_call_builder()`
- `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py` — Update for new flow
- `Makefile` — Add `sync-ontology` target

## Implementation Steps

### Step 1: Create `services/maizzle-builder/scripts/sync-ontology.js`

Reads 4 YAML files from `app/knowledge/ontology/data/`, writes lookup-optimized JSON.

```js
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_SRC = resolve(__dirname, '../../../app/knowledge/ontology/data');
const DATA_DEST = resolve(__dirname, '../data');

function loadYaml(filename) {
  return yaml.load(readFileSync(resolve(DATA_SRC, filename), 'utf-8'));
}

function buildOptimized() {
  const clientsData = loadYaml('clients.yaml');
  const propsData = loadYaml('css_properties.yaml');
  const supportData = loadYaml('support_matrix.yaml');
  const fallbacksData = loadYaml('fallbacks.yaml');

  // Index properties by CSS name for fast Declaration lookup
  const propertiesByName = {};
  for (const p of propsData.properties) {
    if (!propertiesByName[p.property_name]) propertiesByName[p.property_name] = [];
    propertiesByName[p.property_name].push({ id: p.id, value: p.value || null, category: p.category });
  }

  // Sparse support: only none/partial stored (absent = full)
  const supportLookup = {};
  for (const s of (supportData.support || [])) {
    supportLookup[`${s.property_id}::${s.client_id}`] = s.level;
  }

  // Fallbacks indexed by source_property_id, with resolved target names
  const fallbacksBySource = {};
  for (const f of (fallbacksData.fallbacks || [])) {
    if (!fallbacksBySource[f.source_property_id]) fallbacksBySource[f.source_property_id] = [];
    const target = propsData.properties.find(p => p.id === f.target_property_id);
    fallbacksBySource[f.source_property_id].push({
      target_property_name: target?.property_name || null,
      target_value: target?.value || null,
      client_ids: f.client_ids || [],
      technique: f.technique || null,
    });
  }

  return {
    version: new Date().toISOString(),
    client_ids: clientsData.clients.map(c => c.id),
    properties_by_name: propertiesByName,
    support_lookup: supportLookup,
    fallbacks_by_source: fallbacksBySource,
  };
}

mkdirSync(DATA_DEST, { recursive: true });
const ontology = buildOptimized();
const outPath = resolve(DATA_DEST, 'ontology.json');
writeFileSync(outPath, JSON.stringify(ontology, null, 2));

const propCount = Object.values(ontology.properties_by_name).flat().length;
console.log(`Ontology synced: ${propCount} properties, ${Object.keys(ontology.support_lookup).length} support entries → ${outPath}`);
```

### Step 2: Create `services/maizzle-builder/postcss-email-optimize.js`

Mirrors Python `should_remove_property` + `get_conversions_for_property` logic.

```js
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
let ontologyData = null;

function loadOntology() {
  if (ontologyData) return ontologyData;
  ontologyData = JSON.parse(readFileSync(resolve(__dirname, 'data/ontology.json'), 'utf-8'));
  return ontologyData;
}

function findPropertyId(ontology, propName, value) {
  const entries = ontology.properties_by_name[propName];
  if (!entries) return null;
  if (value) {
    const first = value.trim().split(/\s/)[0];
    const specific = entries.find(e => e.value === first);
    if (specific) return specific.id;
  }
  return (entries.find(e => e.value === null) || entries[0])?.id || null;
}

function getSupport(ontology, propertyId, clientId) {
  return ontology.support_lookup[`${propertyId}::${clientId}`] || 'full';
}

function shouldRemove(ontology, propertyId, targetClients) {
  if (!targetClients.every(c => getSupport(ontology, propertyId, c) === 'none')) return false;
  const fb = ontology.fallbacks_by_source[propertyId];
  return !fb || fb.length === 0;
}

function getConversions(ontology, propertyId, targetClients) {
  const unsupported = targetClients.filter(c => getSupport(ontology, propertyId, c) === 'none');
  if (!unsupported.length) return [];
  const fallbacks = ontology.fallbacks_by_source[propertyId];
  if (!fallbacks) return [];

  const result = [];
  for (const fb of fallbacks) {
    let affected = unsupported;
    if (fb.client_ids.length > 0) {
      affected = unsupported.filter(c => fb.client_ids.includes(c));
      if (!affected.length) continue;
    }
    if (fb.target_property_name) {
      result.push({
        replacement_property: fb.target_property_name,
        replacement_value: fb.target_value || '',
        reason: fb.technique || 'Fallback',
        affected_clients: affected,
      });
    }
  }
  return result;
}

const REMOVE_AT_RULES = new Set(['charset', 'layer', 'import', 'namespace']);

const plugin = (opts = {}) => {
  const targetClients = opts.targetClients || ['gmail_web', 'outlook_365_win', 'apple_mail_macos', 'yahoo_web'];
  const ontology = loadOntology();
  const removed = [];
  const conversions = [];
  const warnings = [];

  return {
    postcssPlugin: 'postcss-email-optimize',

    Declaration(decl, { result }) {
      const propertyId = findPropertyId(ontology, decl.prop, decl.value);
      if (!propertyId) return;

      if (shouldRemove(ontology, propertyId, targetClients)) {
        removed.push(`${decl.prop}: ${decl.value}`);
        result.messages.push({ type: 'email-optimize', subtype: 'removed', property: decl.prop });
        decl.remove();
        return;
      }

      const convs = getConversions(ontology, propertyId, targetClients);
      if (convs.length > 0) {
        const first = convs[0];
        conversions.push({
          original_property: decl.prop, original_value: decl.value,
          replacement_property: first.replacement_property,
          replacement_value: first.replacement_value || decl.value,
          reason: first.reason, affected_clients: first.affected_clients,
        });
        decl.prop = first.replacement_property;
        if (first.replacement_value) decl.value = first.replacement_value;
      }

      const partial = targetClients.filter(c => getSupport(ontology, propertyId, c) === 'partial');
      if (partial.length) warnings.push(`${decl.prop}: partial support in ${partial.join(', ')}`);
    },

    AtRule(atRule) {
      if (REMOVE_AT_RULES.has(atRule.name.toLowerCase())) {
        warnings.push(`Removed @${atRule.name}`);
        atRule.remove();
      }
    },

    OnceExit(root, { result }) {
      result.emailOptimization = { removed_properties: removed, conversions, warnings };
    },
  };
};

plugin.postcss = true;
export default plugin;
export { loadOntology };
```

### Step 3: Rewrite `services/maizzle-builder/index.js`

```js
import express from "express";
import { render } from "@maizzle/framework";
import postcss from "postcss";
import emailOptimize, { loadOntology } from "./postcss-email-optimize.js";
import { transform } from "lightningcss";

const app = express();
const PORT = process.env.PORT || 3001;
app.use(express.json({ limit: "5mb" }));

let ontologyVersion = null;
try {
  ontologyVersion = loadOntology().version;
  console.log(`Ontology loaded: ${ontologyVersion}`);
} catch (err) {
  console.warn(`Ontology not loaded: ${err.message}`);
}

async function optimizeCss(html, targetClients) {
  const MSO_RE = /<!--\[if\s+mso.*?\]>.*?<!\[endif\]-->/gis;
  const msoMap = new Map();
  let idx = 0;
  let safe = html;
  for (const m of html.matchAll(MSO_RE)) {
    const ph = `__MSO_${idx++}__`;
    msoMap.set(ph, m[0]);
    safe = safe.replace(m[0], ph);
  }

  const STYLE_RE = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  const blocks = [];
  let match;
  while ((match = STYLE_RE.exec(safe)) !== null) blocks.push(match[1]);

  if (!blocks.length) {
    for (const [ph, orig] of msoMap) safe = safe.replace(ph, orig);
    return { optimizedHtml: safe, optimization: { removed_properties: [], conversions: [], warnings: [], original_css_size: 0, optimized_css_size: 0 } };
  }

  const allRemoved = [], allConversions = [], allWarnings = [];
  let origSize = 0, optSize = 0;
  const optimized = [];

  for (const css of blocks) {
    origSize += Buffer.byteLength(css, 'utf-8');
    const r = await postcss([emailOptimize({ targetClients })]).process(css, { from: undefined });
    let out = r.css;
    try { out = transform({ filename: 'email.css', code: Buffer.from(out), minify: true }).code.toString(); } catch {}
    optSize += Buffer.byteLength(out, 'utf-8');
    optimized.push(out);
    if (r.emailOptimization) {
      allRemoved.push(...r.emailOptimization.removed_properties);
      allConversions.push(...r.emailOptimization.conversions);
      allWarnings.push(...r.emailOptimization.warnings);
    }
  }

  let bi = 0;
  let result = safe.replace(STYLE_RE, () => `<style>${optimized[bi++] || ''}</style>`);
  for (const [ph, orig] of msoMap) result = result.replace(ph, orig);

  return { optimizedHtml: result, optimization: { removed_properties: allRemoved, conversions: allConversions, warnings: allWarnings, original_css_size: origSize, optimized_css_size: optSize } };
}

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", service: "maizzle-builder", ontology_version: ontologyVersion });
});

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

    const maizzleConfig = { ...config, build: { content: [], ...(config.build || {}) } };
    if (production) {
      maizzleConfig.inlineCSS = { enabled: true };
      maizzleConfig.prettify = false;
      maizzleConfig.minify = { collapseWhitespace: true, removeComments: true };
    }

    const rendered = await render(html, { maizzle: maizzleConfig });
    res.json({ html: rendered.html, build_time_ms: Date.now() - start, ...(optimization && { optimization }) });
  } catch (err) {
    console.error("Build failed:", err.message);
    res.status(500).json({ error: "Build failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});

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

    const rendered = await render(html, { maizzle: { ...config, inlineCSS: { enabled: true }, prettify: true } });
    res.json({ html: rendered.html, build_time_ms: Date.now() - start, ...(optimization && { optimization }) });
  } catch (err) {
    console.error("Preview failed:", err.message);
    res.status(500).json({ error: "Preview failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});

app.listen(PORT, () => console.log(`Maizzle builder listening on port ${PORT}`));
```

### Step 4: Update `services/maizzle-builder/package.json`

Add to `dependencies`: `"js-yaml": "^4.1.0"`, `"lightningcss": "^1.28.0"`, `"postcss": "^8.4.49"`.
Add to `devDependencies`: `"vitest": "^3.0.0"`.
Add to `scripts`: `"sync-ontology": "node scripts/sync-ontology.js"`, `"test": "vitest run"`.

### Step 5: Update `services/maizzle-builder/Dockerfile`

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY scripts/ ./scripts/
COPY postcss-email-optimize.js ./
COPY index.js ./
COPY data/ ./data/
EXPOSE 3001
USER node
CMD ["node", "index.js"]
```

`data/ontology.json` must be generated before Docker build (CI runs `npm run sync-ontology` first).

### Step 6: Modify `app/ai/blueprints/nodes/maizzle_build_node.py`

Remove the `EmailCSSCompiler` import and `optimize_css()` call. Pass `target_clients` to sidecar, read `optimization` from response.

Replace the `execute` method:

```python
async def execute(self, context: NodeContext) -> NodeResult:
    """POST to Maizzle builder with CSS optimization, sanitize output."""
    if not context.html:
        return NodeResult(status="failed", error="No HTML to build")

    settings = get_settings()
    source_html = context.html

    skip_css = CSS_PREOPTIMIZED_MARKER in source_html
    if skip_css:
        source_html = source_html.replace(CSS_PREOPTIMIZED_MARKER, "", 1)
        logger.info("blueprint.maizzle_build.css_skipped_preoptimized")

    url = f"{settings.maizzle_builder_url}/build"
    payload: dict[str, object] = {"source": source_html, "config": {}, "production": False}

    if not skip_css:
        raw_clients = context.metadata.get("target_clients")
        if isinstance(raw_clients, list):
            payload["target_clients"] = list(cast("list[str]", raw_clients))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            compiled_html = str(result["html"])

            optimization = result.get("optimization")
            if optimization:
                logger.info(
                    "blueprint.maizzle_build.css_optimized",
                    removed_count=len(optimization.get("removed_properties", [])),
                    conversion_count=len(optimization.get("conversions", [])),
                    original_css_size=optimization.get("original_css_size", 0),
                    optimized_css_size=optimization.get("optimized_css_size", 0),
                )
    except httpx.ConnectError:
        logger.warning("blueprint.maizzle_build.unavailable", url=url)
        return NodeResult(status="failed", error="Maizzle builder unavailable")
    except httpx.HTTPStatusError as exc:
        logger.error("blueprint.maizzle_build.http_error", status=exc.response.status_code)
        return NodeResult(status="failed", error=f"Builder returned {exc.response.status_code}")
    except Exception as exc:
        logger.error("blueprint.maizzle_build.failed", error=str(exc))
        return NodeResult(status="failed", error=f"Build failed: {exc}")

    compiled_html = sanitize_html_xss(compiled_html)
    logger.info("blueprint.maizzle_build.completed", input_length=len(context.html), output_length=len(compiled_html))
    return NodeResult(status="success", html=compiled_html, details=f"Compiled {len(compiled_html)} chars")
```

The `from app.email_engine.css_compiler.compiler import EmailCSSCompiler` import (currently inside `execute`) is removed entirely.

### Step 7: Modify `app/email_engine/service.py`

**7a.** Replace `_call_builder` — add `target_clients` param, return `tuple[str, dict | None]`:

```python
async def _call_builder(
    self,
    source_html: str,
    config_overrides: dict[str, object] | None,
    is_production: bool,
    target_clients: list[str] | None = None,
) -> tuple[str, dict[str, object] | None]:
    """Call the Maizzle builder sidecar. Returns (html, optimization_metadata)."""
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
            return str(result["html"]), result.get("optimization")
    except httpx.ConnectError as exc:
        raise BuildServiceUnavailableError("Cannot connect to maizzle-builder service") from exc
    except httpx.HTTPStatusError as exc:
        logger.error("email_engine.builder_http_error", status_code=exc.response.status_code)
        raise BuildFailedError("Email build failed") from exc
```

**7b.** In `build()`, replace lines 64-70 (the `_optimize_css_for_build` + `_call_builder` block):

```python
try:
    compiled, optimization = await self._call_builder(
        data.source_html, data.config_overrides, data.is_production,
        target_clients=settings.email_engine.css_compiler_target_clients,
    )
    compiled = sanitize_html_xss(compiled)
    if optimization:
        logger.info(
            "email_engine.css_optimized",
            removed_count=len(optimization.get("removed_properties", [])),
            conversion_count=len(optimization.get("conversions", [])),
        )
    build.compiled_html = compiled
    build.status = "success"
```

**7c.** In `preview()`, same change:

```python
async def preview(self, data: PreviewRequest) -> PreviewResponse:
    logger.info("email_engine.preview_started")
    start = time.monotonic()
    compiled, _optimization = await self._call_builder(
        data.source_html, data.config_overrides, is_production=False,
        target_clients=settings.email_engine.css_compiler_target_clients,
    )
    compiled = sanitize_html_xss(compiled)
    elapsed = (time.monotonic() - start) * 1000
    logger.info("email_engine.preview_completed", build_time_ms=elapsed)
    return PreviewResponse(compiled_html=compiled, build_time_ms=round(elapsed, 2))
```

**7d.** Delete `_optimize_css_for_build()` method (lines 202-221). No longer called.

`compile_css()` and `inject_schema()` are unchanged — they still use Python `EmailCSSCompiler`.

### Step 8: Create `services/maizzle-builder/postcss-email-optimize.test.js`

```js
import { describe, it, expect } from 'vitest';
import postcss from 'postcss';
import emailOptimize from './postcss-email-optimize.js';

async function optimize(css, targetClients) {
  const result = await postcss([emailOptimize({ targetClients })]).process(css, { from: undefined });
  return { css: result.css, optimization: result.emailOptimization };
}

describe('postcss-email-optimize', () => {
  it('passes through supported properties unchanged', async () => {
    const { css } = await optimize('.hero { display: block; color: red; }', ['gmail_web']);
    expect(css).toContain('display');
    expect(css).toContain('color');
  });

  it('returns optimization metadata structure', async () => {
    const { optimization } = await optimize('.hero { display: block; }', ['gmail_web']);
    expect(optimization).toBeDefined();
    expect(optimization.removed_properties).toBeInstanceOf(Array);
    expect(optimization.conversions).toBeInstanceOf(Array);
    expect(optimization.warnings).toBeInstanceOf(Array);
  });

  it('removes @charset and @layer at-rules', async () => {
    const { css } = await optimize(
      '@charset "UTF-8"; @layer base { .x { color: red; } } .hero { margin: 0; }',
      ['gmail_web']
    );
    expect(css).not.toContain('@charset');
    expect(css).not.toContain('@layer');
    expect(css).toContain('.hero');
  });

  it('preserves @media at-rules', async () => {
    const { css } = await optimize(
      '@media (prefers-color-scheme: dark) { .hero { color: white; } }',
      ['gmail_web']
    );
    expect(css).toContain('@media');
  });

  it('handles empty CSS', async () => {
    const { css, optimization } = await optimize('', ['gmail_web']);
    expect(css).toBe('');
    expect(optimization.removed_properties).toHaveLength(0);
  });
});
```

### Step 9: Rewrite `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py`

Remove ontology mocks (Python CSS compiler no longer called). Test sidecar payload instead.

```python
# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportCallIssue=false
"""Tests for MaizzleBuildNode with consolidated sidecar CSS pipeline."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.nodes.maizzle_build_node import MaizzleBuildNode
from app.ai.blueprints.protocols import NodeContext


@pytest.fixture
def node() -> MaizzleBuildNode:
    return MaizzleBuildNode()


@contextmanager
def _patch_httpx(
    html: str = "<html><body>compiled</body></html>",
    optimization: dict[str, object] | None = None,
) -> Generator[MagicMock]:
    response_data: dict[str, object] = {"html": html}
    if optimization is not None:
        response_data["optimization"] = optimization

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", MagicMock(return_value=mock_cm)):
        yield mock_client


class TestMaizzleBuildNodeConsolidatedPipeline:
    @pytest.mark.asyncio
    async def test_passes_target_clients_to_sidecar(self, node: MaizzleBuildNode) -> None:
        ctx = NodeContext(
            html="<html><head><style>.h{color:red}</style></head><body>Hi</body></html>",
            metadata={"target_clients": ["gmail_web"]},
        )
        with _patch_httpx(optimization={"removed_properties": [], "conversions": [], "warnings": [], "original_css_size": 50, "optimized_css_size": 40}) as mock:
            result = await node.execute(ctx)
        assert result.status == "success"
        payload = mock.post.call_args.kwargs.get("json") or mock.post.call_args[1]["json"]
        assert payload["target_clients"] == ["gmail_web"]

    @pytest.mark.asyncio
    async def test_skips_target_clients_when_preoptimized(self, node: MaizzleBuildNode) -> None:
        from app.ai.templates.precompiler import CSS_PREOPTIMIZED_MARKER
        html = CSS_PREOPTIMIZED_MARKER + "<html><body>Hi</body></html>"
        ctx = NodeContext(html=html, metadata={"target_clients": ["gmail_web"]})
        with _patch_httpx() as mock:
            result = await node.execute(ctx)
        assert result.status == "success"
        payload = mock.post.call_args.kwargs.get("json") or mock.post.call_args[1]["json"]
        assert "target_clients" not in payload
        assert CSS_PREOPTIMIZED_MARKER not in payload["source"]

    @pytest.mark.asyncio
    async def test_omits_target_clients_when_not_in_metadata(self, node: MaizzleBuildNode) -> None:
        ctx = NodeContext(html="<html><body>test</body></html>")
        with _patch_httpx() as mock:
            result = await node.execute(ctx)
        assert result.status == "success"
        payload = mock.post.call_args.kwargs.get("json") or mock.post.call_args[1]["json"]
        assert "target_clients" not in payload

    @pytest.mark.asyncio
    async def test_handles_response_without_optimization(self, node: MaizzleBuildNode) -> None:
        ctx = NodeContext(html="<html><body>test</body></html>")
        with _patch_httpx():
            result = await node.execute(ctx)
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_fails_on_empty_html(self, node: MaizzleBuildNode) -> None:
        result = await node.execute(NodeContext(html=""))
        assert result.status == "failed"
```

### Step 10: Update `Makefile`

Add target after existing `ontology-sync-dry` (~line 100):

```makefile
sync-ontology: ## Sync ontology data to sidecar (YAML → JSON)
	cd services/maizzle-builder && npm run sync-ontology
```

Update `dev` target to run sync before starting:

```makefile
dev: ## Start backend + frontend in parallel
	@echo "Syncing ontology to sidecar..."
	@cd services/maizzle-builder && npm run sync-ontology 2>/dev/null || echo "Ontology sync skipped (run npm install in services/maizzle-builder first)"
	@echo "Starting backend on :8891 and frontend on :3000..."
	@(uv run uvicorn app.main:app --reload --port 8891 &) && \
	(cd cms && pnpm --filter web dev)
```

### Step 11: Install + Generate

```bash
cd services/maizzle-builder && npm install && npm run sync-ontology
```

## Security Checklist

- **No new HTTP routes.** Existing sidecar `/build` and `/preview` are internal-only (not public-facing).
- **No auth needed** — sidecar not exposed to public network.
- **`sanitize_html_xss()` still runs in Python** on all sidecar output — security boundary preserved.
- **PostCSS plugin processes only CSS declarations** — no HTML injection vector. Source comes from trusted templates.
- **Ontology is read-only static config** — no secrets, no user input.

## Verification

- [ ] `cd services/maizzle-builder && npm run sync-ontology` produces `data/ontology.json`
- [ ] `cd services/maizzle-builder && npm test` — plugin tests pass
- [ ] Sidecar `/health` returns `ontology_version`
- [ ] POST `/build` with `target_clients` returns `optimization` in response
- [ ] POST `/build` without `target_clients` works as before (backward compatible)
- [ ] `make test` — backend tests pass
- [ ] `make lint` + `make types` — clean
- [ ] `make check` — all green
- [ ] `EmailCSSCompiler.compile()` / `optimize_css()` still work (API endpoint + precompilation)
