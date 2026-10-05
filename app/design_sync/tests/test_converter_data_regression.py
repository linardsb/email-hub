"""Data-driven converter regression tests.

Each ``data/debug/<case>/manifest.yaml`` defines a regression case.
Tests are auto-discovered and parametrized — adding a new case requires
zero code changes: just drop a directory with ``manifest.yaml`` +
``structure.json`` + ``tokens.json``.

Run all cases::

    make converter-data-regression

Run a single case::

    make converter-data-regression CASE=reframe
"""

from __future__ import annotations

import dataclasses
import html as html_lib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark.structures import ParameterSet
from lxml import etree

from app.design_sync.converter_service import ConversionResult
from app.design_sync.diagnose.report import (
    _node_from_dict,
    dump_structure_to_json,
    load_structure_from_json,
    load_tokens_from_json,
)
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.protocol import DesignNode, DesignNodeType
from app.design_sync.services._serialization import serialize_node
from app.design_sync.tests.known_failures import apply_known_failures, known_failure_marks
from app.design_sync.tests.ladder_harness import (
    SEMANTIC_UNDERCOUNT_CASES,
    SEMANTIC_UNDERCOUNT_REASON,
    LadderRow,
    compute_all_ladders,
    discover_ladder_case_ids,
    drift_view,
    ladder_to_dict,
    load_ladder_snapshot,
    load_target_sections,
)
from app.design_sync.tests.manifest_schema import CaseManifest
from app.design_sync.tests.regression_runner import (
    collect_metrics,
    compute_slot_fill_rate,
    discover_cases,
    load_case_manifest,
    normalize_html,
    run_case_conversion,
    write_report,
)

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"

# Matches ALL MSO conditional blocks (if mso, if !mso, if gte mso, etc.)
_MSO_BLOCK_RE = re.compile(r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", re.DOTALL)
# Also the non-MSO wrapper: <!--[if !mso]><!--> ... <!--<![endif]-->
_NON_MSO_WRAPPER_RE = re.compile(
    r"<!--\[if\s+!mso\]><!-->(.*?)<!--<!\[endif\]-->",
    re.DOTALL,
)


def _strip_mso_blocks(html: str) -> str:
    """Remove all MSO conditional blocks for structural analysis.

    Unwrap the non-MSO wrappers first: ``_MSO_BLOCK_RE`` also matches a whole
    ``<!--[if !mso]><!-->…<!--<![endif]-->`` wrapper and would drop its content.
    """
    result = _NON_MSO_WRAPPER_RE.sub(r"\1", html)
    return _MSO_BLOCK_RE.sub("", result)


def test_strip_mso_blocks_keeps_non_mso_content() -> None:
    """CE-11: a VML-paired anchor survives; the VML block is dropped."""
    wrapped = (
        '<td><!--[if mso]><v:roundrect href="#"><center>Go</center></v:roundrect>'
        '<![endif]--><!--[if !mso]><!--><a href="#">Go</a><!--<![endif]--></td>'
    )
    assert _strip_mso_blocks(wrapped) == '<td><a href="#">Go</a></td>'


# ── Fixtures ─────────────────────────────────────────────────────


def _discover_ids() -> list[str]:
    """Return case directory names for parametrize IDs."""
    return [p.name for p in discover_cases(_DEBUG_DIR)]


def _converter_case_ids() -> list[str]:
    """Return case IDs that have converter inputs (not reference_only)."""
    ids: list[str] = []
    for p in discover_cases(_DEBUG_DIR):
        manifest = load_case_manifest(p)
        if not manifest.reference_only and (p / "structure.json").exists():
            ids.append(p.name)
    return ids


def _load_case(case_name: str) -> tuple[Path, CaseManifest, str]:
    """Load manifest and resolve HTML source for assertions.

    For ``reference_only`` cases or when converter inputs are missing,
    assertions run against ``expected.html`` instead of converter output.
    """
    case_dir = _DEBUG_DIR / case_name
    manifest = load_case_manifest(case_dir)

    if manifest.reference_only:
        expected_path = case_dir / "expected.html"
        if not expected_path.exists():
            pytest.skip(f"{case_name}: reference_only but no expected.html")
        return case_dir, manifest, expected_path.read_text()

    result = run_case_conversion(case_dir)
    if result is None:
        expected_path = case_dir / "expected.html"
        if expected_path.exists():
            return case_dir, manifest, expected_path.read_text()
        pytest.skip(f"{case_name}: missing structure.json/tokens.json and no expected.html")

    return case_dir, manifest, result.html


@pytest.fixture(params=_discover_ids())
def case(request: pytest.FixtureRequest) -> tuple[Path, CaseManifest, str]:
    """Parametrized fixture yielding (case_dir, manifest, html) for all cases."""
    apply_known_failures(request, request.param)
    return _load_case(request.param)


@pytest.fixture(params=_converter_case_ids())
def converter_case(request: pytest.FixtureRequest) -> tuple[Path, CaseManifest, str]:
    """Parametrized fixture for cases with actual converter output only."""
    case_name: str = request.param
    apply_known_failures(request, case_name)
    case_dir = _DEBUG_DIR / case_name
    manifest = load_case_manifest(case_dir)
    result = run_case_conversion(case_dir)
    if result is None:
        pytest.skip(f"{case_name}: missing converter inputs")
    return case_dir, manifest, result.html


@pytest.fixture(params=_converter_case_ids())
def case_with_result(
    request: pytest.FixtureRequest,
) -> tuple[Path, CaseManifest, ConversionResult]:
    """Parametrized fixture that requires actual converter output."""
    case_name: str = request.param
    apply_known_failures(request, case_name)
    case_dir = _DEBUG_DIR / case_name
    manifest = load_case_manifest(case_dir)
    result = run_case_conversion(case_dir)
    if result is None:
        pytest.skip(f"{case_name}: missing structure.json/tokens.json")
    return case_dir, manifest, result


# ── Universal assertions (converter output only) ─────────────────


class TestUniversalChecks:
    """Structural checks on converter output (not reference HTML)."""

    def test_no_nested_p_tags(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        _, _, html = converter_case
        assert "<p><p>" not in html, "Nested <p> tags found"
        assert "</p></p>" not in html, "Nested closing </p> tags found"

    def test_no_empty_sections(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        _, _, html = converter_case
        empty = re.findall(
            r"<!-- section:section_\d+ -->\s*<!-- section:section_\d+ -->",
            html,
        )
        assert not empty, f"Empty sections found: {len(empty)} consecutive markers"

    def test_valid_html_structure(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        _, _, html = converter_case
        parser = etree.HTMLParser(recover=True)
        doc = etree.fromstring(html, parser)
        assert doc is not None, "lxml failed to parse HTML"
        # Table balance after stripping MSO conditionals. Allow +-1 tolerance
        # because hybrid responsive patterns can have closing tags from
        # conditional branches that aren't perfectly paired after stripping.
        cleaned = _strip_mso_blocks(html)
        tables_open = len(re.findall(r"<table[\s>]", cleaned, re.IGNORECASE))
        tables_close = len(re.findall(r"</table>", cleaned, re.IGNORECASE))
        assert abs(tables_open - tables_close) <= 1, (
            f"Unbalanced tables: {tables_open} open vs {tables_close} close"
        )

    def test_no_bare_layout_divs(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        """No <div> with layout CSS that isn't the hybrid responsive column pattern."""
        _, _, html = converter_case
        cleaned = _strip_mso_blocks(html)
        # Only flag float or display:block — inline-block columns are valid
        layout_divs = re.findall(
            r"<div[^>]+style=\"[^\"]*(?:float\s*:\s*(?!none)|display\s*:\s*block)",
            cleaned,
            re.IGNORECASE,
        )
        assert not layout_divs, (
            f"Found {len(layout_divs)} <div> with layout CSS "
            f"(should use table/tr/td): {layout_divs[0][:80]}..."
        )

    def test_mso_conditionals_balanced(
        self, converter_case: tuple[Path, CaseManifest, str]
    ) -> None:
        _, _, html = converter_case
        # Count all <!--[if ...]> and <![endif]--> pairs
        opens = len(re.findall(r"<!--\[if\s", html))
        closes = len(re.findall(r"<!\[endif\]-->", html))
        assert opens == closes, f"Unbalanced MSO conditionals: {opens} opens vs {closes} closes"

    def test_images_have_dimensions(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        _, _, html = converter_case
        imgs = re.findall(r"<img\s[^>]*>", html, re.IGNORECASE)
        missing_width: list[str] = []
        for img in imgs:
            if "width=" not in img.lower():
                # Skip 1px spacer images (common in email)
                if 'src="https://example.com"' in img or "spacer" in img.lower():
                    continue
                missing_width.append(img[:80])
        if missing_width:
            import warnings

            warnings.warn(
                f"{len(missing_width)} <img> tags missing width attribute",
                stacklevel=1,
            )

    def test_slot_fill_rate(self, converter_case: tuple[Path, CaseManifest, str]) -> None:
        _, _, html = converter_case
        rate = compute_slot_fill_rate(html)
        if rate < 0.8:
            import warnings

            warnings.warn(
                f"Slot fill rate {rate:.0%} < 80%",
                stacklevel=1,
            )


# ── Manifest-driven assertions (all cases) ───────────────────────


_LADDER_SNAPSHOT = load_ladder_snapshot()


@lru_cache(maxsize=1)
def _actual_ladders() -> dict[str, LadderRow]:
    """Converter's current ladder per case (computed once, cached for the run)."""
    return compute_all_ladders()


@pytest.mark.parametrize("case_id", discover_ladder_case_ids())
class TestSectionLadder:
    """A2 (plan §Track A): un-circular the structural gate via the A1 ladder.

    No single count cleanly recovers the design target — band_count just inverts
    the wrapper-unwrap (== candidates by construction) and rendered/marker counts
    are per-block — so the old ``sections.count`` gate, pinned to the converter's
    own output, measured nothing. The gate is split in two:

    - ``test_ladder_no_drift`` (hard, green): the converter's current count ladder
      (candidates → analyzed → rendered → bands + the per-wrapper band descriptor,
      the harness's "real signal") must match the committed
      ``data/debug/ladder_snapshot.json``. Catches ANY segmentation/render drift.
      Regen after an *intended* change (then re-verify expected.html):
      ``python -m app.design_sync.tests.ladder_harness --write``.
    - ``test_rendered_matches_target`` (module-level, per-case strictness): the
      rendered top-level section count must equal the design ``target_sections``.
      STRICT for the cases band grouping lands exactly (7/8/9 — Phase 53 D1);
      xfail for the proven-semantic under-counters (5/6/10) until Track D3.

    See .agents/plans/53-converter-engine-fix.md §Track A (A2) and
    .agents/plans/53-d-fork-a-execution.md §D1.
    """

    def test_ladder_no_drift(self, case_id: str) -> None:
        row = _actual_ladders().get(case_id)
        if row is None:
            pytest.skip(f"{case_id}: missing structure.json/tokens.json")
        if case_id not in _LADDER_SNAPSHOT:
            pytest.fail(
                f"{case_id}: fixture present but no entry in committed "
                f"data/debug/ladder_snapshot.json. Regen via "
                f"`python -m app.design_sync.tests.ladder_harness --write` and COMMIT it "
                f"(a missing snapshot must fail loudly, not silently drop the gate)."
            )
        committed = drift_view(_LADDER_SNAPSHOT[case_id])
        actual = drift_view(ladder_to_dict(row))
        assert actual == committed, (
            f"Case {case_id}: count ladder drifted from committed snapshot.\n"
            f"  committed: {committed}\n  actual:    {actual}\n"
            f"If intended, re-verify expected.html and regen via "
            f"`python -m app.design_sync.tests.ladder_harness --write`."
        )


def _target_gate_params() -> list[ParameterSet]:
    """Per-case strictness for the A2 target gate (Phase 53 D1.4)."""
    return [
        pytest.param(
            cid,
            marks=(
                [pytest.mark.xfail(strict=False, reason=SEMANTIC_UNDERCOUNT_REASON)]
                if cid in SEMANTIC_UNDERCOUNT_CASES
                else []
            )
            + known_failure_marks(cid, "test_rendered_matches_target"),
        )
        for cid in discover_ladder_case_ids()
    ]


@pytest.mark.parametrize("case_id", _target_gate_params())
def test_rendered_matches_target(case_id: str) -> None:
    """A2 target gate: rendered top-level section count == design ``target_sections``."""
    row = _actual_ladders().get(case_id)
    if row is None:
        pytest.skip(f"{case_id}: missing structure.json/tokens.json")
    if row.target is None:
        pytest.skip(f"{case_id}: no design target_sections")
    assert row.rendered == row.target, (
        f"Case {case_id}: rendered {row.rendered} sections != design target {row.target}"
    )


def _fold_quotes(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _decoded_text(html: str) -> str:
    """Lower-cased HTML with entities decoded and typographic quotes folded."""
    return _fold_quotes(html_lib.unescape(html).lower())


class TestRequiredContent:
    def test_required_content(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if not manifest.required_content:
            pytest.skip("No required_content in manifest")
        decoded = _decoded_text(html)
        missing = [r for r in manifest.required_content if _fold_quotes(r.lower()) not in decoded]
        assert not missing, f"Missing required content: {missing}"

    def test_forbidden_content(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if not manifest.forbidden_content:
            pytest.skip("No forbidden_content in manifest")
        html_lower = html.lower()
        found = [f for f in manifest.forbidden_content if f.lower() in html_lower]
        assert not found, f"Forbidden content found: {found}"


class TestTokenCompliance:
    def test_font_family(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if manifest.tokens is None or manifest.tokens.primary_font is None:
            pytest.skip("No font token expectations")
        assert manifest.tokens.primary_font.split(",")[0].strip() in html, (
            f"Primary font '{manifest.tokens.primary_font}' not found in output"
        )
        for banned in manifest.tokens.banned_fonts:
            assert banned not in html, f"Banned font '{banned}' found in output"

    def test_text_color(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if manifest.tokens is None or manifest.tokens.text_color is None:
            pytest.skip("No text color expectations")
        html_lower = html.lower()
        assert manifest.tokens.text_color.lower() in html_lower, (
            f"Text color {manifest.tokens.text_color} not found"
        )
        for banned in manifest.tokens.banned_colors:
            assert banned.lower() not in html_lower, f"Banned color '{banned}' found in output"


class TestCTAProperties:
    def test_cta_colors(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if not manifest.ctas:
            pytest.skip("No CTA expectations")
        html_lower = html.lower()
        for cta in manifest.ctas:
            if cta.bg_color is None:
                continue
            assert cta.text.lower() in html_lower, f"CTA text '{cta.text}' not found in output"
            assert cta.bg_color.lower() in html_lower, (
                f"CTA bg_color {cta.bg_color} for '{cta.text}' not found"
            )

    def test_cta_vml(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        vml_ctas = [c for c in manifest.ctas if c.has_vml]
        if not vml_ctas:
            pytest.skip("No VML CTA expectations")
        for cta in vml_ctas:
            assert "v:roundrect" in html.lower(), f"VML roundrect missing for CTA '{cta.text}'"


class TestComponentSelection:
    def test_component_selection(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        components = manifest.sections.components
        if not components:
            pytest.skip("No component expectations")
        decoded = _decoded_text(html)
        for comp in components:
            if comp.match_by == "content" and comp.content_hint:
                assert _fold_quotes(comp.content_hint.lower()) in decoded, (
                    f"Component content hint '{comp.content_hint}' "
                    f"(expected: {comp.expected_component}) not found"
                )

    def test_container_bgcolors(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        bgcolor_comps = [c for c in manifest.sections.components if c.container_bgcolor]
        if not bgcolor_comps:
            pytest.skip("No container_bgcolor expectations")
        html_lower = html.lower()
        for comp in bgcolor_comps:
            assert comp.container_bgcolor is not None
            assert comp.container_bgcolor.lower() in html_lower, (
                f"Container bgcolor {comp.container_bgcolor} for '{comp.content_hint}' not found"
            )


# ── Structural diff (soft, metadata only) ────────────────────────


class TestStructuralDiff:
    def test_expected_html_diff(
        self,
        case_with_result: tuple[Path, CaseManifest, ConversionResult],
    ) -> None:
        case_dir, manifest, result = case_with_result
        expected_path = case_dir / "expected.html"
        if not expected_path.exists():
            pytest.skip("No expected.html for structural diff")

        expected_norm = normalize_html(expected_path.read_text())
        actual_norm = normalize_html(result.html)
        metrics = collect_metrics(manifest, result.html, result)
        write_report(case_dir, metrics)

        if expected_norm != actual_norm:
            import warnings

            warnings.warn(
                f"{case_dir.name}: structural diff detected "
                f"(overall score: {metrics.overall_score:.2%})",
                stacklevel=1,
            )


# ── Metrics report ───────────────────────────────────────────────


class TestMetricsReport:
    def test_write_metrics(
        self,
        case_with_result: tuple[Path, CaseManifest, ConversionResult],
    ) -> None:
        case_dir, manifest, result = case_with_result
        metrics = collect_metrics(manifest, result.html, result)
        write_report(case_dir, metrics)
        report_path = case_dir / "report.json"
        assert report_path.exists(), f"report.json not written for {case_dir.name}"
        assert metrics.overall_score >= 0.0


# ── Fixture freshness (CE-3) ─────────────────────────────────────

# Keys the current dump writes that a case's structure.json predates, tolerated
# per case until re-synced. Empty since CE-6 re-synced every case (closed
# ce-3-fixture-schema-lag-6-10). A case not listed here must carry every key, and
# a listed key that a case now carries fails the test (delete it from the map).
_KNOWN_LAGGING_KEYS: dict[str, frozenset[str]] = {}


def _node_key_sets(structure: dict[str, Any]) -> list[tuple[str, frozenset[str]]]:
    out: list[tuple[str, frozenset[str]]] = []

    def _walk(node: dict[str, Any]) -> None:
        out.append((node["id"], frozenset(node)))
        for child in node.get("children", []):
            _walk(child)

    for page in structure["pages"]:
        _walk(page)
    return out


def _structure_case_ids() -> list[str]:
    return [p.name for p in discover_cases(_DEBUG_DIR) if (p / "structure.json").exists()]


class TestFixtureFreshness:
    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_structure_written_by_current_schema(self, case_id: str, tmp_path: Path) -> None:
        """A committed structure.json carries every key the current dump writes."""
        committed_path = _DEBUG_DIR / case_id / "structure.json"
        dumped_path = tmp_path / "structure.json"
        dump_structure_to_json(load_structure_from_json(committed_path), dumped_path)
        committed = _node_key_sets(json.loads(committed_path.read_text()))
        dumped = _node_key_sets(json.loads(dumped_path.read_text()))
        assert [i for i, _ in committed] == [i for i, _ in dumped]
        missing = {
            k for (_, have), (_, want) in zip(committed, dumped, strict=True) for k in want - have
        }
        allowed = _KNOWN_LAGGING_KEYS.get(case_id, frozenset())
        lagging = sorted(missing - allowed)
        assert not lagging, (
            f"case {case_id}: structure.json predates the dump schema, missing {lagging}. "
            f"Re-sync: uv run python scripts/resync-case-structure.py {case_id}"
        )
        stale = sorted(allowed - missing)
        assert not stale, (
            f"case {case_id}: no longer lags {stale}; drop it from _KNOWN_LAGGING_KEYS"
        )


# ── Auto-layout sizing capture (CE-6) ────────────────────────────

_SIZING = frozenset({"FIXED", "HUG", "FILL"})


def _walk_nodes(node: DesignNode) -> list[DesignNode]:
    out = [node]
    for child in node.children:
        out.extend(_walk_nodes(child))
    return out


class TestSizingCapture:
    """Invariants over every committed case; per-design counts live in the CE-6 report."""

    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_every_parsed_node_has_sizing(self, case_id: str) -> None:
        structure = load_structure_from_json(_DEBUG_DIR / case_id / "structure.json")
        bad = [
            (n.id, n.layout_sizing_horizontal, n.layout_sizing_vertical)
            for page in structure.pages
            for n in _walk_nodes(page)
            if n.type != DesignNodeType.PAGE
            and (
                n.layout_sizing_horizontal not in _SIZING or n.layout_sizing_vertical not in _SIZING
            )
        ]
        assert not bad, f"case {case_id}: {len(bad)} nodes without sizing, first {bad[:3]}"

    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_wrap_on_every_auto_layout_frame(self, case_id: str) -> None:
        structure = load_structure_from_json(_DEBUG_DIR / case_id / "structure.json")
        bad = [
            n.id
            for page in structure.pages
            for n in _walk_nodes(page)
            if (n.layout_wrap is not None) != (n.layout_mode not in (None, "NONE"))
        ]
        assert not bad, f"case {case_id}: wrap/layout_mode mismatch on {bad[:5]}"

    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_root_frame_is_fixed(self, case_id: str) -> None:
        structure = load_structure_from_json(_DEBUG_DIR / case_id / "structure.json")
        (page,) = structure.pages
        (root,) = page.children
        assert root.layout_sizing_horizontal == "FIXED"

    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_root_width_is_container_width(self, case_id: str) -> None:
        """Verification invariant (green before CE-6): the email width is the root frame width."""
        case_dir = _DEBUG_DIR / case_id
        structure = load_structure_from_json(case_dir / "structure.json")
        tokens = load_tokens_from_json(case_dir / "tokens.json")
        (page,) = structure.pages
        (root,) = page.children
        assert root.width is not None
        document = EmailDesignDocument.from_legacy(structure, tokens)
        assert int(root.width) == document.layout.container_width

    @pytest.mark.parametrize("case_id", _structure_case_ids())
    def test_live_cache_path_matches_corpus_load(self, case_id: str) -> None:
        """The production read (cache dict -> JSON -> _node_from_dict) loses no field."""
        structure = load_structure_from_json(_DEBUG_DIR / case_id / "structure.json")
        names = [f.name for f in dataclasses.fields(DesignNode) if f.name != "children"]
        for page in structure.pages:
            live = _node_from_dict(json.loads(json.dumps(serialize_node(page))))
            for want, got in zip(_walk_nodes(page), _walk_nodes(live), strict=True):
                diff = [n for n in names if getattr(got, n) != getattr(want, n)]
                assert not diff, f"case {case_id}: node {want.id} lost {diff}"


# ── known_failures rows (CE-3) ───────────────────────────────────

_LEDGER_PATH = _DEBUG_DIR.parents[1] / ".agents" / "deferred-items.json"
_OWNER_ISSUE_RE = re.compile(r"^#\d+$")
_COUNT_TESTS = frozenset({"test_rendered_matches_target", "test_section_count"})


def _hooked_test_names() -> set[str]:
    """Tests that consult known_failures: fixture-driven classes + both target gates."""
    classes = (
        TestUniversalChecks,
        TestRequiredContent,
        TestTokenCompliance,
        TestCTAProperties,
        TestComponentSelection,
        TestStructuralDiff,
        TestMetricsReport,
    )
    names = {n for cls in classes for n in dir(cls) if n.startswith("test_")}
    return names | _COUNT_TESTS


def test_known_failures_name_hooked_tests_and_owners() -> None:
    ledger_ids = {item["id"] for item in json.loads(_LEDGER_PATH.read_text())["items"]}
    hooked = _hooked_test_names()
    for case_dir in discover_cases(_DEBUG_DIR):
        for row in load_case_manifest(case_dir).known_failures:
            assert row.test in hooked, f"{case_dir.name}: {row.test} is not a hooked test"
            assert _OWNER_ISSUE_RE.match(row.owner) or row.owner in ledger_ids, (
                f"{case_dir.name}: owner {row.owner!r} is neither #<issue> nor a ledger id"
            )
            assert row.reason.strip(), f"{case_dir.name}: {row.test} has no reason"
            # A row on a test that never runs for this case is a dead ratchet.
            assert not load_case_manifest(case_dir).reference_only, (
                f"{case_dir.name}: known_failures on a reference_only case never run"
            )
            if row.test in _COUNT_TESTS:
                assert load_target_sections().get(case_dir.name) is not None, (
                    f"{case_dir.name}: {row.test} skips without target_sections"
                )
