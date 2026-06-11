# pyright: reportReturnType=false, reportArgumentType=false
"""Tests for cross-agent insight extraction, persistence, recall, and formatting."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.audience_context import AudienceProfile
from app.ai.blueprints.engine import BlueprintRun
from app.ai.blueprints.insight_bus import (
    _MAX_CONTENT_LENGTH,
    _MAX_CONTEXT_LENGTH,
    AgentInsight,
    _compute_dedup_hash,
    _format_insight_for_memory,
    extract_insights,
    format_insight_context,
    persist_insights,
    recall_insights,
)
from app.ai.blueprints.protocols import AgentHandoff, StructuredFailure

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    *,
    status: str = "completed",
    qa_passed: bool | None = True,
    qa_failures: list[str] | None = None,
    handoffs: list[AgentHandoff] | None = None,
    previous_failures: list[StructuredFailure] | None = None,
    current_failures: list[StructuredFailure] | None = None,
) -> BlueprintRun:
    run = BlueprintRun()
    run.status = status
    run.qa_passed = qa_passed
    run.qa_failures = qa_failures or []
    run._handoff_history = handoffs or []
    run.previous_qa_failure_details = previous_failures or []
    run.qa_failure_details = current_failures or []
    run.iteration_counts = {}
    run.model_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return run


def _make_audience(
    client_ids: tuple[str, ...] = ("samsung_mail", "outlook_365"),
) -> AudienceProfile:
    return AudienceProfile(
        persona_names=("test",),
        client_ids=client_ids,
        clients=(),
        constraints=(),
        dark_mode_required=False,
        mobile_viewports=(),
    )


def _make_insight(**overrides: object) -> AgentInsight:
    defaults: dict[str, object] = {
        "source_agent": "dark_mode",
        "target_agents": ("scaffolder", "code_reviewer"),
        "client_ids": ("samsung_mail",),
        "insight": "Avoid #1a1a1a backgrounds — Samsung double-inverts",
        "category": "dark_mode",
        "confidence": 0.85,
        "evidence_count": 1,
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return AgentInsight(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# TestExtractInsights
# ===========================================================================


class TestExtractInsights:
    def test_extract_from_qa_fix(self) -> None:
        """QA failure fixed between iterations → insight routed to root-cause agent."""
        # dark_mode check root cause = dark_mode agent (via _QA_CHECK_AGENT_MAP)
        # fixer = outlook_fixer (via suggested_agent on StructuredFailure)
        # root_cause != fixer → cross-agent insight created
        prev_failure = StructuredFailure(
            check_name="dark_mode",
            score=0.4,
            details="Samsung double-inverts backgrounds",
            suggested_agent="outlook_fixer",
            priority=1,
        )
        run = _make_run(
            handoffs=[AgentHandoff(agent_name="outlook_fixer", confidence=0.7)],
            previous_failures=[prev_failure],
            current_failures=[],  # Fixed!
        )
        audience = _make_audience(client_ids=("samsung_mail",))

        insights = extract_insights(run, "campaign", audience)

        assert len(insights) >= 1
        qa_insight = insights[0]
        assert qa_insight.source_agent == "outlook_fixer"
        assert "dark_mode" in qa_insight.target_agents
        assert qa_insight.category == "dark_mode"
        assert "samsung_mail" in qa_insight.client_ids

    def test_same_agent_fix_no_insight(self) -> None:
        """When root-cause agent == fixer agent → no cross-agent insight."""
        prev_failure = StructuredFailure(
            check_name="css_support",
            score=0.4,
            details="Unsupported gradient",
            suggested_agent="scaffolder",
            priority=2,
        )
        run = _make_run(
            handoffs=[AgentHandoff(agent_name="scaffolder", confidence=0.8)],
            previous_failures=[prev_failure],
            current_failures=[],
        )
        insights = extract_insights(run, "campaign", _make_audience())
        # css_support root cause = scaffolder, fixer = scaffolder → same agent, skip
        qa_insights = [i for i in insights if "css_support" in i.insight]
        assert len(qa_insights) == 0

    def test_extract_from_handoff_learnings(self) -> None:
        """Handoff with learnings → insight created for other agents."""
        handoff = AgentHandoff(
            agent_name="dark_mode",
            confidence=0.9,
            learnings=("Samsung dark mode inverted hero background — added data-ogsb",),
        )
        run = _make_run(handoffs=[handoff])
        audience = _make_audience()

        insights = extract_insights(run, "campaign", audience)

        assert len(insights) >= 1
        learning_insight = next(i for i in insights if "Samsung dark mode inverted" in i.insight)
        assert learning_insight.source_agent == "dark_mode"
        assert "dark_mode" not in learning_insight.target_agents  # Excludes source
        assert "scaffolder" in learning_insight.target_agents

    def test_extract_low_confidence(self) -> None:
        """Handoff with confidence < 0.7 → advisory insight."""
        handoff = AgentHandoff(
            agent_name="scaffolder",
            confidence=0.45,
            decisions=("Used 2-column layout", "Guessed CTA color"),
        )
        run = _make_run(handoffs=[handoff])
        audience = _make_audience()

        insights = extract_insights(run, "campaign", audience)

        low_conf = [i for i in insights if "Low confidence" in i.insight]
        assert len(low_conf) == 1
        assert low_conf[0].source_agent == "scaffolder"
        assert "code_reviewer" in low_conf[0].target_agents
        assert low_conf[0].confidence == 0.45

    def test_dedup_same_pattern(self) -> None:
        """Duplicate learnings from same agent → deduplicated."""
        handoff = AgentHandoff(
            agent_name="dark_mode",
            confidence=0.9,
            learnings=(
                "Samsung inverts backgrounds",
                "Samsung inverts backgrounds",  # Duplicate
            ),
        )
        run = _make_run(handoffs=[handoff])

        insights = extract_insights(run, "campaign", _make_audience())

        samsung_insights = [i for i in insights if "Samsung inverts" in i.insight]
        assert len(samsung_insights) == 1  # Deduplicated

    def test_no_insights_clean_run(self) -> None:
        """Clean run with no failures and high confidence → empty list."""
        handoff = AgentHandoff(agent_name="scaffolder", confidence=0.95)
        run = _make_run(handoffs=[handoff])

        insights = extract_insights(run, "campaign", _make_audience())

        assert insights == []

    def test_category_mapping(self) -> None:
        """QA check names map to correct insight categories."""
        # accessibility root cause = accessibility agent, fixer = scaffolder → cross-agent
        prev_failures = [
            StructuredFailure(
                check_name="accessibility",
                score=0.3,
                details="Missing alt text",
                suggested_agent="scaffolder",
                priority=1,
            ),
        ]
        run = _make_run(
            handoffs=[AgentHandoff(agent_name="scaffolder", confidence=0.8)],
            previous_failures=prev_failures,
            current_failures=[],
        )

        insights = extract_insights(run, "campaign", _make_audience())

        a11y = [i for i in insights if i.category == "accessibility"]
        assert len(a11y) == 1

    def test_extract_no_audience(self) -> None:
        """No audience profile → insights created with empty client_ids."""
        handoff = AgentHandoff(
            agent_name="dark_mode",
            confidence=0.9,
            learnings=("Always add data-ogsb for dark backgrounds",),
        )
        run = _make_run(handoffs=[handoff])

        insights = extract_insights(run, "campaign", audience_profile=None)

        assert len(insights) >= 1
        assert insights[0].client_ids == ()

    def test_insight_content_truncation(self) -> None:
        """Insight text exceeding 4000 chars → truncated."""
        long_learning = "x" * 5000
        handoff = AgentHandoff(
            agent_name="dark_mode",
            confidence=0.9,
            learnings=(long_learning,),
        )
        run = _make_run(handoffs=[handoff])

        insights = extract_insights(run, "campaign", _make_audience())
        assert len(insights) >= 1

        # Format for memory should truncate
        formatted = _format_insight_for_memory(insights[0])
        assert len(formatted) <= _MAX_CONTENT_LENGTH


# ===========================================================================
# TestPersistInsights
# ===========================================================================


class TestPersistInsights:
    @pytest.mark.asyncio()
    async def test_store_new_insight(self) -> None:
        """New insight → MemoryService.store() called with correct MemoryCreate."""
        mock_service = AsyncMock()
        mock_service.store = AsyncMock()

        insight = _make_insight()

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            count = await persist_insights([insight], project_id=42)

        # 2 target agents → 2 store calls
        assert mock_service.store.await_count == 2
        assert count == 2

        # Check first store call
        call_args = mock_service.store.call_args_list[0][0][0]
        assert call_args.agent_type == "scaffolder"
        assert call_args.memory_type == "semantic"
        assert call_args.project_id == 42
        assert call_args.metadata["source"] == "cross_agent_insight"
        assert call_args.metadata["source_agent"] == "dark_mode"
        assert call_args.metadata["category"] == "dark_mode"
        assert "dedup_hash" in call_args.metadata

    @pytest.mark.asyncio()
    async def test_evergreen_threshold(self) -> None:
        """evidence_count >= 5 → is_evergreen=True."""
        mock_service = AsyncMock()
        mock_service.store = AsyncMock()

        insight = _make_insight(evidence_count=5, target_agents=("scaffolder",))

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await persist_insights([insight], project_id=42)

        call_args = mock_service.store.call_args_list[0][0][0]
        assert call_args.is_evergreen is True

    @pytest.mark.asyncio()
    async def test_multi_target(self) -> None:
        """Insight targeting 2 agents → stored once per target agent."""
        mock_service = AsyncMock()
        mock_service.store = AsyncMock()

        insight = _make_insight(target_agents=("scaffolder", "accessibility"))

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            count = await persist_insights([insight], project_id=42)

        assert count == 2
        agent_types = [call[0][0].agent_type for call in mock_service.store.call_args_list]
        assert set(agent_types) == {"scaffolder", "accessibility"}

    @pytest.mark.asyncio()
    async def test_persist_error_resilience(self) -> None:
        """store() raises on 1st call, succeeds on 2nd → 1 stored, no crash."""
        mock_service = AsyncMock()
        mock_service.store = AsyncMock(side_effect=[RuntimeError("DB error"), MagicMock()])

        insight = _make_insight(target_agents=("scaffolder", "code_reviewer"))

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            count = await persist_insights([insight], project_id=42)

        assert count == 1  # 1 succeeded, 1 failed


# ===========================================================================
# TestRecallInsights
# ===========================================================================


class TestRecallInsights:
    @pytest.mark.asyncio()
    async def test_recall_filters_by_source(self) -> None:
        """Only entries with source='cross_agent_insight' are returned."""
        mock_memory = MagicMock()
        mock_memory.metadata_json = {
            "source": "cross_agent_insight",
            "source_agent": "dark_mode",
            "client_ids": ["samsung_mail"],
            "category": "dark_mode",
            "evidence_count": 3,
            "dedup_hash": "abc123",
        }
        mock_memory.content = "Avoid #1a1a1a backgrounds"
        mock_memory.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_memory.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        # Non-insight memory
        mock_non_insight = MagicMock()
        mock_non_insight.metadata_json = {"source": "blueprint_outcome"}
        mock_non_insight.content = "Run completed"
        mock_non_insight.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        mock_non_insight.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[(mock_memory, 0.8), (mock_non_insight, 0.7)])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await recall_insights(
                "scaffolder", client_ids=("samsung_mail",), project_id=42
            )

        assert len(results) == 1
        assert results[0].source_agent == "dark_mode"

    @pytest.mark.asyncio()
    async def test_recall_with_client_filter(self) -> None:
        """client_ids influence query construction."""
        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await recall_insights(
                "scaffolder", client_ids=("samsung_mail", "outlook_365"), project_id=42
            )

        query = mock_service.recall.call_args[0][0]
        assert "samsung_mail" in query

    @pytest.mark.asyncio()
    async def test_recall_empty(self) -> None:
        """No matching memories → empty list."""
        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(return_value=[])

        with (
            patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
            patch("app.knowledge.embedding.get_embedding_provider"),
            patch("app.memory.service.MemoryService", return_value=mock_service),
            patch("app.core.config.get_settings"),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await recall_insights("scaffolder", client_ids=None, project_id=42)

        assert results == []

    @pytest.mark.asyncio()
    async def test_recall_dedup_by_hash(self) -> None:
        """2 memories with same dedup_hash → only highest evidence_count returned."""

        def _make_memory(
            dedup_hash: str, evidence_count: int, score: float
        ) -> tuple[MagicMock, float]:
            m = MagicMock()
            m.metadata_json = {
                "source": "cross_agent_insight",
                "source_agent": "dark_mode",
                "client_ids": ["samsung_mail"],
                "category": "dark_mode",
                "evidence_count": evidence_count,
                "dedup_hash": dedup_hash,
            }
            m.content = "Avoid #1a1a1a"
            m.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            m.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
            return (m, score)

        mock_service = AsyncMock()
        mock_service.recall = AsyncMock(
            return_value=[
                _make_memory("hash1", evidence_count=2, score=0.8),
                _make_memory("hash1", evidence_count=5, score=0.7),  # Same hash, higher evidence
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

            results = await recall_insights(
                "scaffolder", client_ids=("samsung_mail",), project_id=42
            )

        assert len(results) == 1
        assert results[0].evidence_count == 5  # Kept the higher one


# ===========================================================================
# TestFormatInsightContext
# ===========================================================================


class TestFormatInsightContext:
    def test_format_single(self) -> None:
        insight = _make_insight()
        result = format_insight_context([insight])

        assert "--- CROSS-AGENT INSIGHTS ---" in result
        assert "dark_mode" in result
        assert "1x" in result
        assert "samsung_mail" in result

    def test_format_multiple(self) -> None:
        insights = [
            _make_insight(evidence_count=5, source_agent="dark_mode", confidence=0.9),
            _make_insight(evidence_count=1, source_agent="scaffolder", confidence=0.5),
            _make_insight(evidence_count=3, source_agent="accessibility", confidence=0.7),
        ]
        result = format_insight_context(insights)

        # Sorted by confidence descending: dark_mode (0.9), accessibility (0.7), scaffolder (0.5)
        dm_pos = result.index("dark_mode")
        a11y_pos = result.index("accessibility")
        assert dm_pos < a11y_pos

    def test_format_truncation(self) -> None:
        """Context block > 800 chars → truncated, least confident dropped."""
        insights = [
            _make_insight(
                insight="A" * 300,
                source_agent=f"agent_{i}",
                confidence=0.9 - i * 0.1,
                evidence_count=1,
            )
            for i in range(10)
        ]
        result = format_insight_context(insights)

        assert len(result) <= _MAX_CONTEXT_LENGTH


# ===========================================================================
# TestHandoffLearnings
# ===========================================================================


class TestHandoffLearnings:
    def test_learnings_field_default(self) -> None:
        handoff = AgentHandoff()
        assert handoff.learnings == ()

    def test_learnings_preserved_in_compact(self) -> None:
        handoff = AgentHandoff(
            agent_name="dark_mode",
            artifact="<p>big html</p>",
            learnings=("Samsung inverts backgrounds",),
        )
        compacted = handoff.compact()

        assert compacted.learnings == ("Samsung inverts backgrounds",)
        assert compacted.artifact == ""  # Artifact stripped

    def test_learnings_in_summary(self) -> None:
        handoff = AgentHandoff(
            agent_name="dark_mode",
            confidence=0.85,
            learnings=("Learning 1", "Learning 2"),
        )
        summary = handoff.summary()

        assert "lrn=2" in summary

    def test_no_learnings_in_summary(self) -> None:
        handoff = AgentHandoff(agent_name="dark_mode", confidence=0.85)
        summary = handoff.summary()

        assert "lrn=" not in summary


# ===========================================================================
# TestDedupHash
# ===========================================================================


class TestDedupHash:
    def test_deterministic(self) -> None:
        h1 = _compute_dedup_hash("dark_mode", "color", ("samsung_mail",), "test insight")
        h2 = _compute_dedup_hash("dark_mode", "color", ("samsung_mail",), "test insight")
        assert h1 == h2

    def test_different_agents_different_hash(self) -> None:
        h1 = _compute_dedup_hash("dark_mode", "color", ("samsung_mail",), "test")
        h2 = _compute_dedup_hash("scaffolder", "color", ("samsung_mail",), "test")
        assert h1 != h2

    def test_client_order_irrelevant(self) -> None:
        h1 = _compute_dedup_hash("dark_mode", "color", ("a", "b"), "test")
        h2 = _compute_dedup_hash("dark_mode", "color", ("b", "a"), "test")
        assert h1 == h2  # sorted internally
