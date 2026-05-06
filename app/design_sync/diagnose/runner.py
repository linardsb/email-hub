"""Diagnostic runner — orchestrates the conversion pipeline with capture at each stage."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.design_sync.component_matcher import match_all
from app.design_sync.component_renderer import ComponentRenderer, RenderedSection
from app.design_sync.converter_service import (
    COMPONENT_SHELL,
    build_component_style_block,
    dark_mode_meta_tags,
)
from app.design_sync.diagnose.analyzers import (
    analyze_assembly_stage,
    analyze_design_tree,
    analyze_layout_stage,
    analyze_matching_stage,
    analyze_post_processing,
    analyze_rendering_stage,
    build_section_traces,
)
from app.design_sync.diagnose.models import (
    DataLossEvent,
    DesignSummary,
    DiagnosticReport,
    SectionTrace,
    StageResult,
)
from app.design_sync.figma.layout_analyzer import analyze_layout
from app.design_sync.html_formatter import format_email_html
from app.design_sync.protocol import DesignFileStructure, ExtractedTokens
from app.design_sync.sanitizers import sanitize_web_tags_for_email
from app.design_sync.visual_verify import VerificationLoopResult

logger = get_logger(__name__)

_FINAL_HTML_PREVIEW_LIMIT = 5000


class DiagnosticRunner:
    """Runs the full conversion pipeline with diagnostic capture at each stage."""

    def run_from_structure(
        self,
        structure: DesignFileStructure,
        tokens: ExtractedTokens,
        *,
        raw_figma_json: dict[str, Any] | None = None,
        target_clients: list[str] | None = None,  # noqa: ARG002 — reserved for future use
        verification_result: VerificationLoopResult | None = None,
        generation_methods: dict[int, str] | None = None,
        vlm_classifications: dict[int, tuple[str, float]] | None = None,
    ) -> DiagnosticReport:
        """Synchronous entry — for CLI and tests.

        Calls the same pipeline functions as converter_service._convert_with_components()
        but captures input/output at each stage boundary.
        """
        run_id = uuid.uuid4().hex[:12]
        t_start = time.perf_counter()
        stages: list[StageResult] = []
        all_images: list[dict[str, str]] = []

        # ── Stage 0: Design tree analysis ──
        design_summary, tree_loss = analyze_design_tree(structure, raw_figma_json)

        # ── Stage 1: Layout analysis ──
        try:
            layout = analyze_layout(structure)
            stage1 = analyze_layout_stage(structure, layout)
        except Exception as exc:
            logger.warning("diagnose.layout_analysis_failed", error=str(exc))
            stage1 = StageResult(
                name="layout_analysis",
                elapsed_ms=0.0,
                input_summary={},
                output_summary={},
                data_loss=(),
                warnings=(),
                error=str(exc),
            )
            stages.append(stage1)
            return self._build_report(
                run_id=run_id,
                t_start=t_start,
                stages=stages,
                design_summary=design_summary,
                section_traces=[],
                final_html="",
                images=[],
            )

        stages.append(stage1)

        # Derive container width (same logic as DesignConverterService)
        container_width = 600
        if layout.overall_width is not None:
            container_width = max(400, min(800, int(layout.overall_width)))

        # ── Stage 2: Component matching ──
        try:
            matches = match_all(layout.sections, container_width=container_width)
            stage2 = analyze_matching_stage(layout.sections, matches)
        except Exception as exc:
            logger.warning("diagnose.component_matching_failed", error=str(exc))
            stage2 = StageResult(
                name="component_matching",
                elapsed_ms=0.0,
                input_summary={"sections": len(layout.sections)},
                output_summary={},
                data_loss=(),
                warnings=(),
                error=str(exc),
            )
            stages.append(stage2)
            return self._build_report(
                run_id=run_id,
                t_start=t_start,
                stages=stages,
                design_summary=design_summary,
                section_traces=[],
                final_html="",
                images=[],
            )

        stages.append(stage2)

        # ── Stage 3: Rendering ──
        try:
            renderer = ComponentRenderer(container_width=container_width)
            renderer.load()
            rendered: list[RenderedSection] = renderer.render_all(matches)
            stage3 = analyze_rendering_stage(matches, rendered)
            for rs in rendered:
                all_images.extend(rs.images)
        except Exception as exc:
            logger.warning("diagnose.rendering_failed", error=str(exc))
            stage3 = StageResult(
                name="rendering",
                elapsed_ms=0.0,
                input_summary={"matches": len(matches)},
                output_summary={},
                data_loss=(),
                warnings=(),
                error=str(exc),
            )
            stages.append(stage3)
            return self._build_report(
                run_id=run_id,
                t_start=t_start,
                stages=stages,
                design_summary=design_summary,
                section_traces=[],
                final_html="",
                images=all_images,
            )

        stages.append(stage3)

        # ── Stage 4: Assembly ──
        assembled_html = self._assemble(rendered, tokens, container_width)
        stage4 = analyze_assembly_stage(rendered, assembled_html)
        stages.append(stage4)

        # ── Stage 5: Post-processing ──
        final_html = sanitize_web_tags_for_email(assembled_html)
        stage5 = analyze_post_processing(assembled_html, final_html)
        stages.append(stage5)

        # ── Build section traces ──
        # Extract per-section verification data from loop result
        per_section_verification: dict[int, tuple[float, int]] | None = None
        if verification_result and verification_result.iterations:
            per_section_verification = {}
            last_iter = verification_result.iterations[-1]
            # Build section_idx lookup from node_id scores
            for idx, section in enumerate(layout.sections):
                fidelity = last_iter.section_scores.get(section.node_id, 0.0)
                correction_count = sum(1 for c in last_iter.corrections if c.section_idx == idx)
                per_section_verification[idx] = (fidelity, correction_count)

        section_traces = build_section_traces(
            layout,
            matches,
            rendered,
            verification_results=per_section_verification,
            generation_methods=generation_methods,
            vlm_classifications=vlm_classifications,
        )

        # ── Structured logging for enhanced metadata ──
        if verification_result:
            sections_with_corrections = sum(1 for t in section_traces if t.corrections_applied > 0)
            logger.info(
                "diagnose.verification_metadata_attached",
                iterations=len(verification_result.iterations),
                final_fidelity=verification_result.final_fidelity,
                sections_with_corrections=sections_with_corrections,
            )

        if generation_methods:
            logger.debug(
                "diagnose.custom_generation_traced",
                count=len(generation_methods),
                section_indices=sorted(generation_methods.keys()),
            )

        if vlm_classifications:
            logger.debug(
                "diagnose.vlm_classification_traced",
                count=len(vlm_classifications),
                section_indices=sorted(vlm_classifications.keys()),
            )

        return self._build_report(
            run_id=run_id,
            t_start=t_start,
            stages=stages,
            design_summary=design_summary,
            section_traces=section_traces,
            final_html=final_html,
            images=all_images,
            tree_loss=tree_loss,
            verification_result=verification_result,
        )

    @staticmethod
    def _assemble(
        rendered: list[RenderedSection],
        tokens: ExtractedTokens,
        container_width: int,
    ) -> str:
        """Assemble rendered sections into full email HTML (mirrors converter_service)."""
        from app.design_sync.sanitizers import _sanitize_css_value
        from app.design_sync.token_transforms import (
            convert_colors_to_palette,
            convert_typography,
        )

        section_parts = [rs.html for rs in rendered]
        sections_html = "\n".join(section_parts)

        palette = convert_colors_to_palette(tokens.colors)
        typography = convert_typography(tokens.typography)
        bg_color = _sanitize_css_value(palette.background) or "#ffffff"
        safe_body_font = _sanitize_css_value(typography.body_font)
        safe_mso_font = _sanitize_css_value(typography.heading_font) or '"Segoe UI", sans-serif'

        style_block = build_component_style_block(
            safe_body_font or "Arial, Helvetica, sans-serif",
            tokens,
        )

        meta_tags = ""
        if tokens.dark_colors:
            meta_tags = dark_mode_meta_tags()

        result_html = COMPONENT_SHELL.format(
            meta_tags=meta_tags,
            style_block=style_block,
            mso_font=safe_mso_font,
            bg_color=bg_color,
            body_font=safe_body_font or "Arial, Helvetica, sans-serif",
            base_size=typography.base_size or "16px",
            container_width=container_width,
            sections=sections_html,
        )
        return format_email_html(result_html)

    @staticmethod
    def _build_report(
        *,
        run_id: str,
        t_start: float,
        stages: list[StageResult],
        design_summary: DesignSummary,
        section_traces: list[SectionTrace],
        final_html: str,
        images: list[dict[str, str]],
        tree_loss: list[DataLossEvent] | None = None,
        verification_result: VerificationLoopResult | None = None,
    ) -> DiagnosticReport:
        """Construct the final DiagnosticReport."""
        total_elapsed = (time.perf_counter() - t_start) * 1000.0
        total_warnings = sum(len(s.warnings) for s in stages)
        total_loss = sum(len(s.data_loss) for s in stages)
        if tree_loss:
            total_loss += len(tree_loss)

        # Verification loop summary
        loop_iterations = 0
        final_fidelity: float | None = None
        if verification_result:
            loop_iterations = len(verification_result.iterations)
            final_fidelity = verification_result.final_fidelity

        return DiagnosticReport(
            id=run_id,
            connection_id=None,
            timestamp=datetime.now(tz=UTC).isoformat(),
            total_elapsed_ms=round(total_elapsed, 2),
            stages_completed=len(stages),
            total_warnings=total_warnings,
            total_data_loss_events=total_loss,
            design_summary=design_summary,
            stages=tuple(stages),
            section_traces=tuple(section_traces),
            final_html_preview=final_html[:_FINAL_HTML_PREVIEW_LIMIT],
            final_html_length=len(final_html),
            images=images,
            verification_loop_iterations=loop_iterations,
            final_fidelity=final_fidelity,
        )
