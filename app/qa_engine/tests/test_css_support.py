"""Unit tests for the css_support QA check (bespoke — ontology + cssutils)."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks.css_support import CssSupportCheck
from app.qa_engine.tests._helpers import valid_html


class TestCssSupport:
    check = CssSupportCheck()

    async def test_no_unsupported_css_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        # color-scheme CSS property has limited client support but is required for dark mode
        # Score may be < 1.0 due to color-scheme flagging, but should still be high
        assert result.score >= 0.7

    async def test_position_fixed_flagged(self) -> None:
        html = "<!DOCTYPE html><html><style>div { position: fixed; }</style></html>"
        result = await self.check.run(html)
        # position: fixed has fallbacks, so downgraded to warning (check passes)
        assert "position" in (result.details or "")
        assert result.score < 1.0

    async def test_display_grid_flagged(self) -> None:
        html = "<!DOCTYPE html><html><style>.grid { display: grid; }</style></html>"
        result = await self.check.run(html)
        # display: grid has fallbacks, so downgraded to warning (check passes)
        assert "display" in (result.details or "")
        assert result.score < 1.0

    async def test_display_flex_flagged(self) -> None:
        html = "<!DOCTYPE html><html><style>.flex { display: flex; }</style></html>"
        result = await self.check.run(html)
        # display: flex has fallbacks, so downgraded to warning (check passes)
        assert "display" in (result.details or "")
        assert result.score < 1.0


class TestCssSupportSyntax:
    """Test CSS syntax validation (new in 11.10)."""

    check = CssSupportCheck()

    async def test_vendor_prefix_detected(self) -> None:
        html = valid_html(
            head_extra="<style>td { -webkit-border-radius: 5px; -moz-border-radius: 5px; }</style>"
        )
        result = await self.check.run(html)
        assert result.details is not None
        assert "vendor prefix" in result.details.lower() or "-webkit-" in result.details

    async def test_external_stylesheet_flagged(self) -> None:
        html = valid_html(
            head_extra='<link rel="stylesheet" href="https://example.com/styles.css">'
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert result.details is not None
        assert "external stylesheet" in result.details.lower() or "link" in result.details.lower()

    async def test_import_rule_flagged(self) -> None:
        html = valid_html(
            head_extra=(
                "<style>@import url('https://fonts.googleapis.com/css2?family=Roboto');</style>"
            )
        )
        result = await self.check.run(html)
        assert result.details is not None
        assert "@import" in result.details

    async def test_important_overuse_flagged(self) -> None:
        important_css = "; ".join(f"prop{i}: val{i} !important" for i in range(15))
        html = valid_html(head_extra=f"<style>td {{ {important_css} }}</style>")
        result = await self.check.run(html)
        assert result.details is not None
        assert "!important" in result.details

    async def test_important_in_dark_mode_ok(self) -> None:
        dark_css = """
        @media (prefers-color-scheme: dark) {
            .body { background-color: #000 !important; color: #fff !important; }
        }
        """
        html = valid_html(head_extra=f"<style>{dark_css}</style>")
        result = await self.check.run(html)
        # Should not flag dark mode !important as "overuse"
        if result.details:
            assert "!important declarations outside dark mode" not in result.details

    async def test_important_mixed_block_counts_correctly(self) -> None:
        """Block with dark mode AND non-dark !important: only flag non-dark ones."""
        mixed_css = """
        td { color: red !important; font-size: 14px !important; }
        .header { background: blue !important; }
        @media (prefers-color-scheme: dark) {
            td { color: #fff !important; background: #000 !important; }
        }
        """
        # 5 total !important: 3 outside dark mode, 2 inside.
        # Threshold is 10 by default, so 3 non-dark won't trigger.
        # Lower threshold to 2 to trigger it.
        from app.qa_engine.check_config import QACheckConfig

        config = QACheckConfig(params={"important_threshold": 2})
        html = valid_html(head_extra=f"<style>{mixed_css}</style>")
        result = await self.check.run(html, config)
        assert result.details is not None
        assert "3 !important declarations outside dark mode" in result.details

    async def test_empty_declaration_flagged(self) -> None:
        html = valid_html(body='<p style="color: ; font-size: 14px;">text</p>')
        result = await self.check.run(html)
        assert result.details is not None
        assert "empty" in result.details.lower() or "color" in result.details.lower()

    async def test_clean_css_passes(self) -> None:
        html = valid_html(
            head_extra="<style>td { color: #333; font-size: 14px; }</style>",
            body='<p style="color: #333; font-size: 14px;">Clean CSS</p>',
        )
        result = await self.check.run(html)
        assert "syntax" not in (result.details or "").lower()

    async def test_mso_prefix_not_flagged(self) -> None:
        """mso- prefixed properties are Outlook-specific and valid."""
        html = valid_html(
            body='<p style="mso-line-height-rule: exactly; mso-text-raise: 2px;">text</p>'
        )
        result = await self.check.run(html)
        if result.details:
            assert "mso-" not in result.details

    async def test_dark_mode_multi_condition_media_query(self) -> None:
        """!important in multi-condition dark mode query should be excluded."""
        css = """
        td { color: red !important; }
        @media (min-width: 600px) and (prefers-color-scheme: dark) {
            td { color: #fff !important; background: #000 !important; }
        }
        """
        config = QACheckConfig(params={"important_threshold": 0})
        html = valid_html(head_extra=f"<style>{css}</style>")
        result = await self.check.run(html, config)
        # Only 1 non-dark !important (the td color:red), not 3
        if result.details:
            assert "1 !important" in result.details

    async def test_dark_mode_nested_supports(self) -> None:
        """!important inside @supports nested within dark mode should be excluded."""
        css = """
        @media (prefers-color-scheme: dark) {
            @supports (display: grid) {
                .x { color: #fff !important; }
            }
            td { background: #000 !important; }
        }
        """
        config = QACheckConfig(params={"important_threshold": 0})
        html = valid_html(head_extra=f"<style>{css}</style>")
        result = await self.check.run(html, config)
        # Both !important are inside dark mode — overuse check should not flag them
        assert (
            result.details is None
            or "!important declarations outside dark mode" not in result.details
        )

    async def test_inline_style_with_quoted_fonts(self) -> None:
        """Inline styles with quoted font families should be fully extracted."""
        html = valid_html(
            head_extra="<style>td { font-family: Arial; }</style>",
            body="<td style=\"font-family: 'Segoe UI', Arial, sans-serif;\">text</td>",
        )
        result = await self.check.run(html)
        # font-family has inline fallback — should NOT be flagged as missing
        if result.details:
            assert "'font-family' in <style> block only" not in result.details

    async def test_property_name_no_partial_match(self) -> None:
        """'color' in <style> should not match 'background-color' inline."""
        html = valid_html(
            head_extra="<style>td { color: #333; }</style>",
            body='<td style="background-color: #fff;">text</td>',
        )
        config = QACheckConfig(params={"deduction_non_inline": 0.10})
        result = await self.check.run(html, config)
        # 'color' is in <style> only — background-color inline is NOT a fallback
        assert result.details is not None
        assert "'color' in <style> block only" in result.details
