"""Unit tests for the html_validation QA check (20 DOM checks)."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check
from app.qa_engine.tests._helpers import valid_html


class TestHtmlValidation:
    check = get_check("html_validation")

    # --- Group A: Document Skeleton ---

    async def test_valid_html_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0
        assert result.check_name == "html_validation"

    async def test_empty_html_fails(self) -> None:
        result = await self.check.run("")
        assert result.passed is False
        assert result.score == 0.0
        assert "Empty" in (result.details or "")

    async def test_missing_doctype_fails(self) -> None:
        html = valid_html(doctype=False)
        result = await self.check.run(html)
        assert result.passed is False
        assert "DOCTYPE" in (result.details or "")

    async def test_missing_head_fails(self) -> None:
        html = "<!DOCTYPE html><html><body><p>Hello</p></body></html>"
        result = await self.check.run(html)
        assert result.passed is False
        # Should flag missing charset, viewport, title (head is auto-created but empty)

    async def test_missing_charset_fails(self) -> None:
        html = valid_html(charset=False)
        result = await self.check.run(html)
        assert result.passed is False
        assert "charset" in (result.details or "").lower()

    async def test_http_equiv_charset_passes(self) -> None:
        html = valid_html(
            charset=False,
            head_extra='<meta http-equiv="Content-Type" content="text/html; charset=utf-8">',
        )
        result = await self.check.run(html)
        assert "charset" not in (result.details or "").lower()

    async def test_missing_viewport_fails(self) -> None:
        html = valid_html(viewport=False)
        result = await self.check.run(html)
        assert result.passed is False
        assert "viewport" in (result.details or "").lower()

    async def test_missing_title_fails(self) -> None:
        html = valid_html(title="")
        result = await self.check.run(html)
        assert result.passed is False
        assert "title" in (result.details or "").lower()

    # --- Group B: Tag Integrity ---

    async def test_unclosed_div_fails(self) -> None:
        html = valid_html(body="<div><p>Hello</p>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "Unclosed" in (result.details or "")
        assert "<div>" in (result.details or "")

    async def test_unclosed_td_fails(self) -> None:
        html = valid_html(body="<table><tr><td>Hello</tr></table>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "Unclosed" in (result.details or "")

    async def test_block_in_inline_fails(self) -> None:
        html = valid_html(body="<span><div>Bad nesting</div></span>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "nesting" in (result.details or "").lower()
        assert "<div>" in (result.details or "")
        assert "<span>" in (result.details or "")

    async def test_duplicate_id_fails(self) -> None:
        html = valid_html(body='<div id="hero">A</div><div id="hero">B</div>')
        result = await self.check.run(html)
        assert result.passed is False
        assert "Duplicate" in (result.details or "")
        assert "hero" in (result.details or "")

    # --- Group C: Content Integrity ---

    async def test_empty_body_fails(self) -> None:
        html = valid_html(body="")
        result = await self.check.run(html)
        assert result.passed is False
        assert "Empty <body>" in (result.details or "")

    async def test_style_in_body_fails(self) -> None:
        html = valid_html(body="<style>.test { color: red; }</style><p>Hello</p>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "<style> in <body>" in (result.details or "")

    async def test_style_in_head_passes(self) -> None:
        html = valid_html(head_extra="<style>.test { color: red; }</style>")
        result = await self.check.run(html)
        assert "<style> in <body>" not in (result.details or "")

    async def test_external_stylesheet_fails(self) -> None:
        html = valid_html(
            head_extra='<link rel="stylesheet" href="https://example.com/style.css">',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "stylesheet" in (result.details or "").lower()

    # --- Group D: Email-Specific Structure ---

    async def test_td_outside_tr_fails(self) -> None:
        html = valid_html(body="<table><td>Orphan</td></table>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "Table structure" in (result.details or "")

    async def test_valid_table_passes(self) -> None:
        html = valid_html(
            body="<table><thead><tr><th>Header</th></tr></thead>"
            "<tbody><tr><td>Cell</td></tr></tbody></table>",
        )
        result = await self.check.run(html)
        assert "Table structure" not in (result.details or "")

    async def test_orphaned_li_fails(self) -> None:
        html = valid_html(body="<li>Orphan item</li>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "List structure" in (result.details or "")

    async def test_valid_list_passes(self) -> None:
        html = valid_html(body="<ul><li>Item 1</li><li>Item 2</li></ul>")
        result = await self.check.run(html)
        assert "List structure" not in (result.details or "")

    async def test_duplicate_body_fails(self) -> None:
        html = "<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>T</title></head><body><p>A</p></body><body><p>B</p></body></html>"
        result = await self.check.run(html)
        assert result.passed is False
        assert "Duplicate <body>" in (result.details or "")

    async def test_nested_links_fails(self) -> None:
        html = valid_html(
            body='<a href="https://outer.com"><a href="https://inner.com">Nested</a></a>',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "Nested <a>" in (result.details or "")

    # --- Group E: Progressive Enhancement ---

    async def test_video_without_poster_fails(self) -> None:
        html = valid_html(
            body='<video><source src="video.mp4" type="video/mp4">No poster</video>',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "poster" in (result.details or "").lower()

    async def test_video_with_poster_and_fallback_passes(self) -> None:
        html = valid_html(
            body='<video poster="thumb.jpg"><source src="v.mp4" type="video/mp4">'
            '<img src="thumb.jpg" alt="Video thumbnail"></video>',
        )
        result = await self.check.run(html)
        assert "poster" not in (result.details or "").lower()

    async def test_audio_without_fallback_fails(self) -> None:
        html = valid_html(
            body='<audio><source src="audio.mp3" type="audio/mpeg"></audio>',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "<audio>" in (result.details or "")

    async def test_picture_without_img_fails(self) -> None:
        html = valid_html(
            body='<picture><source srcset="dark.png" media="(prefers-color-scheme: dark)"></picture>',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "<picture>" in (result.details or "")
        assert "<img>" in (result.details or "")

    async def test_picture_with_img_passes(self) -> None:
        html = valid_html(
            body='<picture><source srcset="dark.png" media="(prefers-color-scheme: dark)">'
            '<img src="light.png" alt="Logo"></picture>',
        )
        result = await self.check.run(html)
        assert "<picture> missing" not in (result.details or "")

    async def test_details_without_summary_fails(self) -> None:
        html = valid_html(body="<details><p>Content without summary</p></details>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "summary" in (result.details or "").lower()

    async def test_details_with_summary_passes(self) -> None:
        html = valid_html(
            body="<details><summary>Click to expand</summary><p>Content</p></details>",
        )
        result = await self.check.run(html)
        assert "<details> must have <summary>" not in (result.details or "")

    async def test_input_without_label_fails(self) -> None:
        html = valid_html(body='<input type="checkbox" id="toggle1">')
        result = await self.check.run(html)
        assert result.passed is False
        assert "label" in (result.details or "").lower()

    async def test_input_with_label_passes(self) -> None:
        html = valid_html(
            body='<input type="checkbox" id="toggle1"><label for="toggle1">Toggle</label>',
        )
        result = await self.check.run(html)
        assert "label" not in (result.details or "").lower()

    async def test_invalid_ld_json_fails(self) -> None:
        html = valid_html(
            head_extra='<script type="application/ld+json">{invalid json}</script>',
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "invalid JSON" in (result.details or "")

    async def test_valid_ld_json_passes(self) -> None:
        html = valid_html(
            head_extra='<script type="application/ld+json">{"@type": "Order"}</script>',
        )
        result = await self.check.run(html)
        assert "ld+json" not in (result.details or "")

    async def test_template_element_fails(self) -> None:
        html = valid_html(body="<template><p>Hidden content</p></template>")
        result = await self.check.run(html)
        assert result.passed is False
        assert "<template>" in (result.details or "")

    async def test_base_tag_fails(self) -> None:
        html = valid_html(head_extra='<base href="https://example.com/">')
        result = await self.check.run(html)
        assert result.passed is False
        assert "<base" in (result.details or "")

    async def test_unparseable_html_fails(self) -> None:
        """Completely unparseable input returns score 0."""
        null_result = await self.check.run("\x00\x01\x02")
        # lxml tolerates almost anything — null bytes still parse
        assert null_result.score <= 1.0
        result_ws = await self.check.run("   \n\t  ")
        assert result_ws.passed is False
        assert result_ws.score == 0.0
        assert "Empty" in (result_ws.details or "")

    async def test_inline_svg_missing_accessibility(self) -> None:
        """Inline SVG without role='img' and aria-label is flagged."""
        html = valid_html(
            body='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            "<circle cx='12' cy='12' r='10'/></svg>",
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert "svg" in (result.details or "").lower()
        assert "aria-label" in (result.details or "")

    async def test_inline_svg_with_accessibility_passes(self) -> None:
        """Inline SVG with role='img' and aria-label passes."""
        html = valid_html(
            body='<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Icon" '
            'viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>',
        )
        result = await self.check.run(html)
        assert "svg" not in (result.details or "").lower()

    # --- Scoring ---

    async def test_cumulative_deductions(self) -> None:
        """Multiple issues deduct cumulatively."""
        # Has <html> so structure check continues, but missing:
        # doctype(-0.15), charset(-0.15), viewport(-0.10), title(-0.10),
        # empty head(-0.15), empty body(-0.15) = 0.80 deducted → score 0.20
        html = "<html><head></head><body></body></html>"
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score == 0.2

    async def test_score_clamps_at_zero(self) -> None:
        """Score never goes below 0.0."""
        html = ""
        result = await self.check.run(html)
        assert result.score >= 0.0

    async def test_config_override_deduction(self) -> None:
        """Config params override default deductions."""

        html = valid_html(doctype=False)
        # Default deduction for doctype is 0.15
        result_default = await self.check.run(html)
        # Custom: much smaller deduction
        config = QACheckConfig(params={"deduction_doctype": 0.01})
        result_custom = await self.check.run(html, config)
        assert result_custom.score > result_default.score
