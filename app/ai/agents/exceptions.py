"""Agent-layer exceptions."""

from app.core.exceptions import AppError


class ToolCapExceededError(AppError):
    """Per-session tool-call cap exceeded (maps to 503, reason=tool_cap_exceeded)."""

    reason = "tool_cap_exceeded"

    def __init__(self, agent: str, cap: int) -> None:
        self.agent = agent
        self.cap = cap
        super().__init__(f"Agent '{agent}' exceeded tool-call cap ({cap})")
