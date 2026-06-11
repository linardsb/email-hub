# pyright: reportReturnType=false, reportArgumentType=false
"""Tests for cross-agent failure pattern extraction, persistence, and recall."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.audience_context import AudienceProfile
from app.ai.blueprints.engine import BlueprintRun
from app.ai.blueprints.failure_patterns import (
    FAILURE_PATTERN_DATASET,
    FailurePattern,
    _format_pattern_for_graph,
    _format_pattern_for_memory,
    export_failure_patterns_to_graph,
    extract_failure_patterns,
    format_failure_pattern_context,
    persist_failure_patterns,
    recall_failure_patterns,
)
from app.ai.blueprints.protocols import AgentHandoff


def _make_run(
    *,
    status: str = "completed",
    qa_passed: bool | None = True,
    qa_failures: list[str] | None = None,
    handoffs: list[AgentHandoff] | None = None,
) -> BlueprintRun:
    """Helper to build a BlueprintRun with controlled state."""
    run = BlueprintRun()
    run.status = status
    run.qa_passed = qa_passed
    run.qa_failures = qa_failures or []
    run._handoff_history = handoffs or []
    run.iteration_counts = {}
    run.model_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return run


def _make_audience(
    client_ids: tuple[str, ...] = ("outlook_2016", "apple_mail_18"),
) -> AudienceProfile:
    """Helper to build a minimal AudienceProfile."""
    return AudienceProfile(
        persona_names=("test_persona",),
        client_ids=client_ids,
        clients=(),
        constraints=(),
        dark_mode_required=False,
        mobile_viewports=(),
    )


class TestExtractFailurePatterns:
    def test_no_failures_returns_empty(self) -> None:
        run = _make_run(qa_passed=True)
        result = extract_failure_patterns(run, "campaign")
        assert result == []

    def test_qa_none_returns_empty(self) -> None:
        run = _make_run(qa_passed=None)
        result = extract_failure_patterns(run, "campaign")
        assert result == []

    def test_qa_failures_produces_patterns(self) -> None:
        handoff = AgentHandoff(
            agent_name="scaffolder",
            artifact="<p>bad</p>",
            decisions=("Used table layout",),
            warnings=("Missing dark_mode meta tag",),
            confidence=0.4,
        )
        run = _make_run(
            qa_passed=False,
            qa_failures=[
                "dark_mode: Missing color-scheme meta",
                "css_support: Unsupported property",
            ],
            handoffs=[handoff],
        )
        audience = _make_audience()

        patterns = extract_failure_patterns(run, "campaign", audience)

        assert len(patterns) == 2
        # dark_mode maps to dark_mode agent
        assert patterns[0].agent_name == "dark_mode"
        assert patterns[0].qa_check == "dark_mode"
        assert patterns[0].client_ids == ("outlook_2016", "apple_mail_18")
        assert "Missing color-scheme meta" in patterns[0].description
        # css_support maps to scaffolder agent
        assert patterns[1].agent_name == "scaffolder"
        assert patterns[1].qa_check == "css_support"

    def test_maps_qa_check_to_agent(self) -> None:
        run = _make_run(
            qa_passed=False,
            qa_failures=["fallback: Missing MSO conditionals"],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert patterns[0].agent_name == "outlook_fixer"

    def test_fallback_agent_from_handoff_history(self) -> None:
        handoff = AgentHandoff(agent_name="innovation", artifact="<p>x</p>")
        run = _make_run(
            qa_passed=False,
            qa_failures=["unknown_check: Something weird"],
            handoffs=[handoff],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert patterns[0].agent_name == "innovation"

    def test_no_agent_found_uses_unknown(self) -> None:
        run = _make_run(
            qa_passed=False,
            qa_failures=["unknown_check: Something weird"],
            handoffs=[],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert patterns[0].agent_name == "unknown"

    def test_includes_workaround_from_warnings(self) -> None:
        handoff = AgentHandoff(
            agent_name="scaffolder",
            artifact="<p>bad</p>",
            warnings=("css_support: inline styles only for Outlook",),
            decisions=("Used 2-column layout",),
            confidence=0.5,
        )
        run = _make_run(
            qa_passed=False,
            qa_failures=["css_support: Unsupported flexbox"],
            handoffs=[handoff],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert "inline styles only for Outlook" in patterns[0].workaround

    def test_uses_decisions_when_no_matching_warnings(self) -> None:
        handoff = AgentHandoff(
            agent_name="scaffolder",
            artifact="<p>bad</p>",
            warnings=("Unrelated warning",),
            decisions=("Used table layout", "Added VML"),
            confidence=0.6,
        )
        run = _make_run(
            qa_passed=False,
            qa_failures=["css_support: Unsupported property"],
            handoffs=[handoff],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert "Used table layout" in patterns[0].workaround
        assert "Added VML" in patterns[0].workaround

    def test_without_audience_produces_empty_client_ids(self) -> None:
        run = _make_run(
            qa_passed=False,
            qa_failures=["dark_mode: Missing meta"],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert patterns[0].client_ids == ()

    def test_empty_qa_check_skipped(self) -> None:
        run = _make_run(
            qa_passed=False,
            qa_failures=[": empty check name"],
        )
        patterns = extract_failure_patterns(run, "campaign")
        assert len(patterns) == 0


class TestFormatPatternForMemory:
    def test_contains_all_fields(self) -> None:
        pattern = FailurePattern(
            agent_name="scaffolder",
            qa_check="css_support",
            client_ids=("outlook_2016",),
            description="Unsupported flexbox",
            workaround="Use table layout",
            confidence=0.4,
            run_id="run-123",
            blueprint_name="campaign",
        )
        text = _format_pattern_for_memory(pattern)
        assert "[failure_pattern]" in text
        assert "scaffolder" in text
        assert "css_support" in text
        assert "outlook_2016" in text
        assert "Unsupported flexbox" in text
        assert "Use table layout" in text
        assert "0.40" in text

    def test_truncates_long_content(self) -> None:
        pattern = FailurePattern(
            agent_name="scaffolder",
            qa_check="css_support",
            client_ids=tuple(f"client_{i}" for i in range(500)),
            description="A" * 3000,
            workaround="B" * 1000,
            confidence=0.5,
            run_id="run-123",
            blueprint_name="campaign",
        )
        text = _format_pattern_for_memory(pattern)
        assert len(text) <= 4000


class TestFormatPatternForGraph:
    def test_has_entity_friendly_headings(self) -> None:
        pattern = FailurePattern(
            agent_name="dark_mode",
            qa_check="dark_mode",
            client_ids=("outlook_2016", "apple_mail_18"),
            description="Missing color-scheme meta",
            workaround="Add meta tag",
            confidence=0.3,
            run_id="run-456",
            blueprint_name="campaign",
        )
        text = _format_pattern_for_graph(pattern)
        assert "# Failure Pattern: dark_mode on dark_mode" in text
        assert "## Affected Email Clients" in text
        assert "- outlook_2016" in text
        assert "- apple_mail_18" in text
        assert "## Known Context" in text
        assert "Add meta tag" in text
        assert "0.30" in text


class TestPersistFailurePatterns:
    @pytest.mark.asyncio()
    async def test_stores_semantic_memory(self) -> None:
        mock_service = MagicMock()
        mock_service.store = AsyncMock()

        patterns = [
            FailurePattern(
                agent_name="scaffolder",
                qa_check="css_support",
                client_ids=("outlook_2016",),
                description="Unsupported property",
                run_id="run-1",
                blueprint_name="campaign",
            ),
        ]

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_failure_patterns(patterns, project_id=42)

        mock_service.store.assert_awaited_once()
        call_args = mock_service.store.call_args[0][0]
        assert call_args.memory_type == "semantic"
        assert call_args.agent_type == "scaffolder"
        assert call_args.project_id == 42
        assert call_args.metadata["source"] == "failure_pattern"
        assert call_args.metadata["qa_check"] == "css_support"
        assert call_args.is_evergreen is False

    @pytest.mark.asyncio()
    async def test_error_safe(self) -> None:
        with patch(
            "app.core.scoped_db.get_system_db_context",
            side_effect=RuntimeError("DB unavailable"),
        ):
            # Should not raise
            await persist_failure_patterns(
                [FailurePattern(agent_name="x", qa_check="y", client_ids=(), description="z")],
                project_id=1,
            )

    @pytest.mark.asyncio()
    async def test_partial_failure_continues(self) -> None:
        mock_service = MagicMock()
        # First call raises, second succeeds
        mock_service.store = AsyncMock(side_effect=[RuntimeError("fail"), None])

        patterns = [
            FailurePattern(
                agent_name="a1",
                qa_check="q1",
                client_ids=(),
                description="d1",
                run_id="r1",
                blueprint_name="bp",
            ),
            FailurePattern(
                agent_name="a2",
                qa_check="q2",
                client_ids=(),
                description="d2",
                run_id="r1",
                blueprint_name="bp",
            ),
        ]

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_failure_patterns(patterns, project_id=1)

        assert mock_service.store.await_count == 2

    @pytest.mark.asyncio()
    async def test_empty_patterns_noop(self) -> None:
        await persist_failure_patterns([], project_id=1)
        # No error, no calls


class TestExportFailurePatternsToGraph:
    @pytest.mark.asyncio()
    async def test_queues_redis(self) -> None:
        mock_redis = AsyncMock()
        patterns = [
            FailurePattern(
                agent_name="scaffolder",
                qa_check="css_support",
                client_ids=("outlook_2016",),
                description="Unsupported property",
                run_id="run-1",
                blueprint_name="campaign",
            ),
        ]

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            await export_failure_patterns_to_graph(patterns, project_id=42)

        mock_redis.rpush.assert_awaited_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == "graph:documents:pending"
        payload = json.loads(call_args[0][1])
        assert payload["dataset_name"] == FAILURE_PATTERN_DATASET
        assert payload["project_id"] == 42
        assert len(payload["documents"]) == 1
        assert "scaffolder" in payload["documents"][0]

    @pytest.mark.asyncio()
    async def test_redis_failure_does_not_propagate(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.rpush.side_effect = ConnectionError("Redis down")

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            await export_failure_patterns_to_graph(
                [FailurePattern(agent_name="x", qa_check="y", client_ids=(), description="z")],
                project_id=1,
            )

    @pytest.mark.asyncio()
    async def test_empty_patterns_noop(self) -> None:
        await export_failure_patterns_to_graph([], project_id=1)


class TestRecallFailurePatterns:
    @pytest.mark.asyncio()
    async def test_empty_clients_returns_empty(self) -> None:
        result = await recall_failure_patterns("scaffolder", (), project_id=1)
        assert result == ""

    @pytest.mark.asyncio()
    async def test_filters_by_source(self) -> None:
        mock_memory_1 = MagicMock()
        mock_memory_1.content = "failure pattern content"
        mock_memory_1.metadata_json = {
            "source": "failure_pattern",
            "client_ids": ["outlook_2016"],
        }

        mock_memory_2 = MagicMock()
        mock_memory_2.content = "blueprint outcome content"
        mock_memory_2.metadata_json = {
            "source": "blueprint_outcome",
            "client_ids": ["outlook_2016"],
        }

        mock_service = MagicMock()
        mock_service.recall = AsyncMock(
            return_value=[
                (mock_memory_1, 0.8),
                (mock_memory_2, 0.7),
            ]
        )

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await recall_failure_patterns("scaffolder", ("outlook_2016",), project_id=1)

        assert "failure pattern content" in result
        assert "blueprint outcome content" not in result

    @pytest.mark.asyncio()
    async def test_filters_by_client(self) -> None:
        mock_memory = MagicMock()
        mock_memory.content = "gmail only pattern"
        mock_memory.metadata_json = {
            "source": "failure_pattern",
            "client_ids": ["gmail"],
        }

        mock_service = MagicMock()
        mock_service.recall = AsyncMock(return_value=[(mock_memory, 0.8)])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await recall_failure_patterns("scaffolder", ("outlook_2016",), project_id=1)

        assert result == ""

    @pytest.mark.asyncio()
    async def test_recall_error_returns_empty(self) -> None:
        with patch(
            "app.core.scoped_db.get_system_db_context",
            side_effect=RuntimeError("DB unavailable"),
        ):
            result = await recall_failure_patterns("scaffolder", ("outlook_2016",), project_id=1)
        assert result == ""

    @pytest.mark.asyncio()
    async def test_low_score_filtered(self) -> None:
        mock_memory = MagicMock()
        mock_memory.content = "low relevance"
        mock_memory.metadata_json = {
            "source": "failure_pattern",
            "client_ids": ["outlook_2016"],
        }

        mock_service = MagicMock()
        mock_service.recall = AsyncMock(return_value=[(mock_memory, 0.1)])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await recall_failure_patterns("scaffolder", ("outlook_2016",), project_id=1)

        assert result == ""


class TestFormatFailurePatternContext:
    def test_has_header_and_numbered_items(self) -> None:
        patterns = [
            "Agent 'scaffolder' failed QA check 'css_support'.",
            "Agent 'dark_mode' failed QA check 'dark_mode'.",
        ]
        result = format_failure_pattern_context(patterns)
        assert "--- CROSS-AGENT FAILURE PATTERNS ---" in result
        assert "1." in result
        assert "2." in result
        assert "scaffolder" in result
        assert "dark_mode" in result

    def test_strips_failure_pattern_prefix(self) -> None:
        patterns = ["[failure_pattern] Agent 'scaffolder' failed."]
        result = format_failure_pattern_context(patterns)
        assert "[failure_pattern]" not in result
        assert "Agent 'scaffolder' failed." in result
