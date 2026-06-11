"""Correction Few-Shot Injection — store and recall successful corrections.

When a self-correction round succeeds (fixer runs → QA passes), stores a
compact correction example. On future correction rounds, recalls 1-2
relevant examples and injects as few-shot context.

Enabled via BLUEPRINT__CORRECTION_EXAMPLES_ENABLED=true (default: false).
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_CORRECTION_SOURCE = "correction_example"


async def store_correction_example(
    agent_name: str,
    check_name: str,
    failure_description: str,
    correction_summary: str,
    project_id: int | None,
    run_id: str,
) -> None:
    """Store a successful correction as procedural memory. Fire-and-forget.

    Uses existing MemoryService with memory_type="procedural" and
    metadata.source="correction_example".
    """
    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.schemas import MemoryCreate
    from app.memory.service import MemoryService

    content = (
        f"FAILURE: {failure_description}\n"
        f"CORRECTION: {correction_summary}\n"
        f"AGENT: {agent_name}\n"
        f"CHECK: {check_name}"
    )

    async with get_system_db_context() as db:
        embedding_provider = get_embedding_provider(get_settings())
        memory_service = MemoryService(db, embedding_provider)
        await memory_service.store(
            MemoryCreate(
                agent_type=agent_name,
                memory_type="procedural",
                content=content,
                project_id=project_id,
                metadata={
                    "source": _CORRECTION_SOURCE,
                    "check_name": check_name,
                    "run_id": run_id,
                },
            )
        )
        await db.commit()

    logger.debug(
        "blueprint.correction_example_stored",
        agent=agent_name,
        check=check_name,
        run_id=run_id,
    )


async def recall_correction_examples(
    agent_name: str,
    qa_failures: list[str],
    project_id: int | None,
    limit: int = 2,
) -> list[str]:
    """Recall 1-2 correction examples relevant to current failures.

    Queries procedural memories with source="correction_example",
    filtered by similarity to the current failure descriptions.
    Returns formatted content strings.
    """
    if not qa_failures:
        return []

    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.service import MemoryService

    query = f"agent:{agent_name} failures: {'; '.join(qa_failures[:5])}"

    try:
        async with get_system_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            memory_service = MemoryService(db, embedding_provider)
            memories = await memory_service.recall(
                query,
                project_id=project_id,
                agent_type=agent_name,
                memory_type="procedural",
                limit=limit * 3,  # over-fetch, filter by source below
            )

        results: list[str] = []
        for entry, score in memories:
            if score < 0.3:
                continue
            meta: dict[str, Any] = entry.metadata_json or {}
            if meta.get("source") != _CORRECTION_SOURCE:
                continue
            results.append(entry.content)
            if len(results) >= limit:
                break

        return results
    except Exception:
        logger.debug(
            "blueprint.correction_recall_failed",
            agent=agent_name,
            exc_info=True,
        )
        return []


def format_correction_examples(examples: list[str]) -> str:
    """Format correction examples as a context block for agent prompts."""
    if not examples:
        return ""
    lines = ["## Prior Successful Corrections", ""]
    for i, example in enumerate(examples, 1):
        lines.append(f"### Example {i}")
        lines.append(example)
        lines.append("")
    return "\n".join(lines)
