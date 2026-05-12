"""Unit tests for the file_size QA check."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestFileSize:
    """Tests for FileSizeCheck with multi-client thresholds."""

    check = get_check("file_size")

    async def test_small_html_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0

    async def test_under_all_thresholds(self) -> None:
        html = "x" * (50 * 1024)
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_over_yahoo_threshold(self) -> None:
        """76KB — exceeds Yahoo 75KB but under Gmail 102KB."""
        html = "x" * (76 * 1024)
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score < 1.0
        assert "yahoo" in (result.details or "").lower()

    async def test_over_outlook_threshold(self) -> None:
        """101KB — exceeds Outlook 100KB, Braze 100KB, Yahoo 75KB but under Gmail 102KB."""
        html = "x" * (101 * 1024)
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score < 0.8

    async def test_over_gmail_threshold(self) -> None:
        """103KB — exceeds ALL thresholds including Gmail 102KB."""
        html = "x" * (103 * 1024)
        result = await self.check.run(html)
        assert result.passed is False
        assert result.severity == "error"
        assert result.score < 0.5

    async def test_details_include_size_summary(self) -> None:
        """Details should include file size summary with breakdown."""
        html = "x" * (50 * 1024)
        result = await self.check.run(html)
        assert "Raw:" in (result.details or "")

    async def test_custom_gmail_threshold(self) -> None:
        """Config can override Gmail threshold."""

        config = QACheckConfig(params={"gmail_threshold_kb": 200})
        html = "x" * (103 * 1024)
        result = await self.check.run(html, config)
        details = (result.details or "").lower()
        # Gmail check should pass (103 < 200), but Yahoo/Outlook/Braze still fail
        assert "gmail" not in details

    async def test_severity_escalation(self) -> None:
        """Over Gmail = error severity; over Yahoo only = warning severity."""
        # Over Gmail — error
        html_big = "x" * (105 * 1024)
        result_big = await self.check.run(html_big)
        assert result_big.severity == "error"

        # Over Yahoo only — warning
        html_mid = "x" * (80 * 1024)
        result_mid = await self.check.run(html_mid)
        assert result_mid.severity == "warning"

    async def test_score_degrades_with_more_violations(self) -> None:
        """Score should be lower when more client thresholds are exceeded."""
        html_80 = "x" * (80 * 1024)  # Yahoo only
        html_105 = "x" * (105 * 1024)  # All clients

        r80 = await self.check.run(html_80)
        r105 = await self.check.run(html_105)

        assert r105.score < r80.score

    async def test_inline_css_bloat_flagged(self) -> None:
        """HTML dominated by inline styles should flag content distribution issue."""
        styled_divs = (
            '<div style="color:red;font-size:16px;font-family:Arial,sans-serif;'
            "padding:20px;margin:10px;border:1px solid #ccc;"
            'background-color:#f0f0f0;text-align:center;">x</div>'
        ) * 200
        base = (
            f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f"</head><body>{styled_divs}</body></html>"
        )
        result = await self.check.run(base)
        details = (result.details or "").lower()
        assert "inline" in details or "style" in details

    async def test_disabled_check_still_runs(self) -> None:
        """The check itself doesn't check enabled — the service does."""

        config = QACheckConfig(enabled=False, params={})
        html = "x" * (200 * 1024)
        result = await self.check.run(html, config)
        assert result.passed is False
