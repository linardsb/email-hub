"""Offline, fixture-driven fidelity scoring for converter regression cases.

Phase 53 A3 (52.1-finish): wires :func:`app.design_sync.visual_scorer.score_fidelity`
to a real design reference, end-to-end, without a live Figma connection.

The live :class:`~app.design_sync.fidelity_service.VisualFidelityService` path
needs Figma credentials + image export. This module instead scores a converter
*case directory* (``data/debug/<case>/`` with committed ``structure.json`` +
``tokens.json``) against a committed reference PNG, so the metric can run in CI
as an **advisory** number.

Two pieces of registration make the score meaningful:

1. **Origin correction.** ``EmailSection.y_position`` values are absolute Figma
   canvas coords (e.g. case 7 starts at y≈3326). ``score_fidelity`` maps section
   bands by ``y_position / design_total_height``, so the absolute offset must be
   removed first or every band lands in the wrong place. We subtract the minimum
   non-null ``y_position`` from every section (``dataclasses.replace`` — the
   dataclass is frozen).
2. **Height scaling.** The rendered screenshot and the reference rarely share a
   pixel height; the caller scales the rendered PNG to the reference height so
   the two align at both ends (no cumulative gap-drift).

:func:`score_case_fidelity` itself does NOT render — the caller supplies both
PNGs — so it stays deterministic and Playwright-free, which is what lets a CI
test score two committed fixtures. :func:`render_case_png` is the canonical
Playwright recipe used to (re)generate the committed ``rendered_*.png`` fixture
and for live scoring; it is intentionally separate so CI never depends on it.
Before screenshotting, it rewrites the converter HTML's API asset URLs to
``file://`` URLs under ``<case_dir>/assets/`` (test-harness only — the shipped
HTML is untouched), so the screenshot contains the real images when the case's
node-keyed assets are present on disk.
"""

from __future__ import annotations

import io
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from app.design_sync.converter_service import ConversionResult

from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import EmailSection
from app.design_sync.tests.regression_runner import run_case_conversion
from app.design_sync.visual_scorer import FidelityScore, score_fidelity
from app.shared.imaging import safe_image_open

logger = get_logger(__name__)


@dataclass(frozen=True)
class CaseFidelityResult:
    """Advisory fidelity result for a converter case.

    ``score`` carries the per-section scores and the **min** overall (worst
    section dominates — see ``score_fidelity``). ``section_min`` and
    ``section_median`` are surfaced separately so a single broken band (e.g. an
    unresolved image) reads as an outlier rather than as the headline number.
    """

    score: FidelityScore
    full_image: float  # color similarity over the whole frame (no sections)
    section_min: float  # == score.overall when sections exist
    section_median: float  # robust to single-band outliers


def _origin_correct(sections: list[EmailSection]) -> list[EmailSection]:
    """Shift section ``y_position`` so the topmost section starts at 0.

    Figma ``y_position`` values are absolute canvas coords; ``score_fidelity``
    expects design-local coords. Sections with no ``y_position`` are passed
    through unchanged (they are skipped by the scorer anyway).
    """
    ys = [s.y_position for s in sections if s.y_position is not None]
    if not ys:
        return sections
    min_y = min(ys)
    return [
        s if s.y_position is None else replace(s, y_position=s.y_position - min_y) for s in sections
    ]


def score_case_fidelity(
    case_dir: Path,
    reference_png: bytes,
    rendered_png: bytes,
    *,
    blur_sigma: float = 0.0,
) -> CaseFidelityResult:
    """Score a converter case's rendered HTML against a design reference PNG.

    Runs the converter on ``case_dir`` to recover layout sections, origin-
    corrects them, scales the rendered screenshot to the reference height, and
    scores per-section + full-image color fidelity.

    Args:
        case_dir: A ``data/debug/<case>/`` directory with ``structure.json`` and
            ``tokens.json``.
        reference_png: PNG bytes of the design reference (the Figma frame export).
        rendered_png: PNG bytes of the rendered converter HTML.
        blur_sigma: Optional anti-aliasing smoothing (passed through; 0.0 = off).

    Returns:
        A :class:`CaseFidelityResult` with min/median/full-image scores.

    Raises:
        ValueError: if the case directory is missing ``structure.json`` /
            ``tokens.json``.
    """
    result = run_case_conversion(case_dir)
    if result is None or result.layout is None:
        raise ValueError(f"Case {case_dir} is missing structure.json/tokens.json")

    sections = _origin_correct(result.layout.sections)

    reference = safe_image_open(io.BytesIO(reference_png)).convert("RGB")
    rendered = safe_image_open(io.BytesIO(rendered_png)).convert("RGB")

    # Scale the rendered PNG to the reference height so bands align at both ends.
    if rendered.size != reference.size:
        rendered = rendered.resize(reference.size, Image.Resampling.LANCZOS)
    rendered_bytes = _to_png(rendered)

    section_score = score_fidelity(reference_png, rendered_bytes, sections, blur_sigma=blur_sigma)
    full_image_score = score_fidelity(reference_png, rendered_bytes, [], blur_sigma=blur_sigma)

    section_values = [s.ssim for s in section_score.sections]
    section_min = min(section_values) if section_values else full_image_score.overall
    section_median = (
        round(float(median(section_values)), 4) if section_values else full_image_score.overall
    )

    logger.info(
        "design_sync.case_fidelity_scored",
        case=case_dir.name,
        section_count=len(section_values),
        full_image=full_image_score.overall,
        section_min=section_min,
        section_median=section_median,
    )

    return CaseFidelityResult(
        score=section_score,
        full_image=full_image_score.overall,
        section_min=round(section_min, 4),
        section_median=section_median,
    )


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Converter asset URLs as emitted in the shipped HTML (node ids contain ':').
_ASSET_SRC_RE = re.compile(r'src="/api/v1/design-sync/assets/([^"]+?)\.png"')


def _rewrite_asset_srcs(html: str, case_dir: Path) -> str:
    """Rewrite API asset URLs to local ``file://`` URLs (test-harness only).

    The converter emits ``/api/v1/design-sync/assets/<node>.png`` srcs that only
    resolve behind the live API. For fixture rendering, point each at the case's
    on-disk ``assets/<node>.png`` (``:`` → ``_``, the export naming) so the
    screenshot contains the real images. Srcs with no on-disk asset are left
    untouched (they render as broken images, same as before).
    """
    assets_dir = case_dir / "assets"

    def _sub(match: re.Match[str]) -> str:
        node_id = match.group(1)
        asset = assets_dir / f"{node_id.replace(':', '_')}.png"
        if not asset.exists():
            return match.group(0)
        return f'src="{asset.resolve().as_uri()}"'

    return _ASSET_SRC_RE.sub(_sub, html)


# Rendering width used for the committed fixtures and the reference export.
_RENDER_WIDTH = 600


async def render_case_png(case_dir: Path, *, width: int = _RENDER_WIDTH) -> bytes:
    """Render a case's converter HTML to a full-page PNG (the fixture recipe).

    Canonical recipe used to regenerate the committed ``rendered_w600.png``
    fixture and for live (non-CI) scoring. Renders a plain page at the given
    viewport width with ``device_scale_factor=1`` — deliberately NOT a client
    rendering profile — so the pixels match what ``score_case_fidelity`` scores.

    Image srcs are rewritten via :func:`_rewrite_asset_srcs` and the HTML is
    served from a temporary ``file://`` document (Chromium refuses ``file://``
    subresources from a ``set_content``/about:blank page) so the case's
    committed node-keyed assets actually load. Requires Playwright + Chromium —
    never called from CI.

    Args:
        case_dir: A ``data/debug/<case>/`` directory with structure/tokens JSON.
        width: Viewport width in CSS px (email canvas width; default 600).

    Returns:
        Full-page PNG bytes.

    Raises:
        ValueError: if the case directory is missing structure/tokens JSON.
    """
    from playwright.async_api import async_playwright

    result: ConversionResult | None = run_case_conversion(case_dir)
    if result is None:
        raise ValueError(f"Case {case_dir} is missing structure.json/tokens.json")

    html = _rewrite_asset_srcs(result.html, case_dir)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context(
                viewport={"width": width, "height": 1000},
                device_scale_factor=1,
            )
            page = await context.new_page()
            with tempfile.TemporaryDirectory() as tmp:
                doc = Path(tmp) / "case.html"
                doc.write_text(html, encoding="utf-8")
                await page.goto(doc.as_uri(), wait_until="networkidle")
                png: bytes = await page.screenshot(full_page=True)
        finally:
            await browser.close()

    logger.info("design_sync.case_rendered", case=case_dir.name, width=width, bytes=len(png))
    return png
