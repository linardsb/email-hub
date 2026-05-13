# Plan: Phase 26.5 — Tests & Documentation

## Context
Phase 26 introduced a CSS optimization pipeline (26.1 `optimize_css`, 26.2 CSS audit QA check, 26.3 template precompilation, 26.4 consolidated sidecar pipeline). Existing tests are thin — the task requires comprehensive coverage, pipeline equivalence regression tests, and performance benchmarks. Current state:
- `app/email_engine/tests/test_css_compiler.py` — 32 tests (conversions, inliner, compiler, service, routes)
- `app/qa_engine/tests/test_css_audit.py` — 7 tests (basic coverage)
- `app/ai/templates/tests/test_precompiler.py` — 7 tests (basic precompiler)
- `app/ai/blueprints/nodes/tests/test_maizzle_build_node.py` — 7 tests (node execution)
- `services/maizzle-builder/postcss-email-optimize.test.js` — 5 tests (basic PostCSS plugin)
- No pipeline equivalence tests exist
- No performance benchmarks exist
- No `make bench` target exists

## Files to Create/Modify

### New Files
1. `app/email_engine/tests/test_optimize_css.py` — 15+ tests for `optimize_css()` specifically
2. `app/email_engine/tests/test_pipeline_equivalence.py` — regression suite comparing `compile()` vs `optimize_css()` paths
3. `app/email_engine/tests/test_performance_benchmark.py` — benchmark suite with `@pytest.mark.benchmark`
4. `app/email_engine/tests/conftest.py` — shared fixtures for email engine tests (mock registries, golden HTML templates)

### Modified Files
5. `app/qa_engine/tests/test_css_audit.py` — expand from 7 to 15+ tests
6. `app/ai/templates/tests/test_precompiler.py` — expand from 7 to 15+ tests
7. `services/maizzle-builder/postcss-email-optimize.test.js` — expand from 5 to 15+ tests
8. `Makefile` — add `bench` target

## Implementation Steps

### Step 1: Create shared test fixtures (`app/email_engine/tests/conftest.py`)

Uses the **real golden templates** from `app/ai/templates/library/` (15 production email templates) and **real component HTML** from `app/components/data/seeds.py` (21 seeded components including email-shell with full MSO/dark mode CSS) instead of fabricating synthetic HTML.

```python
"""Shared fixtures for email engine tests."""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.knowledge.ontology.types import SupportLevel

# ── Real golden templates from the template library ──

LIBRARY_DIR = Path(__file__).resolve().parent.parent.parent / "ai" / "templates" / "library"


def load_golden_templates() -> dict[str, str]:
    """Load all golden template HTML files from the library directory."""
    templates: dict[str, str] = {}
    for html_file in sorted(LIBRARY_DIR.glob("*.html")):
        templates[html_file.stem] = html_file.read_text()
    return templates


# 5 representative templates covering different archetypes:
#   simple (minimal_text), complex multi-column (newsletter_2col),
#   dark-mode-heavy (promotional_hero), responsive (promotional_grid),
#   MSO-conditional-heavy (transactional_receipt)
REPRESENTATIVE_TEMPLATE_NAMES = [
    "minimal_text",
    "newsletter_2col",
    "promotional_hero",
    "promotional_grid",
    "transactional_receipt",
]


# ── Real component HTML from seeded components ──


def load_component_html() -> dict[str, str]:
    """Load component HTML from seed data.

    Returns dict keyed by slug: email-shell, email-header, email-footer,
    cta-button, hero-block, product-card, spacer, social-icons, etc.
    """
    from app.components.data.seeds import COMPONENT_SEEDS

    return {seed["slug"]: seed["html_source"] for seed in COMPONENT_SEEDS}


# Key components for CSS pipeline testing (7 of 21, covering all archetypes):
#   email-shell (full HTML doc wrapper — all CSS, dark mode, responsive, MSO),
#   hero-block (background images, overlay, complex layout),
#   cta-button (VML button with ghost variant),
#   column-layout-3 (multi-column with MSO table wrappers),
#   article-card (image + text + CTA composite),
#   image-grid (responsive grid layout),
#   navigation-bar (links with hover states)
REPRESENTATIVE_COMPONENT_SLUGS = [
    "email-shell",
    "hero-block",
    "cta-button",
    "column-layout-3",
    "article-card",
    "image-grid",
    "navigation-bar",
]


@pytest.fixture(scope="session")
def golden_templates() -> dict[str, str]:
    """All 15 golden template HTMLs keyed by name."""
    return load_golden_templates()


@pytest.fixture(scope="session")
def representative_templates() -> dict[str, str]:
    """5 representative golden templates for equivalence/benchmark tests."""
    all_templates = load_golden_templates()
    return {k: all_templates[k] for k in REPRESENTATIVE_TEMPLATE_NAMES if k in all_templates}


@pytest.fixture(scope="session")
def component_html() -> dict[str, str]:
    """All 21 seeded component HTMLs keyed by slug."""
    return load_component_html()


@pytest.fixture(scope="session")
def representative_components() -> dict[str, str]:
    """7 representative component HTMLs for CSS pipeline tests."""
    all_components = load_component_html()
    return {k: all_components[k] for k in REPRESENTATIVE_COMPONENT_SLUGS if k in all_components}


# ── Mock ontology helpers ──


def make_mock_registry(
    *,
    support_none: bool = False,
    has_fallback: bool = False,
) -> MagicMock:
    """Create a mock OntologyRegistry for testing."""
    reg = MagicMock()
    prop = MagicMock()
    prop.id = "display_flex"
    prop.property_name = "display"
    prop.value = "flex"
    reg.find_property_by_name.return_value = prop

    if support_none:
        reg.get_support.return_value = SupportLevel.NONE
    else:
        reg.get_support.return_value = SupportLevel.FULL

    if has_fallback:
        fb = MagicMock()
        fb.target_property_id = "display_block"
        fb.client_ids = []
        fb.technique = "Use display:block as fallback"
        target_prop = MagicMock()
        target_prop.property_name = "display"
        target_prop.value = "block"
        reg.get_property.return_value = target_prop
        reg.fallbacks_for.return_value = [fb]
    else:
        reg.fallbacks_for.return_value = []

    return reg


@pytest.fixture
def mock_ontology_supported() -> Generator[MagicMock]:
    """Mock ontology where all properties are supported."""
    reg = make_mock_registry(support_none=False)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield reg


@pytest.fixture
def mock_ontology_unsupported() -> Generator[MagicMock]:
    """Mock ontology where all properties are unsupported (no fallback)."""
    reg = make_mock_registry(support_none=True, has_fallback=False)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield reg


@pytest.fixture
def mock_ontology_with_fallback() -> Generator[MagicMock]:
    """Mock ontology where properties are unsupported but have fallbacks."""
    reg = make_mock_registry(support_none=True, has_fallback=True)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield reg
```

### Step 2: Create `test_optimize_css.py` (15+ tests)

File: `app/email_engine/tests/test_optimize_css.py`

```python
"""Tests for optimize_css() — stages 1-5 only (no inlining)."""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.email_engine.css_compiler.compiler import EmailCSSCompiler, OptimizedCSS


class TestOptimizeCSSStructure:
    """Tests for OptimizedCSS result structure."""

    def test_returns_optimized_css_dataclass(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head><style>.x{color:red}</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert isinstance(result, OptimizedCSS)
        assert isinstance(result.html, str)
        assert isinstance(result.removed_properties, list)
        assert isinstance(result.conversions, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.optimize_time_ms, float)

    def test_html_contains_style_blocks_not_inlined(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head><style>.x{color:red}</style></head><body><div class='x'>Hi</div></body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert "<style>" in result.html

    def test_optimize_time_is_nonnegative(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert result.optimize_time_ms >= 0


class TestOptimizeCSSRemovals:
    """Tests for ontology-driven property removal."""

    def test_removes_unsupported_property(self, mock_ontology_unsupported: MagicMock) -> None:
        html = "<html><head><style>.x { display: flex; }</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        assert any("display" in p for p in result.removed_properties)

    def test_removes_from_inline_styles(self, mock_ontology_unsupported: MagicMock) -> None:
        html = '<html><head></head><body><div style="display: flex">Hi</div></body></html>'
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        assert len(result.removed_properties) > 0

    def test_does_not_remove_supported_property(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head><style>.x { color: red; }</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert result.removed_properties == []


class TestOptimizeCSSConversions:
    """Tests for fallback conversions."""

    def test_applies_fallback_conversion(self, mock_ontology_with_fallback: MagicMock) -> None:
        html = "<html><head><style>.x { display: flex; }</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        assert len(result.conversions) > 0
        assert result.conversions[0].replacement_property == "display"
        assert result.conversions[0].replacement_value == "block"

    def test_conversion_records_affected_clients(self, mock_ontology_with_fallback: MagicMock) -> None:
        html = "<html><head><style>.x { display: flex; }</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        assert "outlook_2019" in result.conversions[0].affected_clients


class TestOptimizeCSSVariables:
    """Tests for CSS variable resolution."""

    def test_resolves_variables_with_values(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head><style>.x{color:var(--brand)}</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(
            target_clients=["gmail_web"], css_variables={"brand": "#ff0000"}
        ).optimize_css(html)
        assert "var(--brand)" not in result.html

    def test_preserves_var_with_fallback_when_no_variable(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head><style>.x{color:var(--missing, blue)}</style></head><body>Hi</body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert "blue" in result.html


class TestOptimizeCSSPreservation:
    """Tests for things that must be preserved through optimization."""

    def test_preserves_mso_conditional_comments(self, mock_ontology_supported: MagicMock) -> None:
        html = (
            "<html><head></head><body>"
            "<!--[if mso]><table><tr><td>MSO</td></tr></table><![endif]-->"
            "<p>Normal</p></body></html>"
        )
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        assert "<!--[if mso]>" in result.html
        assert "<![endif]-->" in result.html

    def test_preserves_media_queries(self, mock_ontology_supported: MagicMock) -> None:
        html = (
            "<html><head><style>"
            "@media (max-width:480px){.x{font-size:14px}}"
            "</style></head><body>Hi</body></html>"
        )
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert "@media" in result.html

    def test_preserves_slot_placeholders(self, mock_ontology_supported: MagicMock) -> None:
        html = (
            "<html><head><style>.x{color:red}</style></head><body>"
            "{{headline_slot}}<p>Content</p>{{footer_slot}}</body></html>"
        )
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert "{{headline_slot}}" in result.html
        assert "{{footer_slot}}" in result.html

    def test_preserves_esp_tokens(self, mock_ontology_supported: MagicMock) -> None:
        html = (
            "<html><head><style>.x{color:red}</style></head><body>"
            "<p>Hello {{ first_name | default: 'Friend' }}</p>"
            "<p>{% if vip %}VIP content{% endif %}</p></body></html>"
        )
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert "{{ first_name" in result.html
        assert "{% if vip %}" in result.html


class TestOptimizeCSSEdgeCases:
    """Edge cases and multi-block handling."""

    def test_removes_empty_style_blocks(self, mock_ontology_unsupported: MagicMock) -> None:
        html = (
            "<html><head><style>.x { display: flex; }</style></head>"
            "<body>Hi</body></html>"
        )
        result = EmailCSSCompiler(target_clients=["outlook_2019"]).optimize_css(html)
        # After removing the only property, the style block content should be empty
        # The compiler filters out empty blocks in optimize_css
        assert result.removed_properties  # At least one removed

    def test_handles_multiple_style_blocks_independently(self, mock_ontology_supported: MagicMock) -> None:
        html = (
            "<html><head>"
            "<style>.a{color:red}</style>"
            "<style>.b{font-size:14px}</style>"
            "<style>.c{margin:0}</style>"
            "</head><body>Hi</body></html>"
        )
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert isinstance(result.html, str)
        assert result.html.count("<style>") >= 1  # At least one style block preserved

    def test_handles_no_style_blocks(self, mock_ontology_supported: MagicMock) -> None:
        html = "<html><head></head><body><p>No styles</p></body></html>"
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css(html)
        assert result.removed_properties == []
        assert result.conversions == []

    def test_handles_empty_html(self, mock_ontology_supported: MagicMock) -> None:
        result = EmailCSSCompiler(target_clients=["gmail_web"]).optimize_css("<html><body></body></html>")
        assert isinstance(result, OptimizedCSS)
        assert result.optimize_time_ms >= 0
```

### Step 3: Expand `test_css_audit.py` (add 8+ new tests)

Add to the existing `TestCSSAuditCheck` class in `app/qa_engine/tests/test_css_audit.py`:

New tests to add:
1. `test_severity_error_for_removed_in_tier1` — Supply `OptimizedCSS` with `removed_properties=["flex"]`, mock ontology so `flex` is NONE in `gmail-web` with no fallback. Assert `severity == "error"` and `details["error_count"] > 0`.
2. `test_severity_warning_for_converted` — Supply `OptimizedCSS` with a `CSSConversion`, assert `severity == "warning"` and `details["warning_count"] > 0` (when no errors).
3. `test_severity_info_for_partial_support` — Mock ontology with PARTIAL support, assert severity is "info".
4. `test_conversion_details_populated` — Supply `OptimizedCSS` with conversions, verify `details["conversions"]` list has correct structure (original_property, replacement_property, etc.).
5. `test_empty_html_graceful` — Pass completely empty string, assert no crash, passed=True.
6. `test_per_client_coverage_score_calculation` — Verify `client_coverage_score` dict has entries for each target client, values are 0-100.
7. `test_overall_coverage_score_is_average` — Supply known matrix, verify `overall_coverage_score` equals average of per-client scores.
8. `test_integration_with_qa_service_run_checks` — Verify css_audit is included in `QAEngineService.run_checks()` results (check name present in 14-check output). Reuse existing `test_run_checks_returns_14_results` pattern but verify css_audit specifically.

Each test follows the existing pattern: use `CSSAuditCheck()` fixture, supply `OptimizedCSS` or `QACheckConfig`, assert on `QACheckResult` fields.

### Step 4: Expand `test_precompiler.py` (add 8+ new tests)

Add to `app/ai/templates/tests/test_precompiler.py`:

1. `test_precompile_populates_metadata_fields` — Verify `optimization_metadata` contains all expected keys: `removed_properties`, `conversions`, `compile_time_ms`, `original_size`, `optimized_size`.
2. `test_precompile_metadata_sizes_are_correct` — Verify `original_size` matches `len(template.html.encode("utf-8"))`.
3. `test_is_stale_returns_false_same_clients_different_order` — Precompile with `("gmail", "outlook")`, check `is_stale` with `("outlook", "gmail")` returns False (set comparison).
4. `test_precompile_preserves_slot_markers` — Template HTML with `data-slot="headline"` attribute, verify it appears in `optimized_html`. (Real templates use `data-slot` attributes, not `{{ }}` placeholders.)
5. `test_precompile_preserves_mso_conditionals` — Template HTML with `<!--[if mso]>...<![endif]-->`, verify MSO blocks preserved in `optimized_html`.
6. `test_precompile_all_returns_correct_report_on_partial_failure` — One template succeeds, one fails (mock ontology error for second). Verify `report.succeeded == 1`, `report.failed == 1`, errors dict has failing template name.
7. `test_precompile_all_keeps_original_on_failure` — Verify the failing template in `updated` dict still has `optimized_html is None`.
8. `test_precompile_marker_in_html` — Verify `CSS_PREOPTIMIZED_MARKER` is prepended to `optimized_html`.
9. `test_precompile_with_build_node_skips_css` — Verify a `MaizzleBuildNode` seeing the marker in HTML does NOT send `target_clients` to sidecar (this is a cross-module integration test; mock httpx as done in existing maizzle node tests).
10. `test_precompile_optimized_at_is_utc` — Verify `optimized_at` has UTC timezone.

### Step 5: Create `test_pipeline_equivalence.py` (regression suite)

File: `app/email_engine/tests/test_pipeline_equivalence.py`

Uses the **real golden templates** from `app/ai/templates/library/` via the `representative_templates` session fixture (5 templates: `minimal_text`, `newsletter_2col`, `promotional_hero`, `promotional_grid`, `transactional_receipt`).

```python
"""Pipeline equivalence regression tests.

For each golden template from the template library, build via:
1. Old path: EmailCSSCompiler.compile() (stages 1-7)
2. New path: EmailCSSCompiler.optimize_css() (stages 1-5 only)

Verify the optimization stages produce consistent results — same properties
removed, same conversions applied, same structural elements preserved.
"""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from app.email_engine.css_compiler.compiler import EmailCSSCompiler
from app.email_engine.tests.conftest import make_mock_registry


@pytest.fixture(autouse=True)
def _mock_ontology() -> Generator[None]:
    """Use consistent mock ontology for equivalence tests."""
    reg = make_mock_registry(support_none=False)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield


class TestPipelineEquivalence:
    """Verify compile() and optimize_css() produce consistent optimization results
    across real golden templates."""

    def test_optimization_stages_match(self, representative_templates: dict[str, str]) -> None:
        """Stages 1-5 produce same removed/converted properties in both paths."""
        for name, html in representative_templates.items():
            compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
            compile_result = compiler.compile(html)
            optimize_result = compiler.optimize_css(html)

            assert set(compile_result.removed_properties) == set(optimize_result.removed_properties), (
                f"Template '{name}': removed properties differ"
            )
            compile_convs = {(c.original_property, c.replacement_property) for c in compile_result.conversions}
            optimize_convs = {(c.original_property, c.replacement_property) for c in optimize_result.conversions}
            assert compile_convs == optimize_convs, f"Template '{name}': conversions differ"

    def test_mso_conditionals_preserved_both_paths(self, representative_templates: dict[str, str]) -> None:
        """MSO conditionals survive both compile and optimize paths."""
        for name, html in representative_templates.items():
            compiler = EmailCSSCompiler(target_clients=["outlook_2019"])
            compile_result = compiler.compile(html)
            optimize_result = compiler.optimize_css(html)

            if "<!--[if mso]>" in html:
                assert "<!--[if mso]>" in compile_result.html, f"Template '{name}': MSO lost in compile"
                assert "<!--[if mso]>" in optimize_result.html, f"Template '{name}': MSO lost in optimize"

    def test_media_queries_preserved_both_paths(self, representative_templates: dict[str, str]) -> None:
        """@media rules survive both paths."""
        for name, html in representative_templates.items():
            compiler = EmailCSSCompiler(target_clients=["gmail_web"])
            compile_result = compiler.compile(html)
            optimize_result = compiler.optimize_css(html)

            if "@media" in html:
                assert "@media" in compile_result.html, f"Template '{name}': @media lost in compile"
                assert "@media" in optimize_result.html, f"Template '{name}': @media lost in optimize"

    def test_no_regressions_in_compiled_output(self, representative_templates: dict[str, str]) -> None:
        """Compiled output is valid HTML with body content preserved."""
        for name, html in representative_templates.items():
            compiler = EmailCSSCompiler(target_clients=["gmail_web"])
            result = compiler.compile(html)
            assert "<body" in result.html.lower(), f"Template '{name}': missing <body>"
            assert result.compiled_size > 0
            assert result.compiled_size <= result.original_size * 1.5, (
                f"Template '{name}': output grew unexpectedly"
            )

    def test_all_15_templates_compile_without_error(self, golden_templates: dict[str, str]) -> None:
        """Every golden template in the library compiles successfully."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for name, html in golden_templates.items():
            result = compiler.compile(html)
            assert result.compiled_size > 0, f"Template '{name}': zero compiled size"

    def test_all_15_templates_optimize_without_error(self, golden_templates: dict[str, str]) -> None:
        """Every golden template in the library optimizes successfully."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for name, html in golden_templates.items():
            result = compiler.optimize_css(html)
            assert isinstance(result.html, str), f"Template '{name}': optimize failed"

    def test_all_components_compile_without_error(self, component_html: dict[str, str]) -> None:
        """Every seeded component HTML compiles successfully."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for slug, html in component_html.items():
            result = compiler.compile(html)
            assert result.compiled_size > 0, f"Component '{slug}': zero compiled size"

    def test_all_components_optimize_without_error(self, component_html: dict[str, str]) -> None:
        """Every seeded component HTML optimizes successfully."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for slug, html in component_html.items():
            result = compiler.optimize_css(html)
            assert isinstance(result.html, str), f"Component '{slug}': optimize failed"

    def test_email_shell_preserves_mso_and_dark_mode(self, component_html: dict[str, str]) -> None:
        """Email shell component preserves MSO conditionals and dark mode CSS."""
        shell = component_html.get("email-shell", "")
        if not shell:
            pytest.skip("email-shell component not in seeds")
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])

        compile_result = compiler.compile(shell)
        optimize_result = compiler.optimize_css(shell)

        for result, label in [(compile_result.html, "compile"), (optimize_result.html, "optimize")]:
            assert "<!--[if mso]>" in result, f"email-shell {label}: MSO conditionals lost"
            assert "prefers-color-scheme" in result, f"email-shell {label}: dark mode CSS lost"
            assert "data-slot" in result, f"email-shell {label}: slot markers lost"

    def test_component_slot_markers_preserved(self, representative_components: dict[str, str]) -> None:
        """Component slot markers (data-slot) survive both pipeline paths."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web"])
        for slug, html in representative_components.items():
            if "data-slot" not in html:
                continue
            compile_result = compiler.compile(html)
            optimize_result = compiler.optimize_css(html)
            assert "data-slot" in compile_result.html, f"Component '{slug}': slots lost in compile"
            assert "data-slot" in optimize_result.html, f"Component '{slug}': slots lost in optimize"
```

### Step 6: Create `test_performance_benchmark.py`

File: `app/email_engine/tests/test_performance_benchmark.py`

Uses **real golden templates** for realistic benchmarks alongside synthetic scaling tests.

```python
"""Performance benchmarks for CSS compilation pipeline.

Run with: make bench
Not included in standard `make test`.
"""
from __future__ import annotations

import time
from collections.abc import Generator
from unittest.mock import patch

import pytest

from app.email_engine.css_compiler.compiler import EmailCSSCompiler
from app.email_engine.tests.conftest import make_mock_registry


def _generate_scaled_email(section_count: int) -> str:
    """Generate an email with N sections for scaling benchmarks.

    Uses table-based layout matching real email component patterns.
    """
    styles = "\n".join(
        f".section-{i} {{ color: #{i:02x}{i:02x}{i:02x}; font-size: {12 + i}px; "
        f"padding: {i}px; margin: {i}px; line-height: 1.{i % 10}; }}"
        for i in range(section_count)
    )
    sections = "\n".join(
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td class="section-{i}" style="padding: {10 + i}px; font-family: Arial, sans-serif;">'
        f"<h2>Section {i}</h2><p>Content block {i} with text.</p>"
        f"</td></tr></table>"
        for i in range(section_count)
    )
    return (
        f'<!DOCTYPE html><html><head><style>{styles}</style></head>'
        f'<body><table role="presentation" width="600" align="center" '
        f'cellpadding="0" cellspacing="0" border="0"><tr><td>'
        f'{sections}'
        f'</td></tr></table></body></html>'
    )


@pytest.fixture(autouse=True)
def _mock_ontology() -> Generator[None]:
    reg = make_mock_registry(support_none=False)
    with (
        patch("app.email_engine.css_compiler.compiler.load_ontology", return_value=reg),
        patch("app.email_engine.css_compiler.conversions.load_ontology", return_value=reg),
    ):
        yield


def _time_fn(fn, *args, iterations: int = 5) -> float:
    """Return median execution time in ms over N iterations."""
    times: list[float] = []
    for _ in range(iterations):
        start = time.monotonic()
        fn(*args)
        times.append((time.monotonic() - start) * 1000)
    times.sort()
    return times[len(times) // 2]


@pytest.mark.benchmark
class TestCompilationBenchmarks:
    """Benchmark compile() vs optimize_css() performance."""

    @pytest.mark.parametrize("sections", [5, 15, 30])
    def test_optimize_faster_than_compile_scaled(self, sections: int) -> None:
        """optimize_css() should be faster than compile() on synthetic scaled emails."""
        html = _generate_scaled_email(sections)
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])

        compile_ms = _time_fn(compiler.compile, html)
        optimize_ms = _time_fn(compiler.optimize_css, html)

        print(f"\n  [{sections} sections] compile={compile_ms:.1f}ms  optimize={optimize_ms:.1f}ms  "
              f"speedup={compile_ms / max(optimize_ms, 0.01):.1f}x")

        assert optimize_ms < compile_ms, (
            f"optimize_css ({optimize_ms:.1f}ms) should be faster than compile ({compile_ms:.1f}ms)"
        )

    def test_optimize_real_templates(self, representative_templates: dict[str, str]) -> None:
        """Benchmark optimize_css() on real golden templates from the library."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for name, html in representative_templates.items():
            ms = _time_fn(compiler.optimize_css, html)
            print(f"\n  [{name}] optimize={ms:.1f}ms  size={len(html)}b")
            assert ms < 200, f"Template '{name}' optimize took {ms:.1f}ms, expected <200ms"

    def test_compile_real_templates(self, representative_templates: dict[str, str]) -> None:
        """Benchmark full compile() on real golden templates."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for name, html in representative_templates.items():
            ms = _time_fn(compiler.compile, html)
            print(f"\n  [{name}] compile={ms:.1f}ms  size={len(html)}b")
            assert ms < 500, f"Template '{name}' compile took {ms:.1f}ms, expected <500ms"

    def test_optimize_30_sections_under_100ms(self) -> None:
        """30-section email optimize_css should complete in under 100ms."""
        html = _generate_scaled_email(30)
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        ms = _time_fn(compiler.optimize_css, html)
        print(f"\n  [30 sections] optimize={ms:.1f}ms")
        assert ms < 100, f"optimize_css took {ms:.1f}ms, expected <100ms"

    def test_compile_50_sections_completes(self) -> None:
        """50-section email compile() should complete without error."""
        html = _generate_scaled_email(50)
        compiler = EmailCSSCompiler(target_clients=["gmail_web"])
        result = compiler.compile(html)
        assert result.compiled_size > 0
        print(f"\n  [50 sections] compile={result.compile_time_ms:.1f}ms")

    def test_optimize_email_shell_component(self, component_html: dict[str, str]) -> None:
        """Benchmark optimize_css() on the email-shell component (heaviest CSS)."""
        shell = component_html.get("email-shell", "")
        if not shell:
            pytest.skip("email-shell component not in seeds")
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        ms = _time_fn(compiler.optimize_css, shell)
        print(f"\n  [email-shell] optimize={ms:.1f}ms  size={len(shell)}b")
        assert ms < 200, f"email-shell optimize took {ms:.1f}ms, expected <200ms"

    def test_optimize_all_components(self, component_html: dict[str, str]) -> None:
        """Benchmark optimize_css() across all 21 seeded components."""
        compiler = EmailCSSCompiler(target_clients=["gmail_web", "outlook_2019"])
        for slug, html in component_html.items():
            ms = _time_fn(compiler.optimize_css, html)
            print(f"\n  [{slug}] optimize={ms:.1f}ms  size={len(html)}b")
```

### Step 7: Expand sidecar tests (`services/maizzle-builder/postcss-email-optimize.test.js`)

Add 10+ new tests to the existing Vitest file:

```javascript
// Add these tests to the existing describe block:

it('removes unsupported properties per ontology', async () => {
  // This test verifies the plugin interacts with the ontology correctly
  // Properties that are NONE in all target clients with no fallback should be removed
  const { optimization } = await optimize('.x { display: block; }', ['gmail_web']);
  // display:block is universally supported, should NOT be removed
  expect(optimization.removed_properties).not.toContain('display: block');
});

it('preserves @media rules intact', async () => {
  const { css } = await optimize(
    '@media (max-width: 600px) { .mobile { font-size: 14px; } } .desktop { font-size: 16px; }',
    ['gmail_web']
  );
  expect(css).toContain('@media');
  expect(css).toContain('.mobile');
  expect(css).toContain('.desktop');
});

it('preserves @keyframes rules', async () => {
  const { css } = await optimize(
    '@keyframes fade { from { opacity: 0; } to { opacity: 1; } }',
    ['gmail_web']
  );
  expect(css).toContain('@keyframes');
});

it('removes @import at-rules', async () => {
  const { css, optimization } = await optimize(
    '@import url("styles.css"); .hero { color: red; }',
    ['gmail_web']
  );
  expect(css).not.toContain('@import');
  expect(optimization.warnings.some(w => w.includes('@import'))).toBe(true);
});

it('handles multiple selectors', async () => {
  const { css } = await optimize(
    '.a { color: red; } .b { font-size: 14px; } .c { margin: 0; }',
    ['gmail_web']
  );
  expect(css).toContain('.a');
  expect(css).toContain('.b');
  expect(css).toContain('.c');
});

it('handles CSS with no declarations', async () => {
  const { css } = await optimize('.empty {}', ['gmail_web']);
  expect(typeof css).toBe('string');
});

it('conversion metadata has correct structure', async () => {
  const { optimization } = await optimize('.x { color: red; }', ['gmail_web']);
  expect(optimization).toHaveProperty('removed_properties');
  expect(optimization).toHaveProperty('conversions');
  expect(optimization).toHaveProperty('warnings');
  expect(Array.isArray(optimization.removed_properties)).toBe(true);
  expect(Array.isArray(optimization.conversions)).toBe(true);
  expect(Array.isArray(optimization.warnings)).toBe(true);
});

it('conversion entry has required fields', async () => {
  // Test that when a conversion occurs, it has the right shape
  const { optimization } = await optimize('.x { display: block; }', ['gmail_web']);
  for (const conv of optimization.conversions) {
    expect(conv).toHaveProperty('original_property');
    expect(conv).toHaveProperty('replacement_property');
    expect(conv).toHaveProperty('affected_clients');
    expect(Array.isArray(conv.affected_clients)).toBe(true);
  }
});

it('uses default target clients when none provided', async () => {
  // Plugin should work with default clients
  const result = await postcss([emailOptimize()]).process('.x { color: red; }', { from: undefined });
  expect(result.emailOptimization).toBeDefined();
});

it('handles complex nested selectors', async () => {
  const { css } = await optimize(
    '.parent .child > .grandchild { color: red; font-size: 14px; }',
    ['gmail_web']
  );
  expect(css).toContain('.parent');
});
```

Also add a separate describe block for the sync-ontology script validation:
```javascript
import { existsSync, readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

describe('ontology sync', () => {
  const __dirname = dirname(fileURLToPath(import.meta.url));

  it('ontology.json exists and is valid', () => {
    const path = resolve(__dirname, 'data/ontology.json');
    expect(existsSync(path)).toBe(true);
    const data = JSON.parse(readFileSync(path, 'utf-8'));
    expect(data).toHaveProperty('version');
    expect(data).toHaveProperty('properties_by_name');
    expect(data).toHaveProperty('support_lookup');
    expect(data).toHaveProperty('fallbacks_by_source');
    expect(typeof data.version).toBe('string');
  });

  it('ontology has client_ids array', () => {
    const path = resolve(__dirname, 'data/ontology.json');
    const data = JSON.parse(readFileSync(path, 'utf-8'));
    expect(Array.isArray(data.client_ids)).toBe(true);
    expect(data.client_ids.length).toBeGreaterThan(0);
  });
});
```

### Step 8: Add `make bench` target to Makefile

Add after the existing `test-properties` target (around line 48):

```makefile
bench: ## Run performance benchmark tests
	uv run pytest -v -m benchmark --no-header -rN
```

### Step 9: Configure pytest benchmark marker

Check `pyproject.toml` for pytest config and add the marker registration if needed. Add to the `[tool.pytest.ini_options]` section:

```toml
markers = [
    ...,
    "benchmark: Performance benchmark tests (run with: make bench)",
]
```

Also ensure `make test` excludes benchmark tests by updating the test filter:
```makefile
test: ## Run backend unit tests
	uv run pytest -v -m "not integration and not benchmark"
```

## Security Checklist
- No new endpoints created — this is a test-only change
- No user input handling — all tests use hardcoded fixture data
- No secrets or credentials in test files
- No external network calls — all HTTP is mocked

## Verification
- [ ] `make test` passes (all new + existing tests, excludes benchmarks)
- [ ] `make bench` runs benchmark tests and shows timing output
- [ ] `make check` all green (lint + types + tests + security)
- [ ] `make eval-golden` passes (no regression)
- [ ] Pipeline equivalence tests confirm consistent optimization results across 5 golden templates
- [ ] Total new test count: ~65+ across all files
  - `test_optimize_css.py`: 15 new tests (structure, removals, conversions, variables, preservation, edge cases)
  - `test_css_audit.py`: 7 existing + 8 new = 15 tests
  - `test_precompiler.py`: 7 existing + 10 new = 17 tests
  - `test_pipeline_equivalence.py`: 11 tests (templates + components equivalence, slot/MSO/dark mode preservation)
  - `test_performance_benchmark.py`: 8 tests (3 parametrized scaling + 2 real template + 2 component + 1 threshold)
  - `postcss-email-optimize.test.js`: 5 existing + 12 new = 17 tests (plugin + ontology sync)
  - `conftest.py`: shared fixtures only (loads 15 templates + 21 components from real data)
