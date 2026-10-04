"""Tests for post-conversion quality contracts (39.4)."""

from __future__ import annotations

from app.design_sync.quality_contracts import (
    check_completeness,
    check_contrast,
    check_placeholders,
    run_quality_contracts,
)


def _make_html(body: str) -> str:
    """Wrap body content in a minimal email HTML shell."""
    return f"<!DOCTYPE html><html><head><title>Test</title></head><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# Contrast tests (6)
# ---------------------------------------------------------------------------


class TestCheckContrast:
    """WCAG AA contrast ratio validation."""

    def test_white_on_orange_warns(self) -> None:
        """#FFFFFF on #FE5117 → ratio ~3.2:1, below 4.5:1 for normal text."""
        html = _make_html(
            '<td style="background-color:#FE5117;">'
            '<span style="color:#FFFFFF;font-size:14px;">Hello</span>'
            "</td>"
        )
        warnings = check_contrast(html)
        assert len(warnings) == 1
        assert warnings[0].category == "contrast"
        assert float(warnings[0].context["ratio"]) < 4.5

    def test_dark_on_white_no_warning(self) -> None:
        """#333333 on #FFFFFF → ratio ~12.6:1, passes WCAG AA."""
        html = _make_html(
            '<td style="background-color:#FFFFFF;"><span style="color:#333333;">Hello</span></td>'
        )
        warnings = check_contrast(html)
        assert len(warnings) == 0

    def test_dark_on_orange_warns(self) -> None:
        """#333333 on #FE5117 → ratio ~3.85:1, below 4.5:1 for normal text."""
        html = _make_html(
            '<td style="background-color:#FE5117;"><span style="color:#333333;">Hello</span></td>'
        )
        warnings = check_contrast(html)
        assert len(warnings) == 1
        assert float(warnings[0].context["ratio"]) < 4.5

    def test_large_text_lower_threshold(self) -> None:
        """Large text (18px+) with ratio ~3.5:1 → passes (threshold 3.0:1)."""
        # #767676 on #FFFFFF gives ~4.54:1, too high.
        # Use a color pair that's between 3.0 and 4.5.
        # #757575 on #FFFFFF = ~4.6:1 — still above. Let's use #949494 on #FFFFFF = ~2.8:1
        # Actually, let's compute: we need ratio between 3.0 and 4.5 for the test.
        # #808080 on #FFFFFF → lum(#808080) ≈ 0.216, lum(#FFF) = 1.0
        # ratio = (1.0 + 0.05) / (0.216 + 0.05) = 1.05 / 0.266 ≈ 3.95 — perfect.
        html = _make_html(
            '<td style="background-color:#FFFFFF;">'
            '<span style="color:#808080;font-size:18px;">Large text</span>'
            "</td>"
        )
        warnings = check_contrast(html)
        # Ratio ~3.95:1, above large-text threshold 3.0:1 → no warning
        assert len(warnings) == 0

    def test_no_inline_styles_no_warnings(self) -> None:
        """HTML without inline color styles produces no warnings."""
        html = _make_html("<td><p>Plain text</p></td>")
        warnings = check_contrast(html)
        assert len(warnings) == 0

    def test_multiple_elements_mixed(self) -> None:
        """Multiple elements: one passes, one fails → exactly 1 warning."""
        html = _make_html(
            '<td style="background-color:#FE5117;">'
            '<span style="color:#FFFFFF;">Low contrast</span>'
            '<span style="color:#000000;">Good contrast</span>'
            "</td>"
        )
        warnings = check_contrast(html)
        # #FFFFFF on #FE5117 → ~3.2:1 (fail), #000000 on #FE5117 → ~4.3:1 (fail too, < 4.5)
        # Actually both may fail. Let's use a color that clearly passes.
        # Re-do: one pass, one fail
        html = _make_html(
            '<td style="background-color:#FFFFFF;">'
            '<span style="color:#CCCCCC;">Low contrast</span>'
            '<span style="color:#000000;">Good contrast</span>'
            "</td>"
        )
        warnings = check_contrast(html)
        # #CCCCCC on #FFFFFF → very low contrast → 1 warning
        # #000000 on #FFFFFF → 21:1 → no warning
        assert len(warnings) == 1
        assert warnings[0].context["text_color"] == "#CCCCCC"


# ---------------------------------------------------------------------------
# Completeness tests (6)
# ---------------------------------------------------------------------------


class TestCheckCompleteness:
    """Section and button count verification."""

    def test_all_sections_present(self) -> None:
        """12 section markers with input=12 → no warning."""
        markers = "\n".join(f"<!-- section:node{i}:content -->" for i in range(12))
        html = _make_html(markers)
        warnings = check_completeness(html, input_section_count=12)
        assert len(warnings) == 0

    def test_missing_section_warns(self) -> None:
        """11 section markers with input=12 → warning."""
        markers = "\n".join(f"<!-- section:node{i}:content -->" for i in range(11))
        html = _make_html(markers)
        warnings = check_completeness(html, input_section_count=12)
        assert len(warnings) == 1
        assert warnings[0].category == "completeness"
        assert warnings[0].context["type"] == "section"
        assert warnings[0].context["expected"] == 12
        assert warnings[0].context["found"] == 11

    def test_all_buttons_present(self) -> None:
        """3 buttons in HTML with input=3 → no warning."""
        buttons = "\n".join(
            f'<a href="#" style="display:inline-block;padding:12px 24px;">CTA {i}</a>'
            for i in range(3)
        )
        html = _make_html(buttons)
        warnings = check_completeness(html, input_button_count=3)
        assert len(warnings) == 0

    def test_missing_button_warns(self) -> None:
        """2 buttons in HTML with input=3 → warning."""
        buttons = "\n".join(
            f'<a href="#" style="display:inline-block;padding:12px 24px;">CTA {i}</a>'
            for i in range(2)
        )
        html = _make_html(buttons)
        warnings = check_completeness(html, input_button_count=3)
        assert len(warnings) == 1
        assert warnings[0].context["type"] == "button"
        assert warnings[0].context["expected"] == 3
        assert warnings[0].context["found"] == 2

    def test_zero_expected_no_warning(self) -> None:
        """0 section markers with input=0 → no warning."""
        html = _make_html("<td>Content</td>")
        warnings = check_completeness(html, input_section_count=0, input_button_count=0)
        assert len(warnings) == 0

    def test_mso_vml_buttons_counted(self) -> None:
        """MSO v:roundrect button patterns are counted."""
        vml_button = (
            "<!--[if mso]>"
            '<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" '
            'style="width:200px;height:40px;" arcsize="10%" fillcolor="#FF0000">'
            "</v:roundrect>"
            "<![endif]-->"
        )
        html = _make_html(vml_button * 2)
        warnings = check_completeness(html, input_button_count=2)
        assert len(warnings) == 0

    def test_vml_twin_counts_once(self) -> None:
        """CE-11: one VML-wrapped anchor is one button, not two (open + close tag)."""
        anchor = '<a href="#" style="display:inline-block;padding:12px 24px;">CTA</a>'
        wrapped = (
            '<!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="#" '
            'style="height:40px;v-text-anchor:middle;width:200px;" arcsize="10%" stroke="f" '
            'fillcolor="#FF0000"><center>CTA</center></v:roundrect><![endif]-->'
            f"<!--[if !mso]><!-->{anchor}<!--<![endif]-->"
        )
        warnings = check_completeness(_make_html(wrapped), input_button_count=2)
        assert len(warnings) == 1
        assert warnings[0].context["found"] == 1


# ---------------------------------------------------------------------------
# Placeholder tests (4)
# ---------------------------------------------------------------------------


class TestCheckPlaceholders:
    """Leaked placeholder text detection."""

    def test_image_caption_placeholder(self) -> None:
        """'Image caption' text → warning."""
        html = _make_html("<td>Image caption — describe the image</td>")
        warnings = check_placeholders(html)
        assert len(warnings) == 1
        assert warnings[0].category == "placeholder"
        assert "image caption" in str(warnings[0].context["pattern"]).lower()

    def test_lorem_ipsum_placeholder(self) -> None:
        """'Lorem ipsum' text → warning."""
        html = _make_html("<td>Lorem ipsum dolor sit amet</td>")
        warnings = check_placeholders(html)
        assert len(warnings) == 1
        assert "lorem ipsum" in str(warnings[0].context["pattern"]).lower()

    def test_real_content_no_warning(self) -> None:
        """Real content like 'Welcome to our newsletter' → no warning."""
        html = _make_html("<td>Welcome to our newsletter</td>")
        warnings = check_placeholders(html)
        assert len(warnings) == 0

    def test_multiple_placeholders(self) -> None:
        """Multiple distinct placeholders → one warning per unique match."""
        html = _make_html(
            "<td>Lorem ipsum dolor sit amet</td>"
            "<td>Add your text here</td>"
            "<td>Image caption for hero</td>"
        )
        warnings = check_placeholders(html)
        assert len(warnings) == 3
        patterns = {w.context["pattern"] for w in warnings}
        assert "lorem ipsum" in patterns
        assert "add your text" in patterns
        assert "image caption" in patterns


# ---------------------------------------------------------------------------
# Integration tests (2)
# ---------------------------------------------------------------------------


class TestRunQualityContracts:
    """Orchestrator integration tests."""

    def test_clean_html_no_warnings(self) -> None:
        """Well-formed HTML with good contrast, no placeholders → empty list."""
        html = _make_html(
            "<!-- section:n1:content -->"
            '<td style="background-color:#FFFFFF;">'
            '<span style="color:#333333;">Real content</span>'
            "</td>"
        )
        result = run_quality_contracts(html, input_section_count=1)
        assert result == []

    def test_all_violation_types(self) -> None:
        """HTML with all 3 violation types → warnings from all categories."""
        html = _make_html(
            "<!-- section:n1:content -->"
            '<td style="background-color:#FE5117;">'
            '<span style="color:#FFFFFF;">Lorem ipsum dolor sit amet</span>'
            "</td>"
        )
        # input_section_count=2 but only 1 marker → completeness warning
        result = run_quality_contracts(
            html,
            input_section_count=2,
            input_button_count=0,
        )
        categories = {w.category for w in result}
        assert "contrast" in categories
        assert "completeness" in categories
        assert "placeholder" in categories

    def test_empty_html_returns_empty(self) -> None:
        """Empty string → no checks run, empty list."""
        assert run_quality_contracts("") == []
