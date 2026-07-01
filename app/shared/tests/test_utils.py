"""Tests for shared utility helpers."""

from __future__ import annotations

import pytest

from app.shared.utils import escape_like


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("hello world", "hello world"),  # no wildcards -> unchanged
        ("%", r"\%"),  # lone percent
        ("_", r"\_"),  # lone underscore
        ("\\", r"\\"),  # lone backslash -> doubled
        (r"\%_", r"\\\%\_"),  # ordering: backslash-first, no double-escape
        (r"50%_off\deal", r"50\%\_off\\deal"),  # realistic combined string
    ],
)
def test_escape_like(raw: str, escaped: str) -> None:
    assert escape_like(raw) == escaped
