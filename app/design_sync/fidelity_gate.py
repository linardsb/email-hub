# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Per-section fidelity gate for the converter cases (CE-1, #419).

Renders each case's converter output in a pinned Chromium, cuts the render
into sections by the converter's own ``<!-- section:section_<i> -->`` markers,
cuts the committed 1x design reference by each section's Figma box, and scores
every pair with the colour-aware metric (``visual_scorer._color_similarity``).
Scores are keyed by the section's Figma node id (``ConversionResult.
section_node_ids``), so a grouping change that renumbers markers does not move
a baseline onto a different section.

``check`` fails when any section drops more than the baseline margin below its
committed score, or when a section is lost or new. ``restamp`` rewrites the
baseline and appends a reason to its ``stamps`` history; it runs only in the
pinned image (``make fidelity-restamp``). Unlike the advisory A3 scorer
(``fidelity_case_scorer``), crops follow the render's own section boxes, so a
height change in one section cannot shift the crops of the others.

Docs: ``docs/fidelity-gate.md``.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.design_sync.converter_service import ConversionResult
from app.design_sync.fidelity_case_scorer import (
    _rewrite_asset_srcs,  # pyright: ignore[reportPrivateUsage]
)
from app.design_sync.figma.layout_analyzer import EmailSection
from app.design_sync.tests.manifest_schema import CaseManifest
from app.design_sync.tests.regression_runner import load_case_manifest, run_case_conversion
from app.design_sync.visual_scorer import (
    _MIN_SECTION_HEIGHT_PX,  # pyright: ignore[reportPrivateUsage]
    _color_similarity,  # pyright: ignore[reportPrivateUsage]
)
from app.shared.imaging import safe_image_open

logger = get_logger(__name__)

REPO = Path(__file__).resolve().parent.parent.parent
DEBUG_DIR = REPO / "data/debug"
BASELINE_PATH = DEBUG_DIR / "fidelity_baseline.json"
OUT_DIR = REPO / ".tmpscratch/fidelity-gate"
REFERENCE_NAME = "reference_1x.png"
DEFAULT_MARGIN = 0.005
PINNED_ENV = "pinned"

Box = tuple[int, int, int, int]  # x, y, width, height


class GateError(AppError):
    """A gate precondition failed (missing input, wrong environment, bad reason)."""


# ── Baseline schema ──────────────────────────────────────────────


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionBaseline(_Strict):
    marker: str
    score: float
    design_box: Box


class CaseBaseline(_Strict):
    design: str
    frame_width: int
    reference: str  # repo-relative path
    sections: dict[str, SectionBaseline]  # keyed by Figma node id
    skipped: dict[str, str] = Field(default_factory=dict)  # node id -> reason
    unmarked: dict[str, str] = Field(default_factory=dict)  # node id -> section type


class Environment(_Strict):
    image: str
    playwright: str


class Stamp(_Strict):
    date: str
    commit: str
    reason: str = Field(min_length=1)
    cases: list[str]


class FidelityBaseline(_Strict):
    schema_version: int = 1
    margin: float
    environment: Environment
    stamps: list[Stamp] = Field(default_factory=list)
    cases: dict[str, CaseBaseline] = Field(default_factory=dict)


class ScoreRun(_Strict):
    """One scoring pass: what ``check`` writes and ``restamp --from`` reads."""

    environment: Environment
    commit: str
    cases: dict[str, CaseBaseline]


# ── Geometry and scoring (no browser) ────────────────────────────


def frame_origin(sections: list[EmailSection]) -> tuple[float, float]:
    """Top-left of the email frame: the minimum section x and y (Figma canvas coords)."""
    xs = [s.x_position for s in sections if s.x_position is not None]
    ys = [s.y_position for s in sections if s.y_position is not None]
    return (min(xs) if xs else 0.0, min(ys) if ys else 0.0)


def frame_width(sections: list[EmailSection]) -> int:
    """Frame width in px: the widest section."""
    return round(max((s.width if s.width is not None else 0.0) for s in sections))


def design_box(
    section: EmailSection, origin: tuple[float, float], ref_size: tuple[int, int]
) -> Box | None:
    """The section's box in the 1x reference, clipped to it; None without geometry."""
    if section.x_position is None or section.y_position is None:
        return None
    x = round(section.x_position - origin[0])
    y = round(section.y_position - origin[1])
    width = section.width if section.width is not None else 0.0
    height = section.height if section.height is not None else 0.0
    x2 = min(x + round(width), ref_size[0])
    y2 = min(y + round(height), ref_size[1])
    x, y = max(x, 0), max(y, 0)
    return (x, y, max(x2 - x, 0), max(y2 - y, 0))


def _crop(img: Image.Image, box: Box) -> Image.Image:
    x, y, w, h = box
    return img.crop((x, y, x + w, y + h))


def score_section(reference: Image.Image, rendered: Image.Image, dbox: Box, rbox: Box) -> float:
    """Colour similarity of one section: render crop resized to the design crop's size."""
    design_crop = _crop(reference, dbox)
    render_crop = _crop(rendered, rbox).resize(design_crop.size, Image.Resampling.LANCZOS)
    a = np.asarray(design_crop.convert("RGB"), dtype=np.float64)
    b = np.asarray(render_crop.convert("RGB"), dtype=np.float64)
    return round(_color_similarity(a, b), 4)


def unmarked_sections(result: ConversionResult) -> dict[str, str]:
    """Layout sections that carry no section marker (absorbed spacers, dividers)."""
    if result.layout is None:
        return {}
    marked = set(result.section_node_ids)
    return {
        s.node_id: s.section_type.value for s in result.layout.sections if s.node_id not in marked
    }


@dataclass(frozen=True)
class RenderedCase:
    """A case's render: full-page PNG plus each marker's page-coordinate box."""

    png: bytes
    boxes: dict[str, Box]  # marker (section_<i>) -> render box
    result: ConversionResult


def score_rendered_case(
    case: str,
    rendered: RenderedCase,
    *,
    dump_crops: Path | None = None,
) -> CaseBaseline:
    """Score every marked section of a rendered case against its 1x reference."""
    result = rendered.result
    if result.layout is None:
        raise GateError(f"case {case}: conversion has no layout")
    case_dir = DEBUG_DIR / case
    ref_path = case_dir / REFERENCE_NAME
    width = frame_width(result.layout.sections)
    reference = safe_image_open(ref_path).convert("RGB")
    if reference.width != width:
        raise GateError(
            f"case {case}: {ref_path.name} is {reference.width}px wide, frame is {width}px"
        )
    render = safe_image_open(io.BytesIO(rendered.png)).convert("RGB")
    by_node = {s.node_id: s for s in result.layout.sections}
    origin = frame_origin(result.layout.sections)

    sections: dict[str, SectionBaseline] = {}
    skipped: dict[str, str] = {}
    for idx, node_id in enumerate(result.section_node_ids):
        marker = f"section_{idx}"
        rbox = rendered.boxes.get(marker)
        dbox = design_box(by_node[node_id], origin, reference.size)
        if rbox is None:
            skipped[node_id] = f"{marker}: no render box"
        elif rbox[2] < 1 or rbox[3] < 1:
            skipped[node_id] = f"{marker}: render box empty ({rbox[2]}x{rbox[3]})"
        elif dbox is None:
            skipped[node_id] = f"{marker}: section has no design position"
        elif dbox[2] < _MIN_SECTION_HEIGHT_PX or dbox[3] < _MIN_SECTION_HEIGHT_PX:
            skipped[node_id] = (
                f"{marker}: design crop {dbox[2]}x{dbox[3]} < {_MIN_SECTION_HEIGHT_PX}px"
            )
        else:
            score = score_section(reference, render, dbox, rbox)
            sections[node_id] = SectionBaseline(marker=marker, score=score, design_box=dbox)
            if dump_crops is not None:
                _dump_crop_pair(dump_crops / case, node_id, reference, render, dbox, rbox)

    manifest: CaseManifest = load_case_manifest(case_dir)
    logger.info(
        "design_sync.fidelity_gate_scored",
        case=case,
        scored=len(sections),
        skipped=len(skipped),
        section_min=min((s.score for s in sections.values()), default=None),
    )
    return CaseBaseline(
        design=manifest.name,
        frame_width=width,
        reference=str(ref_path.relative_to(REPO)),
        sections=sections,
        skipped=skipped,
        unmarked=unmarked_sections(result),
    )


def _dump_crop_pair(
    out: Path, node_id: str, reference: Image.Image, render: Image.Image, dbox: Box, rbox: Box
) -> None:
    """Write design (left) and resized render (right) crops side by side."""
    design_crop = _crop(reference, dbox)
    render_crop = _crop(render, rbox).resize(design_crop.size, Image.Resampling.LANCZOS)
    pair = Image.new("RGB", (design_crop.width * 2 + 8, design_crop.height), "magenta")
    pair.paste(design_crop, (0, 0))
    pair.paste(render_crop, (design_crop.width + 8, 0))
    out.mkdir(parents=True, exist_ok=True)
    pair.save(out / f"{node_id.replace(':', '_')}.png")


# ── Compare ──────────────────────────────────────────────────────

Status = Literal["pass", "improved", "drop", "lost", "new"]
FAILING: frozenset[str] = frozenset({"drop", "lost", "new"})


@dataclass(frozen=True)
class SectionRow:
    case: str
    node_id: str
    marker: str
    baseline: float | None
    now: float | None
    status: Status
    detail: str = ""

    @property
    def delta(self) -> float | None:
        if self.baseline is None or self.now is None:
            return None
        return round(self.now - self.baseline, 4)


@dataclass(frozen=True)
class GateReport:
    margin: float
    rows: list[SectionRow] = field(default_factory=list[SectionRow])

    @property
    def failures(self) -> list[SectionRow]:
        return [r for r in self.rows if r.status in FAILING]

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    def format(self, *, verdict: bool = True) -> str:
        """Table of every section; ``verdict=False`` for a re-stamp's before/after view."""
        lines = [
            f"{'case':>4}  {'node':<10} {'marker':<11} {'base':>6} {'now':>6} {'delta':>7}  status"
        ]
        for r in self.rows:
            base = f"{r.baseline:.4f}" if r.baseline is not None else "-"
            now = f"{r.now:.4f}" if r.now is not None else "-"
            delta = f"{r.delta:+.4f}" if r.delta is not None else "-"
            detail = f"  {r.detail}" if r.detail else ""
            lines.append(
                f"{r.case:>4}  {r.node_id:<10} {r.marker:<11} {base:>6} {now:>6} {delta:>7}  "
                f"{r.status}{detail}"
            )
        if verdict:
            result = f"FAIL ({len(self.failures)} sections)" if self.failed else "PASS"
            lines.append(f"margin {self.margin}  ->  {result}")
        return "\n".join(lines)


def compare(baseline: FidelityBaseline, run: ScoreRun) -> GateReport:
    """Per-section comparison of a scoring run against the baseline."""
    margin = baseline.margin
    rows: list[SectionRow] = []
    for case in sorted(baseline.cases.keys() | run.cases.keys(), key=_case_sort_key):
        base = baseline.cases.get(case)
        now = run.cases.get(case)
        base_secs = base.sections if base else {}
        now_secs = now.sections if now else {}
        for node_id in sorted(base_secs.keys() | now_secs.keys()):
            b, n = base_secs.get(node_id), now_secs.get(node_id)
            if b is not None and n is not None:
                drop = round(b.score - n.score, 4)
                if drop > margin:
                    status: Status = "drop"
                elif -drop > margin:
                    status = "improved"
                else:
                    status = "pass"
                rows.append(SectionRow(case, node_id, n.marker, b.score, n.score, status))
            elif b is not None:
                why = (now.skipped.get(node_id, "") if now else "case not scored") or "absent"
                rows.append(
                    SectionRow(
                        case,
                        node_id,
                        b.marker,
                        b.score,
                        None,
                        "lost",
                        f"section lost or re-keyed ({why}): re-stamp needed",
                    )
                )
            elif n is not None:
                rows.append(
                    SectionRow(
                        case,
                        node_id,
                        n.marker,
                        None,
                        n.score,
                        "new",
                        "new section: re-stamp needed",
                    )
                )
    return GateReport(margin=margin, rows=rows)


def _case_sort_key(case: str) -> tuple[int, str]:
    return (int(case), case) if case.isdigit() else (1 << 30, case)


# ── Render (browser) ─────────────────────────────────────────────

# Pairs each ``section:X`` comment with its ``/section:X`` close, keeps only
# pairs not nested in another pair, and returns the Range box between the two
# comments in page coordinates.
_SECTION_BOXES_JS = r"""
() => {
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  const open = {}; const out = {}; let depth = 0;
  while (walker.nextNode()) {
    const text = walker.currentNode.nodeValue;
    let m = text.match(/^\s*section:(section_\d+)\s*$/);
    if (m) { open[m[1]] = [walker.currentNode, depth]; depth++; continue; }
    m = text.match(/^\s*\/section:(section_\d+)\s*$/);
    if (m && open[m[1]]) {
      depth--;
      const [start, d] = open[m[1]];
      if (d !== 0) continue;
      const range = document.createRange();
      range.setStartAfter(start); range.setEndBefore(walker.currentNode);
      const b = range.getBoundingClientRect();
      out[m[1]] = [b.left + window.scrollX, b.top + window.scrollY, b.width, b.height];
    }
  }
  return out;
}
"""


async def render_case_sections(case: str, result: ConversionResult, width: int) -> RenderedCase:
    """Render a case's output at ``width`` CSS px (DPR 1) and measure every section's box."""
    from playwright.async_api import Route, async_playwright

    html = _rewrite_asset_srcs(result.html, DEBUG_DIR / case)

    async def _local_only(route: Route) -> None:
        if route.request.url.startswith("file://"):
            await route.continue_()
        else:
            await route.abort()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context(
                viewport={"width": width, "height": 1000}, device_scale_factor=1
            )
            page = await context.new_page()
            await page.route("**/*", _local_only)
            with tempfile.TemporaryDirectory() as tmp:
                doc = Path(tmp) / "case.html"
                doc.write_text(html, encoding="utf-8")
                await page.goto(doc.as_uri(), wait_until="networkidle")
                await page.evaluate("document.fonts.ready.then(() => true)")
                raw: dict[str, list[float]] = await page.evaluate(_SECTION_BOXES_JS)
                png: bytes = await page.screenshot(full_page=True)
        finally:
            await browser.close()
    boxes: dict[str, Box] = {
        k: (round(v[0]), round(v[1]), round(v[2]), round(v[3])) for k, v in raw.items()
    }
    return RenderedCase(png=png, boxes=boxes, result=result)


# ── Entry points ─────────────────────────────────────────────────


def gated_cases() -> list[str]:
    """Case ids that have a committed 1x reference."""
    return sorted(
        (p.parent.name for p in DEBUG_DIR.glob(f"*/{REFERENCE_NAME}")), key=_case_sort_key
    )


def current_environment() -> Environment:
    from importlib.metadata import version

    return Environment(
        image=os.environ.get("FIDELITY_IMAGE", "unpinned"), playwright=version("playwright")
    )


def current_commit() -> str:
    """Short HEAD sha: from ``FIDELITY_COMMIT`` (set by make) or git."""
    sha = os.environ.get("FIDELITY_COMMIT", "").strip()
    if sha:
        return sha
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    return proc.stdout.strip() or "unknown"


def load_baseline(path: Path = BASELINE_PATH) -> FidelityBaseline:
    if not path.exists():
        raise GateError(f'no baseline at {path}: run make fidelity-restamp REASON="..."')
    return FidelityBaseline.model_validate_json(path.read_text())


def score_cases(cases: list[str], *, dump_crops: bool = False) -> ScoreRun:
    """Render and score the given cases (pinned image only: needs Chromium)."""
    import asyncio

    crops = OUT_DIR / "crops" if dump_crops else None
    scored: dict[str, CaseBaseline] = {}
    for case in cases:
        result = run_case_conversion(DEBUG_DIR / case)
        if result is None or result.layout is None:
            raise GateError(f"case {case}: missing structure.json/tokens.json")
        width = frame_width(result.layout.sections)
        rendered = asyncio.run(render_case_sections(case, result, width))
        scored[case] = score_rendered_case(case, rendered, dump_crops=crops)
    return ScoreRun(environment=current_environment(), commit=current_commit(), cases=scored)


def write_run(run: ScoreRun) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "scores.json"
    path.write_text(run.model_dump_json(indent=1) + "\n")
    return path


def check(*, cases: list[str] | None = None, dump_crops: bool = False) -> GateReport:
    """Score every baselined case (plus any new gated case) and compare."""
    baseline = load_baseline()
    wanted = cases or sorted(set(baseline.cases) | set(gated_cases()), key=_case_sort_key)
    run = score_cases(wanted, dump_crops=dump_crops)
    write_run(run)
    if cases:
        baseline = baseline.model_copy(
            update={"cases": {c: v for c, v in baseline.cases.items() if c in cases}}
        )
    return compare(baseline, run)


def restamp(
    reason: str,
    *,
    cases: list[str] | None = None,
    from_path: Path | None = None,
    path: Path = BASELINE_PATH,
) -> tuple[FidelityBaseline, GateReport]:
    """Rewrite the baseline for ``cases`` (default: all gated) and log the stamp."""
    if not reason.strip():
        raise GateError("a non-empty --reason is required")
    if os.environ.get("FIDELITY_GATE_ENV") != PINNED_ENV:
        raise GateError(
            'restamp runs only in the pinned image: use make fidelity-restamp REASON="..."'
        )
    old = (
        load_baseline(path)
        if path.exists()
        else FidelityBaseline(margin=DEFAULT_MARGIN, environment=current_environment())
    )
    if from_path is not None:
        run = ScoreRun.model_validate_json(from_path.read_text())
        if run.environment.image != old.environment.image:
            raise GateError(
                f"{from_path} was scored in {run.environment.image}, "
                f"baseline expects {old.environment.image}"
            )
        if cases:
            run = run.model_copy(update={"cases": {c: run.cases[c] for c in cases}})
    else:
        run = score_cases(cases or gated_cases())
    stamped = sorted(run.cases, key=_case_sort_key)
    before = old.model_copy(
        update={"cases": {c: v for c, v in old.cases.items() if c in run.cases}}
    )
    report = compare(before, run)
    new = old.model_copy(
        update={
            "environment": run.environment,
            "cases": dict(
                sorted({**old.cases, **run.cases}.items(), key=lambda kv: _case_sort_key(kv[0]))
            ),
            "stamps": [
                *old.stamps,
                Stamp(
                    date=datetime.now(UTC).date().isoformat(),
                    commit=current_commit(),
                    reason=reason.strip(),
                    cases=stamped,
                ),
            ],
        }
    )
    path.write_text(json.dumps(new.model_dump(mode="json"), indent=1) + "\n")
    logger.info("design_sync.fidelity_baseline_stamped", cases=stamped, reason=reason.strip())
    return new, report
