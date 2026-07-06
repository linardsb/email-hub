"""Lightweight structured audit log for agent decisions.

The existing structured-logging stack is the source of truth. We add a single
JSON line per agent run with stable keys so ops/admin tooling can query the
"causality chain" of any LLM-backed decision without coupling to a DB schema.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def hash_input(text: str) -> str:
    """Stable sha256 of the assembled user message — log this instead of raw text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_agent_decision(
    *,
    agent: str,
    user_id: int | None,
    blueprint_run_id: str | None,
    model: str,
    prompt_version: str | None,
    input_hash: str,
    output_summary: str,
    duration_ms: int,
    tokens_in: int,
    tokens_out: int,
    decision: str,
    tool_calls_made: int = 0,
    planning_steps: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit one structured line per agent run: ai.agent_decision.

    decision is one of: "ok" | "refused" | "error" | "timeout" | "disabled" |
    "cap_exceeded".

    ``tool_calls_made`` / ``planning_steps`` are the 51.3 additions — additive
    only, with defaults, so pre-51.3 call sites and existing log consumers
    (Phase 44.9 Loki dashboards) keep their exact schema and see stable keys.
    """
    payload: dict[str, Any] = {
        "agent": agent,
        "user_id": user_id,
        "blueprint_run_id": blueprint_run_id,
        "model": model,
        "prompt_version": prompt_version,
        "input_hash": input_hash,
        "output_summary": output_summary,
        "duration_ms": duration_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "decision": decision,
        "tool_calls_made": tool_calls_made,
        "planning_steps": planning_steps if planning_steps is not None else [],
    }
    if extra:
        payload.update(extra)
    logger.info("ai.agent_decision", **payload)
