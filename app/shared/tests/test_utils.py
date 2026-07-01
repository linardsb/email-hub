"""Tests for shared utility functions."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.utils import format_iso


def test_format_iso_returns_isoformat_string() -> None:
    """format_iso(dt) returns dt.isoformat()."""
    assert format_iso(datetime(2026, 7, 1, 12, 30, 0, tzinfo=UTC)) == "2026-07-01T12:30:00+00:00"
