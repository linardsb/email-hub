"""Cross-agent insight persistence.

Defines the ``AgentInsight`` record and ``persist_insights`` — stores insights
as semantic memory entries, one per target agent. Consumed by the design-sync
converter trace pipeline (``app/design_sync/traces/converter.py``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.core.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

logger = get_logger(__name__)

InsightCategory = Literal[
    "color", "layout", "typography", "dark_mode", "accessibility", "mso", "conversion"
]

# Max content length for MemoryCreate
_MAX_CONTENT_LENGTH = 4000

# Evidence count threshold for marking insights as evergreen
_EVERGREEN_THRESHOLD = 5


@dataclass(frozen=True)
class AgentInsight:
    """A cross-agent learning extracted from a blueprint run."""

    source_agent: str
    target_agents: tuple[str, ...]
    client_ids: tuple[str, ...]
    insight: str
    category: InsightCategory
    confidence: float
    evidence_count: int
    first_seen: datetime
    last_seen: datetime


def _compute_dedup_hash(
    source_agent: str,
    category: InsightCategory,
    client_ids: tuple[str, ...],
    insight: str,
) -> str:
    """Compute a deterministic hash for insight deduplication."""
    key = f"{source_agent}:{category}:{','.join(sorted(client_ids))}:{insight[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _format_insight_for_memory(insight: AgentInsight) -> str:
    """Format an insight as searchable memory text."""
    parts = [
        f"[cross_agent_insight] From {insight.source_agent}: {insight.insight}",
    ]
    if insight.client_ids:
        parts.append(f"Email clients: {', '.join(insight.client_ids)}.")
    parts.append(f"Category: {insight.category}. Confidence: {insight.confidence:.2f}.")
    text = " ".join(parts)
    return text[:_MAX_CONTENT_LENGTH]


async def persist_insights(
    insights: list[AgentInsight],
    project_id: int | None,
) -> int:
    """Store insights as semantic memory entries, one per target agent.

    Per-item try/except so one failure doesn't block the rest.
    Deduplication happens at recall time via dedup_hash metadata.
    """
    if not insights:
        return 0

    try:
        from app.core.config import get_settings
        from app.core.scoped_db import get_system_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.schemas import MemoryCreate
        from app.memory.service import MemoryService

        stored = 0
        async with get_system_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            service = MemoryService(db, embedding_provider)

            for insight in insights:
                content = _format_insight_for_memory(insight)
                dedup = _compute_dedup_hash(
                    insight.source_agent,
                    insight.category,
                    insight.client_ids,
                    insight.insight,
                )
                metadata: dict[str, Any] = {
                    "source": "cross_agent_insight",
                    "source_agent": insight.source_agent,
                    "client_ids": list(insight.client_ids),
                    "category": insight.category,
                    "evidence_count": insight.evidence_count,
                    "dedup_hash": dedup,
                }

                for target in insight.target_agents:
                    try:
                        await service.store(
                            MemoryCreate(
                                agent_type=target,
                                memory_type="semantic",
                                content=content,
                                project_id=project_id,
                                metadata=metadata,
                                is_evergreen=insight.evidence_count >= _EVERGREEN_THRESHOLD,
                            ),
                        )
                        stored += 1
                    except Exception:
                        logger.warning(
                            "insights.persist_single_failed",
                            source_agent=insight.source_agent,
                            target_agent=target,
                            exc_info=True,
                        )

        logger.info(
            "insights.persisted",
            count=stored,
            total=len(insights),
            project_id=project_id,
        )
        return stored

    except Exception:
        logger.warning(
            "insights.persist_failed",
            count=len(insights),
            exc_info=True,
        )
        return 0
