"""Tests for the per-session tool-call cap + planning telemetry (Phase 51.3).

Completes the K_max cap trio (run-seconds + token caps already ship as G4).
Covers: cap raises at N+1 with a ``cap_exceeded`` audit line, planning steps
captured for structured mode, counter reset between ``process()`` calls, the
additive ``ai.agent_decision`` schema, ``tool_calls_made=0`` for tool-less
agents, and the 503/``tool_cap_exceeded`` HTTP mapping.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.agents.audit import log_agent_decision
from app.ai.agents.dark_mode.schemas import DarkModeRequest
from app.ai.agents.dark_mode.service import DarkModeService
from app.ai.agents.exceptions import ToolCapExceededError
from app.ai.agents.scaffolder.schemas import ScaffolderRequest, ScaffolderResponse
from app.ai.agents.scaffolder.service import ScaffolderService
from app.ai.agents.tests.conftest import configure_mock_security
from app.ai.protocols import CompletionResponse
from app.core.exceptions import app_exception_handler

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


# ── Cap enforcement ──────────────────────────────────────────────────


@pytest.mark.asyncio()
async def test_cap_raises_at_n_plus_1_emits_cap_exceeded_audit(
    dark_mode_request: DarkModeRequest,
) -> None:
    """The (cap+1)-th tool call raises and the audit line records cap_exceeded."""
    service = DarkModeService()
    cap = 3

    async def _spam(_request: Any, _ctx: Any, _telemetry: Any, counter: Any) -> None:
        for _ in range(cap + 1):
            counter.record_tool_call()

    with (
        patch.object(DarkModeService, "_process_impl", side_effect=_spam),
        patch("app.ai.agents.base.get_settings") as mock_settings,
        patch("app.ai.agents.base.log_agent_decision") as mock_audit,
    ):
        mock_settings.return_value.ai.provider = "test"
        configure_mock_security(mock_settings, agent_max_tool_calls=cap)

        with pytest.raises(ToolCapExceededError):
            await service.process(dark_mode_request)

    assert mock_audit.call_count == 1
    assert mock_audit.call_args.kwargs["decision"] == "cap_exceeded"


@pytest.mark.asyncio()
async def test_planning_steps_captured_for_structured_mode() -> None:
    """Structured dispatch records one planning step on the audit line."""
    service = ScaffolderService()
    request = ScaffolderRequest(
        brief="Build a summer sale email for a retail client.",
        output_mode="structured",
    )
    dummy = ScaffolderResponse(model="test:standard-model")

    with (
        patch("app.ai.agents.base.get_settings") as mock_settings,
        patch("app.ai.agents.base.log_agent_decision") as mock_audit,
        patch.object(ScaffolderService, "_process_structured", AsyncMock(return_value=dummy)),
    ):
        mock_settings.return_value.ai.provider = "test"
        configure_mock_security(mock_settings)

        result = await service.process(request)

    assert result is dummy
    assert mock_audit.call_count == 1
    assert mock_audit.call_args.kwargs["planning_steps"] == ["scaffolder:structured"]
    assert mock_audit.call_args.kwargs["tool_calls_made"] == 0


@pytest.mark.asyncio()
async def test_counter_resets_between_process_invocations(
    dark_mode_request: DarkModeRequest,
) -> None:
    """A fresh counter per ``process()`` — the second call does not accumulate."""
    service = DarkModeService()
    k = 3

    async def _spam_k(_request: Any, _ctx: Any, _telemetry: Any, counter: Any) -> None:
        for _ in range(k):
            counter.record_tool_call()

    with (
        patch.object(DarkModeService, "_process_impl", side_effect=_spam_k),
        patch("app.ai.agents.base.get_settings") as mock_settings,
        patch("app.ai.agents.base.log_agent_decision") as mock_audit,
    ):
        mock_settings.return_value.ai.provider = "test"
        configure_mock_security(mock_settings, agent_max_tool_calls=25)

        await service.process(dark_mode_request)
        await service.process(dark_mode_request)

    assert mock_audit.call_count == 2
    assert mock_audit.call_args_list[0].kwargs["tool_calls_made"] == k
    assert mock_audit.call_args_list[1].kwargs["tool_calls_made"] == k


# ── Additive telemetry schema ────────────────────────────────────────


def test_agent_decision_schema_is_additive() -> None:
    """Old-signature callers still succeed; new keys default additively."""
    with patch("app.ai.agents.audit.logger") as mock_logger:
        log_agent_decision(
            agent="dark_mode",
            user_id=1,
            blueprint_run_id=None,
            model="test:standard-model",
            prompt_version=None,
            input_hash="abc123",
            output_summary="summary",
            duration_ms=5,
            tokens_in=10,
            tokens_out=20,
            decision="ok",
        )

    mock_logger.info.assert_called_once()
    event = mock_logger.info.call_args.args[0]
    payload = mock_logger.info.call_args.kwargs
    assert event == "ai.agent_decision"
    # New keys default additively.
    assert payload["tool_calls_made"] == 0
    assert payload["planning_steps"] == []
    # Original keys preserved and unchanged.
    assert payload["agent"] == "dark_mode"
    assert payload["decision"] == "ok"
    assert payload["model"] == "test:standard-model"
    assert payload["input_hash"] == "abc123"
    assert payload["tokens_in"] == 10
    assert payload["tokens_out"] == 20


@pytest.mark.asyncio()
async def test_tool_calls_made_zero_for_tool_less_agent(
    mock_provider: AsyncMock, dark_mode_request: DarkModeRequest
) -> None:
    """A normal tool-less run reports zero tool calls and no planning steps."""
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

    assert mock_audit.call_count == 1
    assert mock_audit.call_args.kwargs["tool_calls_made"] == 0
    assert mock_audit.call_args.kwargs["planning_steps"] == []


# ── HTTP mapping ─────────────────────────────────────────────────────


@pytest.mark.asyncio()
async def test_tool_cap_exceeded_maps_to_503() -> None:
    """The exception maps to 503 with reason=tool_cap_exceeded in the body."""
    request: Any = MagicMock()
    request.url.path = "/api/v1/test"
    request.method = "POST"

    try:
        raise ToolCapExceededError("dark_mode", 25)
    except ToolCapExceededError as exc:
        response = await app_exception_handler(request, exc)

    assert response.status_code == 503
    body = json.loads(bytes(response.body))
    assert body["reason"] == "tool_cap_exceeded"
