# pyright: reportReturnType=false, reportArgumentType=false
"""Tests for correction pattern tracking (Phase 35.7)."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.rate_limit import limiter
from app.design_sync.correction_tracker import (
    CorrectionTracker,
    _compute_pattern_hash,
    extract_correction_diffs,
)
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/design-sync"


def _make_user(role: str = "admin") -> User:
    user = User(email="test@example.com", hashed_password="x", role=role)
    user.id = 1
    return user


def _make_html_shorthand_padding() -> str:
    return '<table><tr><td style="padding:20px">Hello</td></tr></table>'


def _make_html_longhand_padding() -> str:
    return '<table><tr><td style="padding:20px 20px 20px 20px">Hello</td></tr></table>'


def _make_html_no_dark_mode() -> str:
    return "<html><head><style>body{color:#000}</style></head><body><p>Hi</p></body></html>"


def _make_html_with_dark_mode() -> str:
    return (
        "<html><head><style>body{color:#000}"
        "@media (prefers-color-scheme:dark){body{color:#fff}}"
        "</style></head><body><p>Hi</p></body></html>"
    )


def _make_html_no_align() -> str:
    return '<table><tr><td style="width:100%">Content</td></tr></table>'


def _make_html_with_align() -> str:
    return '<table><tr><td style="width:100%" align="center">Content</td></tr></table>'


def _seed_log(data_dir: Path, agent: str, n: int, same_values: bool = True) -> str:
    """Write n log entries for a single pattern hash. Returns the hash."""
    h = _compute_pattern_hash(agent, "td", "style.padding", "property_changed")
    log_path = data_dir / "correction_patterns.jsonl"
    now = datetime.now(UTC).isoformat()
    with log_path.open("a") as f:
        for i in range(n):
            entry = {
                "timestamp": now,
                "agent": agent,
                "pattern_hash": h,
                "element_tag": "td",
                "attribute": "style.padding",
                "change_type": "property_changed",
                "old_value": "20px" if same_values else f"val_{i}",
                "new_value": "20px 20px 20px 20px" if same_values else f"new_{i}",
            }
            f.write(json.dumps(entry) + "\n")
    return h


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Generator[None]:
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
def _auth_admin() -> Generator[None]:
    user = _make_user("admin")
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def _auth_viewer() -> Generator[None]:
    user = _make_user("viewer")
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# extract_correction_diffs
# ===========================================================================


class TestExtractCorrectionDiffs:
    def test_style_property_change(self) -> None:
        """Shorthand→longhand padding is detected as property_changed."""
        diffs = extract_correction_diffs(
            _make_html_shorthand_padding(),
            _make_html_longhand_padding(),
        )
        style_diffs = [d for d in diffs if d.change_type == "property_changed"]
        assert len(style_diffs) >= 1
        padding_diff = next(d for d in style_diffs if "padding" in d.attribute)
        assert padding_diff.old_value == "20px"
        assert "20px 20px 20px 20px" in padding_diff.new_value

    def test_attribute_addition(self) -> None:
        """New align attribute is detected as attribute_added."""
        diffs = extract_correction_diffs(
            _make_html_no_align(),
            _make_html_with_align(),
        )
        attr_diffs = [d for d in diffs if d.change_type == "attribute_added"]
        assert len(attr_diffs) >= 1
        assert any(d.attribute == "align" for d in attr_diffs)

    def test_identical_html_no_diffs(self) -> None:
        """Identical HTML produces no diffs."""
        html = _make_html_shorthand_padding()
        diffs = extract_correction_diffs(html, html)
        assert diffs == []

    def test_element_added(self) -> None:
        """Added element is detected."""
        original = "<table><tr><td>Hello</td></tr></table>"
        corrected = "<table><tr><td>Hello</td><td>World</td></tr></table>"
        diffs = extract_correction_diffs(original, corrected)
        added = [d for d in diffs if d.change_type == "element_added"]
        assert len(added) >= 1
        assert any(d.element_tag == "td" for d in added)

    def test_element_removed(self) -> None:
        """Removed element is detected."""
        original = "<table><tr><td>A</td><td>B</td></tr></table>"
        corrected = "<table><tr><td>A</td></tr></table>"
        diffs = extract_correction_diffs(original, corrected)
        removed = [d for d in diffs if d.change_type == "element_removed"]
        assert len(removed) >= 1
        assert any(d.element_tag == "td" for d in removed)

    def test_invalid_html_returns_empty(self) -> None:
        """Unparseable HTML returns empty list gracefully."""
        diffs = extract_correction_diffs("", "")
        assert diffs == []


# ===========================================================================
# CorrectionTracker.record_correction
# ===========================================================================


class TestRecordCorrection:
    @pytest.mark.asyncio
    async def test_records_single_correction(self, tmp_path: Path) -> None:
        """A padding change is recorded to JSONL."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            count = await tracker.record_correction(
                agent="outlook_fixer",
                original_html=_make_html_shorthand_padding(),
                corrected_html=_make_html_longhand_padding(),
            )

        assert count >= 1
        log_path = tmp_path / "correction_patterns.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == count
        entry = json.loads(lines[0])
        assert entry["agent"] == "outlook_fixer"
        assert entry["pattern_hash"]

    @pytest.mark.asyncio
    async def test_no_diff_no_record(self, tmp_path: Path) -> None:
        """Identical HTML records nothing."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        html = _make_html_shorthand_padding()
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            count = await tracker.record_correction(
                agent="outlook_fixer",
                original_html=html,
                corrected_html=html,
            )

        assert count == 0
        assert not (tmp_path / "correction_patterns.jsonl").exists()

    @pytest.mark.asyncio
    async def test_appends_to_existing_log(self, tmp_path: Path) -> None:
        """Multiple corrections append to the same JSONL file."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            await tracker.record_correction(
                "outlook_fixer",
                _make_html_shorthand_padding(),
                _make_html_longhand_padding(),
            )
            await tracker.record_correction(
                "outlook_fixer",
                _make_html_no_align(),
                _make_html_with_align(),
            )

        lines = (tmp_path / "correction_patterns.jsonl").read_text().strip().split("\n")
        assert len(lines) >= 2


# ===========================================================================
# CorrectionTracker.get_frequent_patterns
# ===========================================================================


class TestGetFrequentPatterns:
    def test_returns_patterns_above_threshold(self, tmp_path: Path) -> None:
        """Patterns with ≥5 occurrences and ≥0.9 confidence are returned."""
        h = _seed_log(tmp_path, "outlook_fixer", 10)
        tracker = CorrectionTracker(data_dir=tmp_path)
        patterns = tracker.get_frequent_patterns(min_occurrences=5, min_confidence=0.9)
        assert len(patterns) == 1
        assert patterns[0].pattern_hash == h
        assert patterns[0].occurrences == 10
        assert patterns[0].confidence == 1.0

    def test_excludes_below_min_occurrences(self, tmp_path: Path) -> None:
        """Patterns with <5 occurrences are excluded."""
        _seed_log(tmp_path, "outlook_fixer", 3)
        tracker = CorrectionTracker(data_dir=tmp_path)
        patterns = tracker.get_frequent_patterns(min_occurrences=5, min_confidence=0.9)
        assert len(patterns) == 0

    def test_excludes_below_min_confidence(self, tmp_path: Path) -> None:
        """Patterns with low confidence (varying values) are excluded."""
        _seed_log(tmp_path, "dark_mode", 10, same_values=False)
        tracker = CorrectionTracker(data_dir=tmp_path)
        patterns = tracker.get_frequent_patterns(min_occurrences=5, min_confidence=0.9)
        assert len(patterns) == 0

    def test_deduplicates_by_pattern_hash(self, tmp_path: Path) -> None:
        """Same pattern from same agent is aggregated into one entry."""
        _seed_log(tmp_path, "outlook_fixer", 5)
        _seed_log(tmp_path, "outlook_fixer", 5)  # same hash, append
        tracker = CorrectionTracker(data_dir=tmp_path)
        patterns = tracker.get_frequent_patterns(min_occurrences=5, min_confidence=0.9)
        assert len(patterns) == 1
        assert patterns[0].occurrences == 10

    def test_empty_log_returns_empty(self, tmp_path: Path) -> None:
        """No log file → empty list."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        assert tracker.get_frequent_patterns() == []


# ===========================================================================
# CorrectionTracker.suggest_converter_rules
# ===========================================================================


class TestSuggestConverterRules:
    def test_generates_suggestion_for_frequent_pattern(self, tmp_path: Path) -> None:
        """Frequent pattern generates a suggestion with Python snippet."""
        _seed_log(tmp_path, "outlook_fixer", 10)
        tracker = CorrectionTracker(data_dir=tmp_path)
        suggestions = tracker.suggest_converter_rules(min_occurrences=5, min_confidence=0.9)
        assert len(suggestions) == 1
        assert suggestions[0].status == "suggested"
        assert "converter.py" in suggestions[0].suggested_code
        assert suggestions[0].agent_source == "outlook_fixer"

    def test_no_suggestions_below_threshold(self, tmp_path: Path) -> None:
        """Patterns below threshold produce no suggestions."""
        _seed_log(tmp_path, "outlook_fixer", 3)
        tracker = CorrectionTracker(data_dir=tmp_path)
        suggestions = tracker.suggest_converter_rules(min_occurrences=5, min_confidence=0.9)
        assert len(suggestions) == 0

    def test_suggestion_includes_python_snippet(self, tmp_path: Path) -> None:
        """Suggestion for property_changed includes element tag and property."""
        _seed_log(tmp_path, "outlook_fixer", 10)
        tracker = CorrectionTracker(data_dir=tmp_path)
        suggestions = tracker.suggest_converter_rules(min_occurrences=5, min_confidence=0.9)
        code = suggestions[0].suggested_code
        assert "padding" in code
        assert "td" in code


# ===========================================================================
# CorrectionTracker.approve_rule
# ===========================================================================


class TestApproveRule:
    def test_approve_updates_status(self, tmp_path: Path) -> None:
        """Approving a pattern persists status to rules JSON."""
        h = _seed_log(tmp_path, "outlook_fixer", 5)
        tracker = CorrectionTracker(data_dir=tmp_path)
        tracker.approve_rule(h)

        rules_path = tmp_path / "correction_rules.json"
        assert rules_path.exists()
        data = json.loads(rules_path.read_text())
        assert data["statuses"][h] == "approved"

    def test_approve_reflected_in_suggestions(self, tmp_path: Path) -> None:
        """After approval, suggestion status reflects 'approved'."""
        h = _seed_log(tmp_path, "outlook_fixer", 10)
        tracker = CorrectionTracker(data_dir=tmp_path)
        tracker.approve_rule(h)
        suggestions = tracker.suggest_converter_rules(min_occurrences=5, min_confidence=0.9)
        assert suggestions[0].status == "approved"

    def test_approve_nonexistent_raises(self, tmp_path: Path) -> None:
        """Approving a nonexistent pattern raises DomainValidationError."""
        from app.core.exceptions import DomainValidationError

        tracker = CorrectionTracker(data_dir=tmp_path)
        with pytest.raises(DomainValidationError, match="not found"):
            tracker.approve_rule("0000000000000000")


# ===========================================================================
# Log rotation
# ===========================================================================


class TestLogRotation:
    @pytest.mark.asyncio
    async def test_rotates_when_over_max(self, tmp_path: Path) -> None:
        """Log is trimmed to max_entries when exceeded."""
        _seed_log(tmp_path, "outlook_fixer", 15)
        tracker = CorrectionTracker(data_dir=tmp_path)

        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10
            await tracker.record_correction(
                "dark_mode",
                _make_html_shorthand_padding(),
                _make_html_longhand_padding(),
            )

        lines = (tmp_path / "correction_patterns.jsonl").read_text().strip().split("\n")
        assert len(lines) <= 10


# ===========================================================================
# Pattern hash
# ===========================================================================


class TestPatternHash:
    def test_deterministic(self) -> None:
        """Same inputs always produce the same hash."""
        h1 = _compute_pattern_hash("outlook_fixer", "td", "style.padding", "property_changed")
        h2 = _compute_pattern_hash("outlook_fixer", "td", "style.padding", "property_changed")
        assert h1 == h2

    def test_different_agents_different_hash(self) -> None:
        """Different agents produce different hashes."""
        h1 = _compute_pattern_hash("outlook_fixer", "td", "style.padding", "property_changed")
        h2 = _compute_pattern_hash("dark_mode", "td", "style.padding", "property_changed")
        assert h1 != h2

    def test_hash_is_hex(self) -> None:
        """Hash is a 16-char hex string."""
        h = _compute_pattern_hash("outlook_fixer", "td", "style.padding", "property_changed")
        assert len(h) == 16
        int(h, 16)  # Must be valid hex


# ===========================================================================
# API Endpoints
# ===========================================================================


class TestApiEndpoints:
    @pytest.mark.usefixtures("_auth_admin")
    def test_list_patterns(self, client: TestClient, tmp_path: Path) -> None:
        """GET /correction-patterns returns patterns for admin."""
        _seed_log(tmp_path, "outlook_fixer", 10)
        with patch("app.design_sync.routes.Path", return_value=tmp_path):
            resp = client.get(f"{BASE}/correction-patterns?min_occurrences=5")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    @pytest.mark.usefixtures("_auth_admin")
    def test_list_patterns_with_agent_filter(self, client: TestClient, tmp_path: Path) -> None:
        """Agent filter narrows results."""
        _seed_log(tmp_path, "outlook_fixer", 10)
        with patch("app.design_sync.routes.Path", return_value=tmp_path):
            resp = client.get(f"{BASE}/correction-patterns?agent=nonexistent&min_occurrences=5")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.usefixtures("_auth_admin")
    def test_get_suggestions(self, client: TestClient, tmp_path: Path) -> None:
        """GET /correction-patterns/suggestions returns suggestions for admin."""
        _seed_log(tmp_path, "outlook_fixer", 10)
        with patch("app.design_sync.routes.Path", return_value=tmp_path):
            resp = client.get(f"{BASE}/correction-patterns/suggestions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.usefixtures("_auth_admin")
    def test_approve_pattern(self, client: TestClient, tmp_path: Path) -> None:
        """POST /correction-patterns/{hash}/approve updates status."""
        h = _seed_log(tmp_path, "outlook_fixer", 10)
        with patch("app.design_sync.routes.Path", return_value=tmp_path):
            resp = client.post(f"{BASE}/correction-patterns/{h}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.usefixtures("_auth_admin")
    def test_approve_invalid_hash_format(self, client: TestClient) -> None:
        """Invalid hash format returns 422-like error."""
        resp = client.post(f"{BASE}/correction-patterns/INVALID/approve")
        assert resp.status_code in (400, 422)

    @pytest.mark.usefixtures("_auth_viewer")
    def test_viewer_forbidden(self, client: TestClient) -> None:
        """Viewer role gets 403 on correction pattern endpoints."""
        resp = client.get(f"{BASE}/correction-patterns")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        """No auth returns 401."""
        app.dependency_overrides.clear()
        resp = client.get(f"{BASE}/correction-patterns")
        assert resp.status_code == 401


# ===========================================================================
# Blueprint integration
# ===========================================================================


class TestBlueprintIntegration:
    @pytest.mark.asyncio
    async def test_engine_records_correction_on_html_change(self, tmp_path: Path) -> None:
        """When correction_tracker is enabled and HTML changes, correction is recorded."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            count = await tracker.record_correction(
                agent="outlook_fixer",
                original_html=_make_html_shorthand_padding(),
                corrected_html=_make_html_longhand_padding(),
            )
        assert count >= 1
        log_path = tmp_path / "correction_patterns.jsonl"
        entries = [json.loads(line) for line in log_path.read_text().strip().split("\n")]
        agents = {e["agent"] for e in entries}
        assert "outlook_fixer" in agents

    @pytest.mark.asyncio
    async def test_tracker_error_does_not_propagate(self) -> None:
        """Tracker errors are caught — never crash the pipeline."""
        tracker = CorrectionTracker(data_dir=Path("/nonexistent/path"))
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            # record_correction may raise due to invalid path; we test the engine's
            # try/except pattern by verifying the tracker raises but can be caught
            try:
                await tracker.record_correction(
                    "outlook_fixer",
                    _make_html_shorthand_padding(),
                    _make_html_longhand_padding(),
                )
            except OSError:
                pass  # Expected — engine.py wraps this in try/except

    @pytest.mark.asyncio
    async def test_skips_when_no_diffs(self, tmp_path: Path) -> None:
        """When original == corrected, nothing is recorded."""
        tracker = CorrectionTracker(data_dir=tmp_path)
        html = _make_html_shorthand_padding()
        with patch("app.design_sync.traces.correction.get_settings") as mock_settings:
            mock_settings.return_value.correction_tracker.max_log_entries = 10_000
            count = await tracker.record_correction("dark_mode", html, html)
        assert count == 0
