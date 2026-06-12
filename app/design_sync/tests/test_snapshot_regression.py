"""Snapshot regression tests for design-to-HTML conversion.

Loads real design inputs (structure.json + tokens.json) from data/debug/{case}/,
runs the full converter pipeline, and compares output against visually verified
expected.html files.

This is the ground truth — every converter fix must pass all snapshot cases.

To add a new case:
    1. Capture design data:  python -m app.design_sync.diagnose.extract --connection-id <N>
    2. Generate current output:  python scripts/snapshot-capture.py <case_id>
    3. Open data/debug/<case_id>/expected.html in a browser, verify visually
    4. Add the case to data/debug/manifest.yaml with status: active
    5. Run:  make snapshot-test
"""

from __future__ import annotations

import asyncio
import difflib
import re
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from _pytest.mark.structures import ParameterSet

from app.design_sync.converter_service import ConversionResult, DesignConverterService
from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.tests.ladder_harness import (
    SEMANTIC_UNDERCOUNT_CASES,
    SEMANTIC_UNDERCOUNT_REASON,
    load_target_sections,
)
from app.design_sync.visual_verify import (
    VerificationLoopResult,
    VerificationResult,
)

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"
_MANIFEST = _DEBUG_DIR / "manifest.yaml"
_REFERENCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "email-templates"
    / "training_HTML"
    / "for_converter_engine"
)


def _load_manifest() -> list[dict[str, Any]]:
    """Load active snapshot cases from manifest."""
    if not _MANIFEST.exists():
        return []
    data = yaml.safe_load(_MANIFEST.read_text())
    cases: list[dict[str, Any]] = data.get("cases", [])
    return [c for c in cases if c.get("status") == "active"]


def _get_active_case_ids() -> list[str]:
    """Return case IDs for parametrize."""
    return [c["id"] for c in _load_manifest()]


def _normalize_html(html: str) -> str:
    """Normalize HTML for comparison.

    - Collapse whitespace runs to single space
    - Strip leading/trailing whitespace per line
    - Remove blank lines
    - Normalize self-closing tags

    This allows the snapshot to survive whitespace-only reformatting
    while catching any real content/structure changes.
    """
    # Collapse runs of whitespace (including newlines) to single space
    html = re.sub(r"\s+", " ", html)
    # Normalize self-closing tags: <br /> → <br>
    html = re.sub(r"\s*/>", ">", html)
    # Split on > to get roughly one tag per line for readable diffs
    parts = html.split(">")
    lines = [p.strip() + ">" for p in parts if p.strip()]
    return "\n".join(lines)


def _html_diff(expected: str, actual: str) -> str:
    """Generate a readable unified diff between normalized HTML."""
    expected_lines = _normalize_html(expected).splitlines(keepends=True)
    actual_lines = _normalize_html(actual).splitlines(keepends=True)
    diff = difflib.unified_diff(
        expected_lines,
        actual_lines,
        fromfile="expected.html",
        tofile="actual.html",
        n=3,
    )
    return "".join(list(diff)[:100])  # Cap at 100 lines for readability


# ── Background continuity helpers ─────────────────────────────────

_SECTION_MARKER_RE = re.compile(r"<!-- section:section_(\d+) -->")
_BG_STYLE_RE = re.compile(r"<table[^>]*style=\"[^\"]*background-color:\s*([^;\"]+)", re.IGNORECASE)
_BGCOLOR_ATTR_RE = re.compile(r"<table[^>]*\bbgcolor=\"([^\"]+)\"", re.IGNORECASE)


def _extract_converter_section_bgcolors(html: str) -> dict[int, str | None]:
    """Extract background color per section from converter output.

    Uses ``<!-- section:section_N -->`` markers to identify sections.
    Checks both ``background-color`` inline style and ``bgcolor`` attribute
    on the first ``<table>`` in each section.
    """
    parts = _SECTION_MARKER_RE.split(html)
    # parts: [preamble, "0", content0, "1", content1, ...]
    result: dict[int, str | None] = {}
    for i in range(1, len(parts), 2):
        idx = int(parts[i])
        content = parts[i + 1] if i + 1 < len(parts) else ""
        # Prefer background-color style, fall back to bgcolor attr
        style_m = _BG_STYLE_RE.search(content)
        attr_m = _BGCOLOR_ATTR_RE.search(content)
        color = None
        if style_m:
            color = style_m.group(1).strip().upper()
        elif attr_m:
            color = attr_m.group(1).strip().upper()
        result[idx] = color
    return result


_REF_SECTION_RE = re.compile(
    r'<table[^>]*width="600"[^>]*class="resptab"[^>]*bgcolor="([^"]*)"[^>]*>',
    re.IGNORECASE,
)


def _extract_reference_bgcolors(html: str) -> list[str]:
    """Extract bgcolor from 600px resptab section tables in reference HTML."""
    return [m.upper() for m in _REF_SECTION_RE.findall(html)]


# Expected bgcolors for converter output (calibrated from actual converter).
# Keys are section indices from <!-- section:section_N --> markers.
_CONVERTER_BGCOLOR_EXPECTATIONS: dict[str, dict[int, str]] = {
    "10": {
        # section_1 (text-block) adjacent to hero — Mammut orange from tokens
        1: "#FE5117",
        # section_3 (text-block) adjacent to second image — Mammut blue
        3: "#0252B3",
    },
    "6": {
        # section_1 (text-block) adjacent to hero — Starbucks cream
        1: "#F7F0E3",
    },
    "5": {},  # MAAP — white backgrounds, no continuity (negative test)
}

# Expected bgcolors for reference HTMLs (from docs/architecture/converter-training-reference.md).
# Indices are positional within 600px resptab tables.
_REFERENCE_BGCOLOR_EXPECTATIONS: dict[str, list[str]] = {
    "10": [
        "#E85D26",  # heading (continues hero orange)
        "#E85D26",  # paragraph
        "#E85D26",  # button-ghost
        "#E85D26",  # button-ghost
        "#0252B5",  # heading (continues hero blue)
        "#0252B5",  # paragraph
        "#0252B5",  # text-link
        "#FFFFFF",  # heading (white section)
        "#FFFFFF",  # product grid
        "#FFFFFF",  # heading
        "#FFFFFF",  # nav/footer
    ],
    "6": [
        "#F2F0EB",  # heading (cream after hero)
        "#F2F0EB",  # paragraph
        "#F2F0EB",  # button
        "#AA1733",  # two-column (holiday red)
        "#FFFFFF",  # social icons
        "#FFFFFF",  # footer
        "#FFFFFF",  # logo
    ],
}

_REFERENCE_MAP: dict[str, str] = {
    "10": "mammut-duvet-day.html",
    "6": "starbucks-pumpkin-spice.html",
    "5": "maap-kask.html",
}

# Converter sections with dark backgrounds where text must be inverted.
_DARK_SECTION_CASES: dict[str, list[int]] = {
    "10": [1, 3],  # Orange (#FE5117) + blue (#0252B3) sections
}


def _require_fixtures(case_dir: Path) -> None:
    """Skip the test when snapshot fixtures aren't present locally.

    `data/debug/{id}/structure.json` and `tokens.json` are dev-only artifacts
    generated via `python -m app.design_sync.diagnose.extract`. They aren't
    committed, so CI lanes without a local extract must skip rather than fail.
    """
    if not (case_dir / "structure.json").exists() or not (case_dir / "tokens.json").exists():
        pytest.skip(f"Snapshot fixtures missing for case {case_dir.name}")


def _run_conversion(case_dir: Path) -> ConversionResult:
    """Load real inputs and run the full converter pipeline."""
    _require_fixtures(case_dir)
    structure = load_structure_from_json(case_dir / "structure.json")
    tokens = load_tokens_from_json(case_dir / "tokens.json")
    document = EmailDesignDocument.from_legacy(structure, tokens)
    return DesignConverterService().convert_document(document)


# ── Snapshot tests ────────────────────────────────────────────────


@pytest.mark.snapshot
class TestSnapshotRegression:
    """Each active case in manifest.yaml must produce output matching expected.html."""

    @pytest.mark.parametrize("case_id", _get_active_case_ids())
    def test_snapshot_matches(self, case_id: str) -> None:
        case_dir = _DEBUG_DIR / case_id

        expected_path = case_dir / "expected.html"
        assert expected_path.exists(), (
            f"Missing expected.html for case {case_id}. "
            f"Run: python scripts/snapshot-capture.py {case_id}"
        )

        expected_html = expected_path.read_text()
        assert "PLACEHOLDER" not in expected_html, (
            f"expected.html for case {case_id} still has placeholder content. "
            f"Run: python scripts/snapshot-capture.py {case_id} "
            f"then verify visually and remove the placeholder comment."
        )

        result = _run_conversion(case_dir)

        assert result.html, f"Converter produced empty HTML for case {case_id}"
        assert result.sections_count > 0, f"Converter found 0 sections for case {case_id}"

        expected_norm = _normalize_html(expected_html)
        actual_norm = _normalize_html(result.html)

        if expected_norm != actual_norm:
            diff = _html_diff(expected_html, result.html)
            # Also save the actual output for easy comparison
            actual_path = case_dir / "actual.html"
            actual_path.write_text(result.html)
            pytest.fail(
                f"Snapshot mismatch for case {case_id}.\n"
                f"Actual output saved to: {actual_path}\n"
                f"Open both files in a browser to compare visually.\n\n"
                f"If the new output is correct, update expected.html:\n"
                f"  cp {actual_path} {expected_path}\n\n"
                f"Diff (first 100 lines):\n{diff}"
            )


class TestSnapshotSanity:
    """Basic sanity checks on all cases (including pending)."""

    @pytest.mark.parametrize(
        "case_id",
        [
            cast(dict[str, Any], c)["id"]
            for c in cast(
                list[Any],
                cast(
                    dict[str, Any],
                    yaml.safe_load((_DEBUG_DIR / "manifest.yaml").read_text()) or {},
                ).get("cases", []),
            )
        ],
    )
    def test_case_loads(self, case_id: str) -> None:
        """Every case in the manifest must have loadable structure + tokens."""
        case_dir = _DEBUG_DIR / case_id
        _require_fixtures(case_dir)

        structure = load_structure_from_json(case_dir / "structure.json")
        load_tokens_from_json(case_dir / "tokens.json")

        assert len(structure.pages) > 0, f"Empty pages in case {case_id}"
        assert structure.file_name, f"Empty file_name in case {case_id}"


def _section_count_params() -> list[ParameterSet]:
    """Per-case strictness for the A2 target gate (Phase 53 D1.4)."""
    return [
        pytest.param(
            cid,
            marks=[pytest.mark.xfail(strict=False, reason=SEMANTIC_UNDERCOUNT_REASON)]
            if cid in SEMANTIC_UNDERCOUNT_CASES
            else [],
        )
        for cid in _get_active_case_ids()
    ]


@pytest.mark.snapshot
class TestSnapshotSectionCount:
    """Rendered section count vs the *design* ``target_sections`` (the Phase 53 defect).

    Re-pinned from ``sections`` (= the converter's own current output, which made
    this a circular gate that passed *because* the converter mis-segments) to
    ``target_sections`` (design truth). Per-case strictness since Phase 53 D1:
    band grouping (default-on after the 53.1 gate) lands cases 7/8/9 exactly on
    target — those run STRICT; the proven-semantic under-counters (5/6/10) stay
    xfail until Track D3. Output drift is independently caught by
    ``TestSnapshotRegression.test_snapshot_matches`` (expected.html comparison); the
    full count ladder lives in the converter-data-regression suite
    (``TestSectionLadder``). See .agents/plans/53-converter-engine-fix.md §Track A (A2)
    and .agents/plans/53-d-fork-a-execution.md §D1.
    """

    @pytest.mark.parametrize("case_id", _section_count_params())
    def test_section_count(self, case_id: str) -> None:
        target = load_target_sections().get(case_id)
        if target is None:
            pytest.skip("No target_sections in manifest")

        case_dir = _DEBUG_DIR / case_id
        result = _run_conversion(case_dir)
        assert result.sections_count == target, (
            f"Case {case_id}: rendered {result.sections_count} sections != design target {target}"
        )


# ── Background continuity tests ──────────────────────────────────


@pytest.mark.snapshot
class TestBackgroundContinuity:
    """Verify background color continuity on converter output.

    Content sections adjacent to full-width hero images must carry the
    brand background color from the design tokens — not default to white.
    Breaking the token extraction or component assembly reverts these to
    ``#ffffff``, which this test catches.
    """

    @pytest.mark.parametrize("case_id", _get_active_case_ids())
    def test_background_continuity(self, case_id: str) -> None:
        expectations = _CONVERTER_BGCOLOR_EXPECTATIONS.get(case_id, {})
        if not expectations:
            pytest.skip(f"Case {case_id} has no bgcolor continuity expectations")

        case_dir = _DEBUG_DIR / case_id
        result = _run_conversion(case_dir)
        assert result.html, f"Converter produced empty HTML for case {case_id}"

        bgcolors = _extract_converter_section_bgcolors(result.html)

        mismatches: list[str] = []
        for section_idx, expected_color in expectations.items():
            actual = bgcolors.get(section_idx)
            if actual is None:
                mismatches.append(
                    f"  section_{section_idx}: expected {expected_color}, got no background color"
                )
            elif actual != expected_color.upper():
                mismatches.append(
                    f"  section_{section_idx}: expected {expected_color}, got {actual}"
                )

        if mismatches:
            debug_info = "\n".join(f"  section_{k}: {v}" for k, v in sorted(bgcolors.items()))
            pytest.fail(
                f"Background continuity mismatch for case {case_id}:\n"
                + "\n".join(mismatches)
                + f"\n\nAll section bgcolors:\n{debug_info}"
            )

    @pytest.mark.parametrize("case_id", list(_DARK_SECTION_CASES))
    def test_text_inversion_on_dark_sections(self, case_id: str) -> None:
        """Dark-background sections must not contain dark text colors.

        The inversion pipeline (Phase 41.3) replaces dark ``color:`` values
        with ``#ffffff`` when ``bgcolor`` luminance < 0.4.  This catches
        regressions where dark text is left on a dark background.
        """
        case_dir = _DEBUG_DIR / case_id
        result = _run_conversion(case_dir)
        assert result.html

        parts = _SECTION_MARKER_RE.split(result.html)
        dark_indices = _DARK_SECTION_CASES[case_id]

        for section_idx in dark_indices:
            # Find the section content in the split parts
            content = None
            for i in range(1, len(parts), 2):
                if int(parts[i]) == section_idx:
                    content = parts[i + 1] if i + 1 < len(parts) else ""
                    break
            if content is None:
                continue

            # Find dark text colors that should have been inverted
            dark_colors = re.findall(
                r"(?<!background-)color\s*:\s*"
                r"(#(?:000|111|222|333|1[aA]1[aA]1[aA]|0{6})\b)",
                content,
            )
            assert not dark_colors, (
                f"Case {case_id} section_{section_idx}: dark text colors "
                f"{dark_colors} found on dark-background section — "
                f"should be inverted to #ffffff"
            )


class TestReferenceBgcolorSanity:
    """Validate that hand-built reference HTMLs match our expectation maps.

    If a reference HTML is edited, this catches stale expectations.
    """

    @pytest.mark.parametrize(
        "case_id",
        list(_REFERENCE_BGCOLOR_EXPECTATIONS),
    )
    def test_reference_bgcolors(self, case_id: str) -> None:
        ref_file = _REFERENCE_DIR / _REFERENCE_MAP[case_id]
        if not ref_file.exists():
            pytest.skip(f"Reference HTML not found: {ref_file}")

        html = ref_file.read_text()
        bgcolors = _extract_reference_bgcolors(html)
        expected = _REFERENCE_BGCOLOR_EXPECTATIONS[case_id]

        assert len(bgcolors) == len(expected), (
            f"Reference {_REFERENCE_MAP[case_id]}: expected {len(expected)} "
            f"section tables, found {len(bgcolors)}"
        )

        mismatches: list[str] = []
        for i, (actual, exp) in enumerate(zip(bgcolors, expected, strict=True)):
            if actual != exp.upper():
                mismatches.append(f"  [{i}] expected {exp}, got {actual}")

        if mismatches:
            pytest.fail(
                f"Reference {_REFERENCE_MAP[case_id]} bgcolor mismatch:\n" + "\n".join(mismatches)
            )


# ── Verification metadata tests (47.9) ─────────────────────────────


_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _make_loop_result(
    *,
    iterations_count: int = 3,
    initial_fidelity: float = 0.80,
    final_fidelity: float = 0.98,
    total_corrections: int = 5,
    converged: bool = True,
    final_html: str = "<html>corrected</html>",
) -> VerificationLoopResult:
    """Build a mock VerificationLoopResult."""
    iterations: list[VerificationResult] = []
    for i in range(iterations_count):
        fidelity = initial_fidelity + (final_fidelity - initial_fidelity) * i / max(
            iterations_count - 1, 1
        )
        iterations.append(
            VerificationResult(
                iteration=i,
                fidelity_score=fidelity,
                section_scores={"n1": (1.0 - fidelity) * 100},
                corrections=[],
                pixel_diff_pct=(1.0 - fidelity) * 100,
                converged=i == iterations_count - 1,
            )
        )
    return VerificationLoopResult(
        iterations=iterations,
        final_html=final_html,
        initial_fidelity=initial_fidelity,
        final_fidelity=final_fidelity,
        total_corrections_applied=total_corrections,
        total_vlm_cost_tokens=0,
        converged=converged,
        reverted=False,
    )


def _mock_vlm_settings() -> Any:
    """Return a mock settings object with VLM verification enabled."""
    mock_ds = type(
        "DS",
        (),
        {
            "vlm_verify_enabled": True,
            "vlm_verify_model": "",
            "vlm_verify_timeout": 5.0,
            "vlm_verify_diff_skip_threshold": 2.0,
            "vlm_verify_max_sections": 20,
            "vlm_verify_max_iterations": 3,
            "vlm_verify_target_fidelity": 0.97,
            "vlm_verify_confidence_threshold": 0.7,
            "vlm_verify_client": "gmail_web",
        },
    )()
    return type("S", (), {"design_sync": mock_ds})()


@pytest.mark.snapshot
class TestVerificationMetadata:
    """Verify that mock-VLM verification loop produces metadata on real cases."""

    @pytest.mark.parametrize("case_id", _get_active_case_ids())
    def test_mock_vlm_loop_produces_metadata(self, case_id: str) -> None:
        """Run converter then _apply_verification with mock VLM, assert metadata fields."""
        case_dir = _DEBUG_DIR / case_id
        base_result = _run_conversion(case_dir)
        assert base_result.html

        mock_loop_result = _make_loop_result(
            iterations_count=3,
            final_html=base_result.html,
        )

        converter = DesignConverterService()
        with (
            patch(
                "app.design_sync.visual_verify.run_verification_loop",
                new_callable=AsyncMock,
                return_value=mock_loop_result,
            ),
            patch(
                "app.design_sync.converter_service.get_settings",
                return_value=_mock_vlm_settings(),
            ),
        ):
            result = asyncio.run(
                converter._apply_verification(
                    base_result,
                    {"n1": _FAKE_PNG},
                    [],
                    600,
                )
            )

        assert result.verification_iterations == 3
        assert result.verification_final_fidelity is not None
        assert result.verification_final_fidelity >= 0.0
        assert result.verification_initial_fidelity is not None

    @pytest.mark.parametrize("case_id", _get_active_case_ids())
    def test_fidelity_improves_over_baseline(self, case_id: str) -> None:
        """Mock VLM returns improving fidelity across iterations."""
        case_dir = _DEBUG_DIR / case_id
        base_result = _run_conversion(case_dir)
        assert base_result.html

        mock_loop_result = _make_loop_result(
            iterations_count=3,
            initial_fidelity=0.75,
            final_fidelity=0.98,
            final_html=base_result.html,
        )

        converter = DesignConverterService()
        with (
            patch(
                "app.design_sync.visual_verify.run_verification_loop",
                new_callable=AsyncMock,
                return_value=mock_loop_result,
            ),
            patch(
                "app.design_sync.converter_service.get_settings",
                return_value=_mock_vlm_settings(),
            ),
        ):
            result = asyncio.run(
                converter._apply_verification(
                    base_result,
                    {"n1": _FAKE_PNG},
                    [],
                    600,
                )
            )

        assert result.verification_final_fidelity is not None
        assert result.verification_initial_fidelity is not None
        assert result.verification_final_fidelity >= result.verification_initial_fidelity

    @pytest.mark.parametrize("case_id", _get_active_case_ids())
    def test_correction_types_match_reference(self, case_id: str) -> None:
        """Mock VLM returns color corrections matching reference bgcolor expectations."""
        expectations = _CONVERTER_BGCOLOR_EXPECTATIONS.get(case_id, {})
        if not expectations:
            pytest.skip(f"Case {case_id} has no bgcolor correction expectations")

        case_dir = _DEBUG_DIR / case_id
        base_result = _run_conversion(case_dir)
        assert base_result.html

        total_corrections = len(expectations)
        mock_loop_result = _make_loop_result(
            iterations_count=2,
            initial_fidelity=0.85,
            final_fidelity=0.97,
            total_corrections=total_corrections,
            final_html=base_result.html,
        )

        converter = DesignConverterService()
        with (
            patch(
                "app.design_sync.visual_verify.run_verification_loop",
                new_callable=AsyncMock,
                return_value=mock_loop_result,
            ),
            patch(
                "app.design_sync.converter_service.get_settings",
                return_value=_mock_vlm_settings(),
            ),
        ):
            result = asyncio.run(
                converter._apply_verification(
                    base_result,
                    {"n1": _FAKE_PNG},
                    [],
                    600,
                )
            )

        assert result.verification_iterations == 2
        assert result.verification_final_fidelity is not None
        assert result.verification_final_fidelity >= 0.95
