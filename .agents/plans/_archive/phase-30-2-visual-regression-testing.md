# Plan: Phase 30.2 — Visual Regression Testing in CI

## Context
The emulator system (Phase 27.1) produces screenshots via Playwright (`app/rendering/local/runner.py::capture_screenshot`), and the calibration loop (Phase 27.4) compares against external providers — but there's no CI check that emulator outputs are *stable across code changes*. A refactor to the Gmail emulator rules could silently change all Gmail screenshots. Visual regression testing catches this: baseline screenshots are committed, and any deviation is flagged.

**Key existing infrastructure:**
- `app/rendering/visual_diff.py` — `run_odiff()` and `compare_images()` wrappers (ODiff via `npx odiff`)
- `app/rendering/local/runner.py` — `capture_screenshot(html, profile, output_dir) -> bytes`
- `app/rendering/local/profiles.py` — `CLIENT_PROFILES` dict with 14 profiles
- `app/rendering/local/emulators.py` — `EmailClientEmulator` chain-of-rules, `get_emulator(client_id)`
- `app/rendering/local/service.py` — `LocalRenderingProvider.render_screenshots()`
- `app/rendering/schemas.py` — existing diff/baseline schemas
- `app/rendering/exceptions.py` — existing exception hierarchy
- `app/ai/templates/library/*.html` — 15 golden templates (real production HTML)
- `app/core/config.py:227` — `RenderingConfig` with `visual_diff_threshold: float = 0.01`
- `pyproject.toml:217` — markers: `integration`, `benchmark` (add `visual_regression`)
- `Makefile:44` — `test` excludes `integration` and `benchmark` markers

## Files to Create/Modify

### New Files
- `app/rendering/tests/visual_regression/__init__.py` — package init
- `app/rendering/tests/visual_regression/schemas.py` — result dataclasses
- `app/rendering/tests/visual_regression/baseline_generator.py` — `BaselineGenerator` class
- `app/rendering/tests/visual_regression/regression_runner.py` — `VisualRegressionRunner` class
- `app/rendering/tests/visual_regression/conftest.py` — pytest fixtures
- `app/rendering/tests/visual_regression/test_regression.py` — unit tests
- `app/rendering/tests/visual_regression/baselines/.gitkeep` — baseline directory placeholder

### Modified Files
- `app/core/config.py` — add `visual_regression_threshold` to `RenderingConfig`
- `pyproject.toml` — add `visual_regression` marker
- `Makefile` — add `rendering-baselines` and `rendering-regression` targets
- `.gitattributes` — add PNG LFS tracking for baselines directory

## Implementation Steps

### Step 1: Config — Add visual regression threshold to `RenderingConfig`

In `app/core/config.py`, add to `RenderingConfig` class (after `visual_diff_threshold` line ~242):

```python
visual_regression_threshold: float = 0.5  # % pixel diff that flags regression
```

This is separate from `visual_diff_threshold` (which is the ODiff per-pixel sensitivity). The regression threshold is the overall percentage of different pixels allowed before a test fails.

### Step 2: Schemas — Create result dataclasses

**File:** `app/rendering/tests/visual_regression/__init__.py` — empty

**File:** `app/rendering/tests/visual_regression/schemas.py`

```python
"""Schemas for visual regression testing results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BaselineResult:
    """Result of generating a single baseline screenshot."""

    template_slug: str
    profile_id: str
    output_path: Path
    size_bytes: int


@dataclass(frozen=True)
class BaselineManifest:
    """Manifest of all generated baselines."""

    baselines: list[BaselineResult]
    template_slugs: list[str]
    profile_ids: list[str]
    emulator_versions: dict[str, str]  # profile_id -> version hash


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing one baseline against current emulator output."""

    template: str
    profile: str
    diff_percentage: float
    passed: bool
    diff_image_path: Path | None  # generated only on failure
    error: str | None = None  # if rendering/comparison failed


@dataclass
class RegressionReport:
    """Aggregate report from a visual regression run."""

    passed: bool
    threshold: float
    results: list[ComparisonResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # profiles with no baseline

    @property
    def failures(self) -> list[ComparisonResult]:
        return [r for r in self.results if not r.passed]

    @property
    def total(self) -> int:
        return len(self.results)
```

### Step 3: Baseline Generator

**File:** `app/rendering/tests/visual_regression/baseline_generator.py`

```python
"""Generate baseline screenshots for visual regression testing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.logging import get_logger
from app.rendering.local.emulators import _EMULATORS
from app.rendering.local.profiles import CLIENT_PROFILES, RenderingProfile
from app.rendering.local.runner import capture_screenshot
from app.rendering.tests.visual_regression.schemas import (
    BaselineManifest,
    BaselineResult,
)

logger = get_logger(__name__)

# 5 golden templates selected for visual diversity:
# 1. Simple text-only (minimal CSS)
# 2. Hero image + CTA (common marketing pattern)
# 3. Multi-column product grid (complex table layout)
# 4. Dark mode enabled (tests dark mode emulation)
# 5. Progressive enhancement (flexbox with MSO fallback)
REGRESSION_TEMPLATES: list[str] = [
    "minimal_text",
    "promotional_hero",
    "promotional_grid",
    "newsletter_2col",
    "transactional_receipt",
]

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "ai" / "templates" / "library"


def _load_template_html(slug: str) -> str:
    """Load template HTML from the golden template library."""
    path = TEMPLATE_DIR / f"{slug}.html"
    if not path.exists():
        msg = f"Template not found: {path}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")


def _emulator_version_hash(client_id: str) -> str:
    """Hash emulator rule names for drift detection."""
    emulator = _EMULATORS.get(client_id)
    if not emulator:
        return "no-emulator"
    rule_names = sorted(r.name for r in emulator.rules)
    return hashlib.sha256("|".join(rule_names).encode()).hexdigest()[:16]


class BaselineGenerator:
    """Generates baseline screenshots for visual regression testing."""

    async def generate_baselines(
        self,
        templates: list[str] | None = None,
        profiles: list[str] | None = None,
        output_dir: Path | None = None,
    ) -> BaselineManifest:
        """Generate baselines for each template × profile combination.

        Args:
            templates: Template slugs to render. Defaults to REGRESSION_TEMPLATES.
            profiles: Profile IDs to render. Defaults to all CLIENT_PROFILES.
            output_dir: Output directory. Defaults to baselines/ in this package.
        """
        template_slugs = templates or REGRESSION_TEMPLATES
        profile_ids = profiles or list(CLIENT_PROFILES.keys())
        baselines_dir = output_dir or (Path(__file__).parent / "baselines")
        baselines_dir.mkdir(parents=True, exist_ok=True)

        results: list[BaselineResult] = []
        emulator_versions: dict[str, str] = {}

        for slug in template_slugs:
            html = _load_template_html(slug)
            template_dir = baselines_dir / slug
            template_dir.mkdir(parents=True, exist_ok=True)

            for profile_id in profile_ids:
                profile = CLIENT_PROFILES.get(profile_id)
                if not profile:
                    logger.warning(
                        "visual_regression.unknown_profile",
                        profile=profile_id,
                    )
                    continue

                try:
                    image_bytes = await capture_screenshot(
                        html, profile, template_dir
                    )
                    output_path = template_dir / f"{profile_id}.png"
                    output_path.write_bytes(image_bytes)

                    results.append(
                        BaselineResult(
                            template_slug=slug,
                            profile_id=profile_id,
                            output_path=output_path,
                            size_bytes=len(image_bytes),
                        )
                    )

                    if profile.emulator_id and profile.emulator_id not in emulator_versions:
                        emulator_versions[profile.emulator_id] = (
                            _emulator_version_hash(profile.emulator_id)
                        )

                except Exception:
                    logger.exception(
                        "visual_regression.baseline_failed",
                        template=slug,
                        profile=profile_id,
                    )

        # Write manifest
        manifest_data = {
            "templates": template_slugs,
            "profiles": profile_ids,
            "emulator_versions": emulator_versions,
            "baseline_count": len(results),
        }
        manifest_path = baselines_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2), encoding="utf-8"
        )

        logger.info(
            "visual_regression.baselines_generated",
            count=len(results),
            templates=template_slugs,
            profiles=profile_ids,
        )

        return BaselineManifest(
            baselines=results,
            template_slugs=template_slugs,
            profile_ids=profile_ids,
            emulator_versions=emulator_versions,
        )
```

### Step 4: Regression Runner

**File:** `app/rendering/tests/visual_regression/regression_runner.py`

```python
"""Run visual regression tests against committed baselines."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rendering.local.profiles import CLIENT_PROFILES
from app.rendering.local.runner import capture_screenshot
from app.rendering.tests.visual_regression.baseline_generator import (
    REGRESSION_TEMPLATES,
    _load_template_html,
)
from app.rendering.tests.visual_regression.schemas import (
    ComparisonResult,
    RegressionReport,
)
from app.rendering.visual_diff import run_odiff

logger = get_logger(__name__)


class VisualRegressionRunner:
    """Runs visual regression tests by comparing current output against baselines."""

    def __init__(
        self,
        baseline_dir: Path | None = None,
        threshold: float | None = None,
    ) -> None:
        self.baseline_dir = baseline_dir or (Path(__file__).parent / "baselines")
        settings = get_settings()
        self.threshold = (
            threshold
            if threshold is not None
            else settings.rendering.visual_regression_threshold
        )

    def _load_manifest(self) -> dict[str, list[str]] | None:
        """Load manifest.json from baseline directory."""
        manifest_path = self.baseline_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "templates": data.get("templates", REGRESSION_TEMPLATES),
            "profiles": data.get("profiles", []),
        }

    async def run(
        self,
        profiles: list[str] | None = None,
    ) -> RegressionReport:
        """Run regression against all baselines.

        For each baseline PNG:
        1. Re-render the template through the same profile
        2. Compare with ODiff
        3. Flag if diff exceeds threshold

        Args:
            profiles: Subset of profiles to test. None = all with baselines.
        """
        manifest = self._load_manifest()
        if not manifest:
            logger.warning("visual_regression.no_manifest")
            return RegressionReport(passed=True, threshold=self.threshold)

        template_slugs = manifest["templates"]
        all_profile_ids = profiles or manifest["profiles"]

        results: list[ComparisonResult] = []
        skipped: list[str] = []

        for slug in template_slugs:
            template_dir = self.baseline_dir / slug
            if not template_dir.exists():
                skipped.append(slug)
                continue

            try:
                html = _load_template_html(slug)
            except FileNotFoundError:
                logger.warning(
                    "visual_regression.template_missing",
                    template=slug,
                )
                skipped.append(slug)
                continue

            for profile_id in all_profile_ids:
                baseline_path = template_dir / f"{profile_id}.png"
                if not baseline_path.exists():
                    skipped.append(f"{slug}/{profile_id}")
                    continue

                profile = CLIENT_PROFILES.get(profile_id)
                if not profile:
                    skipped.append(f"{slug}/{profile_id}")
                    continue

                result = await self._compare_single(
                    slug, profile_id, html, profile, baseline_path
                )
                results.append(result)

        passed = all(r.passed for r in results)

        report = RegressionReport(
            passed=passed,
            threshold=self.threshold,
            results=results,
            skipped=skipped,
        )

        if not passed:
            for failure in report.failures:
                logger.error(
                    "visual_regression.regression_detected",
                    template=failure.template,
                    profile=failure.profile,
                    diff_percentage=failure.diff_percentage,
                    diff_image=str(failure.diff_image_path),
                )

        logger.info(
            "visual_regression.run_complete",
            passed=passed,
            total=report.total,
            failures=len(report.failures),
            skipped=len(skipped),
        )

        return report

    async def _compare_single(
        self,
        template_slug: str,
        profile_id: str,
        html: str,
        profile: "RenderingProfile",
        baseline_path: Path,
    ) -> ComparisonResult:
        """Compare a single baseline against current emulator output."""
        from app.rendering.local.profiles import RenderingProfile as _RP  # noqa: F811

        try:
            with tempfile.TemporaryDirectory(prefix="vr_") as tmpdir:
                output_dir = Path(tmpdir)
                current_bytes = await capture_screenshot(html, profile, output_dir)

                current_path = output_dir / f"{profile_id}_current.png"
                current_path.write_bytes(current_bytes)

                diff_output = output_dir / f"{profile_id}_diff.png"

                result = await run_odiff(
                    baseline_path,
                    current_path,
                    diff_output,
                    threshold=0.01,  # per-pixel sensitivity
                )

                passed = result.diff_percentage <= self.threshold

                # Persist diff image only on failure
                diff_image_path: Path | None = None
                if not passed and result.diff_image:
                    # Save diff to a persistent location
                    diffs_dir = self.baseline_dir / "_diffs"
                    diffs_dir.mkdir(parents=True, exist_ok=True)
                    diff_image_path = diffs_dir / f"{template_slug}__{profile_id}.png"
                    diff_image_path.write_bytes(result.diff_image)

                return ComparisonResult(
                    template=template_slug,
                    profile=profile_id,
                    diff_percentage=result.diff_percentage,
                    passed=passed,
                    diff_image_path=diff_image_path,
                )

        except Exception as exc:
            logger.exception(
                "visual_regression.comparison_error",
                template=template_slug,
                profile=profile_id,
            )
            return ComparisonResult(
                template=template_slug,
                profile=profile_id,
                diff_percentage=100.0,
                passed=False,
                diff_image_path=None,
                error=str(exc),
            )
```

### Step 5: Pytest Fixtures

**File:** `app/rendering/tests/visual_regression/conftest.py`

```python
"""Fixtures for visual regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rendering.tests.visual_regression.regression_runner import (
    VisualRegressionRunner,
)

BASELINES_DIR = Path(__file__).parent / "baselines"


@pytest.fixture
def visual_baselines() -> Path:
    """Path to the committed baselines directory."""
    return BASELINES_DIR


@pytest.fixture
def regression_runner(visual_baselines: Path) -> VisualRegressionRunner:
    """Initialized runner with default config."""
    return VisualRegressionRunner(baseline_dir=visual_baselines)
```

### Step 6: Unit Tests

**File:** `app/rendering/tests/visual_regression/test_regression.py`

Tests use mocked `capture_screenshot` and `run_odiff` to avoid Playwright/ODiff dependency in CI unit tests. The actual regression run via `make rendering-regression` will use real Playwright.

```python
"""Visual regression testing — unit tests (mocked Playwright/ODiff)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.rendering.tests.visual_regression.baseline_generator import (
    BaselineGenerator,
    REGRESSION_TEMPLATES,
)
from app.rendering.tests.visual_regression.regression_runner import (
    VisualRegressionRunner,
)
from app.rendering.tests.visual_regression.schemas import (
    ComparisonResult,
    RegressionReport,
)
from app.rendering.visual_diff import DiffResult

# Minimal 1×1 white PNG for mocking
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.visual_regression
class TestBaselineGenerator:
    """Tests for BaselineGenerator."""

    @patch(
        "app.rendering.tests.visual_regression.baseline_generator.capture_screenshot",
        new_callable=AsyncMock,
    )
    async def test_generates_baselines_for_templates_and_profiles(
        self, mock_capture: AsyncMock
    ) -> None:
        mock_capture.return_value = _TINY_PNG

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            gen = BaselineGenerator()
            manifest = await gen.generate_baselines(
                templates=["minimal_text"],
                profiles=["gmail_web"],
                output_dir=output,
            )

            assert len(manifest.baselines) == 1
            assert manifest.baselines[0].template_slug == "minimal_text"
            assert manifest.baselines[0].profile_id == "gmail_web"
            assert (output / "minimal_text" / "gmail_web.png").exists()

            # Manifest JSON written
            manifest_path = output / "manifest.json"
            assert manifest_path.exists()
            data = json.loads(manifest_path.read_text())
            assert data["baseline_count"] == 1

    @patch(
        "app.rendering.tests.visual_regression.baseline_generator.capture_screenshot",
        new_callable=AsyncMock,
    )
    async def test_skips_unknown_profile(self, mock_capture: AsyncMock) -> None:
        mock_capture.return_value = _TINY_PNG

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BaselineGenerator()
            manifest = await gen.generate_baselines(
                templates=["minimal_text"],
                profiles=["nonexistent_profile"],
                output_dir=Path(tmpdir),
            )
            assert len(manifest.baselines) == 0

    @patch(
        "app.rendering.tests.visual_regression.baseline_generator.capture_screenshot",
        new_callable=AsyncMock,
    )
    async def test_continues_on_capture_failure(
        self, mock_capture: AsyncMock
    ) -> None:
        mock_capture.side_effect = [OSError("display fail"), _TINY_PNG]

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BaselineGenerator()
            manifest = await gen.generate_baselines(
                templates=["minimal_text"],
                profiles=["gmail_web", "apple_mail"],
                output_dir=Path(tmpdir),
            )
            # One failed, one succeeded
            assert len(manifest.baselines) == 1
            assert manifest.baselines[0].profile_id == "apple_mail"


@pytest.mark.visual_regression
class TestRegressionRunner:
    """Tests for VisualRegressionRunner."""

    async def test_passes_when_baselines_match(self) -> None:
        """All baselines match current output → passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            baselines = Path(tmpdir)
            # Create a baseline
            tpl_dir = baselines / "minimal_text"
            tpl_dir.mkdir()
            (tpl_dir / "gmail_web.png").write_bytes(_TINY_PNG)
            # Create manifest
            (baselines / "manifest.json").write_text(
                json.dumps({
                    "templates": ["minimal_text"],
                    "profiles": ["gmail_web"],
                })
            )

            runner = VisualRegressionRunner(
                baseline_dir=baselines, threshold=0.5
            )

            with (
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.capture_screenshot",
                    new_callable=AsyncMock,
                    return_value=_TINY_PNG,
                ),
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.run_odiff",
                    new_callable=AsyncMock,
                    return_value=DiffResult(
                        identical=True,
                        diff_percentage=0.0,
                        diff_image=None,
                        pixel_count=0,
                        changed_regions=[],
                    ),
                ),
            ):
                report = await runner.run()

            assert report.passed is True
            assert report.total == 1
            assert len(report.failures) == 0

    async def test_detects_regression_above_threshold(self) -> None:
        """Modified emulator rule → detects regression for affected clients."""
        with tempfile.TemporaryDirectory() as tmpdir:
            baselines = Path(tmpdir)
            tpl_dir = baselines / "promotional_hero"
            tpl_dir.mkdir()
            (tpl_dir / "gmail_web.png").write_bytes(_TINY_PNG)
            (baselines / "manifest.json").write_text(
                json.dumps({
                    "templates": ["promotional_hero"],
                    "profiles": ["gmail_web"],
                })
            )

            runner = VisualRegressionRunner(
                baseline_dir=baselines, threshold=0.5
            )

            diff_image_bytes = b"fake-diff-png"
            with (
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.capture_screenshot",
                    new_callable=AsyncMock,
                    return_value=_TINY_PNG,
                ),
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.run_odiff",
                    new_callable=AsyncMock,
                    return_value=DiffResult(
                        identical=False,
                        diff_percentage=2.3,
                        diff_image=diff_image_bytes,
                        pixel_count=1500,
                        changed_regions=[],
                    ),
                ),
            ):
                report = await runner.run()

            assert report.passed is False
            assert len(report.failures) == 1
            assert report.failures[0].diff_percentage == 2.3
            assert report.failures[0].diff_image_path is not None

    async def test_skips_profile_with_no_baseline(self) -> None:
        """New emulator rule with no baseline → skipped (not failed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            baselines = Path(tmpdir)
            (baselines / "manifest.json").write_text(
                json.dumps({
                    "templates": ["minimal_text"],
                    "profiles": ["brand_new_client"],
                })
            )

            runner = VisualRegressionRunner(
                baseline_dir=baselines, threshold=0.5
            )
            report = await runner.run()

            assert report.passed is True
            assert report.total == 0
            assert "minimal_text" in report.skipped

    async def test_threshold_override(self) -> None:
        """Threshold override via constructor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            baselines = Path(tmpdir)
            tpl_dir = baselines / "minimal_text"
            tpl_dir.mkdir()
            (tpl_dir / "gmail_web.png").write_bytes(_TINY_PNG)
            (baselines / "manifest.json").write_text(
                json.dumps({
                    "templates": ["minimal_text"],
                    "profiles": ["gmail_web"],
                })
            )

            # High threshold — 2.3% diff should pass
            runner = VisualRegressionRunner(
                baseline_dir=baselines, threshold=5.0
            )

            with (
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.capture_screenshot",
                    new_callable=AsyncMock,
                    return_value=_TINY_PNG,
                ),
                patch(
                    "app.rendering.tests.visual_regression.regression_runner.run_odiff",
                    new_callable=AsyncMock,
                    return_value=DiffResult(
                        identical=False,
                        diff_percentage=2.3,
                        diff_image=None,
                        pixel_count=100,
                        changed_regions=[],
                    ),
                ),
            ):
                report = await runner.run()

            assert report.passed is True

    async def test_no_manifest_returns_pass(self) -> None:
        """No manifest.json → empty pass (first run, no baselines yet)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = VisualRegressionRunner(
                baseline_dir=Path(tmpdir), threshold=0.5
            )
            report = await runner.run()
            assert report.passed is True
            assert report.total == 0

    async def test_report_properties(self) -> None:
        """RegressionReport properties work correctly."""
        r1 = ComparisonResult(
            template="a", profile="b", diff_percentage=0.0,
            passed=True, diff_image_path=None,
        )
        r2 = ComparisonResult(
            template="c", profile="d", diff_percentage=5.0,
            passed=False, diff_image_path=Path("/tmp/diff.png"),
        )
        report = RegressionReport(
            passed=False, threshold=0.5, results=[r1, r2],
        )
        assert report.total == 2
        assert len(report.failures) == 1
        assert report.failures[0].template == "c"
```

### Step 7: Baselines Directory

**File:** `app/rendering/tests/visual_regression/baselines/.gitkeep` — empty file

The `baselines/` directory holds committed PNGs. Initially empty — populated via `make rendering-baselines`.

### Step 8: Register Pytest Marker

In `pyproject.toml`, add to the `markers` list (after the `benchmark` line):

```toml
    "visual_regression: Visual regression tests requiring Playwright + ODiff (run with: make rendering-regression)",
```

### Step 9: Makefile Targets

Add after the `bench:` target block (around line 49):

```makefile
rendering-baselines: ## Regenerate visual regression baselines (manual, destructive)
	uv run python -c "import asyncio; from app.rendering.tests.visual_regression.baseline_generator import BaselineGenerator; asyncio.run(BaselineGenerator().generate_baselines())"

rendering-regression: ## Run visual regression tests against baselines
	uv run pytest app/rendering/tests/visual_regression/ -v -m visual_regression
```

### Step 10: Update `make test` exclusion

The existing `make test` command (line 45) excludes `integration` and `benchmark`. Add `visual_regression`:

```makefile
test: ## Run backend unit tests
	uv run pytest -v -m "not integration and not benchmark and not visual_regression"
```

### Step 11: .gitattributes — LFS tracking (optional)

Add to `.gitattributes` (create if missing):

```
app/rendering/tests/visual_regression/baselines/**/*.png filter=lfs diff=lfs merge=lfs -text
```

If Git LFS is not available, baselines commit directly. The 5 templates × 14 profiles = 70 PNGs at ~50-100KB each ≈ 3.5-7MB total, manageable without LFS.

### Step 12: Add `_diffs/` to .gitignore

Add to `.gitignore`:

```
# Visual regression diff images (generated on failure)
app/rendering/tests/visual_regression/baselines/_diffs/
```

## Security Checklist

This feature adds **no new API endpoints** — it is purely a test-time tool:
- **No routes** — all code is under `tests/` or invoked via `make` targets
- **No user input** — reads only from committed baselines and golden templates
- **No external calls** — ODiff runs locally, Playwright renders local HTML files
- **No secrets** — baselines are static PNGs, no credentials involved
- **No SQL** — no database access in the regression pipeline
- **Subprocess safety** — `run_odiff()` uses `asyncio.create_subprocess_exec` (not shell=True), args are `Path` objects (no injection risk)

## Verification

- [ ] `make check` passes — visual regression tests excluded from `make test` by default
- [ ] `make rendering-baselines` generates baselines in `app/rendering/tests/visual_regression/baselines/`
- [ ] `make rendering-regression` runs visual regression tests and passes against fresh baselines
- [ ] Intentionally modify a Gmail emulator rule → `make rendering-regression` detects regression with diff image in `_diffs/`
- [ ] Restore rule → `make rendering-regression` passes again
- [ ] `pytest -m visual_regression` runs only visual regression tests
- [ ] `make test` does NOT run visual regression tests
- [ ] New marker registered: `pytest --markers | grep visual_regression`
