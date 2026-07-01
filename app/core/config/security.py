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

    # 51.3 — per-session tool-call cap (completes K_max). Default 25 is
    # deliberately permissive — must not trip any current agent.
    # Env: SECURITY__AGENT_MAX_TOOL_CALLS
    agent_max_tool_calls: int = 25

    # 51.1 — Default TTL (seconds) for credential revocations triggered by the
    # kill switch. ``None`` = permanent until ``POST /api/v1/credentials/revoke``
    # with ``restore=true`` (or ``restore_for_agent`` from a Python entry point).
    # Env: SECURITY__REVOCATION_DEFAULT_TTL_S
    revocation_default_ttl_s: int | None = None
