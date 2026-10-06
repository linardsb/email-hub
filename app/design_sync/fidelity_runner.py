"""Score any converter path's output through the CE-1 fidelity gate (CE-27, #467).

``fidelity_gate.score_cases`` converts each case itself through the template
path. ``score_conversion`` takes a ``ConversionResult`` from any path instead,
checks that its section ids are exactly the baseline's ids for the case
(``SectionIdMismatch`` before any render) and that each is a layout section,
then renders and scores it with the gate's own renderer and scorer.
``check_conversion`` compares the score with the committed baseline for that
one case.

Docs: ``docs/fidelity-gate.md`` (Scoring another converter path).
"""

from __future__ import annotations

import asyncio
from collections import Counter

from app.design_sync.converter_service import ConversionResult
from app.design_sync.fidelity_gate import (
    CaseBaseline,
    FidelityBaseline,
    GateError,
    GateReport,
    ScoreRun,
    compare,
    current_commit,
    current_environment,
    frame_width,
    load_baseline,
    render_case_sections,
    score_rendered_case,
)


class SectionIdMismatch(GateError):
    """A result's section ids differ from the fidelity baseline's ids for the case."""


def baseline_node_ids(case: CaseBaseline) -> frozenset[str]:
    """Node ids the gate saw marked: scored plus skipped (``unmarked`` never was)."""
    return frozenset(case.sections.keys() | case.skipped.keys())


def assert_section_ids(case: str, result: ConversionResult, baseline: FidelityBaseline) -> None:
    """Raise unless ``result`` marks exactly the baseline's sections for ``case``, once each."""
    base = baseline.cases.get(case)
    if base is None:
        raise GateError(f"case {case}: not in the fidelity baseline")
    expected = baseline_node_ids(base)
    got = set(result.section_node_ids)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    duplicates = sorted(n for n, k in Counter(result.section_node_ids).items() if k > 1)
    if missing or extra or duplicates:
        groups = [
            f"{name}: {ids}"
            for name, ids in (("missing", missing), ("extra", extra), ("duplicates", duplicates))
            if ids
        ]
        raise SectionIdMismatch(
            f"case {case}: section ids differ from the fidelity baseline ({'; '.join(groups)}): "
            "fix the path to mark exactly the baseline's sections rather than re-stamping over it"
        )


def score_conversion(
    case: str, result: ConversionResult, *, baseline: FidelityBaseline | None = None
) -> CaseBaseline:
    """Render and score ``result`` for ``case`` (pinned image only: needs Chromium)."""
    baseline = baseline if baseline is not None else load_baseline()
    assert_section_ids(case, result, baseline)
    if result.layout is None:
        raise GateError(f"case {case}: conversion has no layout")
    in_layout = {s.node_id for s in result.layout.sections}
    absent = sorted(set(result.section_node_ids) - in_layout)
    if absent:
        raise GateError(f"case {case}: marked section ids not in the layout: {absent}")
    width = frame_width(result.layout.sections)
    rendered = asyncio.run(render_case_sections(case, result, width))
    return score_rendered_case(case, rendered)


def check_conversion(
    case: str, result: ConversionResult, *, baseline: FidelityBaseline | None = None
) -> GateReport:
    """Score ``result`` and compare it with the committed baseline for ``case`` only."""
    baseline = baseline if baseline is not None else load_baseline()
    scored = score_conversion(case, result, baseline=baseline)
    run = ScoreRun(environment=current_environment(), commit=current_commit(), cases={case: scored})
    one_case = baseline.model_copy(
        update={"cases": {c: v for c, v in baseline.cases.items() if c == case}}
    )
    return compare(one_case, run)
