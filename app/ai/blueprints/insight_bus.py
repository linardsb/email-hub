"""Cross-agent insight propagation.

Extracts learnings from completed blueprint runs and routes them to agents
that can benefit:
1. Extracts insights from QA fix patterns + handoff learnings + low-confidence decisions
2. Persists as semantic memory entries tagged per target agent
3. Recalls relevant insights for injection into agentic node context
4. Formats as agent-readable context blocks (LAYER 17)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.ai.blueprints.audience_context import AudienceProfile
    from app.ai.blueprints.engine import BlueprintRun

logger = get_logger(__name__)

InsightCategory = Literal[
    "color", "layout", "typography", "dark_mode", "accessibility", "mso", "conversion"
]

# Map QA check names → insight categories
_QA_CHECK_CATEGORY_MAP: dict[str, InsightCategory] = {
    "dark_mode": "dark_mode",
    "fallback": "mso",
    "css_support": "layout",
    "html_validation": "layout",
    "accessibility": "accessibility",
    "link_validation": "layout",
    "spam_score": "typography",
    "image_optimization": "layout",
    "file_size": "layout",
    "brand_compliance": "color",
}

# Max content length for MemoryCreate
_MAX_CONTENT_LENGTH = 4000

# Max total chars for formatted insight context block
_MAX_CONTEXT_LENGTH = 800

# Confidence threshold below which advisory insights are generated
_LOW_CONFIDENCE_THRESHOLD = 0.7

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


def _category_for_qa_check(qa_check: str) -> InsightCategory:
    """Map a QA check name to an insight category."""
    return _QA_CHECK_CATEGORY_MAP.get(qa_check, "layout")


def extract_insights(
    run: BlueprintRun,
    blueprint_name: str,
    audience_profile: AudienceProfile | None = None,
) -> list[AgentInsight]:
    """Extract cross-agent insights from a completed blueprint run.

    Sources:
    - QA failures that were fixed (root-cause → fixer insight)
    - Handoff learnings declared by agents
    - Low-confidence handoffs (advisory insights)
    """
    from app.ai.blueprints.failure_patterns import _QA_CHECK_AGENT_MAP

    now = datetime.now(UTC)
    client_ids: tuple[str, ...] = ()
    if audience_profile is not None:
        client_ids = tuple(audience_profile.client_ids)

    seen_hashes: dict[str, AgentInsight] = {}

    # --- Source 1: QA failures that were fixed ---
    # A "fixed" failure is one present in previous_qa_failure_details but absent
    # from the final qa_failure_details (meaning an agent corrected it).
    if run.previous_qa_failure_details:
        current_checks = {sf.check_name for sf in run.qa_failure_details}
        for prev_sf in run.previous_qa_failure_details:
            if prev_sf.check_name in current_checks:
                continue  # Still failing — not fixed

            root_cause_agent = _QA_CHECK_AGENT_MAP.get(prev_sf.check_name)
            fixer_agent = prev_sf.suggested_agent or "unknown"

            if not root_cause_agent or root_cause_agent == fixer_agent:
                continue  # Same agent — no cross-agent learning

            insight_text = (
                f"[{blueprint_name}] When building for "
                f"{', '.join(client_ids) or 'any clients'}, "
                f"avoid patterns that cause '{prev_sf.check_name}' failures — "
                f"{fixer_agent} had to correct: {prev_sf.details[:200]}"
            )

            category = _category_for_qa_check(prev_sf.check_name)
            targets = tuple(dict.fromkeys([root_cause_agent, "code_reviewer"]))
            dedup = _compute_dedup_hash(fixer_agent, category, client_ids, insight_text)

            insight = AgentInsight(
                source_agent=fixer_agent,
                target_agents=targets,
                client_ids=client_ids,
                insight=insight_text,
                category=category,
                confidence=prev_sf.score,
                evidence_count=1,
                first_seen=now,
                last_seen=now,
            )
            seen_hashes[dedup] = insight

    # --- Source 2: Handoff learnings ---
    for handoff in run._handoff_history:
        if not handoff.learnings:
            continue
        for learning in handoff.learnings:
            handoff_category: InsightCategory = "layout"
            # Infer category from learning text
            lower = learning.lower()
            if any(w in lower for w in ("color", "palette", "hex", "#")):
                handoff_category = "color"
            elif any(w in lower for w in ("dark mode", "dark-mode", "prefers-color")):
                handoff_category = "dark_mode"
            elif any(w in lower for w in ("font", "typograph", "line-height")):
                handoff_category = "typography"
            elif any(w in lower for w in ("mso", "outlook", "vml")):
                handoff_category = "mso"
            elif any(w in lower for w in ("aria", "alt=", "accessibility", "screen reader")):
                handoff_category = "accessibility"

            # Target all agents except the source
            targets = tuple(
                a
                for a in (
                    "scaffolder",
                    "dark_mode",
                    "outlook_fixer",
                    "accessibility",
                    "code_reviewer",
                )
                if a != handoff.agent_name
            )
            dedup = _compute_dedup_hash(handoff.agent_name, handoff_category, client_ids, learning)
            if dedup in seen_hashes:
                continue

            seen_hashes[dedup] = AgentInsight(
                source_agent=handoff.agent_name,
                target_agents=targets,
                client_ids=client_ids,
                insight=learning,
                category=handoff_category,
                confidence=handoff.confidence or 0.5,
                evidence_count=1,
                first_seen=now,
                last_seen=now,
            )

    # --- Source 3: Low-confidence handoffs ---
    for handoff in run._handoff_history:
        if (
            handoff.confidence is not None
            and handoff.confidence < _LOW_CONFIDENCE_THRESHOLD
            and handoff.agent_name
        ):
            insight_text = (
                f"Low confidence ({handoff.confidence:.2f}) from {handoff.agent_name} "
                f"on {', '.join(client_ids) or 'unspecified clients'}. "
                f"Decisions: {'; '.join(handoff.decisions[:2]) or 'none recorded'}"
            )
            category = "layout"
            targets = ("code_reviewer",)
            dedup = _compute_dedup_hash(handoff.agent_name, category, client_ids, insight_text)
            if dedup not in seen_hashes:
                seen_hashes[dedup] = AgentInsight(
                    source_agent=handoff.agent_name,
                    target_agents=targets,
                    client_ids=client_ids,
                    insight=insight_text,
                    category=category,
                    confidence=handoff.confidence,
                    evidence_count=1,
                    first_seen=now,
                    last_seen=now,
                )

    return list(seen_hashes.values())


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


async def recall_insights(
    agent_name: str,
    client_ids: tuple[str, ...] | None,
    project_id: int | None,
    limit: int = 5,
) -> list[AgentInsight]:
    """Recall cross-agent insights relevant to this agent and clients.

    Over-fetches then deduplicates by dedup_hash, keeping the highest
    evidence_count entry per hash.
    """
    try:
        from app.core.config import get_settings
        from app.core.scoped_db import get_system_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.service import MemoryService

        client_names = ", ".join((client_ids or ())[:5])
        query = f"cross_agent_insight {agent_name} email rendering {client_names}"

        async with get_system_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            service = MemoryService(db, embedding_provider)
            memories = await service.recall(
                query,
                project_id=project_id,
                agent_type=agent_name,
                memory_type="semantic",
                limit=limit * 2,
            )

        # Filter to cross_agent_insight source, deduplicate by hash
        best_per_hash: dict[str, tuple[AgentInsight, float]] = {}
        for memory, score in memories:
            if score < 0.3:
                continue
            meta: dict[str, object] = memory.metadata_json or {}
            if meta.get("source") != "cross_agent_insight":
                continue

            dedup_hash = str(meta.get("dedup_hash", ""))
            evidence_count = int(meta.get("evidence_count", 1))  # type: ignore[call-overload]
            raw_clients = meta.get("client_ids", [])
            pattern_clients: list[str] = (
                [str(c) for c in raw_clients]  # pyright: ignore[reportUnknownArgumentType,reportUnknownVariableType]
                if isinstance(raw_clients, list)
                else []
            )

            # Check client overlap if requested
            if client_ids and pattern_clients and not set(pattern_clients).intersection(client_ids):
                continue

            insight = AgentInsight(
                source_agent=str(meta.get("source_agent", "unknown")),
                target_agents=(agent_name,),
                client_ids=tuple(pattern_clients),
                insight=memory.content,
                category=str(meta.get("category", "layout")),  # type: ignore[arg-type]
                confidence=score,
                evidence_count=evidence_count,
                first_seen=datetime.fromisoformat(str(memory.created_at)),
                last_seen=datetime.fromisoformat(str(memory.updated_at)),
            )

            existing = best_per_hash.get(dedup_hash)
            if existing is None or evidence_count > existing[0].evidence_count:
                best_per_hash[dedup_hash] = (insight, score)

        # Sort by evidence_count * similarity_score descending
        ranked = sorted(
            best_per_hash.values(),
            key=lambda pair: pair[0].evidence_count * pair[1],
            reverse=True,
        )
        return [insight for insight, _score in ranked[:limit]]

    except Exception:
        logger.debug(
            "insights.recall_failed",
            agent_name=agent_name,
            exc_info=True,
        )
        return []


def format_insight_context(insights: list[AgentInsight]) -> str:
    """Format recalled insights as an agent-readable context block.

    Capped at ~800 chars total, truncating least-confident insights.
    """
    if not insights:
        return ""

    # Sort by confidence descending so truncation drops least confident
    sorted_insights = sorted(insights, key=lambda i: i.confidence, reverse=True)

    parts = ["--- CROSS-AGENT INSIGHTS ---"]
    total_len = len(parts[0])

    for insight in sorted_insights:
        clients = ", ".join(insight.client_ids[:3]) or "all clients"
        line = (
            f"From {insight.source_agent} ({insight.evidence_count}x, {clients}):\n"
            f"  {insight.insight[:200]}"
        )
        if total_len + len(line) + 1 > _MAX_CONTEXT_LENGTH:
            break
        parts.append(line)
        total_len += len(line) + 1

    return "\n".join(parts)
