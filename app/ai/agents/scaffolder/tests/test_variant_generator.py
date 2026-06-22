"""Tests for multi-variant campaign assembly."""

import pytest
from pydantic import ValidationError

from app.ai.agents.scaffolder.variant_generator import (
    build_comparison_matrix,
    build_strategy_prompt_modifier,
)
from app.ai.agents.scaffolder.variant_schemas import (
    STRATEGY_DESCRIPTIONS,
    VariantPlan,
)
from app.ai.agents.schemas.build_plan import SlotFill
from app.ai.exceptions import AIExecutionError


class TestStrategyPromptModifier:
    """Test that each strategy produces a distinct prompt modifier."""

    @pytest.mark.parametrize("strategy", list(STRATEGY_DESCRIPTIONS.keys()))
    def test_modifier_exists_for_each_strategy(self, strategy: str) -> None:
        modifier = build_strategy_prompt_modifier(strategy)  # type: ignore[arg-type]
        assert len(modifier) > 50
        assert "CONTENT STRATEGY" in modifier

    def test_modifiers_are_distinct(self) -> None:
        modifiers = {s: build_strategy_prompt_modifier(s) for s in STRATEGY_DESCRIPTIONS}
        values = list(modifiers.values())
        assert len(set(values)) == len(values), "All modifiers should be unique"


class TestComparisonMatrix:
    """Test comparison matrix generation."""

    def _make_variant(self, vid: str, strategy: str, subject: str, cta_content: str) -> VariantPlan:
        return VariantPlan(
            variant_id=vid,
            strategy_name=strategy,  # type: ignore[arg-type]
            hypothesis=f"Test hypothesis for {strategy}",
            slot_fills=(
                SlotFill(slot_id="hero_heading", content=f"Hero for {strategy}"),
                SlotFill(slot_id="cta_text", content=cta_content),
            ),
            subject_line=subject,
            preheader=f"Preheader {vid}",
            predicted_differentiator=f"Diff {vid}",
        )

    def test_matrix_captures_subject_line_differences(self) -> None:
        variants = [
            self._make_variant("A", "urgency_driven", "Last chance!", "Buy now"),
            self._make_variant("B", "benefit_focused", "Save 50% today", "Start saving"),
        ]
        matrix = build_comparison_matrix(variants)
        assert matrix.subject_lines == {"A": "Last chance!", "B": "Save 50% today"}

    def test_matrix_identifies_differing_slots(self) -> None:
        variants = [
            self._make_variant("A", "urgency_driven", "Subj A", "Buy now!"),
            self._make_variant("B", "benefit_focused", "Subj B", "Start saving"),
        ]
        matrix = build_comparison_matrix(variants)
        diff_ids = [d.slot_id for d in matrix.slot_differences]
        assert "cta_text" in diff_ids
        assert "hero_heading" in diff_ids

    def test_identical_slots_excluded_from_diff(self) -> None:
        v1 = VariantPlan(
            variant_id="A",
            strategy_name="urgency_driven",
            hypothesis="H1",
            slot_fills=(SlotFill(slot_id="footer", content="© 2026 Acme"),),
            subject_line="S1",
            preheader="P1",
            predicted_differentiator="D1",
        )
        v2 = VariantPlan(
            variant_id="B",
            strategy_name="benefit_focused",
            hypothesis="H2",
            slot_fills=(SlotFill(slot_id="footer", content="© 2026 Acme"),),
            subject_line="S2",
            preheader="P2",
            predicted_differentiator="D2",
        )
        matrix = build_comparison_matrix([v1, v2])
        diff_ids = [d.slot_id for d in matrix.slot_differences]
        assert "footer" not in diff_ids


class TestVariantSchemas:
    """Test variant count validation."""

    def test_variant_request_bounds_too_low(self) -> None:
        from app.ai.agents.scaffolder.schemas import VariantRequest

        with pytest.raises(ValidationError):
            VariantRequest(brief="A" * 20, variant_count=1)

    def test_variant_request_bounds_too_high(self) -> None:
        from app.ai.agents.scaffolder.schemas import VariantRequest

        with pytest.raises(ValidationError):
            VariantRequest(brief="A" * 20, variant_count=6)

    def test_variant_request_valid(self) -> None:
        from app.ai.agents.scaffolder.schemas import VariantRequest

        req = VariantRequest(brief="Summer sale for premium subscribers", variant_count=3)
        assert req.variant_count == 3


class TestSelectStrategies:
    """Test LLM strategy selection with mocked call_json."""

    @pytest.mark.asyncio
    async def test_returns_requested_count(self) -> None:
        """select_strategies returns exactly N strategies."""
        from unittest.mock import AsyncMock

        from app.ai.agents.scaffolder.variant_generator import select_strategies

        mock_call = AsyncMock(
            return_value={
                "strategies": [
                    {
                        "strategy_name": "urgency_driven",
                        "hypothesis": "H1",
                        "predicted_differentiator": "D1",
                    },
                    {
                        "strategy_name": "benefit_focused",
                        "hypothesis": "H2",
                        "predicted_differentiator": "D2",
                    },
                    {
                        "strategy_name": "social_proof",
                        "hypothesis": "H3",
                        "predicted_differentiator": "D3",
                    },
                ]
            }
        )
        result = await select_strategies("Summer sale campaign", 3, mock_call)
        assert len(result) == 3
        assert result[0][0] == "urgency_driven"

    @pytest.mark.asyncio
    async def test_handles_fewer_than_requested(self) -> None:
        """LLM returns fewer strategies -> returns what's available."""
        from unittest.mock import AsyncMock

        from app.ai.agents.scaffolder.variant_generator import select_strategies

        mock_call = AsyncMock(
            return_value={
                "strategies": [
                    {
                        "strategy_name": "urgency_driven",
                        "hypothesis": "H1",
                        "predicted_differentiator": "D1",
                    },
                ]
            }
        )
        result = await select_strategies("Brief", 3, mock_call)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filters_unknown_strategies(self) -> None:
        """Unknown strategy names are filtered out."""
        from unittest.mock import AsyncMock

        from app.ai.agents.scaffolder.variant_generator import select_strategies

        mock_call = AsyncMock(
            return_value={
                "strategies": [
                    {
                        "strategy_name": "urgency_driven",
                        "hypothesis": "H1",
                        "predicted_differentiator": "D1",
                    },
                    {
                        "strategy_name": "nonexistent_strategy",
                        "hypothesis": "H2",
                        "predicted_differentiator": "D2",
                    },
                ]
            }
        )
        result = await select_strategies("Brief", 3, mock_call)
        assert len(result) == 1
        assert result[0][0] == "urgency_driven"


class TestVariantPlanImmutability:
    """Test VariantPlan frozen dataclass."""

    def test_variant_plan_immutable(self) -> None:
        """VariantPlan is frozen — can't mutate fields."""
        plan = VariantPlan(
            variant_id="A",
            strategy_name="urgency_driven",
            hypothesis="H",
            slot_fills=(SlotFill(slot_id="cta", content="Buy"),),
            subject_line="Subj",
            preheader="Pre",
            predicted_differentiator="Diff",
        )
        with pytest.raises(AttributeError):
            plan.variant_id = "B"  # type: ignore[misc]


class TestCampaignVariantSetStructure:
    """Test CampaignVariantSet top-level structure."""

    def test_set_contains_comparison(self) -> None:
        """CampaignVariantSet includes comparison matrix."""
        from app.ai.agents.scaffolder.variant_schemas import CampaignVariantSet

        v1 = VariantPlan(
            variant_id="A",
            strategy_name="urgency_driven",
            hypothesis="H1",
            slot_fills=(SlotFill(slot_id="cta", content="Buy now"),),
            subject_line="Last chance!",
            preheader="Don't miss out",
            predicted_differentiator="Urgency",
        )
        v2 = VariantPlan(
            variant_id="B",
            strategy_name="benefit_focused",
            hypothesis="H2",
            slot_fills=(SlotFill(slot_id="cta", content="Save more"),),
            subject_line="Save 50%",
            preheader="Great deals",
            predicted_differentiator="Value",
        )
        matrix = build_comparison_matrix([v1, v2])
        variant_set = CampaignVariantSet(
            brief="Test brief",
            base_template="promo_1col",
            base_design_tokens={},
            variants=(),
            comparison=matrix,
        )
        assert variant_set.comparison is not None
        assert len(variant_set.comparison.subject_lines) == 2

    def test_empty_variants_allowed(self) -> None:
        """CampaignVariantSet with empty variants tuple."""
        from app.ai.agents.scaffolder.variant_schemas import CampaignVariantSet, ComparisonMatrix

        matrix = ComparisonMatrix(
            subject_lines={},
            preheaders={},
            slot_differences=(),
            strategy_summary={},
        )
        variant_set = CampaignVariantSet(
            brief="Empty test",
            base_template="promo_1col",
            base_design_tokens={},
            variants=(),
            comparison=matrix,
        )
        assert len(variant_set.variants) == 0


class TestVariantServiceValidation:
    """Test ScaffolderService.generate_variants config validation."""

    @pytest.mark.asyncio
    async def test_exceeds_max_raises(self) -> None:
        """variant_count > max_variants -> error."""
        from unittest.mock import MagicMock, patch

        from app.ai.agents.scaffolder.schemas import VariantRequest

        mock_settings = MagicMock()
        mock_settings.variants.max_variants = 3

        with patch("app.ai.agents.scaffolder.service.get_settings", return_value=mock_settings):
            from app.ai.agents.scaffolder.service import ScaffolderService

            svc = ScaffolderService()
            with pytest.raises(AIExecutionError):
                await svc.generate_variants(
                    VariantRequest(brief="Test brief for campaign", variant_count=5)
                )
