# pyright: reportUnknownVariableType=false
"""Request/response schemas for the Visual QA agent."""

from pydantic import BaseModel, Field

from app.ai.agents.types import BaseAgentRequest


class VisualQARequest(BaseAgentRequest):
    """Request body for the visual QA analysis endpoint."""

    screenshots: dict[str, str] = Field(
        description="Client name → base64 PNG screenshot",
        min_length=1,
    )
    html: str = Field(
        min_length=50,
        max_length=200_000,
        description="Original email HTML that was rendered",
    )
    baseline_diffs: list[dict[str, object]] | None = Field(
        default=None,
        description="Optional ODiff results from Phase 17.2 (diff_percentage, changed_pixels per client)",
    )
    output_mode: str = "structured"  # Visual QA is always structured
    stream: bool = False
    run_qa: bool = False


class VisualDefect(BaseModel):
    """A single rendering defect detected by the VLM."""

    region: str = Field(
        description="Description of the affected region (e.g. 'CTA button in footer')"
    )
    description: str = Field(description="Human-readable description of the defect")
    severity: str = Field(description="critical | warning | info")
    affected_clients: list[str] = Field(default_factory=list)
    suggested_fix: str = Field(default="", description="Suggested CSS/HTML fix")
    css_property: str | None = Field(default=None, description="CSS property causing the issue")
    ontology_fallback: str | None = Field(
        default=None, description="Known fallback from ontology, if available"
    )


class VisualComparisonResult(BaseModel):
    """Result of comparing rendered email screenshots against original design."""

    drift_score: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Pixel diff percentage (0-100)"
    )
    diff_regions: list[dict[str, object]] = Field(default_factory=list)
    diff_image_ref: str | None = Field(
        default=None, description="Path or content block ID for diff image"
    )
    semantic_description: str = Field(
        default="", description="VLM interpretation of visual differences"
    )
    regressed: bool = Field(default=False, description="True if worse than previous iteration")


class VisualQAResponse(BaseModel):
    """Response from the visual QA analysis endpoint."""

    defects: list[VisualDefect] = Field(default_factory=list)
    summary: str = ""
    overall_rendering_score: float = Field(default=1.0, ge=0.0, le=1.0)
    auto_fixable: bool = False
    critical_clients: list[str] = Field(default_factory=list)
    model: str = ""
    confidence: float | None = None
    skills_loaded: list[str] = Field(default_factory=list)
