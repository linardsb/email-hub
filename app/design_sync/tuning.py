"""Threshold knobs for design_sync — promoted from env-tunable fields (F035).

These constants used to live on ``DesignSyncConfig`` as Pydantic fields
configurable via ``DESIGN_SYNC__*`` env vars, but no deployment was tuning
them. Moving them here cuts the config surface area without changing
runtime behaviour. Override in a fork by editing this file directly.
"""

from typing import Final

# ── Match confidence ──────────────────────────────────────────────────
LOW_MATCH_CONFIDENCE_THRESHOLD: Final[float] = 0.6
"""Confidence below which a section match is flagged as low-quality."""

# ── Image / colour processing ─────────────────────────────────────────
OPACITY_COMPOSITE_BG: Final[str] = "#FFFFFF"
"""Background hex used for alpha-compositing semi-transparent fills."""

# ── Sibling / repeating-group detection ───────────────────────────────
SIBLING_MIN_GROUP: Final[int] = 2
SIBLING_SIMILARITY_THRESHOLD: Final[float] = 0.8

# ── Nested-card + frame-rule heuristics ───────────────────────────────
NESTED_CARD_PERCEPTUAL_THRESHOLD: Final[int] = 30
"""Per-channel RGB Δ above which a centroid colour is treated as a card."""

PHYSICAL_CARD_MIN_SIGNALS: Final[int] = 2
"""Minimum signals required to classify a frame as a physical card."""

RULE_7_ALIGNMENT_TOLERANCE_PX: Final[float] = 4.0
"""Pill x-offset tolerance for Rule 7 alignment classification."""

# ── Visual fidelity scoring (SSIM) ────────────────────────────────────
FIDELITY_SSIM_WINDOW: Final[int] = 7
"""SSIM Gaussian window (odd, ≤ min image dim)."""

FIDELITY_BLUR_SIGMA: Final[float] = 1.0
"""Gaussian blur applied before SSIM (anti-aliasing tolerance)."""

FIDELITY_FIGMA_SCALE: Final[float] = 2.0
"""Figma export scale factor for fidelity frame capture."""

# ── VLM section classification ────────────────────────────────────────
VLM_CLASSIFICATION_CONFIDENCE_THRESHOLD: Final[float] = 0.7
"""Confidence floor for accepting a VLM section-type classification."""

# ── Band grouping (wrapper regrouping) ────────────────────────────────
BAND_GROUPING_ABSORB_SPACERS: Final[bool] = True
"""Drop SPACER-typed pseudo-sections inside a grouped band (render as padding)."""

# ── VLM verify loop knobs ─────────────────────────────────────────────
VLM_VERIFY_DIFF_SKIP_THRESHOLD: Final[float] = 2.0
"""Verification-loop skip threshold — diff %% under which we skip the LLM."""

VLM_VERIFY_MAX_ITERATIONS: Final[int] = 3
VLM_VERIFY_TARGET_FIDELITY: Final[float] = 0.97
VLM_VERIFY_CONFIDENCE_THRESHOLD: Final[float] = 0.7
