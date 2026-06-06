# Converter Engine Audit #2 — Why Figma→Email Still Doesn't Render Properly (post‑Phase‑52)

> **Filename note.** Requested as `converter_autid_2.md`; saved as `converter_audit_2.md` (typo corrected, matches the existing `docs/audit_2*.md` family). Rename if the misspelling was intentional.

**Date:** 2026-06-01
**Branch:** `tech-debt/phase-52-converter-foundation` (12 commits ahead of `main`, latest `260b29ec`)
**Method:** 17-agent forensic workflow `wf_f43162b1-56b` — empirical render (ran the real converter on all 6 fixtures), differential code-verification against *current* post‑P52 code, engine-fork evaluation, and adversarial verification of every headline claim. ~1.18M tokens, 26 min. 16/17 agents returned (one fork agent failed structured output; its conclusion is reconstructed from the RC‑C + decomposition findings and labeled as such).
**Predecessor:** `docs/fidelity-gap-audit-findings.md` (2026-05-30) — this audit is **differential** against it: that audit predates the 12 Phase‑52 commits, so its line numbers are stale and several of its root causes are now fixed. See §2.

---

## 1. Executive answer

The converter's *property plumbing* is now genuinely fixed (Phase 52: colors, alignment, CTA targets/radii, typography props all reach the shipped HTML — verified live). **But the user's complaint — "still cannot render the HTML properly from the HTML components" — is about layout *structure*, and that is entirely unfixed.** It is the Phase‑53 "engine" work, which has **not started**.

Three findings, each empirically reproduced today:

1. **The engine mis-decomposes layout on *every* fixture.** It produces the wrong number of sections — both over- and under-segmenting — and the error lives one stage *before* component matching, in the layout analyzer. (§3)
2. **The over-segmentation has a single, pinned, proven cause:** the Phase‑50.3 wrapper-unwrap pre-pass `_expand_container_wrappers`. Forcing it to passthrough takes LEGO from **17 sections back to exactly 8** — *but* disabling the pass is **not** the fix: it regresses the under-segmenting fixtures the pass was built to help (§3.3). The target is **8 visual bands, not 8 flat sections** (the Opus hand-build is itself ~17 finer blocks *within* 8 bands — §3.2). (§3.2–§3.3)
3. **Nothing can be *proven* fixed yet** because the fidelity metric is blind: the converter's own `<img>` srcs are node-id URLs with no on-disk file map, so renders show broken images and a **blank page scores higher than the real render** (0.7214 > 0.7202 — inversion live-reproduced). Asset resolution is the gate for the entire effort. (§5)

**Bottom line:** the cheapest, highest-ROI, *fork-independent* win is to (a) resolve assets so the metric becomes trustworthy, then (b) *surgically fix* (not disable) the segmentation gate so it preserves band grouping without losing the under-segmentation help it gives cases 5/10. The bigger "render arbitrary geometry" problem is a genuine engine fork (§6) that should only be chosen *after* the metric is real — exactly as the Phase‑52/53 plan sequenced it.

---

## 2. What changed since the 2026‑05‑30 audit (differential)

The May-30 audit catalogued root causes RC‑A…RC‑G. Here is each one's **current** status against post‑P52 code. (Verified at `file:line`; the old audit's line numbers are stale and noted where they'd mislead.)

| RC | Root cause (May-30) | Status now | Evidence (current code) |
|----|---------------------|-----------|--------------------------|
| **RC‑A** | `text_color` always `None` (`getattr(t,"text_color")` vs field `color`) | ✅ **FIXED** (P52.2) | `email_design_document.py:597` reads `color=t.text_color`; `:617` `text_color=self.color`. Round-trip test passes (17 tests). Live LEGO: 19 distinct text colors incl. brand `#AFCA01`/`#4E3092`. |
| **RC‑B** | Bridge drops `text_align`/`url`/`border_radius`/`corner_radius_spec`/stroke/Phase‑50 fields | ✅ **FIXED** (P52.2/52.3) | Full serialize path `EmailSection→DocumentSection→to_json→from_json→to_email_section` drops **only** `source_frame_id` (write-only telemetry, never read anywhere in `app/` — harmless). Carry sites `:607-625`, `:796-815`, `:1105-1145`. ⚠ old audit lines `:695/:743/:685-718` are pre‑P52 and now point at unrelated code. |
| **RC‑D** | Override allowlist closed + first-element-only; typography never emitted | 🟡 **PARTIAL** (P52.4) | All 5 typography props (font-weight/line-height/letter-spacing/text-transform/text-decoration) **are now emitted + dispatched** (verified live on LEGO). **Still open:** (1) one value per role — first-heading/first-body only; `style_runs` captured but never consumed; (2) padding is all-or-nothing 4-side shorthand → a 1–3-side spec drops *all* padding. |
| **RC‑C** | Fixed-seed renderer is the structural ceiling | 🔴 **INTACT** (Phase 53) | `component_renderer.py` can only **decorate** seeds (leaf content fills + a closed leaf-CSS allowlist + uniform N-way repetition). It cannot change table topology: column count/proportions, nesting depth, per-cell paddings, geometry, element count. P52 widened the *decoration* allowlist and added **zero** structural capability. |
| **RC‑E** | Lossy ingest: effects/blendMode/gradient/opacity/etc. | 🔴 **UNTOUCHED** (Phase 53) | **Zero** P52 commits modified `figma/service.py` or `protocol.py`. Never-parsed: effects/shadow, blendMode, scaleMode/imageTransform, rotation, z-order, per-node gradient (no `node_id`), AUTO/% line-height, opacity-vs-white compositing. **Correction to May-30:** non-button strokes *and* corner radii are **not** lost at ingest. **Big caveat:** the regression corpus loads frozen `structure.json` and never runs `_parse_node`, so most RC‑E losses are **latent** (bite only on live re-ingest), not active on the 6 fixtures — and several are moot for image nodes that ship as node-id PNG exports. |
| **RC‑F** | Metric color-blind/blur/mean/off/never-runs | 🟡 **PARTIAL** (P52.1) | Correctness repaired (`visual_scorer.py`: CIEDE2000, no grayscale, blur default 0.0, MIN-agg). **Still blind in practice:** (a) the only wired caller `fidelity_service.py:80` still passes the prod blur of **1.0**; (b) unwired from CI, `fidelity_enabled=False`, tests use synthetic images; (c) **asset blocker → metric inverted** (see §5). |
| **RC‑G** | VLM verify→correct loop dead on default path | 🔴 **DEAD / untouched** (Phase 53) | Flag default `False`; `convert_document` discards screenshots (`_ = design_screenshots`); only the MJML path calls `_apply_verification`; no prod caller passes screenshots. Its internal metric `1 - avg_diff/100` returns **1.0 on empty input** — so on broken renders it would no-op or report a *false perfect*. Not worth reviving until assets resolve. |

**Net:** P52 closed the two cheapest, real wins (RC‑A/RC‑B) and half of RC‑D/RC‑F. The structural causes (RC‑C engine, RC‑E ingest, RC‑G loop) were deliberately deferred to Phase 53 and remain fully open. **None of the P52 fixes move perceived fidelity** — that is gated on structure, which is §3.

---

## 3. The empirical smoking gun — layout decomposition is wrong on every fixture

This is the centerpiece, and it is **new** (every prior audit was code-reading; this one ran the converter and looked).

### 3.1 Section-count drift (live-measured today, not from stale manifest)

Entry point: `run_case_conversion(Path("data/debug/<N>"))` → `ConversionResult.sections_count`.

| Case | Name | Live count | Target (bands) | Drift | Mean match conf. |
|------|------|-----------:|---------------:|------:|-----------------:|
| 5 | MAAP | 11 | 13 | **−2** | 0.991 |
| 6 | Starbucks | 5 | 9 | **−4** | 1.000 |
| 7 | LEGO | 17 | 8 | **+9** | 0.993 |
| 8 | Performance Reimagined | 11 | 10 | **+1** | 1.000 |
| 9 | Slate | 10 | 8 | **+2** | 0.969 |
| 10 | Mammut | 14 | 18 | **−4** | 0.993 |

**Aggregate:** abs-drift sum = 22, mean abs drift = 3.67 sections, **zero exact matches**. Both over- (7,8,9) and under-segmentation (5,6,10) occur.

**Two decisive observations:**

- **The drift is decoupled from component matching.** Match confidence stays near-perfect (0.969–1.00) *even on the 2×-over-segmented LEGO case*. The matcher is `section[i]→match[i]`, count-neutral — it confidently matches a component to every wrong section. **Match confidence is therefore a misleading health signal: it is highest exactly when the section count is most wrong.**
- **The drift is born in the layout analyzer, before matching.** LEGO's raw `layout.sections` is already **21** (14 `CONTENT` + 5 `SPACER` + 1 hero + 1 footer) for an 8-band design; rendering only collapses it to 17. `section_type` is a generic `CONTENT` catch-all in 5 of 6 fixtures (`layout_analyzer.py:234-246`).

### 3.2 Where LEGO's 8 bands become 17 sections — the pinned, proven cause

**Adversarially confirmed (control + instrumentation).** The inflation is caused **entirely by one function**: `_expand_container_wrappers` — the Phase‑50.3 wrapper-unwrap pre-pass (`figma/layout_analyzer.py`, call at `:318`, body `~:540-576`, inner append `:568-575`).

The pipeline:
1. `_get_section_candidates` **correctly** produces **8** wrapper bands (all FRAME `mj-wrapper`s).
2. `_expand_container_wrappers` then fires `_is_container_wrapper(node)` (`:579-584`) = **(non-default fill) AND (≥2 section-children)**. It matches exactly 3 wrappers: `2833:1897` (lime, 4 children), `2833:1941` (lime, 8 children), `2833:2040` (grey, 4 children).
3. Each matched wrapper is **exploded into one section per child**: `8 − 3 + (4+8+4) = 5 + 16 = 21` candidates.
4. Spacer churn `21 → 17`: of 5 `SPACER` pseudo-sections, 4 are dropped and **1 leaks** through as a standalone section (`section_14 = "Component: spacer"`, via the structural fallback at `:598`).

**The control proof:** forcing `_expand_container_wrappers` to passthrough yields **exactly 8 sections** — proving it is the sole cause. (`wrapper_unwrap_enabled` defaults `True`, `config/design_sync.py:97`, so this is the production path.) Sibling-group detection fires *inside* already-exploded wrappers (`2833:1904`, `2833:1946`) and is therefore downstream — **not** a cause of top-level over-segmentation.

> ⚠ **Important nuance — don't chase the literal number "8".** The Opus hand-build (`manual_component_build.html`) deliberately uses **17 numbered blocks (#1–#16 + #20)** *while preserving 8 visual bands*. The defect is **not** "17 instead of 8" literally — it is **destroyed band grouping + spacer leakage + flat cards**. A naive `assert sections_count == 8` regression gate would chase the wrong target. The correct invariant is **band structure** (the 8 bands preserved as nested groups), not a flat top-level count.

### 3.3 The structural diagnosis — one count-gate, pulled two ways

The number of email sections is decided by **one heuristic at a single fixed tree depth**: `_is_container_wrapper` = (colored fill) AND (≥2 section-children). There is **no semantic coalescing** anywhere downstream.

- **LEGO over-segments** because colored wrappers with 4/8 children get exploded into one section each.
- **Starbucks/Mammut under-segment** because single-child wrappers are *never* unwrapped, so logical blocks one level deeper collapse into a single `CONTENT` section (Starbucks: 3 `mj-wrapper`→`CONTENT` for inner blocks of 1/2/4 against a 9-band target).

Both are the **same gate pulled in opposite directions**, so **no scalar threshold satisfies both fixtures**. This is a structural ceiling, not a tuning gap — and it is now proven empirically, not just argued.

**Passthrough control across all 6 fixtures (reproduced 2026-06-01, `.tmpscratch/passthrough_all.py`).** Disabling `_expand_container_wrappers` (forcing the no-op shape):

| Case | Name | Baseline | **Passthrough** | Target | Base drift | Pass drift |
|------|------|---------:|----------------:|-------:|-----------:|-----------:|
| 5 | MAAP | 11 | 9 | 13 | −2 | **−4 (worse)** |
| 6 | Starbucks | 5 | 5 | 9 | −4 | −4 (no change) |
| 7 | LEGO | 17 | **8** | 8 | +9 | **0 (fixed)** |
| 8 | Performance | 11 | **10** | 10 | +1 | **0 (fixed)** |
| 9 | Slate | 10 | **8** | 8 | +2 | **0 (fixed)** |
| 10 | Mammut | 14 | 12 | 18 | −4 | **−6 (worse)** |

Abs-drift sum: baseline 22 → passthrough 14; exact matches 0 → 3. **Disabling the pass fixes every over-segmenting case *exactly* and worsens every under-segmenting case** — it does not reduce the error, it relocates it. Phase 50.3 added the pass precisely to *cure* under-segmentation ("so heading + cards don't collapse into one component", `config:97`), and the control shows it does help cases 5/10. So the pass is doing a real job badly: it correctly decides a wrapper should be unwrapped, but then **explodes the children into flat top-level sections** (causing over-segmentation + flat cards, §3.4) instead of keeping them as a **nested band group**. The surgical fix is to emit nested groups, not to disable the pass — and that nested-group structure is exactly what the recursive renderer (fork b, §6) produces for free.

### 3.4 What the engine gets wrong with the tools it already has (vs the Opus manual build)

Diffing case-7 output against `manual_component_build.html` (same 150-component library, all 11 rules tagged) isolates engine error from library limits. **P52 plumbing genuinely reaches output** (real LEGO colors, varied text-align, real slot content, CTA pill radii). **But the engine losses are structural and untouched:**

- Every membership/product **card renders as a flat 2-column band** — the detected `inner_radius` (12/18px) and `inner_bg` (white card on colored wrapper) **never reach the HTML**. Form is lost; order is preserved.
- 5 spacer frames become **standalone sections** instead of band padding.
- 2 heading slots render the **literal placeholder `"Section Heading"`** even though the real text exists in the parsed layout (`placeholder_in_output` warnings).

---

## 4. Verified root-cause map (current, prioritized)

| ID | Current root cause | Where | Severity | Fork-dependent? |
|----|--------------------|-------|----------|-----------------|
| **S‑1** | Wrapper-unwrap over-explosion / under-unwrap — single depth-fixed count-gate | `layout_analyzer.py` `_expand_container_wrappers` `:540-576`, `_is_container_wrapper` `:579-584` | **structural / headline** | partially (see §6) |
| **S‑2** | `CONTENT` catch-all + `SPACER`-as-section noise; no semantic block typing | `layout_analyzer.py:234-246, 858-917` | structural | partially |
| **S‑3** | Detected nested-card structure (`inner_bg`/`inner_radius`) never rendered → flat cards | bridge carries it; renderer doesn't emit inner table | high | yes (renderer) |
| **S‑4** | Placeholder text leaks to output despite real parsed text | `component_renderer.py` slot fill + matcher | medium | no |
| **RC‑C** | Fixed-seed renderer can only decorate, never restructure | `component_renderer.py` | structural ceiling | **the fork itself** |
| **RC‑E** | Lossy ingest (effects/gradient/opacity/rotation/blend) — latent on fixtures | `figma/service.py`, `protocol.py` | structural | yes |
| **RC‑D′** | Per-run typography (`style_runs`) + per-side padding still unconsumed | `component_matcher.py` overrides, `component_renderer.py` | medium | no |
| **RC‑F** | Metric blind in practice (blur 1.0 passed, unwired, **inverted by broken assets**) | `fidelity_service.py:80`, `config:fidelity_enabled` | **the gate** | no |
| **RC‑G** | VLM loop dead; internal metric also blind | `converter_service.py`, `visual_verify.py:184-187` | medium | yes |
| **A‑1** | **Asset resolution** — node-id `<img>` srcs have no on-disk map → metric inverted | `data/debug/*/`, `import_service.py:658` | **the gate** | no |

---

## 5. The measurement gate (why nothing can be *proven* yet)

**This blocks a correct deliverable, so it leads the fix plan.** The metric is **live-inverted**:

- LEGO's 22 `<img>` srcs are node-id URLs `/api/v1/design-sync/assets/2833:*.png` with **no node-id→file map on disk**, so they 404 on render.
- A **blank white page scores 0.7214** vs the **real broken-asset render's 0.7202** against the LEGO design — i.e. the metric rewards rendering *nothing*.
- **Any fidelity/ΔE/SSIM number on a real fixture today is meaningless** (the workflow's constraint audit confirmed no agent treated one as ground truth — every numeric is a structural count, a component-match score explicitly flagged non-fidelity, or an inversion value cited as proof of brokenness).

**Asset state per fixture (live-checked):**
- Cases **5/6/10**: have on-disk `assets/` dirs; resolvable after a **trivial colon→underscore filename normalization**.
- Cases **7/8/9** (incl. flagship LEGO): **no `assets/` dir at all** — need a real Figma export or a hand-map (~22 node-ids for LEGO).
- **No** case has the `design.png` reference the visual test requires.

Until this is fixed, the engine fork cannot be chosen on measured ΔE; structural inspection (section/band counts, element presence, color/radius sampling) is the only trustworthy signal — and it is enough to act on Tier 0–1 below.

---

## 6. The engine fork (Phase 53.1) — armed, not decided

This is a **user decision gate**. Below are grounded effort/ceiling estimates per option. **Recommendation: do Tier 0–1 (§7) first regardless — they are fork-independent — then choose.**

### Option (a) — Keep fixed-seed + decorate *(low effort, known ceiling)*
*(Reconstructed: the dedicated agent failed structured output; conclusion derived from the RC‑C + decomposition findings and the all-6 passthrough control I ran directly — §3.3.)*
- **Buys:** promote surviving Rules 1–11 + composite slots, widen overrides (RC‑D′), and *surgically* fix the `_expand_container_wrappers` gate (§3.3) so band grouping improves.
- **Cannot:** RC‑C is intact — the seed renderer can never restructure (column proportions, nesting, geometry are baked). **Crucially, the all-6 control shows segmentation is *not* a clean win under (a):** no single change to the gate makes all 6 fixtures exact (disabling fixes 7/8/9 but regresses 5/10), and emitting the *nested band group* the fix needs may itself exceed what the seed renderer can render. Decorating provably inherits the ceiling.
- **Effort:** low (days–1.5 wk) for the gate tweak + nested-card render + typography; this is mostly the open Phase‑52 backlog.
- **Verdict:** the **floor** — meaningfully better typography/spacing on Gmail-class clients and *less-wrong* grouping, but it cannot make all fixtures structurally correct and caps below the design on any layout the 150 seeds don't already contain.

### Option (b) — Restore the deleted recursive renderer *(conditional; strongest structural win)*
- **Grounded live:** `git show d9132c7c^:app/design_sync/converter.py` = **1625 LOC**, recoverable verbatim. Run live on the LEGO tree it produced **8 visual bands (not 17)**, real card radii (`border-radius 12px ×6, 18px ×1`), **proportional column widths** (164/240/250/269/291/440/600px), real palette, and **real text content — zero placeholders**. It is the **only** fork that dissolves *both* the segmentation smoking gun **and** the RC‑C restructure ceiling, because it renders the `DesignNode` auto-layout tree directly instead of matching to frozen seeds.
- **Cannot:** it is the **middle tier** (Auto-Layout/typography/gradient) — **never** effects/geometry/pixel; does **not** fix RC‑E ingest losses (separate work). And it has **no semantic merge/split** — it faithfully reproduces *whatever the Figma tree is*, so it's strictly better only on **clean** trees (LEGO) and neutral-to-worse on pathological ones (Starbucks shared-parent collapse).
- **Effort: ~2.5–4 eng-weeks (NOT a quick revival — HANDOFF lists "just needs wiring" as a dead end).** Breakdown: restore 1625 LOC + reconcile imports (3–5d); **tree-persistence re-plumbing is the real cost** — `from_legacy` runs `analyze_layout()` and stores only flat sections (`email_design_document.py:1381`); `converter_service.py:315` passes `_frames=[]` and `:328-335` returns empty with *"Recursive converter requires full DesignNode frames which the document path doesn't carry"* (4–6d); test rebuild — `d9132c7c` deleted 22 test files / 4676 LOC (5–8d). Surviving scaffolding lowers cost (`RenderContext`, `_collect_frames`, `_build_props_map_from_nodes`, `protocol.DesignNode` all intact but orphaned).
- **Prereqs:** asset resolution (§5) + **re-measure band correspondence on all 6 fixtures** (only LEGO verified live; (b) trades the wrapper-gate for raw tree-fidelity — confirm it doesn't regress the under-segmenting cases).
- **Verdict:** **strongest structural lift**, but a genuine multi-session project, capped at middle tier.

### Option (c) — Per-frame rasterization for irreproducible subtrees *(fallback-only)*
- **Buys:** pixel fidelity for subtrees email constitutionally can't rebuild (gradient meshes, vector art, shadows, blend, rotation, overlap). The raster primitive **already ships and works** (`figma/service.py:1648 export_images`, `:1750 _export_full_frame_png`; storage `assets.py:90`; binding `import_service.py:658`).
- **Cannot / wrong tool here:** it does **not** address the user's complaint (wrong section counts = grouping); it only collapses counts *destructively* (one PNG per band kills every card's CTA/heading). Rasterized regions are **dead** — no dark-mode, no responsive restack, no personalization/Liquid, a11y degrades to alt-text. PNGs measured at **0.64–2.4 MB** blow the QA file-size gate + Gmail's 102 KB clip. The LEGO manual build **rasterizes nothing** — it reconstructs every card as live HTML (VML roundrect CTAs, per-corner radii, dark-mode classes).
- **The hidden cost — the "selective" half doesn't exist:** the high-loss detector requires RC‑E ingest extension (`_parse_node` reads **0** effect/gradient/vector/blend/rotation keys today). Raster-a-named-subtree ≈ 2–3 days; *deciding which* subtree ≈ 2–3 **weeks**.
- **Verdict:** a **narrow escape hatch** for purely-decorative, non-reproducible subtrees — never for content/CTA/personalized regions. Pair *with* (b), not instead of it.

### Recommendation (for the user to ratify)
The evidence favors a **(b)-with-(c)-as-escape-hatch** target *as the long-term engine*, **but** the entire decision is moot until the metric is trustworthy. So: **do not pick the fork yet.** Land Tier 0–1, get a real measured ΔE on ≥1 fixture, then spike (b) on the committed fixture (the recursive renderer can be run live today against the tree — partial spike already done) and confirm it doesn't regress under-segmenting cases before committing the 2.5–4 weeks.

---

## 7. The fix plan (sequenced, evidence-grounded)

### Tier 0 — Make the failure measurable *(the gate; fork-independent; do first)*
1. **Asset resolution (A‑1).** Cases 5/6/10: implement colon→underscore filename normalization in the asset resolver so existing on-disk PNGs bind. Cases 7/8/9: produce a node-id→file map (hand-map ~22 LEGO node-ids, or re-export from Figma keyed by node-id). **This unblocks everything.** *Est: 1–2d for 5/6/10; +1–2d per case needing export.*
2. **Wire the metric for real (finish RC‑F / 52.1).** Pass `blur=0.0` from `fidelity_service.py:80` (stop re-blurring); commit ≥1 un-gitignored fixture + its `design.png`; flip `fidelity_enabled` for the test path; run **advisory** in CI. *Est: 1–2d after assets.*
3. **Segmentation regression gate — but on band structure, not flat count.** Assert the **8 visual bands** are preserved as nested groups (not `== target_sections` naively — §3.2 nuance). Currently 0/6 fixtures structurally correct. Locks the metric before engine work. *Est: ~1d.*

### Tier 1 — Fix segmentation + last-mile structure *(highest ROI; partly fork-dependent — see #4)*
4. **Surgically fix the count-gate (S‑1) — do not disable the pass.** The all-6 passthrough control (§3.3) proves disabling `_expand_container_wrappers` *causes* the over-segmentation (fixes 7/8/9 exactly) but *regresses* the under-segmenting cases (5/10 get worse). So the fix is **band-preserving**, not removal: (a) **absorb `SPACER` pseudo-sections** into adjacent band padding (removes the 5 phantom LEGO sections + the leak at `:598`); (b) **keep wrapper children nested inside their band group** instead of exploding them to flat top-level sections (this is the over-segmentation cause *and* the flat-card cause §3.4); (c) **recurse single-child wrappers** so Starbucks/Mammut stop collapsing. ⚠ Whether the fixed-seed renderer can *emit* a nested band group is itself the RC‑C question — so #4 is only fully achievable under an engine that renders nested structure (fork b emits it for free). Under fork (a) this becomes "less wrong on all 6" rather than "exact". *Est: 3–5d; reusable under (b).*
5. **Render the detected nested-card structure (S‑3).** Emit the `_inner` table layer so `inner_bg`/`inner_radius` (already carried through the bridge) produce rounded white cards instead of flat bands. *Est: 2–3d.*
6. **Stop placeholder leakage (S‑4).** Fill heading slots from the real parsed text; treat `placeholder_in_output` as an error in the regression gate. *Est: 1d.*

### Tier 2 — Engine fork decision (§6) *(only after Tier 0 gives a real number)*
7. Spike (b) on the committed fixture; re-measure band correspondence on all 6; pick (a)/(b)/(c)-hybrid by **measured ΔE + effort**. Produce the 53.1 decision doc. *Est: 1 wk spike; implementation per chosen fork (a: ~1–1.5 wk incl. Tier 1 / b: ~2.5–4 wk / c: escape-hatch only).*

### Tier 3 — Ingest + remaining plumbing *(fork-dependent / latent)*
8. **RC‑E lossless capture (52.5):** node-scoped gradient `node_id`, opacity-vs-real-backdrop, AUTO/% line-height, non-button strokes. Capturing now stops irreversible loss even though it's latent on the frozen fixtures. *Est: 2–3d.*
9. **RC‑D′:** consume `style_runs` for per-run typography (the deferred 52.4b structural sub-project — needs per-node `<td>` anchors, not the shared `_heading`/`_body` class); fix per-side padding shorthand. *Est: 2–3d.*
10. **RC‑G:** revive the VLM loop on the default path **only after** assets resolve (its internal metric is the same blind comparison) — or honestly retire it from the roadmap. *Decision, then 2–3d.*
11. **Honest ceiling doc (52.7):** per-client achievable fidelity + the "cannot reproduce in email" list.

---

## 8. What "fixed" can honestly mean (the dual ceiling)

- **Physical:** table+VML email tops **~95% on Outlook/Word**. Drop/inner shadow, true gradients, SVG/vector, blend modes, opacity-over-non-white, rotation, and overlapping/z-ordered layers are **not reproducible** in the email box model — several also die at ingest (RC‑E).
- **Structural:** the fixed-seed renderer (RC‑C) caps below pixel fidelity regardless; the recursive renderer (fork b) reaches the **middle tier** (Auto-Layout/typography/gradient), never pixel/effects.
- **Realistic post-fix target:** correct band grouping + much higher typography/spacing/color fidelity on Gmail-class clients; a hard ~95% Outlook floor; effects/shadow/gradient/blend/rotation/overlap permanently below 100%. **The real number stays unknown until Tier 0 lands.**

---

## 9. Open risks / things still to verify
- **Band-correspondence of fork (b) on cases 6/8/9/10** — only LEGO verified live; (b) helps clean trees, not pathological ones.
- **The "8" target is a band count, not a section count** — the manual build is 17 blocks in 8 bands; don't write a gate that asserts a flat number (§3.2).
- **RC‑E is latent on the frozen corpus** — re-ingest losses won't show on `data/debug/*`; a live re-sync test is needed to exercise `_parse_node`.
- **Contrast warnings are now loud** (Performance 15, Starbucks 6) — that is the bridge fix *surfacing real* low-contrast color pairs, plus `_fix_text_contrast` mis-scoping (52.6); orthogonal to segmentation but worth a pass.
- **`source_frame_id`** is the one field still dropped by the bridge — currently harmless (write-only), but anything downstream that starts reading it will get `None`.

## 10. Provenance / re-run
- Workflow run id: `wf_f43162b1-56b` (resumable; cached agents return instantly). Script persisted under the session `workflows/scripts/` dir.
- Empirical scratch lives under `.tmpscratch/` (gitignored): `passthrough_all.py` (the all-6 control table in §3.3), `noexpand.py` (the LEGO 17→8 control), `sectype_hist.py`, `verify_claim.py`, `test_recursive_b*.py` (deleted-renderer live run), `audit_inversion.py` (metric inversion).
- Conversion entry point: `run_case_conversion(Path("data/debug/<N>"))` → `ConversionResult`. Run via `PYTHONPATH=. uv run python`.
- Recover the deleted recursive renderer: `git show d9132c7c^:app/design_sync/converter.py` (1625 LOC).
