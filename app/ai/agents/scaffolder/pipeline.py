"""3-pass generation pipeline for the Scaffolder agent.

Pass 1 (Layout):  Brief → TemplateSelection + SectionDecisions
Pass 2 (Content): Brief + Template slots → SlotFills
Pass 3 (Design):  Brief + Brand config → DesignTokens

Pass 1 runs first (needs template name). Passes 2+3 run in parallel.
Per-slot retry on content failures.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from app.ai.agents.scaffolder.pipeline_checkpoint import (
        PassName,
        PipelineCheckpointCallback,
    )
    from app.ai.agents.scaffolder.variant_schemas import CampaignVariantSet
    from app.components.tree_schema import EmailTree
    from app.projects.design_system import DesignSystem

from app.ai.agents.scaffolder.pipeline_checkpoint import (
    serialize_content_design_pass,
    serialize_layout_pass,
)
from app.ai.agents.schemas.build_plan import (
    DesignTokens,
    EmailBuildPlan,
    SectionDecision,
    SlotFill,
    TemplateSelection,
)
from app.ai.protocols import LLMProvider, Message
from app.ai.sanitize import sanitize_prompt
from app.ai.templates import GoldenTemplate, TemplateRegistry, get_template_registry
from app.core.logging import get_logger

logger = get_logger(__name__)

# Retry budget for individual pass failures
_MAX_RETRIES: int = 1


class PipelineError(Exception):
    """Raised when the pipeline cannot produce a valid plan."""


class ScaffolderPipeline:
    """3-pass generation pipeline with structured output."""

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        registry: TemplateRegistry | None = None,
        max_tokens: int = 4096,
        design_system: DesignSystem | None = None,
        checkpoint_callback: PipelineCheckpointCallback | None = None,
        run_id: str = "",
    ) -> None:
        self._provider = provider
        self._model = model
        self._registry = registry or get_template_registry()
        self._max_tokens = max_tokens
        self._design_system = design_system
        self._checkpoint_cb = checkpoint_callback
        self._run_id = run_id

    async def execute(
        self,
        brief: str,
        brand_config: dict[str, object] | None = None,
        resume: bool = False,
    ) -> EmailBuildPlan:
        """Execute 3-pass pipeline. Returns complete EmailBuildPlan.

        Pass 1 (layout) must complete first — it determines which template
        and slots to fill. Passes 2 (content) and 3 (design) then run
        in parallel since they're independent.

        When ``resume=True``, loads existing pass checkpoints and skips
        completed passes (avoids re-running expensive LLM calls on retry).
        """
        brief = sanitize_prompt(brief)

        # Load existing checkpoints if resuming
        cached_passes: dict[str, dict[str, Any]] = {}
        if resume and self._checkpoint_cb is not None:
            cached_passes = await self._load_pass_checkpoints()

        # Pass 1: Layout selection (must complete first)
        if "layout" in cached_passes:
            layout_data = cached_passes["layout"]
            template_selection = TemplateSelection(
                template_name=layout_data["template_name"],
                reasoning=layout_data["reasoning"],
                section_order=tuple(layout_data.get("section_order", ())),
                fallback_template=layout_data.get("fallback_template"),
            )
            section_decisions = tuple(
                SectionDecision(**sd) for sd in layout_data.get("section_decisions", [])
            )
            slot_details: list[dict[str, object]] = layout_data.get("slot_details", [])
            logger.info("scaffolder.layout_pass_resumed", template=template_selection.template_name)
        else:
            template_selection, section_decisions = await self._layout_pass(brief)

            # Resolve slot IDs from selected template
            template = self._resolve_template_for_slots(template_selection)
            slot_details = (
                [
                    {
                        "slot_id": s.slot_id,
                        "slot_type": s.slot_type,
                        "max_chars": s.max_chars,
                        "required": s.required,
                    }
                    for s in template.slots
                ]
                if template
                else []
            )
            # Checkpoint after layout pass
            await self._save_pass_checkpoint(
                "layout",
                0,
                serialize_layout_pass(
                    template_selection.template_name,
                    template_selection.reasoning,
                    template_selection.section_order,
                    template_selection.fallback_template,
                    section_decisions,
                    slot_details,
                ),
            )

        # Pass 2 + 3 in parallel (independent of each other)
        if "content_design" in cached_passes:
            cd_data = cached_passes["content_design"]
            slot_fills: tuple[SlotFill, ...] = tuple(SlotFill(**sf) for sf in cd_data["slot_fills"])
            design_tokens = DesignTokens(**cd_data["design_tokens"])
            logger.info("scaffolder.content_design_pass_resumed")
        else:
            # Re-resolve template if layout was resumed from checkpoint
            if "layout" in cached_passes:
                template = self._resolve_template_for_slots(template_selection)
                if not slot_details and template:
                    slot_details = [
                        {
                            "slot_id": s.slot_id,
                            "slot_type": s.slot_type,
                            "max_chars": s.max_chars,
                            "required": s.required,
                        }
                        for s in template.slots
                    ]

            slot_fills, design_tokens = await asyncio.gather(
                self._content_pass(brief, template_selection, slot_details),
                self._design_pass(brief, brand_config),
            )
            # Checkpoint after content+design pass
            await self._save_pass_checkpoint(
                "content_design",
                1,
                serialize_content_design_pass(slot_fills, design_tokens),
            )

        # Merge locked fills from design system (footer, logo override LLM fills)
        if self._design_system is not None:
            # Resolve template for slot IDs (may already be resolved above)
            template = self._resolve_template_for_slots(template_selection)
            available_slots: set[str] = {s.slot_id for s in template.slots} if template else set()
            locked = self._build_locked_fills(self._design_system, available_slots)
            if locked:
                fill_map = {sf.slot_id: sf for sf in slot_fills}
                fill_map.update(locked)
                slot_fills = tuple(fill_map.values())
                logger.info(
                    "scaffolder.locked_fills_applied",
                    locked_count=len(locked),
                    locked_slots=list(locked.keys()),
                )

        # Auto-detect tier strategy based on template modern CSS usage
        tier_strategy = self._detect_tier_strategy(template_selection)

        plan = EmailBuildPlan(
            template=template_selection,
            slot_fills=slot_fills,
            design_tokens=design_tokens,
            sections=section_decisions,
            preheader_text=self._extract_preheader(slot_fills),
            subject_line=self._extract_subject(slot_fills),
            tier_strategy=tier_strategy,
            confidence=0.85,
            reasoning=template_selection.reasoning,
        )

        logger.info(
            "scaffolder.pipeline_completed",
            template=template_selection.template_name,
            slots_filled=len(slot_fills),
            passes=3,
        )
        return plan

    async def _save_pass_checkpoint(
        self,
        pass_name: PassName,
        pass_index: int,
        data: dict[str, Any],
    ) -> None:
        """Fire-and-forget checkpoint save after a completed pass."""
        if self._checkpoint_cb is None:
            return
        try:
            from app.ai.agents.scaffolder.pipeline_checkpoint import PipelineCheckpoint

            checkpoint = PipelineCheckpoint(
                run_id=self._run_id,
                pass_name=pass_name,
                pass_index=pass_index,
                data=data,
            )
            await self._checkpoint_cb.save_pass(checkpoint)
            logger.info(
                "scaffolder.pass_checkpoint_saved",
                pass_name=pass_name,
                run_id=self._run_id,
            )
        except Exception:
            logger.warning(
                "scaffolder.pass_checkpoint_failed",
                pass_name=pass_name,
                run_id=self._run_id,
                exc_info=True,
            )

    async def _load_pass_checkpoints(self) -> dict[str, dict[str, Any]]:
        """Load existing pass checkpoints for resume. Returns {pass_name: data}."""
        if self._checkpoint_cb is None or not self._run_id:
            return {}
        try:
            checkpoints = await self._checkpoint_cb.load_passes(self._run_id)
            return {cp.pass_name: cp.data for cp in checkpoints}
        except Exception:
            logger.warning(
                "scaffolder.pass_checkpoint_load_failed",
                run_id=self._run_id,
                exc_info=True,
            )
            return {}

    def _resolve_template_for_slots(self, selection: TemplateSelection) -> GoldenTemplate | None:
        """Resolve template to extract slot definitions for Pass 2.

        For '__compose__' mode, composes the template from section blocks.
        For regular templates, looks up in the registry.
        """
        if selection.template_name == "__compose__":
            from app.ai.templates.composer import CompositionError, get_composer

            composer = get_composer()
            section_order = list(selection.section_order)
            if section_order:
                try:
                    return composer.compose(section_order)
                except CompositionError:
                    logger.warning(
                        "scaffolder.slot_resolution_fallback",
                        template=selection.template_name,
                    )
            # Fall through to fallback
            if selection.fallback_template:
                return self._registry.get(selection.fallback_template)
            return None

        template = self._registry.get(selection.template_name)
        if template is None and selection.fallback_template:
            template = self._registry.get(selection.fallback_template)
        return template

    # ── Conversion memory recall ──

    async def recall_conversion_context(
        self,
        brief: str,
        project_id: int | None,
    ) -> str | None:
        """Recall past conversion quality data for similar designs.

        Returns formatted context string or None if no relevant memories.
        """
        try:
            from app.core.config import get_settings
            from app.core.scoped_db import get_system_db_context
            from app.knowledge.embedding import get_embedding_provider
            from app.memory.service import MemoryService

            settings = get_settings()
            if not settings.design_sync.conversion_memory_enabled:
                return None

            async with get_system_db_context() as db:
                embedding_provider = get_embedding_provider(settings)
                service = MemoryService(db, embedding_provider)
                memories = await service.recall(
                    brief,
                    project_id=project_id,
                    agent_type="design_sync",
                    memory_type="semantic",
                    limit=6,
                )

            entries: list[str] = []
            for memory, score in memories:
                if score < 0.3:
                    continue
                meta: dict[str, object] = memory.metadata_json or {}
                if not meta.get("has_quality_issues"):
                    continue
                entries.append(memory.content)
                if len(entries) >= 3:
                    break

            if not entries:
                return None

            return "## Conversion History Insights\n" + "\n\n".join(entries)
        except Exception:
            logger.warning("scaffolder.conversion_recall_failed", exc_info=True)
            return None

    # ── Pass 1: Layout ──

    async def _layout_pass(
        self, brief: str
    ) -> tuple[TemplateSelection, tuple[SectionDecision, ...]]:
        """Pick template + section visibility. Lightweight pass."""
        available = self._registry.list_for_selection()
        template_list = "\n".join(
            f"- {m.name}: {m.display_name} ({m.layout_type}, {m.column_count}-col) — {m.description}"
            for m in available
        )

        # Load available section blocks for composition fallback
        from app.ai.templates.composer import get_composer

        composer = get_composer()
        section_blocks = composer.available_sections()
        section_list = ", ".join(section_blocks)

        # Phase 48: recall conversion history for context
        conversion_ctx = await self.recall_conversion_context(brief, project_id=None)
        conversion_block = f"{conversion_ctx}\n\n" if conversion_ctx else ""

        system = (
            f"{conversion_block}"
            "You are an email layout architect. Select the best template for the brief.\n\n"
            "Return a JSON object with these fields:\n"
            "- template_name: string (one of the available template names, or '__compose__' for custom composition)\n"
            "- reasoning: string (why this template fits)\n"
            "- section_order: array of strings (section block IDs, required when template_name is '__compose__')\n"
            "- fallback_template: string | null (backup golden template)\n"
            "- section_decisions: array of {section_name: string, background_color?: string, hidden?: boolean}\n\n"
            f"Available templates:\n{template_list}\n\n"
            "If no template is a good fit (confidence < 0.7), compose a custom layout:\n"
            '- Set template_name to "__compose__"\n'
            f"- Set section_order to an ordered list of section block IDs from: {section_list}\n"
            "- Set fallback_template to the closest matching golden template as backup\n"
            "- Always include at least one content block and one footer block\n\n"
            "Respond ONLY with valid JSON, no markdown fences."
        )
        user = f"Campaign brief:\n{brief}"

        parsed = await self._call_json(system, user)

        template_selection = TemplateSelection(
            template_name=str(parsed.get("template_name", "")),
            reasoning=str(parsed.get("reasoning", "")),
            section_order=tuple(parsed.get("section_order", ())),
            fallback_template=parsed.get("fallback_template"),
        )

        if not template_selection.template_name:
            raise PipelineError("Layout pass returned empty template_name")

        section_decisions = tuple(
            SectionDecision(
                section_name=str(s.get("section_name", "")),
                background_color=s.get("background_color"),
                padding=s.get("padding"),
                hidden=bool(s.get("hidden", False)),
            )
            for s in parsed.get("section_decisions", [])
        )

        logger.info(
            "scaffolder.layout_pass_completed",
            template=template_selection.template_name,
            sections=len(section_decisions),
        )
        return template_selection, section_decisions

    # ── Pass 2: Content ──

    async def _content_pass(
        self,
        brief: str,
        template: TemplateSelection,
        slot_details: list[dict[str, object]],
    ) -> tuple[SlotFill, ...]:
        """Fill each slot with content. Includes slot metadata for guidance."""
        slots_desc = "\n".join(
            f"- {s['slot_id']} (type: {s['slot_type']}, max_chars: {s.get('max_chars', 'unlimited')}, required: {s.get('required', True)})"
            for s in slot_details
        )

        system = (
            "You are an email content writer. Fill each content slot with appropriate text/HTML.\n\n"
            "Return a JSON object with:\n"
            "- slot_fills: array of {slot_id: string, content: string, is_personalisable: boolean}\n\n"
            "Rules:\n"
            "- Content must match the campaign brief tone and purpose\n"
            "- Respect max_chars limits\n"
            "- For CTA slots, provide short action-oriented text\n"
            "- For image slots, provide a descriptive placeholder URL\n"
            "- For URL slots (ending in _url), provide a realistic placeholder URL\n"
            "- Set is_personalisable=true for slots that benefit from personalisation (e.g., greetings, names)\n\n"
            f"Template: {template.template_name}\n"
            f"Slots to fill:\n{slots_desc}\n\n"
            "Respond ONLY with valid JSON, no markdown fences."
        )
        user = f"Campaign brief:\n{brief}"

        parsed = await self._call_json(system, user)

        fills = tuple(
            SlotFill(
                slot_id=str(sf.get("slot_id", "")),
                content=str(sf.get("content", "")),
                is_personalisable=bool(sf.get("is_personalisable", False)),
            )
            for sf in parsed.get("slot_fills", [])
        )

        if not fills:
            raise PipelineError("Content pass returned no slot_fills")

        logger.info(
            "scaffolder.content_pass_completed",
            slots_filled=len(fills),
        )
        return fills

    # ── Pass 3: Design ──

    async def _design_pass(
        self,
        brief: str,
        brand_config: dict[str, object] | None = None,
    ) -> DesignTokens:
        """Pick colours, fonts, spacing. Deterministic when design system exists."""
        if self._design_system is not None:
            return self._design_pass_from_system(self._design_system)
        return await self._design_pass_llm(brief, brand_config)

    @staticmethod
    def _design_pass_from_system(ds: DesignSystem) -> DesignTokens:
        """Build DesignTokens deterministically from client design system. Zero LLM calls."""
        from app.projects.design_system import (
            resolve_color_map,
            resolve_font_map,
            resolve_font_size_map,
            resolve_spacing_map,
        )

        colors = resolve_color_map(ds)
        fonts = resolve_font_map(ds)
        font_sizes = resolve_font_size_map(ds)
        spacing = resolve_spacing_map(ds)
        locked_roles = tuple(colors.keys())

        logger.info(
            "scaffolder.design_pass_from_system",
            color_roles=len(colors),
            locked_roles=len(locked_roles),
        )

        return DesignTokens(
            colors=colors,
            fonts=fonts,
            font_sizes=font_sizes,
            spacing=spacing,
            button_style=ds.button_style,
            source="design_system",
            locked_roles=locked_roles,
        )

    async def _design_pass_llm(
        self,
        brief: str,
        brand_config: dict[str, object] | None = None,
    ) -> DesignTokens:
        """LLM-generated design tokens (no design system configured)."""
        brand_context = ""
        if brand_config:
            brand_context = f"\nBrand guidelines:\n{json.dumps(brand_config, default=str)}"

        system = (
            "You are an email design architect. Choose design tokens for the email.\n\n"
            "Return a JSON object with:\n"
            '- colors: object with keys like "primary", "secondary", "background", "text", '
            '"heading", "body", "muted", "cta", "link" — all hex #RRGGBB values\n'
            '- fonts: object with "heading" and "body" as web-safe font stacks\n'
            '- button_style: "filled" | "outlined" | "text"\n\n'
            "Use web-safe hex colors. Font stacks must include system fallbacks."
            f"{brand_context}\n\n"
            "Respond ONLY with valid JSON, no markdown fences."
        )
        user = f"Campaign brief:\n{brief}"

        parsed = await self._call_json(system, user, max_tokens=1024)

        logger.info("scaffolder.design_pass_completed")

        return DesignTokens(
            colors=_extract_str_dict(parsed.get("colors", {})),
            fonts=_extract_str_dict(parsed.get("fonts", {})),
            font_sizes=_extract_str_dict(parsed.get("font_sizes", {})),
            spacing=_extract_str_dict(parsed.get("spacing", {})),
            button_style=parsed.get("button_style", "filled"),
            source="llm_generated",
        )

    # ── Helpers ──

    async def _call_json(
        self, system: str, user: str, max_tokens: int | None = None
    ) -> dict[str, Any]:
        """Make an LLM call and parse JSON from response. Retries once on parse failure."""
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]

        result = None
        for attempt in range(_MAX_RETRIES + 1):
            result = await self._provider.complete(
                messages,
                model_override=self._model,
                max_tokens=max_tokens or self._max_tokens,
            )
            parsed = _parse_json(result.content)
            if parsed:
                return parsed

            if attempt < _MAX_RETRIES:
                logger.warning(
                    "scaffolder.json_retry",
                    attempt=attempt + 1,
                    content_preview=result.content[:200],
                )
                # Append assistant response + retry instruction
                messages.append(Message(role="assistant", content=result.content))
                messages.append(
                    Message(
                        role="user",
                        content="That was not valid JSON. Please respond with ONLY a valid JSON object, no markdown fences or explanatory text.",
                    ),
                )

        raise PipelineError(
            f"Failed to parse JSON after {_MAX_RETRIES + 1} attempts. "
            f"Last response: {result.content[:200] if result else 'no response'}"
        )

    @staticmethod
    def _build_locked_fills(
        ds: DesignSystem,
        available_slots: set[str],
    ) -> dict[str, SlotFill]:
        """Build locked fills from whatever the design system provides.

        Client-agnostic: only locks slots that (a) exist in the template
        and (b) the design system has a value for. Skips everything else.
        """
        locked: dict[str, SlotFill] = {}

        def _lock(slot_id: str, content: str) -> None:
            if slot_id in available_slots and content:
                locked[slot_id] = SlotFill(
                    slot_id=slot_id, content=content, is_personalisable=False
                )

        if ds.footer:
            _lock("footer_company", ds.footer.company_name)
            _lock("footer_legal", ds.footer.legal_text)
            _lock("footer_address", ds.footer.address)
            _lock("footer_unsubscribe", ds.footer.unsubscribe_text)

        if ds.logo:
            _lock("logo_url", ds.logo.url)
            _lock("logo_alt", ds.logo.alt_text)

        return locked

    @staticmethod
    def _extract_preheader(fills: tuple[SlotFill, ...]) -> str:
        """Extract preheader from slot fills if present."""
        for fill in fills:
            if fill.slot_id == "preheader":
                return fill.content
        return ""

    @staticmethod
    def _extract_subject(fills: tuple[SlotFill, ...]) -> str:
        """Extract subject line from slot fills if present."""
        for fill in fills:
            if fill.slot_id == "subject_line":
                return fill.content
        return ""

    async def execute_tree(
        self,
        brief: str,
        brand_config: dict[str, object] | None = None,
    ) -> EmailTree:
        """Execute 3-pass pipeline in tree mode. Returns EmailTree.

        Pass 1: Select components from manifest (tree layout)
        Pass 2: Fill per-component slots (tree content)  } parallel
        Pass 3: Design tokens (reuses _design_pass)      }
        """
        from app.ai.agents.scaffolder.prompt import (
            build_component_manifest_prompt,
            build_tree_content_system_prompt,
            build_tree_layout_system_prompt,
        )
        from app.ai.agents.scaffolder.tree_builder import (
            ComponentSelection,
            TreeBuilder,
            _build_manifest_index,
            _infer_slot_value,
        )

        brief = sanitize_prompt(brief)

        # Build manifest index for slot definitions
        manifest_slugs, slot_defs = _build_manifest_index()

        # Pass 1: Tree layout — select components
        manifest_prompt = build_component_manifest_prompt()
        layout_system = build_tree_layout_system_prompt(manifest_prompt)
        layout_parsed = await self._call_json(layout_system, f"Campaign brief:\n{brief}")

        component_selections = [
            ComponentSelection(
                component_slug=str(s.get("component_slug", "")),
                rationale=str(s.get("rationale", "")),
            )
            for s in layout_parsed.get("sections", [])
        ]

        if not component_selections:
            raise PipelineError("Tree layout pass returned no sections")

        subject = str(layout_parsed.get("subject", ""))
        preheader = str(layout_parsed.get("preheader", ""))

        logger.info(
            "scaffolder.tree_layout_completed",
            sections=len(component_selections),
            slugs=[cs.component_slug for cs in component_selections],
        )

        # Prepare per-section slot definitions for content pass
        section_specs: list[dict[str, Any]] = []
        for cs in component_selections:
            slug_defs = slot_defs.get(cs.component_slug, [])
            section_specs.append(
                {
                    "component_slug": cs.component_slug,
                    "slot_definitions": slug_defs,
                }
            )

        # Pass 2 (tree content) + Pass 3 (design) in parallel
        content_system = build_tree_content_system_prompt(section_specs)

        async def _tree_content_pass() -> dict[int, dict[str, Any]]:
            content_parsed = await self._call_json(content_system, f"Campaign brief:\n{brief}")
            fills_by_section: dict[int, dict[str, Any]] = {}
            for section_data in content_parsed.get("sections", []):
                idx = int(section_data.get("index", 0))
                raw_fills = section_data.get("fills", {})
                fills_by_section[idx] = raw_fills
            return fills_by_section

        raw_fills_by_section, design_tokens = await asyncio.gather(
            _tree_content_pass(),
            self._design_pass(brief, brand_config),
        )

        logger.info(
            "scaffolder.tree_content_completed",
            sections_filled=len(raw_fills_by_section),
        )

        # Convert raw fills to typed SlotValues
        typed_fills_by_section: dict[int, dict[str, Any]] = {}
        for idx, raw_fills in raw_fills_by_section.items():
            typed: dict[str, Any] = {}
            # Look up slot_type from manifest
            slug = (
                component_selections[idx].component_slug if idx < len(component_selections) else ""
            )
            slug_slot_defs = slot_defs.get(slug, [])
            slot_type_map = {
                s.get("slot_id", ""): s.get("slot_type", "content") for s in slug_slot_defs
            }

            for slot_id, content in raw_fills.items():
                slot_type = slot_type_map.get(slot_id, "content")
                typed[slot_id] = _infer_slot_value(slot_id, content, slot_type)
            typed_fills_by_section[idx] = typed

        # Assemble EmailTree
        design_dict: dict[str, dict[str, str]] = {
            "colors": design_tokens.colors,
            "fonts": design_tokens.fonts,
        }

        builder = TreeBuilder(manifest_slugs, slot_defs)
        tree = builder.build(
            component_selections=component_selections,
            slot_fills_by_section=typed_fills_by_section,
            design_tokens=design_dict,
            subject=subject,
            preheader=preheader,
        )

        logger.info(
            "scaffolder.tree_pipeline_completed",
            sections=len(tree.sections),
            subject=tree.metadata.subject,
        )

        return tree

    async def execute_variants(
        self,
        brief: str,
        count: int = 3,
        brand_config: dict[str, object] | None = None,
    ) -> CampaignVariantSet:
        """Execute multi-variant pipeline: shared layout+design, parallel content passes.

        1. Layout pass (once) — shared template + sections
        2. Design pass (once) — shared design tokens
        3. Strategy selection — LLM picks top N strategies for this brief
        4. Content pass x N (parallel) — one per strategy with prompt modifier
        5. Assembly x N (parallel) — deterministic HTML assembly
        6. QA x N (parallel) — all variants checked
        7. Comparison matrix — side-by-side diff
        """
        from app.ai.agents.scaffolder.variant_generator import (
            build_comparison_matrix,
            build_strategy_prompt_modifier,
            select_strategies,
        )
        from app.ai.agents.scaffolder.variant_schemas import (
            CampaignVariantSet,
            StrategyName,
            VariantPlan,
            VariantResult,
        )

        brief = sanitize_prompt(brief)

        # Step 1: Layout pass (shared)
        template_selection, section_decisions = await self._layout_pass(brief)
        template = self._resolve_template_for_slots(template_selection)
        slot_details: list[dict[str, object]] = (
            [
                {
                    "slot_id": s.slot_id,
                    "slot_type": s.slot_type,
                    "max_chars": s.max_chars,
                    "required": s.required,
                }
                for s in template.slots
            ]
            if template
            else []
        )

        # Step 2: Design pass (shared)
        design_tokens = await self._design_pass(brief, brand_config)

        # Step 3: Strategy selection
        strategies = await select_strategies(brief, count, self._call_json)
        if not strategies:
            raise PipelineError("Strategy selection returned no strategies")

        # Step 4: Parallel content passes (one per strategy)
        variant_labels = ("A", "B", "C", "D", "E")

        async def _content_for_strategy(
            idx: int,
            strategy_name: StrategyName,
            hypothesis: str,
            differentiator: str,
        ) -> VariantPlan:
            modifier = build_strategy_prompt_modifier(strategy_name)
            modified_brief = f"{brief}\n\n{modifier}"
            slot_fills = await self._content_pass(modified_brief, template_selection, slot_details)

            return VariantPlan(
                variant_id=variant_labels[idx],
                strategy_name=strategy_name,
                hypothesis=hypothesis,
                slot_fills=slot_fills,
                subject_line=self._extract_subject(slot_fills),
                preheader=self._extract_preheader(slot_fills),
                predicted_differentiator=differentiator,
            )

        variant_plans = list(
            await asyncio.gather(
                *(
                    _content_for_strategy(i, name, hyp, diff)
                    for i, (name, hyp, diff) in enumerate(strategies)
                )
            )
        )

        # Merge locked fills from design system (same as single-email path)
        locked: dict[str, SlotFill] = {}
        if self._design_system is not None:
            available_slots: set[str] = {s.slot_id for s in template.slots} if template else set()
            locked = self._build_locked_fills(self._design_system, available_slots)

        # Step 5: Assemble + QA each variant (parallel)
        from app.ai.agents.scaffolder.assembler import TemplateAssembler
        from app.ai.shared import sanitize_html_xss
        from app.qa_engine.checks import ALL_CHECKS
        from app.qa_engine.schemas import QACheckResult

        assembler = TemplateAssembler()
        tier_strategy = self._detect_tier_strategy(template_selection)

        async def _assemble_and_qa(vp: VariantPlan) -> VariantResult:
            # Apply locked fills
            fills = vp.slot_fills
            if locked:
                fill_map = {sf.slot_id: sf for sf in fills}
                fill_map.update(locked)
                fills = tuple(fill_map.values())
            plan = EmailBuildPlan(
                template=template_selection,
                slot_fills=fills,
                design_tokens=design_tokens,
                sections=section_decisions,
                preheader_text=vp.preheader,
                subject_line=vp.subject_line,
                tier_strategy=tier_strategy,
                confidence=0.85,
                reasoning=f"Variant {vp.variant_id}: {vp.strategy_name}",
            )

            html = assembler.assemble(plan)
            html = sanitize_html_xss(html, profile="scaffolder")

            # QA (reuse base agent QA pattern)
            qa_results: list[QACheckResult] = []
            for check in ALL_CHECKS:
                qa_results.append(await check.run(html))
            qa_passed = all(r.passed for r in qa_results)

            return VariantResult(
                variant_id=vp.variant_id,
                strategy_name=vp.strategy_name,
                hypothesis=vp.hypothesis,
                predicted_differentiator=vp.predicted_differentiator,
                subject_line=vp.subject_line,
                preheader=vp.preheader,
                html=html,
                build_plan=plan,
                qa_results=qa_results,
                qa_passed=qa_passed,
            )

        variant_results = tuple(
            await asyncio.gather(*(_assemble_and_qa(vp) for vp in variant_plans))
        )

        # Step 6: Comparison matrix
        comparison = build_comparison_matrix(variant_plans)

        logger.info(
            "scaffolder.variants_completed",
            variant_count=len(variant_results),
            all_passed=all(vr.qa_passed for vr in variant_results),
            strategies=[vr.strategy_name for vr in variant_results],
        )

        return CampaignVariantSet(
            brief=brief,
            base_template=template_selection.template_name,
            base_design_tokens=dataclasses.asdict(design_tokens),
            variants=variant_results,
            comparison=comparison,
        )

    def _detect_tier_strategy(
        self, selection: TemplateSelection
    ) -> Literal["universal", "progressive"]:
        """Detect if the template uses modern CSS requiring progressive enhancement.

        Scans template HTML for flexbox/grid in inline styles or <style> blocks.
        If found, recommends progressive tier strategy for MSO compatibility.
        """
        template = self._resolve_template_for_slots(selection)
        if template is None:
            return "universal"

        template_html = template.html
        modern_css_re = re.compile(
            r"display\s*:\s*(?:flex|grid|inline-flex|inline-grid)",
            re.IGNORECASE,
        )
        if modern_css_re.search(template_html):
            logger.info(
                "scaffolder.tier_strategy_detected",
                strategy="progressive",
                template=selection.template_name,
            )
            return "progressive"

        return "universal"


def _parse_json(content: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response. Handles code fences and raw JSON."""
    # Try code fence first
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # Try raw JSON parse
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Try to find JSON object boundaries
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    return None


def _extract_str_dict(raw: object) -> dict[str, str]:
    """Safely extract dict[str, str] from LLM JSON output."""
    if not isinstance(raw, dict):
        return {}
    d = cast(dict[str, Any], raw)
    return {str(k): str(v) for k, v in d.items() if isinstance(v, str)}
