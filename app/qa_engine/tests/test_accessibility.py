"""Unit tests for the accessibility QA check (WCAG AA, 24 DOM checks)."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestAccessibility:
    check = get_check("accessibility")

    @staticmethod
    def _html(
        body: str,
        lang: str = "en",
        head: str = "",
    ) -> str:
        return (
            f'<!DOCTYPE html><html lang="{lang}"><head>'
            f'<meta charset="utf-8"><title>Test</title>{head}</head>'
            f"<body>{body}</body></html>"
        )

    # --- Fully accessible email passes ---

    async def test_fully_accessible_email(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td>'
            "<h1>Welcome</h1>"
            "<p>Hello! <strong>Important</strong> info here.</p>"
            "<h2>Products</h2>"
            '<a href="https://x.com/product">View product details</a>'
            '<img src="product.jpg" alt="Blue cotton t-shirt">'
            '<img src="pixel.gif" width="1" height="1" alt="" aria-hidden="true">'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_accessible_html_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0

    async def test_empty_html_fails(self) -> None:
        result = await self.check.run("")
        assert result.passed is False
        assert result.score == 0.0

    # --- Group A: Language ---

    async def test_lang_present_passes(self) -> None:
        html = self._html('<table role="presentation"><tr><td><h1>Hello</h1></td></tr></table>')
        result = await self.check.run(html)
        assert "lang" not in (result.details or "").lower()

    async def test_lang_missing_degrades(self) -> None:
        html = '<!DOCTYPE html><html><head><title>T</title></head><body><table role="presentation"><tr><td><h1>Hi</h1></td></tr></table></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "lang" in (result.details or "").lower()

    async def test_lang_invalid_degrades(self) -> None:
        html = '<!DOCTYPE html><html lang=""><head><title>T</title></head><body><table role="presentation"><tr><td><h1>Hi</h1></td></tr></table></body></html>'
        result = await self.check.run(html)
        assert "lang" in (result.details or "").lower()

    # --- Group B: Table Semantics ---

    async def test_layout_table_with_role_passes(self) -> None:
        html = self._html('<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>')
        result = await self.check.run(html)
        assert "presentation" not in (result.details or "").lower()

    async def test_layout_table_without_role_degrades(self) -> None:
        html = self._html("<table><tr><td><h1>Content</h1></td></tr></table>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "presentation" in (result.details or "").lower()

    async def test_data_table_without_scope_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<table role="table"><tr><th>Name</th></tr><tr><td>Val</td></tr></table>'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert "scope" in (result.details or "").lower()

    async def test_mixed_signals_degrades(self) -> None:
        html = self._html('<table role="presentation"><tr><th>Bad</th></tr></table><h1>Hi</h1>')
        result = await self.check.run(html)
        assert "conflict" in (result.details or "").lower()

    # --- Group C: Image Accessibility ---

    async def test_img_with_alt_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<img src="x.png" alt="Photo"></td></tr></table>'
        )
        result = await self.check.run(html)
        assert "missing alt" not in (result.details or "").lower()

    async def test_img_missing_alt_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1><img src="photo.jpg"></td></tr></table>'
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "alt" in (result.details or "").lower()

    async def test_tracking_pixel_with_empty_alt_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<img src="pixel.gif" width="1" height="1" alt=""></td></tr></table>'
        )
        result = await self.check.run(html)
        assert "tracking" not in (result.details or "").lower()

    async def test_tracking_pixel_with_text_alt_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<img src="pixel.gif" width="1" height="1" alt="track"></td></tr></table>'
        )
        result = await self.check.run(html)
        assert (
            "tracking" in (result.details or "").lower()
            or "pixel" in (result.details or "").lower()
        )

    async def test_linked_img_no_alt_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<a href="https://x.com"><img src="hero.jpg" alt=""></a></td></tr></table>'
        )
        result = await self.check.run(html)
        assert (
            "linked" in (result.details or "").lower() or "link" in (result.details or "").lower()
        )

    # --- Group D: Heading Hierarchy (disabled — td-only email layout has no h tags) ---

    async def test_heading_rules_disabled_no_deduction(self) -> None:
        """Heading rules are disabled — emails use td-only layout with no h tags."""
        html = self._html('<table role="presentation"><tr><td>No headings</td></tr></table>')
        result = await self.check.run(html)
        assert "heading" not in (result.details or "").lower()

    # --- Group E: Link Accessibility ---

    async def test_descriptive_link_text_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<a href="https://x.com">View your order</a></td></tr></table>'
        )
        result = await self.check.run(html)
        assert "generic" not in (result.details or "").lower()

    async def test_generic_link_text_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<a href="https://x.com">Click here</a></td></tr></table>'
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert (
            "generic" in (result.details or "").lower()
            or "click here" in (result.details or "").lower()
        )

    async def test_empty_link_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<a href="https://x.com"></a></td></tr></table>'
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "empty" in (result.details or "").lower()

    async def test_redundant_links_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<a href="https://x.com"><img src="p.jpg" alt="Product"></a>'
            '<a href="https://x.com">Product</a>'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert "redundant" in (result.details or "").lower()

    # --- Group F: Content Semantics ---

    async def test_strong_em_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            "<strong>Bold</strong> and <em>italic</em></td></tr></table>"
        )
        result = await self.check.run(html)
        assert "<b>" not in (result.details or "")

    async def test_b_i_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            "<b>Bold</b> and <i>italic</i></td></tr></table>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "strong" in (result.details or "").lower() or "em" in (result.details or "").lower()

    async def test_consecutive_br_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>text<br><br>more text</td></tr></table>'
        )
        result = await self.check.run(html)
        assert "br" in (result.details or "").lower()

    async def test_outline_none_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>',
            head="<style>a { outline: none; }</style>",
        )
        result = await self.check.run(html)
        assert "outline" in (result.details or "").lower()

    # --- Group G: Dark Mode Contrast ---

    async def test_dark_mode_safe_colors_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>',
            head='<meta name="color-scheme" content="light dark">'
            "<style>@media (prefers-color-scheme: dark) { .body { background-color: #1a1a1a; color: #f0f0f0; } }</style>",
        )
        result = await self.check.run(html)
        assert "dark mode" not in (result.details or "").lower()
        assert "unsafe" not in (result.details or "").lower()

    async def test_dark_mode_unsafe_pure_bw_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>',
            head='<meta name="color-scheme" content="light dark">'
            "<style>@media (prefers-color-scheme: dark) { .body { background-color: #000000; color: #ffffff; } }</style>",
        )
        result = await self.check.run(html)
        assert (
            "dark mode" in (result.details or "").lower()
            or "unsafe" in (result.details or "").lower()
            or "#ffffff" in (result.details or "").lower()
        )

    async def test_dark_meta_no_styles_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>',
            head='<meta name="color-scheme" content="light dark">',
        )
        result = await self.check.run(html)
        assert "dark" in (result.details or "").lower()

    async def test_no_dark_mode_no_issue(self) -> None:
        """Emails without dark mode meta should not trigger G21/G22."""
        html = self._html('<table role="presentation"><tr><td><h1>Hi</h1></td></tr></table>')
        result = await self.check.run(html)
        assert "dark" not in (result.details or "").lower()

    # --- Group H: AMP Form Accessibility ---

    async def test_input_with_label_passes(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<label for="email">Email</label><input type="email" id="email">'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert "label" not in (result.details or "").lower()

    async def test_input_no_label_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<input type="email" placeholder="Email">'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert (
            "label" in (result.details or "").lower()
            or "placeholder" in (result.details or "").lower()
        )

    async def test_required_no_aria_degrades(self) -> None:
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1>'
            '<label for="name">Name</label><input type="text" id="name" required>'
            "</td></tr></table>"
        )
        result = await self.check.run(html)
        assert (
            "required" in (result.details or "").lower() or "aria" in (result.details or "").lower()
        )

    async def test_no_form_elements_no_issues(self) -> None:
        """Emails without form elements should not trigger H23/H24."""
        html = self._html(
            '<table role="presentation"><tr><td><h1>Hi</h1><p>No forms</p></td></tr></table>'
        )
        result = await self.check.run(html)
        assert "label" not in (result.details or "").lower()
        assert "aria-required" not in (result.details or "").lower()

    # --- Config override ---

    async def test_config_overrides_deduction(self) -> None:

        html = '<!DOCTYPE html><html><head><title>T</title></head><body><table role="presentation"><tr><td><h1>Hi</h1></td></tr></table></body></html>'
        config = QACheckConfig(params={"deduction_lang_missing": 0.50})
        result = await self.check.run(html, config)
        # Score should reflect the higher deduction
        assert result.score < 0.55
