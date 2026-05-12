"""Unit tests for the personalisation_syntax QA check."""

from app.qa_engine.check_config import QACheckConfig
from app.qa_engine.checks._factory import get_check


class TestPersonalisationSyntax:
    check = get_check("personalisation_syntax")

    async def test_clean_braze_template(self) -> None:
        html = '<html><body><p>Hi {{ ${first_name} | default: "Friend" }}</p></body></html>'
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_clean_ampscript_template(self) -> None:
        html = '<html><body>%%[SET @name = "World"]%% %%[IF Empty(@name) THEN SET @name = "Friend" ENDIF]%% Hello %%=v(@name)=%%</body></html>'
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_mixed_liquid_ampscript(self) -> None:
        html = "<html><body>{{ name }} %%[SET @x = 1]%%</body></html>"
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score <= 0.70

    async def test_tags_without_fallbacks(self) -> None:
        tags = "".join(f"{{{{ field_{i} }}}}" for i in range(5))
        html = f"<html><body>{tags}</body></html>"
        result = await self.check.run(html)
        # Should report missing fallbacks (but unknown platform, so deduction for that)
        assert result.score < 1.0

    async def test_unbalanced_delimiters(self) -> None:
        html = "<html><body>{{ name } {% if cond %}yes{% endif %}</body></html>"
        result = await self.check.run(html)
        assert result.score < 1.0

    async def test_no_personalisation_passes(self) -> None:
        html = "<html><body><p>Hello World</p></body></html>"
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0
        assert result.details is not None
        assert "No personalisation" in result.details

    async def test_empty_html_passes(self) -> None:
        result = await self.check.run("")
        assert result.passed is True
        assert result.score == 1.0

    async def test_tracking_pixel_no_personalisation(self) -> None:
        html = '<html><body><img src="https://track.example.com/pixel.gif" width="1" height="1"></body></html>'
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_mailchimp_merge_tags(self) -> None:
        html = "<html><body>Hi *|FNAME|*, welcome to *|LIST:COMPANY|*</body></html>"
        result = await self.check.run(html)
        assert result.check_name == "personalisation_syntax"
        # Merge tags without IF wrapper = missing fallbacks
        assert result.score < 1.0

    async def test_hubspot_hubl(self) -> None:
        html = '<html><body>{{ contact.firstname | default("Friend") }}</body></html>'
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_iterable_handlebars(self) -> None:
        html = "<html><body>{{#if firstName}}Hi {{firstName}}{{/if}}</body></html>"
        result = await self.check.run(html)
        assert result.check_name == "personalisation_syntax"

    async def test_klaviyo_django(self) -> None:
        html = "<html><body>{{ first_name|default:'Friend' }}</body></html>"
        result = await self.check.run(html)
        assert result.check_name == "personalisation_syntax"

    async def test_excessive_nesting(self) -> None:
        html = "<html><body>{% if a %}{% if b %}{% if c %}{% if d %}deep{% endif %}{% endif %}{% endif %}{% endif %}</body></html>"
        result = await self.check.run(html)
        assert (
            result.details is not None and "nesting" in result.details.lower()
        ) or result.score < 1.0

    async def test_adobe_jssp_with_fallback(self) -> None:
        html = '<html><body><%= recipient.firstName || "Friend" %></body></html>'
        result = await self.check.run(html)
        assert result.passed is True
        assert result.score == 1.0

    async def test_combined_issues(self) -> None:
        # Unbalanced + missing fallback + deep nesting
        html = (
            "<html><body>"
            "{{ name } "  # unbalanced
            "{{ email }} "  # no fallback
            "{% if a %}{% if b %}{% if c %}{% if d %}deep{% endif %}{% endif %}{% endif %}{% endif %}"
            "</body></html>"
        )
        result = await self.check.run(html)
        assert result.score < 1.0
        assert result.passed is False

    async def test_disabled_config(self) -> None:
        config = QACheckConfig(enabled=False)
        html = "<html><body>{{ broken }}} %%[bad]%%</body></html>"
        result = await self.check.run(html, config)
        assert result.passed is True
        assert result.score == 1.0
