"""Unit tests for the brand_compliance QA check."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestBrandCompliance:
    check = get_check("brand_compliance")

    def _config(self, **params: object) -> QACheckConfig:
        return QACheckConfig(params=params)

    # --- Backward compatibility: no rules configured ---

    async def test_no_rules_passes(self, sample_html_valid: str) -> None:
        """No brand rules configured → pass with info message."""
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0
        assert "No brand rules configured" in (result.details or "")

    async def test_no_rules_with_empty_config(self) -> None:
        html = "<html><body><p>Test</p></body></html>"
        config = self._config(
            allowed_colors=[],
            required_fonts=[],
            required_elements=[],
            forbidden_patterns=[],
        )
        result = await self.check.run(html, config)
        assert result.passed is True
        assert result.score == 1.0

    async def test_disabled_config(self) -> None:
        from app.qa_engine.check_config import QACheckConfig

        config = QACheckConfig(enabled=False)
        result = await self.check.run("<html><body></body></html>", config)
        assert result.passed is True
        assert "disabled" in (result.details or "").lower()

    # --- Color compliance ---

    async def test_matching_colors_pass(self) -> None:
        html = '<html><body><p style="color: #ff0000;">Red</p></body></html>'
        config = self._config(allowed_colors=["#ff0000"])
        result = await self.check.run(html, config)
        assert result.passed is True
        assert result.score == 1.0

    async def test_off_brand_color_deducted(self) -> None:
        html = '<html><body><p style="color: #00ff00;">Green</p></body></html>'
        config = self._config(allowed_colors=["#ff0000", "#0000ff"])
        result = await self.check.run(html, config)
        assert result.passed is False
        assert result.score < 1.0
        assert "Off-brand color" in (result.details or "")

    # --- Typography compliance ---

    async def test_matching_fonts_pass(self) -> None:
        html = "<html><head><style>body { font-family: Arial, sans-serif; }</style></head><body>Test</body></html>"
        config = self._config(required_fonts=["arial"])
        result = await self.check.run(html, config)
        assert result.passed is True

    async def test_wrong_font_deducted(self) -> None:
        html = '<html><head><style>body { font-family: "Comic Sans MS", cursive; }</style></head><body>Test</body></html>'
        config = self._config(required_fonts=["arial", "helvetica"])
        result = await self.check.run(html, config)
        assert result.passed is False
        assert "Non-brand font" in (result.details or "")

    # --- Required elements ---

    async def test_missing_footer_deducted(self) -> None:
        html = "<html><body><p>No footer here</p></body></html>"
        config = self._config(required_elements=["footer"])
        result = await self.check.run(html, config)
        assert result.passed is False
        assert "footer" in (result.details or "").lower()

    async def test_footer_present_passes(self) -> None:
        html = '<html><body><div class="footer">Legal text</div></body></html>'
        config = self._config(required_elements=["footer"])
        result = await self.check.run(html, config)
        assert result.passed is True

    async def test_missing_logo_deducted(self) -> None:
        html = "<html><body><img src='photo.jpg' alt='photo'></body></html>"
        config = self._config(required_elements=["logo"])
        result = await self.check.run(html, config)
        assert result.passed is False

    async def test_logo_present_passes(self) -> None:
        html = "<html><body><img src='logo.png' alt='Company logo'></body></html>"
        config = self._config(required_elements=["logo"])
        result = await self.check.run(html, config)
        assert result.passed is True

    # --- Forbidden patterns ---

    async def test_forbidden_pattern_deducted(self) -> None:
        html = "<html><body><p>Click here to win!</p></body></html>"
        config = self._config(forbidden_patterns=["click here"])
        result = await self.check.run(html, config)
        assert result.passed is False
        assert "Forbidden pattern" in (result.details or "")

    async def test_no_forbidden_patterns_passes(self) -> None:
        html = "<html><body><p>Learn more about our services</p></body></html>"
        config = self._config(forbidden_patterns=["click here", "buy now"])
        result = await self.check.run(html, config)
        assert result.passed is True

    # --- Empty/invalid HTML ---

    async def test_empty_html_fails(self) -> None:
        config = self._config(allowed_colors=["#ff0000"])
        result = await self.check.run("", config)
        assert result.passed is False
        assert result.score == 0.0
