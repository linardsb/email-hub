"""Unit tests for the spam_score QA check."""

from app.qa_engine.checks._factory import get_check


class TestSpamScore:
    check = get_check("spam_score")

    async def test_clean_content_passes(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.passed is True

    async def test_spam_triggers_flagged(self) -> None:
        html = "<html><body><p>Buy now! Free offer! Click here!</p></body></html>"
        result = await self.check.run(html)
        assert result.passed is False or result.score < 1.0
        assert "buy now" in (result.details or "").lower()

    async def test_few_triggers_still_passes(self) -> None:
        """Low-weight triggers should not immediately fail."""
        html = "<html><body><p>This is free content with a guarantee.</p></body></html>"
        result = await self.check.run(html)
        # 'free' (0.05) + 'guarantee' (0.05) = 0.10 deduction, score = 0.90
        assert result.passed is True
        assert result.score >= 0.5

    async def test_word_boundary_matching(self) -> None:
        """Triggers should match on word boundaries, not substrings."""
        # 'free' should match 'free' but not 'freedom' or 'carefree'
        html_match = "<html><body><p>Get it for free today!</p></body></html>"
        result_match = await self.check.run(html_match)
        assert result_match.score < 1.0

        html_no_match = "<html><body><p>Enjoy the freedom of choice.</p></body></html>"
        result_no_match = await self.check.run(html_no_match)
        # 'freedom' should NOT trigger 'free' — word boundary matching
        assert result_no_match.score == 1.0 or result_no_match.score > result_match.score

    async def test_excessive_punctuation_flagged(self) -> None:
        """3+ consecutive ! or ? should be flagged."""
        html = "<html><body><p>Amazing deal!!!! Don't miss out???</p></body></html>"
        result = await self.check.run(html)
        assert "punctuation" in (result.details or "").lower()

    async def test_all_caps_words_flagged(self) -> None:
        """3+ consecutive all-caps words should be flagged."""
        html = "<html><body><p>THIS IS ABSOLUTELY FREE TODAY ONLY</p></body></html>"
        result = await self.check.run(html)
        assert "caps" in (result.details or "").lower()

    async def test_obfuscation_detected(self) -> None:
        """Leet-speak obfuscation like 'fr33' should be caught."""
        html = "<html><body><p>Get your fr33 prize now!</p></body></html>"
        result = await self.check.run(html)
        assert "obfuscat" in (result.details or "").lower()

    async def test_subject_line_higher_weight(self) -> None:
        """Spam triggers in <title> should have 3x weight multiplier."""
        html_body = (
            "<html><head><title>Newsletter</title></head><body><p>Buy now!</p></body></html>"
        )
        html_subject = (
            "<html><head><title>Buy now!</title></head><body><p>Regular content.</p></body></html>"
        )
        result_body = await self.check.run(html_body)
        result_subject = await self.check.run(html_subject)
        # Subject trigger (3x) should produce a larger deduction than body trigger
        assert result_subject.score < result_body.score

    async def test_heavy_triggers_fail(self) -> None:
        """Multiple high-weight triggers should push score below threshold."""
        html = (
            "<html><body><p>Congratulations! You have been selected as a winner! "
            "This is not spam. Double your money with this million dollars offer! "
            "Act now! Hurry! Last chance!</p></body></html>"
        )
        result = await self.check.run(html)
        assert result.passed is False
        assert result.score < 0.5

    async def test_empty_html(self) -> None:
        """Empty HTML should return error."""
        result = await self.check.run("")
        assert result.passed is False
        assert result.score == 0.0

    async def test_spam_triggers_export_backwards_compatible(self) -> None:
        """SPAM_TRIGGERS should still be importable as a list of strings."""
        from app.qa_engine.spam_triggers import SPAM_TRIGGERS

        assert isinstance(SPAM_TRIGGERS, list)
        assert len(SPAM_TRIGGERS) >= 50
        assert all(isinstance(t, str) for t in SPAM_TRIGGERS)
        assert "buy now" in SPAM_TRIGGERS
