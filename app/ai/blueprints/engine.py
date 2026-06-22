"""Blueprint state machine engine — routes between deterministic and agentic nodes."""

import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from app.ai.blueprints.audience_context import AudienceProfile
    from app.ai.blueprints.checkpoint import CheckpointStore
    from app.ai.recovery_outcomes import RecoveryOutcomeRepository
    from app.core.quota import BlueprintCostTracker
    from app.knowledge.graph.protocols import GraphSearchResult
    from app.projects.design_system import DesignSystem

from app.ai.agents.context_budget import (
    ECONOMY_MODE_THRESHOLD,
    compact_handoff_history,
    get_budget,
    summarize_trajectory,
)
from app.ai.agents.evals.judges.schemas import JudgeVerdict
from app.ai.blueprints.exceptions import BlueprintError, BlueprintEscalatedError, BlueprintNodeError
from app.ai.blueprints.handoff import format_upstream_constraints
from app.ai.blueprints.protocols import (
    AgentHandoff,
    BlueprintNode,
    ComponentResolver,
    GraphContextProvider,
    HandoffStatus,
    NodeContext,
    NodeResult,
    StructuredFailure,
)
from app.ai.blueprints.route_advisor import RoutingDecision, RoutingPlan, build_routing_plan
from app.ai.blueprints.schemas import BlueprintProgress
from app.ai.security.prompt_guard import scan_for_injection
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Callback type for persisting handoffs to memory after each agentic node.
# Signature: (handoff, run_id, project_id) -> None
HandoffMemoryCallback = Callable[[AgentHandoff, str, int | None], Coroutine[Any, Any, None]]

# Callback type for logging completed run outcomes to graph + memory.
# Signature: (run, blueprint_name, project_id) -> None
OutcomeCallback = Callable[["BlueprintRun", str, int | None], Coroutine[Any, Any, None]]

MAX_SELF_CORRECTION_ROUNDS = 2
MAX_TOTAL_STEPS = 25  # safety brake (includes repair node steps between agents and QA gate)
CONFIDENCE_REVIEW_THRESHOLD = 0.5

# Reserved keys a LAYER may return to update top-level NodeContext fields
# instead of metadata. Keys are underscore-prefixed in the layer output dict
# and applied via ``dataclasses.replace`` in ``_build_node_context``.
RESERVED_FIELD_KEYS: tuple[str, ...] = ("_html", "_brief", "_multimodal_context")

EdgeCondition = Literal["success", "qa_fail", "always", "route_to"]


@dataclass
class Edge:
    """Directed edge between two blueprint nodes."""

    from_node: str
    to_node: str
    condition: EdgeCondition
    route_value: str = ""  # used when condition == "route_to"


@dataclass
class BlueprintDefinition:
    """Named graph of nodes and edges with an entry point."""

    name: str
    nodes: dict[str, BlueprintNode]
    edges: list[Edge]
    entry_node: str


@dataclass
class BlueprintRun:
    """Mutable state for a single blueprint execution."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "running"
    html: str = ""
    brief_text: str = ""
    progress: list[BlueprintProgress] = field(default_factory=lambda: list[BlueprintProgress]())
    iteration_counts: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    qa_failures: list[str] = field(default_factory=lambda: list[str]())
    qa_failure_details: list[StructuredFailure] = field(
        default_factory=lambda: list[StructuredFailure]()
    )
    previous_qa_failure_details: list[StructuredFailure] = field(
        default_factory=lambda: list[StructuredFailure]()
    )
    qa_passed: bool | None = None
    judge_verdict: JudgeVerdict | None = None
    model_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    skipped_nodes: list[str] = field(default_factory=lambda: list[str]())
    routing_decisions: tuple[RoutingDecision, ...] = ()
    _last_result: NodeResult | None = field(default=None, repr=False)
    _last_handoff: AgentHandoff | None = field(default=None, repr=False)
    _handoff_history: list[AgentHandoff] = field(
        default_factory=lambda: list[AgentHandoff](), repr=False
    )
    resumed_from: str | None = None
    token_budget: int = 500_000

    @property
    def remaining_budget(self) -> float:
        """Fraction of token budget remaining (0.0 to 1.0)."""
        used = self.model_usage.get("total_tokens", 0)
        if self.token_budget <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - used / self.token_budget))


class BlueprintEngine:
    """Executes a blueprint definition as a state machine.

    Interleaves deterministic nodes (QA gate, build, export) with
    agentic nodes (scaffolder, dark mode), supporting bounded
    self-correction via recovery routing.
    """

    def __init__(
        self,
        definition: BlueprintDefinition,
        component_resolver: ComponentResolver | None = None,
        on_handoff: HandoffMemoryCallback | None = None,
        project_id: int | None = None,
        graph_provider: GraphContextProvider | None = None,
        audience_profile: "AudienceProfile | None" = None,
        judge_on_retry: bool = False,
        design_system: "DesignSystem | None" = None,
        checkpoint_store: "CheckpointStore | None" = None,
        recovery_outcome_repo: "RecoveryOutcomeRepository | None" = None,
        client_id: str | None = None,
    ) -> None:
        self._definition = definition
        self._component_resolver = component_resolver
        self._on_handoff = on_handoff
        self._project_id = project_id
        self._client_id = client_id
        self._graph_provider = graph_provider
        self._audience_profile = audience_profile
        self._judge_on_retry = judge_on_retry
        self._design_system = design_system
        self._checkpoint_store = checkpoint_store
        self._recovery_outcome_repo = recovery_outcome_repo

        # Layer pipeline executed by ``_build_node_context`` in source order.
        # Each layer is an async (ctx, run, node) -> dict[str, Any] method;
        # reserved keys (RESERVED_FIELD_KEYS) update top-level NodeContext
        # fields, all other keys merge into ``ctx.metadata``.
        self._METADATA_LAYERS: tuple[
            Callable[
                [NodeContext, BlueprintRun, BlueprintNode],
                Coroutine[Any, Any, dict[str, Any]],
            ],
            ...,
        ] = (
            self._layer_01_agent_budget,
            self._layer_02_upstream_handoff,
            self._layer_03_handoff_history,
            self._layer_04_qa_failure_details,
            self._layer_05_economy,
            self._layer_06_progress_anchor,
            self._layer_10_recalled_memories,
            self._layer_11_component_context,
            self._layer_12_graph_context,
            self._layer_13_recovery_repo,
            self._layer_14_audience_profile_ref,
            self._layer_15_audience_context,
            self._layer_16_project_subgraph,
            self._layer_17_failure_patterns,
            self._layer_18_competitive_context,
            self._layer_19_client_lookup_tools,
            self._layer_21_knowledge_prefetch,
            self._layer_22_multimodal,
            self._layer_23_visual_override,
            self._layer_24_design_system,
            self._layer_25_injection_scan,
        )

    async def run(
        self, brief: str, initial_html: str = "", user_id: int | None = None
    ) -> BlueprintRun:
        """Execute the blueprint graph from entry to terminal node."""
        from app.core.quota import BlueprintCostTracker

        run = BlueprintRun(html=initial_html, brief_text=brief)

        # Build routing plan before main loop (deterministic, no I/O)
        routing_plan = build_routing_plan(
            node_names=list(self._definition.nodes.keys()),
            audience_profile=self._audience_profile,
            html=initial_html,
            brief=brief,
        )
        run.routing_decisions = routing_plan.decisions

        # Set up cost tracking if user_id provided
        cost_tracker: BlueprintCostTracker | None = None
        if user_id is not None:
            _settings = get_settings()
            cost_tracker = BlueprintCostTracker(daily_cap=_settings.blueprint.daily_token_cap)

        logger.info(
            "blueprint.run_started",
            blueprint=self._definition.name,
            run_id=run.run_id,
        )

        return await self._execute_from(
            run, self._definition.entry_node, brief, routing_plan, cost_tracker, user_id
        )

    async def resume(self, run_id: str, brief: str, user_id: int | None = None) -> BlueprintRun:
        """Resume a blueprint run from its latest checkpoint.

        Loads the latest checkpoint, validates the blueprint definition hasn't
        changed incompatibly, and continues execution from the next unfinished node.
        """
        if self._checkpoint_store is None:
            raise BlueprintError("Checkpoints are not enabled — cannot resume")

        from app.ai.blueprints.checkpoint import restore_run

        data = await self._checkpoint_store.load_latest(run_id)
        if data is None:
            raise BlueprintError(f"No checkpoint found for run {run_id}")

        # Validate blueprint name matches
        if data.blueprint_name != self._definition.name:
            raise BlueprintError(
                f"Blueprint mismatch: checkpoint is for '{data.blueprint_name}', "
                f"but engine has '{self._definition.name}'"
            )

        # Validate next node exists in current definition
        next_node = data.next_node_name
        if next_node is not None and next_node not in self._definition.nodes:
            raise BlueprintError(
                f"Blueprint definition changed: node '{next_node}' no longer exists"
            )

        run = restore_run(data)
        run.resumed_from = data.node_name

        # Terminal checkpoint — nothing left to execute
        if next_node is None:
            if run.status == "running":
                run.status = (
                    "completed" if run.qa_passed is not False else "completed_with_warnings"
                )
            logger.info(
                "blueprint.resume_terminal",
                run_id=run_id,
                node_name=data.node_name,
            )
            return run

        # Build routing plan for remaining nodes
        routing_plan = build_routing_plan(
            node_names=list(self._definition.nodes.keys()),
            audience_profile=self._audience_profile,
            html=run.html,
            brief=brief,
        )
        run.routing_decisions = routing_plan.decisions

        # Set up cost tracking
        from app.core.quota import BlueprintCostTracker

        cost_tracker: BlueprintCostTracker | None = None
        if user_id is not None:
            _settings = get_settings()
            cost_tracker = BlueprintCostTracker(daily_cap=_settings.blueprint.daily_token_cap)

        logger.info(
            "blueprint.run_resumed",
            run_id=run_id,
            checkpoint_node=data.node_name,
            next_node=next_node,
            blueprint=self._definition.name,
        )

        return await self._execute_from(run, next_node, brief, routing_plan, cost_tracker, user_id)

    async def _execute_from(
        self,
        run: BlueprintRun,
        start_node: str | None,
        brief: str,
        routing_plan: RoutingPlan,
        cost_tracker: "BlueprintCostTracker | None" = None,
        user_id: int | None = None,
    ) -> BlueprintRun:
        """Execute the blueprint graph starting from ``start_node``.

        Thin orchestration loop — per-step work is delegated to the helpers
        ``_run_node`` / ``_record_progress`` / ``_handle_qa_gate_outcome`` /
        ``_persist_handoff`` etc. Shared by :meth:`run` (from entry) and
        :meth:`resume` (from checkpoint).
        """
        current = start_node
        steps = 0
        while current is not None and steps < MAX_TOTAL_STEPS:
            steps += 1
            node = self._definition.nodes[current]
            iteration = run.iteration_counts.get(current, 0)
            if node.node_type == "agentic" and iteration >= MAX_SELF_CORRECTION_ROUNDS:
                raise BlueprintEscalatedError(current, iteration)

            if self._is_skipped_by_routing_plan(node, current, routing_plan):
                current = self._handle_skipped_node(run, node, current, iteration, routing_plan)
                continue

            context, result, duration_ms, judge_break = await self._run_node(
                node, run, brief, iteration, current
            )

            self._record_progress(run, node, current, result, iteration, duration_ms)
            if await self._enforce_cost_cap(run, result, cost_tracker, user_id):
                break

            if current == "qa_gate":
                await self._handle_qa_gate_outcome(run, result)

            if node.node_type == "agentic":
                run.iteration_counts[current] = iteration + 1
            run._last_result = result

            await self._persist_handoff(run, current, result)
            await self._track_correction_pattern(run, context, current, node, result)

            if judge_break or self._is_low_confidence_break(run, current, result):
                break

            logger.info(
                "blueprint.node_completed",
                node=current,
                node_type=node.node_type,
                status=result.status,
                iteration=iteration,
                duration_ms=round(duration_ms, 1),
            )

            next_node = self._resolve_next_node(current, result)
            await self._save_checkpoint(
                run, current, len(run.progress) - 1, next_node_name=next_node
            )
            current = next_node

        self._finalize_run_status(run, steps)
        await self._emit_terminal_notification(run)
        return run

    # ── ``_execute_from`` helpers ──

    def _is_skipped_by_routing_plan(
        self, node: BlueprintNode, current: str, routing_plan: RoutingPlan
    ) -> bool:
        """Routing-plan-skip predicate for agentic nodes."""
        return (
            node.node_type == "agentic"
            and not routing_plan.force_full
            and current in routing_plan.skip_nodes
        )

    def _handle_skipped_node(
        self,
        run: BlueprintRun,
        node: BlueprintNode,
        current: str,
        iteration: int,
        routing_plan: RoutingPlan,
    ) -> str | None:
        """Record a routing-plan-skipped node and return the next graph hop."""
        logger.info(
            "blueprint.node_skipped",
            node=current,
            run_id=run.run_id,
            reason="routing_plan_skip",
        )
        run.skipped_nodes.append(current)
        run.progress.append(
            BlueprintProgress(
                node_name=current,
                node_type=node.node_type,
                status="skipped",
                iteration=iteration,
                summary=_skip_summary(current, routing_plan),
                duration_ms=0.0,
            )
        )
        skip_result = NodeResult(status="skipped", html=run.html)
        return self._resolve_next_node(current, skip_result)

    async def _run_node(
        self,
        node: BlueprintNode,
        run: BlueprintRun,
        brief: str,
        iteration: int,
        current: str,
    ) -> tuple[NodeContext, NodeResult, float, bool]:
        """Build context, execute the node, scope-validate, and inline-judge.

        Returns ``(context, result, duration_ms, judge_break)`` where
        ``judge_break`` is True when the inline judge has set
        ``run.status = "needs_review"`` and the loop must exit.
        """
        context = await self._build_node_context(node, run, brief, iteration)
        start = time.monotonic()
        try:
            result = await node.execute(context)
        except Exception as exc:
            # Translation boundary: any node failure becomes BlueprintNodeError.
            logger.error(
                "blueprints.node_failed",
                node=current,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise BlueprintNodeError(current, "execution failed") from exc
        duration_ms = (time.monotonic() - start) * 1000

        result = self._validate_scope_or_reject(result, node, current, iteration, run)
        judge_break = await self._run_inline_judge_if_needed(
            node, current, iteration, context, result, run
        )
        return context, result, duration_ms, judge_break

    def _validate_scope_or_reject(
        self,
        result: NodeResult,
        node: BlueprintNode,
        current: str,
        iteration: int,
        run: BlueprintRun,
    ) -> NodeResult:
        """Reject out-of-scope fixer changes on retry by replacing the result."""
        if not (node.node_type == "agentic" and iteration > 0 and run.html and result.html):
            return result
        from app.ai.blueprints.nodes.recovery_router_node import AGENT_SCOPES
        from app.ai.blueprints.scope_validator import validate_scope

        agent_scope = AGENT_SCOPES.get(current)
        if agent_scope is None:
            return result
        violations = validate_scope(
            pre_html=run.html,
            post_html=result.html,
            scope=agent_scope,
            agent_name=current,
        )
        if not violations:
            return result
        logger.warning(
            "blueprint.scope_violation",
            agent=current,
            violations=[v.description for v in violations],
            run_id=run.run_id,
        )
        # Reject the change — keep pre-fix HTML, mark failed
        return NodeResult(
            status="failed",
            html=run.html,
            details=f"scope_violation:{current}",
            error=f"Scope violation: {violations[0].description}",
        )

    async def _run_inline_judge_if_needed(
        self,
        node: BlueprintNode,
        _current: str,
        iteration: int,
        context: NodeContext,
        result: NodeResult,
        run: BlueprintRun,
    ) -> bool:
        """Run inline judge on recovery retries; return True to break the loop."""
        if not (
            self._judge_on_retry
            and node.node_type == "agentic"
            and iteration > 0
            and result.status == "success"
            and result.html
        ):
            return False
        from app.ai.blueprints.inline_judge import run_inline_judge

        agent_name = node.name.removesuffix("_node")
        verdict = await run_inline_judge(
            agent_name=agent_name,
            context=context,
            html_output=result.html,
            run=run,
        )
        if verdict is None:
            return False
        run.judge_verdict = verdict

        if not verdict.overall_pass:
            run.status = "needs_review"
            logger.warning(
                "blueprint.inline_judge_rejected",
                agent=agent_name,
                run_id=run.run_id,
                failed_criteria=[cr.criterion for cr in verdict.criteria_results if not cr.passed],
            )
            return True
        logger.info(
            "blueprint.inline_judge_approved",
            agent=agent_name,
            run_id=run.run_id,
        )
        return False

    def _record_progress(
        self,
        run: BlueprintRun,
        node: BlueprintNode,
        current: str,
        result: NodeResult,
        iteration: int,
        duration_ms: float,
    ) -> None:
        """Append a BlueprintProgress entry and merge result html/usage into run."""
        run.progress.append(
            BlueprintProgress(
                node_name=current,
                node_type=node.node_type,
                status=result.status,
                iteration=iteration,
                summary=result.details or result.error or f"{result.status}",
                duration_ms=round(duration_ms, 1),
            )
        )
        if result.html:
            run.html = result.html
        if result.usage:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                run.model_usage[key] += result.usage.get(key, 0)

    async def _enforce_cost_cap(
        self,
        run: BlueprintRun,
        result: NodeResult,
        cost_tracker: "BlueprintCostTracker | None",
        user_id: int | None,
    ) -> bool:
        """Record this node's token spend and break the loop when the cap is hit."""
        if cost_tracker is None or user_id is None or not result.usage:
            return False
        node_tokens = result.usage.get("total_tokens", 0)
        if node_tokens <= 0:
            return False
        await cost_tracker.record_usage(user_id, node_tokens)
        remaining = await cost_tracker.check_budget(user_id)
        if remaining > 0:
            return False
        run.status = "cost_cap_exceeded"
        logger.warning(
            "blueprint.cost_cap_reached",
            run_id=run.run_id,
            user_id=user_id,
            total_tokens=run.model_usage["total_tokens"],
        )
        return True

    async def _handle_qa_gate_outcome(self, run: BlueprintRun, result: NodeResult) -> None:
        """QA gate-specific bookkeeping: pass/fail, recovery outcomes, corrections."""
        if result.status == "success":
            run.qa_passed = True
            run.qa_failures = []
            run.qa_failure_details = []
        else:
            run.qa_passed = False
            run.qa_failures = [line.strip() for line in result.details.split("\n") if line.strip()]
            # Save previous failures for cycle detection before updating.
            run.previous_qa_failure_details = list(run.qa_failure_details)
            run.qa_failure_details = list(result.structured_failures)

        if self._recovery_outcome_repo is not None:
            try:
                await self._record_recovery_outcomes(run)
            except Exception:
                # Fire-and-forget: outcome recording failures must not crash the pipeline.
                logger.debug(
                    "blueprint.recovery_outcome_record_failed",
                    run_id=run.run_id,
                    exc_info=True,
                )

    async def _persist_handoff(self, run: BlueprintRun, current: str, result: NodeResult) -> None:
        """Record handoff state on the run and dispatch the memory callback."""
        if result.handoff is None:
            return
        run._last_handoff = result.handoff
        run._handoff_history.append(result.handoff)
        if self._on_handoff is None:
            return
        try:
            await self._on_handoff(result.handoff, run.run_id, self._project_id)
        except Exception:
            # Fire-and-forget: memory persistence failures must not crash the pipeline.
            logger.warning(
                "blueprint.handoff_memory_failed",
                node=current,
                run_id=run.run_id,
                exc_info=True,
            )

    async def _track_correction_pattern(
        self,
        run: BlueprintRun,
        context: NodeContext,
        current: str,
        node: BlueprintNode,
        result: NodeResult,
    ) -> None:
        """Record a (pre, post) HTML correction pair when the agent changed HTML."""
        if not (
            node.node_type == "agentic"
            and context.html
            and result.html
            and context.html != result.html
            and result.handoff is not None
            and get_settings().correction_tracker.enabled
        ):
            return
        try:
            from app.design_sync.correction_tracker import CorrectionTracker

            tracker = CorrectionTracker(data_dir=Path("data"))
            await tracker.record_correction(
                agent=result.handoff.agent_name,
                original_html=context.html,
                corrected_html=result.html,
            )
        except Exception:
            # Fire-and-forget: correction-tracker failures must not crash the pipeline.
            logger.debug(
                "blueprint.correction_tracker_failed",
                node=current,
                run_id=run.run_id,
                exc_info=True,
            )

    def _is_low_confidence_break(self, run: BlueprintRun, current: str, result: NodeResult) -> bool:
        """Set ``needs_review`` and return True when the agent's confidence is too low."""
        if result.handoff is None or result.handoff.confidence is None:
            return False
        if result.handoff.confidence >= CONFIDENCE_REVIEW_THRESHOLD:
            return False
        run.status = "needs_review"
        logger.warning(
            "blueprint.low_confidence",
            node=current,
            confidence=result.handoff.confidence,
            threshold=CONFIDENCE_REVIEW_THRESHOLD,
            run_id=run.run_id,
        )
        return True

    def _finalize_run_status(self, run: BlueprintRun, steps: int) -> None:
        """Apply terminal status when the loop exits without one already set."""
        if run.status == "running":
            run.status = "completed" if run.qa_passed is not False else "completed_with_warnings"
        logger.info(
            "blueprint.run_completed",
            run_id=run.run_id,
            status=run.status,
            steps=steps,
            qa_passed=run.qa_passed,
        )

    async def _emit_terminal_notification(self, run: BlueprintRun) -> None:
        """Dispatch a completed/failed notification on terminal status."""
        from app.notifications.channels import Notification
        from app.notifications.emitter import emit_notification

        if run.status in ("completed", "completed_with_warnings"):
            await emit_notification(
                Notification(
                    event="blueprint.run_completed",
                    severity="info",
                    title="Blueprint run completed",
                    body=f"Blueprint run {run.run_id} completed ({run.status})",
                    project_id=self._project_id,
                    metadata={"run_id": run.run_id, "status": run.status},
                )
            )
        elif run.status in ("needs_review", "cost_cap_exceeded"):
            await emit_notification(
                Notification(
                    event="blueprint.run_failed",
                    severity="error",
                    title="Blueprint run failed",
                    body=f"Blueprint run {run.run_id}: {run.status}",
                    project_id=self._project_id,
                    metadata={"run_id": run.run_id, "status": run.status},
                )
            )

    async def _save_checkpoint(
        self,
        run: BlueprintRun,
        node_name: str,
        node_index: int,
        next_node_name: str | None = None,
    ) -> None:
        """Fire-and-forget checkpoint save after a successful node."""
        if self._checkpoint_store is None:
            return
        try:
            from app.ai.blueprints.checkpoint import serialize_run

            data = serialize_run(
                run,
                node_name=node_name,
                node_index=node_index,
                blueprint_name=self._definition.name,
                next_node_name=next_node_name,
            )
            await self._checkpoint_store.save(data)
        except Exception:
            logger.warning(
                "blueprint.checkpoint_save_failed",
                node=node_name,
                run_id=run.run_id,
                exc_info=True,
            )

    def _resolve_next_node(self, current: str, result: NodeResult) -> str | None:
        """Determine the next node based on edges and result metadata."""
        # If handoff reports blocked/failed, treat as failure for routing purposes
        if result.handoff and result.handoff.status in (
            HandoffStatus.BLOCKED,
            HandoffStatus.FAILED,
        ):
            effective_status = "failed"
        else:
            effective_status = result.status

        # Check for metadata-based routing (recovery router sets route_to)
        metadata_route = None
        if hasattr(result, "details") and "route_to:" in result.details:
            metadata_route = result.details.split("route_to:")[-1].strip()

        for edge in self._definition.edges:
            if edge.from_node != current:
                continue

            if edge.condition == "success" and effective_status == "success":
                return edge.to_node
            if edge.condition == "qa_fail" and effective_status == "failed":
                return edge.to_node
            if edge.condition == "route_to" and metadata_route == edge.route_value:
                return edge.to_node
            if edge.condition == "always":
                return edge.to_node

        return None  # terminal node

    async def _build_node_context(
        self,
        node: BlueprintNode,
        run: BlueprintRun,
        brief: str,
        iteration: int,
    ) -> NodeContext:
        """Build progressively-hydrated context by running the layer pipeline.

        The seed context is constructed from ``run`` once; each layer in
        ``self._METADATA_LAYERS`` then returns a dict that either updates
        a top-level ``NodeContext`` field (via reserved keys, applied with
        ``dataclasses.replace``) or merges into ``ctx.metadata``.
        """
        ctx = NodeContext(
            html=run.html,
            brief=brief,
            iteration=iteration,
            qa_failures=list(run.qa_failures),
        )
        for layer in self._METADATA_LAYERS:
            out = await layer(ctx, run, node)
            if not out:
                continue
            field_updates: dict[str, Any] = {
                k.lstrip("_"): out.pop(k) for k in list(out) if k in RESERVED_FIELD_KEYS
            }
            if field_updates:
                ctx = replace(ctx, **field_updates)
            if out:
                ctx.merge_metadata(out)
        return ctx

    # ── LAYERs (executed in source order by ``_build_node_context``) ──
    #
    # Contract: each layer is a pure ``async (ctx, run, node) -> dict[str, Any]``.
    # Returned dict keys merge into ``ctx.metadata`` (last-write-wins) except
    # for ``RESERVED_FIELD_KEYS`` (``_html``, ``_brief``, ``_multimodal_context``)
    # which update top-level NodeContext fields. Layers must not mutate ``ctx``
    # except where explicitly documented (visual override consumes a one-shot).

    async def _layer_01_agent_budget(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Per-agent name + token budget; optional client_id pin."""
        agent_name = node.name.removesuffix("_node")
        out: dict[str, Any] = {
            "agent_name": agent_name,
            "agent_budget": get_budget(agent_name),
        }
        if self._client_id:
            out["client_id"] = self._client_id
        return out

    async def _layer_02_upstream_handoff(
        self,
        _ctx: NodeContext,
        run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Inject upstream handoff (compact in economy mode) for agentic nodes."""
        if run._last_handoff is None:
            return {}
        economy = run.remaining_budget < ECONOMY_MODE_THRESHOLD
        out: dict[str, Any] = {
            "upstream_handoff": run._last_handoff.compact() if economy else run._last_handoff,
        }
        if node.node_type == "agentic":
            upstream_constraints = format_upstream_constraints(run._last_handoff)
            if upstream_constraints:
                out["upstream_constraints"] = upstream_constraints
            if run._last_handoff.learnings:
                out["upstream_learnings"] = run._last_handoff.learnings
        return out

    async def _layer_03_handoff_history(
        self,
        _ctx: NodeContext,
        run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Compacted handoff history with decay tiers when ≥4 entries."""
        if not run._handoff_history:
            return {}
        economy = run.remaining_budget < ECONOMY_MODE_THRESHOLD
        use_decay = len(run._handoff_history) >= 4
        return {
            "handoff_history": compact_handoff_history(
                run._handoff_history, economy=economy, decay_tiers=use_decay
            ),
        }

    async def _layer_04_qa_failure_details(
        self,
        _ctx: NodeContext,
        run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Structured QA failure lists (compact in economy mode)."""
        out: dict[str, Any] = {}
        if run.qa_failure_details:
            economy = run.remaining_budget < ECONOMY_MODE_THRESHOLD
            out["qa_failure_details"] = (
                [f.compact() for f in run.qa_failure_details]
                if economy
                else list(run.qa_failure_details)
            )
        if run.previous_qa_failure_details:
            out["previous_qa_failure_details"] = list(run.previous_qa_failure_details)
        return out

    async def _layer_05_economy(
        self,
        _ctx: NodeContext,
        run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Trajectory summary + economy_mode flag when budget is tight."""
        if run.remaining_budget >= ECONOMY_MODE_THRESHOLD:
            return {}
        return {
            "trajectory_summary": summarize_trajectory(run),
            "economy_mode": True,
        }

    async def _layer_06_progress_anchor(
        self,
        ctx: NodeContext,
        run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Compact progress summary for agentic retries."""
        if node.node_type != "agentic" or ctx.iteration <= 0:
            return {}
        return {"progress_anchor": self._build_progress_anchor(run)}

    async def _layer_10_recalled_memories(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Episodic memory recall keyed on the brief."""
        if node.node_type != "agentic" or not ctx.brief or self._project_id is None:
            return {}
        recalled = await self._recall_memories(ctx.brief)
        if not recalled:
            return {}
        return {"recalled_memories": recalled}

    async def _layer_11_component_context(
        self,
        _ctx: NodeContext,
        run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Resolve referenced components in the live HTML."""
        if node.node_type != "agentic" or not run.html or self._component_resolver is None:
            return {}
        from app.ai.blueprints.component_context import (
            detect_component_refs,
            format_component_context,
        )

        slugs = detect_component_refs(run.html)
        if not slugs:
            return {}
        components = await self._component_resolver.resolve(slugs)
        if not components:
            return {}
        return {"component_context": format_component_context(components)}

    async def _layer_12_graph_context(
        self,
        ctx: NodeContext,
        run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Knowledge graph context (lazy — only when triggers say so)."""
        if node.node_type != "agentic" or self._graph_provider is None:
            return {}
        from app.ai.blueprints.graph_context import (
            format_graph_context,
            should_fetch_graph_context,
        )

        if not should_fetch_graph_context(
            brief=ctx.brief,
            html=run.html,
            qa_failures=run.qa_failures,
            iteration=ctx.iteration,
        ):
            return {}
        graph_results = await self._search_graph(ctx.brief)
        if not graph_results:
            return {}
        return {"graph_context": format_graph_context(graph_results)}

    async def _layer_13_recovery_repo(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Adaptive-routing repo handle for the recovery router node."""
        if self._recovery_outcome_repo is None:
            return {}
        return {
            "recovery_outcome_repo": self._recovery_outcome_repo,
            "project_id": self._project_id,
        }

    async def _layer_14_audience_profile_ref(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Raw audience-profile object for downstream filters."""
        if self._audience_profile is None:
            return {}
        return {"audience_profile": self._audience_profile}

    async def _layer_15_audience_context(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Formatted audience constraints (LAYER 7 in legacy comments)."""
        if node.node_type != "agentic" or self._audience_profile is None:
            return {}
        from app.ai.blueprints.audience_context import format_audience_context

        return {
            "audience_context": format_audience_context(self._audience_profile),
            "audience_client_ids": tuple(self._audience_profile.client_ids),
        }

    async def _layer_16_project_subgraph(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Project-specific compatibility subgraph (LAYER 8 in legacy comments)."""
        if node.node_type != "agentic" or self._project_id is None or self._graph_provider is None:
            return {}
        project_subgraph = await self._search_project_subgraph(ctx.brief)
        if not project_subgraph:
            return {}
        return {"project_subgraph": project_subgraph}

    async def _layer_17_failure_patterns(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Cross-agent failure patterns (LAYER 9 in legacy comments)."""
        if node.node_type != "agentic" or self._audience_profile is None:
            return {}
        from app.ai.blueprints.failure_patterns import recall_failure_patterns

        failure_context = await recall_failure_patterns(
            agent_name=node.name.removesuffix("_node"),
            client_ids=self._audience_profile.client_ids,
            project_id=self._project_id,
        )
        if not failure_context:
            return {}
        return {"failure_patterns": failure_context}

    async def _layer_18_competitive_context(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Competitive context for the innovation node (LAYER 10 in legacy comments).

        Reads ``self._audience_profile.client_ids`` directly (not metadata) so
        the layer is independent of execution order.
        """
        if node.node_type != "agentic" or node.name != "innovation":
            return {}
        from app.ai.blueprints.competitor_context import (
            build_competitive_context,
            should_fetch_competitive_context,
        )

        if not should_fetch_competitive_context(ctx.brief):
            return {}
        audience_client_ids: tuple[str, ...] = (
            tuple(self._audience_profile.client_ids) if self._audience_profile else ()
        )
        if audience_client_ids:
            from app.knowledge.ontology.competitive_feasibility import format_feasibility_context

            competitive_ctx = format_feasibility_context(
                client_ids=audience_client_ids,
                technique=ctx.brief,
            )
        else:
            competitive_ctx = build_competitive_context(ctx.brief)
        if not competitive_ctx:
            return {}
        return {"competitive_context": competitive_ctx}

    async def _layer_19_client_lookup_tools(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Deterministic client-matrix lookup tools (LAYER 11.5 in legacy comments)."""
        if node.node_type != "agentic":
            return {}
        from app.ai.agents.tools.client_lookup import (
            _CLIENT_LOOKUP_TOOL,
            _MULTI_CLIENT_LOOKUP_TOOL,
        )

        return {
            "client_lookup_tool": _CLIENT_LOOKUP_TOOL,
            "client_lookup_batch_tool": _MULTI_CLIENT_LOOKUP_TOOL,
        }

    async def _layer_21_knowledge_prefetch(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Cognee prior-outcome prefetch (LAYER 13 in legacy comments)."""
        if node.node_type != "agentic" or self._graph_provider is None or self._project_id is None:
            return {}
        settings = get_settings()
        if not settings.cognee.prefetch_enabled:
            return {}
        from app.ai.agents.knowledge_prefetch import (
            format_prefetch_context,
            prefetch_prior_outcomes,
        )

        try:
            prefetch_results = await prefetch_prior_outcomes(
                agent_name=node.name.removesuffix("_node"),
                brief=ctx.brief,
                project_id=self._project_id,
                graph_provider=self._graph_provider,
                top_k=settings.cognee.prefetch_top_k,
                min_score=settings.cognee.prefetch_min_score,
                cache_ttl=settings.cognee.prefetch_ttl_seconds,
            )
        except Exception:
            logger.debug(
                "blueprint.knowledge_prefetch_failed",
                node=node.name,
                project_id=self._project_id,
                exc_info=True,
            )
            return {}
        if not prefetch_results:
            return {}
        return {"knowledge_prefetch": format_prefetch_context(prefetch_results)}

    async def _layer_22_multimodal(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Feature-gated multimodal context for agentic nodes (LAYER 14).

        Reads ``ctx.metadata['design_import_assets']`` and
        ``ctx.metadata['screenshots']`` — both are external pre-fills, not
        outputs of an earlier layer, so the layer is order-independent.
        """
        if node.node_type != "agentic" or not get_settings().ai.multimodal_context_enabled:
            return {}
        from app.ai.multimodal import ContentBlock, ImageBlock, TextBlock

        multimodal_blocks: list[ContentBlock] = []

        if node.name == "scaffolder":
            design_import_assets: list[dict[str, object]] = ctx.metadata.get(  # type: ignore[assignment]
                "design_import_assets", []
            )
            for asset in design_import_assets:
                raw_image = asset.get("image_bytes")
                if isinstance(raw_image, bytes):
                    multimodal_blocks.append(
                        ImageBlock(
                            data=raw_image,
                            media_type=str(asset.get("media_type", "image/png")),
                            source="base64",
                        )
                    )

        if node.name == "visual_qa":
            import base64 as _b64

            screenshots_dict: dict[str, str] = ctx.metadata.get("screenshots", {})  # type: ignore[assignment]
            for client_name, b64_data in screenshots_dict.items():
                try:
                    image_bytes = _b64.b64decode(b64_data)
                    multimodal_blocks.append(
                        ImageBlock(data=image_bytes, media_type="image/png", source="base64")
                    )
                    multimodal_blocks.append(TextBlock(text=f"[Screenshot: {client_name}]"))
                except Exception:
                    logger.warning(
                        "blueprint.multimodal_context.invalid_screenshot",
                        client=client_name,
                        exc_info=True,
                    )

        if not multimodal_blocks:
            return {}
        from app.ai.multimodal import validate_content_blocks

        try:
            validate_content_blocks(multimodal_blocks)
        except Exception:
            logger.warning(
                "blueprint.multimodal_context.validation_failed",
                node=node.name,
                block_count=len(multimodal_blocks),
                exc_info=True,
            )
            return {}
        return {"_multimodal_context": multimodal_blocks}

    async def _layer_23_visual_override(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Recovery-router-injected screenshot override for fixers (LAYER 14.5).

        One-shot consumer: pops ``multimodal_context_override`` from metadata
        after applying — the only documented metadata-mutation in the layer
        pipeline, modelled on the original code's pop-after-injection.
        """
        override_raw = ctx.metadata.get("multimodal_context_override")
        if not (isinstance(override_raw, list) and override_raw and node.node_type == "agentic"):
            return {}
        from app.ai.multimodal import ContentBlock

        typed_blocks: list[ContentBlock] = [
            b
            for b in cast(list[Any], override_raw)  # type: ignore[redundant-cast]
            if isinstance(b, ContentBlock)
        ]
        # Clear override after injection (one-shot, intentional metadata pop)
        ctx.metadata.pop("multimodal_context_override", None)
        if not typed_blocks:
            return {}
        existing = ctx.multimodal_context or []
        return {"_multimodal_context": [*existing, *typed_blocks]}

    async def _layer_24_design_system(
        self,
        _ctx: NodeContext,
        _run: BlueprintRun,
        _node: BlueprintNode,
    ) -> dict[str, Any]:
        """Design-system tokens for prompt context + brand repair."""
        if self._design_system is None:
            return {}
        from app.projects.design_system import (
            design_system_to_brand_rules,
            resolve_color_map,
            resolve_font_map,
        )

        return {
            "design_system": self._design_system,
            "design_system_brand_rules": design_system_to_brand_rules(self._design_system),
            "ds_color_map": resolve_color_map(self._design_system),
            "ds_font_map": resolve_font_map(self._design_system),
        }

    async def _layer_25_injection_scan(
        self,
        ctx: NodeContext,
        _run: BlueprintRun,
        node: BlueprintNode,
    ) -> dict[str, Any]:
        """Prompt-injection scan over user-supplied fields (LAYER 18).

        May return ``_brief``/``_html`` reserved keys to replace top-level
        fields with sanitised values, plus sanitised ``qa_failure_details``
        and ``graph_context`` metadata overrides. Always runs last so its
        sanitised values take effect over earlier layers' outputs.
        """
        settings_pg = get_settings()
        if not settings_pg.security.prompt_guard_enabled:
            return {}
        pg_mode = settings_pg.security.prompt_guard_mode
        agent_name = node.name.removesuffix("_node")
        out: dict[str, Any] = {}

        for field_name, field_val, reserved_key in (
            ("brief", ctx.brief, "_brief"),
            ("html", ctx.html, "_html"),
        ):
            if not field_val:
                continue
            scan = scan_for_injection(field_val, mode=pg_mode)
            if scan.clean:
                continue
            logger.warning(
                "security.prompt_injection_detected",
                field=field_name,
                flags=scan.flags,
                agent=agent_name,
            )
            if pg_mode == "strip" and scan.sanitized is not None:
                out[reserved_key] = scan.sanitized

        for meta_key in ("qa_failure_details", "graph_context"):
            meta_val = ctx.metadata.get(meta_key)
            if not isinstance(meta_val, str):
                continue
            scan = scan_for_injection(meta_val, mode=pg_mode)
            if not scan.clean and pg_mode == "strip" and scan.sanitized is not None:
                out[meta_key] = scan.sanitized
        return out

    async def _recall_memories(self, brief: str) -> list[dict[str, str]]:
        """Recall relevant memories from prior blueprint runs.

        Returns a list of memory dicts (content, agent, type) for injection
        into agentic node context. Failure-safe: returns empty list on errors.
        """
        try:
            from app.core.scoped_db import get_system_db_context
            from app.knowledge.embedding import get_embedding_provider
            from app.memory.service import MemoryService

            async with get_system_db_context() as db:
                embedding_provider = get_embedding_provider(get_settings())
                memory_service = MemoryService(db, embedding_provider)
                memories = await memory_service.recall(
                    brief,
                    project_id=self._project_id,
                    limit=5,
                )
                return [
                    {
                        "content": m.content,
                        "agent": m.agent_type,
                        "type": m.memory_type,
                    }
                    for m, score in memories
                    if score > 0.3
                ]
        except Exception:
            logger.debug(
                "blueprint.memory_recall_failed",
                project_id=self._project_id,
                exc_info=True,
            )
            return []

    async def _record_recovery_outcomes(self, run: BlueprintRun) -> None:
        """Record recovery outcomes for each fixer that ran before this QA gate.

        Cross-references handoff history with QA results to determine which
        fixes succeeded and which failed. Fire-and-forget safe.
        """
        if self._recovery_outcome_repo is None or not run._handoff_history:
            return

        from app.ai.blueprints.nodes.recovery_router_node import CHECK_TO_AGENT, _fingerprint

        # Build set of still-failing checks
        still_failing: set[str] = set()
        for sf in run.qa_failure_details:
            still_failing.add(sf.check_name)

        # For each previous QA failure that a fixer was routed to address
        for prev_sf in run.previous_qa_failure_details:
            agent = prev_sf.suggested_agent or CHECK_TO_AGENT.get(prev_sf.check_name)
            if agent is None:
                continue

            # Check if this agent actually ran (is in handoff history)
            ran = any(h.agent_name == agent for h in run._handoff_history)
            if not ran:
                continue

            resolved = prev_sf.check_name not in still_failing
            await self._recovery_outcome_repo.record(
                check_name=prev_sf.check_name,
                agent_routed=agent,
                failure_fingerprint=_fingerprint(prev_sf),
                resolved=resolved,
                iterations_needed=run.iteration_counts.get(f"{agent}_node", 1),
                run_id=run.run_id,
                project_id=self._project_id,
            )

    async def _search_graph(self, query: str) -> list["GraphSearchResult"]:
        """Search knowledge graph for structured compatibility context.

        Failure-safe: returns empty list on errors so the pipeline continues.
        """
        if self._graph_provider is None:
            return []

        try:
            results = await self._graph_provider.search(query, top_k=5)

            logger.debug(
                "blueprint.graph_search_completed",
                project_id=self._project_id,
                result_count=len(results),
            )
            return results
        except Exception:
            logger.debug(
                "blueprint.graph_search_failed",
                project_id=self._project_id,
                exc_info=True,
            )
            return []

    async def _search_project_subgraph(self, brief: str) -> str | None:
        """Search the project-specific onboarding subgraph for relevant constraints.

        Returns formatted context string or None if no results.
        Failure-safe: returns None on errors.
        """
        if self._graph_provider is None or self._project_id is None:
            return None
        try:
            dataset = f"project_onboarding_{self._project_id}"
            # dataset_name is supported by CogneeGraphProvider but not in the Protocol
            results = await self._graph_provider.search(  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
                f"email client compatibility constraints for: {brief}",
                dataset_name=dataset,  # pyright: ignore[reportCallIssue]
                top_k=5,
            )
            if not results:
                return None

            from app.ai.blueprints.graph_context import format_graph_context

            formatted = format_graph_context(results)  # pyright: ignore[reportUnknownArgumentType]
            return formatted.replace(
                "--- GRAPH KNOWLEDGE CONTEXT ---",
                "--- PROJECT COMPATIBILITY CONTEXT ---",
            )
        except Exception:
            logger.debug(
                "blueprint.project_subgraph_search_failed",
                project_id=self._project_id,
                exc_info=True,
            )
            return None

    def _build_progress_anchor(self, run: BlueprintRun) -> str:
        """Build compact progress summary for agentic retry context."""
        parts: list[str] = []
        for entry in run.progress:
            if entry.status == "success":
                parts.append(f"{entry.node_name}:ok")
            else:
                parts.append(f"{entry.node_name}:{entry.summary[:60]}")
        return "[PROGRESS] " + " → ".join(parts)


def _skip_summary(node_name: str, plan: RoutingPlan) -> str:
    """Get the skip reason from routing plan for the progress log."""
    for d in plan.decisions:
        if d.node_name == node_name and d.action.value == "skip":
            return f"Skipped: {d.reason}"
    return "Skipped: not relevant for target audience"


def _make_pipeline_checkpoint_adapter(
    store: "CheckpointStore",
    blueprint_name: str,
) -> object:
    """Adapt blueprint CheckpointStore to PipelineCheckpointCallback interface.

    Stores pipeline pass checkpoints in the same ``blueprint_checkpoints`` table
    using compound node names (``scaffolder:<pass_name>``) and a +100 node_index
    offset to avoid collision with node-level checkpoints.
    """
    import hashlib

    from sqlalchemy import select

    from app.ai.agents.scaffolder.pipeline_checkpoint import PipelineCheckpoint
    from app.ai.blueprints.checkpoint_models import BlueprintCheckpoint

    class _Adapter:
        async def save_pass(self, checkpoint: PipelineCheckpoint) -> None:
            data_dict = {"pipeline_pass": checkpoint.pass_name, "pipeline_data": checkpoint.data}
            row = BlueprintCheckpoint(
                run_id=checkpoint.run_id,
                blueprint_name=blueprint_name,
                node_name=f"scaffolder:{checkpoint.pass_name}",
                node_index=checkpoint.pass_index + 100,
                state_json=data_dict,
                html_hash=hashlib.sha256(b"").hexdigest(),
            )
            store._db.add(row)  # type: ignore[attr-defined]
            await store._db.commit()  # type: ignore[attr-defined]

        async def load_passes(self, run_id: str) -> list[PipelineCheckpoint]:
            stmt = (
                select(BlueprintCheckpoint)
                .where(
                    BlueprintCheckpoint.run_id == run_id,
                    BlueprintCheckpoint.node_name.like("scaffolder:%"),
                    BlueprintCheckpoint.node_index >= 100,
                )
                .order_by(BlueprintCheckpoint.node_index.asc())
            )
            raw_result: Any = await store._db.execute(stmt)  # type: ignore[attr-defined]
            rows: list[BlueprintCheckpoint] = list(raw_result.scalars().all())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            return [
                PipelineCheckpoint(
                    run_id=run_id,
                    pass_name=row.state_json["pipeline_pass"],
                    pass_index=row.node_index - 100,
                    data=row.state_json["pipeline_data"],
                )
                for row in rows
            ]

    return _Adapter()
