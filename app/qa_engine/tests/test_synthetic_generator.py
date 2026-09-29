"""Tests for synthetic adversarial email generator."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.qa_engine.synthetic_generator import (
    TARGET_CHECKS,
    SyntheticEmailGenerator,
    load_base_templates,
)


@pytest.fixture()
def generator() -> SyntheticEmailGenerator:
    """Generator with real golden templates."""
    return SyntheticEmailGenerator()


@pytest.fixture()
def small_generator() -> SyntheticEmailGenerator:
    """Generator with a single small template for fast tests."""
    templates = load_base_templates()
    first_name = min(templates.keys())
    return SyntheticEmailGenerator(base_templates={first_name: templates[first_name]})


# ---------------------------------------------------------------------------
# Group A — Generator mechanics
# ---------------------------------------------------------------------------


class TestGeneratorMechanics:
    def test_generate_for_check_returns_correct_count(
        self, generator: SyntheticEmailGenerator
    ) -> None:
        emails = generator.generate_for_check("accessibility", count=5)
        assert len(emails) == 5
        assert all(e.defect_category == "accessibility" for e in emails)

    def test_generate_adversarial_set_covers_all_checks(
        self, generator: SyntheticEmailGenerator
    ) -> None:
        emails = generator.generate_adversarial_set(count_per_check=5)
        assert len(emails) == len(TARGET_CHECKS) * 5
        categories = {e.defect_category for e in emails}
        assert categories == set(TARGET_CHECKS)

    def test_base_template_is_recognizable(self, small_generator: SyntheticEmailGenerator) -> None:
        """Mutated HTML should still resemble an email (has table structure)."""
        emails = small_generator.generate_for_check("accessibility", count=3)
        for email in emails:
            assert "<table" in email.html.lower()

    def test_difficulty_distribution(self, small_generator: SyntheticEmailGenerator) -> None:
        emails = small_generator.generate_for_check("accessibility", count=5)
        difficulties = [e.difficulty for e in emails]
        counts = Counter(difficulties)
        assert counts["easy"] == 2
        assert counts["medium"] == 2
        assert counts["hard"] == 1


# ---------------------------------------------------------------------------
# Group B — Defect specificity
# ---------------------------------------------------------------------------


class TestDefectSpecificity:
    def test_file_size_boundary(self, small_generator: SyntheticEmailGenerator) -> None:
        emails = small_generator.generate_for_check("file_size", count=1)
        size_bytes = len(emails[0].html.encode("utf-8"))
        # easy difficulty -> 101KB target
        assert 101 * 1024 - 100 <= size_bytes <= 101 * 1024 + 100

    def test_accessibility_defect_removes_alt(
        self, small_generator: SyntheticEmailGenerator
    ) -> None:
        emails = small_generator.generate_for_check("accessibility", count=1)
        # easy difficulty removes alt attributes
        assert 'alt="' not in emails[0].html

    def test_liquid_syntax_has_unclosed_tag(self, small_generator: SyntheticEmailGenerator) -> None:
        emails = small_generator.generate_for_check("liquid_syntax", count=1)
        html = emails[0].html
        assert "{% if " in html
        assert html.count("{% if") > html.count("{% endif")

    def test_dark_mode_removes_media_query(self, small_generator: SyntheticEmailGenerator) -> None:
        emails = small_generator.generate_for_check("dark_mode", count=1)
        assert "prefers-color-scheme" not in emails[0].html

    def test_link_validation_injects_javascript_href(
        self, small_generator: SyntheticEmailGenerator
    ) -> None:
        emails = small_generator.generate_for_check("link_validation", count=1)
        assert "javascript:" in emails[0].html


# ---------------------------------------------------------------------------
# Group C — Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_save_writes_manifest_and_html_files(
        self, small_generator: SyntheticEmailGenerator, tmp_path: Path
    ) -> None:
        emails = small_generator.generate_for_check("html_validation", count=3)
        output = SyntheticEmailGenerator.save(emails, tmp_path / "output")

        manifest_path = output / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["count"] == 3
        assert len(manifest["emails"]) == 3

        for email in emails:
            assert (output / f"{email.id}.html").exists()

    def test_expected_failures_labels_are_correct(self, generator: SyntheticEmailGenerator) -> None:
        for check_name in TARGET_CHECKS:
            emails = generator.generate_for_check(check_name, count=1)
            email = emails[0]
            assert email.expected_failures.get(check_name) is True
            assert email.defect_category == check_name

    @pytest.mark.asyncio()
    async def test_round_trip_check_detects_defect(
        self, small_generator: SyntheticEmailGenerator
    ) -> None:
        """Run actual QA check on injected email and verify it detects the defect."""
        from app.qa_engine.checks._factory import get_check

        emails = small_generator.generate_for_check("dark_mode", count=1)
        check = get_check("dark_mode")
        result = await check.run(emails[0].html)
        # easy difficulty removes @media (prefers-color-scheme: dark) block
        assert result.score < 1.0 or not result.passed
