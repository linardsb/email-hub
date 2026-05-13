"""Request/response schemas for the Dark Mode agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.schemas.dark_mode_decisions import DarkModeDecisions
from app.ai.agents.types import BaseAgentRequest
from app.qa_engine.schemas import QACheckResult


class DarkModeRequest(BaseAgentRequest):
    """Request body for the dark mode process endpoint.

    Attributes:
        html: Existing email HTML to enhance with dark mode support.
        color_overrides: Optional mapping of light-mode hex colours to dark-mode hex colours.
        preserve_colors: Optional list of hex colours that should not be remapped.
        stream: Whether to return SSE streaming response.
        run_qa: Whether to run the 10-point QA gate on the enhanced HTML.
    """

    html: str = Field(min_length=50, max_length=200_000, description="Existing email HTML")
    color_overrides: dict[str, str] | None = Field(
        default=None,
        description="Light→dark colour mappings (e.g., {'#ffffff': '#1a1a2e'})",
    )
    preserve_colors: list[str] | None = Field(
        default=None,
        description="Hex colours that should not be remapped",
    )
    output_mode: Literal["html", "structured"] = "html"
    build_plan: dict[str, object] | None = Field(
        default=None, description="EmailBuildPlan from scaffolder (structured mode)"
    )
    stream: bool = False
    run_qa: bool = False


class DarkModeResponse(BaseModel):
    """Response from the dark mode process endpoint.

    Attributes:
        html: The enhanced email HTML with dark mode support.
        qa_results: Individual QA check results (only when run_qa=True).
        qa_passed: Overall QA pass/fail (only when run_qa=True).
        model: The model identifier that processed the HTML.
    """

    html: str
    qa_results: list[QACheckResult] | None = None
    qa_passed: bool | None = None
    model: str
    confidence: float | None = None
    skills_loaded: list[str] = Field(default_factory=list)
    meta_tags_injected: list[str] = Field(default_factory=list)
    plan: dict[str, object] | None = None
    decisions: DarkModeDecisions | None = None
