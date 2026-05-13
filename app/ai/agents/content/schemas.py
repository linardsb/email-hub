"""Request/response schemas for the Content agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.schemas.content_decisions import ContentDecisions
from app.ai.agents.types import BaseAgentRequest


class ContentRequest(BaseAgentRequest):
    """Request body for the content generate endpoint.

    Attributes:
        operation: The copywriting operation to perform.
        text: Source text or campaign brief.
        tone: Target tone for tone_adjust, optional hint for others.
        brand_voice: Brand guidelines loaded from project settings.
        num_alternatives: Number of alternatives to generate.
        stream: Whether to return SSE streaming response.
    """

    operation: Literal[
        "subject_line",
        "preheader",
        "cta",
        "body_copy",
        "rewrite",
        "shorten",
        "expand",
        "tone_adjust",
    ]
    text: str = Field(min_length=1, max_length=10_000, description="Source text or brief")
    tone: str | None = Field(default=None, max_length=100, description="Target tone")
    brand_voice: str | None = Field(
        default=None,
        max_length=2000,
        description="Brand voice guidelines from project settings",
    )
    num_alternatives: int = Field(default=1, ge=1, le=10, description="Number of alternatives")
    audience_client_ids: tuple[str, ...] | None = Field(
        default=None,
        description="Target email client IDs from audience profile for client-aware generation",
    )
    build_plan: dict[str, object] | None = None
    output_mode: str = "html"
    stream: bool = False


class SpamWarning(BaseModel):
    """A spam trigger detected in generated content.

    Attributes:
        trigger: The spam trigger word/phrase found.
        context: Surrounding text snippet for context.
    """

    trigger: str
    context: str


class ContentResponse(BaseModel):
    """Response from the content generate endpoint.

    Attributes:
        content: Generated text alternatives (always a list).
        operation: The operation that was performed.
        spam_warnings: Detected spam triggers with context.
        model: The model identifier that generated the content.
    """

    content: list[str]
    operation: str
    spam_warnings: list[SpamWarning] = []
    length_warnings: list[str] = Field(default_factory=list)
    model: str
    confidence: float | None = None
    skills_loaded: list[str] = Field(default_factory=list)
    decisions: ContentDecisions | None = None
