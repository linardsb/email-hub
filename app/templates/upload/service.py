"""Template upload pipeline orchestrator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.evals.template_eval_generator import TemplateEvalGenerator
from app.ai.shared import sanitize_html_xss
from app.ai.templates.models import DefaultTokens, TemplateSlot
from app.core.config import get_settings
from app.core.logging import get_logger
from app.templates.upload.analyzer import AnalysisResult, TemplateAnalyzer
from app.templates.upload.design_system_mapper import DesignSystemMapper, TokenDiff
from app.templates.upload.exceptions import (
    TemplateAlreadyConfirmedError,
    TemplateTooLargeError,
    UploadNotFoundError,
    UploadRateLimitError,
)
from app.templates.upload.image_importer import ImageImporter, ImportedImage
from app.templates.upload.models import TemplateUpload
from app.templates.upload.repository import TemplateUploadRepository
from app.templates.upload.schemas import (
    AnalysisPreview,
    ConfirmRequest,
    CSSOptimizationPreview,
    ImagePreview,
    SectionPreview,
    SlotPreview,
    TemplateUploadResponse,
    TokenDiffPreview,
    TokenPreview,
    UploadStatus,
    WrapperPreview,
)
from app.templates.upload.slot_extractor import SlotExtractor
from app.templates.upload.template_builder import TemplateBuilder
from app.templates.upload.token_extractor import TokenExtractor

logger = get_logger(__name__)


@dataclass
class _CSSOptimizationResult:
    """Internal result from CSS compilation pass."""

    compiled_html: str | None = None
    removed_properties: list[str] = field(default_factory=lambda: list[str]())
    conversions: list[Any] = field(default_factory=lambda: list[Any]())
    warnings: list[str] = field(default_factory=lambda: list[str]())
    shorthand_expansions: int = 0


class TemplateUploadService:
    """Orchestrates the template upload -> analyze -> confirm pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._repo = TemplateUploadRepository(db)
        self._analyzer = TemplateAnalyzer()
        self._slot_extractor = SlotExtractor()
        self._token_extractor = TokenExtractor()
        self._builder = TemplateBuilder()
        self._eval_gen = TemplateEvalGenerator()
        self._image_importer = ImageImporter()
        self._settings = get_settings().templates

    async def upload_and_analyze(
        self,
        html_content: str,
        user_id: int,
        project_id: int | None = None,
    ) -> AnalysisPreview:
        """Step 1: Upload HTML, sanitize, analyze, store pending upload."""
        file_size = len(html_content.encode())

        # Validate file size
        if file_size > self._settings.max_file_size_bytes:
            msg = (
                f"HTML exceeds {self._settings.max_file_size_bytes} byte limit ({file_size} bytes)"
            )
            raise TemplateTooLargeError(msg)

        # Check rate limit
        since = datetime.now(UTC) - timedelta(hours=1)
        recent_count = await self._repo.count_recent_by_user(user_id, since)
        if recent_count >= self._settings.max_uploads_per_hour:
            msg = f"Upload rate limit exceeded ({self._settings.max_uploads_per_hour}/hour)"
            raise UploadRateLimitError(msg)

        # Sanitize HTML
        sanitized = sanitize_html_xss(html_content, profile="import_annotator")

        # Run CSS compilation to expand shorthands and optimize
        css_optimization = self._compile_css(sanitized, project_id)
        if css_optimization.compiled_html:
            sanitized = css_optimization.compiled_html

        # Create pending upload record early to get upload.id for image storage
        upload = TemplateUpload(
            user_id=user_id,
            project_id=project_id,
            status="pending_review",
            original_html=html_content,
            sanitized_html=sanitized,
            analysis_json={},
            file_size_bytes=file_size,
            esp_platform=None,
        )
        upload = await self._repo.create(upload)
        await self.db.flush()

        # Import external images (needs upload.id for storage path)
        imported_images: list[ImportedImage] = []
        if self._settings.import_images:
            sanitized, imported_images = await self._image_importer.import_images(
                sanitized,
                upload_id=upload.id,
            )

        # Run analysis
        analysis = self._analyzer.analyze(sanitized)
        slots = self._slot_extractor.extract(analysis.slots, analysis.sections)
        tokens = self._token_extractor.extract(analysis.tokens)

        # Map tokens against design system
        token_diff = await self._map_design_system_tokens(tokens, project_id)

        # Generate suggested name
        html_hash = hashlib.sha256(sanitized.encode()).hexdigest()[:6]
        suggested_name = f"uploaded_{analysis.layout_type}_{html_hash}"
        suggested_desc = (
            f"{analysis.layout_type.title()} template with {len(analysis.sections)} sections "
            f"and {len(slots)} slots"
        )
        if analysis.esp_platform:
            suggested_desc += f" ({analysis.esp_platform})"

        # Serialize analysis for storage
        analysis_dict = self._serialize_analysis(
            analysis, slots, tokens, suggested_name, suggested_desc
        )
        analysis_dict["css_optimization"] = {
            "removed_properties": css_optimization.removed_properties,
            "conversions": [
                {
                    "original": f"{c.original_property}: {c.original_value}",
                    "replacement": f"{c.replacement_property}: {c.replacement_value}",
                    "reason": c.reason,
                }
                for c in css_optimization.conversions
            ],
            "warnings": css_optimization.warnings,
            "shorthand_expansions": css_optimization.shorthand_expansions,
        }
        analysis_dict["token_diff"] = [
            {
                "property": d.property,
                "role": d.role,
                "imported_value": d.imported_value,
                "design_system_value": d.design_system_value,
                "action": d.action,
            }
            for d in token_diff
        ]
        analysis_dict["images"] = [
            {
                "original_url": img.original_url,
                "hub_url": img.hub_url,
                "display_width": img.display_width,
                "display_height": img.display_height,
                "intrinsic_width": img.intrinsic_width,
                "intrinsic_height": img.intrinsic_height,
                "alt": img.alt,
                "file_size_bytes": img.file_size_bytes,
            }
            for img in imported_images
        ]

        # Update the upload record with final data
        upload.sanitized_html = sanitized
        upload.analysis_json = analysis_dict
        upload.esp_platform = analysis.esp_platform
        await self.db.commit()

        logger.info(
            "template_upload.analyzed",
            upload_id=upload.id,
            sections=len(analysis.sections),
            slots=len(slots),
            images=len(imported_images),
            esp=analysis.esp_platform,
        )

        return self._build_preview(upload.id, analysis_dict)

    async def get_preview(self, upload_id: int, user_id: int) -> AnalysisPreview:
        """Retrieve analysis preview for review."""
        upload = await self._get_owned_upload(upload_id, user_id)
        return self._build_preview(upload.id, upload.analysis_json)

    async def confirm(
        self,
        upload_id: int,
        user_id: int,
        overrides: ConfirmRequest,
    ) -> TemplateUploadResponse:
        """Step 2: Confirm upload after developer review."""
        upload = await self._get_owned_upload(upload_id, user_id)

        if upload.status != "pending_review":
            raise TemplateAlreadyConfirmedError("Upload has already been confirmed or rejected")

        # Re-analyze to get typed objects (SlotInfo/TokenInfo not deserializable from JSON)
        stored = upload.analysis_json
        analysis = self._analyzer.analyze(upload.sanitized_html)
        slots = self._slot_extractor.extract(analysis.slots, analysis.sections)
        tokens = self._token_extractor.extract(analysis.tokens)

        # Apply overrides
        name = overrides.name or stored.get("suggested_name", "")
        description = overrides.description or stored.get("suggested_description", "")

        # Build GoldenTemplate
        section_names = [s.component_name for s in analysis.sections]
        template = self._builder.build(
            sanitized_html=upload.sanitized_html,
            slots=slots,
            tokens=tokens,
            layout_type=stored.get("layout_type", analysis.layout_type),
            column_count=stored.get("column_count", analysis.complexity.column_count),
            sections=section_names,
            name=name,
            description=description,
            wrapper=analysis.wrapper,
        )

        # Register in TemplateRegistry
        from app.ai.templates.registry import get_template_registry

        registry = get_template_registry()
        registry.register_uploaded(template)

        # Generate eval test cases (non-blocking on failure)
        if self._settings.auto_eval_generate:
            try:
                cases = self._eval_gen.generate(
                    template=template,
                    analysis=analysis,
                )
                self._eval_gen.save(template.metadata.name, cases)
            except Exception:
                logger.warning(
                    "template_upload.eval_generation_failed",
                    template=template.metadata.name,
                    exc_info=True,
                )

        # Inject knowledge (async, non-blocking on failure)
        if self._settings.auto_knowledge_inject:
            try:
                from app.knowledge.services.ingestion import IngestionService
                from app.templates.upload.knowledge_injector import KnowledgeInjector

                knowledge_svc = IngestionService(self.db)
                injector = KnowledgeInjector(knowledge_svc)
                await injector.inject(
                    template_name=template.metadata.name,
                    sanitized_html=upload.sanitized_html,
                    analysis=analysis,
                    esp_platform=analysis.esp_platform,
                )
            except Exception:
                logger.warning("template_upload.knowledge_inject_failed", exc_info=True)

        # Update status
        await self._repo.update_status(
            upload_id,
            "confirmed",
            confirmed_name=template.metadata.name,
            confirmed_at=datetime.now(UTC),
        )
        await self.db.commit()

        logger.info(
            "template_upload.confirmed",
            upload_id=upload_id,
            template_name=template.metadata.name,
        )

        return TemplateUploadResponse(
            id=upload.id,
            status=UploadStatus.CONFIRMED,
            template_name=template.metadata.name,
            created_at=upload.created_at,  # pyright: ignore[reportArgumentType]
        )

    async def reject(self, upload_id: int, user_id: int) -> None:
        """Reject and delete upload."""
        upload = await self._get_owned_upload(upload_id, user_id)
        await self._repo.delete(upload.id)
        await self.db.commit()

        logger.info("template_upload.rejected", upload_id=upload_id)

    async def _get_owned_upload(self, upload_id: int, user_id: int) -> TemplateUpload:
        """Get an upload record, verifying ownership."""
        upload = await self._repo.get(upload_id)
        if upload is None or upload.user_id != user_id:
            raise UploadNotFoundError(f"Upload {upload_id} not found")
        return upload

    def _serialize_analysis(
        self,
        analysis: AnalysisResult,
        slots: tuple[TemplateSlot, ...],
        tokens: DefaultTokens,
        suggested_name: str,
        suggested_desc: str,
    ) -> dict[str, object]:
        """Serialize analysis result for JSON storage."""
        return {
            "sections": [
                {
                    "section_id": s.section_id,
                    "component_name": s.component_name,
                    "element_count": s.element_count,
                    "layout_type": s.layout_type,
                }
                for s in analysis.sections
            ],
            "slots": [
                {
                    "slot_id": s.slot_id,
                    "slot_type": s.slot_type,
                    "selector": s.selector,
                    "required": s.required,
                    "max_chars": s.max_chars,
                    "content_preview": getattr(s, "content_preview", getattr(s, "placeholder", "")),
                }
                for s in slots
            ],
            "tokens": {
                "colors": dict(tokens.colors),
                "fonts": dict(tokens.fonts),
                "font_sizes": dict(tokens.font_sizes),
                "spacing": dict(tokens.spacing),
                "font_weights": dict(tokens.font_weights),
                "line_heights": dict(tokens.line_heights),
                "letter_spacings": dict(tokens.letter_spacings),
            },
            "esp_platform": analysis.esp_platform,
            "layout_type": analysis.layout_type,
            "column_count": analysis.complexity.column_count,
            "complexity_score": analysis.complexity.score,
            "suggested_name": suggested_name,
            "suggested_description": suggested_desc,
            "wrapper": (
                {
                    "tag": analysis.wrapper.tag,
                    "width": analysis.wrapper.width,
                    "align": analysis.wrapper.align,
                    "style": analysis.wrapper.style,
                    "bgcolor": analysis.wrapper.bgcolor,
                    "cellpadding": analysis.wrapper.cellpadding,
                    "cellspacing": analysis.wrapper.cellspacing,
                    "border": analysis.wrapper.border,
                    "role": analysis.wrapper.role,
                    "inner_td_style": analysis.wrapper.inner_td_style,
                    "mso_wrapper": analysis.wrapper.mso_wrapper,
                }
                if analysis.wrapper
                else None
            ),
        }

    def _build_preview(self, upload_id: int, data: dict[str, Any]) -> AnalysisPreview:
        """Build AnalysisPreview from stored JSON data."""
        css_opt_data = data.get("css_optimization")
        css_optimization = CSSOptimizationPreview(**css_opt_data) if css_opt_data else None
        token_diff = [TokenDiffPreview(**d) for d in data.get("token_diff", [])]
        wrapper_data = data.get("wrapper")
        wrapper = WrapperPreview(**wrapper_data) if wrapper_data else None
        images = [ImagePreview(**i) for i in data.get("images", [])]

        return AnalysisPreview(
            upload_id=upload_id,
            sections=[SectionPreview(**s) for s in data.get("sections", [])],
            slots=[SlotPreview(**s) for s in data.get("slots", [])],
            tokens=TokenPreview(**data.get("tokens", {})),
            esp_platform=data.get("esp_platform"),
            layout_type=data.get("layout_type", "newsletter"),
            column_count=data.get("column_count", 1),
            complexity_score=data.get("complexity_score", 0),
            suggested_name=data.get("suggested_name", ""),
            suggested_description=data.get("suggested_description", ""),
            css_optimization=css_optimization,
            token_diff=token_diff,
            wrapper=wrapper,
            images=images,
        )

    def _compile_css(self, sanitized: str, _project_id: int | None) -> _CSSOptimizationResult:
        """Run CSS compilation on sanitized HTML."""
        from app.email_engine.css_compiler import EmailCSSCompiler

        try:
            target_clients = get_settings().email_engine.css_compiler_target_clients
            compiler = EmailCSSCompiler(target_clients=target_clients)
            result = compiler.optimize_css(sanitized)
            return _CSSOptimizationResult(
                compiled_html=result.html,
                removed_properties=result.removed_properties,
                conversions=result.conversions,
                warnings=result.warnings,
                shorthand_expansions=0,  # tracked at sidecar level
            )
        except Exception:
            logger.warning("template_upload.css_compilation_failed", exc_info=True)
            return _CSSOptimizationResult(compiled_html=None)

    async def _map_design_system_tokens(
        self, tokens: DefaultTokens, project_id: int | None
    ) -> list[TokenDiff]:
        """Map extracted tokens against project design system."""
        if not project_id:
            return []
        try:
            from sqlalchemy import select

            from app.projects.design_system import DesignSystem
            from app.projects.models import Project

            result = await self.db.execute(
                select(Project.design_system).where(Project.id == project_id)
            )
            ds_json = result.scalar_one_or_none()
            ds = DesignSystem(**ds_json) if ds_json else None
            mapper = DesignSystemMapper(ds)
            return mapper.generate_diff(tokens, mapper.map_tokens(tokens))
        except Exception:
            logger.warning("template_upload.design_system_mapping_failed", exc_info=True)
            return []
