"""Module-level helpers for design sync.

After Tech Debt 08b, the ``DesignSyncService`` facade was deleted. Callers depend
on the carved sub-services in ``app.design_sync.services`` directly. This module
retains: ``SUPPORTED_PROVIDERS``, ``fetch_target_clients``, ``_filter_structure``,
``_layout_to_response``, and the training-case persistence helpers.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import DesignLayoutDescription
from app.design_sync.figma.service import FigmaDesignSyncService
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignSyncProvider,
)
from app.design_sync.schemas import (
    AnalyzedSectionResponse,
    ButtonElementResponse,
    ImagePlaceholderResponse,
    LayoutAnalysisResponse,
    TextBlockResponse,
)

logger = get_logger(__name__)


# ── Provider registry (re-exported by tests) ─

SUPPORTED_PROVIDERS: dict[str, type[DesignSyncProvider]] = {
    "figma": FigmaDesignSyncService,
}

# Stub providers — registered after the dict literal so `SUPPORTED_PROVIDERS` stays
# the single source of truth for tests that re-export it.
from app.design_sync.canva.service import CanvaDesignSyncService  # noqa: E402
from app.design_sync.sketch.service import SketchDesignSyncService  # noqa: E402

SUPPORTED_PROVIDERS["sketch"] = SketchDesignSyncService  # type: ignore[assignment]
SUPPORTED_PROVIDERS["canva"] = CanvaDesignSyncService  # type: ignore[assignment]

if get_settings().design_sync.penpot_enabled:
    from app.design_sync.penpot.service import PenpotDesignSyncService

    SUPPORTED_PROVIDERS["penpot"] = PenpotDesignSyncService  # type: ignore[assignment]

if get_settings().environment == "development":
    from app.design_sync.mock.service import MockDesignSyncService

    SUPPORTED_PROVIDERS["mock"] = MockDesignSyncService  # type: ignore[assignment]


async def fetch_target_clients(
    db: AsyncSession,
    project_id: int | None,
) -> list[str] | None:
    """Fetch project target clients for compatibility checks (best-effort).

    Returns None if no project or if the lookup fails for any reason.
    """
    if not project_id:
        return None
    try:
        from app.projects.repository import ProjectRepository

        project = await ProjectRepository(db).get(project_id)
        return project.target_clients if project else None
    except Exception:
        logger.debug("design_sync.target_clients_skip", exc_info=True)
        return None


# ── Module-level helpers preserved for tests/routes ─


def _filter_structure(
    structure: DesignFileStructure,
    selected_ids: list[str],
) -> DesignFileStructure:
    """Filter a DesignFileStructure to only include nodes with matching IDs."""
    id_set = set(selected_ids)

    def _filter_node(node: DesignNode) -> DesignNode | None:
        if node.id in id_set:
            return node
        filtered_children = [c for c in (_filter_node(ch) for ch in node.children) if c is not None]
        if filtered_children:
            return replace(node, children=filtered_children)
        return None

    filtered_pages: list[DesignNode] = []
    for page in structure.pages:
        filtered = _filter_node(page)
        if filtered is not None:
            filtered_pages.append(filtered)

    return DesignFileStructure(file_name=structure.file_name, pages=filtered_pages)


def _layout_to_response(
    connection_id: int,
    layout: DesignLayoutDescription,
) -> LayoutAnalysisResponse:
    """Convert DesignLayoutDescription to LayoutAnalysisResponse."""
    sections = [
        AnalyzedSectionResponse(
            section_type=s.section_type.value,
            node_id=s.node_id,
            node_name=s.node_name,
            y_position=s.y_position,
            width=s.width,
            height=s.height,
            column_layout=s.column_layout.value,
            column_count=s.column_count,
            texts=[
                TextBlockResponse(
                    node_id=t.node_id,
                    content=t.content,
                    font_size=t.font_size,
                    is_heading=t.is_heading,
                    font_family=t.font_family,
                    font_weight=t.font_weight,
                    line_height=t.line_height,
                    letter_spacing=t.letter_spacing,
                )
                for t in s.texts
            ],
            images=[
                ImagePlaceholderResponse(
                    node_id=img.node_id,
                    node_name=img.node_name,
                    width=img.width,
                    height=img.height,
                    export_node_id=img.export_node_id,
                )
                for img in s.images
            ],
            buttons=[
                ButtonElementResponse(
                    node_id=btn.node_id,
                    text=btn.text,
                    width=btn.width,
                    height=btn.height,
                )
                for btn in s.buttons
            ],
            spacing_after=s.spacing_after,
            bg_color=s.bg_color,
            classification_confidence=s.classification_confidence,
            content_roles=list(s.content_roles),
        )
        for s in layout.sections
    ]

    return LayoutAnalysisResponse(
        connection_id=connection_id,
        file_name=layout.file_name,
        overall_width=layout.overall_width,
        sections=sections,
        total_text_blocks=layout.total_text_blocks,
        total_images=layout.total_images,
    )


# ── Training case persistence (HTML upload → learning loop) ─

_CASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEBUG_DIR = _PROJECT_ROOT / "data" / "debug"
_MANIFEST_PATH = _DEBUG_DIR / "manifest.yaml"


def _validate_case_id(case_id: str) -> None:
    """Validate case_id to prevent path traversal."""
    from app.design_sync.exceptions import TrainingCaseError

    if not _CASE_ID_PATTERN.match(case_id):
        msg = f"Invalid case_id '{case_id}': must be alphanumeric, hyphens, underscores (max 64 chars)"
        raise TrainingCaseError(msg)


async def create_training_case(
    *,
    case_id: str,
    case_name: str,
    html_content: str,
    source_name: str = "training",
    figma_url: str | None = None,
    figma_node: str | None = None,
    screenshot_data: bytes | None = None,
) -> dict[str, Any]:
    """Save an HTML email + optional screenshot as a training case on disk."""
    from app.design_sync.exceptions import TrainingCaseError, TrainingCaseExistsError

    _validate_case_id(case_id)

    case_dir = _DEBUG_DIR / case_id
    if case_dir.exists():
        raise TrainingCaseExistsError(f"Training case '{case_id}' already exists")

    if not html_content.strip():
        raise TrainingCaseError("HTML content is empty")

    if _MANIFEST_PATH.exists():
        existing_text = _MANIFEST_PATH.read_text()
        if f'id: "{case_id}"' in existing_text:
            raise TrainingCaseExistsError(f"Case '{case_id}' already in manifest")

    log = get_logger(__name__)
    files_written: list[str] = []

    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "expected.html").write_text(html_content, encoding="utf-8")
    files_written.append("expected.html")

    has_screenshot = False
    if screenshot_data:
        (case_dir / "design.png").write_bytes(screenshot_data)
        files_written.append("design.png")
        has_screenshot = True

    entry_yaml = (
        f'\n  - id: "{case_id}"\n'
        f'    name: "{case_name}"\n'
        f'    source: "{source_name}"\n'
        f'    figma_node: "{figma_node or "unknown"}"\n'
        f"    status: active\n"
        f"    design_image: {'true' if has_screenshot else 'false'}\n"
        f"    visual_threshold: 0.95\n"
        f"    reference_only: true\n"
    )

    if _MANIFEST_PATH.exists():
        with _MANIFEST_PATH.open("a", encoding="utf-8") as f:
            f.write(entry_yaml)
    else:
        _MANIFEST_PATH.write_text(f"cases:{entry_yaml}", encoding="utf-8")
    files_written.append("manifest.yaml (updated)")

    if figma_url or figma_node:
        import json

        meta = {"figma_url": figma_url, "figma_node": figma_node}
        (case_dir / "figma_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        files_written.append("figma_meta.json")

    log.info(
        "training_case.created",
        case_id=case_id,
        files=files_written,
    )

    return {
        "case_id": case_id,
        "case_dir": str(case_dir),
        "files_written": files_written,
        "manifest_updated": True,
    }


async def backfill_training_case(
    case_id: str,
    *,
    traces_only: bool = False,
) -> dict[str, Any]:
    """Backfill a single training case into the learning loop."""
    from app.design_sync.converter_memory import (
        _CLEAN_CONFIDENCE_THRESHOLD,
        build_conversion_metadata,
        format_conversion_quality,
    )
    from app.design_sync.converter_service import ConversionResult, DesignConverterService
    from app.design_sync.converter_traces import append_trace, build_trace
    from app.design_sync.exceptions import TrainingCaseError

    _validate_case_id(case_id)

    log = get_logger(__name__)
    case_dir = _DEBUG_DIR / case_id

    if not case_dir.exists():
        raise TrainingCaseError(f"Training case '{case_id}' not found at {case_dir}")

    has_structure = (case_dir / "structure.json").exists()
    has_html = (case_dir / "expected.html").exists()

    if not has_structure and not has_html:
        raise TrainingCaseError(f"Case '{case_id}' has neither structure.json nor expected.html")

    result: ConversionResult

    if has_structure:
        from app.design_sync.diagnose.report import (
            load_structure_from_json,
            load_tokens_from_json,
        )

        structure = load_structure_from_json(case_dir / "structure.json")
        tokens = load_tokens_from_json(case_dir / "tokens.json")
        from app.design_sync.email_design_document import EmailDesignDocument

        document = EmailDesignDocument.from_legacy(structure, tokens)
        result = DesignConverterService().convert_document(document)
    else:
        from app.design_sync.html_import.adapter import HtmlImportAdapter

        html = (case_dir / "expected.html").read_text(encoding="utf-8")
        adapter = HtmlImportAdapter()
        document = await adapter.parse(html, use_ai=False, source_name=case_id)
        section_count = len(document.sections)

        result = ConversionResult(
            html=html,
            sections_count=section_count,
            warnings=[],
            match_confidences=dict.fromkeys(range(section_count), 1.0),
            quality_warnings=[],
        )

    trace = build_trace(result, f"snapshot_{case_id}")
    append_trace(trace)
    traces_written = 1

    memory_stored = False
    insights_count = 0

    if not traces_only:
        confidences = list(result.match_confidences.values())
        has_issues = bool(result.quality_warnings) or any(
            c < _CLEAN_CONFIDENCE_THRESHOLD for c in confidences
        )

        if has_issues:
            content = format_conversion_quality(result)
            if content is not None:
                metadata = build_conversion_metadata(result, f"snapshot_{case_id}")
                from app.core.scoped_db import get_system_db_context
                from app.knowledge.embedding import get_embedding_provider
                from app.memory.schemas import MemoryCreate
                from app.memory.service import MemoryService

                settings = get_settings()
                async with get_system_db_context() as db:
                    embedding_provider = get_embedding_provider(settings)
                    service = MemoryService(db, embedding_provider)
                    await service.store(
                        MemoryCreate(
                            agent_type="design_sync",
                            memory_type="semantic",
                            content=content,
                            project_id=None,
                            metadata=metadata,
                            is_evergreen=False,
                        ),
                    )
                memory_stored = True

        from app.design_sync.converter_insights import persist_conversion_insights

        insights_count = await persist_conversion_insights(result, f"snapshot_{case_id}", None)

    log.info(
        "training_case.backfill_completed",
        case_id=case_id,
        traces_written=traces_written,
        memory_stored=memory_stored,
        insights_count=insights_count,
        source="structure" if has_structure else "html_only",
    )

    return {
        "case_id": case_id,
        "sections_count": result.sections_count,
        "traces_written": traces_written,
        "memory_stored": memory_stored,
        "insights_count": insights_count,
        "source": "structure" if has_structure else "html_only",
    }
