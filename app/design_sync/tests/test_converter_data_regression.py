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

import re
from functools import lru_cache
from pathlib import Path

import pytest
from lxml import etree

from app.design_sync.converter_service import ConversionResult
from app.design_sync.tests.ladder_harness import (
    LadderRow,
    compute_all_ladders,
    discover_ladder_case_ids,
    drift_view,
    ladder_to_dict,
    load_ladder_snapshot,
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
    """Remove all MSO conditional blocks for structural analysis."""
    result = _MSO_BLOCK_RE.sub("", html)
    # Keep content inside non-MSO wrappers but remove the wrappers themselves
    return _NON_MSO_WRAPPER_RE.sub(r"\1", result)


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
    return _load_case(request.param)


@pytest.fixture(params=_converter_case_ids())
def converter_case(request: pytest.FixtureRequest) -> tuple[Path, CaseManifest, str]:
    """Parametrized fixture for cases with actual converter output only."""
    case_name: str = request.param
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
    - ``test_rendered_matches_target`` (xfail/advisory): the rendered top-level
      section count must equal the design ``target_sections``. EXPECTED to fail
      where the converter mis-segments (Phase 53). Red = the real defect surfacing.

    See .agents/plans/53-converter-engine-fix.md §Track A (A2).
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

    @pytest.mark.xfail(
        reason=(
            "A2: rendered section count vs design target_sections. The converter "
            "mis-segments several fixtures (Phase 53) — xfail means the gate is "
            "measuring the dominant defect, not regressing. Red = the real defect "
            "surfacing. See .agents/plans/53-converter-engine-fix.md §Track A (A2)."
        ),
        strict=False,
    )
    def test_rendered_matches_target(self, case_id: str) -> None:
        row = _actual_ladders().get(case_id)
        if row is None:
            pytest.skip(f"{case_id}: missing structure.json/tokens.json")
        if row.target is None:
            pytest.skip(f"{case_id}: no design target_sections")
        assert row.rendered == row.target, (
            f"Case {case_id}: rendered {row.rendered} sections != design target {row.target}"
        )


class TestRequiredContent:
    def test_required_content(self, case: tuple[Path, CaseManifest, str]) -> None:
        _, manifest, html = case
        if not manifest.required_content:
            pytest.skip("No required_content in manifest")
        import html as html_lib

        # Decode HTML entities and normalize typographic quotes
        decoded = html_lib.unescape(html).lower()
        decoded = decoded.replace("\u2019", "'").replace("\u2018", "'")
        missing = [
            r for r in manifest.required_content if r.lower().replace("\u2019", "'") not in decoded
        ]
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
        html_lower = html.lower()
        for comp in components:
            if comp.match_by == "content" and comp.content_hint:
                assert comp.content_hint.lower() in html_lower, (
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
