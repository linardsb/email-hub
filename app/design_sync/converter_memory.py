# pyright: reportPrivateUsage=false
"""Shim — moved to ``app.design_sync.traces.converter`` in F060.

Re-exports private constants (`_CLEAN_CONFIDENCE_THRESHOLD`,
`_MAX_CONTENT_LENGTH`) intentionally so the pre-F060 tests that imported
them keep working unchanged.
"""

from app.design_sync.traces.converter import (
    _CLEAN_CONFIDENCE_THRESHOLD,
    _MAX_CONTENT_LENGTH,
    build_conversion_metadata,
    format_conversion_quality,
    persist_conversion_quality,
)

__all__ = [
    "_CLEAN_CONFIDENCE_THRESHOLD",
    "_MAX_CONTENT_LENGTH",
    "build_conversion_metadata",
    "format_conversion_quality",
    "persist_conversion_quality",
]
