"""Security settings: prompt-injection guard, agent kill-switch, hard caps."""

from typing import Literal

from pydantic import BaseModel, Field


class SecurityConfig(BaseModel):
    """Security settings including prompt injection detection."""

    prompt_guard_enabled: bool = True  # SECURITY__PROMPT_GUARD_ENABLED
    prompt_guard_mode: Literal["warn", "strip", "block"] = "warn"  # SECURITY__PROMPT_GUARD_MODE

    # G3 — kill switch: agents in this list short-circuit with 503 on every call.
    # Env: SECURITY__DISABLED_AGENTS=scaffolder,dark_mode
    disabled_agents: list[str] = Field(default_factory=list)

    # G4 — per-run hard caps (defense-in-depth on top of provider timeouts)
    agent_max_run_seconds: int = 90  # SECURITY__AGENT_MAX_RUN_SECONDS
    agent_max_total_tokens: int = 32000  # SECURITY__AGENT_MAX_TOTAL_TOKENS
    # 51.3 — completes the K_max trio with a per-process() tool-call count cap.
    # Deliberately permissive: no current agent makes tool calls, so 25 is a
    # no-op until agentic tool loops land.
    agent_max_tool_calls: int = 25  # SECURITY__AGENT_MAX_TOOL_CALLS

    # 51.1 — Default TTL (seconds) for credential revocations triggered by the
    # kill switch. ``None`` = permanent until ``POST /api/v1/credentials/revoke``
    # with ``restore=true`` (or ``restore_for_agent`` from a Python entry point).
    # Env: SECURITY__REVOCATION_DEFAULT_TTL_S
    revocation_default_ttl_s: int | None = None

    # 51.2 — Safe compaction. Pins the safety preamble to the head of every
    # agent system prompt and keeps it alive through token-budget truncation.
    # Kill switch: off ⇒ strict no-op (today's behaviour).
    safe_compaction_enabled: bool = True  # SECURITY__SAFE_COMPACTION_ENABLED
    # Expected preamble version; drift from the loaded file logs a warning when
    # non-empty. Empty ⇒ drift check disabled.
    safety_preamble_version: str = ""  # SECURITY__SAFETY_PREAMBLE_VERSION
