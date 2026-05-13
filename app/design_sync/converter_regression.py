"""Shim — moved to ``app.design_sync.traces.regression`` in F060."""

import sys

from app.design_sync.traces.regression import (
    compute_aggregate_metrics,
    detect_regressions,
    load_baseline,
    load_traces,
    run_converter_regression,
    save_baseline,
)

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
