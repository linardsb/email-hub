"""51.3 — per-session tool-call cap + planning telemetry.

Completes the K_max trio (run-seconds + token caps already live in the
``process()`` security envelope) with a deterministic per-``process()``
tool-call cap, and extends the ``ai.agent_decision`` audit line additively
with ``tool_calls_made`` + ``planning_steps``.

The counter is per-invocation state carried in a contextvar — never a module
global — so ``record_tool_call()`` raises ``ToolCapExceededError`` on the
cap+1-th call of one run and a fresh ``process()`` starts back at zero.
No current agent makes tool calls, so the cap is a strict no-op today
(``tool_calls_made=0``); tests drive the counter through a patched
``_process_impl`` to exercise the envelope end-to-end.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.agents.base import record_planning_step, record_tool_call
from app.ai.agents.dark_mode.schemas import DarkModeRequest
from app.ai.agents.dark_mode.service import DarkModeService
from app.ai.agents.scaffolder.schemas import ScaffolderRequest
from app.ai.agents.scaffolder.service import ScaffolderService
from app.ai.agents.tests.conftest import configure_mock_security
from app.ai.protocols import CompletionResponse
from app.core.config.security import SecurityConfig
from app.core.exceptions import (
    ServiceUnavailableError,
    ToolCapExceededError,
    app_exception_handler,
)

_SAMPLE_HTML = "<table><tr><td>Hello</td></tr></table>"
_SAMPLE_LLM_RESPONSE = f"```html\n{_SAMPLE_HTML}\n```"


@pytest.fixture()
def mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        content=_SAMPLE_LLM_RESPONSE,
        model="standard-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )
    return provider


@pytest.fixture()
def dark_mode_request() -> DarkModeRequest:
    return DarkModeRequest(html="<html><body><table><tr><td>Hello</td></tr></table></body></html>")


def _tool_burst(n: int) -> Any:
    """A fake ``_process_impl`` that makes ``n`` tool calls inside the envelope."""

    async def _impl(*_a: Any, **_k: Any) -> str:
        for _ in range(n):
            record_tool_call()
        return "done"

    return _impl


# ── Cap enforcement ──────────────────────────────────────────────────


class TestToolCallCap:
    @pytest.mark.asyncio()
    async def test_cap_raises_at_n_plus_1_and_audits_cap_exceeded(
        self, dark_mode_request: DarkModeRequest
    ) -> None:
        """The cap+1-th call raises; the audit line records the capped run."""
        service = DarkModeService()
        with (
            patch.object(DarkModeService, "_process_impl", side_effect=_tool_burst(4)),
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.log_agent_decision") as mock_audit,
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings, agent_max_tool_calls=3)

            with pytest.raises(ToolCapExceededError, match="tool-call cap"):
                await service.process(dark_mode_request)

        assert mock_audit.call_count == 1
        kwargs = mock_audit.call_args.kwargs
        assert kwargs["decision"] == "cap_exceeded"
        assert kwargs["tool_calls_made"] == 3  # calls MADE — the 4th was blocked

    @pytest.mark.asyncio()
    async def test_calls_at_cap_do_not_raise(self, dark_mode_request: DarkModeRequest) -> None:
        """Exactly N calls is within budget — permissive default semantics."""
        service = DarkModeService()
        with (
            patch.object(DarkModeService, "_process_impl", side_effect=_tool_burst(3)),
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.log_agent_decision") as mock_audit,
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings, agent_max_tool_calls=3)

            await service.process(dark_mode_request)

        kwargs = mock_audit.call_args.kwargs
        assert kwargs["decision"] == "ok"
        assert kwargs["tool_calls_made"] == 3

    @pytest.mark.asyncio()
    async def test_counter_resets_between_process_invocations(
        self, dark_mode_request: DarkModeRequest
    ) -> None:
        """Per-session state: two 2-call runs under a 3-cap both succeed."""
        service = DarkModeService()
        with (
            patch.object(DarkModeService, "_process_impl", side_effect=_tool_burst(2)),
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.log_agent_decision") as mock_audit,
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings, agent_max_tool_calls=3)

            await service.process(dark_mode_request)
            await service.process(dark_mode_request)

        assert mock_audit.call_count == 2
        second = mock_audit.call_args_list[1].kwargs
        assert second["decision"] == "ok"
        assert second["tool_calls_made"] == 2  # not 4 — no carry-over

    def test_flag_defaults_to_25(self) -> None:
        """Deliberately permissive default — must not trip any current agent."""
        assert SecurityConfig().agent_max_tool_calls == 25


# ── Planning telemetry ───────────────────────────────────────────────


class TestPlanningTelemetry:
    @pytest.mark.asyncio()
    async def test_tool_less_agent_reports_zero_calls_and_no_steps(
        self, mock_provider: AsyncMock, dark_mode_request: DarkModeRequest
    ) -> None:
        """A normal run that never touches tools audits 0 / [] (stable keys)."""
        service = DarkModeService()
        with (
            patch("app.ai.agents.base.get_registry") as mock_registry,
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.resolve_model", return_value="standard-model"),
            patch("app.ai.agents.base.log_agent_decision") as mock_audit,
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings)
            mock_registry.return_value.get_llm.return_value = mock_provider

            await service.process(dark_mode_request)

        kwargs = mock_audit.call_args.kwargs
        assert kwargs["decision"] == "ok"
        assert kwargs["tool_calls_made"] == 0
        assert kwargs["planning_steps"] == []

    @pytest.mark.asyncio()
    async def test_scaffolder_structured_mode_records_planning_steps(self) -> None:
        """The structured pipeline's phases land in the audit line, in order."""
        service = ScaffolderService()
        request = ScaffolderRequest(
            brief="Launch email for the new product line", output_mode="structured"
        )

        mock_plan = MagicMock()
        mock_plan.confidence = 0.9

        with (
            patch("app.ai.agents.base.get_settings") as mock_settings,
            patch("app.ai.agents.base.log_agent_decision") as mock_audit,
            patch("app.ai.agents.scaffolder.service.get_settings") as mock_sc_settings,
            patch("app.ai.agents.scaffolder.service.get_registry"),
            patch("app.ai.agents.scaffolder.service.resolve_model", return_value="standard-model"),
            patch("app.ai.agents.scaffolder.service.ScaffolderPipeline") as mock_pipeline_cls,
            patch("app.ai.agents.scaffolder.service.TemplateAssembler") as mock_assembler_cls,
            patch("app.ai.agents.scaffolder.service._serialize_plan", return_value={}),
        ):
            mock_settings.return_value.ai.provider = "test"
            configure_mock_security(mock_settings)
            mock_sc_settings.return_value.ai.provider = "test"
            mock_sc_settings.return_value.knowledge.crag_enabled = False
            mock_pipeline_cls.return_value.execute = AsyncMock(return_value=mock_plan)
            mock_assembler_cls.return_value.assemble.return_value = _SAMPLE_HTML

            response = await service.process(request)

        assert response.html  # sanity: the structured path actually ran
        kwargs = mock_audit.call_args.kwargs
        assert kwargs["planning_steps"] == [
            "structured_pipeline",
            "template_assembly",
            "xss_sanitize",
        ]

    def test_record_helpers_are_noops_outside_an_agent_run(self) -> None:
        """Calling the hooks with no active envelope must not blow up."""
        record_tool_call()
        record_planning_step("orphan_step")


# ── Additive audit schema ────────────────────────────────────────────


class TestAdditiveSchema:
    def test_log_agent_decision_without_new_fields_keeps_legacy_shape(self) -> None:
        """Existing call sites (no new kwargs) still work; consumers keying on
        the Phase 44.9 fields see them unchanged, with stable new defaults."""
        from app.ai.agents.audit import log_agent_decision

        with patch("app.ai.agents.audit.logger") as mock_logger:
            log_agent_decision(
                agent="dark_mode",
                user_id=7,
                blueprint_run_id="run-1",
                model="test:standard-model",
                prompt_version="v1",
                input_hash="abc",
                output_summary="ok",
                duration_ms=12,
                tokens_in=100,
                tokens_out=50,
                decision="ok",
            )

        payload = mock_logger.info.call_args.kwargs
        legacy_keys = {
            "agent",
            "user_id",
            "blueprint_run_id",
            "model",
            "prompt_version",
            "input_hash",
            "output_summary",
            "duration_ms",
            "tokens_in",
            "tokens_out",
            "decision",
        }
        assert legacy_keys <= payload.keys()
        assert payload["decision"] == "ok"
        # Additive fields present with stable defaults — never absent, never renamed.
        assert payload["tool_calls_made"] == 0
        assert payload["planning_steps"] == []


# ── HTTP mapping ─────────────────────────────────────────────────────


class TestHttpMapping:
    def test_tool_cap_error_is_a_503_service_unavailable(self) -> None:
        exc = ToolCapExceededError(agent="dark_mode", limit=25)
        assert isinstance(exc, ServiceUnavailableError)
        assert exc.reason == "tool_cap_exceeded"

    @pytest.mark.asyncio()
    async def test_handler_returns_503_with_safe_body(self) -> None:
        request = MagicMock()
        request.url.path = "/api/v1/agents/dark-mode/transform"
        request.method = "POST"

        response = await app_exception_handler(request, ToolCapExceededError(agent="x", limit=3))

        assert response.status_code == 503
        body = json.loads(bytes(response.body))
        assert body["type"] == "service_unavailable"
        # Sanitized message — specific enough to act on, no internals leaked.
        assert "tool-call" in body["error"].lower()
