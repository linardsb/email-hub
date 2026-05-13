"""Request/response schemas for the Accessibility Auditor agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.schemas.accessibility_decisions import AccessibilityDecisions
from app.ai.agents.types import BaseAgentRequest
from app.qa_engine.schemas import QACheckResult


class AccessibilityRequest(BaseAgentRequest):
    """Request body for the Accessibility Auditor process endpoint.

    Attributes:
        html: Email HTML to audit for accessibility issues.
        focus_areas: Optional list of specific audit areas (e.g., 'alt_text', 'contrast').
            When None, the agent audits all accessibility categories.
        stream: Whether to return SSE streaming response.
        run_qa: Whether to run the 10-point QA gate on the fixed HTML.
    """

    html: str = Field(min_length=50, max_length=200_000, description="Email HTML to audit")
    focus_areas: list[str] | None = Field(
        default=None,
        description="Specific audit areas to focus on (all areas if None)",
    )
    build_plan: dict[str, object] | None = Field(
        default=None, description="EmailBuildPlan from scaffolder (structured mode)"
    )
    output_mode: Literal["html", "structured"] = "html"
    stream: bool = False
    run_qa: bool = False


class AccessibilityResponse(BaseModel):
    """Response from the Accessibility Auditor process endpoint.

    Attributes:
        html: The fixed email HTML with accessibility improvements.
        skills_loaded: List of L3 skill files that were loaded.
        qa_results: Individual QA check results (only when run_qa=True).
        qa_passed: Overall QA pass/fail (only when run_qa=True).
        model: The model identifier that processed the HTML.
    """

    html: str
    skills_loaded: list[str] = Field(default_factory=list)
    alt_text_warnings: list[str] = Field(default_factory=list)
    qa_results: list[QACheckResult] | None = None
    qa_passed: bool | None = None
    model: str
    confidence: float | None = None
    decisions: AccessibilityDecisions | None = None
    plan: dict[str, object] | None = None
