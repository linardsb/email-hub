"""Tests for correction few-shot injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.blueprints.correction_examples import (
    format_correction_examples,
    recall_correction_examples,
    store_correction_example,
)


def test_format_correction_examples_empty() -> None:
    """Empty list → empty string."""
    assert format_correction_examples([]) == ""


def test_format_correction_examples_single() -> None:
    """Single example formatted with header."""
    result = format_correction_examples(["FAILURE: missing alt\nCORRECTION: added alt text"])
    assert "## Prior Successful Corrections" in result
    assert "### Example 1" in result
    assert "FAILURE: missing alt" in result


def test_format_correction_examples_multiple() -> None:
    """Multiple examples numbered correctly."""
    result = format_correction_examples(["Example A", "Example B"])
    assert "### Example 1" in result
    assert "### Example 2" in result


@pytest.mark.asyncio
async def test_store_correction_example() -> None:
    """Verify store calls MemoryService with correct parameters."""
    mock_memory_svc = AsyncMock()
    mock_memory_svc.store = AsyncMock()

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch(
            "app.memory.service.MemoryService",
            return_value=mock_memory_svc,
        ),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        # Patch MemoryService at the point of import inside the function
        with patch(
            "app.ai.blueprints.correction_examples.MemoryService",
            return_value=mock_memory_svc,
            create=True,
        ):
            await store_correction_example(
                agent_name="dark_mode",
                check_name="dark_mode",
                failure_description="No dark mode support",
                correction_summary="Added prefers-color-scheme media query",
                project_id=1,
                run_id="abc123",
            )

        mock_memory_svc.store.assert_called_once()
        call_args = mock_memory_svc.store.call_args[0][0]
        assert call_args.agent_type == "dark_mode"
        assert call_args.memory_type == "procedural"
        assert "FAILURE:" in call_args.content
        assert "CORRECTION:" in call_args.content
        assert call_args.metadata["source"] == "correction_example"


@pytest.mark.asyncio
async def test_recall_returns_empty_when_no_failures() -> None:
    """No QA failures → no recall attempted."""
    result = await recall_correction_examples("dark_mode", [], None)
    assert result == []


@pytest.mark.asyncio
async def test_recall_filters_by_source() -> None:
    """Only returns memories with source=correction_example."""
    mock_entry_good = MagicMock()
    mock_entry_good.content = "FAILURE: x\nCORRECTION: y"
    mock_entry_good.metadata_json = {"source": "correction_example"}

    mock_entry_bad = MagicMock()
    mock_entry_bad.content = "Some other memory"
    mock_entry_bad.metadata_json = {"source": "blueprint_handoff"}

    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=[(mock_entry_good, 0.8), (mock_entry_bad, 0.7)])

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch(
            "app.memory.service.MemoryService",
            return_value=mock_memory_svc,
        ),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await recall_correction_examples(
            "dark_mode", ["dark_mode: no support"], None, limit=2
        )

    assert len(result) == 1
    assert "FAILURE: x" in result[0]


@pytest.mark.asyncio
async def test_recall_respects_score_threshold() -> None:
    """Low-score memories are filtered out."""
    mock_entry = MagicMock()
    mock_entry.content = "FAILURE: x\nCORRECTION: y"
    mock_entry.metadata_json = {"source": "correction_example"}

    mock_memory_svc = AsyncMock()
    mock_memory_svc.recall = AsyncMock(return_value=[(mock_entry, 0.1)])

    mock_db = AsyncMock()

    with (
        patch("app.core.scoped_db.get_system_db_context") as mock_db_ctx,
        patch("app.knowledge.embedding.get_embedding_provider"),
        patch(
            "app.ai.blueprints.correction_examples.MemoryService",
            return_value=mock_memory_svc,
            create=True,
        ),
    ):
        mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await recall_correction_examples("dark_mode", ["dark_mode: no support"], None)

    assert result == []
