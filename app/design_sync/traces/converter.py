"""Converter trace + insight + memory persistence (F060).

Merges the three legacy modules that all sit on the same
fire-and-forget post-conversion path:

* trace JSONL append (was ``converter_traces``)
* low-confidence insight extraction (was ``converter_insights``)
* semantic memory persistence (was ``converter_memory``)

Pure logic lives at module top; the three ``persist_*`` coroutines own
the I/O and side-effect guards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ai.blueprints.insight_bus import AgentInsight, persist_insights
from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.traces.writer import TraceWriter

if TYPE_CHECKING:
    from app.design_sync.converter_service import ConversionResult

logger = get_logger(__name__)

_DEFAULT_TRACES_PATH = Path("traces/converter_traces.jsonl")
_MAX_CONTENT_LENGTH = 4000
_CLEAN_CONFIDENCE_THRESHOLD = 0.8


# ── quality scoring ───────────────────────────────────────────────────


def compute_quality_score(result: ConversionResult) -> float:
    """Compute a weighted quality score from conversion results.

    Components:
    - avg_confidence * 0.5 (component matching quality)
    - (1 - warning_ratio) * 0.3
    - (1 - error_ratio) * 0.2
    """
    confidences = list(result.match_confidences.values())
    avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0

    sections = max(result.sections_count, 1)
    warning_ratio = min(len(result.quality_warnings) / sections, 1.0)

    error_count = sum(1 for w in result.quality_warnings if w.severity == "error")
    total_warnings = len(result.quality_warnings)
    error_ratio = error_count / total_warnings if total_warnings else 0.0

    return avg_confidence * 0.5 + (1 - warning_ratio) * 0.3 + (1 - error_ratio) * 0.2


# ── trace builder + JSONL appender ────────────────────────────────────


def build_trace(result: ConversionResult, connection_id: str | None) -> dict[str, Any]:
    """Build a trace dict from a ConversionResult."""
    confidences = list(result.match_confidences.values())
    trace_id = f"conv-{connection_id or 'none'}-{uuid.uuid4().hex[:8]}"

    return {
        "trace_id": trace_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "connection_id": connection_id,
        "figma_url": result.figma_url,
        "node_id": result.node_id,
        "sections_count": result.sections_count,
        "warnings": [
            {"category": w.category, "severity": w.severity, "message": w.message}
            for w in result.quality_warnings
        ],
        "match_confidences": {str(k): v for k, v in result.match_confidences.items()},
        "avg_confidence": sum(confidences) / len(confidences) if confidences else 1.0,
        "min_confidence": min(confidences) if confidences else 1.0,
        "quality_score": compute_quality_score(result),
        "compatibility_hint_count": len(result.compatibility_hints),
        "cache_hit_rate": result.cache_hit_rate,
        "design_tokens_used": result.design_tokens_used,
    }


def append_trace(trace: dict[str, Any], path: Path | None = None) -> None:
    """Append a trace as a JSONL line. Creates file if needed."""
    trace_path = path or _DEFAULT_TRACES_PATH
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as f:
        import json

        f.write(json.dumps(trace, default=str) + "\n")


async def persist_converter_trace(
    result: ConversionResult,
    connection_id: str | None,
) -> None:
    """Build and append a converter trace. Fire-and-forget."""
    try:
        settings = get_settings()
        if not settings.design_sync.conversion_traces_enabled:
            return

        trace = build_trace(result, connection_id)
        trace_path = Path(settings.design_sync.conversion_traces_path)
        append_trace(trace, trace_path)

        logger.info(
            "converter_traces.appended",
            trace_id=trace["trace_id"],
            quality_score=trace["quality_score"],
        )
    except Exception:
        logger.warning(
            "converter_traces.persist_failed",
            connection_id=connection_id,
            exc_info=True,
        )


# ── insight extraction (was converter_insights) ───────────────────────


def extract_conversion_insights(
    result: ConversionResult,
) -> list[AgentInsight]:
    """Scan match_confidences for entries below threshold.

    Groups nearby low-confidence sections by section type (from layout)
    to avoid insight flooding.
    """
    settings = get_settings()
    threshold = settings.design_sync.low_match_confidence_threshold

    low_sections = sorted(
        (idx, conf) for idx, conf in result.match_confidences.items() if conf < threshold
    )
    if not low_sections:
        return []

    section_types: dict[int, str] = {}
    if result.layout:
        for i, section in enumerate(result.layout.sections):
            section_types[i] = section.section_type.value

    now = datetime.now(UTC)
    insights: list[AgentInsight] = []

    def _section_type(item: tuple[int, float]) -> str:
        return section_types.get(item[0], "unknown")

    for section_type, group in groupby(low_sections, key=_section_type):
        items = list(group)
        indices = [idx for idx, _ in items]
        avg_conf = sum(conf for _, conf in items) / len(items)

        if len(items) == 1:
            idx, conf = items[0]
            text = (
                f"Section {idx} ({section_type}) matched with "
                f"{conf:.0%} confidence. Consider alternative templates "
                f"for this layout pattern."
            )
        else:
            text = (
                f"Sections {indices} ({section_type}) matched with "
                f"avg {avg_conf:.0%} confidence. Consider alternative "
                f"templates for this layout pattern."
            )

        insights.append(
            AgentInsight(
                source_agent="design_sync",
                target_agents=("scaffolder",),
                client_ids=(),
                insight=text,
                category="conversion",
                confidence=1.0 - avg_conf,
                evidence_count=1,
                first_seen=now,
                last_seen=now,
            )
        )

    return insights


async def persist_conversion_insights(
    result: ConversionResult,
    connection_id: str | None,
    project_id: int | None,
) -> int:
    """Extract and persist conversion insights. Fire-and-forget."""
    try:
        settings = get_settings()
        if not settings.design_sync.conversion_memory_enabled:
            return 0

        insights = extract_conversion_insights(result)
        if not insights:
            return 0

        count = await persist_insights(insights, project_id)
        logger.info(
            "converter_insights.persisted",
            count=count,
            connection_id=connection_id,
        )
        return count
    except Exception:
        logger.warning(
            "converter_insights.persist_failed",
            connection_id=connection_id,
            exc_info=True,
        )
        return 0


# ── semantic memory persistence (was converter_memory) ────────────────


def _should_persist_memory(result: ConversionResult) -> bool:
    """Skip clean conversions — only persist when there are quality issues."""
    return bool(result.quality_warnings) or any(
        c < _CLEAN_CONFIDENCE_THRESHOLD for c in result.match_confidences.values()
    )


def format_conversion_quality(
    result: ConversionResult,
) -> str | None:
    """Format a conversion quality report as a memory content string.

    Returns None if the conversion is clean (no warnings, high confidence).
    """
    if not _should_persist_memory(result):
        return None

    lines: list[str] = [
        f"Conversion quality report (sections={result.sections_count}, "
        f"warnings={len(result.quality_warnings)}):",
    ]

    for w in result.quality_warnings:
        lines.append(f"- {w.category} ({w.severity}): {w.message}")

    low_confidence = [idx for idx, conf in result.match_confidences.items() if conf < 0.6]
    if low_confidence:
        avg_low = sum(result.match_confidences[i] for i in low_confidence) / len(low_confidence)
        lines.append(f"Low-confidence matches: sections {low_confidence} (avg {avg_low:.2f})")

    if result.design_tokens_used:
        token_parts: list[str] = []
        if "primary_color" in result.design_tokens_used:
            token_parts.append(str(result.design_tokens_used["primary_color"]))
        if "font_family" in result.design_tokens_used:
            token_parts.append(str(result.design_tokens_used["font_family"]))
        if token_parts:
            lines.append(f"Design tokens: {', '.join(token_parts)}")

    lines.append(f"Source: {result.figma_url or 'unknown'}")

    content = "\n".join(lines)
    if len(content) > _MAX_CONTENT_LENGTH:
        content = content[: _MAX_CONTENT_LENGTH - 3] + "..."
    return content


def build_conversion_metadata(
    result: ConversionResult,
    connection_id: str | None,
) -> dict[str, Any]:
    """Build metadata dict for the memory entry."""
    low_confidence_sections = [idx for idx, conf in result.match_confidences.items() if conf < 0.6]
    confidences = list(result.match_confidences.values())
    avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
    categories = sorted({w.category for w in result.quality_warnings})

    return {
        "source": "converter_quality",
        "connection_id": connection_id,
        "figma_url": result.figma_url,
        "node_id": result.node_id,
        "sections_count": result.sections_count,
        "warning_count": len(result.quality_warnings),
        "warning_categories": categories,
        "avg_match_confidence": round(avg_confidence, 4),
        "low_confidence_sections": low_confidence_sections,
        "has_quality_issues": True,
    }


async def persist_conversion_quality(
    result: ConversionResult,
    connection_id: str | None,
    project_id: int | None,
) -> None:
    """Persist conversion quality data as a semantic memory entry.

    Fire-and-forget — exceptions are logged but never propagate.
    """
    try:
        settings = get_settings()
        if not settings.design_sync.conversion_memory_enabled:
            return

        content = format_conversion_quality(result)
        if content is None:
            return

        metadata = build_conversion_metadata(result, connection_id)

        from app.core.scoped_db import get_system_db_context
        from app.knowledge.embedding import get_embedding_provider
        from app.memory.schemas import MemoryCreate
        from app.memory.service import MemoryService

        async with get_system_db_context() as db:
            embedding_provider = get_embedding_provider(settings)
            service = MemoryService(db, embedding_provider)
            await service.store(
                MemoryCreate(
                    agent_type="design_sync",
                    memory_type="semantic",
                    content=content,
                    project_id=project_id,
                    metadata=metadata,
                    is_evergreen=False,
                ),
            )

        logger.info(
            "converter_memory.persisted",
            connection_id=connection_id,
            warning_count=len(result.quality_warnings),
            project_id=project_id,
        )
    except Exception:
        logger.warning(
            "converter_memory.persist_failed",
            connection_id=connection_id,
            exc_info=True,
        )


# Re-export for symmetry with the legacy modules
__all__ = [
    "TraceWriter",
    "append_trace",
    "build_conversion_metadata",
    "build_trace",
    "compute_quality_score",
    "extract_conversion_insights",
    "format_conversion_quality",
    "persist_conversion_insights",
    "persist_conversion_quality",
    "persist_converter_trace",
]
