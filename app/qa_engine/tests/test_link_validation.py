"""Unit tests for the link_validation QA check."""

from app.qa_engine.checks._factory import get_check


class TestLinkValidation:
    check = get_check("link_validation")

    async def test_https_links_pass(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score == 1.0

    async def test_http_links_flagged(self) -> None:
        html = '<a href="http://example.com">Click</a>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "Non-HTTPS" in (result.details or "")

    async def test_mailto_allowed(self) -> None:
        html = '<a href="mailto:test@example.com">Email</a>'
        result = await self.check.run(html)
        assert result.passed is True

    async def test_tel_allowed(self) -> None:
        html = '<a href="tel:+1234567890">Call</a>'
        result = await self.check.run(html)
        assert result.passed is True

    async def test_liquid_templates_allowed(self) -> None:
        html = '<a href="{{ url }}">Link</a>'
        result = await self.check.run(html)
        assert result.passed is True

    async def test_jinja_templates_allowed(self) -> None:
        html = '<a href="{% if url %}{{ url }}{% endif %}">Link</a>'
        result = await self.check.run(html)
        assert result.passed is True

    async def test_localhost_http_allowed(self) -> None:
        html = '<a href="http://localhost:3000/test">Dev link</a>'
        result = await self.check.run(html)
        assert result.passed is True


class TestLinkValidationCheck:
    check = get_check("link_validation")

    async def test_valid_https_links(self) -> None:
        html = '<html><body><a href="https://example.com">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.score == 1.0
        assert result.passed is True

    async def test_http_link_deducted(self) -> None:
        html = '<html><body><a href="http://example.com">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.score < 1.0
        assert "Non-HTTPS" in (result.details or "")

    async def test_empty_href_deducted(self) -> None:
        html = '<html><body><a href="">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.score < 1.0

    async def test_javascript_protocol_severe(self) -> None:
        html = '<html><body><a href="javascript:alert(1)">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.score < 0.8  # Heavy deduction

    async def test_valid_liquid_template_not_flagged(self) -> None:
        html = '<html><body><a href="{{ url }}">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.passed is True

    async def test_unbalanced_template_flagged(self) -> None:
        html = '<html><body><a href="{{ url }">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "template" in (result.details or "").lower()

    async def test_malformed_url_deducted(self) -> None:
        html = '<html><body><a href="https://">Link</a></body></html>'
        result = await self.check.run(html)
        assert result.score < 1.0

    async def test_empty_html(self) -> None:
        result = await self.check.run("")
        assert result.passed is False
        assert result.score == 0.0

    async def test_valid_html_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True
        assert result.score >= 0.9

    async def test_multiple_issues_capped(self) -> None:
        links = "".join(f'<a href="http://bad{i}.com">Link{i}</a>' for i in range(10))
        html = f"<html><body>{links}</body></html>"
        result = await self.check.run(html)
        assert result.score >= 0.0  # Capped at 0.0 not negative
