# 53.3 — Never-parsed ingest render

> Renders (or honestly falls back on) the visual data the ingest historically dropped.
> 52.5 (`a6d2afa1`) landed the **capture** half for backdrop compositing / gradient
> `node_id` / non-button strokes / AUTO-% line-height; this plan is the **render** half plus
> the still-never-parsed properties. Fork (a) ratified — all work targets the fixed-seed
> renderer. Folds in the deferred stub `.agents/plans/deferred/53.3-per-frame-export-default.md`.

## Current facts (verified 2026-06-12)

- `_parse_visual_props` (`figma/service.py:569-649`) parses fills/text color/imageRef/
  stroke/hyperlink. **Still ignored:** `effects`, `blendMode`, `scaleMode`/`imageTransform`,
  `rotation`; z-order exists only as array order.
- Gradients: `ExtractedGradient.node_id` populated (`service.py:1352-1359`), round-trips via
  `DocumentGradient` (`email_design_document.py:184-215`) — but nothing reattaches a gradient
  to its section; `DocumentSection` carries only `background_color`.
- Renderer background surface: `_outer`/`_inner` token overrides
  (`component_matcher.py:1817-1964` → `component_renderer.py:1073-1164`). Zero gradient/VML
  emission in the renderer; VML `v:rect`/`v:fill` precedent exists in seeds
  (`email-templates/components/vml-bg.html`, `hero-block.html`).
- Frame export exists: `export_frame_screenshots` (`figma/service.py:1819-1869`, batches of
  100, returns `{node_id: bytes}`); assets pipeline normalizes/stores/resizes
  (`assets.py:24-151`). No reproducibility classifier exists anywhere.
- Bridge trap (RC-A/RC-B class): every new `EmailSection`/`DocumentSection` field must be
  added in **four** places — `to_json`/`from_json` + `to_email_section`/`from_email_section`
  (`email_design_document.py:1022-1240`) — or it dies at the bridge (D2 precedent).

## Sub-items, ordered by visible value per effort

### 53.3b — Per-node gradient reattach `[M, ~2d]` — DO FIRST (visible win, all plumbing exists)

1. `EmailSection.gradient_ref: str | None` + `DocumentSection.gradient_ref` (+ 4 bridge
   sites + schema property). At `analyze_layout` section construction: when the section
   node's id (or its wrapper's) matches a `DocumentTokens.gradients[*].node_id`, set it.
2. Matcher: `_build_token_overrides` — when `section.gradient_ref` resolves, emit
   `TokenOverride("background-image", "_outer", "linear-gradient(<angle>, stops…)")` plus
   keep the existing solid `background-color` (= `fallback_hex`) as the non-supporting-client
   fallback. Needs the gradient list in scope: thread `tokens` into `match_all` the same way
   `image_urls` is threaded (`converter_service` call site).
3. Renderer: `_outer` arm gains a `background-image` branch that upserts into the band/outer
   table style (reuse `_upsert_style_decl`); MSO fallback = existing `bgcolor` attr already
   stamped by `_replace_outer_bg_color` (solid fallback_hex) — **no VML in v1** (VML gradient
   `v:fill type="gradient"` is a follow-up; note in ceiling doc).
4. Verify: grep `data/debug/*/tokens.json` for gradients with `node_id`; whichever fixtures
   carry them become the regression surface; baseline regen + diff audit; A3 advisory delta.

### 53.3c — Image crop via frame export `[S-M, ~1d]`

`scaleMode`/`imageTransform` are crop instructions the HTML `<img>` can't express. Instead of
parsing the matrix: **export the cropped result**. The frame-wrapping-single-image path
already exports the FRAME (`export_node_id`, `layout_analyzer.py:1254-1275`) — extend the
same preference to IMAGE fills whose `scaleMode != "FILL"`-default (read `scaleMode` in
`_parse_visual_props`, stamp `DesignNode.scale_mode`; when set and non-default, the
ImagePlaceholder's `export_node_id` = the node itself so the Figma render bakes the crop).
This is the deferred stub's `image_resolution_mode` idea reduced to the only case where it
matters. One extra batched `/v1/images` call only when crops exist.

### 53.3d — Rotation + z-order/overlap → frame_export fallback `[M, ~2-3d]` (the fork-(c) escape hatch seam)

1. Parse `rotation` (`DesignNode.rotation`) and detect sibling bbox overlap at
   `_get_section_candidates` level (x/y/w/h already on `DesignNode`).
2. New `_is_reproducible(node) -> bool` in `layout_analyzer.py`: False when the subtree
   contains `rotation` beyond ±1° or overlapping non-background siblings. THIS is the
   reproducibility classifier — keep it boring and conservative (false→raster only when
   certain).
3. Non-reproducible section subtree ⇒ replace its content extraction with a single
   `ImagePlaceholder(export_node_id=<subtree root>)` (`is_background=False`, full width) —
   rendered via the existing image seed; bytes come from `export_frame_screenshots` on the
   live import path, `scripts/export-case-assets.py` for fixtures.
4. Gate behind `DESIGN_SYNC__FRAME_EXPORT_FALLBACK_ENABLED` (default off; register in
   `feature-flags.yaml`); log `design_sync.frame_export_fallback` with node id + reason.
   File-size guard: PNG > ~200 KB → log warning (Gmail 102 KB clip risk is per-HTML, but
   keep the audit trail).

### 53.3a — Effects/blendMode: capture + documented flat fallback `[S, ~1d]` — LAST (lowest render value)

Per the ceiling doc §2, shadows/blur/blends are **not reproducible**; the deliverable is
explicitness, not rendering: parse `effects[]`/`blendMode` into `DesignNode.effects_summary`
(count + types) and surface a converter warning (`design_sync.effects_dropped`, node id,
types) so the loss appears in conversion warnings instead of silence. Optional follow-up
(NOT v1): box-shadow emission for modern clients only.

## Out of scope

- VML gradient fills (follow-up; solid fallback ships first).
- Per-text-node z-order (covered by 53.3d's subtree raster).
- Vector recovery — separate plan `.agents/plans/53-5-vector-recovery.md`.

## Verify (per Track E contract)

Each sub-item: fixtures render within ΔE tolerance (A3 advisory, flag-on where gated) OR
fall back to a **documented** flat export; ladder counts unchanged on all 6; baseline regen
only after intended-vs-structural diff audit (Track-B playbook); bridge round-trip unit tests
for every new field (D2 trap); `make types` + design_sync suite + golden-conformance green.

## Deferred-items touching this plan

- `phase-53.7-asset-reexport-prerequisite` — 53.3c/d add export dependence; the fallback must
  log loudly when assets are unavailable rather than emitting conn-less 404 URLs.
- `phase-53.7-typography-maxitems-cap` — unrelated but same schema file; if 53.3b adds the
  `gradient_ref` schema property, do NOT "fix" the cap in passing (separate close).
- 52.5 capture limits noted in TODO.md (image-fill frames yield no `child_bg`;
  gradient-topmost fills don't update `child_bg`) — 53.3b inherits them; do not silently
  re-promise them.

## Result (2026-07-06, `fix/phase-53.3-ingest-render`)

Shipped all four sub-items as planned. **Corpus effect: ZERO by design** — the raw_figma
audit (2026-07-06) found the 6 fixture cases carry no gradients, no non-FILL scaleModes, no
rotations beyond float noise, no effects, and only NORMAL/PASS_THROUGH blends, so synthetic
trees (`test_ingest_render.py`, 31 tests) are the only coverage; baselines stayed
byte-identical (no regen), ladder 13/9/8/10/8/12 held (data-regression 73 passed / 1 mammut
xfail), and scores are **flat: c5 0.840 / c6 0.802 / c7 0.794 / c8 0.778 / c9 0.680 /
c10 0.742** (BEFORE row reproduced exactly, AFTER identical — the A3 advisory delta is 0).

- **53.3b** — `gradient_ref` on `EmailSection`/`DocumentSection` (+ all 4 bridge sites + the
  schema property, and the missing `gradient.node_id` schema property — a 52.5 leftover of
  the same strictness family); attach at `analyze_layout` via `gradient_node_ids` threaded
  from `from_legacy`; matcher resolves against `tokens.gradients[*].node_id` and emits
  `background-image` on `_outer` plus the solid midpoint `background-color` when the section
  has no fill (stamps MSO `bgcolor`); renderer upserts via `_apply_outer_bg_image`
  (`_outer`-classed element, else first visible presentation table — MSO ghost skipped).
  E2e verified: `from_legacy → convert_document` HTML carries
  `background-image:linear-gradient(90deg, …)` + the `#5E6F80` fallback. **Linear only** —
  radial+ stay solid; **no VML gradient in v1** (ceiling doc §2 updated).
- **53.3c** — `scaleMode` parsed off the consumed IMAGE fill (`_VisualProps.scale_mode` →
  `DesignNode.scale_mode`); `_walk_for_images` sets `export_node_id = node.id` for non-FILL
  modes (`_crop_export_id`) on both the plain-IMAGE and FRAME-bg branches, so the Figma
  render bakes the crop. `imageTransform` matrix deliberately not parsed (plan: export the
  cropped result instead).
- **53.3d** — `DesignNode.rotation` (degrees, Figma REST convention);
  `_unreproducible_reason`/`_is_reproducible` in `layout_analyzer.py` (rotation beyond ±1°,
  sibling bbox overlap ≥25% of the smaller box, ≥95%-of-parent backdrop layers excluded,
  invisible subtrees skipped); flag-gated section raster
  (`DESIGN_SYNC__FRAME_EXPORT_FALLBACK_ENABLED`, default off, registered in
  `feature-flags.yaml` + settings) replaces extraction with one
  `ImagePlaceholder(export_node_id=frame)` and logs `design_sync.frame_export_fallback`;
  oversized-asset audit warning (`design_sync.asset_oversized`, >200 KB) in `assets.py`.
- **53.3a** — `effects[]`/`blendMode` → `DesignNode.effects_summary`
  (`"<count>:<TYPE,…>"`), aggregated per section (`_collect_effects_summary`), bridged
  (4 sites + schema), surfaced by `convert_document` as `design_sync.effects_dropped` log +
  conversion warning. NOTE: `_collect_vector_warnings` in `converter_service.py` turned out
  to be dead code (zero callers), so the plan's "appears in conversion warnings" needed the
  section-level carry — `DesignNode`-only state cannot reach the document path.

**Honest read / follow-ups:** rotation unit is asserted (degrees) from figma-api typings, not
verified against a live rotated design — the classifier errs to rastering either way;
`match_section_with_vlm_fallback` accepts `gradients` but no production caller threads it
(the path itself is flag-off); effects warnings emit on `convert_document` only (the MJML
path builds its own warnings list). New ledger entry:
`phase-53.3-line-height-relative-loader-gap` (the diagnose loader drops the 52.5 AUTO/%
line-height field on reload — latent, fixture dumps predate 52.5). Ledger sweep: no entry
closes — `phase-53f-decorative-image-flag` needs per-image role capture (not the 53.3d
subtree classifier) + the frame-wrap width fix; the mammut escape-hatch condition needs case
10 to actually converge (flag is default-off). Gates: `make types` 0 errors ·
design_sync+components 2885 passed / 2 xfailed · golden-conformance 26 · scoped ruff (incl.
S-rules) clean · flag audit 87 flags green.
