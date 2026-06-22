"""Shared base types for agent request schemas (F070)."""

from __future__ import annotations

from pydantic import BaseModel


class BaseAgentRequest(BaseModel):
    """Common base for every agent request schema.

    Declares the four fields that the Blueprint engine injects into requests
    at runtime so downstream agents can read them with typed access rather
    than ``getattr(request, ...)``. All default to ``None`` because the
    fields are populated only when a request flows through the orchestrator;
    direct callers (REST routes, eval runners) leave them unset.
    """

    user_id: str | None = None
    blueprint_run_id: str | None = None
    prompt_version: str | None = None
    client_id: str | None = None
