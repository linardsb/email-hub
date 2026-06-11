"""Proactive QA warning extraction and pipeline injection.

Turns past QA failure patterns into future prevention by:
1. Extracting structured warnings from failed QA results
2. Querying semantic memory for component+client-scoped warnings
3. Formatting warnings for injection into agent prompts
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProactiveWarning:
    """A structured warning derived from past QA failures."""

    component: str
    client: str
    failure: str
    severity: str  # "critical" | "warning" | "info"
    suggestion: str
    occurrence_count: int = 1
    first_seen: str = ""
    last_seen: str = ""


class FailureExtractor:
    """Extracts ProactiveWarning instances from failed QA check results."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def extract_from_qa_result(
        self,
        *,
        check_name: str,
        passed: bool,
        details: dict[str, object],
        component_slugs: list[str],
        client_ids: list[str],
        score: float = 0.0,
    ) -> list[ProactiveWarning]:
        """Extract warnings from a single QA check result.

        Only produces warnings when the check failed.
        Deduplicates within the current batch by component+client+check hash.
        """
        if passed:
            return []

        severity = _score_to_severity(score)
        description = str(details.get("message", f"QA check '{check_name}' failed"))
        suggestion = str(details.get("suggestion", ""))

        warnings: list[ProactiveWarning] = []
        for component in component_slugs or [""]:
            for client in client_ids or [""]:
                dedup_key = hashlib.blake2b(
                    f"{component}:{client}:{check_name}".encode(),
                    digest_size=16,
                ).hexdigest()

                if dedup_key in self._seen:
                    continue
                self._seen.add(dedup_key)

                warnings.append(
                    ProactiveWarning(
                        component=component,
                        client=client,
                        failure=check_name,
                        severity=severity,
                        suggestion=suggestion or description,
                    )
                )

        return warnings


class ProactiveWarningInjector:
    """Queries semantic memory for component+client-scoped warnings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def query_warnings(
        self,
        *,
        component_slugs: list[str],
        client_ids: list[str],
        project_id: int | None,
    ) -> list[ProactiveWarning]:
        """Query semantic memory for warnings matching components and clients.

        Returns warnings where metadata source is 'failure_pattern' and
        client_ids overlap with the requested set.
        """
        if not component_slugs and not client_ids:
            return []

        cfg = self._settings.knowledge
        min_occurrences = cfg.failure_min_occurrences
        max_warnings = cfg.proactive_max_warnings

        try:
            results = await _recall_component_warnings(
                component_slugs=component_slugs,
                client_ids=client_ids,
                project_id=project_id,
                limit=max_warnings * 2,
            )
        except Exception:
            logger.warning("proactive_qa.query_failed", exc_info=True)
            return []

        # Filter by min occurrences and cap
        filtered = [w for w in results if w.occurrence_count >= min_occurrences]
        return filtered[:max_warnings]

    def format_warnings_for_prompt(self, warnings: list[ProactiveWarning]) -> str:
        """Format warnings as a markdown block for agent prompt injection."""
        if not warnings:
            return ""

        lines: list[str] = [
            "## Known Failure Patterns",
            "",
        ]
        for w in warnings:
            parts: list[str] = []
            if w.component:
                parts.append(w.component)
            if w.client:
                parts.append(f"in {w.client}")
            parts.append(f"— {w.suggestion}")
            if w.occurrence_count > 1:
                parts.append(f"(seen {w.occurrence_count}x)")

            lines.append(f"- {' '.join(parts)}")

        return "\n".join(lines)


async def _recall_component_warnings(
    *,
    component_slugs: list[str],
    client_ids: list[str],
    project_id: int | None,
    limit: int = 20,
) -> list[ProactiveWarning]:
    """Query semantic memory by component+client terms.

    Similar pattern to recall_failure_patterns() in failure_patterns.py
    but queries by component slugs instead of agent names.
    """
    from app.core.config import get_settings
    from app.core.scoped_db import get_system_db_context
    from app.knowledge.embedding import get_embedding_provider
    from app.memory.service import MemoryService

    # Build query from component slugs + client ids
    slug_part = " ".join(component_slugs[:5])
    client_part = " ".join(client_ids[:5])
    query = f"failure_pattern component {slug_part} email client {client_part}"

    async with get_system_db_context() as db:
        embedding_provider = get_embedding_provider(get_settings())
        service = MemoryService(db, embedding_provider)
        memories = await service.recall(
            query,
            project_id=project_id,
            memory_type="semantic",
            limit=limit,
        )

    warnings: list[ProactiveWarning] = []
    client_set = set(client_ids)

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
        if client_set and pattern_clients and not pattern_clients.intersection(client_set):
            continue

        qa_check = str(metadata.get("qa_check", "unknown"))
        # Count occurrences by checking how many similar entries exist
        occurrence_count = 1

        warnings.append(
            ProactiveWarning(
                component=slug_part.split()[0] if slug_part else "",
                client=str(next(iter(pattern_clients), "")) if pattern_clients else "",
                failure=qa_check,
                severity="warning",
                suggestion=memory.content[:200],
                occurrence_count=occurrence_count,
            )
        )
        if len(warnings) >= limit:
            break

    return warnings


def _score_to_severity(score: float) -> str:
    """Map QA check score to severity level."""
    if score < 0.3:
        return "critical"
    if score < 0.7:
        return "warning"
    return "info"
