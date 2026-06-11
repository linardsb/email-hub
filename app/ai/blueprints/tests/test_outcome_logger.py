# pyright: reportReturnType=false, reportArgumentType=false
"""Tests for blueprint outcome logging — formatting, queueing, and memory storage."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.engine import BlueprintRun
from app.ai.blueprints.outcome_logger import (
    OUTCOME_QUEUE_KEY,
    build_outcome_payload,
    format_outcome_text,
    persist_outcome_to_memory,
    queue_outcome_for_graph,
)
from app.ai.blueprints.protocols import AgentHandoff


def _make_run(
    *,
    status: str = "completed",
    qa_passed: bool | None = True,
    qa_failures: list[str] | None = None,
    handoffs: list[AgentHandoff] | None = None,
    iteration_counts: dict[str, int] | None = None,
    model_usage: dict[str, int] | None = None,
) -> BlueprintRun:
    """Helper to build a BlueprintRun with controlled state."""
    run = BlueprintRun()
    run.status = status
    run.qa_passed = qa_passed
    run.qa_failures = qa_failures or []
    run._handoff_history = handoffs or []
    run.iteration_counts = iteration_counts or {}
    run.model_usage = model_usage or {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    return run


class TestFormatOutcomeText:
    def test_completed_with_qa_passed(self) -> None:
        handoff = AgentHandoff(
            agent_name="scaffolder",
            artifact="<p>ok</p>",
            decisions=("Used 2-column layout",),
            warnings=("Missing logo placeholder",),
            confidence=0.92,
        )
        run = _make_run(
            qa_passed=True,
            handoffs=[handoff],
            model_usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )

        text = format_outcome_text(run, "campaign")

        assert "campaign" in text
        assert "completed" in text
        assert "scaffolder" in text
        assert "QA gate passed" in text
        assert "Used 2-column layout" in text
        assert "Missing logo placeholder" in text
        assert "0.92" in text
        assert "150" in text

    def test_failed_with_qa_failures(self) -> None:
        run = _make_run(
            status="completed_with_warnings",
            qa_passed=False,
            qa_failures=["dark_mode", "accessibility"],
        )

        text = format_outcome_text(run, "campaign")

        assert "QA gate failed on: dark_mode, accessibility" in text

    def test_with_self_correction(self) -> None:
        run = _make_run(iteration_counts={"scaffolder": 2, "dark_mode": 1})

        text = format_outcome_text(run, "campaign")

        assert "Self-correction applied" in text
        assert "scaffolder (2 iterations)" in text
        assert "dark_mode" not in text  # Only 1 iteration, not retried

    def test_empty_handoffs(self) -> None:
        run = _make_run(handoffs=[], qa_passed=None)

        text = format_outcome_text(run, "campaign")

        assert "campaign" in text
        assert "completed" in text
        assert "Agents involved" not in text
        assert "QA gate" not in text


class TestBuildOutcomePayload:
    def test_structure(self) -> None:
        handoff = AgentHandoff(agent_name="scaffolder", artifact="<p>ok</p>")
        run = _make_run(handoffs=[handoff], qa_passed=True)

        payload = build_outcome_payload(run, "campaign", project_id=42)

        assert payload["run_id"] == run.run_id
        assert payload["blueprint_name"] == "campaign"
        assert payload["project_id"] == 42
        assert payload["status"] == "completed"
        assert payload["qa_passed"] is True
        assert payload["qa_failures"] == []
        assert payload["agents_involved"] == ["scaffolder"]
        assert isinstance(payload["outcome_text"], str)
        assert isinstance(payload["timestamp"], str)


class TestQueueOutcomeForGraph:
    @pytest.mark.asyncio()
    async def test_success(self) -> None:
        mock_redis = AsyncMock()
        run = _make_run()

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            await queue_outcome_for_graph(run, "campaign", project_id=1)

        mock_redis.rpush.assert_awaited_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == OUTCOME_QUEUE_KEY
        payload = json.loads(call_args[0][1])
        assert payload["blueprint_name"] == "campaign"

    @pytest.mark.asyncio()
    async def test_redis_failure_does_not_propagate(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.rpush.side_effect = ConnectionError("Redis down")
        run = _make_run()

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            # Should not raise
            await queue_outcome_for_graph(run, "campaign", project_id=1)


class TestPersistOutcomeToMemory:
    @pytest.mark.asyncio()
    async def test_success(self) -> None:
        mock_service = MagicMock()
        mock_service.store = AsyncMock()
        mock_embedding = MagicMock()

        handoff = AgentHandoff(agent_name="scaffolder", artifact="<p>ok</p>")
        run = _make_run(handoffs=[handoff])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch(
                "app.knowledge.embedding.get_embedding_provider",
                return_value=mock_embedding,
            ),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_outcome_to_memory(run, "campaign", project_id=42)

        mock_service.store.assert_awaited_once()
        call_args = mock_service.store.call_args[0][0]
        assert call_args.memory_type == "semantic"
        assert call_args.agent_type == "scaffolder"
        assert call_args.project_id == 42
        assert call_args.metadata["source"] == "blueprint_outcome"

    @pytest.mark.asyncio()
    async def test_failure_does_not_propagate(self) -> None:
        run = _make_run()

        with patch(
            "app.core.scoped_db.get_system_db_context",
            side_effect=RuntimeError("DB unavailable"),
        ):
            # Should not raise
            await persist_outcome_to_memory(run, "campaign", project_id=1)

    @pytest.mark.asyncio()
    async def test_primary_agent_from_first_handoff(self) -> None:
        mock_service = MagicMock()
        mock_service.store = AsyncMock()

        handoffs = [
            AgentHandoff(agent_name="scaffolder", artifact="<p>1</p>"),
            AgentHandoff(agent_name="dark_mode", artifact="<p>2</p>"),
        ]
        run = _make_run(handoffs=handoffs)

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_outcome_to_memory(run, "campaign", project_id=1)

        call_args = mock_service.store.call_args[0][0]
        assert call_args.agent_type == "scaffolder"

    @pytest.mark.asyncio()
    async def test_no_handoffs_uses_blueprint_agent_type(self) -> None:
        mock_service = MagicMock()
        mock_service.store = AsyncMock()

        run = _make_run(handoffs=[])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_outcome_to_memory(run, "campaign", project_id=1)

        call_args = mock_service.store.call_args[0][0]
        assert call_args.agent_type == "blueprint"
