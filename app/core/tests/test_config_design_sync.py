"""Tests for the ``DesignSyncConfig`` field surface (Phase 50.6.4 PR-1).

PR-1 constantizes over-engineered internal knobs off ``DesignSyncConfig`` into
``app.design_sync.tuning`` with no behaviour change (each constant equals the
field's former default). These tests pin the shrunken config surface so a
future re-addition — or a botched constantize revert — is caught by the gate.
"""

from __future__ import annotations

from app.core.config.design_sync import DesignSyncConfig

# The 8 fields moved to ``app.design_sync.tuning`` in Phase 50.6.4 PR-1.
_CONSTANTIZED_FIELDS = frozenset(
    {
        "fidelity_ssim_window",
        "fidelity_blur_sigma",
        "fidelity_figma_scale",
        "vlm_classification_confidence_threshold",
        "band_grouping_absorb_spacers",
        "nested_card_perceptual_threshold",
        "rule_7_alignment_tolerance_px",
        "physical_card_min_signals",
    }
)


def test_design_sync_field_count_bounded() -> None:
    # PR-1 (constantize) landing under the §50.6.4 conservative-keep rule.
    # ≤45 was the aspiration, but the do-not-touch set (vlm_verify_*/
    # custom_component_*/sibling_*/…) reserves ~20 fields for PR-2, so PR-1's
    # safe pool tops out at 8 → 57. PR-2 (retire-feature) drives toward ≤30.
    # +1 (58): 53.3d ``frame_export_fallback_enabled`` — plan-mandated kill
    # switch, cull-tracked in feature-flags.yaml (removal 2026-10-06); counts
    # against the PR-2 retirement pool, not new sprawl headroom.
    assert len(DesignSyncConfig.model_fields) <= 58


def test_constantized_fields_removed() -> None:
    # The 8 constantized fields must no longer be config fields — reads go
    # through the ``app.design_sync.tuning`` constants instead.
    assert _CONSTANTIZED_FIELDS.isdisjoint(DesignSyncConfig.model_fields)
