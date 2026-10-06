"""CE-27 (#467) case runner into the CE-1 fidelity gate.

Unit tests (no browser) run in ``make test`` and the CI Test step: the section
id rule on the real cases, the named mismatch error and its position before
rendering, and the ``check_conversion`` wiring. ``TestRunnerReproducesGate``
renders in Chromium and runs only in the pinned image (``make fidelity-gate``).
"""

from __future__ import annotations

import os
from dataclasses import replace
from functools import cache

import pytest

from app.design_sync import fidelity_runner
from app.design_sync.converter_service import ConversionResult
from app.design_sync.fidelity_gate import (
    DEBUG_DIR,
    CaseBaseline,
    Environment,
    FidelityBaseline,
    GateError,
    RenderedCase,
    SectionBaseline,
    gated_cases,
    load_baseline,
    score_cases,
)
from app.design_sync.fidelity_runner import (
    SectionIdMismatch,
    assert_section_ids,
    baseline_node_ids,
    check_conversion,
    score_conversion,
)
from app.design_sync.tests.regression_runner import run_case_conversion

CASES = ["5", "6", "7", "8", "9", "10", "reframe"]
_ENV = Environment(image="img:1", playwright="1.0")


@cache
def _convert(case: str) -> ConversionResult:
    result = run_case_conversion(DEBUG_DIR / case)
    if result is None or result.layout is None:
        pytest.skip(f"case {case}: structure.json/tokens.json not present")
    return result


def _case(*node_ids: str) -> CaseBaseline:
    return CaseBaseline(
        design="d",
        frame_width=600,
        reference="r.png",
        sections={
            n: SectionBaseline(marker=f"section_{i}", score=1.0, design_box=(0, 0, 1, 1))
            for i, n in enumerate(node_ids)
        },
    )


def _baseline(**cases: CaseBaseline) -> FidelityBaseline:
    return FidelityBaseline(margin=0.005, environment=_ENV, cases=cases)


class TestBaselineNodeIds:
    def test_includes_skipped_excludes_unmarked(self) -> None:
        case = _case("a").model_copy(update={"skipped": {"b": "x"}, "unmarked": {"c": "spacer"}})
        assert baseline_node_ids(case) == frozenset({"a", "b"})


class TestAssertSectionIds:
    @pytest.mark.parametrize("case", CASES)
    def test_template_path_matches_baseline(self, case: str) -> None:
        assert_section_ids(case, _convert(case), load_baseline())

    def test_missing_id_named(self) -> None:
        result = _convert("5")
        dropped = result.section_node_ids[0]
        bad = replace(result, section_node_ids=result.section_node_ids[1:])
        with pytest.raises(SectionIdMismatch, match="missing") as exc:
            assert_section_ids("5", bad, load_baseline())
        assert dropped in str(exc.value)

    def test_extra_id_named(self) -> None:
        baseline = load_baseline()
        (unmarked,) = baseline.cases["9"].unmarked
        result = _convert("9")
        bad = replace(result, section_node_ids=(*result.section_node_ids, unmarked))
        with pytest.raises(SectionIdMismatch, match="extra") as exc:
            assert_section_ids("9", bad, baseline)
        assert unmarked in str(exc.value)

    def test_duplicate_id_named(self) -> None:
        result = _convert("5")
        first = result.section_node_ids[0]
        bad = replace(result, section_node_ids=(*result.section_node_ids, first))
        with pytest.raises(SectionIdMismatch, match="duplicate") as exc:
            assert_section_ids("5", bad, load_baseline())
        assert first in str(exc.value)

    def test_uncased_baseline_raises(self) -> None:
        baseline = _baseline(**{"5": _case("a")})
        with pytest.raises(GateError, match="not in the fidelity baseline") as exc:
            assert_section_ids("6", _convert("6"), baseline)
        assert not isinstance(exc.value, SectionIdMismatch)


class TestScoreConversion:
    def test_no_layout_raises(self) -> None:
        bad = replace(_convert("5"), layout=None)
        with pytest.raises(GateError, match="no layout"):
            score_conversion("5", bad, baseline=load_baseline())

    def test_mismatch_raises_before_render(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def boom(case: str, result: ConversionResult, width: int) -> RenderedCase:
            raise AssertionError("rendered")

        monkeypatch.setattr(fidelity_runner, "render_case_sections", boom)
        result = _convert("5")
        bad = replace(result, section_node_ids=result.section_node_ids[1:])
        with pytest.raises(SectionIdMismatch):
            score_conversion("5", bad, baseline=load_baseline())

    def test_layout_missing_marked_section_raises_before_render(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(case: str, result: ConversionResult, width: int) -> RenderedCase:
            raise AssertionError("rendered")

        monkeypatch.setattr(fidelity_runner, "render_case_sections", boom)
        result = _convert("5")
        assert result.layout is not None
        dropped = result.section_node_ids[0]
        sections = [s for s in result.layout.sections if s.node_id != dropped]
        bad = replace(result, layout=replace(result.layout, sections=sections))
        with pytest.raises(GateError, match="not in the layout") as exc:
            score_conversion("5", bad, baseline=load_baseline())
        assert dropped in str(exc.value)


class TestCheckConversion:
    def test_check_conversion_wraps_compare(self, monkeypatch: pytest.MonkeyPatch) -> None:
        committed = load_baseline().cases["5"]

        def fake_score(
            case: str, result: ConversionResult, *, baseline: FidelityBaseline | None = None
        ) -> CaseBaseline:
            return committed

        monkeypatch.setattr(fidelity_runner, "score_conversion", fake_score)
        report = check_conversion("5", _convert("5"))
        assert len(report.rows) == len(committed.sections)
        assert {r.status for r in report.rows} == {"pass"}
        assert {r.case for r in report.rows} == {"5"}


# ── Runner == gate (pinned image only) ───────────────────────────


@pytest.mark.fidelity_gate
@pytest.mark.skipif(
    os.environ.get("FIDELITY_GATE_ENV") != "pinned",
    reason="fidelity gate renders only in the pinned Playwright image: run make fidelity-gate",
)
class TestRunnerReproducesGate:
    @pytest.mark.parametrize("case", gated_cases())
    def test_reproduces_gate_and_baseline(self, case: str, monkeypatch: pytest.MonkeyPatch) -> None:
        scored: list[CaseBaseline] = []
        real_score = fidelity_runner.score_conversion

        def spy(
            case: str, result: ConversionResult, *, baseline: FidelityBaseline | None = None
        ) -> CaseBaseline:
            scored.append(real_score(case, result, baseline=baseline))
            return scored[-1]

        monkeypatch.setattr(fidelity_runner, "score_conversion", spy)
        report = check_conversion(case, _convert(case))
        (ours,) = scored
        assert ours == score_cases([case]).cases[case]
        print(report.format())  # noqa: T201
        assert not report.failed, report.format()
