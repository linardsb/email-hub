"""Unit tests for the fallback QA check (MSO conditionals + VML)."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestFallback:
    check = get_check("fallback")

    async def test_valid_mso_html_scores_perfect(self, sample_html_valid: str) -> None:
        """Full valid MSO HTML with balanced conditionals, namespaces, DPI → 1.0"""
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0

    async def test_unbalanced_conditional_degrades(self) -> None:
        """Extra opener without closer → score reduction."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            "<!--[if mso]><table><tr><td><![endif]-->"
            "<p>Content</p>"
            "<!--[if mso]></td></tr></table><![endif]-->"
            "<!--[if mso]><p>Orphan opener"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score <= 0.80

    async def test_vml_outside_conditional_degrades(self) -> None:
        """<v:rect> not inside <!--[if mso]> → score reduction."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            "<!--[if mso]><p>MSO</p><![endif]-->"
            "<v:rect>orphan VML</v:rect>"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "VML" in (result.details or "")

    async def test_missing_namespaces_degrades(self) -> None:
        """VML present but no xmlns:v on <html> → score reduction."""
        html = (
            "<!DOCTYPE html><html><head>"
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            "<!--[if mso]><v:rect></v:rect><![endif]-->"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert (
            "xmlns" in (result.details or "").lower()
            or "namespace" in (result.details or "").lower()
        )

    async def test_complex_nested_conditionals_valid(self) -> None:
        """Multiple nested balanced blocks → passes balance checks."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            '<!--[if mso]><table width="600"><tr><td><![endif]-->'
            "<p>Content</p>"
            "<!--[if mso]></td></tr></table><![endif]-->"
            "<!--[if gte mso 12]><v:rect></v:rect><![endif]-->"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_no_mso_at_all_degrades(self, sample_html_minimal: str) -> None:
        """Plain HTML, no MSO/VML → presence checks fail, low score."""
        result = await self.check.run(sample_html_minimal)
        assert result.passed is False
        assert result.score <= 0.5

    async def test_ghost_table_missing_width_degrades(self) -> None:
        """Ghost table pattern without width attr → score reduction."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            '<div style="max-width: 600px;">'
            "<!--[if mso]><table><tr><td><![endif]-->"
            "<p>Content</p>"
            "<!--[if mso]></td></tr></table><![endif]-->"
            "</div>"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "width" in (result.details or "").lower()

    async def test_invalid_version_syntax_degrades(self) -> None:
        """<!--[if mso 13]> invalid version → syntax error."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            "<!--[if mso 13]><p>Bad version</p><![endif]-->"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "13" in (result.details or "")

    async def test_non_mso_block_balanced(self) -> None:
        """<!--[if !mso]><!-->...<!--<![endif]--> correctly paired → passes."""
        html = (
            '<!DOCTYPE html><html lang="en" xmlns:v="urn:schemas-microsoft-com:vml"'
            ' xmlns:o="urn:schemas-microsoft-com:office:office"><head>'
            "<!--[if mso]><xml><o:OfficeDocumentSettings>"
            "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings>"
            "</xml><![endif]--></head><body>"
            '<!--[if mso]><table width="600"><tr><td><![endif]-->'
            "<!--[if !mso]><!--><p>Non-Outlook</p><!--<![endif]-->"
            "<!--[if mso]></td></tr></table><![endif]-->"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is True

    async def test_config_overrides_deductions(self) -> None:
        """Custom QACheckConfig overrides default deduction values."""

        html = "<html><body><p>No MSO at all</p></body></html>"
        config = QACheckConfig(
            enabled=True,
            params={
                "deduction_no_mso": 0.10,
                "deduction_no_namespaces": 0.05,
                "deduction_no_dpi_fix": 0.01,
            },
        )
        result = await self.check.run(html, config)
        assert result.passed is False
        # With reduced deductions (0.10 + 0.05 + 0.01 = 0.16), score should be ~0.84
        assert result.score >= 0.80
