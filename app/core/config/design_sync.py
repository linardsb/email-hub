"""Design tool sync settings."""

from pydantic import BaseModel


class DesignSyncConfig(BaseModel):
    """Design tool sync settings."""

    encryption_key: str = ""  # If empty, derived from jwt_secret_key via PBKDF2
    asset_storage_path: str = "data/design-assets"
    asset_max_width: int = 1200  # Max width for email images; 1200 = 2x retina for 600px containers
    # Penpot integration (self-hosted design tool)
    penpot_enabled: bool = False
    penpot_base_url: str = "http://localhost:9001"
    penpot_request_timeout: float = 30.0
    converter_enabled: bool = True  # DESIGN_SYNC__CONVERTER_ENABLED (provider-agnostic)
    figma_variables_enabled: bool = True  # DESIGN_SYNC__FIGMA_VARIABLES_ENABLED
    ai_layout_enabled: bool = True  # DESIGN_SYNC__AI_LAYOUT_ENABLED
    # Visual fidelity scoring (SSIM comparison of Figma frames vs rendered HTML)
    fidelity_enabled: bool = False  # DESIGN_SYNC__FIDELITY_ENABLED
    fidelity_ssim_window: int = 7  # SSIM Gaussian window (odd, ≤ min image dim)
    fidelity_blur_sigma: float = 1.0  # Gaussian blur before SSIM (anti-aliasing tolerance)
    fidelity_figma_scale: float = 2.0  # Figma export scale factor
    # Figma webhooks (live preview sync)
    figma_webhook_enabled: bool = False  # DESIGN_SYNC__FIGMA_WEBHOOK_ENABLED
    figma_webhook_passcode: str = ""  # DESIGN_SYNC__FIGMA_WEBHOOK_PASSCODE (HMAC secret)
    figma_webhook_callback_url: str = ""  # DESIGN_SYNC__FIGMA_WEBHOOK_CALLBACK_URL
    webhook_debounce_seconds: int = 5  # DESIGN_SYNC__WEBHOOK_DEBOUNCE_SECONDS
    # Section cache (35.10 — incremental conversion)
    section_cache_enabled: bool = True  # DESIGN_SYNC__SECTION_CACHE_ENABLED
    section_cache_memory_max: int = 500  # DESIGN_SYNC__SECTION_CACHE_MEMORY_MAX
    section_cache_redis_ttl: int = 3600  # DESIGN_SYNC__SECTION_CACHE_REDIS_TTL (seconds)
    # MJML import (36.4)
    mjml_import_enabled: bool = True  # DESIGN_SYNC__MJML_IMPORT_ENABLED
    # HTML reverse-engineering import (36.5)
    html_import_ai_enabled: bool = True  # DESIGN_SYNC__HTML_IMPORT_AI_ENABLED
    html_import_max_size_bytes: int = 2_097_152  # DESIGN_SYNC__HTML_IMPORT_MAX_SIZE_BYTES (2 MB)
    # Converter learning loop (Phase 48)
    conversion_memory_enabled: bool = True  # DESIGN_SYNC__CONVERSION_MEMORY_ENABLED
    conversion_traces_enabled: bool = True  # DESIGN_SYNC__CONVERSION_TRACES_ENABLED
    conversion_traces_path: str = (
        "traces/converter_traces.jsonl"  # DESIGN_SYNC__CONVERSION_TRACES_PATH
    )
    # Adjacent-section background color propagation (Phase 41.2)
    bgcolor_propagation_enabled: bool = True  # DESIGN_SYNC__BGCOLOR_PROPAGATION_ENABLED
    # VLM-assisted section classification fallback (Phase 41.5)
    vlm_fallback_enabled: bool = False  # DESIGN_SYNC__VLM_FALLBACK_ENABLED
    # VLM-assisted section type classification in layout analysis (Phase 41.7)
    vlm_classification_enabled: bool = False  # DESIGN_SYNC__VLM_CLASSIFICATION_ENABLED
    vlm_classification_model: str = (
        ""  # DESIGN_SYNC__VLM_CLASSIFICATION_MODEL (empty = default routing)
    )
    vlm_classification_confidence_threshold: float = (
        0.7  # DESIGN_SYNC__VLM_CLASSIFICATION_CONFIDENCE_THRESHOLD
    )
    vlm_classification_timeout: float = 15.0  # DESIGN_SYNC__VLM_CLASSIFICATION_TIMEOUT (seconds)
    # VLM visual verification loop (Phase 47.2) — RETIRED at 53.4 (2026-06-12):
    # stays default-off until the 2026-09-10 cull; reopen conditions in
    # .agents/plans/53-4-vlm-retirement.md. Do not credit it in fidelity claims.
    vlm_verify_enabled: bool = False  # DESIGN_SYNC__VLM_VERIFY_ENABLED
    vlm_verify_model: str = ""  # DESIGN_SYNC__VLM_VERIFY_MODEL (empty = auto-resolve vision)
    vlm_verify_timeout: float = 30.0  # DESIGN_SYNC__VLM_VERIFY_TIMEOUT (seconds)
    vlm_verify_diff_skip_threshold: float = 2.0  # DESIGN_SYNC__VLM_VERIFY_DIFF_SKIP_THRESHOLD (%)
    vlm_verify_max_sections: int = 20  # DESIGN_SYNC__VLM_VERIFY_MAX_SECTIONS
    # Verification loop parameters (Phase 47.4)
    vlm_verify_max_iterations: int = 3  # DESIGN_SYNC__VLM_VERIFY_MAX_ITERATIONS
    vlm_verify_target_fidelity: float = 0.97  # DESIGN_SYNC__VLM_VERIFY_TARGET_FIDELITY
    vlm_verify_confidence_threshold: float = 0.7  # DESIGN_SYNC__VLM_VERIFY_CONFIDENCE_THRESHOLD
    # Pipeline integration (Phase 47.5)
    vlm_verify_correction_confidence: float = 0.6  # DESIGN_SYNC__VLM_VERIFY_CORRECTION_CONFIDENCE
    vlm_verify_client: str = "gmail_web"  # DESIGN_SYNC__VLM_VERIFY_CLIENT (rendering target)
    # Custom component generation via Scaffolder for low-confidence matches (Phase 47.8)
    custom_component_enabled: bool = False  # DESIGN_SYNC__CUSTOM_COMPONENT_ENABLED
    custom_component_confidence_threshold: float = (
        # Raised from 0.6 → 0.85 because observed matcher scores are 0.85+ for
        # every real case, so the previous default guaranteed the AI fallback
        # never fired even with custom_component_enabled=true.
        0.85  # DESIGN_SYNC__CUSTOM_COMPONENT_CONFIDENCE_THRESHOLD
    )
    custom_component_model: str = ""  # DESIGN_SYNC__CUSTOM_COMPONENT_MODEL (empty = default)
    custom_component_max_per_email: int = 3  # DESIGN_SYNC__CUSTOM_COMPONENT_MAX_PER_EMAIL
    # Data-driven converter regression (Phase 49.9)
    regression_dir: str = "data/debug"  # DESIGN_SYNC__REGRESSION_DIR
    regression_strict: bool = False  # DESIGN_SYNC__REGRESSION_STRICT
    # Sibling pattern detection — repeated-content grouping (Phase 49.1)
    sibling_detection_enabled: bool = True  # DESIGN_SYNC__SIBLING_DETECTION_ENABLED
    sibling_min_group: int = 2  # DESIGN_SYNC__SIBLING_MIN_GROUP
    sibling_similarity_threshold: float = 0.8  # DESIGN_SYNC__SIBLING_SIMILARITY_THRESHOLD
    # Wrapper band grouping — Phase 53 Track C, default ON since the 53.1 fork
    # gate ratified fork (a) (2026-06-12, .agents/plans/53-1-fork-decision.md).
    # Regroup sections sharing a ``parent_wrapper_id`` (stamped by the wrapper
    # unwrap pre-pass) back into one band, instead of re-deriving similarity.
    # Design-agnostic: keys only on the exploded-wrapper id, never on any
    # specific design. Env var is the kill switch; cull the flag once soaked
    # (review by 2026-09-10 per `make flag-audit` lifecycle).
    band_grouping_enabled: bool = True  # DESIGN_SYNC__BAND_GROUPING_ENABLED
    # When band grouping is on, drop SPACER-typed pseudo-sections inside a band
    # (they render as padding, not their own row). Phase 53 Track C2.
    band_grouping_absorb_spacers: bool = True  # DESIGN_SYNC__BAND_GROUPING_ABSORB_SPACERS
    # Semantic peel/keep seam — Phase 53 D3 spike (default OFF; flag-off output
    # byte-identical). Peel `mj-wrapper → single mj-section → N column` grandkids
    # into their own sections when the content-scale heuristic reads them as
    # cards (imagery / card-height) rather than an atomic stat/nav row. The
    # under-count residual is SEMANTIC (53.1 gate) — this is the discriminator.
    semantic_peel_enabled: bool = False  # DESIGN_SYNC__SEMANTIC_PEEL_ENABLED
    # Per-email token scoping — scope to target frame subtree (Phase 49.6)
    token_scoping_enabled: bool = True  # DESIGN_SYNC__TOKEN_SCOPING_ENABLED
    # Design-sync → EmailTree bridge (Phase 49.8)
    tree_bridge_enabled: bool = False  # DESIGN_SYNC__TREE_BRIDGE_ENABLED
    # Full-design PNG threading for global visual context (Phase 50.1, Gap 9)
    full_design_png_enabled: bool = True  # DESIGN_SYNC__FULL_DESIGN_PNG_ENABLED
    vlm_low_confidence_threshold: float = 0.7  # DESIGN_SYNC__VLM_LOW_CONFIDENCE_THRESHOLD
    # Wrapper unwrap pre-pass (Phase 50.3, Gap 1) — expand coloured mj-wrappers
    # with ≥2 section children into per-child sections so heading + cards
    # don't collapse into one component. Gated to MJML naming convention.
    wrapper_unwrap_enabled: bool = True  # DESIGN_SYNC__WRAPPER_UNWRAP_ENABLED
    # Nested-card background detection (Phase 50.4, Gap 10) — detect when a
    # section sits on a coloured wrapper but has its own card surface
    # (e.g. white card on lime wrapper). Renderer wraps content in a ``_inner``
    # table when ``inner_bg`` is detected.
    nested_card_detection_enabled: bool = True  # DESIGN_SYNC__NESTED_CARD_DETECTION_ENABLED
    # Per-channel RGB Δ above which a PNG-sampled centroid color is considered
    # distinct from the container background (i.e. a real inner card surface).
    nested_card_perceptual_threshold: int = 30  # DESIGN_SYNC__NESTED_CARD_PERCEPTUAL_THRESHOLD
    # FRAME-tree rules 7/8/10/11 (Phase 50.5) — pure FRAME-tree predicates that
    # emit alignment, per-corner radius, and dominant-image card width without
    # PNG sampling. Disable to fall back to Phase 50.4 behaviour.
    frame_rules_enabled: bool = True  # DESIGN_SYNC__FRAME_RULES_ENABLED
    # Pill x-offset tolerance (px) for Rule 7 alignment classification.
    rule_7_alignment_tolerance_px: float = 4.0  # DESIGN_SYNC__RULE_7_ALIGNMENT_TOLERANCE_PX
    # Physical-card identity exception (Phase 50.7, Rule 9 prep) — detect
    # FRAMEs that depict a real plastic card so Phase 52.7's dark-mode flip
    # can opt out and keep them visually consistent across modes. Pure
    # FRAME-tree heuristics; runs only on sections with an ``inner_bg``.
    physical_card_detection_enabled: bool = True  # DESIGN_SYNC__PHYSICAL_CARD_DETECTION_ENABLED
    physical_card_min_signals: int = 2  # DESIGN_SYNC__PHYSICAL_CARD_MIN_SIGNALS
