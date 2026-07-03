"""Shared fixtures + helpers for AI agent tests.

When a test patches ``app.ai.agents.base.get_settings`` to a MagicMock,
the new ``SecurityConfig`` fields (Phase: secure-ai-agents) leak as
MagicMock objects into ``asyncio.wait_for`` and similar typed call sites.
``configure_mock_security`` populates those fields with sane defaults so
tests don't need to know about the security envelope unless they
deliberately exercise it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


def configure_mock_security(mock_settings: MagicMock, **overrides: Any) -> None:
    """Set security-config defaults on a patched ``get_settings`` mock.

    Call inside any test that patches ``app.ai.agents.base.get_settings``
    and exercises ``BaseAgentService.process``.

    Default ``agent_max_total_tokens`` is intentionally large (1M) so existing
    tests that don't care about the cap won't trip it. Override per-test for
    the cap test.
    """
    sec = mock_settings.return_value.security
    sec.disabled_agents = overrides.get("disabled_agents", [])
    sec.agent_max_run_seconds = overrides.get("agent_max_run_seconds", 90)
    sec.agent_max_total_tokens = overrides.get("agent_max_total_tokens", 1_000_000)
    sec.prompt_guard_enabled = overrides.get("prompt_guard_enabled", False)
    sec.prompt_guard_mode = overrides.get("prompt_guard_mode", "warn")
    # 51.2 — safe compaction defaults on (prod parity) so existing process()
    # tests exercise the pinned-preamble path deterministically.
    sec.safe_compaction_enabled = overrides.get("safe_compaction_enabled", True)
    sec.safety_preamble_version = overrides.get("safety_preamble_version", "")
    # CRAG check is gated by isinstance(self, CRAGMixin) but set defensively.
    mock_settings.return_value.knowledge.crag_enabled = overrides.get("crag_enabled", False)
