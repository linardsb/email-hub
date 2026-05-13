"""Shim — moved to ``app.design_sync.traces.converter`` in F060."""

from app.design_sync.traces.converter import (
    extract_conversion_insights,
    persist_conversion_insights,
)

__all__ = ["extract_conversion_insights", "persist_conversion_insights"]
