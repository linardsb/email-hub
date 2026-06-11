"""Judge Verdict Aggregation → Prompt Patching.

Aggregates inline judge verdicts over time. When a criterion has a low pass
rate, auto-generates a targeted instruction and injects it into the agent's
context as a "prompt patch".

Enabled via BLUEPRINT__JUDGE_AGGREGATION_ENABLED=true (default: false).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.agents.evals.judges.schemas import JudgeVerdict
from app.core.logging import get_logger

logger = get_logger(__name__)

PASS_RATE_THRESHOLD = 0.70
MIN_VERDICT_SAMPLES = 5
_VERDICT_SOURCE = "judge_verdict"


@dataclass(frozen=True)
class PromptPatch:
    """A targeted instruction for an underperforming criterion."""

    agent_name: str
    criterion: str
    pass_rate: float
    instruction: str
    sample_count: int


async def persist_judge_verdict(
    verdict: JudgeVerdict,
    project_id: int | None,
    run_id: str,
) -> None:
    """Store each CriterionResult as a semantic memory entry. Fire-and-forget.

    Each criterion result is stored separately so aggregation can group by criterion.
    """
    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.schemas import MemoryCreate
    from app.memory.service import MemoryService

    async with get_system_db_context() as db:
        embedding_provider = get_embedding_provider(get_settings())
        memory_service = MemoryService(db, embedding_provider)

        for cr in verdict.criteria_results:
            content = (
                f"agent={verdict.agent} criterion={cr.criterion} "
                f"passed={cr.passed} reasoning={cr.reasoning[:200]}"
            )
            await memory_service.store(
                MemoryCreate(
                    agent_type=verdict.agent,
                    memory_type="semantic",
                    content=content,
                    project_id=project_id,
                    metadata={
                        "source": _VERDICT_SOURCE,
                        "agent": verdict.agent,
                        "criterion": cr.criterion,
                        "passed": cr.passed,
                        "run_id": run_id,
                    },
                )
            )

        await db.commit()

    logger.debug(
        "blueprint.judge_verdicts_persisted",
        agent=verdict.agent,
        criteria_count=len(verdict.criteria_results),
        run_id=run_id,
    )


async def aggregate_verdicts(
    agent_name: str,
    project_id: int | None,
    lookback_limit: int = 50,
) -> list[PromptPatch]:
    """Query recent judge verdicts and compute per-criterion pass rates.

    Returns PromptPatch for criteria below PASS_RATE_THRESHOLD with
    >= MIN_VERDICT_SAMPLES samples.
    """
    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.service import MemoryService

    try:
        async with get_system_db_context() as db:
            embedding_provider = get_embedding_provider(get_settings())
            memory_service = MemoryService(db, embedding_provider)

            # Recall recent judge verdict memories for this agent
            memories = await memory_service.recall(
                f"agent={agent_name} judge verdict",
                project_id=project_id,
                agent_type=agent_name,
                memory_type="semantic",
                limit=lookback_limit,
            )

        # Group by criterion
        criterion_stats: dict[str, dict[str, int]] = {}
        for entry, score in memories:
            if score < 0.2:
                continue
            meta: dict[str, Any] = entry.metadata_json or {}
            if meta.get("source") != _VERDICT_SOURCE:
                continue
            criterion = str(meta.get("criterion", ""))
            if not criterion:
                continue
            if criterion not in criterion_stats:
                criterion_stats[criterion] = {"passed": 0, "total": 0}
            criterion_stats[criterion]["total"] += 1
            if meta.get("passed"):
                criterion_stats[criterion]["passed"] += 1

        patches: list[PromptPatch] = []
        for criterion, stats in criterion_stats.items():
            total = stats["total"]
            if total < MIN_VERDICT_SAMPLES:
                continue
            pass_rate = stats["passed"] / total
            if pass_rate < PASS_RATE_THRESHOLD:
                instruction = (
                    f"IMPORTANT: Your output frequently fails the '{criterion}' quality criterion "
                    f"(pass rate: {pass_rate:.0%} over {total} recent runs). "
                    f"Pay extra attention to this area."
                )
                patches.append(
                    PromptPatch(
                        agent_name=agent_name,
                        criterion=criterion,
                        pass_rate=pass_rate,
                        instruction=instruction,
                        sample_count=total,
                    )
                )

        return patches
    except Exception:
        logger.debug(
            "blueprint.judge_aggregation_failed",
            agent=agent_name,
            exc_info=True,
        )
        return []


def format_prompt_patches(patches: list[PromptPatch]) -> str:
    """Format prompt patches as a context block for agent prompts."""
    if not patches:
        return ""
    lines = ["## Quality Focus Areas", ""]
    for patch in patches:
        lines.append(f"- {patch.instruction}")
    lines.append("")
    return "\n".join(lines)
