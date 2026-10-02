"""Strict-xfail marks for manifest ``known_failures`` rows (CE-3 #421).

A row names a test function, the case, an owner (``#<issue>`` or a
deferred-items id) and a reason. The mark is ``xfail(strict=True)``, so a row
whose test starts passing fails the run until the fixing PR deletes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.tests.regression_runner import load_case_manifest

_DEBUG_DIR = Path(__file__).resolve().parents[3] / "data" / "debug"


def known_failure_marks(case_id: str, test_name: str) -> list[pytest.MarkDecorator]:
    """One strict xfail mark for ``test_name`` on ``case_id`` if any row names it.

    ``raises=AssertionError``: only a failed assertion counts as the known
    failure; a crash in the test still fails the run. Rows naming the same test
    (two causes) are merged into one mark whose reason lists every owner.
    """
    manifest_path = _DEBUG_DIR / case_id / "manifest.yaml"
    if not manifest_path.exists():
        return []
    rows = [
        row
        for row in load_case_manifest(_DEBUG_DIR / case_id).known_failures
        if row.test == test_name
    ]
    if not rows:
        return []
    reason = "; ".join(f"{row.owner}: {row.reason}" for row in rows)
    return [pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)]


def apply_known_failures(request: pytest.FixtureRequest, case_id: str) -> None:
    """Mark the requesting test when the case's manifest lists it."""
    for mark in known_failure_marks(case_id, request.function.__name__):
        request.applymarker(mark)
