"""Converter trace & correction observability (F060).

Consolidates the previously-scattered modules
``converter_traces``, ``converter_insights``, ``converter_memory``,
``converter_regression`` and ``correction_tracker``. Legacy file paths
(``app/design_sync/converter_*.py``) remain as thin re-export shims so
the ~20 existing import sites keep working untouched.
"""

from app.design_sync.traces.converter import (
    append_trace,
    build_conversion_metadata,
    build_trace,
    compute_quality_score,
    extract_conversion_insights,
    format_conversion_quality,
    persist_conversion_insights,
    persist_conversion_quality,
    persist_converter_trace,
)
from app.design_sync.traces.correction import (
    ConverterRuleSuggestion,
    ConverterRuleSuggestionResponse,
    CorrectionDiff,
    CorrectionPattern,
    CorrectionPatternResponse,
    CorrectionTracker,
    extract_correction_diffs,
)
from app.design_sync.traces.regression import (
    compute_aggregate_metrics,
    detect_regressions,
    load_baseline,
    load_traces,
    run_converter_regression,
    save_baseline,
)
from app.design_sync.traces.writer import TraceWriter

__all__ = [
    "ConverterRuleSuggestion",
    "ConverterRuleSuggestionResponse",
    "CorrectionDiff",
    "CorrectionPattern",
    "CorrectionPatternResponse",
    "CorrectionTracker",
    "TraceWriter",
    "append_trace",
    "build_conversion_metadata",
    "build_trace",
    "compute_aggregate_metrics",
    "compute_quality_score",
    "detect_regressions",
    "extract_conversion_insights",
    "extract_correction_diffs",
    "format_conversion_quality",
    "load_baseline",
    "load_traces",
    "persist_conversion_insights",
    "persist_conversion_quality",
    "persist_converter_trace",
    "run_converter_regression",
    "save_baseline",
]
