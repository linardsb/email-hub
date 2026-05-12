"""Background poller for rendering change detection."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.poller import DataPoller
from app.core.redis import get_redis
from app.knowledge.ontology.change_detector import (
    DetectionResult,
    RenderingChange,
    RenderingChangeDetector,
)

logger = get_logger(__name__)

_REDIS_BASELINES_KEY = "change_detection:baselines"
_REDIS_BASELINES_TTL = 60 * 60 * 24 * 90  # 90 days
_REDIS_LAST_RUN_KEY = "change_detection:last_run"


class RenderingChangePoller(DataPoller):
    """Weekly poller that detects email client rendering changes."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            name="rendering-change-detector",
            interval_seconds=settings.change_detection.interval_hours * 3600,
            leader_lock_ttl=600,  # 10 min — rendering is slow
        )
        self._detector = RenderingChangeDetector()

    async def fetch(self) -> object:
        """Load baselines from Redis and run change detection."""
        baselines = await self._load_baselines()
        result, new_baselines = await self._detector.detect_changes(
            baselines=baselines,
        )
        return {"result": result, "new_baselines": new_baselines}

    async def store(self, data: object) -> None:
        """Persist updated baselines and store changes in knowledge base."""
        if data is None:
            return

        payload: dict[str, object] = data  # type: ignore[assignment]
        result: DetectionResult = payload["result"]  # type: ignore[assignment]
        new_baselines: dict[str, bytes] = payload["new_baselines"]  # type: ignore[assignment]

        # Persist updated baselines
        await self._save_baselines(new_baselines)

        # Store changes in knowledge base
        if result.changes:
            await self._store_changes_as_knowledge(result.changes)

        # Save last run metadata
        await self._save_last_run(result)

        logger.info(
            "change_detection.run_completed",
            changes=len(result.changes),
            templates=result.templates_checked,
            clients=result.clients_checked,
            baselines_created=result.baselines_created,
            errors=result.errors,
        )

    async def _store_changes_as_knowledge(self, changes: list[RenderingChange]) -> None:
        """Store detected changes as knowledge base documents."""
        try:
            from app.core.database import get_db_context
            from app.knowledge.services.ingestion import IngestionService

            async with get_db_context() as db:
                service = IngestionService(db)
                for change in changes:
                    title = (
                        f"Rendering change: {change.property_id} in "
                        f"{change.client_id} ({change.diff_percentage:.1f}% diff)"
                    )
                    content = (
                        f"# Rendering Change Detected\n\n"
                        f"**Property:** `{change.property_id}`\n"
                        f"**Client:** `{change.client_id}`\n"
                        f"**Diff:** {change.diff_percentage:.2f}%\n"
                        f"**Detected:** {change.detected_at.isoformat()}\n"
                        f"**Template:** `{change.template_name}`\n\n"
                        f"The email client `{change.client_id}` has changed "
                        f"how it renders CSS property `{change.property_id}`. "
                        f"This may indicate expanded or reduced CSS support. "
                        f"Review the ontology support matrix and update if needed."
                    )
                    try:
                        await service.ingest_text(
                            title=title,
                            content=content,
                            domain="rendering_changes",
                        )
                    except Exception:
                        logger.warning(
                            "change_detection.knowledge_write_failed",
                            property_id=change.property_id,
                            client_id=change.client_id,
                            exc_info=True,
                        )
                await db.commit()
        except Exception:
            logger.warning(
                "change_detection.knowledge_store_failed",
                exc_info=True,
            )

    async def _load_baselines(self) -> dict[str, bytes]:
        """Load baseline screenshots from Redis."""
        try:
            redis = await get_redis()
            raw = await redis.get(_REDIS_BASELINES_KEY)
            if raw:
                data: dict[str, str] = json.loads(raw)
                return {k: base64.b64decode(v) for k, v in data.items()}
        except Exception:
            logger.debug("change_detection.baselines_load_failed", exc_info=True)
        return {}

    async def _save_baselines(self, baselines: dict[str, bytes]) -> None:
        """Persist baseline screenshots to Redis (base64-encoded)."""
        try:
            redis = await get_redis()
            data = {k: base64.b64encode(v).decode("ascii") for k, v in baselines.items()}
            await redis.setex(
                _REDIS_BASELINES_KEY,
                _REDIS_BASELINES_TTL,
                json.dumps(data),
            )
        except Exception:
            logger.warning("change_detection.baselines_save_failed", exc_info=True)

    async def _save_last_run(self, result: DetectionResult) -> None:
        """Save last run metadata to Redis."""
        try:
            redis = await get_redis()
            data = {
                "run_at": datetime.now(UTC).isoformat(),
                "changes": len(result.changes),
                "templates_checked": result.templates_checked,
                "clients_checked": result.clients_checked,
                "baselines_created": result.baselines_created,
                "errors": result.errors,
            }
            await redis.setex(
                _REDIS_LAST_RUN_KEY,
                _REDIS_BASELINES_TTL,
                json.dumps(data),
            )
        except Exception:
            logger.debug("change_detection.last_run_save_failed", exc_info=True)
