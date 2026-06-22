# pyright: reportUnknownVariableType=false, reportGeneralTypeIssues=false
# ruff: noqa: ANN401, ARG002
"""Scaffolder agent service — orchestrates LLM → extract → sanitize → MSO validate → QA."""

import contextvars
import dataclasses
from collections.abc import AsyncIterator
from typing import Any

from app.ai.agents.base import BaseAgentService
from app.ai.agents.scaffolder.assembler import AssemblyError, TemplateAssembler
from app.ai.agents.scaffolder.pipeline import PipelineError, ScaffolderPipeline
from app.ai.agents.scaffolder.prompt import (
    build_system_prompt as _build_system_prompt,
)
from app.ai.agents.scaffolder.prompt import (
    detect_relevant_skills as _detect_relevant_skills,
)
from app.ai.agents.scaffolder.schemas import (
    ComparisonMatrixResponse,
    ScaffolderRequest,
    ScaffolderResponse,
    SlotDifferenceResponse,
    VariantRequest,
    VariantResultResponse,
    VariantSetResponse,
)
from app.ai.agents.schemas.build_plan import EmailBuildPlan
from app.ai.agents.validation_loop import CRAG_SYSTEM_PROMPT, CRAGMixin
from app.ai.exceptions import AIExecutionError
from app.ai.registry import get_registry
from app.ai.routing import resolve_model
from app.ai.shared import extract_html, sanitize_html_xss
from app.core.config import get_settings
from app.core.logging import get_logger
from app.qa_engine.mso_parser import validate_mso_conditionals
from app.qa_engine.schemas import QACheckResult

logger = get_logger(__name__)

# Per-request storage for MSO warnings (avoids race on singleton instance)
_mso_warnings_var: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "scaffolder_mso_warnings", default=None
)


class ScaffolderService(CRAGMixin, BaseAgentService):
    """Orchestrates the scaffolder agent pipeline.

    Pipeline: build messages → LLM call → validate output →
    extract HTML → XSS sanitize → MSO validate → optional QA checks.
    """

    agent_name = "scaffolder"
    sanitization_profile = "scaffolder"
    model_tier = "complex"
    stream_prefix = "scaffold"
    _output_mode_supported = True
    _user_input_fields = ("brief", "initial_html")

    def build_system_prompt(
        self,
        relevant_skills: list[str],
        output_mode: str = "html",
        *,
        client_id: str | None = None,
    ) -> str:
        return _build_system_prompt(relevant_skills, output_mode=output_mode, client_id=client_id)

    def detect_relevant_skills(self, request: Any) -> list[str]:
        req: ScaffolderRequest = request
        return _detect_relevant_skills(req.brief)

    def _build_user_message(self, request: Any) -> str:
        req: ScaffolderRequest = request
        message = req.brief
        if req.design_context:
            from app.ai.agents.scaffolder.prompt import build_design_context_section

            message += "\n\n" + build_design_context_section(req.design_context)
        if req.initial_html:
            message += (
                "\n\n## Initial HTML Skeleton\n\n"
                "Below is a pre-generated HTML skeleton from the design file. "
                "Use this as a structural starting point and enhance it with "
                "proper content, styling, and email client compatibility:\n\n"
                f"```html\n{req.initial_html}\n```"
            )
        return message

    def _post_process(self, raw_content: str) -> str:
        """Extract HTML, sanitize XSS, then run MSO validation."""
        html = extract_html(raw_content)
        html = sanitize_html_xss(html, profile=self.sanitization_profile)

        # MSO-first: validate generated HTML for Outlook issues
        mso_result = validate_mso_conditionals(html)
        warnings = [
            f"[{issue.severity}] {issue.category}: {issue.message}" for issue in mso_result.issues
        ]
        _mso_warnings_var.set(warnings)

        if warnings:
            logger.warning(
                "agents.scaffolder.mso_validation_issues",
                issue_count=len(warnings),
                categories=list({i.category for i in mso_result.issues}),
            )

        return html

    def _build_response(
        self,
        *,
        request: Any,
        html: str,
        qa_results: list[QACheckResult] | None,
        qa_passed: bool | None,
        model_id: str,
        confidence: float | None,
        skills_loaded: list[str],
        raw_content: str,
    ) -> ScaffolderResponse:
        warnings = _mso_warnings_var.get(None) or []
        return ScaffolderResponse(
            html=html,
            qa_results=qa_results,
            qa_passed=qa_passed,
            model=model_id,
            confidence=confidence,
            skills_loaded=skills_loaded,
            mso_warnings=warnings,
        )

    async def _process_structured(self, request: Any) -> ScaffolderResponse:
        """Structured mode: 3-pass pipeline -> deterministic assembly -> QA."""
        req: ScaffolderRequest = request

        # Route tree mode to dedicated handler
        if req.output_mode == "tree":
            return await self._process_tree(req)

        settings = get_settings()
        provider_name = settings.ai.provider
        model = resolve_model(self._get_model_tier(request))
        model_id = f"{provider_name}:{model}"

        registry = get_registry()
        provider = registry.get_llm(provider_name)

        logger.info(
            "agents.scaffolder.structured_started",
            provider=provider_name,
            model=model,
        )

        # Phase 1: LLM decisions (3-pass structured JSON)
        pipeline = ScaffolderPipeline(provider, model)
        try:
            plan = await pipeline.execute(req.brief, brand_config=req.brand_config)
        except PipelineError as e:
            logger.error(
                "agents.scaffolder.pipeline_failed",
                error=str(e),
                provider=provider_name,
            )
            raise AIExecutionError("scaffolder structured pipeline failed") from e

        # Phase 2: Deterministic assembly (no LLM)
        assembler = TemplateAssembler()
        try:
            html = assembler.assemble(plan)
        except AssemblyError as e:
            logger.error(
                "agents.scaffolder.assembly_failed",
                error=str(e),
                template=plan.template.template_name,
            )
            raise AIExecutionError("scaffolder template assembly failed") from e

        # Phase 3: XSS sanitize (template HTML is trusted, but slot fills are not)
        html = sanitize_html_xss(html, profile=self.sanitization_profile)

        # Phase 3.5: CRAG validation loop
        if settings.knowledge.crag_enabled:
            html, _crag_corrections = await self._crag_validate_and_correct(
                html,
                system_prompt=CRAG_SYSTEM_PROMPT,
                model=model,
            )

        # Phase 4: QA gate
        qa_results: list[QACheckResult] | None = None
        qa_passed: bool | None = None
        if self._should_run_qa(request):
            qa_results, qa_passed = await self._run_qa(html)

        return ScaffolderResponse(
            html=html,
            plan=_serialize_plan(plan),
            qa_results=qa_results,
            qa_passed=qa_passed,
            model=model_id,
            confidence=plan.confidence,
            skills_loaded=[],
            mso_warnings=[],
        )

    async def _process_tree(self, req: ScaffolderRequest) -> ScaffolderResponse:
        """Tree mode: 3-pass pipeline → EmailTree (no HTML compilation)."""
        settings = get_settings()
        provider_name = settings.ai.provider
        model = resolve_model(self._get_model_tier(req))
        model_id = f"{provider_name}:{model}"

        registry = get_registry()
        provider = registry.get_llm(provider_name)

        logger.info(
            "agents.scaffolder.tree_started",
            provider=provider_name,
            model=model,
        )

        pipeline = ScaffolderPipeline(provider, model)
        try:
            tree = await pipeline.execute_tree(req.brief, brand_config=req.brand_config)
        except PipelineError as e:
            logger.error(
                "agents.scaffolder.tree_pipeline_failed",
                error=str(e),
                provider=provider_name,
            )
            raise AIExecutionError("scaffolder tree pipeline failed") from e

        return ScaffolderResponse(
            html="",
            tree=tree.model_dump(),
            model=model_id,
            confidence=0.9,
            skills_loaded=[],
            mso_warnings=[],
        )

    async def generate_variants(self, request: VariantRequest) -> VariantSetResponse:
        """Generate multi-variant campaign from a single brief."""
        settings = get_settings()
        if request.variant_count > settings.variants.max_variants:
            raise AIExecutionError(
                f"Requested {request.variant_count} variants exceeds maximum of {settings.variants.max_variants}"
            )

        provider_name = settings.ai.provider
        model = resolve_model(self._get_model_tier(request))
        registry = get_registry()
        provider = registry.get_llm(provider_name)

        logger.info(
            "agents.scaffolder.variants_started",
            provider=provider_name,
            model=model,
            variant_count=request.variant_count,
        )

        pipeline = ScaffolderPipeline(provider, model)
        try:
            variant_set = await pipeline.execute_variants(
                brief=request.brief,
                count=request.variant_count,
                brand_config=request.brand_config,
            )
        except PipelineError as e:
            logger.error("agents.scaffolder.variants_failed", error=str(e))
            raise AIExecutionError("variant generation pipeline failed") from e

        return VariantSetResponse(
            brief=variant_set.brief,
            base_template=variant_set.base_template,
            variant_count=len(variant_set.variants),
            variants=[
                VariantResultResponse(
                    variant_id=vr.variant_id,
                    strategy_name=vr.strategy_name,
                    hypothesis=vr.hypothesis,
                    predicted_differentiator=vr.predicted_differentiator,
                    subject_line=vr.subject_line,
                    preheader=vr.preheader,
                    html=vr.html,
                    qa_results=list(vr.qa_results),
                    qa_passed=vr.qa_passed,
                )
                for vr in variant_set.variants
            ],
            comparison=ComparisonMatrixResponse(
                subject_lines=variant_set.comparison.subject_lines,
                preheaders=variant_set.comparison.preheaders,
                slot_differences=[
                    SlotDifferenceResponse(slot_id=sd.slot_id, variants=sd.variants)
                    for sd in variant_set.comparison.slot_differences
                ],
                strategy_summary=variant_set.comparison.strategy_summary,
            ),
            all_qa_passed=all(vr.qa_passed for vr in variant_set.variants),
        )

    # Scaffolder uses generate/stream_generate names for backward compat with routes
    async def generate(self, request: ScaffolderRequest) -> ScaffolderResponse:
        """Generate email HTML from a campaign brief."""
        return await self.process(request)  # type: ignore[no-any-return]

    async def stream_generate(self, request: ScaffolderRequest) -> AsyncIterator[str]:
        """Stream email HTML generation as SSE-formatted chunks."""
        async for chunk in self.stream_process(request):
            yield chunk


# ── Module-level singleton ──

_scaffolder_service: ScaffolderService | None = None


def get_scaffolder_service() -> ScaffolderService:
    """Get or create the scaffolder service singleton."""
    global _scaffolder_service
    if _scaffolder_service is None:
        _scaffolder_service = ScaffolderService()
    return _scaffolder_service


def _serialize_plan(plan: EmailBuildPlan) -> dict[str, object]:
    """Serialize EmailBuildPlan to dict for API response."""
    return dataclasses.asdict(plan)
