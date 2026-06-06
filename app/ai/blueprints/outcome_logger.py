"""Blueprint outcome logging — formats run outcomes and queues for graph ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.ai.blueprints.audience_context import AudienceProfile
    from app.ai.blueprints.engine import BlueprintRun

logger = get_logger(__name__)

# Redis key for the outcome queue
OUTCOME_QUEUE_KEY = "blueprint:outcomes:pending"


def format_outcome_text(
    run: BlueprintRun,
    blueprint_name: str,
) -> str:
    """Convert a completed BlueprintRun into natural language for Cognee ECL pipeline.

    Produces narrative text that Cognee will decompose into entities and relationships
    (e.g., agent -> failed_on -> QA check, agent -> recovered_by -> fixer agent).
    """
    lines: list[str] = [
        f"Blueprint run '{blueprint_name}' completed with status: {run.status}.",
    ]

    # Agents involved
    agents = [h.agent_name for h in run._handoff_history]
    if agents:
        lines.append(f"Agents involved: {', '.join(agents)}.")

    # QA result
    if run.qa_passed is True:
        lines.append("QA gate passed — all checks succeeded.")
    elif run.qa_passed is False:
        lines.append(f"QA gate failed on: {', '.join(run.qa_failures)}.")

    # Recovery path (iterations > 1 on any node = self-correction happened)
    retried = {k: v for k, v in run.iteration_counts.items() if v > 1}
    if retried:
        parts = [f"{node} ({count} iterations)" for node, count in retried.items()]
        lines.append(f"Self-correction applied: {', '.join(parts)}.")

    # Key decisions and warnings from handoffs
    for handoff in run._handoff_history:
        if handoff.decisions:
            lines.append(f"{handoff.agent_name} decisions: {'; '.join(handoff.decisions)}.")
        if handoff.warnings:
            lines.append(f"{handoff.agent_name} warnings: {'; '.join(handoff.warnings)}.")
        if handoff.confidence is not None:
            lines.append(f"{handoff.agent_name} confidence: {handoff.confidence:.2f}.")

    # Token usage summary
    total = run.model_usage.get("total_tokens", 0)
    if total > 0:
        lines.append(f"Total token usage: {total:,}.")

    return "\n".join(lines)


def build_outcome_payload(
    run: BlueprintRun,
    blueprint_name: str,
    project_id: int | None,
) -> dict[str, object]:
    """Build JSON-serializable payload for the Redis outcome queue."""
    agents = [h.agent_name for h in run._handoff_history]
    return {
        "run_id": run.run_id,
        "blueprint_name": blueprint_name,
        "project_id": project_id,
        "status": run.status,
        "qa_passed": run.qa_passed,
        "qa_failures": run.qa_failures,
        "agents_involved": agents,
        "outcome_text": format_outcome_text(run, blueprint_name),
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def queue_outcome_for_graph(
    run: BlueprintRun,
    blueprint_name: str,
    project_id: int | None,
) -> None:
    """Push a blueprint outcome onto the Redis queue for async graph ingestion.

    Fire-and-forget: errors are logged but never propagated.
    """
    try:
        from app.core.redis import get_redis

        payload = build_outcome_payload(run, blueprint_name, project_id)
        redis = await get_redis()
        await redis.rpush(OUTCOME_QUEUE_KEY, json.dumps(payload))
        logger.info(
            "blueprint.outcome_queued",
            run_id=run.run_id,
            blueprint_name=blueprint_name,
            project_id=project_id,
        )
    except Exception:
        logger.warning(
            "blueprint.outcome_queue_failed",
            run_id=run.run_id,
            exc_info=True,
        )


async def persist_outcome_to_memory(
    run: BlueprintRun,
    blueprint_name: str,
    project_id: int | None,
) -> None:
    """Store a condensed outcome summary in the memory system (pgvector).

    Stored as ``semantic`` memory so agents can recall patterns like
    "common Scaffolder failures" via similarity search.
    Fire-and-forget: errors are logged but never propagated.
    """
    try:
        from app.core.config import get_settings
        from app.core.database import get_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.schemas import MemoryCreate
        from app.memory.service import MemoryService

        outcome_text = format_outcome_text(run, blueprint_name)

        # Determine the primary agent (first in chain)
        primary_agent = run._handoff_history[0].agent_name if run._handoff_history else "blueprint"

        async with get_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            service = MemoryService(db, embedding_provider)

            await service.store(
                MemoryCreate(
                    agent_type=primary_agent,
                    memory_type="semantic",
                    content=outcome_text,
                    project_id=project_id,
                    metadata={
                        "source": "blueprint_outcome",
                        "run_id": run.run_id,
                        "blueprint_name": blueprint_name,
                        "status": run.status,
                        "qa_passed": run.qa_passed,
                        "qa_failures": run.qa_failures,
                        "agents_involved": [h.agent_name for h in run._handoff_history],
                    },
                    is_evergreen=False,
                ),
            )

        logger.info(
            "blueprint.outcome_memory_stored",
            run_id=run.run_id,
            project_id=project_id,
            agent_type=primary_agent,
        )
    except Exception:
        logger.warning(
            "blueprint.outcome_memory_failed",
            run_id=run.run_id,
            exc_info=True,
        )


async def extract_and_store_failure_patterns(
    run: BlueprintRun,
    blueprint_name: str,
    project_id: int | None,
    audience_profile: AudienceProfile | None = None,
) -> None:
    """Extract failure patterns from a completed run and store for cross-agent discovery.

    Fire-and-forget: errors are logged but never propagated.
    """
    try:
        from app.ai.blueprints.failure_patterns import (
            export_failure_patterns_to_graph,
            extract_failure_patterns,
            persist_failure_patterns,
        )

        patterns = extract_failure_patterns(run, blueprint_name, audience_profile)
        if not patterns:
            return

        # Dual persistence: memory (pgvector) + graph (Cognee)
        await persist_failure_patterns(patterns, project_id)
        await export_failure_patterns_to_graph(patterns, project_id)

        logger.info(
            "failure_patterns.extracted",
            count=len(patterns),
            run_id=run.run_id,
            blueprint_name=blueprint_name,
        )
    except Exception:
        logger.warning(
            "failure_patterns.extraction_failed",
            run_id=run.run_id,
            exc_info=True,
        )


async def extract_and_store_insights(
    run: BlueprintRun,
    blueprint_name: str,
    audience_profile: AudienceProfile | None,
    project_id: int | None,
) -> int:
    """Extract cross-agent insights from a completed run and persist.

    Fire-and-forget: errors are logged but never propagated.
    """
    try:
        from app.ai.blueprints.insight_bus import extract_insights, persist_insights

        insights = extract_insights(run, blueprint_name, audience_profile)
        if not insights:
            return 0

        count = await persist_insights(insights, project_id)
        run.insights_extracted = count
        return count
    except Exception:
        logger.warning(
            "insights.extraction_failed",
            run_id=run.run_id,
            exc_info=True,
        )
        return 0
