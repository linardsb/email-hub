"""Extract, store, and surface failure patterns across agents.

When a blueprint run completes with QA failures, this module:
1. Extracts structured FailurePattern records from the run
2. Persists them as searchable semantic memory entries
3. Exports them as graph-ready markdown for Cognee ECL
4. Formats relevant patterns as agent-readable context blocks
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.ai.blueprints.audience_context import AudienceProfile
    from app.ai.blueprints.engine import BlueprintRun

logger = get_logger(__name__)

# Dataset name for failure pattern graph documents
FAILURE_PATTERN_DATASET = "failure_patterns"


class _AgentInfo(NamedTuple):
    """Handoff context for an agent, used during failure pattern extraction."""

    warnings: tuple[str, ...]
    decisions: tuple[str, ...]
    confidence: float | None


@dataclass(frozen=True)
class FailurePattern:
    """A structured failure record from a blueprint run."""

    agent_name: str
    qa_check: str
    client_ids: tuple[str, ...]
    description: str
    workaround: str = ""
    confidence: float | None = None
    run_id: str = ""
    blueprint_name: str = ""


# Map QA check names to the agent most likely responsible
_QA_CHECK_AGENT_MAP: dict[str, str] = {
    "dark_mode": "dark_mode",
    "fallback": "outlook_fixer",
    "css_support": "scaffolder",
    "html_validation": "scaffolder",
    "accessibility": "accessibility",
    "link_validation": "scaffolder",
    "spam_score": "content",
    "image_optimization": "scaffolder",
    "file_size": "code_reviewer",
    "brand_compliance": "scaffolder",
}


def _find_responsible_agent(qa_check: str, run: BlueprintRun) -> str | None:
    """Identify the agent most likely responsible for a QA failure.

    Uses a static mapping first, then falls back to the last agentic node
    in the handoff history.
    """
    if qa_check in _QA_CHECK_AGENT_MAP:
        return _QA_CHECK_AGENT_MAP[qa_check]

    # Fallback: last agent in the chain before QA gate
    for handoff in reversed(run._handoff_history):
        if handoff.agent_name:
            return handoff.agent_name

    return None


def extract_failure_patterns(
    run: BlueprintRun,
    blueprint_name: str,
    audience_profile: AudienceProfile | None = None,
) -> list[FailurePattern]:
    """Extract structured failure patterns from a completed blueprint run.

    Only produces patterns when QA failed -- successful runs don't generate
    failure patterns (they confirm existing patterns are resolved).
    """
    if run.qa_passed is not False or not run.qa_failures:
        return []

    client_ids: tuple[str, ...] = ()
    if audience_profile is not None:
        client_ids = tuple(audience_profile.client_ids)

    # Build agent -> context lookup from handoff history
    agent_context: dict[str, _AgentInfo] = {}
    for handoff in run._handoff_history:
        if handoff.agent_name:
            agent_context[handoff.agent_name] = _AgentInfo(
                warnings=handoff.warnings,
                decisions=handoff.decisions,
                confidence=handoff.confidence,
            )

    patterns: list[FailurePattern] = []

    for failure_line in run.qa_failures:
        # QA failures format: "check_name: description (score=X.X)"
        # or just "check_name: description"
        qa_check, _, description = failure_line.partition(":")
        qa_check = qa_check.strip()
        description = description.strip()

        if not qa_check:
            continue

        responsible_agent = _find_responsible_agent(qa_check, run)

        # Pull workaround hints from agent warnings/decisions
        workaround = ""
        confidence = None
        if responsible_agent and responsible_agent in agent_context:
            info = agent_context[responsible_agent]
            confidence = info.confidence
            relevant = [
                w
                for w in info.warnings
                if qa_check.replace("_", " ") in w.lower() or qa_check in w.lower()
            ]
            if relevant:
                workaround = "; ".join(relevant)
            elif info.decisions:
                workaround = "; ".join(info.decisions[:2])

        patterns.append(
            FailurePattern(
                agent_name=responsible_agent or "unknown",
                qa_check=qa_check,
                client_ids=client_ids,
                description=description or f"QA check '{qa_check}' failed",
                workaround=workaround,
                confidence=confidence,
                run_id=run.run_id,
                blueprint_name=blueprint_name,
            )
        )

    return patterns


def _format_pattern_for_memory(pattern: FailurePattern) -> str:
    """Format a failure pattern as searchable memory text.

    Structured so pgvector similarity search finds it when agents query
    for related client/check combinations.
    """
    parts = [
        f"[failure_pattern] Agent '{pattern.agent_name}' failed QA check "
        f"'{pattern.qa_check}' during blueprint '{pattern.blueprint_name}'.",
    ]

    if pattern.client_ids:
        clients = ", ".join(pattern.client_ids)
        parts.append(f"Target email clients: {clients}.")

    if pattern.description:
        parts.append(f"Issue: {pattern.description}")

    if pattern.workaround:
        parts.append(f"Agent context: {pattern.workaround}")

    if pattern.confidence is not None:
        parts.append(f"Agent confidence at failure: {pattern.confidence:.2f}.")

    text = " ".join(parts)
    # MemoryCreate.content has max_length=4000
    return text[:4000]


async def persist_failure_patterns(
    patterns: list[FailurePattern],
    project_id: int | None,
) -> None:
    """Store failure patterns as semantic memory entries.

    Each pattern becomes a separate memory entry tagged with:
    - memory_type="semantic" (durable, cross-agent searchable)
    - source="failure_pattern"
    - agent_type=pattern.agent_name (but searchable by ANY agent)

    Fire-and-forget: errors are logged but never propagated.
    """
    if not patterns:
        return

    try:
        from app.core.config import get_settings
        from app.core.database import get_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.schemas import MemoryCreate
        from app.memory.service import MemoryService

        stored = 0
        async with get_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            service = MemoryService(db, embedding_provider)

            for pattern in patterns:
                try:
                    content = _format_pattern_for_memory(pattern)
                    await service.store(
                        MemoryCreate(
                            agent_type=pattern.agent_name,
                            memory_type="semantic",
                            content=content,
                            project_id=project_id,
                            metadata={
                                "source": "failure_pattern",
                                "qa_check": pattern.qa_check,
                                "client_ids": list(pattern.client_ids),
                                "run_id": pattern.run_id,
                                "blueprint_name": pattern.blueprint_name,
                                "confidence": pattern.confidence,
                            },
                            is_evergreen=False,
                        ),
                    )
                    stored += 1
                except Exception:
                    logger.warning(
                        "failure_patterns.persist_single_failed",
                        qa_check=pattern.qa_check,
                        agent_name=pattern.agent_name,
                        exc_info=True,
                    )

        logger.info(
            "failure_patterns.persisted",
            count=stored,
            total=len(patterns),
            project_id=project_id,
        )
    except Exception:
        logger.warning(
            "failure_patterns.persist_failed",
            count=len(patterns),
            exc_info=True,
        )


def _format_pattern_for_graph(pattern: FailurePattern) -> str:
    """Format a failure pattern as structured markdown for Cognee ECL.

    Uses consistent entity naming so Cognee extracts graph triplets:
    Agent:scaffolder [failed_on] QACheck:dark_mode
    QACheck:dark_mode [affects_client] EmailClient:outlook_2016
    """
    lines = [
        f"# Failure Pattern: {pattern.agent_name} on {pattern.qa_check}",
        "",
        f"Agent {pattern.agent_name} failed the {pattern.qa_check} quality check.",
    ]

    if pattern.description:
        lines.append(f"Issue description: {pattern.description}")

    if pattern.client_ids:
        lines.append("")
        lines.append("## Affected Email Clients")
        for client_id in pattern.client_ids:
            lines.append(f"- {client_id}")

    if pattern.workaround:
        lines.append("")
        lines.append("## Known Context")
        lines.append(pattern.workaround)

    if pattern.confidence is not None:
        lines.append("")
        lines.append(f"Agent confidence at failure: {pattern.confidence:.2f}")

    lines.append("")
    lines.append(f"Source: blueprint run {pattern.run_id} ({pattern.blueprint_name})")

    return "\n".join(lines)


async def export_failure_patterns_to_graph(
    patterns: list[FailurePattern],
    project_id: int | None,
) -> None:
    """Export failure patterns as graph documents for Cognee ECL pipeline.

    Queued via Redis (same mechanism as outcome_logger.py).
    Fire-and-forget: errors logged, never propagated.
    """
    if not patterns:
        return

    try:
        from app.core.redis import get_redis

        documents: list[str] = []
        for pattern in patterns:
            documents.append(_format_pattern_for_graph(pattern))

        redis = await get_redis()
        payload = json.dumps(
            {
                "dataset_name": FAILURE_PATTERN_DATASET,
                "documents": documents,
                "project_id": project_id,
                "source": "failure_pattern_export",
            }
        )
        await redis.rpush("graph:documents:pending", payload)

        logger.info(
            "failure_patterns.graph_queued",
            count=len(patterns),
            project_id=project_id,
        )
    except Exception:
        logger.warning(
            "failure_patterns.graph_export_failed",
            count=len(patterns),
            exc_info=True,
        )


async def recall_failure_patterns(
    agent_name: str,
    client_ids: tuple[str, ...],
    project_id: int | None,
    limit: int = 5,
) -> str:
    """Recall failure patterns relevant to this agent and target clients.

    Searches semantic memory for failure patterns matching the agent's domain
    AND the target client audience. Returns formatted context block for
    injection into the agent's system prompt.
    """
    if not client_ids:
        return ""

    try:
        from app.core.config import get_settings
        from app.core.database import get_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.service import MemoryService

        # Build a query that captures agent + client combination
        client_names = ", ".join(client_ids[:5])  # Cap query length
        query = f"failure_pattern {agent_name} QA failure email client {client_names}"

        async with get_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            service = MemoryService(db, embedding_provider)
            memories = await service.recall(
                query,
                project_id=project_id,
                memory_type="semantic",
                limit=limit * 2,  # Over-fetch, then filter
            )

        # Filter to failure_pattern source entries with matching clients
        relevant: list[str] = []
        for memory, score in memories:
            if score < 0.3:
                continue
            metadata: dict[str, object] = memory.metadata_json or {}
            if metadata.get("source") != "failure_pattern":
                continue
            # Check client overlap
            raw_clients: object = metadata.get("client_ids", [])
            pattern_clients: set[object] = (
                set(raw_clients) if isinstance(raw_clients, list) else set()  # pyright: ignore[reportUnknownArgumentType]
            )
            if pattern_clients and not pattern_clients.intersection(client_ids):
                continue
            relevant.append(memory.content)
            if len(relevant) >= limit:
                break

        if not relevant:
            return ""

        return format_failure_pattern_context(relevant)

    except Exception:
        logger.debug(
            "failure_patterns.recall_failed",
            agent_name=agent_name,
            exc_info=True,
        )
        return ""


def format_failure_pattern_context(patterns: list[str]) -> str:
    """Format recalled failure patterns as an agent-readable context block."""
    parts = [
        "--- CROSS-AGENT FAILURE PATTERNS ---",
        "The following failure patterns were observed in previous runs "
        "targeting similar email clients. Use these to avoid repeating "
        "known issues:",
        "",
    ]
    for i, pattern in enumerate(patterns, 1):
        cleaned = pattern.replace("[failure_pattern] ", "")
        parts.append(f"{i}. {cleaned}")
        parts.append("")

    return "\n".join(parts)
