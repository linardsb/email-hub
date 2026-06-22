# pyright: reportReturnType=false, reportArgumentType=false
"""Tests for cross-agent insight persistence, dedup hashing, and handoff learnings."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.insight_bus import (
    AgentInsight,
    _compute_dedup_hash,
    persist_insights,
)
from app.ai.blueprints.protocols import AgentHandoff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
