# Plan: 26.3 Template-Level CSS Precompilation

## Context

Golden templates have static CSS that doesn't change between builds. Running ontology analysis, Lightning CSS minification, and property elimination on the *same* CSS for every build is wasted computation. Pre-compiling amortizes this cost to template registration (once per template version). Build-time CSS work drops to O(token_count) string replacements.

**Key architectural insight:** `GoldenTemplate` is a **frozen dataclass** loaded from filesystem YAML+HTML files (`app/ai/templates/library/`), NOT a SQLAlchemy model. There is no `golden_templates` DB table. The spec's mention of Alembic migrations is adapted here: precompilation state lives in the dataclass (new optional fields with defaults) and in the in-memory registry. Uploaded templates (source="uploaded") registered via `register_uploaded()` also benefit.

## Files to Create/Modify

- `app/ai/templates/models.py` — Add precompilation fields to `GoldenTemplate`
- `app/ai/templates/precompiler.py` — **NEW** `TemplatePrecompiler` class
- `app/ai/templates/registry.py` — Hook precompilation into `load()` and `register_uploaded()`; add `get_build_html()` helper
- `app/ai/blueprints/nodes/maizzle_build_node.py` — Check `skip_css_optimization` metadata flag
- `app/ai/agents/scaffolder/assembler.py` — No changes needed (assembler operates on inline styles / HTML attributes, not `<style>` blocks — works identically on pre-optimized HTML)
- `app/ai/blueprints/nodes/scaffolder_node.py` — Set `skip_css_optimization` metadata when template is pre-optimized
- `app/templates/routes.py` — Add `POST /api/v1/templates/precompile` admin endpoint
- `app/ai/templates/__init__.py` — Re-export new symbols
- `app/ai/templates/tests/test_precompiler.py` — **NEW** unit tests
- `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py` — Add skip-optimization test

## Implementation Steps

### Step 1: Add precompilation fields to `GoldenTemplate`

**File:** `app/ai/templates/models.py`

Add 4 new optional fields to the frozen dataclass. Defaults ensure backward compatibility.

```python
from datetime import datetime

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
```

**Notes:**
- Use `tuple[str, ...]` not `list[str]` for `optimized_for_clients` (frozen dataclass requires hashable fields)
- `optimization_metadata` stores: `removed_properties`, `conversions`, `compile_time_ms`, `original_size`, `optimized_size`
- Import `datetime` from `datetime` module at top of file

### Step 2: Create `TemplatePrecompiler`

**File:** `app/ai/templates/precompiler.py` — **NEW**

```python
"""Pre-compile CSS for golden templates at registration time."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.ai.templates.models import GoldenTemplate
from app.core.config import get_settings
from app.core.logging import get_logger
from app.email_engine.css_compiler.compiler import EmailCSSCompiler

logger = get_logger(__name__)

_DEFAULT_TARGETS = ("gmail", "outlook", "apple_mail", "yahoo_mail")


@dataclass(frozen=True)
class PrecompilationReport:
    """Result of batch precompilation."""

    total: int
    succeeded: int
    failed: int
    total_size_reduction_bytes: int
    avg_compile_time_ms: float
    errors: dict[str, str]  # template_name -> error message


class TemplatePrecompiler:
    """Pre-compiles CSS optimization for golden templates.

    Uses EmailCSSCompiler.optimize_css() (from 26.1) on template HTML.
    Result is stored in GoldenTemplate.optimized_html via dataclasses.replace().
    """

    def __init__(self, target_clients: tuple[str, ...] | None = None) -> None:
        settings = get_settings()
        configured = settings.email_engine.css_compiler_target_clients
        self._target_clients = target_clients or tuple(configured) or _DEFAULT_TARGETS

    def precompile(self, template: GoldenTemplate) -> GoldenTemplate:
        """Pre-compile CSS for a single template.

        Returns a new GoldenTemplate with optimized_html populated.
        Preserves slot placeholders, ESP tokens, builder annotations.
        """
        compiler = EmailCSSCompiler(target_clients=list(self._target_clients))
        start = time.monotonic()

        try:
            optimized = compiler.optimize_css(template.html)
        except Exception:
            logger.warning(
                "templates.precompile_failed",
                template=template.metadata.name,
                exc_info=True,
            )
            raise

        compile_time_ms = round((time.monotonic() - start) * 1000, 2)
        original_size = len(template.html.encode("utf-8"))
        optimized_size = len(optimized.html.encode("utf-8"))

        metadata: dict[str, object] = {
            "removed_properties": optimized.removed_properties,
            "conversions": len(optimized.conversions),
            "compile_time_ms": compile_time_ms,
            "original_size": original_size,
            "optimized_size": optimized_size,
        }

        result = replace(
            template,
            optimized_html=optimized.html,
            optimized_at=datetime.now(timezone.utc),
            optimized_for_clients=self._target_clients,
            optimization_metadata=metadata,
        )

        logger.info(
            "templates.precompiled",
            template=template.metadata.name,
            original_size=original_size,
            optimized_size=optimized_size,
            reduction_bytes=original_size - optimized_size,
            compile_time_ms=compile_time_ms,
        )

        return result

    def precompile_all(
        self,
        templates: dict[str, GoldenTemplate],
    ) -> tuple[dict[str, GoldenTemplate], PrecompilationReport]:
        """Batch precompile all templates.

        Returns updated templates dict and a report.
        """
        succeeded = 0
        failed = 0
        total_reduction = 0
        total_time = 0.0
        errors: dict[str, str] = {}
        updated: dict[str, GoldenTemplate] = {}

        for name, template in templates.items():
            try:
                compiled = self.precompile(template)
                updated[name] = compiled
                succeeded += 1
                meta = compiled.optimization_metadata
                total_reduction += int(meta.get("original_size", 0)) - int(
                    meta.get("optimized_size", 0)
                )
                total_time += float(meta.get("compile_time_ms", 0))
            except Exception as exc:
                updated[name] = template  # keep original
                failed += 1
                errors[name] = str(exc)

        total = succeeded + failed
        report = PrecompilationReport(
            total=total,
            succeeded=succeeded,
            failed=failed,
            total_size_reduction_bytes=total_reduction,
            avg_compile_time_ms=round(total_time / max(succeeded, 1), 2),
            errors=errors,
        )

        logger.info(
            "templates.precompile_all_completed",
            total=total,
            succeeded=succeeded,
            failed=failed,
            total_reduction_bytes=total_reduction,
        )

        return updated, report

    @staticmethod
    def is_stale(template: GoldenTemplate, target_clients: tuple[str, ...]) -> bool:
        """Check if precompiled CSS is stale.

        Returns True if:
        - optimized_at is None (never precompiled)
        - optimized_for_clients differs from target_clients
        """
        if template.optimized_at is None:
            return True
        if set(template.optimized_for_clients) != set(target_clients):
            return True
        return False
```

**Notes:**
- `precompile()` is synchronous — `optimize_css()` is CPU-bound, not async
- No `asyncio.create_task` for fire-and-forget; synchronous precompilation during `load()` is fine since it runs once at startup
- `precompile_all()` returns updated dict + report, caller replaces `_templates`
- `is_stale()` is a staticmethod — no side effects

### Step 3: Hook precompilation into `TemplateRegistry`

**File:** `app/ai/templates/registry.py`

**3a.** Add import at top:

```python
from app.ai.templates.precompiler import TemplatePrecompiler
```

**3b.** Add precompilation at end of `load()` method (after line 70, after `self._loaded = True`):

```python
    def load(self) -> None:
        """Load all templates from library/ directory."""
        # ... existing code through self._loaded = True ...

        # Pre-compile CSS for all templates (26.3)
        try:
            precompiler = TemplatePrecompiler()
            self._templates, report = precompiler.precompile_all(self._templates)
            logger.info(
                "templates.registry_precompiled",
                succeeded=report.succeeded,
                failed=report.failed,
                total_reduction_bytes=report.total_size_reduction_bytes,
            )
        except Exception:
            logger.warning("templates.registry_precompile_failed", exc_info=True)
            # Non-fatal — templates work without precompilation

        logger.info("templates.registry_loaded", count=len(self._templates))
```

Move the existing `logger.info("templates.registry_loaded", ...)` line to AFTER the precompilation block.

**3c.** Add `get_build_html()` method to `TemplateRegistry`:

```python
    def get_build_html(self, template: GoldenTemplate) -> tuple[str, bool]:
        """Return the best HTML for building.

        Returns (html, is_preoptimized) tuple.
        If optimized_html is available and not stale, returns it.
        Otherwise returns raw html.
        """
        if template.optimized_html is not None:
            return template.optimized_html, True
        return template.html, False
```

**3d.** Add precompilation to `register_uploaded()` (after line 199):

```python
    def register_uploaded(self, template: GoldenTemplate) -> None:
        # ... existing validation ...

        # Pre-compile CSS for uploaded template
        try:
            precompiler = TemplatePrecompiler()
            template = precompiler.precompile(template)
        except Exception:
            logger.warning(
                "templates.uploaded_precompile_failed",
                name=template.metadata.name,
                exc_info=True,
            )
            # Non-fatal — template works without precompilation

        self._templates[name] = template
        logger.info("templates.uploaded_registered", name=name)
```

**3e.** Add `precompile_all()` method to `TemplateRegistry` (for the admin endpoint):

```python
    def precompile_all(
        self,
        target_clients: tuple[str, ...] | None = None,
    ) -> PrecompilationReport:
        """Re-precompile all templates. Used by admin endpoint."""
        self._ensure_loaded()
        precompiler = TemplatePrecompiler(target_clients=target_clients)
        self._templates, report = precompiler.precompile_all(self._templates)
        return report
```

Import `PrecompilationReport` in the imports.

### Step 4: Set `skip_css_optimization` flag in blueprint pipeline

**File:** `app/ai/blueprints/nodes/scaffolder_node.py`

Find where the scaffolder node sets `context.metadata` before passing to MaizzleBuildNode. The flow is: ScaffolderNode produces HTML → engine passes to MaizzleBuildNode. The `skip_css_optimization` flag needs to be set in `metadata` when the template was pre-optimized.

First, read the scaffolder node to understand how metadata flows. The flag should be set by the engine when building context for MaizzleBuildNode, based on whether the assembler used pre-optimized HTML.

**Approach:** Add a metadata key `css_preoptimized` to the `EmailBuildPlan` or set it in the `NodeResult` metadata from the scaffolder node. The simplest approach: check in `MaizzleBuildNode.execute()` whether `context.metadata.get("skip_css_optimization")` is True.

The flag needs to be set somewhere upstream. Two options:
1. ScaffolderNode sets it after assembly
2. BlueprintEngine sets it when building MaizzleBuildNode context

**Simplest:** ScaffolderNode/assembler can detect this and include it in the result metadata. Since `TemplateAssembler.assemble()` resolves the template, it knows if `optimized_html` was used.

**Modified approach — in `TemplateAssembler.assemble()`:**

Add to assembler to track whether preoptimized HTML was used, and expose it:

```python
class TemplateAssembler:
    def __init__(self, ...) -> None:
        # ... existing ...
        self._used_preoptimized = False

    def assemble(self, plan: EmailBuildPlan) -> str:
        template = self._resolve_template(plan)

        # Use pre-optimized HTML if available (26.3)
        build_html, self._used_preoptimized = self._registry.get_build_html(template)

        # Step 1: Fill slots — use build_html as starting point
        fills = {sf.slot_id: sf.content for sf in plan.slot_fills}
        html = self._registry.fill_slots(
            # Create a template view with the build HTML for slot filling
            replace(template, html=build_html) if self._used_preoptimized else template,
            fills,
        )
        # ... rest of assembly steps unchanged ...

    @property
    def used_preoptimized(self) -> bool:
        """Whether the last assemble() call used pre-optimized HTML."""
        return self._used_preoptimized
```

Wait — `GoldenTemplate` is frozen, so `replace(template, html=build_html)` would work but `fill_slots` only uses `template.slots` and `template.html`. We need `fill_slots` to operate on the pre-optimized HTML instead.

**Better approach:** `fill_slots` takes a `GoldenTemplate` and uses `template.html`. So we pass a replaced template:

```python
from dataclasses import replace as dc_replace

# In assemble():
template = self._resolve_template(plan)

# Use pre-optimized HTML if available (26.3)
if template.optimized_html is not None:
    template = dc_replace(template, html=template.optimized_html)
    self._used_preoptimized = True
else:
    self._used_preoptimized = False

# Step 1: Fill slots (now uses pre-optimized HTML if available)
fills = {sf.slot_id: sf.content for sf in plan.slot_fills}
html = self._registry.fill_slots(template, fills)
```

This is clean — `fill_slots` uses regex on `template.html`, which is now the optimized version.

**File:** `app/ai/agents/scaffolder/assembler.py`

Add at top:
```python
from dataclasses import replace as dc_replace
```

Modify `assemble()` method — insert after `template = self._resolve_template(plan)` (line 45) and before Step 1:

```python
        # Use pre-optimized HTML if available (26.3)
        if template.optimized_html is not None:
            template = dc_replace(template, html=template.optimized_html)
            self._used_preoptimized = True
        else:
            self._used_preoptimized = False
```

Add `self._used_preoptimized = False` to `__init__`.

Add property:
```python
    @property
    def used_preoptimized(self) -> bool:
        """Whether the last assemble() used pre-optimized template HTML."""
        return self._used_preoptimized
```

### Step 5: Skip CSS optimization in MaizzleBuildNode

**File:** `app/ai/blueprints/nodes/maizzle_build_node.py`

Modify `execute()` to check `context.metadata.get("skip_css_optimization")`:

```python
    async def execute(self, context: NodeContext) -> NodeResult:
        """Optimize CSS, POST to Maizzle builder, sanitize output."""
        if not context.html:
            return NodeResult(status="failed", error="No HTML to build")

        settings = get_settings()
        source_html = context.html

        # Skip CSS optimization if template was pre-optimized (26.3)
        skip_css = bool(context.metadata.get("skip_css_optimization"))

        if not skip_css:
            # CSS optimization: run ontology-driven stages 1-5 before Maizzle inlines
            raw_clients = context.metadata.get("target_clients")
            target_clients_list: list[str] | None = None
            if isinstance(raw_clients, list):
                target_clients_list = list(cast("list[str]", raw_clients))

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
                logger.warning("blueprint.maizzle_build.css_optimize_failed", error=str(exc))
        else:
            logger.info("blueprint.maizzle_build.css_skipped_preoptimized")

        # ... rest unchanged (Maizzle POST, sanitize) ...
```

### Step 6: Set `skip_css_optimization` flag from ScaffolderNode

**File:** Need to check `app/ai/blueprints/nodes/scaffolder_node.py` to see where to inject the flag.

The scaffolder node calls the pipeline which calls the assembler. After assembly, the scaffolder node returns a `NodeResult` with HTML. The *next* node (MaizzleBuildNode) receives a `NodeContext` built by the engine.

The flag should flow through the engine. The simplest path: set it on the `NodeResult.details` or via a custom metadata field. Actually, looking at the `NodeContext`, `metadata` is populated by `BlueprintEngine._build_node_context()`.

**Approach:** The ScaffolderNode should set a result metadata indicating pre-optimization was used. Then the engine propagates it to the next node's context.

Actually, the simplest approach that doesn't require engine changes: **set the flag on the NodeResult metadata** from the ScaffolderNode, and have the engine pass NodeResult metadata forward. But we need to verify how the engine works.

**Alternative (simpler, self-contained):** Since the MaizzleBuildNode has access to `context.metadata`, and the engine builds context from the previous node's result, we can look at how metadata propagates.

**Most pragmatic approach:** Set `skip_css_optimization` directly on the `NodeResult` from ScaffolderNode, and check if the engine copies result metadata to the next context. If not, the simplest change is to add it to the engine's context builder.

**However**, to keep changes minimal and avoid modifying the engine, use a different strategy:

**In `MaizzleBuildNode.execute()`**, instead of relying on upstream metadata, detect whether the HTML has already been optimized. We can use a lightweight HTML comment marker:

**In `TemplatePrecompiler.precompile()`**, inject a marker comment in the optimized HTML:

```python
_PREOPTIMIZED_MARKER = "<!-- css-preoptimized -->"

# After optimize_css():
optimized_html = _PREOPTIMIZED_MARKER + optimized.html
```

**In `MaizzleBuildNode.execute()`**, check for the marker:

```python
_PREOPTIMIZED_MARKER = "<!-- css-preoptimized -->"

skip_css = _PREOPTIMIZED_MARKER in source_html
if skip_css:
    source_html = source_html.replace(_PREOPTIMIZED_MARKER, "", 1)
```

This is self-contained, doesn't require engine changes, and the marker is stripped before the Maizzle build.

**Decision:** Use the marker approach. It's the simplest, most reliable, and doesn't couple to engine internals.

**Updated Step 2** — In `TemplatePrecompiler.precompile()`, prepend marker to optimized HTML:

```python
CSS_PREOPTIMIZED_MARKER = "<!-- css-preoptimized -->"

# In precompile(), after optimize_css():
optimized_html = CSS_PREOPTIMIZED_MARKER + optimized.html
```

**Updated Step 5** — In `MaizzleBuildNode.execute()`:

```python
from app.ai.templates.precompiler import CSS_PREOPTIMIZED_MARKER

# After source_html = context.html:
skip_css = CSS_PREOPTIMIZED_MARKER in source_html
if skip_css:
    source_html = source_html.replace(CSS_PREOPTIMIZED_MARKER, "", 1)
```

This removes the need for Step 6 entirely and avoids modifying ScaffolderNode.

### Step 7: Add admin precompile endpoint

**File:** `app/templates/routes.py`

Add at the end of the file:

```python
from app.ai.templates import get_template_registry
from app.ai.templates.precompiler import PrecompilationReport


@router.post(
    "/templates/precompile",
    response_model=dict[str, object],
    status_code=200,
)
@limiter.limit("2/minute")
async def precompile_templates(
    request: Request,
    current_user: User = Depends(require_role("admin")),  # noqa: B008
) -> dict[str, object]:
    """Trigger batch precompilation of all golden templates. Admin only."""
    registry = get_template_registry()
    report = registry.precompile_all()

    logger.info(
        "templates.precompile_endpoint",
        user_id=current_user.id,
        total=report.total,
        succeeded=report.succeeded,
        failed=report.failed,
    )

    return {
        "total": report.total,
        "succeeded": report.succeeded,
        "failed": report.failed,
        "total_size_reduction_bytes": report.total_size_reduction_bytes,
        "avg_compile_time_ms": report.avg_compile_time_ms,
        "errors": report.errors,
    }
```

**Imports needed at top:** Add `get_template_registry`, `PrecompilationReport`, `limiter`, `require_role`, `User` (check existing imports — `require_role` and `User` may already be imported).

Check existing imports in routes.py — `require_role` is already used for `create_template`. Add `get_template_registry` and the limiter import.

### Step 8: Update `__init__.py` exports

**File:** `app/ai/templates/__init__.py`

Add to existing exports:

```python
from app.ai.templates.precompiler import (
    CSS_PREOPTIMIZED_MARKER,
    PrecompilationReport,
    TemplatePrecompiler,
)
```

### Step 9: Write tests

**File:** `app/ai/templates/tests/test_precompiler.py` — **NEW**

```python
"""Tests for TemplatePrecompiler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ai.templates.models import GoldenTemplate, TemplateMetadata, TemplateSlot
from app.ai.templates.precompiler import (
    CSS_PREOPTIMIZED_MARKER,
    TemplatePrecompiler,
)


def _make_template(name: str = "test", html: str = "") -> GoldenTemplate:
    """Create a minimal GoldenTemplate for testing."""
    return GoldenTemplate(
        metadata=TemplateMetadata(
            name=name,
            display_name="Test",
            layout_type="newsletter",
            column_count=1,
            has_hero_image=False,
            has_navigation=False,
            has_social_links=False,
            sections=(),
            ideal_for=(),
            description="test template",
        ),
        html=html or "<html><head><style>.hero{color:red}</style></head><body>test</body></html>",
        slots=(),
    )


@pytest.fixture
def _mock_ontology():
    """Mock ontology for CSS compiler."""
    from app.email_engine.tests.test_css_compiler import _mock_registry

    reg = _mock_registry(support_none=False)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield


class TestTemplatePrecompiler:
    def test_precompile_populates_optimized_html(self, _mock_ontology) -> None:
        template = _make_template()
        precompiler = TemplatePrecompiler(target_clients=("gmail",))
        result = precompiler.precompile(template)

        assert result.optimized_html is not None
        assert CSS_PREOPTIMIZED_MARKER in result.optimized_html
        assert result.optimized_at is not None
        assert result.optimized_for_clients == ("gmail",)
        assert result.optimization_metadata["original_size"] > 0

    def test_precompile_preserves_original_fields(self, _mock_ontology) -> None:
        template = _make_template(name="promo")
        precompiler = TemplatePrecompiler(target_clients=("gmail",))
        result = precompiler.precompile(template)

        assert result.metadata.name == "promo"
        assert result.slots == ()
        assert result.html == template.html  # original HTML unchanged

    def test_is_stale_no_optimization(self) -> None:
        template = _make_template()
        assert TemplatePrecompiler.is_stale(template, ("gmail",)) is True

    def test_is_stale_different_clients(self, _mock_ontology) -> None:
        precompiler = TemplatePrecompiler(target_clients=("gmail",))
        result = precompiler.precompile(_make_template())
        assert TemplatePrecompiler.is_stale(result, ("outlook",)) is True
        assert TemplatePrecompiler.is_stale(result, ("gmail",)) is False

    def test_precompile_all_reports(self, _mock_ontology) -> None:
        templates = {
            "a": _make_template("a"),
            "b": _make_template("b"),
        }
        precompiler = TemplatePrecompiler(target_clients=("gmail",))
        updated, report = precompiler.precompile_all(templates)

        assert report.total == 2
        assert report.succeeded == 2
        assert report.failed == 0
        assert updated["a"].optimized_html is not None
        assert updated["b"].optimized_html is not None

    def test_precompile_all_handles_failure(self) -> None:
        templates = {"fail": _make_template("fail")}
        # No ontology mock → compile will fail
        with patch(
            "app.email_engine.css_compiler.compiler.load_ontology",
            side_effect=RuntimeError("no ontology"),
        ):
            precompiler = TemplatePrecompiler(target_clients=("gmail",))
            updated, report = precompiler.precompile_all(templates)

        assert report.failed == 1
        assert "fail" in report.errors
        assert updated["fail"].optimized_html is None  # kept original
```

**File:** `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py`

Add test for skip behavior:

```python
    @pytest.mark.asyncio
    async def test_execute_skips_css_when_preoptimized(
        self, node: MaizzleBuildNode
    ) -> None:
        """CSS optimization is skipped when HTML contains preoptimized marker."""
        from app.ai.templates.precompiler import CSS_PREOPTIMIZED_MARKER

        html = (
            CSS_PREOPTIMIZED_MARKER
            + "<html><head><style>.hero{color:red}</style></head>"
            + "<body><div class='hero'>Hello</div></body></html>"
        )
        context = NodeContext(html=html, metadata={})

        with (
            patch(
                "app.email_engine.css_compiler.compiler.EmailCSSCompiler"
            ) as mock_compiler_cls,
            _patch_httpx(),
        ):
            result = await node.execute(context)

        assert result.status == "success"
        # CSS compiler should NOT have been instantiated
        mock_compiler_cls.assert_not_called()
```

### Step 10: Verify assembler compatibility

The `TemplateAssembler.assemble()` uses `template.html` for slot filling (Step 1), then performs string replacements for palette, fonts, dark mode, sections, etc. (Steps 2-11). These all operate on inline styles and HTML attributes, not on raw `<style>` blocks.

When `optimized_html` is used:
- `<style>` blocks are already optimized (unsupported properties removed, conversions applied, minified)
- Slot filling works identically (uses `data-slot` attributes)
- Palette replacement works (replaces hex colors in `style=` attributes and `<style>` blocks)
- Font replacement works (replaces font-family strings)

**Key:** The assembler replaces `template.html` with `template.optimized_html` via `dc_replace()` before slot filling. All 11 steps operate on the resulting HTML string without any awareness of whether CSS was pre-optimized.

**No changes needed in assembler steps 1-11.** Only the initial template resolution adds the swap logic.

## Security Checklist

### `POST /api/v1/templates/precompile` endpoint:
- [x] Auth: `require_role("admin")` — admin only
- [x] Rate limiting: `@limiter.limit("2/minute")` — prevent abuse
- [x] No user-facing inputs — operates on internal template registry
- [x] Pre-compiled HTML goes through same `sanitize_html_xss()` pipeline (in MaizzleBuildNode)
- [x] No project-scoped data — global template registry
- [x] Error responses: returns structured report, no internal type leakage
- [x] No new secrets or credentials
- [x] No SQL queries — operates on in-memory registry

### General:
- [x] `CSS_PREOPTIMIZED_MARKER` is an HTML comment — safe, cannot cause XSS
- [x] Marker is stripped before Maizzle build — doesn't appear in final output
- [x] Pre-compilation failures are non-fatal — pipeline falls back to runtime optimization
- [x] No user input reaches the precompilation path

## Verification

- [ ] `make check` passes (includes lint, types, tests, frontend, security-check)
- [ ] Register a new template → `optimized_html` populated (check in test)
- [ ] Build email from pre-optimized template → identical output to non-optimized path (diff test)
- [ ] Build time measurably faster — MaizzleBuildNode skips CSS optimization stage
- [ ] Modify template HTML → `is_stale()` returns True
- [ ] `POST /api/v1/templates/precompile` returns report with all templates succeeded
- [ ] Pre-compilation failure → graceful fallback (template works without optimization)
- [ ] `CSS_PREOPTIMIZED_MARKER` stripped before Maizzle build (not in final HTML)
- [ ] New endpoint has auth (admin) + rate limiting
- [ ] Error responses don't leak internal types

## Implementation Order

1. `models.py` — Add fields (all downstream depends on this)
2. `precompiler.py` — NEW file, the core logic
3. `registry.py` — Hook precompilation into load/register
4. `assembler.py` — Swap to pre-optimized HTML when available
5. `maizzle_build_node.py` — Skip CSS optimization on marker
6. `routes.py` — Admin endpoint
7. `__init__.py` — Exports
8. Tests — `test_precompiler.py` + update `test_maizzle_build_node.py`
