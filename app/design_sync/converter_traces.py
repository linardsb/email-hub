"""Shim — moved to ``app.design_sync.traces.converter`` in F060.

Existing import sites (``from app.design_sync.converter_traces import …``)
continue to work via re-export.
"""

from app.design_sync.traces.converter import (
    append_trace,
    build_trace,
    compute_quality_score,
    persist_converter_trace,
)

__all__ = [
    "append_trace",
    "build_trace",
    "compute_quality_score",
    "persist_converter_trace",
]
