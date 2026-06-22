"""Blueprint service — resolves and executes named blueprints."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.blueprints.definitions.campaign import build_campaign_blueprint
from app.ai.blueprints.engine import BlueprintDefinition, BlueprintEngine, BlueprintRun
from app.ai.blueprints.exceptions import BlueprintError

if TYPE_CHECKING:
    from app.ai.blueprints.audience_context import AudienceProfile
from app.ai.blueprints.protocols import AgentHandoff, ComponentResolver, GraphContextProvider
from app.ai.blueprints.schemas import (
    BlueprintProgress,
    BlueprintResumeRequest,
    BlueprintRunRequest,
    BlueprintRunResponse,
    HandoffSummary,
    InlineJudgeCriterionResponse,
    InlineJudgeVerdictResponse,
    RoutingDecisionResponse,
)
from app.core.logging import get_logger
from app.personas.schemas import PersonaResponse

logger = get_logger(__name__)

BLUEPRINT_REGISTRY: dict[str, Callable[[], BlueprintDefinition]] = {
    "campaign": build_campaign_blueprint,
}


class BlueprintService:
    """Resolves blueprint by name and runs the engine."""

    async def _build_engine(
        self,
        blueprint_name: str,
        options: dict[str, object] | None,
        persona_ids: list[int] | None,
        db: AsyncSession | None,
    ) -> tuple[
        BlueprintEngine,
        BlueprintDefinition,
        int | None,
        AudienceProfile | None,
    ]:
        """Wire up all engine dependencies. Shared by run() and resume()."""
        from app.ai.blueprints.audience_context import (
            build_audience_profile,
        )
        from app.ai.blueprints.checkpoint import CheckpointStore, PostgresCheckpointStore
        from app.ai.blueprints.handoff_memory import persist_handoff_to_memory
        from app.ai.blueprints.resolvers import DbComponentResolver
        from app.core.config import get_settings
        from app.projects.design_system import DesignSystem, load_design_system

        factory = BLUEPRINT_REGISTRY.get(blueprint_name)
        if factory is None:
            available = ", ".join(sorted(BLUEPRINT_REGISTRY.keys()))
            raise BlueprintError(f"Unknown blueprint '{blueprint_name}'. Available: {available}")

        definition = factory()

        component_resolver: ComponentResolver | None = None
        if db is not None:
            component_resolver = DbComponentResolver(db)

        raw_project_id = options.get("project_id") if options else None
        project_id: int | None = int(str(raw_project_id)) if raw_project_id is not None else None

        # Resolve target audience personas
        audience_profile: AudienceProfile | None = None
        if persona_ids and db is not None:
            from app.personas.service import PersonaService

            persona_svc = PersonaService(db)
            personas: list[PersonaResponse] = []
            for pid in persona_ids:
                try:
                    personas.append(await persona_svc.get_persona(pid))
                except Exception:
                    logger.warning("blueprint.persona_not_found", persona_id=pid, exc_info=True)
            if personas:
                audience_profile = build_audience_profile(personas)

        # Wire graph knowledge provider (optional — only if Cognee enabled)
        settings = get_settings()
        graph_provider: GraphContextProvider | None = None
        try:
            if settings.cognee.enabled:
                from app.knowledge.graph.cognee_provider import CogneeGraphProvider

                graph_provider = CogneeGraphProvider(settings)
        except Exception:
            logger.debug("blueprint.graph_provider_init_skipped", exc_info=True)

        # Load design system and client_id from project (single DB read)
        design_system: DesignSystem | None = None
        client_id: str | None = None
        if project_id is not None and db is not None:
            try:
                from app.projects.repository import ProjectRepository

                repo = ProjectRepository(db)
                project = await repo.get(project_id)
                if project is not None:
                    design_system = load_design_system(project.design_system)
                    # Resolve client_id for per-client skill overlays (Phase 32.11)
                    org = getattr(project, "client_org", None)
                    if org is not None:
                        client_id = org.slug
            except Exception:
                logger.warning(
                    "blueprint.design_system_load_failed",
                    project_id=project_id,
                    exc_info=True,
                )

        # Wire checkpoint store (opt-in via config)
        checkpoint_store: CheckpointStore | None = None
        if settings.blueprint.checkpoints_enabled and db is not None:
            checkpoint_store = PostgresCheckpointStore(db)

        # Wire recovery outcome repo (opt-in via config)
        recovery_outcome_repo = None
        if settings.blueprint.recovery_ledger_enabled and db is not None:
            from app.ai.recovery_outcomes import RecoveryOutcomeRepository

            recovery_outcome_repo = RecoveryOutcomeRepository(db)

        engine = BlueprintEngine(
            definition,
            component_resolver=component_resolver,
            on_handoff=persist_handoff_to_memory,
            project_id=project_id,
            graph_provider=graph_provider,
            audience_profile=audience_profile,
            judge_on_retry=settings.blueprint.judge_on_retry,
            design_system=design_system,
            checkpoint_store=checkpoint_store,
            recovery_outcome_repo=recovery_outcome_repo,
            client_id=client_id,
        )

        return engine, definition, project_id, audience_profile

    def _build_response(
        self,
        bp_run: BlueprintRun,
        definition: BlueprintDefinition,
        audience_profile: AudienceProfile | None,
        checkpoint_count: int = 0,
        template_version_id: int | None = None,
    ) -> BlueprintRunResponse:
        """Build API response from a completed BlueprintRun."""
        from app.ai.blueprints.audience_context import format_audience_context

        def _to_summary(h: AgentHandoff) -> HandoffSummary:
            return HandoffSummary(
                agent_name=h.agent_name,
                decisions=list(h.decisions),
                warnings=list(h.warnings),
                component_refs=list(h.component_refs),
                confidence=h.confidence,
            )

        final_handoff: HandoffSummary | None = None
        if bp_run._last_handoff is not None:
            final_handoff = _to_summary(bp_run._last_handoff)

        handoff_history = [_to_summary(h) for h in bp_run._handoff_history]

        # Map inline judge verdict to response
        judge_verdict_response: InlineJudgeVerdictResponse | None = None
        if bp_run.judge_verdict is not None:
            judge_verdict_response = InlineJudgeVerdictResponse(
                trace_id=bp_run.judge_verdict.trace_id,
                agent=bp_run.judge_verdict.agent,
                overall_pass=bp_run.judge_verdict.overall_pass,
                criteria_results=[
                    InlineJudgeCriterionResponse(
                        criterion=cr.criterion,
                        passed=cr.passed,
                        reasoning=cr.reasoning,
                    )
                    for cr in bp_run.judge_verdict.criteria_results
                ],
            )

        return BlueprintRunResponse(
            run_id=bp_run.run_id,
            blueprint_name=definition.name,
            status=bp_run.status,
            html=bp_run.html,
            brief_text=bp_run.brief_text,
            progress=[
                BlueprintProgress(
                    node_name=p.node_name,
                    node_type=p.node_type,
                    status=p.status,
                    iteration=p.iteration,
                    summary=p.summary,
                    duration_ms=p.duration_ms,
                )
                for p in bp_run.progress
            ],
            qa_passed=bp_run.qa_passed,
            model_usage=bp_run.model_usage,
            final_handoff=final_handoff,
            handoff_history=handoff_history,
            audience_summary=(
                format_audience_context(audience_profile) if audience_profile else None
            ),
            skipped_nodes=bp_run.skipped_nodes,
            routing_decisions=[
                RoutingDecisionResponse(
                    node_name=d.node_name,
                    action=d.action.value,
                    reason=d.reason,
                )
                for d in bp_run.routing_decisions
            ],
            judge_verdict=judge_verdict_response,
            checkpoint_count=checkpoint_count,
            resumed_from=bp_run.resumed_from,
            template_version_id=template_version_id,
        )

    async def _count_checkpoints(self, run_id: str, db: AsyncSession | None) -> int:
        """Count checkpoints for a run (non-blocking, failure-safe)."""
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.blueprint.checkpoints_enabled or db is None:
            return 0
        try:
            from sqlalchemy import func as sa_func
            from sqlalchemy import select as sa_select

            from app.ai.blueprints.checkpoint_models import BlueprintCheckpoint

            count_stmt = (
                sa_select(sa_func.count())
                .select_from(BlueprintCheckpoint)
                .where(BlueprintCheckpoint.run_id == run_id)
            )
            count_result = await db.execute(count_stmt)
            return count_result.scalar_one()
        except Exception:
            logger.debug("blueprint.checkpoint_count_failed", extra={"run_id": run_id})
            return 0

    async def _post_run_hooks(
        self,
        bp_run: BlueprintRun,
        definition: BlueprintDefinition,
        project_id: int | None,
        audience_profile: AudienceProfile | None,
        brief: str,
    ) -> None:
        """Post-run outcome logging and production sampling (fire-and-forget)."""
        try:
            from app.ai.blueprints.outcome_logger import (
                extract_and_store_failure_patterns,
                persist_outcome_to_memory,
                queue_outcome_for_graph,
            )

            await queue_outcome_for_graph(bp_run, definition.name, project_id)
            await persist_outcome_to_memory(bp_run, definition.name, project_id)
            await extract_and_store_failure_patterns(
                bp_run, definition.name, project_id, audience_profile
            )
        except Exception:
            logger.warning(
                "blueprint.outcome_logging_failed",
                run_id=bp_run.run_id,
                exc_info=True,
            )

        if bp_run.status == "completed" and bp_run.qa_passed:
            try:
                from app.ai.agents.evals.production_sampler import enqueue_for_judging

                agents_executed = [p.node_name for p in bp_run.progress if p.node_type == "agentic"]
                await enqueue_for_judging(
                    run_id=bp_run.run_id,
                    blueprint_name=definition.name,
                    brief=brief,
                    html=bp_run.html,
                    agents_executed=agents_executed,
                )
            except Exception:
                logger.warning(
                    "blueprint.production_sampling_failed",
                    run_id=bp_run.run_id,
                    exc_info=True,
                )

    async def _auto_save_template_version(
        self,
        bp_run: BlueprintRun,
        request: BlueprintRunRequest,
        project_id: int | None,
        user_id: int | None,
        db: AsyncSession | None,
    ) -> int | None:
        """Auto-save blueprint output as a TemplateVersion (fire-and-forget).

        Returns the new version ID, or None if saving was skipped or failed.
        """
        if bp_run.status != "completed" or not bp_run.html or db is None or user_id is None:
            return None

        try:
            from app.templates.repository import TemplateRepository
            from app.templates.schemas import TemplateCreate, VersionCreate

            repo = TemplateRepository(db)

            if request.template_id is not None:
                # Add version to existing template
                version = await repo.create_version(
                    request.template_id,
                    VersionCreate(
                        html_source=bp_run.html,
                        changelog=f"Blueprint run {bp_run.run_id}",
                    ),
                    user_id,
                )
                logger.info(
                    "blueprint.auto_save.version_created",
                    template_id=request.template_id,
                    version_id=version.id,
                    run_id=bp_run.run_id,
                )
                return version.id

            if project_id is not None:
                # Create new template with initial version
                brief_name = bp_run.brief_text[:80] if bp_run.brief_text else "Blueprint output"
                template = await repo.create(
                    project_id,
                    TemplateCreate(
                        name=brief_name,
                        html_source=bp_run.html,
                        subject_line=None,
                        preheader_text=None,
                    ),
                    user_id,
                )
                # create() auto-creates v1 — get its ID
                versions = await repo.get_versions(template.id)
                version_id = versions[0].id if versions else None
                logger.info(
                    "blueprint.auto_save.template_created",
                    template_id=template.id,
                    version_id=version_id,
                    run_id=bp_run.run_id,
                )
                return version_id

        except Exception:
            logger.warning(
                "blueprint.auto_save_failed",
                run_id=bp_run.run_id,
                exc_info=True,
            )
        return None

    async def run(
        self,
        request: BlueprintRunRequest,
        user_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> BlueprintRunResponse:
        """Execute a named blueprint and return structured response."""
        engine, definition, project_id, audience_profile = await self._build_engine(
            request.blueprint_name, request.options, request.persona_ids, db
        )

        logger.info("blueprint.service.run_started", blueprint=request.blueprint_name)

        bp_run = await engine.run(
            brief=request.brief,
            initial_html=request.initial_html,
            user_id=user_id,
        )

        await self._post_run_hooks(bp_run, definition, project_id, audience_profile, request.brief)
        checkpoint_count = await self._count_checkpoints(bp_run.run_id, db)
        template_version_id = await self._auto_save_template_version(
            bp_run, request, project_id, user_id, db
        )

        return self._build_response(
            bp_run, definition, audience_profile, checkpoint_count, template_version_id
        )

    async def resume(
        self,
        request: BlueprintResumeRequest,
        user_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> BlueprintRunResponse:
        """Resume a blueprint run from its latest checkpoint."""
        if db is None:
            raise BlueprintError("Database session required for resume")

        engine, definition, project_id, audience_profile = await self._build_engine(
            request.blueprint_name, None, None, db
        )

        logger.info("blueprint.service.resume_started", run_id=request.run_id)

        bp_run = await engine.resume(
            run_id=request.run_id,
            brief=request.brief,
            user_id=user_id,
        )

        await self._post_run_hooks(bp_run, definition, project_id, audience_profile, request.brief)
        checkpoint_count = await self._count_checkpoints(bp_run.run_id, db)

        return self._build_response(bp_run, definition, audience_profile, checkpoint_count)


_service: BlueprintService | None = None


def get_blueprint_service() -> BlueprintService:
    """Module-level singleton for the blueprint service."""
    global _service
    if _service is None:
        _service = BlueprintService()
    return _service
