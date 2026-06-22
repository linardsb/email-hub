# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportArgumentType=false
"""Per-helper unit tests for ``BlueprintEngine._execute_from`` decomposition.

Each helper extracted in Step 3 is exercised in isolation to lock down its
contract: gate predicates, side effects on ``BlueprintRun`` state, and the
break-or-continue signals returned to the orchestrator loop.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ai.blueprints.engine import (
    BlueprintDefinition,
    BlueprintEngine,
    BlueprintRun,
)
from app.ai.blueprints.protocols import (
    AgentHandoff,
    HandoffStatus,
    NodeContext,
    NodeResult,
    NodeType,
    StructuredFailure,
)
from app.ai.blueprints.route_advisor import RoutingPlan


class _StubNode:
    def __init__(self, name: str, node_type: NodeType = "agentic") -> None:
        self._name: str = name
        self._node_type: NodeType = node_type

    @property
    def name(self) -> str:
        return self._name

    @property
    def node_type(self) -> NodeType:
        return self._node_type

    async def execute(self, _context: NodeContext) -> NodeResult:
        return NodeResult(status="success")


def _make_engine(**kwargs: object) -> BlueprintEngine:
    definition = BlueprintDefinition(name="test", nodes={}, edges=[], entry_node="entry")
    return BlueprintEngine(definition, **kwargs)  # type: ignore[arg-type]


# ── _is_skipped_by_routing_plan ──


class TestIsSkipped:
    def test_agentic_in_skip_set_skipped(self) -> None:
        engine = _make_engine()
        plan = RoutingPlan(
            decisions=(),
            skip_nodes=frozenset({"dark_mode"}),
            prioritise_nodes=frozenset(),
            force_full=False,
        )
        assert engine._is_skipped_by_routing_plan(_StubNode("dark_mode"), "dark_mode", plan)

    def test_force_full_overrides_skip(self) -> None:
        engine = _make_engine()
        plan = RoutingPlan(
            decisions=(),
            skip_nodes=frozenset({"dark_mode"}),
            prioritise_nodes=frozenset(),
            force_full=True,
        )
        assert not engine._is_skipped_by_routing_plan(_StubNode("dark_mode"), "dark_mode", plan)

    def test_deterministic_node_not_skipped(self) -> None:
        engine = _make_engine()
        plan = RoutingPlan(
            decisions=(),
            skip_nodes=frozenset({"qa_gate"}),
            prioritise_nodes=frozenset(),
            force_full=False,
        )
        assert not engine._is_skipped_by_routing_plan(
            _StubNode("qa_gate", node_type="deterministic"), "qa_gate", plan
        )


# ── _validate_scope_or_reject ──


class TestValidateScope:
    def test_no_violations_returns_original(self) -> None:
        engine = _make_engine()
        run = BlueprintRun(html="<html><body><p>orig</p></body></html>")
        result = NodeResult(status="success", html="<html><body><p>orig</p></body></html>")
        node = _StubNode("scaffolder_node", node_type="agentic")
        out = engine._validate_scope_or_reject(
            result, node, "scaffolder_node", iteration=1, run=run
        )
        assert out is result

    def test_first_iteration_passthrough(self) -> None:
        """No scope check on first iteration (only retries are validated)."""
        engine = _make_engine()
        run = BlueprintRun(html="<p>before</p>")
        result = NodeResult(status="success", html="<p>after</p>")
        node = _StubNode("scaffolder_node", node_type="agentic")
        out = engine._validate_scope_or_reject(
            result, node, "scaffolder_node", iteration=0, run=run
        )
        assert out is result


# ── _record_progress ──


class TestRecordProgress:
    def test_appends_progress_and_updates_state(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        node = _StubNode("scaffolder_node")
        result = NodeResult(
            status="success",
            html="<p>built</p>",
            details="ok",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        engine._record_progress(run, node, "scaffolder_node", result, iteration=0, duration_ms=42.0)
        assert len(run.progress) == 1
        assert run.progress[0].status == "success"
        assert run.html == "<p>built</p>"
        assert run.model_usage["total_tokens"] == 30


# ── _enforce_cost_cap ──


@pytest.mark.asyncio
class TestEnforceCostCap:
    async def test_no_tracker_returns_false(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        result = NodeResult(status="success", usage={"total_tokens": 100})
        assert not await engine._enforce_cost_cap(run, result, None, user_id=1)

    async def test_no_user_returns_false(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        tracker = AsyncMock()
        assert not await engine._enforce_cost_cap(
            run, NodeResult(status="success"), tracker, user_id=None
        )

    async def test_cap_exceeded_sets_status(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        tracker = AsyncMock()
        tracker.check_budget.return_value = 0
        result = NodeResult(status="success", usage={"total_tokens": 1000})
        broke = await engine._enforce_cost_cap(run, result, tracker, user_id=42)
        assert broke
        assert run.status == "cost_cap_exceeded"


# ── _handle_qa_gate_outcome ──


@pytest.mark.asyncio
class TestHandleQAGateOutcome:
    async def test_success_clears_failures(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        run.qa_failure_details = [
            StructuredFailure(
                check_name="x",
                score=0.1,
                details="d",
                suggested_agent="a",
                priority=1,
            )
        ]
        await engine._handle_qa_gate_outcome(run, NodeResult(status="success", details="all good"))
        assert run.qa_passed is True
        assert run.qa_failures == []
        assert run.qa_failure_details == []

    async def test_failure_records_details(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        result = NodeResult(
            status="failed",
            details="html_validation: missing\ncss_audit: bad",
            structured_failures=(
                StructuredFailure(
                    check_name="html_validation",
                    score=0.0,
                    details="x",
                    suggested_agent="scaffolder",
                    priority=1,
                ),
            ),
        )
        await engine._handle_qa_gate_outcome(run, result)
        assert run.qa_passed is False
        assert run.qa_failures == ["html_validation: missing", "css_audit: bad"]
        assert len(run.qa_failure_details) == 1


# ── _persist_handoff ──


@pytest.mark.asyncio
class TestPersistHandoff:
    async def test_no_handoff_noop(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        await engine._persist_handoff(run, "scaff", NodeResult(status="success"))
        assert run._last_handoff is None
        assert run._handoff_history == []

    async def test_records_and_dispatches_callback(self) -> None:
        callback = AsyncMock()
        engine = _make_engine(on_handoff=callback)
        run = BlueprintRun()
        handoff = AgentHandoff(status=HandoffStatus.OK, agent_name="scaffolder")
        await engine._persist_handoff(
            run, "scaffolder_node", NodeResult(status="success", handoff=handoff)
        )
        assert run._last_handoff is handoff
        assert run._handoff_history == [handoff]
        callback.assert_awaited_once()

    async def test_callback_failure_does_not_raise(self) -> None:
        callback = AsyncMock(side_effect=RuntimeError("boom"))
        engine = _make_engine(on_handoff=callback)
        run = BlueprintRun()
        handoff = AgentHandoff(status=HandoffStatus.OK, agent_name="scaffolder")
        # Must not raise — fire-and-forget
        await engine._persist_handoff(
            run, "scaffolder_node", NodeResult(status="success", handoff=handoff)
        )
        assert run._last_handoff is handoff


# ── _is_low_confidence_break ──


class TestLowConfidenceBreak:
    def test_no_handoff_no_break(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        assert not engine._is_low_confidence_break(run, "scaff", NodeResult(status="success"))

    def test_high_confidence_no_break(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        result = NodeResult(
            status="success",
            handoff=AgentHandoff(agent_name="scaff", confidence=0.9),
        )
        assert not engine._is_low_confidence_break(run, "scaff", result)
        assert run.status == "running"

    def test_low_confidence_breaks_and_marks_review(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        result = NodeResult(
            status="success",
            handoff=AgentHandoff(agent_name="scaff", confidence=0.3),
        )
        assert engine._is_low_confidence_break(run, "scaff", result)
        assert run.status == "needs_review"


# ── _track_correction_pattern ──


@pytest.mark.asyncio
class TestTrackCorrection:
    async def test_no_change_noop(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        ctx = NodeContext(html="<p>same</p>")
        result = NodeResult(
            status="success",
            html="<p>same</p>",
            handoff=AgentHandoff(agent_name="scaff"),
        )
        # Must not raise — gated on html difference
        await engine._track_correction_pattern(run, ctx, "scaff", _StubNode("scaff"), result)

    async def test_no_handoff_noop(self) -> None:
        engine = _make_engine()
        run = BlueprintRun()
        ctx = NodeContext(html="<p>before</p>")
        result = NodeResult(status="success", html="<p>after</p>")
        await engine._track_correction_pattern(run, ctx, "scaff", _StubNode("scaff"), result)


# ── _finalize_run_status ──


class TestFinalizeRunStatus:
    def test_running_with_qa_passed_completes(self) -> None:
        engine = _make_engine()
        run = BlueprintRun(status="running")
        run.qa_passed = True
        engine._finalize_run_status(run, steps=5)
        assert run.status == "completed"

    def test_running_with_qa_failed_completes_with_warnings(self) -> None:
        engine = _make_engine()
        run = BlueprintRun(status="running")
        run.qa_passed = False
        engine._finalize_run_status(run, steps=10)
        assert run.status == "completed_with_warnings"

    def test_already_terminal_kept(self) -> None:
        engine = _make_engine()
        run = BlueprintRun(status="needs_review")
        run.qa_passed = False
        engine._finalize_run_status(run, steps=3)
        assert run.status == "needs_review"
