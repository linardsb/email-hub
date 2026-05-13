"""Request/response schemas for the Scaffolder agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.types import BaseAgentRequest
from app.qa_engine.schemas import QACheckResult


class ScaffolderRequest(BaseAgentRequest):
    """Request body for the scaffolder generate endpoint.

    Attributes:
        brief: The campaign brief describing the email to generate.
        stream: Whether to return SSE streaming response.
        run_qa: Whether to run the 10-point QA gate on the generated HTML.
        output_mode: "html" for raw LLM HTML, "structured" for template-first pipeline.
    """

    brief: str = Field(min_length=10, max_length=4000, description="Campaign brief")
    stream: bool = False
    run_qa: bool = False
    output_mode: Literal["html", "structured", "tree"] = "html"
    brand_config: dict[str, object] | None = Field(
        default=None,
        description="Brand guidelines for design token selection (colours, fonts, etc.)",
    )
    design_context: dict[str, object] | None = Field(
        default=None,
        description="Figma design context: image URLs, layout analysis, design tokens",
    )
    initial_html: str = Field(
        default="",
        max_length=50000,
        description="Pre-generated HTML skeleton for the Scaffolder to enhance (e.g. from Penpot converter)",
    )


class ScaffolderResponse(BaseModel):
    """Response from the scaffolder generate endpoint.

    Attributes:
        html: The generated Maizzle email HTML.
        qa_results: Individual QA check results (only when run_qa=True).
        qa_passed: Overall QA pass/fail (only when run_qa=True).
        model: The model identifier that generated the HTML.
        plan: Structured build plan (only when output_mode="structured").
    """

    html: str = ""
    qa_results: list[QACheckResult] | None = None
    qa_passed: bool | None = None
    model: str
    confidence: float | None = None
    skills_loaded: list[str] = Field(default_factory=list)
    mso_warnings: list[str] = Field(default_factory=list)
    plan: dict[str, object] | None = None
    tree: dict[str, object] | None = None


class VariantRequest(BaseModel):
    """Request body for multi-variant campaign assembly."""

    brief: str = Field(min_length=10, max_length=4000, description="Campaign brief")
    variant_count: int = Field(default=3, ge=2, le=5, description="Number of variants (2-5)")
    run_qa: bool = True
    brand_config: dict[str, object] | None = Field(
        default=None,
        description="Brand guidelines for design token selection",
    )


class VariantResultResponse(BaseModel):
    """Single variant in the response."""

    variant_id: str
    strategy_name: str
    hypothesis: str
    predicted_differentiator: str
    subject_line: str
    preheader: str
    html: str
    qa_results: list[QACheckResult] = Field(default_factory=list[QACheckResult])
    qa_passed: bool = False


class SlotDifferenceResponse(BaseModel):
    """A slot that differs across variants."""

    slot_id: str
    variants: dict[str, str]


class ComparisonMatrixResponse(BaseModel):
    """Side-by-side comparison."""

    subject_lines: dict[str, str]
    preheaders: dict[str, str]
    slot_differences: list[SlotDifferenceResponse] = Field(
        default_factory=list[SlotDifferenceResponse]
    )
    strategy_summary: dict[str, str]


class VariantSetResponse(BaseModel):
    """Response from multi-variant generation."""

    brief: str
    base_template: str
    variant_count: int
    variants: list[VariantResultResponse]
    comparison: ComparisonMatrixResponse
    all_qa_passed: bool
