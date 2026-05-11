"""Extract email-development patterns and inject into knowledge base."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.templates.upload.analyzer import AnalysisResult

if TYPE_CHECKING:
    from app.knowledge.services.ingestion import IngestionService

logger = get_logger(__name__)

# Patterns worth documenting
_PATTERN_DETECTORS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "VML background images",
        "css_support",
        re.compile(r"v:rect|v:image|v:roundrect", re.IGNORECASE),
    ),
    ("MSO conditional comments", "client_quirks", re.compile(r"<!--\[if\s+mso\b")),
    ("CSS grid with fallback", "best_practices", re.compile(r"display:\s*grid", re.IGNORECASE)),
    (
        "Dark mode meta support",
        "best_practices",
        re.compile(r"color-scheme:\s*light\s+dark", re.IGNORECASE),
    ),
    (
        "Fluid hybrid layout",
        "best_practices",
        re.compile(r"max-width.*width:\s*100%", re.IGNORECASE | re.DOTALL),
    ),
    ("AMP for email", "best_practices", re.compile(r"⚡4email|amp4email", re.IGNORECASE)),
    (
        "Responsive media queries",
        "best_practices",
        re.compile(r"@media[^{]*max-width", re.IGNORECASE),
    ),
    ("Braze connected content", "client_quirks", re.compile(r"connected_content", re.IGNORECASE)),
    (
        "Retina images (2x)",
        "best_practices",
        re.compile(r'width="\d+"[^>]*style="[^"]*width:\s*\d+px', re.IGNORECASE),
    ),
]


class KnowledgeInjector:
    """Creates knowledge base entries from analyzed template patterns."""

    def __init__(self, knowledge_service: IngestionService) -> None:
        self.knowledge = knowledge_service

    async def inject(
        self,
        template_name: str,
        sanitized_html: str,
        analysis: AnalysisResult,
        esp_platform: str | None,
    ) -> int | None:
        """Extract patterns and create knowledge document.

        Returns document ID or None if no notable patterns found.
        """
        patterns = self._detect_patterns(sanitized_html)
        if not patterns:
            logger.info("template_upload.no_notable_patterns", template=template_name)
            return None

        # Build text summary
        summary = self._build_summary(template_name, patterns, analysis, esp_platform)
        tags = list({p[1] for p in patterns})

        # Write summary to a temp file for knowledge service ingestion
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix=f"template_{template_name}_", delete=False
        ) as f:
            f.write(summary)
            temp_path = f.name

        try:
            from app.knowledge.schemas import DocumentUpload

            upload = DocumentUpload(
                domain="email_templates",
                title=f"Template patterns: {template_name}",
                description=f"Email development patterns extracted from uploaded template {template_name}",
                language="en",
                metadata_json=json.dumps({"tags": tags}),
            )

            result = await self.knowledge.ingest_document(
                file_path=temp_path,
                upload=upload,
                filename=f"{template_name}_patterns.txt",
                source_type="text",
                file_size=len(summary.encode()),
            )

            logger.info(
                "template_upload.knowledge_injected",
                template=template_name,
                document_id=result.id,
                patterns=len(patterns),
            )
            return result.id
        except Exception:
            logger.warning(
                "template_upload.knowledge_inject_failed",
                template=template_name,
                exc_info=True,
            )
            return None
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _detect_patterns(self, html: str) -> list[tuple[str, str]]:
        """Detect notable patterns in the HTML."""
        found: list[tuple[str, str]] = []
        for name, tag, pattern in _PATTERN_DETECTORS:
            if pattern.search(html):
                found.append((name, tag))
        return found

    def _build_summary(
        self,
        template_name: str,
        patterns: list[tuple[str, str]],
        analysis: AnalysisResult,
        esp_platform: str | None,
    ) -> str:
        """Build a text summary of detected patterns."""
        lines = [
            f"# Template Patterns: {template_name}",
            "",
            f"Layout: {analysis.layout_type}",
            f"Sections: {len(analysis.sections)}",
            f"Slots: {len(analysis.slots)}",
            f"Complexity: {analysis.complexity.score}/100",
        ]

        if esp_platform:
            lines.append(f"ESP Platform: {esp_platform}")

        lines.append("")
        lines.append("## Detected Patterns")
        lines.append("")

        for name, tag in patterns:
            lines.append(f"- **{name}** (category: {tag})")

        lines.append("")
        lines.append("## Section Structure")
        lines.append("")
        for section in analysis.sections:
            lines.append(
                f"- {section.component_name}: {section.element_count} elements ({section.layout_type})"
            )

        return "\n".join(lines)
