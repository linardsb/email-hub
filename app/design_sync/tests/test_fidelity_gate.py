# pyright: reportPrivateUsage=false
"""CE-1 (#419) per-section fidelity gate.

Unit tests (no browser) run in ``make test`` and the CI Test step: the
``section_node_ids`` marker mapping on the real cases, crop geometry, scoring,
``compare`` rules, the baseline schema, committed fixtures and the re-stamp
guards. ``test_fidelity_gate_holds_baseline`` renders in Chromium and runs only
in the pinned image (``make fidelity-gate``).
"""

from __future__ import annotations

import html
import io
import os
import re
import subprocess
from functools import cache
from pathlib import Path

import pytest
from PIL import Image, ImageOps
from pydantic import ValidationError

from app.design_sync.converter_service import ConversionResult
from app.design_sync.fidelity_case_scorer import _ASSET_SRC_RE
from app.design_sync.fidelity_gate import (
    BASELINE_PATH,
    DEBUG_DIR,
    REPO,
    Box,
    CaseBaseline,
    Environment,
    FidelityBaseline,
    GateError,
    RenderedCase,
    ScoreRun,
    SectionBaseline,
    Stamp,
    check,
    compare,
    design_box,
    frame_origin,
    frame_width,
    gated_cases,
    load_baseline,
    restamp,
    score_rendered_case,
    score_section,
)
from app.design_sync.figma.layout_analyzer import EmailSection
from app.design_sync.tests.regression_runner import run_case_conversion

CASES = ["5", "6", "7", "8", "9", "10", "reframe"]
_MARKER_RE = re.compile(r"<!-- (/?)section:section_(\d+) -->")
_ENV = Environment(image="img:1", playwright="1.0")


@cache
def _convert(case: str) -> ConversionResult:
    result = run_case_conversion(DEBUG_DIR / case)
    if result is None or result.layout is None:
        pytest.skip(f"case {case}: structure.json/tokens.json not present")
    return result


def _layout_sections(case: str) -> list[EmailSection]:
    layout = _convert(case).layout
    assert layout is not None
    return list(layout.sections)


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace-collapsed and lowercased."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip().lower()


# ── section_node_ids (Task 2) ────────────────────────────────────


@pytest.mark.parametrize("case", CASES)
class TestSectionNodeIds:
    def test_markers_are_flat(self, case: str) -> None:
        depth = 0
        for m in _MARKER_RE.finditer(_convert(case).html):
            depth += -1 if m.group(1) else 1
            assert 0 <= depth <= 1, f"case {case}: nested section marker at section_{m.group(2)}"
        assert depth == 0

    def test_one_marker_per_node_id(self, case: str) -> None:
        result = _convert(case)
        opened = {int(m.group(2)) for m in _MARKER_RE.finditer(result.html) if not m.group(1)}
        assert opened == set(range(len(result.section_node_ids)))

    def test_node_ids_are_unique_layout_sections(self, case: str) -> None:
        result = _convert(case)
        layout_ids = {s.node_id for s in _layout_sections(case)}
        assert len(set(result.section_node_ids)) == len(result.section_node_ids)
        assert set(result.section_node_ids) <= layout_ids

    def test_marker_wraps_its_own_node(self, case: str) -> None:
        """Marker ``section_i`` holds the text of ``section_node_ids[i]`` (order, not just set)."""
        result = _convert(case)
        by_id = {s.node_id: s for s in _layout_sections(case)}
        checked = 0
        for i, node_id in enumerate(result.section_node_ids):
            m = re.search(
                rf"<!-- section:section_{i} -->(.*?)<!-- /section:section_{i} -->",
                result.html,
                re.DOTALL,
            )
            assert m is not None
            body = _text(m.group(1))
            texts = [t for t in (_text(x.content) for x in by_id[node_id].texts) if t]
            if not body or not texts:  # image-only render or text-less section
                continue
            assert any(t[:20] in body for t in texts), f"section_{i} does not hold {node_id}"
            checked += 1
        assert checked >= 4

    def test_unmarked_set_matches_baseline(self, case: str) -> None:
        if not BASELINE_PATH.exists():
            pytest.skip("no fidelity baseline committed yet")
        baseline = load_baseline()
        if case not in baseline.cases:
            pytest.skip(f"case {case} not in the fidelity baseline")
        marked = set(_convert(case).section_node_ids)
        unmarked = {
            s.node_id: s.section_type.value
            for s in _layout_sections(case)
            if s.node_id not in marked
        }
        assert unmarked == baseline.cases[case].unmarked, "unmarked set changed: re-stamp needed"


# ── Geometry and scoring (Task 7 b, c) ───────────────────────────


class TestDesignBox:
    def test_case6_peel_row_members_side_by_side(self) -> None:
        sections = _layout_sections("6")
        by_id = {s.node_id: s for s in sections}
        origin = frame_origin(sections)
        width = frame_width(sections)
        boxes = [
            design_box(by_id[n], origin, (width, 10_000))
            for n in ("2833:1455", "2833:1460", "2833:1465", "2833:1470")
        ]
        assert all(b is not None for b in boxes)
        xs = [b[0] for b in boxes if b]
        assert xs == sorted(xs) and len(set(xs)) == 4
        assert len({b[1] for b in boxes if b}) == 1
        assert all(0 <= b[0] and b[0] + b[2] <= width for b in boxes if b)

    @pytest.mark.parametrize("case", CASES)
    def test_every_box_inside_frame(self, case: str) -> None:
        sections = _layout_sections(case)
        origin = frame_origin(sections)
        width = frame_width(sections)
        for s in sections:
            assert s.x_position is not None and s.width is not None
            assert s.x_position - origin[0] >= 0
            assert round(s.x_position - origin[0] + s.width) <= width, s.node_id

    def test_clips_to_reference(self) -> None:
        s = _layout_sections("5")[-1]
        origin = frame_origin(_layout_sections("5"))
        box = design_box(s, origin, (600, 10))
        assert box is not None and box[3] == 0


class TestScoreSection:
    def test_identity_and_inversion(self) -> None:
        ref = Image.open(DEBUG_DIR / "5/reference_1x.png").convert("RGB")
        box = (0, 0, ref.width, 400)
        assert score_section(ref, ref, box, box) == 1.0
        assert score_section(ref, ImageOps.invert(ref), box, box) < 0.5

    def test_render_crop_resized_to_design_crop(self) -> None:
        ref = Image.open(DEBUG_DIR / "5/reference_1x.png").convert("RGB")
        dbox = (0, 0, 300, 200)
        doubled = ref.crop((0, 0, 300, 200)).resize((600, 400), Image.Resampling.LANCZOS)
        assert score_section(ref, doubled, dbox, (0, 0, 600, 400)) > 0.98

    def test_rendered_case_scores_reference_as_render(self) -> None:
        """Real case 5 conversion; the reference itself stands in as the render."""
        result = _convert("5")
        sections = _layout_sections("5")
        ref = Image.open(DEBUG_DIR / "5/reference_1x.png").convert("RGB")
        origin = frame_origin(sections)
        by_id = {s.node_id: s for s in sections}
        boxes: dict[str, Box] = {}
        for i, node in enumerate(result.section_node_ids):
            box = design_box(by_id[node], origin, ref.size)
            assert box is not None
            boxes[f"section_{i}"] = box
        boxes.pop("section_0")  # a marker that rendered no box is skipped, not dropped
        buf = io.BytesIO()
        ref.save(buf, format="PNG")
        scored = score_rendered_case("5", RenderedCase(buf.getvalue(), boxes, result))
        first = result.section_node_ids[0]
        assert scored.skipped == {first: "section_0: no render box"}
        assert set(scored.sections) == set(result.section_node_ids) - {first}
        assert all(s.score == 1.0 for s in scored.sections.values())
        assert scored.frame_width == 600 and scored.unmarked == {}


# ── compare (Task 7 a) ───────────────────────────────────────────


def _case(**scores: float) -> CaseBaseline:
    return CaseBaseline(
        design="d",
        frame_width=600,
        reference="r.png",
        sections={
            n: SectionBaseline(marker=f"section_{i}", score=v, design_box=(0, 0, 1, 1))
            for i, (n, v) in enumerate(scores.items())
        },
    )


def _baseline(**scores: float) -> FidelityBaseline:
    return FidelityBaseline(margin=0.005, environment=_ENV, cases={"5": _case(**scores)})


def _run(**scores: float) -> ScoreRun:
    return ScoreRun(environment=_ENV, commit="abc", cases={"5": _case(**scores)})


class TestCompare:
    def test_drop_beyond_margin_fails(self) -> None:
        report = compare(_baseline(a=0.9), _run(a=0.8949))
        assert report.failed and report.rows[0].status == "drop"

    def test_drop_equal_to_margin_passes(self) -> None:
        report = compare(_baseline(a=0.9), _run(a=0.895))
        assert not report.failed and report.rows[0].status == "pass"

    def test_lost_section_fails(self) -> None:
        report = compare(_baseline(a=0.9, b=0.9), _run(a=0.9))
        assert report.failed
        assert [(r.node_id, r.status) for r in report.failures] == [("b", "lost")]

    def test_new_section_fails(self) -> None:
        report = compare(_baseline(a=0.9), _run(a=0.9, b=0.5))
        assert [(r.node_id, r.status) for r in report.failures] == [("b", "new")]

    def test_improvement_passes_and_is_reported(self) -> None:
        report = compare(_baseline(a=0.8), _run(a=0.9))
        assert not report.failed and report.rows[0].status == "improved"
        assert "improved" in report.format() and "PASS" in report.format()

    def test_case_missing_from_run_loses_every_section(self) -> None:
        run = ScoreRun(environment=_ENV, commit="abc", cases={})
        report = compare(_baseline(a=0.9, b=0.9), run)
        assert {r.status for r in report.rows} == {"lost"}


# ── Baseline schema and committed fixtures (Task 7 d, e, f) ──────


class TestBaselineSchema:
    def test_round_trip(self) -> None:
        b = _baseline(a=0.9).model_copy(
            update={"stamps": [Stamp(date="2026-09-30", commit="abc", reason="r", cases=["5"])]}
        )
        assert FidelityBaseline.model_validate_json(b.model_dump_json()) == b

    def test_stamp_requires_reason(self) -> None:
        with pytest.raises(ValidationError):
            Stamp.model_validate({"date": "d", "commit": "c", "cases": []})
        with pytest.raises(ValidationError):
            Stamp(date="d", commit="c", reason="", cases=[])

    def test_unknown_field_rejected(self) -> None:
        data = _baseline(a=0.9).model_dump()
        data["extra"] = 1
        with pytest.raises(ValidationError):
            FidelityBaseline.model_validate(data)


def _tracked(paths: list[str]) -> set[str]:
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "--", *paths],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    return set(out.split())


class TestCommittedFixtures:
    def test_baseline_covers_every_case(self) -> None:
        baseline = load_baseline()
        assert set(baseline.cases) == set(gated_cases())
        assert set(CASES) <= set(baseline.cases)
        assert baseline.margin > 0
        assert baseline.stamps, "baseline has no stamp history"

    @pytest.mark.parametrize("case", CASES)
    def test_inputs_and_reference_committed(self, case: str) -> None:
        baseline = load_baseline().cases[case]
        tracked = _tracked([f"data/debug/{case}"])
        for name in ("structure.json", "tokens.json", "reference_1x.png"):
            assert f"data/debug/{case}/{name}" in tracked, f"case {case}: {name} not committed"
        assert baseline.reference == f"data/debug/{case}/reference_1x.png"
        with Image.open(REPO / baseline.reference) as ref:
            assert ref.width == baseline.frame_width == frame_width(_layout_sections(case))

    @pytest.mark.parametrize("case", CASES)
    def test_every_referenced_asset_committed(self, case: str) -> None:
        nodes = {m.group(1).replace(":", "_") for m in _ASSET_SRC_RE.finditer(_convert(case).html)}
        tracked = _tracked([f"data/debug/{case}/assets"])
        missing = sorted(n for n in nodes if f"data/debug/{case}/assets/{n}.png" not in tracked)
        assert not missing, f"case {case}: assets referenced but not committed: {missing}"


# ── Re-stamp guards (Task 9) ─────────────────────────────────────


class TestRestamp:
    def test_blank_reason_refused(self) -> None:
        with pytest.raises(GateError, match="reason"):
            restamp("  ")

    def test_outside_pinned_env_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIDELITY_GATE_ENV", raising=False)
        with pytest.raises(GateError, match="make fidelity-restamp"):
            restamp("reason")

    def test_from_scores_file_appends_stamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FIDELITY_GATE_ENV", "pinned")
        monkeypatch.setenv("FIDELITY_COMMIT", "feed123")
        path = tmp_path / "baseline.json"
        path.write_text(_baseline(a=0.9).model_dump_json())
        scores = tmp_path / "scores.json"
        scores.write_text(_run(a=0.95).model_dump_json())

        new, report = restamp("CI stamp", from_path=scores, path=path)

        assert report.rows[0].status == "improved"
        saved = FidelityBaseline.model_validate_json(path.read_text())
        assert saved == new
        assert saved.cases["5"].sections["a"].score == 0.95
        assert [(s.commit, s.reason, s.cases) for s in saved.stamps] == [
            ("feed123", "CI stamp", ["5"])
        ]

    def test_from_scores_file_other_image_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FIDELITY_GATE_ENV", "pinned")
        path = tmp_path / "baseline.json"
        path.write_text(_baseline(a=0.9).model_dump_json())
        other = _run(a=0.9).model_copy(
            update={"environment": Environment(image="x", playwright="1")}
        )
        scores = tmp_path / "scores.json"
        scores.write_text(other.model_dump_json())
        with pytest.raises(GateError, match="scored in x"):
            restamp("r", from_path=scores, path=path)


# ── The gate (pinned image only, Task 10) ────────────────────────


@pytest.mark.fidelity_gate
@pytest.mark.skipif(
    os.environ.get("FIDELITY_GATE_ENV") != "pinned",
    reason="fidelity gate renders only in the pinned Playwright image: run make fidelity-gate",
)
def test_fidelity_gate_holds_baseline() -> None:
    report = check()
    print(report.format())  # noqa: T201
    assert not report.failed, report.format()
