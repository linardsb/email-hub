"""Tests for 51.2 — safe compaction / pinned safety instructions.

Covers the two load-bearing surfaces:
  * assembly pin in ``BaseAgentService._build_multimodal_messages``
  * trim survival in ``TokenBudgetManager._truncate_system_message``

The mandatory live-path trip tests (T1/T2) drive the token budget *below* the
preamble's own token cost, so raw head-truncation would lose the preamble and
only the pin recovers it — guarding against the 51.3 false-green (a test that
"forces truncation" with budget to spare passes even if the pin is a no-op).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import structlog.testing

from app.ai.agents.base import BaseAgentService
from app.ai.agents.dark_mode.schemas import DarkModeRequest
from app.ai.agents.dark_mode.service import DarkModeService
from app.ai.agents.safety_preamble import (
    PREAMBLE_VERSION,
    SAFETY_PREAMBLE,
    check_version_drift,
)
from app.ai.agents.tests.conftest import configure_mock_security
from app.ai.multimodal import ContentBlock, ImageBlock
from app.ai.protocols import CompletionResponse
from app.ai.token_budget import _MESSAGE_OVERHEAD_TOKENS, TokenBudgetManager
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError

# Minimal valid PNG for multimodal assembly.
_VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_SAMPLE_HTML = "<table><tr><td>Hello</td></tr></table>"
_SAMPLE_LLM_RESPONSE = f"```html\n{_SAMPLE_HTML}\n```"


def _find_log(logs: Sequence[Mapping[str, Any]], event: str) -> Mapping[str, Any] | None:
    return next((entry for entry in logs if entry.get("event") == event), None)


class TestPreambleModule:
    """Loader parses the file + version marker."""

    def test_preamble_loaded_non_empty(self) -> None:
        assert SAFETY_PREAMBLE
        assert "USER_INPUT" in SAFETY_PREAMBLE

    def test_version_parsed_from_marker(self) -> None:
        assert PREAMBLE_VERSION == "51.2.0"

    def test_flag_defaults_on(self) -> None:
        # Prod parity: the pin is active by default.
        assert get_settings().security.safe_compaction_enabled is True


class TestLivePathTrip:
    """Real ``_build_multimodal_messages`` → ``trim_to_budget`` (brief mandate)."""

    def test_t1_system_dropped_keeps_preamble(self) -> None:
        """available_for_system <= 0 → preamble survives instead of a dropped system msg."""
        service = BaseAgentService()
        messages = service._build_multimodal_messages(
            system_prompt="You are a helpful email assistant.",
            user_text="word " * 5000,  # dwarfs any budget
            context_blocks=None,
        )
        # Tiny budget so the whole system message would otherwise be dropped.
        mgr = TokenBudgetManager(model="unknown-model", reserve_tokens=0, max_context_tokens=20)
        result = mgr.trim_to_budget(messages)

        assert result[0].role == "system"
        assert isinstance(result[0].content, str)
        assert SAFETY_PREAMBLE in result[0].content

    def test_t2_sub_preamble_budget_pin_is_load_bearing(self) -> None:
        """0 < available < preamble_tokens → pin keeps preamble; raw truncation would cut it."""
        service = BaseAgentService()
        messages = service._build_multimodal_messages(
            system_prompt="You are a helpful email assistant with detailed rules.",
            user_text="context data " * 50,
            context_blocks=None,
        )
        system_content = messages[0].content
        assert isinstance(system_content, str)

        probe = TokenBudgetManager(
            model="unknown-model", reserve_tokens=0, max_context_tokens=1_000_000
        )
        preamble_tokens = probe._count_text_tokens(SAFETY_PREAMBLE)
        non_system = probe._count_message_tokens(messages[1])
        target_available = preamble_tokens // 2
        assert 0 < target_available < preamble_tokens

        max_ctx = target_available + non_system + _MESSAGE_OVERHEAD_TOKENS
        mgr = TokenBudgetManager(
            model="unknown-model", reserve_tokens=0, max_context_tokens=max_ctx
        )
        result = mgr.trim_to_budget(messages)
        assert isinstance(result[0].content, str)
        assert SAFETY_PREAMBLE in result[0].content

        # Companion: raw head-truncation at the same budget loses the preamble.
        raw = probe._truncate_text_to_tokens(system_content, target_available)
        assert SAFETY_PREAMBLE not in raw

    def test_t5_property_sweep_preamble_always_survives(self) -> None:
        """Bounded randomized sweep: trimmed output always retains the pinned preamble."""
        assert get_settings().security.safe_compaction_enabled is True
        service = BaseAgentService()
        for i in range(240):
            system_prompt = "instruction " * (1 + (i * 7) % 60)
            messages = service._build_multimodal_messages(
                system_prompt=system_prompt,
                user_text="payload " * (1 + (i * 13) % 200),
                context_blocks=None,
            )
            max_ctx = 20 + (i * 11) % 400  # deterministic, varies by index
            mgr = TokenBudgetManager(
                model="unknown-model", reserve_tokens=0, max_context_tokens=max_ctx
            )
            result = mgr.trim_to_budget(messages)
            assert any(
                isinstance(m.content, str) and SAFETY_PREAMBLE in m.content for m in result
            ), f"preamble lost at i={i}"


class TestAssemblyPin:
    """Flag-on assembly prepends the preamble; flag-off is byte-identical."""

    def test_t3_process_style_assembly(self) -> None:
        service = BaseAgentService()
        system_prompt = "You are a scaffolder."
        messages = service._build_multimodal_messages(
            system_prompt=system_prompt, user_text="Build an email", context_blocks=None
        )
        assert isinstance(messages[0].content, str)
        assert messages[0].content.startswith(SAFETY_PREAMBLE)
        assert messages[0].content.endswith(system_prompt)
        assert isinstance(messages[1].content, str)

    def test_t4_stream_style_assembly_with_blocks(self) -> None:
        service = BaseAgentService()
        blocks: list[ContentBlock] = [ImageBlock(data=_VALID_PNG, media_type="image/png")]
        messages = service._build_multimodal_messages(
            system_prompt="Describe images.",
            user_text="What is this?",
            context_blocks=blocks,
        )
        assert isinstance(messages[0].content, str)
        assert messages[0].content.startswith(SAFETY_PREAMBLE)
        # System stays str + preamble; user becomes a block list.
        assert isinstance(messages[1].content, list)

    def test_t10_flag_off_is_byte_identical(self) -> None:
        service = BaseAgentService()
        system_prompt = "You are helpful."
        with patch("app.ai.agents.base.get_settings") as mock_settings:
            mock_settings.return_value.security.safe_compaction_enabled = False
            messages = service._build_multimodal_messages(
                system_prompt=system_prompt, user_text="Hi", context_blocks=None
            )
        assert messages[0].content == system_prompt


class TestVersionDrift:
    def test_t6_drift_warns_when_mismatched(self) -> None:
        with structlog.testing.capture_logs() as logs:
            check_version_drift("99.9.9")
        assert _find_log(logs, "security.safety_preamble_version_drift") is not None

    def test_t7_no_warning_when_config_empty(self) -> None:
        with structlog.testing.capture_logs() as logs:
            check_version_drift("")
        assert _find_log(logs, "security.safety_preamble_version_drift") is None

    def test_no_warning_when_versions_match(self) -> None:
        with structlog.testing.capture_logs() as logs:
            check_version_drift(PREAMBLE_VERSION)
        assert _find_log(logs, "security.safety_preamble_version_drift") is None


class TestFailClosed:
    """Missing preamble file → 503 when the flag is on, silent when off."""

    def _mock_provider(self) -> AsyncMock:
        provider = AsyncMock()
        provider.complete.return_value = CompletionResponse(
            content=_SAMPLE_LLM_RESPONSE,
            model="standard-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        return provider

    @pytest.mark.asyncio()
    async def test_t8_fail_closed_503_flag_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.ai.agents.safety_preamble._LOAD_ERROR", OSError("missing preamble")
        )
        service = DarkModeService()
        request = DarkModeRequest(
            html="<table><tr><td>Hello from the safe-compaction fail-closed test</td></tr></table>"
        )
        provider = self._mock_provider()
        with (
            patch("app.ai.agents.base.get_registry") as mock_registry,
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.resolve_model", return_value="standard-model"),
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings)  # flag on by default
            mock_registry.return_value.get_llm.return_value = provider

            with pytest.raises(ServiceUnavailableError):
                await service.process(request)

        provider.complete.assert_not_called()

    @pytest.mark.asyncio()
    async def test_t9_flag_off_no_503_despite_missing_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.ai.agents.safety_preamble._LOAD_ERROR", OSError("missing preamble")
        )
        service = DarkModeService()
        request = DarkModeRequest(
            html="<table><tr><td>Hello from the safe-compaction fail-closed test</td></tr></table>"
        )
        provider = self._mock_provider()
        with (
            patch("app.ai.agents.base.get_registry") as mock_registry,
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.resolve_model", return_value="standard-model"),
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings, safe_compaction_enabled=False)
            mock_registry.return_value.get_llm.return_value = provider

            response = await service.process(request)

        assert response.model == "test:standard-model"
        provider.complete.assert_called_once()


class TestGenericCallerSafety:
    def test_t11_preamble_free_messages_untouched(self) -> None:
        """Flag on, but a caller whose system content never carried the preamble
        gets today's behaviour — no preamble injected on truncation."""
        assert get_settings().security.safe_compaction_enabled is True
        mgr = TokenBudgetManager(model="unknown-model", reserve_tokens=0, max_context_tokens=40)
        from app.ai.protocols import Message

        msgs = [
            Message(role="system", content="Important system prompt. " * 200),
            Message(role="user", content="q"),
        ]
        result = mgr.trim_to_budget(msgs)
        assert isinstance(result[0].content, str)
        assert SAFETY_PREAMBLE not in result[0].content
        assert "[...truncated]" in result[0].content
