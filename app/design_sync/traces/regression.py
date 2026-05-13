"""Regression detection over converter trace metrics (F060)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_TRACES_PATH = Path("traces/converter_traces.jsonl")
_DEFAULT_BASELINE_PATH = Path("traces/converter_baseline.json")

_METRIC_KEYS = (
    "avg_quality_score",
    "avg_confidence",
    "warning_rate",
    "error_rate",
    "low_confidence_section_rate",
)


def load_traces(path: Path | None = None, last_n: int = 100) -> list[dict[str, Any]]:
    """Load the most recent N traces from the JSONL file."""
    trace_path = path or _DEFAULT_TRACES_PATH
    if not trace_path.exists():
        return []

    traces: list[dict[str, Any]] = []
    with trace_path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                traces.append(json.loads(stripped))

    return traces[-last_n:]


def compute_aggregate_metrics(traces: list[dict[str, Any]]) -> dict[str, float]:
    """Compute aggregate metrics from a list of traces."""
    if not traces:
        return dict.fromkeys(_METRIC_KEYS, 0.0)

    n = len(traces)
    total_quality = sum(t.get("quality_score", 0.0) for t in traces)
    total_confidence = sum(t.get("avg_confidence", 0.0) for t in traces)

    total_warnings = sum(len(t.get("warnings", [])) for t in traces)
    total_sections = sum(t.get("sections_count", 1) for t in traces)

    error_warnings = sum(
        1 for t in traces for w in t.get("warnings", []) if w.get("severity") == "error"
    )

    low_conf_sections = sum(
        1
        for t in traces
        for conf in t.get("match_confidences", {}).values()
        if isinstance(conf, (int, float)) and conf < 0.6
    )
    total_match_sections = sum(len(t.get("match_confidences", {})) for t in traces)

    return {
        "avg_quality_score": total_quality / n,
        "avg_confidence": total_confidence / n,
        "warning_rate": total_warnings / max(total_sections, 1),
        "error_rate": error_warnings / max(total_warnings, 1),
        "low_confidence_section_rate": low_conf_sections / max(total_match_sections, 1),
    }


def load_baseline(path: Path | None = None) -> dict[str, float] | None:
    """Load a saved baseline from JSON."""
    baseline_path = path or _DEFAULT_BASELINE_PATH
    if not baseline_path.exists():
        return None
    with baseline_path.open(encoding="utf-8") as f:
        data: dict[str, float] = json.load(f)
    return data


def save_baseline(metrics: dict[str, float], path: Path | None = None) -> None:
    """Save current metrics as the baseline."""
    baseline_path = path or _DEFAULT_BASELINE_PATH
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with baseline_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


def detect_regressions(
    current: dict[str, float],
    baseline: dict[str, float],
    tolerance: float = 0.05,
) -> list[str]:
    """Return names of metrics that regressed beyond tolerance.

    For quality/confidence metrics: regression = current < baseline - tolerance
    For rate metrics (warning/error/low_conf): regression = current > baseline + tolerance
    """
    regressed: list[str] = []
    higher_is_better = {"avg_quality_score", "avg_confidence"}

    for key in _METRIC_KEYS:
        cur = current.get(key, 0.0)
        base = baseline.get(key, 0.0)

        if key in higher_is_better:
            if cur < base - tolerance:
                regressed.append(key)
        elif cur > base + tolerance:
            regressed.append(key)

    return regressed


def run_converter_regression(update_baseline: bool = False) -> tuple[bool, str]:
    """CLI entry point for converter regression detection."""
    traces = load_traces()
    if not traces:
        return True, "No traces found — nothing to regress against."

    current = compute_aggregate_metrics(traces)

    if update_baseline:
        save_baseline(current)
        return True, f"Baseline updated with {len(traces)} traces."

    baseline = load_baseline()
    if baseline is None:
        save_baseline(current)
        return True, f"No baseline found — created from {len(traces)} traces."

    regressed = detect_regressions(current, baseline)
    if not regressed:
        lines = ["Converter regression check: PASSED"]
        for key in _METRIC_KEYS:
            lines.append(
                f"  {key}: {current.get(key, 0.0):.4f} (baseline: {baseline.get(key, 0.0):.4f})"
            )
        return True, "\n".join(lines)

    lines = ["Converter regression check: FAILED"]
    for key in regressed:
        lines.append(
            f"  {key}: {current.get(key, 0.0):.4f} (baseline: {baseline.get(key, 0.0):.4f}) — REGRESSED"
        )
    return False, "\n".join(lines)


__all__ = [
    "compute_aggregate_metrics",
    "detect_regressions",
    "load_baseline",
    "load_traces",
    "run_converter_regression",
    "save_baseline",
]


if __name__ == "__main__":
    update = "--update-baseline" in sys.argv
    passed, report = run_converter_regression(update_baseline=update)
    sys.stdout.write(report + "\n")
    sys.exit(0 if passed else 1)
