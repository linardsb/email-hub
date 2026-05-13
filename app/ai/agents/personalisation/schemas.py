"""Request/response schemas for the Personalisation agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.schemas.personalisation_decisions import PersonalisationDecisions
from app.ai.agents.types import BaseAgentRequest
from app.qa_engine.schemas import QACheckResult

ESPPlatform = Literal[
    "braze",
    "sfmc",
    "adobe_campaign",
    "klaviyo",
    "mailchimp",
    "hubspot",
    "iterable",
]


class PersonalisationRequest(BaseAgentRequest):
    """Request body for the Personalisation process endpoint.

    Attributes:
        html: Existing email HTML to personalise.
        platform: Target ESP platform for syntax generation.
        requirements: Natural language description of personalisation needs.
        stream: Whether to return SSE streaming response.
        run_qa: Whether to run the 10-point QA gate on the output HTML.
    """

    html: str = Field(min_length=50, max_length=200_000, description="Email HTML to personalise")
    platform: ESPPlatform = Field(description="Target ESP platform")
    requirements: str = Field(
        min_length=5,
        max_length=5_000,
        description="What personalisation to add (e.g., 'Add first name greeting with fallback, show VIP section for premium users')",
    )
    build_plan: dict[str, object] | None = Field(
        default=None, description="EmailBuildPlan from scaffolder (structured mode)"
    )
    output_mode: Literal["html", "structured"] = "html"
    stream: bool = False
    run_qa: bool = False


class PersonalisationResponse(BaseModel):
    """Response from the Personalisation process endpoint.

    Attributes:
        html: Email HTML with ESP-specific personalisation tags injected.
        platform: The ESP platform used.
        tags_injected: List of personalisation tags added.
        qa_results: Individual QA check results (only when run_qa=True).
        qa_passed: Overall QA pass/fail (only when run_qa=True).
        model: The model identifier that processed the HTML.
    """

    html: str
    platform: ESPPlatform
    tags_injected: list[str] = Field(default_factory=list)
    syntax_warnings: list[str] = Field(default_factory=list)
    qa_results: list[QACheckResult] | None = None
    qa_passed: bool | None = None
    model: str
    confidence: float | None = None
    skills_loaded: list[str] = Field(default_factory=list)
    decisions: PersonalisationDecisions | None = None
    plan: dict[str, object] | None = None
