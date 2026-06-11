"""Bridge between blueprint handoffs and the agent memory system.

Provides a callback that auto-stores each agent's handoff decisions
as episodic memories, enabling cross-agent knowledge sharing across
sessions and blueprint runs.
"""

from app.ai.blueprints.protocols import AgentHandoff
from app.core.logging import get_logger

logger = get_logger(__name__)


def format_handoff_content(handoff: AgentHandoff, run_id: str) -> str:
    """Format a handoff as a memory-friendly text block.

    Produces a compact but searchable summary of what the agent did,
    what it decided, and what warnings it raised.
    """
    parts = [f"[blueprint:{run_id}] Agent '{handoff.agent_name}' completed."]

    if handoff.decisions:
        parts.append(f"Decisions: {'; '.join(handoff.decisions)}")

    if handoff.warnings:
        parts.append(f"Warnings: {'; '.join(handoff.warnings)}")

    if handoff.component_refs:
        parts.append(f"Components: {', '.join(handoff.component_refs)}")

    if handoff.confidence is not None:
        parts.append(f"Confidence: {handoff.confidence:.2f}")

    return " ".join(parts)


async def persist_handoff_to_memory(
    handoff: AgentHandoff,
    run_id: str,
    project_id: int | None,
) -> None:
    """Store a handoff as an episodic memory entry.

    This is designed to be used as the ``on_handoff`` callback in
    :class:`BlueprintEngine`.  It creates a DB session internally
    so that memory writes don't interfere with the engine's own
    transaction lifecycle.

    Args:
        handoff: The structured handoff from an agentic node.
        run_id: Blueprint run identifier for traceability.
        project_id: Project scope (None for global memory).
    """
    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.schemas import MemoryCreate
    from app.memory.service import MemoryService

    content = format_handoff_content(handoff, run_id)

    async with get_system_db_context() as db:
        embedding_provider = get_embedding_provider(get_settings())
        service = MemoryService(db, embedding_provider)

        await service.store(
            MemoryCreate(
                agent_type=handoff.agent_name,
                memory_type="episodic",
                content=content,
                project_id=project_id,
                metadata={
                    "source": "blueprint_handoff",
                    "run_id": run_id,
                    "confidence": handoff.confidence,
                    "component_refs": list(handoff.component_refs),
                },
            )
        )

    logger.info(
        "blueprint.handoff_persisted",
        agent=handoff.agent_name,
        run_id=run_id,
        project_id=project_id,
    )
