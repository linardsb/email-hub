# Tech Debt 06 — `custom_checks.py` Split + RuleEngine Factory

**Source:** `TECH_DEBT_AUDIT.md`
**Scope:** Split 3,738-LOC `custom_checks.py` into 11 domain modules + parameterized factory absorbing the 10 of 14 QA check classes that share the standard RuleEngine pattern. ~1000 LOC removed.
**Goal:** Each `custom_checks/*.py` is 250-400 LOC, single-domain. 10 check classes replaced by registry entries; 3 bespoke classes (`liquid_syntax`, `css_support`, `rendering_resilience`) and 2 already-bespoke (`css_audit`, `deliverability`) preserved.
**Estimated effort:** Full session (heavy).
**Prerequisite:** None.

> **Session 17 rescope (2026-05-12):** Parts A and B already shipped (custom_checks package + RuleEngineCheck factory + 10 boilerplate classes deleted; verify: `ls app/qa_engine/custom_checks/` and `cat app/qa_engine/checks/__init__.py`). **Only Part C remains — F067 test split is the entire Session 17 scope on this plan.** Branch: `test/tech-debt-17-connector-qa-coverage`.

## Findings addressed

F018 (`custom_checks.py` 3738 LOC, 125 funcs, 11 `_param` copies) — Critical
F019 (10 of 14 QA check classes are RuleEngine boilerplate) — High
F029 (blanket `# ruff: noqa: ARG001` on 3738-LOC file) — Medium
F067 (no per-check tests; `test_checks.py` 1944 LOC mega-file) — Medium

## Codebase reality (vs. original plan)

The 14 checks in `app/qa_engine/checks/` are NOT all interchangeable boilerplate:

- **10 fit a parameterized factory** (RuleEngine + parse + score + filter): `accessibility`, `dark_mode`, `fallback`, `link_validation`, `html_validation`, `file_size`, `image_optimization`, `personalisation_syntax`, `brand_compliance`, `spam_score`. Variations: cache_clear, empty-HTML strategy (fail/pass/skip), severity tiers (2- vs 3-tier with thresholds 0.30 / 0.50), pass-filter prefix (`"Raw:"`, `"Brand compliance:"`, etc.), default details, threshold-based pass (`spam_score`), config enricher (brand design-system), skip predicate (brand no-rules path).
- **3 stay as classes (bespoke logic)**: `liquid_syntax` (197 LOC, 4-pass with python-liquid lib), `css_support` (111 LOC, ontology+rule engine dual pass), `rendering_resilience` (74 LOC, chaos engine — must stay outside `ALL_CHECKS` to avoid recursion).
- **2 already bespoke (kept)**: `css_audit`, `deliverability`.

`QACheckResult` schema: `(check_name, passed, score, details, severity)`. `RuleEngine.evaluate(doc, raw_html, config) -> tuple[list[str], float]`.

## Pre-flight

```bash
git checkout -b refactor/tech-debt-06-qa-engine-split
make check
make test app/qa_engine/  # baseline

# QA output baseline:
make eval-golden
cp traces/qa_golden_baseline.json traces/qa_golden_baseline.before.json
```

## Part A — Split `custom_checks.py` (F018)

### A1. Create the package

Line ranges from grep on registration markers (verified):
```
app/qa_engine/custom_checks/
  __init__.py        ← imports all 11 domain modules to trigger register_custom_check
  _helpers.py        ← single param/iter_capped helpers
  html.py            ← lines  1-844    (HTML structure, ~ 19 registrations)
  a11y.py            ← lines  845-1614 (Accessibility, ~ 22 registrations)
  mso.py             ← lines  1615-1719
  dark_mode.py       ← lines  1720-2063
  link.py            ← lines  2064-2269
  file_size.py       ← lines  2270-2424
  spam.py            ← lines  2425-2681
  brand.py           ← lines  2682-2881
  image.py           ← lines  2882-3148
  css.py             ← lines  3149-3460
  personalisation.py ← lines  3461-3738
```

### A2. Extract `_param` helper

Single helper in `app/qa_engine/custom_checks/_helpers.py`:
```python
from typing import Any
from app.qa_engine.check_config import QACheckConfig

def param(config: QACheckConfig | None, key: str, default: Any = None) -> Any:
    if config:
        return config.params.get(key, default)
    return default

def iter_capped(doc, tag: str, cap: int):
    """Iterate elements with a count cap; addresses F024 per-check generator dup."""
    count = 0
    for elem in doc.iter(tag):
        if cap and count >= cap:
            break
        yield elem
        count += 1
```

Replace all 11 `_param`/`_a11y_param`/`_mso_param`/etc. definitions with imports of `param`. Each section's domain module already has its own default constants — keep those local; only the `_param` boilerplate is consolidated.

### A3. Side-effect imports

`app/qa_engine/custom_checks/__init__.py`:
```python
"""Custom QA checks. Importing this package triggers register_custom_check side effects."""

from app.qa_engine.custom_checks import (
    a11y, brand, css, dark_mode, file_size, html, image,
    link, mso, personalisation, spam,
)

__all__ = [
    "a11y", "brand", "css", "dark_mode", "file_size", "html", "image",
    "link", "mso", "personalisation", "spam",
]
```

The original `app/qa_engine/custom_checks.py` is **deleted**. The lone external import site is `app/qa_engine/checks/__init__.py:6`:
```python
import app.qa_engine.custom_checks as _custom_checks
```
This still works against the package's `__init__.py`. Verify:
```bash
rg "from app.qa_engine.custom_checks" app/ --type py
rg "import app.qa_engine.custom_checks" app/ --type py
```

### A4. Drop the blanket `# ruff: noqa: ARG001`

Apply per-function `# noqa: ARG001` only where the `register_custom_check` protocol genuinely forces unused params. Run `ruff check app/qa_engine/custom_checks/` and resolve real warnings.

## Part B — Collapse 10 RuleEngine boilerplate classes (F019)

### B0. Compatibility shim & external callsite prep (do FIRST)

External callsites import classes directly. Migrate before deleting.

**B0.1 — Add a registry accessor.** In `app/qa_engine/checks/_factory.py`:
```python
def get_check(name: str):
    """Look up a check from ALL_CHECKS by name. Replaces direct class imports."""
    from app.qa_engine.checks import ALL_CHECKS
    for c in ALL_CHECKS:
        if getattr(c, "name", None) == name:
            return c
    raise KeyError(f"Unknown check: {name}")
```

**B0.2 — Relocate `SPAM_TRIGGERS`.** New module `app/qa_engine/spam_triggers.py` loads from `data/spam_triggers.yaml`. Update the one external importer:
- `app/ai/agents/content/service.py:36` → `from app.qa_engine.spam_triggers import SPAM_TRIGGERS`

**B0.3 — Rewrite the `isinstance(check, DarkModeCheck)` filter.** In `app/ai/agents/dark_mode/service.py:91,97`:
```python
# before:
dm_check = DarkModeCheck()
... if isinstance(check, DarkModeCheck): ...

# after:
from app.qa_engine.checks._factory import get_check
dm_check = get_check("dark_mode")
... if getattr(check, "name", None) == "dark_mode": ...
```

**B0.4 — Resilience special-path: KEEP, do not migrate.** `RenderingResilienceCheck` runs the chaos engine, which itself iterates `ALL_CHECKS`. Including resilience in the registry causes infinite recursion. The special-path in `app/qa_engine/service.py:115–120` stays. `app/qa_engine/tests/test_resilience_check.py:5` keeps the direct class import.

**B0.5 — External test callsites for the 10 deleted classes.** Migrate to `get_check(...)`:
- `app/ai/blueprints/tests/test_e2e_brand_enforcement.py:12` — `BrandComplianceCheck` → `get_check("brand_compliance")`
- `app/qa_engine/tests/test_synthetic_generator.py:138` — `DarkModeCheck` → `get_check("dark_mode")`
- `app/qa_engine/tests/test_check_config.py:92,108,125` — `FileSizeCheck()`, `SpamScoreCheck()`, `DarkModeCheck()` → `get_check(...)`
- `app/qa_engine/tests/test_checks.py:5-15` — all imports replaced when test file is split (Part C); during interim, migrate to `get_check(...)`.

Kept (no migration):
- `app/tests/test_24b_integration.py:21,22` — `CssSupportCheck`, `LiquidSyntaxCheck` are KEPT classes.
- `app/qa_engine/tests/test_liquid_syntax.py:8` — `LiquidSyntaxCheck` kept.
- `app/qa_engine/tests/test_resilience_check.py:5` — `RenderingResilienceCheck` kept.

The MCP integration callsites (`app/mcp/tools/ai.py:66`, `app/mcp/tools/qa.py:103`) and `app/qa_engine/service.py:534` import `get_detailed_result` from `app/qa_engine/checks/deliverability.py` which is **kept** — no change.

**B0.6 — Test count assertion.** `app/qa_engine/tests/test_service.py:44–45` already changed from `== 14` to `>= 14`. Resilience stays special, so count stays 14. `>=` covers both.

### B1. Create the parameterized factory

**New file:** `app/qa_engine/checks/_factory.py`. The factory uses real `QACheckResult` fields and the real `RuleEngine.evaluate(doc, html, config) -> (issues, total_deduction)` signature. Variations are dataclass fields; full schema in source.

Key decision points encoded as fields:
- `cache_clear: Callable[[], None] | None` — pre-run cache invalidation.
- `empty_strategy: Literal["fail_error", "pass_info", "skip"]` — empty HTML handling.
- `respects_disabled_config: bool` + `disabled_message: str` — honours `config.enabled=False`.
- `failed_severity: Literal["error", "warning"]` + `error_threshold: float | None` — 2-tier (None) or 3-tier (deduction >= threshold → failed_severity, else "warning").
- `pass_filter_prefix: str | None` — issues starting with this prefix don't count toward pass/fail (informational summaries).
- `no_issues_details: str | None` — default `details` when zero issues.
- `threshold_pass: bool` — pass = `score >= config.threshold` (vs. failure_issues count).
- `config_enricher: Callable | None` — pre-evaluate config transformer (brand design-system).
- `skip_predicate: Callable | None` — short-circuit pass path (brand no-rules).
- `parse_error_message: str` — message for HTML parse failure (some checks have custom).

The `run()` method orchestrates: enrich config → disabled guard → skip predicate → cache_clear → empty strategy → parse → engine.evaluate → score/severity/filter → result.

`get_check(name)` accessor lives in the same module (B0.1).

### B2. Registry table

**Replace** `app/qa_engine/checks/__init__.py` with mixed entries (factory + bespoke classes):

```python
ALL_CHECKS: list[QACheckProtocol] = [
    RuleEngineCheck(name="html_validation", rules_path=..., failed_severity="error"),
    CssSupportCheck(),                # bespoke (dual pass)
    CSSAuditCheck(),                  # bespoke
    RuleEngineCheck(
        name="file_size", rules_path=..., cache_clear=clear_file_size_cache,
        empty_strategy="skip", failed_severity="error", error_threshold=0.30,
        pass_filter_prefix="Raw:", no_issues_details="All file size thresholds met",
        parse_error_message="Failed to parse HTML for file size analysis",
    ),
    RuleEngineCheck(name="link_validation", rules_path=..., cache_clear=clear_link_cache),
    RuleEngineCheck(name="spam_score", rules_path=..., threshold_pass=True),
    RuleEngineCheck(name="dark_mode", rules_path=..., cache_clear=clear_dm_cache),
    RuleEngineCheck(name="accessibility", rules_path=...),
    RuleEngineCheck(name="fallback", rules_path=..., cache_clear=clear_mso_cache),
    RuleEngineCheck(
        name="image_optimization", rules_path=..., cache_clear=clear_image_cache,
        empty_strategy="skip", failed_severity="error", error_threshold=0.30,
        pass_filter_prefix="Images:", no_issues_details="All images properly optimized",
        parse_error_message="Failed to parse HTML for image analysis",
    ),
    RuleEngineCheck(
        name="brand_compliance", rules_path=..., cache_clear=clear_brand_cache,
        respects_disabled_config=True,
        disabled_message="Brand compliance check disabled by configuration",
        config_enricher=_enrich_brand_config, skip_predicate=_brand_skip_predicate,
        failed_severity="error", error_threshold=0.50,
        pass_filter_prefix="Brand compliance:",
        no_issues_details="All brand rules satisfied",
    ),
    RuleEngineCheck(
        name="personalisation_syntax", rules_path=...,
        cache_clear=clear_personalisation_cache, respects_disabled_config=True,
        disabled_message="Personalisation syntax check disabled by configuration",
        empty_strategy="pass_info",
        empty_message="Empty HTML document — no personalisation to validate",
        failed_severity="error", error_threshold=0.30,
        pass_filter_prefix="Summary:",
        no_issues_details="No personalisation issues found",
    ),
    DeliverabilityCheck(),  # bespoke
    LiquidSyntaxCheck(),    # bespoke (4-pass python-liquid)
]
```

`RenderingResilienceCheck` is **NOT** in `ALL_CHECKS` — kept as a class loaded directly by `service.py:118` (avoids chaos-engine recursion).

`_enrich_brand_config` and `_brand_skip_predicate` are module-level helpers in `__init__.py` (originally inside `BrandComplianceCheck`).

### B3. Delete the 10 boilerplate check classes

Delete:
- `app/qa_engine/checks/html_validation.py`
- `dark_mode.py`
- `accessibility.py`
- `fallback.py`
- `file_size.py`
- `link_validation.py`
- `image_optimization.py`
- `brand_compliance.py`
- `personalisation_syntax.py`
- `spam_score.py`

Keep:
- `css_audit.py` (bespoke)
- `deliverability.py` (bespoke)
- `liquid_syntax.py` (bespoke, 4-pass python-liquid)
- `css_support.py` (bespoke, dual ontology+rule pass)
- `rendering_resilience.py` (bespoke, chaos engine, special-path)

### B4. Update the QA engine

`app/qa_engine/service.py` already imports `ALL_CHECKS` (`:18`) and iterates (`:94`) — no change needed. The resilience special-path at `:115–120` stays. The deliverability import at `:534` stays.

### B5. F039 follow-up: `clear_*_cache()` location

Per-call cache clears are useless — they invalidate before each run, defeating any caching benefit. Preserve current behavior; address in a follow-up that removes caches entirely.

## Part C — Test split (F067) — **Session 17 scope**

### C0. State on disk (verified 2026-05-12)

- `app/qa_engine/tests/test_checks.py` — 1935 LOC, 13 `Test*` classes (see table below). Imports already use `get_check(...)` for the 10 factory checks + `CssSupportCheck` direct (line 6).
- `_valid_html` helper at `test_checks.py:11–36` — used 48× across the file.
- Pyright pragma at line 1: `# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false` — relaxes types for the whole file.
- Pre-existing files in `app/qa_engine/tests/` that **must not collide** with split outputs:
  - `test_liquid_syntax.py` (127 LOC) — bespoke kept; **already exists**.
  - `test_css_audit.py` — bespoke kept; **already exists**.
  - `test_resilience_check.py` — bespoke kept; direct `RenderingResilienceCheck` import preserved.
  - Analyzer/parser tests with confusable names — **do not merge**: `test_dark_mode_parser.py`, `test_link_parser.py`, `test_file_size_analyzer.py`, `test_image_analyzer.py`, `test_brand_analyzer.py`, `test_personalisation_validator.py`. These test the underlying parsers; the new `test_<check>.py` files test the check classes.

### C1. Per-class → per-file mapping (13 classes → 11 new files)

| Source class (`test_checks.py` line) | Target file | Check obj | Import |
|---|---|---|---|
| `TestHtmlValidation` (39) | `test_html_validation.py` | `get_check("html_validation")` | factory |
| `TestCssSupport` (352) | `test_css_support.py` *(NEW)* | `CssSupportCheck()` | direct |
| `TestCssSupportSyntax` (386) | `test_css_support.py` | `CssSupportCheck()` | direct |
| `TestFileSize` (541) | `test_file_size.py` | `get_check("file_size")` | factory |
| `TestLinkValidation` (647) | `test_link_validation.py` | `get_check("link_validation")` | factory |
| `TestSpamScore` (690) | `test_spam_score.py` | `get_check("spam_score")` | factory |
| `TestDarkMode` (784) | `test_dark_mode.py` | `get_check("dark_mode")` | factory |
| `TestAccessibility` (1003) | `test_accessibility.py` | `get_check("accessibility")` | factory |
| `TestFallback` (1318) | `test_fallback.py` | `get_check("fallback")` | factory |
| `TestImageOptimization` (1474) | `test_image_optimization.py` | `get_check("image_optimization")` | factory |
| `TestBrandCompliance` (1647) | `test_brand_compliance.py` | `get_check("brand_compliance")` | factory |
| `TestLinkValidationCheck` (1768) | `test_link_validation.py` *(merged with `TestLinkValidation`)* | `get_check("link_validation")` | factory |
| `TestPersonalisationSyntax` (1829) | `test_personalisation_syntax.py` | `get_check("personalisation_syntax")` | factory |

Net: **11 new files**, 1 deletion (`test_checks.py`). Two duplicate `TestLinkValidation` / `TestLinkValidationCheck` classes go into the same `test_link_validation.py` (pytest tolerates multiple `Test*` classes per file — keep both class names to preserve test-id stability for the existing CI baseline; merging into one class would rename test ids).

### C2. Shared `_valid_html` helper relocation

Move the 26-line `_valid_html` factory from `test_checks.py:11–36` to a new module `app/qa_engine/tests/_helpers.py` (free function, NOT a pytest fixture — it takes kwargs and is called inline 48 times). Each new test file imports:

```python
from app.qa_engine.tests._helpers import valid_html  # drop the leading underscore on export
```

Rename `_valid_html` → `valid_html` at the export site (the leading underscore was hiding the module-local intent that no longer applies once it's exported). Keep call-sites: `valid_html(doctype=False)` etc. — kwargs unchanged.

`conftest.py` already provides `sample_html_valid` and `sample_html_minimal` fixtures (`app/qa_engine/tests/conftest.py:89,121`) — those remain in conftest, used as fixture args in the new files exactly as today (`async def test_..., sample_html_valid: str`).

### C3. New-file boilerplate template

Each of the 11 new `test_<check>.py` files starts with:

```python
"""Unit tests for the <check_name> QA check."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check  # or CssSupportCheck for bespoke
from app.qa_engine.tests._helpers import valid_html  # only if the file uses it


class Test<CheckName>:
    check = get_check("<check_name>")  # or CssSupportCheck() for css_support

    async def test_<...>(self, sample_html_valid: str) -> None:
        ...
```

**Drop the pyright pragma** from `test_checks.py:1`. Each new file fixes types properly:
- Async test methods: explicit `-> None` return.
- Fixture parameters: `sample_html_valid: str`, `sample_html_minimal: str`.
- Local HTML strings: implicit `str`, no annotation needed.
- `check = get_check(...)` class-level attribute: pyright infers `QACheckProtocol` — no annotation needed.

If pyright still flags a residual `reportUnknownArgumentType`, add a per-line `# pyright: ignore[<code>]` rather than re-introducing the file-wide pragma.

### C4. Deletion of `test_checks.py`

Final commit in the split sequence: `git rm app/qa_engine/tests/test_checks.py`. Verify zero external imports first:
```bash
rg "from app.qa_engine.tests.test_checks|from app.qa_engine.tests import test_checks" --type py
```
Expected: zero matches (verified during preflight).

### C5. Per-check coverage gate

After the split, each new `test_<check>.py` file is expected to exercise its target module ≥ 80% line coverage. Run:
```bash
uv run pytest app/qa_engine/tests/test_<check>.py \
  --cov=app/qa_engine/checks/<check>.py \
  --cov-report=term-missing \
  --cov-fail-under=80
```
Factory-driven checks have no per-check module (deleted in Part B); for those, coverage is measured against the factory invocation path in `app/qa_engine/checks/_factory.py` and `app/qa_engine/custom_checks/<domain>.py`. Document the per-file coverage target in each test file's module docstring; do **not** add a CI gate beyond the existing `make check-full` invocation — Session 17 is a test split, not new coverage tooling.

### C6. Execution sequence

1. Create `_helpers.py` with the renamed `valid_html` function; verify imports work via `python -c "from app.qa_engine.tests._helpers import valid_html"`.
2. Create the 11 new test files one at a time, copying their `Test*` class verbatim plus the boilerplate header from C3.
3. After each file is created, run `uv run pytest app/qa_engine/tests/test_<check>.py -v` and confirm test count matches the source block (use `grep -c "    async def test_" test_checks.py` against the relevant line range as the expected count).
4. Once all 11 pass at parity, delete `test_checks.py`.
5. Run `make check-full` for the full gate (lint + types + tests + security + golden conformance + flag audit).

## Verification

```bash
make check
make test app/qa_engine/ -v

# QA output equivalence (CRITICAL):
make eval-golden
diff traces/qa_golden_baseline.json traces/qa_golden_baseline.before.json
# MUST be empty (refactor preserves behaviour)

# LOC reduction:
wc -l app/qa_engine/custom_checks/*.py
# Each file 250-400; total still ~3700 (split, not deleted)

# Class file count:
ls app/qa_engine/checks/
# Expected: __init__.py, _factory.py, css_audit.py, css_support.py,
# deliverability.py, liquid_syntax.py, rendering_resilience.py
```

## Rollback

The factory + registry is reversible per check: revert one file, re-add a per-check class, remove from `ALL_CHECKS`. Full rollback is a single PR revert.

## Risk notes

- **`register_custom_check` order matters.** Importing `custom_checks/__init__.py` should trigger registration of all 11 modules. Test on a fresh process.
- **`qa_golden_baseline.json` diff must be empty.** Any divergence means the factory missed a behavioral knob — inspect, fix, re-run. Don't ship until clean.
- **`load_rules` caching**: factory lazy-loads on first `run()` and caches per-instance. Original classes loaded at construction time — same effective behavior after warmup; first call is marginally slower.
- **`# ruff: noqa: ARG001` blanket** removal will surface real warnings — fix at the source, don't re-blanket.
- **Import-order sensitivity in `__init__.py`**: cache-clear callables and helper functions for `config_enricher`/`skip_predicate` must be defined or imported before the `ALL_CHECKS` literal.

## Done when

- [ ] `app/qa_engine/custom_checks.py` (3738 LOC) → 11 modules of 250-400 LOC each + `_helpers.py`.
- [ ] 10 RuleEngine check classes deleted; `RuleEngineCheck` factory in `_factory.py`.
- [ ] 3 bespoke classes preserved (`liquid_syntax`, `css_support`, `rendering_resilience`).
- [ ] `get_check(name)` accessor exists in `_factory.py`.
- [ ] `SPAM_TRIGGERS` relocated to `app/qa_engine/spam_triggers.py`; `app/ai/agents/content/service.py` import updated.
- [ ] `app/ai/agents/dark_mode/service.py` no longer uses `isinstance(check, DarkModeCheck)`; switched to name-based filter.
- [ ] Resilience special-path in `service.py:115–120` PRESERVED (avoids chaos-engine recursion).
- [ ] All external callsites listed in B0.5 migrated to `get_check(...)` lookups.
- [ ] `qa_golden_baseline.json` diff empty.
- [ ] Per-check test files exist; `test_checks.py` mega-file deleted.
- [ ] `make check` green.
- [ ] PR titled `refactor(qa-engine): split custom_checks + collapse RuleEngine boilerplate (F018 F019)`.
- [ ] Mark F018, F019, F029, F067 as **RESOLVED**.

## Session 17 — F067 done-when (subset of the full plan above)

Parts A and B already shipped on prior branches. The Session 17 PR scope is **Part C only**.

- [ ] `app/qa_engine/tests/_helpers.py` exists with `valid_html(...)` exported.
- [ ] 11 new `test_<check>.py` files exist (10 factory + `test_css_support.py`), each with proper type hints and no file-level pyright pragma.
- [ ] `TestLinkValidation` and `TestLinkValidationCheck` both relocated to `test_link_validation.py` (preserve both class names).
- [ ] `app/qa_engine/tests/test_checks.py` deleted; `rg "test_checks"` outside `.git/` returns zero matches.
- [ ] `make check-full` green.
- [ ] Per-check pytest invocations from C6 all pass at parity with the pre-split test count.
- [ ] PR titled `test(qa-engine): split test_checks.py per-check (F067)`.
