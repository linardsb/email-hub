"""Background poller that drains blueprint outcomes from Redis into Cognee graph."""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.core.poller import DataPoller

logger = get_logger(__name__)

# Must match the key in outcome_logger.py
OUTCOME_QUEUE_KEY = "blueprint:outcomes:pending"

# Max outcomes to process per poll cycle (prevent unbounded work)
BATCH_SIZE = 10


class OutcomeGraphPoller(DataPoller):
    """Polls Redis for queued blueprint outcomes and feeds them into Cognee.

    Runs on a 30-second interval with leader election to prevent duplicates.
    Processes up to BATCH_SIZE outcomes per cycle.
    """

    def __init__(self) -> None:
        super().__init__(
            name="outcome_graph",
            interval_seconds=30,
            leader_lock_ttl=60,
        )

    async def fetch(self) -> list[dict[str, Any]]:
        """Pop pending outcomes from Redis queue."""
        from app.core.redis import get_redis

        redis = await get_redis()
        outcomes: list[dict[str, Any]] = []

        for _ in range(BATCH_SIZE):
            raw = await redis.lpop(OUTCOME_QUEUE_KEY)
            if raw is None:
                break
            try:
                outcomes.append(json.loads(str(raw)))  # pyright: ignore[reportUnknownArgumentType]
            except json.JSONDecodeError:
                logger.warning(
                    "blueprint.outcome_parse_failed",
                    raw=str(raw)[:200],  # pyright: ignore[reportUnknownArgumentType]
                )

        return outcomes

    async def enrich(self, raw: object) -> list[dict[str, Any]]:
        """Pass through — outcomes are already formatted by outcome_logger."""
        return raw  # type: ignore[return-value]

    async def store(self, data: object) -> None:
        """Feed outcome texts into Cognee via graph provider."""
        outcomes: list[dict[str, Any]] = data  # type: ignore[assignment]
        if not outcomes:
            return

        try:
            from app.core.config import get_settings
            from app.knowledge.graph.cognee_provider import CogneeGraphProvider

            provider = CogneeGraphProvider(get_settings())
        except Exception:
            logger.debug(
                "blueprint.outcome_graph_unavailable",
                reason="Cognee not configured or import failed",
            )
            return

        # Group outcomes by project for scoped dataset ingestion
        by_project: dict[str, list[str]] = {}
        for outcome in outcomes:
            project_id = outcome.get("project_id")
            dataset = f"project_{project_id}" if project_id else "global"
            by_project.setdefault(dataset, []).append(outcome["outcome_text"])

        for dataset_name, texts in by_project.items():
            try:
                await provider.add_documents(texts, dataset_name=dataset_name)
                logger.info(
                    "blueprint.outcomes_ingested",
                    dataset=dataset_name,
                    count=len(texts),
                )
            except Exception:
                logger.warning(
                    "blueprint.outcome_graph_ingest_failed",
                    dataset=dataset_name,
                    count=len(texts),
                    exc_info=True,
                )
