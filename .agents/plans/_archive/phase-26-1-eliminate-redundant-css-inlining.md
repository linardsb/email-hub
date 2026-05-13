# Plan: Phase 26.1 — Eliminate Redundant CSS Inlining

## Context

The email build pipeline currently processes CSS twice:
1. **Maizzle/Juice** inlines raw CSS (Node.js sidecar, specificity-aware, handles pseudo-classes)
2. **`EmailCSSCompiler.compile()`** extracts styles, optimizes via ontology, and re-inlines via BeautifulSoup (`inliner.py:inline_styles()`)

The BeautifulSoup inliner is O(rules × elements) — 100 CSS rules × 50 matching elements = 5,000 element updates. On complex emails (30+ sections), this adds 1–5s. Since Maizzle already does high-quality CSS inlining, the Python inliner is redundant.

**Solution:** Create `EmailCSSCompiler.optimize_css()` that runs stages 1–5 only (parse → analyze → transform → eliminate → optimize) and returns HTML with optimized `<style>` blocks — ready for Maizzle to inline. The build pipeline calls `optimize_css()` before Maizzle, then skips the full `compile()`. The existing `compile()` method stays for backward compatibility (the `/compile-css` API endpoint).

### Key architectural insight from code review
- `compiler.py:71-146` — `compile()` runs 7 stages sequentially. Stages 1–5 optimize CSS. Stage 6 (`inliner.inline_styles()`) is the bottleneck. Stage 7 sanitizes.
- `inliner.py:74-111` — `inline_styles()` uses BeautifulSoup `soup.select()` per CSS rule — O(rules × elements).
- `maizzle_build_node.py:27-81` — `MaizzleBuildNode.execute()` calls Maizzle sidecar, returns `NodeResult` with `html`. No CSS optimization step currently.
- `service.py:44-89` — `EmailEngineService.build()` calls `_call_builder()` directly. No CSS optimization.
- `service.py:105-114` — `preview()` same pattern.
- Neither `build()` nor `MaizzleBuildNode` currently call `EmailCSSCompiler` at all — the double-inlining concern is about the `/compile-css` endpoint AND any future integration. The optimization value is running ontology transforms _before_ Maizzle so Maizzle inlines fewer, cleaner rules.

## Files to Create/Modify

1. **`app/email_engine/css_compiler/compiler.py`** — Add `OptimizedCSS` dataclass + `optimize_css()` method + per-stage timing telemetry to `compile()`
2. **`app/email_engine/css_compiler/__init__.py`** — Export `OptimizedCSS`, update public API
3. **`app/ai/blueprints/nodes/maizzle_build_node.py`** — Add CSS optimization before Maizzle sidecar call
4. **`app/email_engine/service.py`** — Add CSS optimization to `build()` and `preview()` flows
5. **`app/email_engine/tests/test_css_compiler.py`** — Add tests for `optimize_css()` and per-stage timing
6. **`app/ai/blueprints/nodes/tests/test_maizzle_build_node.py`** — Add test for CSS optimization integration (new file if doesn't exist)

## Implementation Steps

### Step 1: Add per-stage timing telemetry to `compile()`

In `app/email_engine/css_compiler/compiler.py`, modify `compile()` to log timing for each stage:

```python
def compile(self, html: str) -> CompilationResult:
    """Run the full CSS compilation pipeline."""
    start = time.monotonic()
    original_size = len(html.encode("utf-8"))
    removed: list[str] = []
    conversions: list[CSSConversion] = []
    warnings: list[str] = []
    stage_timings: dict[str, float] = {}

    # Stage 1: Parse — extract <style> blocks
    t0 = time.monotonic()
    html_no_styles, css_blocks = extract_styles(html)
    stage_timings["parse"] = (time.monotonic() - t0) * 1000

    # Stage 2+3+4: Analyze, Transform, Eliminate on <style> CSS
    t0 = time.monotonic()
    optimized_css_blocks: list[str] = []
    for block in css_blocks:
        processed, blk_removed, blk_conversions, blk_warnings = self._process_css_block(block)
        optimized_css_blocks.append(processed)
        removed.extend(blk_removed)
        conversions.extend(blk_conversions)
        warnings.extend(blk_warnings)
    stage_timings["analyze_transform_eliminate"] = (time.monotonic() - t0) * 1000

    # Stage 2+3+4 on inline styles
    t0 = time.monotonic()
    html_no_styles = self._process_inline_styles(html_no_styles, removed, conversions, warnings)
    stage_timings["inline_style_processing"] = (time.monotonic() - t0) * 1000

    # Stage 5: Optimize — Lightning CSS minification on each block
    t0 = time.monotonic()
    minified_blocks: list[str] = []
    for block in optimized_css_blocks:
        minified = self._minify_css(block, warnings)
        minified_blocks.append(minified)
    stage_timings["optimize"] = (time.monotonic() - t0) * 1000

    # Stage 6: Inline — parse rules and apply as inline styles
    t0 = time.monotonic()
    all_rules: list[tuple[str, list[tuple[str, str]]]] = []
    at_rules: list[str] = []
    for block in minified_blocks:
        rules = parse_css_rules(block)
        all_rules.extend(rules)
        for line in block.split("}"):
            stripped = line.strip()
            if stripped.startswith("@"):
                at_rules.append(stripped + "}")

    result_html = inline_styles(html_no_styles, all_rules)

    if at_rules:
        at_css = "\n".join(at_rules)
        result_html = result_html.replace("</head>", f"<style>{at_css}</style></head>", 1)
    stage_timings["inline"] = (time.monotonic() - t0) * 1000

    # Stage 7: Output — sanitize
    t0 = time.monotonic()
    result_html = sanitize_html_xss(result_html)
    compiled_size = len(result_html.encode("utf-8"))
    stage_timings["sanitize"] = (time.monotonic() - t0) * 1000

    compile_time = (time.monotonic() - start) * 1000

    logger.info(
        "css_compiler.compile_completed",
        original_size=original_size,
        compiled_size=compiled_size,
        reduction_pct=round((1 - compiled_size / original_size) * 100, 1)
        if original_size > 0
        else 0,
        removed_count=len(removed),
        conversion_count=len(conversions),
        target_clients=self._target_clients,
        compile_time_ms=round(compile_time, 2),
        **{f"stage_{k}_ms": round(v, 2) for k, v in stage_timings.items()},
    )

    return CompilationResult(
        html=result_html,
        original_size=original_size,
        compiled_size=compiled_size,
        removed_properties=removed,
        conversions=conversions,
        warnings=warnings,
        compile_time_ms=round(compile_time, 2),
    )
```

### Step 2: Add `OptimizedCSS` dataclass and `optimize_css()` method

In `app/email_engine/css_compiler/compiler.py`, add after the `CompilationResult` class:

```python
@dataclass(frozen=True)
class OptimizedCSS:
    """Result of CSS optimization (stages 1-5 only, no inlining).

    HTML contains optimized <style> blocks ready for external inliner (e.g. Maizzle/Juice).
    """

    html: str
    removed_properties: list[str]
    conversions: list[CSSConversion]
    warnings: list[str]
    optimize_time_ms: float
```

Add to `EmailCSSCompiler` class (new public method, after `compile()`):

```python
def optimize_css(self, html: str) -> OptimizedCSS:
    """Run CSS optimization stages 1-5 only (no inlining).

    Produces HTML with optimized <style> blocks, ready for an external
    inliner like Maizzle/Juice to convert to inline styles. Skips stage 6
    (BeautifulSoup inlining) and stage 7 (XSS sanitization — caller is
    responsible for sanitizing after inlining).

    Use this before sending HTML to the Maizzle sidecar: ontology-driven
    optimization reduces CSS rules before Juice inlines them.
    """
    start = time.monotonic()
    removed: list[str] = []
    conversions: list[CSSConversion] = []
    warnings: list[str] = []

    # Stage 1: Parse — extract <style> blocks
    html_no_styles, css_blocks = extract_styles(html)

    # Stage 2+3+4: Analyze, Transform, Eliminate on <style> CSS
    optimized_css_blocks: list[str] = []
    for block in css_blocks:
        processed, blk_removed, blk_conversions, blk_warnings = self._process_css_block(block)
        optimized_css_blocks.append(processed)
        removed.extend(blk_removed)
        conversions.extend(blk_conversions)
        warnings.extend(blk_warnings)

    # Stage 2+3+4 on inline styles
    html_no_styles = self._process_inline_styles(html_no_styles, removed, conversions, warnings)

    # Stage 5: Optimize — Lightning CSS minification
    minified_blocks: list[str] = []
    for block in optimized_css_blocks:
        minified = self._minify_css(block, warnings)
        minified_blocks.append(minified)

    # Re-inject optimized <style> blocks (NOT inlined)
    if minified_blocks:
        style_tags = "\n".join(f"<style>{block}</style>" for block in minified_blocks if block.strip())
        html_no_styles = html_no_styles.replace("</head>", f"{style_tags}</head>", 1)

    optimize_time = (time.monotonic() - start) * 1000

    logger.info(
        "css_compiler.optimize_completed",
        removed_count=len(removed),
        conversion_count=len(conversions),
        target_clients=self._target_clients,
        optimize_time_ms=round(optimize_time, 2),
    )

    return OptimizedCSS(
        html=html_no_styles,
        removed_properties=removed,
        conversions=conversions,
        warnings=warnings,
        optimize_time_ms=round(optimize_time, 2),
    )
```

### Step 3: Update `__init__.py` exports

Replace contents of `app/email_engine/css_compiler/__init__.py`:

```python
"""Email-specific CSS compiler built on Lightning CSS."""

from .compiler import CompilationResult, EmailCSSCompiler, OptimizedCSS
from .conversions import CSSConversion

__all__ = [
    "CSSConversion",
    "CompilationResult",
    "EmailCSSCompiler",
    "OptimizedCSS",
]
```

### Step 4: Add CSS optimization to `MaizzleBuildNode.execute()`

Modify `app/ai/blueprints/nodes/maizzle_build_node.py`:

```python
"""Maizzle Build deterministic node — compiles email HTML via sidecar service."""

import httpx

from app.ai.blueprints.protocols import NodeContext, NodeResult, NodeType
from app.ai.shared import sanitize_html_xss
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MaizzleBuildNode:
    """Deterministic node that compiles HTML through the Maizzle builder sidecar.

    Pipeline: optimize CSS (stages 1-5) → Maizzle build (Juice inlines) → sanitize.
    """

    @property
    def name(self) -> str:
        return "maizzle_build"

    @property
    def node_type(self) -> NodeType:
        return "deterministic"

    async def execute(self, context: NodeContext) -> NodeResult:
        """Optimize CSS, POST to Maizzle builder, sanitize output."""
        if not context.html:
            return NodeResult(
                status="failed",
                error="No HTML to build",
            )

        settings = get_settings()
        source_html = context.html

        # CSS optimization: run ontology-driven stages 1-5 before Maizzle inlines
        target_clients = context.metadata.get("target_clients")
        target_clients_list: list[str] | None = (
            list(target_clients) if isinstance(target_clients, (list, tuple)) else None
        )

        try:
            from app.email_engine.css_compiler.compiler import EmailCSSCompiler

            compiler = EmailCSSCompiler(target_clients=target_clients_list)
            optimized = compiler.optimize_css(source_html)
            source_html = optimized.html

            logger.info(
                "blueprint.maizzle_build.css_optimized",
                removed_count=len(optimized.removed_properties),
                conversion_count=len(optimized.conversions),
                optimize_time_ms=optimized.optimize_time_ms,
            )
        except Exception as exc:
            # CSS optimization is best-effort — proceed with unoptimized HTML
            logger.warning("blueprint.maizzle_build.css_optimize_failed", error=str(exc))

        url = f"{settings.maizzle_builder_url}/build"
        payload: dict[str, object] = {
            "source": source_html,
            "config": {},
            "production": False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                compiled_html = str(result["html"])
        except httpx.ConnectError:
            logger.warning("blueprint.maizzle_build.unavailable", url=url)
            return NodeResult(
                status="failed",
                error="Maizzle builder unavailable",
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "blueprint.maizzle_build.http_error",
                status=exc.response.status_code,
            )
            return NodeResult(
                status="failed",
                error=f"Builder returned {exc.response.status_code}",
            )
        except Exception as exc:
            logger.error("blueprint.maizzle_build.failed", error=str(exc))
            return NodeResult(
                status="failed",
                error=f"Build failed: {exc}",
            )

        # Sanitize final output (stage 7 equivalent)
        compiled_html = sanitize_html_xss(compiled_html)

        logger.info(
            "blueprint.maizzle_build.completed",
            input_length=len(context.html),
            output_length=len(compiled_html),
        )

        return NodeResult(
            status="success",
            html=compiled_html,
            details=f"Compiled {len(compiled_html)} chars",
        )
```

**Key design decisions:**
- `target_clients` read from `context.metadata` — already populated by `BlueprintEngine._build_node_context()` LAYER 11 (design system injection)
- CSS optimization is best-effort with try/except — if it fails, Maizzle still builds with unoptimized HTML
- `sanitize_html_xss()` now called on Maizzle output since we skip `compile()` stage 7
- Import is lazy (inside method) to avoid circular imports at module level

### Step 5: Add CSS optimization to `EmailEngineService.build()` and `preview()`

Modify `app/email_engine/service.py`:

**Add import at top (after existing imports):**
```python
from app.ai.shared import sanitize_html_xss
```

**Modify `build()` method** — add CSS optimization before `_call_builder()`:

Replace the try block in `build()` (lines 63-83) with:

```python
        try:
            # Optimize CSS before Maizzle inlining
            optimized_html = self._optimize_css_for_build(data.source_html)
            compiled = await self._call_builder(
                optimized_html, data.config_overrides, data.is_production
            )
            compiled = sanitize_html_xss(compiled)
            build.compiled_html = compiled
            build.status = "success"
        except BuildServiceUnavailableError:
            build.status = "failed"
            build.error_message = "Maizzle builder service unavailable"
            raise
        except Exception as exc:
            build.status = "failed"
            build.error_message = "Build failed"
            logger.error(
                "email_engine.build_error",
                build_id=build.id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            raise BuildFailedError("Email build failed") from exc
```

**Modify `preview()` method:**

```python
    async def preview(self, data: PreviewRequest) -> PreviewResponse:
        """Execute a preview build without persisting."""
        logger.info("email_engine.preview_started")
        start = time.monotonic()
        optimized_html = self._optimize_css_for_build(data.source_html)
        compiled = await self._call_builder(
            optimized_html, data.config_overrides, is_production=False
        )
        compiled = sanitize_html_xss(compiled)
        elapsed = (time.monotonic() - start) * 1000
        logger.info("email_engine.preview_completed", build_time_ms=elapsed)
        return PreviewResponse(compiled_html=compiled, build_time_ms=round(elapsed, 2))
```

**Add new private method:**

```python
    def _optimize_css_for_build(self, source_html: str) -> str:
        """Run CSS optimization stages 1-5 before Maizzle inlining.

        Best-effort — returns unmodified HTML on failure.
        """
        try:
            from app.email_engine.css_compiler.compiler import EmailCSSCompiler

            compiler = EmailCSSCompiler()
            optimized = compiler.optimize_css(source_html)
            logger.info(
                "email_engine.css_optimized",
                removed_count=len(optimized.removed_properties),
                conversion_count=len(optimized.conversions),
                optimize_time_ms=optimized.optimize_time_ms,
            )
            return optimized.html
        except Exception as exc:
            logger.warning("email_engine.css_optimize_failed", error=str(exc))
            return source_html
```

### Step 6: Add tests for `optimize_css()`

Add to `app/email_engine/tests/test_css_compiler.py`, in the existing `TestCompiler` class:

```python
    def test_optimize_css_returns_html_with_style_blocks(self) -> None:
        """optimize_css() returns HTML with <style> blocks (not inlined)."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web"])
        result = compiler.optimize_css(STYLE_HTML)
        assert isinstance(result.html, str)
        assert "<style>" in result.html  # CSS stays in <style>, not inlined
        assert result.optimize_time_ms >= 0

    def test_optimize_css_preserves_mso_conditionals(self) -> None:
        """MSO comments are preserved through optimization."""
        compiler = EmailCSSCompiler(target_clients=["outlook_2019"])
        result = compiler.optimize_css(MSO_HTML)
        assert "<!--[if mso]>" in result.html

    def test_optimize_css_resolves_variables(self) -> None:
        """CSS variables are resolved during optimization."""
        html = (
            "<html><head><style>.x { color: var(--brand); }</style></head>"
            "<body><div class='x'>Hi</div></body></html>"
        )
        compiler = EmailCSSCompiler(
            target_clients=["gmail_web"], css_variables={"brand": "#ff0000"}
        )
        result = compiler.optimize_css(html)
        assert "var(--brand)" not in result.html

    def test_optimize_css_no_style_blocks(self) -> None:
        """Handles HTML with no <style> blocks gracefully."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web"])
        result = compiler.optimize_css(MINIMAL_HTML)
        assert isinstance(result.html, str)
        assert result.removed_properties == []
        assert result.conversions == []
```

Add to `TestCompilerWithRemovals`:

```python
    def test_optimize_css_removes_unsupported(self) -> None:
        """optimize_css() removes unsupported properties from <style> blocks."""
        html = (
            "<html><head><style>.x { display: flex; }</style></head>"
            "<body><div class='x'>Hi</div></body></html>"
        )
        compiler = EmailCSSCompiler(target_clients=["outlook_2019"])
        result = compiler.optimize_css(html)
        assert any("display" in p for p in result.removed_properties)
```

Add to `TestCompilerWithConversions`:

```python
    def test_optimize_css_applies_conversions(self) -> None:
        """optimize_css() applies ontology conversions."""
        html = (
            "<html><head><style>.x { display: flex; }</style></head>"
            "<body><div class='x'>Hi</div></body></html>"
        )
        compiler = EmailCSSCompiler(target_clients=["outlook_2019"])
        result = compiler.optimize_css(html)
        assert len(result.conversions) > 0
```

Add a new test class for timing telemetry:

```python
class TestCompilerTelemetry:
    """Tests for per-stage timing telemetry."""

    @pytest.fixture(autouse=True)
    def _mock_ontology(self) -> Generator[None]:
        reg = _mock_registry(support_none=False)
        with (
            patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
            patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
        ):
            yield

    def test_compile_logs_stage_timings(self) -> None:
        """compile() logs per-stage timing metrics."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web"])
        with patch("app.email_engine.css_compiler.compiler.logger") as mock_logger:
            compiler.compile(STYLE_HTML)
            call_kwargs = mock_logger.info.call_args_list[-1].kwargs
            assert "stage_parse_ms" in call_kwargs
            assert "stage_optimize_ms" in call_kwargs
            assert "stage_inline_ms" in call_kwargs
            assert "stage_sanitize_ms" in call_kwargs
```

Add import for `OptimizedCSS` at the top of the test file (line 15):
```python
from app.email_engine.css_compiler.compiler import CompilationResult, EmailCSSCompiler, OptimizedCSS
```

### Step 7: Add test for `MaizzleBuildNode` CSS optimization integration

Check if test file exists at `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py`. If not, create it:

```python
# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportCallIssue=false
"""Tests for MaizzleBuildNode with CSS optimization."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.blueprints.nodes.maizzle_build_node import MaizzleBuildNode
from app.ai.blueprints.protocols import NodeContext


@pytest.fixture
def node() -> MaizzleBuildNode:
    return MaizzleBuildNode()


@pytest.fixture
def context_with_css() -> NodeContext:
    html = (
        "<html><head><style>.hero { color: red; }</style></head>"
        "<body><div class='hero'>Hello</div></body></html>"
    )
    return NodeContext(html=html, metadata={"target_clients": ["gmail_web"]})


class TestMaizzleBuildNodeCSSOptimization:
    @pytest.fixture(autouse=True)
    def _mock_ontology(self) -> Generator[None]:
        from app.email_engine.tests.test_css_compiler import _mock_registry

        reg = _mock_registry(support_none=False)
        with (
            patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
            patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
        ):
            yield

    @pytest.mark.asyncio
    async def test_execute_calls_css_optimization(
        self, node: MaizzleBuildNode, context_with_css: NodeContext
    ) -> None:
        """CSS optimization runs before Maizzle build."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"html": "<html><body>compiled</body></html>"}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await node.execute(context_with_css)

        assert result.status == "success"
        # Verify Maizzle received HTML (optimization ran but is transparent)
        post_call = mock_client.post.call_args
        payload = post_call.kwargs.get("json") or post_call.args[1] if len(post_call.args) > 1 else post_call.kwargs["json"]
        assert "source" in payload

    @pytest.mark.asyncio
    async def test_execute_proceeds_when_css_optimization_fails(
        self, node: MaizzleBuildNode
    ) -> None:
        """If CSS optimization fails, node still sends original HTML to Maizzle."""
        context = NodeContext(html="<html><body>test</body></html>")

        mock_response = AsyncMock()
        mock_response.json.return_value = {"html": "<html><body>compiled</body></html>"}
        mock_response.raise_for_status = AsyncMock()

        with (
            patch(
                "app.ai.blueprints.nodes.maizzle_build_node.EmailCSSCompiler",
                side_effect=RuntimeError("boom"),
            ),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await node.execute(context)

        assert result.status == "success"
```

## Security Checklist

No new endpoints are added. No new attack surface. Scoped review:

- [x] No new HTTP routes — existing auth/rate-limiting unchanged
- [x] `sanitize_html_xss()` still runs on all final output (added explicitly to `MaizzleBuildNode.execute()` and `EmailEngineService.build()/preview()` since they now skip `compile()` stage 7)
- [x] `optimize_css()` intentionally does NOT sanitize (documented — caller responsible after inlining)
- [x] Ontology-driven property elimination is deterministic, no user input reaches query layer
- [x] Error responses via `AppError` hierarchy — no internal type leakage
- [x] CSS optimization failure is caught and logged — falls back to unoptimized HTML, never crashes the build

## Verification

- [ ] `make test` passes — all 546+ existing tests unchanged
- [ ] New `optimize_css()` tests pass (7 new tests)
- [ ] `MaizzleBuildNode` integration tests pass (2 new tests)
- [ ] Telemetry test verifies per-stage timing logs
- [ ] `make lint` passes (ruff format + lint)
- [ ] `make types` passes (mypy + pyright)
- [ ] `make check` all green
- [ ] Manual verification: `EmailCSSCompiler.compile()` still works identically (backward compat)
- [ ] `CompilationResult` contract unchanged — existing `/compile-css` endpoint unaffected
