"""Request/response schemas for the Code Reviewer agent."""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.agents.schemas.code_review_decisions import CodeReviewDecisions
from app.ai.agents.types import BaseAgentRequest
from app.qa_engine.schemas import QACheckResult

ReviewFocus = Literal[
    "redundant_code",
    "css_support",
    "nesting",
    "file_size",
    "link_validation",
    "anti_patterns",
    "spam_patterns",
    "all",
]

IssueSeverity = Literal["critical", "warning", "info"]

# Specialist agents that handle specific issue domains
ResponsibleAgent = Literal[
    "code_reviewer",
    "outlook_fixer",
    "dark_mode",
    "accessibility",
    "personalisation",
    "scaffolder",
]


class CodeReviewIssue(BaseModel):
    """A single code review finding."""

    rule: str = Field(
        description="Rule identifier (e.g., 'redundant-mso-comment', 'unsupported-css-grid')"
    )
    severity: IssueSeverity
    line_hint: int | None = Field(default=None, description="Approximate line number")
    message: str = Field(description="Human-readable description of the issue")
    suggestion: str | None = Field(default=None, description="Actionable fix suggestion")
    current_value: str | None = Field(default=None, description="Current problematic value")
    fix_value: str | None = Field(default=None, description="Recommended replacement value")
    affected_clients: list[str] | None = Field(
        default=None, description="Email clients affected (e.g., ['Outlook', 'Gmail'])"
    )
    responsible_agent: ResponsibleAgent = Field(
        default="code_reviewer",
        description="Specialist agent best suited to fix this issue",
    )


class CodeReviewRequest(BaseAgentRequest):
    """Request body for the Code Reviewer process endpoint."""

    html: str = Field(min_length=50, max_length=200_000, description="Email HTML to review")
    focus: ReviewFocus = Field(default="all", description="Area to focus the review on")
    build_plan: dict[str, object] | None = None
    output_mode: str = "html"
    stream: bool = False
    run_qa: bool = False
    enrich_with_qa: bool = Field(
        default=False,
        description="Cross-check issues against QA engine results",
    )


class CodeReviewResponse(BaseModel):
    """Response from the Code Reviewer process endpoint."""

    html: str = Field(description="Original HTML (unmodified)")
    issues: list[CodeReviewIssue] = Field(default_factory=lambda: list[CodeReviewIssue]())
    summary: str = Field(description="Brief natural-language review summary")
    skills_loaded: list[str] = Field(default_factory=list)
    qa_results: list[QACheckResult] | None = None
    qa_passed: bool | None = None
    model: str
    confidence: float | None = None
    decisions: CodeReviewDecisions | None = None
    actionability_warnings: list[str] = Field(
        default_factory=list,
        description="Post-process validation warnings about suggestion quality",
    )
