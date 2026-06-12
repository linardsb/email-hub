# pyright: reportPrivateUsage=false
"""Phase 53 A3 — the fidelity metric, run end-to-end against a real design.

These tests are **ADVISORY**: they prove the metric *runs* against a committed
real reference (case 5 / maap) and that it *discriminates* a wrong render from
the real one. They do NOT gate CI on a fidelity threshold — case 5 is an
under-segmenter (renders 11 of 13 target bands), so the number it yields is *a*
number, not a verdict; per the Phase 53 plan the metric stays advisory until
≥2 fixtures (incl. an over-segmenter) are wired. They also do NOT call
Playwright — both PNGs are committed fixtures:

  - ``email-templates/training_HTML/for_converter_engine/maap/visual_design.png``
      the Figma frame export (1200x5036, scale 2)
  - ``data/debug/5/rendered_w600.png``
      the current converter HTML rendered at width 600 with the case's six
      node-keyed assets resolved (see ``_rewrite_asset_srcs``)

Regenerate the rendered fixture after converter changes with::

    uv run python -c "
    import asyncio
    from pathlib import Path
    from app.design_sync.fidelity_case_scorer import render_case_png
    case = Path('data/debug/5')
    (case / 'rendered_w600.png').write_bytes(asyncio.run(render_case_png(case)))
    "
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from app.design_sync.fidelity_case_scorer import score_case_fidelity

# Repo root: app/design_sync/tests/ -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASE5_DIR = _REPO_ROOT / "data" / "debug" / "5"
_REFERENCE_PNG = (
    _REPO_ROOT
    / "email-templates"
    / "training_HTML"
    / "for_converter_engine"
    / "maap"
    / "visual_design.png"
)
_RENDERED_PNG = _CASE5_DIR / "rendered_w600.png"

# Skip cleanly if the fixtures are not present (e.g. a sparse checkout).
_FIXTURES_PRESENT = (
    _CASE5_DIR.joinpath("structure.json").exists()
    and _CASE5_DIR.joinpath("tokens.json").exists()
    and _REFERENCE_PNG.exists()
    and _RENDERED_PNG.exists()
)

pytestmark = pytest.mark.skipif(
    not _FIXTURES_PRESENT,
    reason="case 5 fidelity fixtures (structure/tokens/reference/rendered) not present",
)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCaseFiveFidelityRuns:
    def test_metric_runs_and_returns_sane_floats(self) -> None:
        """End-to-end: convert case 5, register, score against the real reference."""
        ref = _REFERENCE_PNG.read_bytes()
        rendered = _RENDERED_PNG.read_bytes()

        result = score_case_fidelity(_CASE5_DIR, ref, rendered)

        # Every advisory number is a sane similarity in [0, 1].
        for value in (result.full_image, result.section_min, result.section_median):
            assert 0.0 <= value <= 1.0

        # Origin correction produced real section bands (case 5 renders ~11;
        # the band *count* is the A2 gate's job, not this test's).
        assert len(result.score.sections) >= 5
        # MIN is the worst band; median is never below it.
        assert result.section_median >= result.section_min


class TestCaseFiveFidelityDiscriminates:
    def test_color_corrupted_render_scores_lower(self) -> None:
        """A deliberately wrong (hue-inverted) render scores LOWER than the real one.

        Proves the metric is color-aware and actually discriminates: inverting
        every pixel's colour clashes the hue of every band, so full-image and
        median fidelity both drop well below the real render's.
        """
        ref = _REFERENCE_PNG.read_bytes()
        rendered_img = Image.open(_RENDERED_PNG).convert("RGB")

        real = score_case_fidelity(_CASE5_DIR, ref, _png(rendered_img))
        wrong = score_case_fidelity(_CASE5_DIR, ref, _png(ImageOps.invert(rendered_img)))

        # Full-image and median both drop — and by a real margin, not noise.
        assert wrong.full_image < real.full_image - 0.1
        assert wrong.section_median < real.section_median - 0.1
        # Min also drops (corrupting every band cannot help the worst band).
        assert wrong.section_min <= real.section_min
