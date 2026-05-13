# pyright: reportPrivateUsage=false
"""Shim — moved to ``app.design_sync.traces.correction`` in F060.

Re-exports `_compute_pattern_hash` intentionally so the pre-F060 test
that imports it keeps working.
"""

from app.design_sync.traces.correction import (
    ConverterRuleSuggestion,
    ConverterRuleSuggestionResponse,
    CorrectionDiff,
    CorrectionPattern,
    CorrectionPatternResponse,
    CorrectionTracker,
    RuleStatus,
    _compute_pattern_hash,
    extract_correction_diffs,
)

__all__ = [
    "ConverterRuleSuggestion",
    "ConverterRuleSuggestionResponse",
    "CorrectionDiff",
    "CorrectionPattern",
    "CorrectionPatternResponse",
    "CorrectionTracker",
    "RuleStatus",
    "_compute_pattern_hash",
    "extract_correction_diffs",
]
