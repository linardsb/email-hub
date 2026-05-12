"""Unit tests for the dark_mode QA check."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestDarkMode:
    check = get_check("dark_mode")

    @staticmethod
    def _html(
        head: str = "",
        body: str = "<table role='presentation'><tr><td>Hello</td></tr></table>",
        lang: str = "en",
    ) -> str:
        return (
            f'<!DOCTYPE html><html lang="{lang}">'
            f"<head><meta charset='utf-8'><title>Test</title>{head}</head>"
            f"<body>{body}</body></html>"
        )

    # --- Full dark mode passes ---

    async def test_comprehensive_dark_mode_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0

    # --- Group A: Meta Tags ---

    async def test_missing_color_scheme_meta_deducts(self) -> None:
        html = self._html(
            head="<style>@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }"
            ":root { color-scheme: light dark; }</style>"
            "<meta name='supported-color-schemes' content='light dark'>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "color-scheme" in (result.details or "").lower()

    async def test_color_scheme_without_dark_deducts(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light'>"
            "<style>@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "dark" in (result.details or "").lower()

    async def test_supported_color_schemes_missing_minor_deduction(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        # Only supported-color-schemes missing — 0.05 deduction
        assert result.passed is False
        assert result.score >= 0.90

    async def test_css_color_scheme_property_missing_minor(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score >= 0.90

    async def test_meta_in_body_not_head_deducts(self) -> None:
        html = (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<title>Test</title>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
            "</head><body>"
            "<meta name='color-scheme' content='light dark'>"
            "<table role='presentation'><tr><td>Hello</td></tr></table>"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "body" in (result.details or "").lower() or "head" in (result.details or "").lower()

    # --- Group B: Media Queries ---

    async def test_no_media_query_heavy_deduction(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<style>[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score <= 0.7

    async def test_empty_media_query_deducts(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<style>@media (prefers-color-scheme: dark) { }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert (
            "no color" in (result.details or "").lower()
            or "empty" in (result.details or "").lower()
        )

    async def test_media_query_no_important_deducts(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #fff; background-color: #000; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "!important" in (result.details or "")

    async def test_media_query_with_colors_and_important_passes(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #fff !important; background-color: #1a1a1a !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #1a1a1a; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    # --- Group C: Outlook Selectors ---

    async def test_no_outlook_selectors_deducts(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<style>@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        # ogsc + ogsb missing = 0.20
        assert "ogsc" in (result.details or "").lower() or "Outlook" in (result.details or "")

    async def test_empty_outlook_selectors_deducts(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<style>@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { } [data-ogsb] .x { }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert (
            "no css declarations" in (result.details or "").lower()
            or "empty" in (result.details or "").lower()
        )

    async def test_ogsc_and_ogsb_with_declarations_passes(self) -> None:
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #fff !important; } }"
            "[data-ogsc] .x { color: #fff; } [data-ogsb] .x { background-color: #000; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is True

    # --- Group D: Color Coherence (integration tests with inline styles) ---

    async def test_good_contrast_dark_colors_passes(self) -> None:
        # No inline styles means no color pairs extracted — passes by default
        html = self._html(
            head="<meta name='color-scheme' content='light dark'>"
            "<meta name='supported-color-schemes' content='light dark'>"
            "<style>:root { color-scheme: light dark; } "
            "@media (prefers-color-scheme: dark) { .x { color: #e0e0e0 !important; background-color: #1a1a1a !important; } }"
            "[data-ogsc] .x { color: #e0e0e0; } [data-ogsb] .x { background-color: #1a1a1a; }</style>"
        )
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    # --- Group F: Backward Compat ---

    async def test_no_dark_mode_at_all_scores_very_low(self, sample_html_minimal: str) -> None:
        result = await self.check.run(sample_html_minimal)
        assert result.passed is False
        assert result.score < 0.5

    # --- Config Override ---

    async def test_config_overrides_deductions(self) -> None:

        # Override all deductions to minimal values
        config = QACheckConfig(
            enabled=True,
            params={
                "deduction_no_dark_mode": 0.01,
                "deduction_missing_color_scheme": 0.01,
                "deduction_missing_supported": 0.01,
                "deduction_missing_css_color_scheme": 0.01,
                "deduction_no_media_query": 0.01,
                "deduction_no_ogsc": 0.01,
                "deduction_no_ogsb": 0.01,
            },
        )
        html = "<html><body>No dark mode</body></html>"
        result = await self.check.run(html, config)
        assert result.passed is False
        # With all deductions reduced to 0.01, score should be much higher
        assert result.score > 0.9
