"""Innovation agent request/response schemas."""

from pydantic import BaseModel, Field

from app.ai.agents.types import BaseAgentRequest


class InnovationRequest(BaseAgentRequest):
    """Request to the Innovation agent."""

    technique: str = Field(..., min_length=5, max_length=2000)
    category: str | None = (
        None  # interactive, visual_effects, amp, progressive_enhancement, accessibility
    )
    target_clients: list[str] | None = None  # Optional client filter
    stream: bool = False


class InnovationResponse(BaseModel):
    """Response from the Innovation agent."""

    prototype: str  # Working HTML/CSS prototype
    feasibility: str  # Feasibility assessment text
    client_coverage: float  # 0.0-1.0 estimated coverage
    risk_level: str  # low, medium, high
    recommendation: str  # ship, test_further, avoid
    fallback_html: str  # Static fallback for unsupported clients
    confidence: float  # 0.0-1.0
    skills_loaded: list[str]
    model: str
