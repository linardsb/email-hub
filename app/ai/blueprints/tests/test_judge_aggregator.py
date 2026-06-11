"""Tests for judge verdict aggregation and prompt patching."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.judge_aggregator import (
    PromptPatch,
    aggregate_verdicts,
    format_prompt_patches,
    persist_judge_verdict,
)

_EntryTuple = tuple[MagicMock, float]


def test_format_prompt_patches_empty() -> None:
    """Empty patches → empty string."""
    assert format_prompt_patches([]) == ""


def test_format_prompt_patches_output() -> None:
    """Patches formatted with header and instructions."""
    patches = [
        PromptPatch(
            agent_name="dark_mode",
            criterion="color_contrast",
            pass_rate=0.4,
            instruction="IMPORTANT: Fix color contrast",
            sample_count=10,
        ),
    ]
    result = format_prompt_patches(patches)
    assert "## Quality Focus Areas" in result
    assert "IMPORTANT: Fix color contrast" in result


@pytest.mark.asyncio
async def test_persist_judge_verdict() -> None:
    """Verify persist stores one memory per criterion."""
    from app.ai.agents.evals.judges.schemas import CriterionResult, JudgeVerdict

    verdict = JudgeVerdict(
        trace_id="t1",
        agent="dark_mode",
        overall_pass=False,
        criteria_results=[
            CriterionResult(criterion="color_contrast", passed=False, reasoning="Low contrast"),
            CriterionResult(criterion="meta_tag", passed=True, reasoning="OK"),
        ],
    )

    mock_memory_svc = AsyncMock()
    mock_memory_svc.store = AsyncMock()

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch("app.memory.service.MemoryService", return_value=mock_memory_svc),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        await persist_judge_verdict(verdict, project_id=1, run_id="abc123")

    # Should store 2 entries (one per criterion)
    assert mock_memory_svc.store.call_count == 2

    # Check first call metadata
    first_call = mock_memory_svc.store.call_args_list[0][0][0]
    assert first_call.memory_type == "semantic"
    assert first_call.metadata["source"] == "judge_verdict"
    assert first_call.metadata["criterion"] == "color_contrast"
    assert first_call.metadata["passed"] is False


@pytest.mark.asyncio
async def test_aggregate_identifies_failing_criteria() -> None:
    """Mixed pass/fail → patches for criteria below threshold."""
    # Build mock memory entries: 10 verdicts for "color_contrast", 3 passed
    entries: list[_EntryTuple] = []
    for i in range(10):
        entry = MagicMock()
        entry.metadata_json = {
            "source": "judge_verdict",
            "agent": "dark_mode",
            "criterion": "color_contrast",
            "passed": i < 3,  # 3 out of 10 passed = 30%
        }
        entry.content = f"verdict {i}"
        entries.append((entry, 0.8))

    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=entries)

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch("app.memory.service.MemoryService", return_value=mock_memory_svc),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        patches = await aggregate_verdicts("dark_mode", project_id=1)

    assert len(patches) == 1
    assert patches[0].criterion == "color_contrast"
    assert patches[0].pass_rate == pytest.approx(0.3)  # pyright: ignore[reportUnknownMemberType]
    assert "color_contrast" in patches[0].instruction


@pytest.mark.asyncio
async def test_aggregate_ignores_small_samples() -> None:
    """Fewer than MIN_VERDICT_SAMPLES → no patches."""
    entries: list[_EntryTuple] = []
    for i in range(3):  # only 3 samples, below MIN_VERDICT_SAMPLES
        entry = MagicMock()
        entry.metadata_json = {
            "source": "judge_verdict",
            "agent": "dark_mode",
            "criterion": "color_contrast",
            "passed": False,
        }
        entry.content = f"verdict {i}"
        entries.append((entry, 0.8))

    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=entries)

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch("app.memory.service.MemoryService", return_value=mock_memory_svc),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        patches = await aggregate_verdicts("dark_mode", project_id=1)

    assert patches == []


@pytest.mark.asyncio
async def test_aggregate_no_verdicts() -> None:
    """No memories → empty list."""
    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=[])

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch("app.memory.service.MemoryService", return_value=mock_memory_svc),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        patches = await aggregate_verdicts("dark_mode", project_id=1)

    assert patches == []


@pytest.mark.asyncio
async def test_aggregate_above_threshold_no_patch() -> None:
    """Criteria above PASS_RATE_THRESHOLD → no patches."""
    entries: list[_EntryTuple] = []
    for i in range(10):
        entry = MagicMock()
        entry.metadata_json = {
            "source": "judge_verdict",
            "agent": "dark_mode",
            "criterion": "meta_tag",
            "passed": i < 9,  # 9/10 = 90% > 70% threshold
        }
        entry.content = f"verdict {i}"
        entries.append((entry, 0.8))

    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=entries)

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch("app.memory.service.MemoryService", return_value=mock_memory_svc),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        patches = await aggregate_verdicts("dark_mode", project_id=1)

    assert patches == []
