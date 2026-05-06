"""Data-driven regression runner for converter cases.

Discovers ``data/debug/<case>/manifest.yaml`` files, runs the converter
pipeline on each case, and collects per-case metrics.

Can also be invoked as a CLI to generate ``report.json`` per case::

    python -m app.design_sync.tests.regression_runner --report
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.design_sync.converter_service import ConversionResult, DesignConverterService
from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.tests.manifest_schema import CaseManifest

_DEFAULT_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"


# ── Discovery ────────────────────────────────────────────────────


def discover_cases(base_dir: Path | None = None) -> list[Path]:
    """Return case directories that contain a per-case ``manifest.yaml``."""
    base = base_dir or _DEFAULT_DEBUG_DIR
    return sorted(p.parent for p in base.glob("*/manifest.yaml"))


def load_case_manifest(case_dir: Path) -> CaseManifest:
    """Read and validate a per-case manifest."""
    path = case_dir / "manifest.yaml"
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return CaseManifest.model_validate(data)


# ── Conversion ───────────────────────────────────────────────────


def run_case_conversion(case_dir: Path) -> ConversionResult | None:
    """Run the converter pipeline on a case directory.

    Returns ``None`` when required input files are missing (caller should
    ``pytest.skip``).
    """
    structure_path = case_dir / "structure.json"
    tokens_path = case_dir / "tokens.json"
    if not structure_path.exists() or not tokens_path.exists():
        return None
    structure = load_structure_from_json(structure_path)
    tokens = load_tokens_from_json(tokens_path)
    document = EmailDesignDocument.from_legacy(structure, tokens)
    return DesignConverterService().convert_document(document)


# ── HTML helpers ─────────────────────────────────────────────────

_DATA_SLOT_RE = re.compile(r'data-slot="([^"]*)"')
_DATA_SLOT_DEFAULT_RE = re.compile(
    r'data-slot="[^"]*"[^>]*>(\s*(?:Image caption|Editorial heading|'
    r"Section Heading|Lorem ipsum|https://example\.com)[^<]*)<",
    re.IGNORECASE,
)


def normalize_html(html: str) -> str:
    """Collapse whitespace for comparison."""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"\s*/>", ">", html)
    parts = html.split(">")
    lines = [p.strip() + ">" for p in parts if p.strip()]
    return "\n".join(lines)


def compute_slot_fill_rate(html: str) -> float:
    """Fraction of ``data-slot`` attrs that have non-default content."""
    total = len(_DATA_SLOT_RE.findall(html))
    if total == 0:
        return 1.0
    defaults = len(_DATA_SLOT_DEFAULT_RE.findall(html))
    return (total - defaults) / total


# ── Metrics ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CaseMetrics:
    """Per-case quality scores (0.0-1.0)."""

    section_count_accuracy: float
    component_match_accuracy: float
    slot_fill_rate: float
    content_coverage: float
    token_compliance: float
    overall_score: float
    details: dict[str, str | float | int] = field(
        default_factory=lambda: {}  # noqa: PIE807
    )


def collect_metrics(manifest: CaseManifest, html: str, result: ConversionResult) -> CaseMetrics:
    """Compute quality metrics for a conversion result against its manifest."""
    # Section count accuracy
    expected_sections = manifest.sections.count
    actual_sections = result.sections_count
    section_acc = max(
        0.0,
        1.0 - abs(actual_sections - expected_sections) / max(expected_sections, 1),
    )

    # Component match accuracy (stub — requires section-by-section analysis)
    component_acc = 1.0  # placeholder until component matching is wired

    # Slot fill rate
    sfr = compute_slot_fill_rate(html)

    # Content coverage
    required = manifest.required_content
    if required:
        html_lower = html.lower()
        found = sum(1 for r in required if r.lower() in html_lower)
        content_cov = found / len(required)
    else:
        content_cov = 1.0

    # Token compliance (stub)
    token_comp = 1.0

    # Weighted overall
    overall = (
        section_acc * 0.25
        + component_acc * 0.25
        + sfr * 0.15
        + content_cov * 0.20
        + token_comp * 0.15
    )

    return CaseMetrics(
        section_count_accuracy=round(section_acc, 4),
        component_match_accuracy=round(component_acc, 4),
        slot_fill_rate=round(sfr, 4),
        content_coverage=round(content_cov, 4),
        token_compliance=round(token_comp, 4),
        overall_score=round(overall, 4),
    )


def write_report(case_dir: Path, metrics: CaseMetrics) -> None:
    """Write ``report.json`` into the case directory."""
    path = case_dir / "report.json"
    path.write_text(json.dumps(asdict(metrics), indent=2) + "\n")


# ── CLI entry point ──────────────────────────────────────────────


def _cli_report() -> None:
    """Generate report.json for all discovered cases."""
    cases = discover_cases()
    if not cases:
        print("No cases found.")  # noqa: T201
        return
    for case_dir in cases:
        manifest = load_case_manifest(case_dir)
        result = run_case_conversion(case_dir)
        if result is None:
            print(f"  SKIP {case_dir.name} (missing structure/tokens)")  # noqa: T201
            continue
        metrics = collect_metrics(manifest, result.html, result)
        write_report(case_dir, metrics)
        print(f"  {case_dir.name}: overall={metrics.overall_score:.2%}")  # noqa: T201


if __name__ == "__main__":
    import sys

    if "--report" in sys.argv:
        _cli_report()
    else:
        print("Usage: python -m app.design_sync.tests.regression_runner --report")  # noqa: T201
