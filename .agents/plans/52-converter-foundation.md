# Phase 52–53: Design→HTML Converter — Foundation + Engine

## Source

`docs/fidelity-gap-audit-findings.md` (2026-05-30, 29-agent audit) **re-verified** by an 11-finder + adversarial workflow (`wf_fa48d17b-6ea`, 23 agents). Every root cause below is confirmed against code at the cited `file:line`. The re-audit found **two root causes the original audit missed** (RC-A, RC-B) that explain why months of converter work never moved the needle, and **corrected two audit claims** that would have misdirected the fix.

## The one-sentence diagnosis

The shipped Phase 49/50 fidelity logic is **built, enabled-by-default, and inert** — a serializer bridge (`EmailDesignDocument.to_email_section`) silently nulls the very fields the overrides consume — and the only fidelity metric that can be turned on is **color-blind, mis-registered, gmail-only, mean-aggregated, off-by-default, and never actually runs**. So the system both *can't apply* its corrections and *can't measure* whether anything helped. That is why it's been "almost fixed" for months.

## Strategy (user decisions, 2026-05-30)

- **Phase 52 = Foundation** (foundation-first): make the failure **measurable** and stop the **self-inflicted** losses. Fork-independent; every engine choice needs this.
- **Phase 53 = Engine**: the renderer fork + never-parsed ingest + VLM loop. Sequenced *after* 52 so engine work is finally driven by a real fidelity signal.
- **Target = honest measured ceiling**: best achievable *per email client* + an explicit "cannot be reproduced in email" list. "99.9% everywhere" is rejected as physically capped and currently unmeasurable.

---

## Verified root-cause map

| ID | Root cause | Where | Severity | Phase |
|----|-----------|-------|----------|-------|
| **RC-A** | `text_color` is ALWAYS None — `getattr(t,"text_color",None)` but field is `color` | `email_design_document.py:414, 695, 743` | high (1-line) | 52.2 |
| **RC-B** | Reader bridge `to_email_section` strips `text_align`/`url`/`border_radius`/`corner_radius_spec`/stroke on EVERY path → Phase 49/50 overrides read None | `email_design_document.py:685-718, 733-766`; writer `793-892` | **structural** | 52.2/52.3 |
| **RC-C** | Fixed-seed renderer is the structural ceiling (≈150 seeds; injects content only; column proportions baked) | `component_renderer.py:272-331, 516-522` | structural | 53 |
| **RC-D** | Override allowlist is closed + first-element-only; font-weight/line-height/letter-spacing/transform/decoration NEVER emitted (data already captured) | `component_matcher.py:1422-1545 (break 1485-1515)`; `component_renderer.py:587-663` | high | 52.4 |
| **RC-E** | Lossy ingest: effects/blendMode never parsed; opacity composited vs hard `#FFFFFF`; gradients dropped + un-reattachable (no `node_id`) | `figma/service.py:554-629, 265-291, 600`; `protocol.py:54-62` | structural | 52.5 (capture) / 53.3 (render) |
| **RC-F** | Metric color-blind grayscale + blur + per-section MEAN + off-by-default + gates nothing; **also dimensionally invalid** (2× Figma vs 1× HTML, white-pad not resample, gmail-only) | `visual_scorer.py:54, 77-79, 181`; `config/design_sync.py:20`; `schemas.py:638`; `fidelity_service.py:33,168` | high | 52.1 |
| **RC-G** | VLM verify→correct loop dead on every path: only wired to `convert_document_mjml`, screenshots never captured in prod, short-circuits on `not design_screenshots` | `converter_service.py:286, 375, 396`; `config/design_sync.py:58`; `import_service.py:221,283` | high | 53.4 |

### Corrections to the original audit (do not re-litigate)

1. **"Recursive renderer just needs wiring"** — WRONG. It was **deleted** in commit `d9132c7c` (`app/design_sync/converter.py` gone; recover via `git show d9132c7c^:app/design_sync/converter.py` = 1625 LOC). What remains (`_build_props_map_from_nodes` at `converter_service.py:1088`, `_frames` param) is orphaned scaffolding with zero callers. Even restored it was the **middle** fidelity tier (Auto-Layout/typography/gradient — NOT effects/geometry/pixel).
2. **"Loss is at the Figma read"** for text_align/per-corner-radius/transform/decoration/style_runs — WRONG location. These are correctly parsed and reach the in-memory `TextBlock`/`ButtonElement`, then dropped at the `EmailDesignDocument` serializer boundary. Fixing the parser would be wasted effort; fix the **bridge** (52.2/52.3).
3. **Debunkings CONFIRMED** — Maizzle/PostCSS/Juice (mjml-only), Euclidean brand-sweep (`assembler.py:119`, `source=='design_system'` only), sanitizer low-impact: all correctly off the default path. The fix plan is not misdirected by them.
4. **"65 passed" proves byte-stability, not fidelity** — `compute_quality_score` measures the matcher's own self-reported confidence, decoupled from design; the richest color fixture (`reframe`) is `reference_only`; real fixtures are gitignored so CI asserts vacuous substrings.

### Three-way loss taxonomy (use this framing; the audit collapsed it)

- **NEVER-PARSED** (no field anywhere): effects/shadow, blendMode, scaleMode/imageTransform (image crop), rotation, AUTO/% line-height, z-order/overlap, non-button strokes. → 52.5 (capture) + 53.3 (render); several physically unreproducible.
- **PARSED-THEN-DROPPED-AT-BRIDGE**: text_color, text_align, button url/border_radius, corner_radius_spec, button stroke, the entire Phase-50 section layer. → **52.2 / 52.3** (cheapest real wins).
- **CAPTURED-BUT-NEVER-EMITTED-AS-CSS**: font-weight, line-height, letter-spacing, text-transform, text-decoration. → **52.4**.

---

## Phase 52 — Foundation (7 subtasks)

> Flag-gate new behavior behind `DESIGN_SYNC__*`. Regression baseline today: `make converter-data-regression` = 65 passed. Every subtask must keep it green (or regenerate baselines with reviewed structural diff per the master-plan risk note).

### 52.1 — Repair & activate the fidelity instrument `[Backend]`

**Why first.** Lowest-*regret* under any fork: you cannot choose the engine (53.1) or prove any fix without a metric that runs and can see color. Distinct from highest-leverage — it doesn't move fidelity, it makes movement visible.

**Steps.**
1. Replace grayscale SSIM with a **color-aware** metric — CIEDE2000 (ΔE in CIELAB) per pixel/region, or reuse the existing ODiff path. Remove `.convert("L")` (`visual_scorer.py:54`).
2. Remove the σ=1.0 Gaussian blur (`visual_scorer.py:77-79, 139`) — it smooths the exact few-px spacing errors the converter introduces. Keep at most a 1px anti-alias.
3. Fix registration/scale: render HTML at `device_scale_factor=2` to match `fidelity_figma_scale=2.0` (`config/design_sync.py:23`), **or** resample (not white-pad) in `_pad_to_match` (`visual_scorer.py:58`).
4. Fix the **gap-aware composite scale**: `_capture_figma_composite` stitches per-node exports back-to-back (no inter-section gaps) but `_compute_design_height` spans gaps → every section below the first is sliced at a drifted y-band (`fidelity_service.py:151-157` vs `visual_scorer.py:147-159, 217-226`).
5. Render/score across the **multi-client profile set incl. Outlook** (not hardcoded `gmail_web` at `fidelity_service.py:33,168`); aggregate per-section by **MIN not MEAN** (`visual_scorer.py:181`), and min-across-clients.
6. **Plug it in:** commit ≥1 real fixture + `design.png` into `data/debug/` (un-gitignore that one case), flip `fidelity_enabled=True` (`config/design_sync.py:20`) for the test path and `score_fidelity` default for the regression run so the metric **actually executes in CI**.
7. Wire as **advisory** (store via `update_import_fidelity`) first; expose the score on the import. (Gate threshold = 52.7 / Phase 53 once trustworthy.)

**Verify.** New `app/design_sync/tests/test_visual_scorer_color.py`: a known wrong-brand-color-at-matching-luminance fixture must now score LOW (proves color-awareness); a 1-section-broken fixture must drag the MIN down (proves min-aggregation). `make converter-data-regression` runs the metric on the committed fixture.

**Reduces.** The "can't measure 99%" trust collapse. **Effort:** 3–4d.

### 52.2 — Serializer bridge Tier-1 (RC-A + RC-B core) `[Backend]`

**Why.** Cheapest real fidelity fix in the whole program — ~6 lines, two call sites — and now provable via 52.1. These fields already round-trip JSON; only the reader drops them.

**Steps.** In `email_design_document.py::to_email_section`:
- `:695` and `:743` — `text_color=getattr(t, "text_color", None)` → `text_color=t.color` (RC-A; the attr is `color` at `:414`).
- `:686-696` and `:734-744` — add `text_align=t.text_align` to the `TextBlock(...)` kwargs (DocumentText carries it at `:415`).
- `:709-718` and `:757-765` — add `url=b.url`, `border_radius=b.border_radius` to `ButtonElement(...)` (DocumentButton round-trips both at `:492-493`).
- Confirm `TextBlock`/`ButtonElement` field names; the override builder consumes `.text_color`/`.text_align` (`component_matcher.py:1507-1515, 1464-1482`) and CTA `url`/`border_radius`.

**Verify.** Import a fixture whose heading is a non-default color + right-aligned + whose CTA has a real href/radius; assert the shipped HTML carries them; assert 52.1 score rises. Add to `make converter-data-regression`.

**Reduces.** Restores color, alignment, CTA targets, corner rounding to the shipped path. **Effort:** ½d.

### 52.3 — Serializer bridge Tier-2 + JSON schema `[Backend]`

**Why.** Un-inerts the rest of the already-shipped Phase 49/50 machinery (Rules 8/10/11, CTA stroke, nested-card/boundary classification) at zero new-feature cost.

**Steps.**
1. Widen `DocumentText`/`DocumentImage`/`DocumentButton`/`DocumentSection` + `to_json`/`from_json` to carry: `corner_radius_spec` (per-corner image radii), `stroke` (color/weight) on section/image/button, `text_transform`, `text_decoration`, `style_runs`, `layout_align`, `role_hint`, and the **Phase-50 section fields** (`inner_bg`, `inner_radius`, `container_bg`, `boundary_above/below`, `child_content_groups`, physical-card signals).
2. Carry all of the above through **both** bridge halves — reader `to_email_section` (`:685-766`) and writer `from_email_section` (`:793-892`).
3. Update `data/schemas/email-design-document-v1.json` to add the new fields **and fix the `additionalProperties:false` inconsistency** (the schema currently forbids `text_align` on the text def and `url`/`border_radius`/`fill_color` on the button def, which `to_json` already emits — `:273-311`).
4. Add a **round-trip property test**: `write → to_json → from_json → to_email_section`, assert field equality, so fields can never be silently re-dropped again.

**Verify.** Property test green; the Phase-50 nested-card/Rule-10 fixtures now show their overrides in output (previously fed None). `make check-full` (migration/schema lint).

**Reduces.** Converts default-on dead logic into live fidelity. **Effort:** 2–3d.

### 52.4 — Widen the override allowlist + renderer dispatch (RC-D) `[Backend]`

**Why.** The typography trio is already on `TextBlock` from the Figma API (`layout_analyzer.py:1097-1099`) — only emission + a renderer dispatch arm are missing. Cheapest wins once the bridge (52.3) keeps the fields.

**Steps.**
1. `component_matcher.py::_build_token_overrides` (`~1422-1545`): emit `font-weight`, `line-height`, `letter-spacing`, `text-transform`, `text-decoration` for `_heading` and `_body`.
2. Remove the **break-after-first-heading/body** (`:1485-1515`) so every text run is styled — restores intra-section hierarchy.
3. Replace the **all-or-nothing 4-side padding** gate with per-side longhand; replace the `<br><br>` body merge with per-paragraph styled blocks.
4. `component_renderer.py` (`~587-663`): add dispatch arms for each new CSS property (mirror the existing `font-size` path).

**Verify.** Fixture with bold/light weight contrast + custom line-height/letter-spacing + uppercase label renders them (not seed defaults); 52.1 score rises; regression baselines regenerated + reviewed.

**Reduces.** The bulk of audit Findings 1–2 typography gap. **Effort:** 2–3d.

### 52.5 — Ingest correctness: lossless capture + value fixes (RC-E, fork-independent) `[Backend]`

**Why.** These are *wrong-value* and *lossless-capture* fixes that are correct under any engine. Rendering of the captured data lands in 53.3, but capturing it now stops irreversible loss and unblocks the fork.

**Steps.**
1. `figma/service.py:265-291` `_rgba_to_hex_with_opacity` — composite alpha against the **real backdrop** (thread parent/section bg), not hard-coded `#FFFFFF` (`bg_hex` default at `:271`). Any translucent layer over non-white is currently the wrong color *before* conversion.
2. `protocol.py:54-62` — add `node_id` to `ExtractedGradient` (and `DocumentGradient`) so a per-section gradient can be reattached later (today they survive only as global node-less tokens; `DocumentSection.background_color` is a single string).
3. Capture **non-button strokes** onto `DocumentSection`/`DocumentImage` (already read at `figma/service.py:619` via `_extract_stroke`; just no field to hold them).
4. Capture **AUTO/% line-height** (`figma/service.py:509-510` reads only `lineHeightPx`): when absent, read `lineHeightPercent`/`lineHeightPercentFontSize` and store a relative value.

**Verify.** Unit tests: translucent-over-color fixture yields the composited-against-real-bg hex; gradient carries its `node_id`; bordered card keeps its stroke field. (Rendering assertions deferred to 53.3.)

**Reduces.** The dominant upstream capture loss; unblocks the fork's renderer. **Effort:** 2–3d.

### 52.6 — Fix `_fix_text_contrast` mis-scoping `[Backend]`

**Why.** Runs on **every** shipped artifact (`import_service.py:842-891`, via `_sanitize_email_html` at `:402`) and can force nested light-cell text to invisible white because the dark-range scan uses `find(close_tag)` (first close, not the matching close).

**Steps.** Use a depth-tracked matching-close-tag scan over nested tables; scope the recolor to genuinely WCAG-failing text and use the design's intended on-dark tint, not literal `#ffffff`.

**Verify.** Nested-table fixture (dark wrapper containing a light cell with `#333` text) keeps the light cell readable; 52.1 confirms no spurious recolor.

**Reduces.** A silent corruption invisible to even a color-aware metric until now. **Effort:** ½–1d.

### 52.7 — Measurement-truth, regression de-vacuum, and roadmap reconciliation `[Backend, Documentation]`

**Steps.**
1. Replace vacuous substring assertions with **real color/binding assertions** against the committed fixture from 52.1 (`test_converter_data_regression.py:274,291`); document the gitignored-fixture CI gap and commit the one un-gated case.
2. Add an **ingest-capture-vs-Figma-tree delta check** — compare the captured `EmailDesignDocument` against the raw Figma node tree to quantify upstream loss (the loss the system has never measured).
3. **Correct `docs/fidelity-gap-audit-findings.md`** per the re-audit (three-way taxonomy; add RC-A/RC-B; "built+enabled+inert" not "frozen Phase-49"; metric "dimensionally invalid" not just "lenient"; narrow the global-PNG claim; "corrected by re-audit" appendix).
4. **Supersede the orphaned numbering:** add a banner to `.agents/plans/50-converter-fidelity-master.md` marking its 50–53 labels stale; relabel its inert "shipped ✅" CTA/Rule-10 rows; mark the 85→99% Success-Metrics ladder an unfalsifiable projection. Renumber the deferred `51.x/52.x/53.x` stubs under the new operative 52/53 (or mark superseded). Update `.agents/deferred-items.json` entries that reference the old numbering (physical-card / Rule-9).

**Verify.** `make converter-data-regression` asserts a real color divergence catches; doc review.

**Reduces.** The trust gap + the dual-numbering debt. **Effort:** 1–2d.

---

## Phase 53 — Engine (fork + ingest render + VLM loop)

> 53.1 is a **decision gate**. The rest forks on its outcome. Detail is intentionally deferred until the metric (52.1) exists to evaluate the options — writing it now would repeat the months-long churn of planning against a blind metric.

### 53.1 — STRATEGY-FORK DECISION + spike `[Backend]` `[Decision Gate]`
With the working metric, evaluate and choose:
- **(a) Keep fixed-seed + decorate** — promote the surviving Rules 1–11 + composite-slot stubs from `50-converter-fidelity-master.md`. Lowest effort, known structural ceiling (RC-C).
- **(b) Restore the recursive renderer** — `git show d9132c7c^:app/design_sync/converter.py` (1625 LOC) + re-plumb ingest to persist the `DesignNode` tree. Buys typography/Auto-Layout/gradient fidelity; NOT effects/geometry/pixel.
- **(c) Per-frame rasterization** for high-loss subtrees — buys pixel fidelity, destroys editable structure + ESP token/personalisation hooks (mutually exclusive with editability per frame).
Spike each on the committed fixture; pick by measured ΔE + effort. **Output:** decision doc + the chosen sub-plan.

### 53.2 — Renderer/engine implementation per the chosen fork.
### 53.3 — Never-parsed ingest render: effects/blendMode (VML/flat fallback), per-node gradient reattach (uses 52.5 `node_id`), scaleMode/imageTransform crop, rotation, z-order/overlap → `frame_export` for non-reproducible subtrees.
### 53.4 — Revive or retire the VLM loop (RC-G): route the default html path into verification (capture per-section screenshots in `import_service`, let `convert_document` invoke correction) OR honestly drop it from the roadmap. No silent "it lifts fidelity" claims.
### 53.5 — Decorative VECTOR recovery (rasterize vector subtrees or inline encoded PNG).
### 53.6 — Promote the Rules 1–11 / composite-slot stubs that survive the fork, wired to the now-live override surface (52.4) and measured by the real metric (52.1).
### 53.7 — Honest per-client ceiling doc + the "cannot reproduce in email" contractual list (Outlook ~95% floor; shadows/gradients/SVG/blend/rotation/overlap as flat fallbacks).

---

## Honest ceiling (what "fixed" can mean)

Dual-capped. **Physically:** table+VML email tops ~95% on Outlook/Word; drop/inner shadow, gradients (crude VML/flat only), SVG, blend modes, true opacity over non-white, rotation, and overlapping/z-ordered layers are **not reproducible** in the email box model — and several die at ingest. **Structurally:** the default fixed-seed renderer (RC-C) caps structural fidelity below pixel fidelity regardless. Realistic post-foundation target: **meaningfully higher typography/spacing/color fidelity on Gmail-class clients, a hard ~95% Outlook floor, and effects/shadow/gradient/blend/rotation/overlap permanently below 100%** — with the real number unknown until 52.1's color-aware, multi-client, min-aggregated metric is wired and run.

## Files affected (Phase 52)

| File | Subtasks |
|------|----------|
| `app/design_sync/visual_scorer.py` | 52.1 (color metric, no-blur, min, scale) |
| `app/design_sync/fidelity_service.py` | 52.1 (multi-client, composite-gap scale) |
| `app/core/config/design_sync.py` | 52.1 (fidelity_enabled, scale), gate flags |
| `app/design_sync/schemas.py` | 52.1 (score_fidelity default on regression) |
| `app/design_sync/email_design_document.py` | 52.2, 52.3 (bridge reader+writer, dataclasses, to_json) |
| `data/schemas/email-design-document-v1.json` | 52.3 (new fields + additionalProperties fix) |
| `app/design_sync/component_matcher.py` | 52.4 (override emission) |
| `app/design_sync/component_renderer.py` | 52.4 (dispatch arms) |
| `app/design_sync/figma/service.py` | 52.5 (opacity-vs-bg, strokes, AUTO/% line-height) |
| `app/design_sync/protocol.py` | 52.5 (gradient node_id) |
| `app/design_sync/import_service.py` | 52.6 (`_fix_text_contrast` scoping) |
| `app/design_sync/tests/*`, `data/debug/<case>/` | 52.1, 52.2, 52.4, 52.7 (fixtures, regression, round-trip) |
| `docs/fidelity-gap-audit-findings.md`, `.agents/plans/50-converter-fidelity-master.md`, `.agents/deferred-items.json` | 52.7 (truth + supersede) |

## Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Bridge widening (52.3) changes persisted `email-design-document-v1.json` data contract | New fields additive + optional; round-trip property test; bump schema version if needed; `make migration-lint` |
| 52.2/52.4 change rendered bytes → snapshot baselines diverge even where correct | Reframe acceptance as "baselines regenerated + structural diff reviewed"; run `make rendering-baselines` after 52.4 |
| Color-aware metric flags pre-existing divergences as failures (red CI) | Land metric as **advisory** first (52.1); set the gate threshold only after a baseline scoring run |
| `_fix_text_contrast` fix (52.6) regresses genuine WCAG fixes | Keep the WCAG-failure path; only change the close-tag scan + the replacement tint |
| Deferred-items physical-card entries assume old 52.7 "Rule 9" numbering | 52.7 step 4 renumbers + updates `.agents/deferred-items.json` in the same change |

## Preflight (per `.claude/rules/deferred-items.md`)

Open deferred entries touching this work: `phase-50.7-ac-4` / `phase-50.8-nested-physical-cards` (physical-card detection feeds the OLD "Rule 9" dark-mode flip — now Phase 53, not 52). 52.7 step 4 must reconcile their numbering. No deferred entry blocks the 52.1–52.6 foundation work.
