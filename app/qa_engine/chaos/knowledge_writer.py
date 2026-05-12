"""Auto-generate knowledge documents from chaos test failures."""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.knowledge.models import Document
from app.knowledge.services.ingestion import IngestionService
from app.qa_engine.schemas import ChaosFailure

logger = get_logger(__name__)

# Recommended fix templates per profile
_FIX_HINTS: dict[str, str] = {
    "gmail_style_strip": (
        "Use inline styles instead of <style> blocks. Gmail strips all <style> and <link> elements."
    ),
    "image_blocked": (
        "Always provide meaningful alt text. Use background colors behind images as fallback."
    ),
    "dark_mode_inversion": (
        "Use explicit dark mode colors via prefers-color-scheme or data-ogsc attributes."
    ),
    "outlook_word_engine": (
        "Avoid flexbox, grid, and CSS custom properties. Use table-based layouts for Outlook."
    ),
    "gmail_clipping": (
        "Keep total HTML under 102KB. Minimize inline CSS, remove comments, compress whitespace."
    ),
    "mobile_narrow": ("Use max-width on wrapper table, not body. Ensure content reflows at 375px."),
    "class_strip": ("Use inline styles. Some security-focused clients strip all class attributes."),
    "media_query_strip": (
        "Don't rely solely on @media queries for layout. Use fluid widths as base."
    ),
}


class ChaosKnowledgeWriter:
    """Creates knowledge documents from chaos test failures for RAG retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._service = IngestionService(db)

    async def write_failure_documents(
        self,
        failures: list[ChaosFailure],
        project_id: int,
    ) -> list[int]:
        """Create knowledge documents for unique failure patterns.

        Deduplicates by title within this batch and against existing documents.
        Returns list of created document IDs.
        """
        if not failures:
            return []

        created_ids: list[int] = []
        seen_titles: set[str] = set()

        for failure in failures:
            title = f"{failure.profile} failure: {failure.check_name}"
            if title in seen_titles:
                continue
            seen_titles.add(title)

            if await self._title_exists(title):
                logger.debug(
                    "chaos.knowledge_writer.duplicate_skipped",
                    title=title,
                )
                continue

            fix_hint = _FIX_HINTS.get(
                failure.profile, "Review the failure and apply client-specific fixes."
            )
            content = self._build_document_content(failure, fix_hint)

            doc_id = await self._service.ingest_text(
                title=title,
                content=content,
                domain="chaos_findings",
                metadata_json=json.dumps(
                    {
                        "profile": failure.profile,
                        "check_name": failure.check_name,
                        "severity": failure.severity,
                        "project_id": project_id,
                        "section_type": "failure_pattern",
                    }
                ),
            )
            created_ids.append(doc_id)

            logger.info(
                "chaos.knowledge_writer.document_created",
                title=title,
                document_id=doc_id,
                profile=failure.profile,
                check_name=failure.check_name,
            )

        return created_ids

    async def _title_exists(self, title: str) -> bool:
        """Check if a document with this title already exists in chaos_findings domain."""
        result = await self._db.execute(
            select(Document.id)
            .where(Document.title == title, Document.domain == "chaos_findings")
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _sanitize_markdown(text: str) -> str:
        """Strip markdown-special characters from untrusted text."""
        return re.sub(r"[#\[\]`*_~<>]", "", text)

    @classmethod
    def _build_document_content(cls, failure: ChaosFailure, fix_hint: str) -> str:
        """Build markdown content for a chaos failure document."""
        safe_description = cls._sanitize_markdown(failure.description)
        return (
            f"# {failure.profile} failure: {failure.check_name}\n\n"
            f"## Failure Pattern\n"
            f"- **Profile:** {failure.profile}\n"
            f"- **Check:** {failure.check_name}\n"
            f"- **Severity:** {failure.severity}\n"
            f"- **Description:** {safe_description}\n\n"
            f"## Recommended Fix\n"
            f"{fix_hint}\n\n"
            f"## Context\n"
            f"This failure was detected by the Email Chaos Engine during "
            f"rendering resilience testing. The `{failure.profile}` profile "
            f"simulates a specific email client degradation that caused the "
            f"`{failure.check_name}` QA check to fail.\n"
        )
