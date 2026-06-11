# [REDACTED] Email Innovation Hub — Implementation Roadmap

> Derived from `[REDACTED]_Email_Innovation_Hub_Plan.md` Sections 2-16
> Architecture: Security-first, development-pattern-adjustable, GDPR-compliant
> Pattern: Each task = one planning + implementation session

---

> **Completed phases (0–49):** See [docs/TODO-completed.md](docs/TODO-completed.md)
>
> Summary: Phases 0-10 (core platform, auth, projects, email engine, components, QA engine, connectors, approval, knowledge graph, full-stack integration). Phase 11 (QA hardening — 38 tasks, template-first architecture, inline judges, production trace sampling, design system pipeline). Phase 12 (Figma-to-email import — 9 tasks). Phase 13 (ESP bidirectional sync — 11 tasks, 4 providers). Phase 14 (blueprint checkpoint & recovery — 7 tasks). Phase 15 (agent communication — typed handoffs, phase-aware memory, adaptive routing, prompt amendments, knowledge prefetch). Phase 16 (domain-specific RAG — query router, structured ontology queries, HTML chunking, component retrieval, CRAG validation, multi-rep indexing). Phase 17 (visual regression agent & VLM-powered QA). Phase 18 (rendering resilience & property-based testing). Phase 19 (Outlook transition advisor & email CSS compiler). Phase 20 (Gmail AI intelligence & deliverability). Phase 21 (real-time ontology sync & competitive intelligence). Phase 22 (AI evolution infrastructure). Phase 23 (multimodal protocol & MCP agent interface — 197 tests). Phase 24 (real-time collaboration & visual builder — 9 subtasks). Phase 25 (platform ecosystem & advanced integrations — 15 subtasks). Phase 26 (email build pipeline performance & CSS optimization — 5 subtasks). Phase 27 (email client rendering fidelity & pre-send testing — 6 subtasks). Phase 28 (export quality gates & approval workflow — 3 subtasks). Phase 29 (design import enhancements — 2 subtasks). Phase 30 (end-to-end testing & CI quality — 3 subtasks). Phase 31 (HTML import fidelity & preview accuracy — 8 subtasks). Phase 32 (agent email rendering intelligence — 12 subtasks: centralized client matrix, content rendering awareness, import annotator skills, knowledge lookup tool, cross-agent insight propagation, eval-driven skill updates, visual QA feedback loop, MCP agent tools, skill versioning, per-client skill overlays). Phase 33 (design token pipeline overhaul — 12 subtasks). Phase 34 (CRAG accept/reject gate — 3 subtasks). Phase 35 (next-gen design-to-email pipeline — 11 subtasks: MJML compilation, tree normalizer, MJML generation, section templates, AI layout intelligence, visual fidelity scoring, correction learning loop, W3C design tokens, Figma webhooks, section caching). Phase 36 (universal email design document & multi-format import hub — 7 subtasks: EmailDesignDocument JSON Schema, converter refactor, Figma/Penpot adapters, MJML import, HTML reverse engineering, Klaviyo + HubSpot ESP export). Phase 37 (golden reference library for AI judge calibration — 5 subtasks: expand golden component library with VML/MSO/ESP/innovation templates, reference loader & criterion mapping, wire into judge prompts, re-run pipeline & measure improvement, complete human labeling). Phase 38 (pipeline fidelity fix — 8 subtasks). Phase 39 (pipeline hardening — 7 subtasks). Phase 40 (converter snapshot & visual regression testing — 7 subtasks). Phase 41 (converter bgcolor continuity + VLM classification — 7 subtasks). Phase 42 (HTTP caching, smart polling & data fetching hardening — 7 subtasks). Phase 43 (judge feedback loop & self-improving calibration). Phase 44 (workflow hardening, CI gaps & operational maturity — 12 subtasks). Phase 45 (scheduling, notifications & build debounce — 6 subtasks). Phase 46 (provider resilience & connector extensibility — 5 subtasks: credential pool with rotation/cooldowns, LLM key rotation, ESP key rotation, credential health dashboard, dynamic ESP connector discovery via plugin system). Phase 47 (VLM visual verification loop & component library expansion — 10 subtasks: section screenshot cropping, VLM section-by-section diff, deterministic correction applicator, verification loop orchestrator, pipeline integration, component gap analysis 89→150+, extended matcher scoring, custom component generation AI fallback, verification tests, diagnostic trace enhancement; fidelity ladder: 85%→93%→97%→99%). Phase 48 (agent pipeline DAG, adversarial quality loops & cross-repo pattern adoption — 13 subtasks: pipeline DAG schema + template registry, parallel agent executor, typed artifact protocol, adversarial evaluator agent, quality contracts and stage gates, EmailTree JSON schema, scaffolder tree-mode generation, deterministic tree compiler, QA meta-evaluation framework, synthetic adversarial email generator, MCP response caching + schema compression, knowledge-graph proactive QA pipeline, agent execution hook system with profiles). Phase 49 (design-sync converter structural fidelity — 9 subtasks: sibling pattern detector, repeating-group renderer, section-to-component classification improvements, token override element-type expansion, per-node slot content extraction fidelity, per-email token scoping from shared Figma files, CTA fidelity button color/shape extraction, design-sync → EmailTree bridge, data-driven converter regression framework).

---

> **How to read this file.** This is the **remaining work only**, in **exact execution order** (top to bottom). Completed subtasks are recorded in [docs/TODO-completed.md](docs/TODO-completed.md). The **converter (active branch) runs first**, then Phase 50, then Phase 51 — independent workstreams that may interleave but are listed in priority order. Each task follows the convention **What / Why / Implementation / Verify / Plan**; the **Plan** line cites the file to read before starting, or marks it ⏳ *plan to be written*.

---

## Phase 52–53 — Figma→Email Converter Engine Fix (ACTIVE — branch `tech-debt/phase-52-converter-foundation`)

> **Operative plan:** `.agents/plans/53-converter-engine-fix.md` (2026-06-02) — supersedes the old linear `53.1–53.7`, the `52-converter-foundation.md §"Phase 53"` outline, and the `50-converter-fidelity-master.md` 50–53 labels + its 85→99% ladder. The Phase-52 foundation is **shipped** (serializer bridge un-inert RC-A/B, typography/align/CTA/radius overrides incl. 52.4a/b/c/d, `_fix_text_contrast` scoping — see docs/TODO-completed.md). What remains is **measurement + the engine fork**, sequenced by dependency.
>
> **Diagnosis (per the plan's re-audit — not independently re-confirmed here):** segmentation (wrong section counts) is the dominant *structural* defect (5/6 fixtures); the fidelity metric is **circular + inverted** until fixture assets resolve; only **case 5 (maap)** binds on disk. Express progress by **defect-class closure, not a fidelity %**.
>
> **Execution order:** A1 → A2 → Track B → Track C → A4 → A3 → 52.5 → **53.1 (gate)** → D → Track E.

### A1 — Structural count-ladder harness (GO/NO-GO) `[Backend]` `[✅ Done 2026-06-04]`

**What:** A deterministic harness beside `app/design_sync/tests/regression_runner.py` that prints, per fixture `data/debug/{5,6,7,8,9,10}`, the count ladder `target_sections (manifest) → len(_get_section_candidates) → len(analyze_layout().sections) → rendered section count`, plus per-section element bags (text/image/button) and a band-grouping descriptor. Commit all 6 fixtures' `structure.json` + `tokens.json` un-gitignored.
**Why:** Track C is built on the claim LEGO over-segments (8→21→17), which no prior session cleanly reproduced. The ladder is the first independent confirmation and the shared measurement substrate for B and C; committing inputs kills the per-session variance class.
**Implementation:** New harness file only; entry point exists — `run_case_conversion(Path("data/debug/<N>"))`. Add `!data/debug/*/structure.json` + `!data/debug/*/tokens.json` to `.gitignore`. Touch only the harness, `.gitignore`, the committed fixtures — do NOT edit `component_matcher.py` / `component_renderer.py` / `layout_analyzer.py` / the regression test.
**Verify:** `make types`; harness runs clean on all 6; prints the 6-row ladder. **GO/NO-GO:** confirm case 7 (LEGO) renders ~17 against target 8 — if it already groups to ~8, STOP and report (Track C's premise breaks).
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §4 Track A (A1).
**Result (commit `2f4d86e1`):** ✅ **GO** — `app/design_sync/tests/ladder_harness.py` reproduces the ladder for all 6 fixtures. LEGO confirmed **8→21→17** (target 8); pattern holds — over-seg LEGO 17/8 + slate 10/8, under-seg maap 11/13, starbucks 5/9, mammut 14/18. All 6 `structure.json` + `tokens.json` committed un-gitignored; `make types` 0 errors. Committing the fixtures **un-skips** the converter regression + snapshot suites in CI → verified **236 passed / 0 failed** in a clean HEAD worktree (CI's file view). Caveat for A2/Track C: band-count == candidate-count *by construction* (grouping inverts the unwrap) — the per-wrapper breakdown is the signal, not the count. Unblocks A2, Track B, Track C.

### A2 — Un-circular the regression gate `[Backend]` `[✅ Done 2026-06-05]`

**What:** Re-pin the section-count gate(s) from the converter's own output (`manifest.sections.count` / top-level `sections`) to the design `target_sections`.
**Why:** The old gate passed *because* the converter mis-segments, so it measured nothing. `target_sections` is the design truth (5→13, 6→9, 7→8, 8→10, 9→8, 10→18). *(= old 52.7 core.)*
**Done (commit `37996703`):** Shipped as a **full ladder-snapshot gate** — not a flat tolerance re-pin. A1 showed no single count cleanly recovers the target (band_count just inverts the wrapper-unwrap; rendered/marker counts are per-block), so: `TestSectionLadder.test_ladder_no_drift` hard-pins the full ladder (candidates/analyzed/rendered/bands + per-wrapper descriptor) to committed `data/debug/ladder_snapshot.json`; `test_rendered_matches_target` + the second circular gate `TestSnapshotSectionCount` xfail `rendered == target_sections`. `manifest_schema.py` untouched (target lives in the top-level manifest, reused via `ladder_harness.load_target_sections`). Parametrized over discovered fixtures so a missing snapshot fails loudly. 6/6 target-xfail + 6/6 drift-pass today; both make-gates green; topology tests intact.
**Carry-forward:** target gate is advisory `xfail(strict=False)` over a per-block metric (`sections_count == len(match.matches)`) vs a band target — may not converge if Track C/D groups at render time; `regression_runner.py:113` still circular (advisory). Tracked: deferred-items `phase-53-a2-advisory-section-gate` → tighten at 53.1/D.
**Plan:** `.agents/plans/53-converter-engine-fix.md` §4 Track A (A2).

### Track B — Cheap, ship-now render fixes (B1–B8) `[Backend]` `[✅ Done 2026-06-10 — B1–B8 complete, merged to main]`

**What:** Eight small per-section fixes to today's shipped render output, in churn-minimizing order.
**Why:** Each is a real defect in the live output, ≤1d, that the A2 gate finally sees. **B1 is the only fork-surviving fix** (the edited seeds also feed the DB component library); the rest die under fork-(b) but fix shipped output now.
**Implementation (in order):** **B1** seed-literal cleanup (`col-icon.html:73,106`, `image-grid.html:16,30`; retire dead `data-slot-alt`) → **B7** phantom `faq-accordion` slug (`component_matcher.py:474`) → **B5** alt derivation (`component_matcher.py:795,1455`) → **B8** multi-CTA, emit all `section.buttons` (`component_matcher.py:930,1002,1062,1189,1286,1671`) → **B2** inner-table column builder (`component_matcher.py:784`, `_column_text_row:759`) → **B3** post-fill blank pass (`component_renderer.py:551`) → **B4** footer regex fix (`component_renderer.py:601`; sequence after B3 — shared `_fill_text_slot`) → **B6** width clamp `max-width:640px` (`component_renderer.py:1172,1179`).
**Verify:** Each fix changes `expected.html` → after EACH: regen baselines + `app/design_sync/tests/snapshot_diff_audit.py` intended-vs-structural review (never assert-unchanged — this caught the 52.4c double-`style=` bug). For B3, confirm footer legally-required fields aren't blanked. `make test` + design_sync suite green.
**Progress:**
- **B1 ✅** (commit `7f299e6e`) — seed-literal cleanup; the one fork-surviving fix (edited seeds also feed the DB component library).
- **B7 ✅** (commit pending) — dropped phantom `faq-accordion` slug → falls to `text-block` (has a slot-fill builder; `faq-list` does not, so a remap would render placeholder Q/A). Removed the now-dead `has_images` param from `_score_extended_candidates` + its callsite; updated `test_faq_question_answer_pairs`. **Baseline-neutral** — `faq-accordion` never fired on the 6 fixtures (no `expected.html` contained it), so no baseline regen needed. be-ship green (lint/mypy/pyright at baseline, 126 matcher tests, converter regression 68 passed).
- **B5 ✅** (commit `4bc095ae`) — alt derivation: `_is_descriptive_alt`/`_derive_image_alt` stop the raw-`node_name` leak (`mj-image, (mjml:mj-image), (type: logo)`). Leak spanned **8** emission sites, not the 2 originally scoped — also the 4 `SlotFill(image_alt)` + 1 `SlotFill(logo_alt)` feeders + the `_fills_social` fallback. Descriptive name kept, else `Company logo`/`Content image`; never `alt=""`, **G3-neg untouched**. Also fixed `col-icon.html` linked-icon `alt=""`→`Feature icon` (unlabeled-link a11y bug). 0 empty/generic/leak alts across all 6 fixtures; baselines regen (alt-only diff, audit clean); golden-conformance + component suite green. Decision + execution note: `.agents/plans/53-b5-alt-derivation-decision.md`; closed deferred-item `phase-53-b5-decorative-empty-alt-vs-g3neg` (Tier-1 verified shipped on main, golden-conformance green; ledger `1772cad8` 2026-06-11; Tier-2 semantic alt + decorative flag → RC-E).
- **B8 ✅** (PR #241, squash `7894ff03`) — multi-CTA routing: ≥2 buttons → `cta-pair` seed (`primary_*`/`secondary_*` slots); single button keeps `cta-button`.
- **B2 ✅** (commit `c3f7fcd8`) — inner-table column builder: img/text/CTA rows wrapped in one `<table role="presentation">` via shared `_column_image_row`/`_column_cta_row`/`_wrap_column_table`; baselines 5–10 regen.
- **B3 ✅** (commit `925d4e05`) — post-fill blank pass `_blank_unfilled_text_slots`; footer legally-required fields preserved (`_PRESERVE_UNFILLED_SLOTS`).
- **B4 ✅** (commit `0bf96eda`) — footer de-truncation: depth-balanced `_find_matching_close` replaces the `(.*?)`+`count=1` that truncated nested `footer_content`.
- **B6 ✅** (commit `02bb1b8e`) — clamp `width="640"`/`max-width:640px`/`width:640px` MSO widths to container; latent on corpus, unit-tested.
- **B8 follow-up ✅** (commit `b50dcf13`) — per-button cta-pair color fidelity (`_cta_primary`/`_cta_secondary` overrides + block-scoped `_apply_cta_pair_override`); closed deferred-item `phase-53-b8-cta-pair-color-fidelity`.
- **Merged to `main`** 2026-06-10 via `--no-ff` merge `f9787f2c` (full B2→B8 stack; merged-tree `make test` 8157 green).
- **B8 follow-up ✅** (commit `2bb6bdbf`, merged `7d5692f0` 2026-06-11) — slug-aware `_fills_cta`: slot set keyed on the chosen slug threaded through `_build_slot_fills`, not button count (VLM fallback path could desync slug from fills); also fixed the same desync class on `text-link` (`link_text`/`link_url`); closed deferred-item `phase-53-b8-fills-cta-slug-desync-vlm`. Rider `e3c80a81` un-reds main's `make check` (`lint-numeric` false positive on B6's "600 or 640" docstring).
- **B8 follow-up ✅** (commit `5d0b2bdb` fix + `b8aa6d1a` ledger 2026-06-11) — non-CTA multi-button drop: `_fills_text_block` now loops over every `section.buttons` (was `buttons[0]`), so a stacked CTA pair in one column (mammut case 10: "SHOP THE COLLECTION" + "DISCOVER EIGER EXTREME 6.0") renders both. **Fill bug, NOT the segmentation/classification problem the ledger first framed** — LCA showed case 10 sec#1 is a correctly-segmented single `mj-column` (`mj-wrapper > mj-section > mj-column > [text,text,btn,btn]`); section counts unchanged (A2 ladder untouched). The diff-audit surfaced a second defect the loop exposed: outlined buttons (white fill + stroke) were forced `color:#ffffff` → invisible white-on-white; stroke-gated, they now emit their designed `text_color`+border (fixed cases 7 & 10). Guard `TestButtonInTextBlock.test_text_block_renders_all_buttons` (RED pre-fix); baselines 7,10 regen (diff-audited), 5/6/8/9 byte-identical; gates green (types 0, golden-conformance 26, `make test` 8163). Closed deferred-item `phase-53-b8-non-cta-multibutton-drop`; new speculative residual `phase-53-b8-text-block-solid-cta-text-color` (solid-fill CTAs keep hardcoded white — case 5 maap design says `#010101`, needs a committed render to adjudicate). **Track B (B1–B8) + all follow-ups now complete.**
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §Track B (B1–B8 table with file:line). *(≈ 1 week total.)*

### Track C — Segmentation spike (C1, C2) `[Backend]` `[Plan Ready · SPIKE]`

**What:** Address the dominant structural defect — the converter cuts the wrong number of sections. **C1** emits a tagged band group (`RepeatingGroup`) when a multi-child wrapper is unwrapped; **C2** recurses single-child wrappers + absorbs `SPACER` pseudo-sections.
**Why:** Segmentation drives perceived fidelity. C1 fixes the over-count (LEGO 17, slate 10 → 8); C2 fixes the under-count (Starbucks/maap/mammut). Run as a **spike** because the fix may be subsumed if fork-(b) wins at the gate.
**Implementation:**
- `[⏳ TODO]` **C1** — in `_expand_container_wrappers` (`app/design_sync/figma/layout_analyzer.py:540-576`) emit a tagged band group into the existing group-aware `_match_phase` / `render_repeating_group` path (`converter_service.py:610-638`; `component_renderer.py:514-528`); steer repeated cards to an `_inner`-bearing seed (`article-card`), not `text-block`.
- `[⏳ TODO]` **C2** — recurse the single-child wrappers the `≥2` predicate leaves merged (`:584`); reuse `physical_card_detector.find_physical_card_in_subtree` (depth≤4), do NOT write a new walker.
**Verify:** A1 ladder shows LEGO 17→8 with correctly nested bands; report the all-6 ladder + the residual cases fork-(b) would still beat. **Do NOT full-commit** — this feeds the 53.1 gate.
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §Track C (prereq: A1 confirms LEGO ~17).

### A4 — Figma node-id-keyed re-export (cases 6–10) `[Backend · USER action]` `[Plan Ready · long pole — start early]`

**What:** Re-export frames for cases 6/7/8/9/10 keyed by the node-ids the converter currently emits, so the pixel metric has an on-disk image map.
**Why:** The emitted node-ids have no on-disk image map today (only case 5/maap binds) — this is the real blocker for a trustworthy *multi-fixture* fork decision.
**Implementation:**
- `[⏳ TODO]` Per case, either (a) live re-export keyed by current node-ids (needs the Figma file + a PAT), or (b) hand-map the semantic PNGs → node-ids.
- `[⏳ TODO]` LEGO *structure* re-parses offline from `.agents/figma-cache/node_2833_1869.json`, but its *images* still need (a) or a ~24-PNG hand-map; perf/slate need live Figma.
**Verify:** ≥2 fixtures (including an over-segmenter) resolve so the metric becomes gate-worthy.
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §4 Track A (A4) — **needs USER / Figma access; begin before the gate.**

### A3 — Case-5 pixel metric, advisory `[Backend]` `[Plan Ready]`

**What:** Wire the (already-correct) fidelity metric to render case-5 HTML via Playwright and compare it against the reference PNG; land advisory in CI.
**Why:** Closes the "can't measure" gap on at least one fixture. The metric code is correct (CIEDE2000 in LAB, MIN-aggregated, blur 0.0); only the wiring + a committed fixture are missing. *(= old 52.1-finish.)*
**Implementation:**
- `[⏳ TODO]` Promote `.tmpscratch/fidelity_case_scorer.WIP.py` + its test into `app/design_sync/`.
- `[⏳ TODO]` Commit case-5 `assets/` (6 PNGs) + the reference `…/for_converter_engine/maap/visual_design.png`.
- `[⏳ TODO]` Land the test-harness-only src-rewrite (`/assets/<node>.png` → `file://…/data/debug/5/assets/…`) before screenshot.
**Verify:** Metric runs in CI on the committed case-5 fixture; stored as advisory. **Never a ship-gate** until ≥2 fixtures resolve (case 5 under-segments → yields *a* number, not the over-segmentation verdict).
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §4 Track A (A3) — harness built but **uncommitted** in `.tmpscratch/*.WIP.py`.

### 52.5 — Ingest RC-E lossless capture `[Backend]` `[Plan Ready · fork-independent]`

**What:** Capture data the ingest currently drops: composite alpha vs the real backdrop, gradient `node_id`, non-button strokes, AUTO/% line-height.
**Why:** Correct under any Phase-53 engine; capturing now stops irreversible loss and unblocks the fork's renderer (render of the captured data lands in 53.3).
**Implementation:**
- `[⏳ TODO]` `app/design_sync/figma/service.py:265-291` `_rgba_to_hex_with_opacity` — composite against the real parent/section bg, not hard-coded `#FFFFFF` / `OPACITY_COMPOSITE_BG`.
- `[⏳ TODO]` `app/design_sync/protocol.py` — add `node_id` to `ExtractedGradient` (+ `DocumentGradient`).
- `[⏳ TODO]` Add a stroke field on `DocumentSection` / `DocumentImage` (already read at `figma/service.py:619`).
- `[⏳ TODO]` Read `lineHeightPercent` / `lineHeightPercentFontSize` when `lineHeightPx` is absent.
**Verify:** Unit tests — translucent-over-color composites against the real bg; gradient carries `node_id`; bordered card keeps its stroke. (Render assertions land in 53.3.)
**Plan:** ✅ `.agents/plans/53-converter-engine-fix.md` §Track E + `.agents/plans/52-converter-foundation.md` §52.5.

### 53.1 — Strategy-fork decision (GATE) `[Backend · decision gate]` `[⏳ output: write the chosen-fork sub-plan]`

**What:** With the live metric + the Track C spike, choose the engine direction — **(a)** keep fixed-seed + Track C patch · **(b)** restore the recursive renderer · **(c)** per-frame raster — and write the chosen sub-plan.
**Why:** Each option implies a different home for ingest render (RC-E) and the VLM loop, so it must be decided before any downstream engine build — on a real number, with segmentation as the explicit success criterion.
**Implementation:**
- `[⏳ TODO]` Re-run the fork spike on the committed fixtures with the live metric.
- `[⏳ TODO]` Record measured ΔE + effort per option.
- `[⏳ TODO]` Author the decision doc + the selected sub-plan.
- _Recommended posture (audits' consensus, to ratify): A+B regardless; C as a spike; lean (b)-long-term + (c)-escape-hatch only if the metric + multi-fixture spike justify the weeks; never (c) as default._
**Verify:** Decision recorded; chosen fork's sub-plan written to `.agents/plans/`; stakeholder sign-off.
**Plan:** procedure in `.agents/plans/53-converter-engine-fix.md` §Gate; **its output is a new sub-plan — ⏳ to be written here.** Unblocked by A3 (+ ideally A4) + the Track C spike.

### D — Execute the chosen fork `[Backend]` `[⏳ Plan to be written at 53.1]`

**What:** Build the engine direction chosen at 53.1 (the structural "for good" fix).
**Why:** Closes the segmentation ceiling (and, for fork b/c, asymmetric columns / pixel fidelity).
**Implementation:** (build only the fork chosen at 53.1)
- `[⏳ TODO]` **(a)** full-commit Track C across all 6 fixtures + a per-column-width override.
- `[⏳ TODO]` **(b)** add a `convert_from_structure` tree-persistence entry, rebuild the recursive renderer re-wired to the live extracted helpers (NOT a verbatim restore — `d9132c7c` pre-extracted ~8 helpers into `shared/color.py`/`sanitizers.py`/`token_transforms.py`/`protocol.py`), rebuild the deleted ~4,490-LOC test corpus, keep `data-slot` hooks so editability survives.
- `[⏳ TODO]` **(c)** wire raster only as a per-subtree fallback behind a reproducibility classifier.
**Verify:** A1 ladder + A3 metric improve vs the pre-fork baseline; `make converter-data-regression` green.
**Plan:** ⏳ **NEEDS WRITING** — only the per-fork framing exists (`.agents/plans/53-converter-engine-fix.md` §Track D); the concrete sub-plan is authored at the 53.1 gate.

### Track E — Ingest render + remaining plumbing `[Backend, Docs]` `[mixed — some Ready, some ⏳ post-fork]`

**What:** The fork-dependent + latent items that land after (or alongside) the gate.
**Why:** Render the data 52.5 captures, decide the VLM loop's fate, recover vectors, and publish the honest ceiling — each measured by the real metric, not the blind ladder.
**Implementation (per item):**
- **RC-D′ — per-run typography** `[Plan Ready]`: emit one `data-node-id` `<td>` per text node + a `_text_<node_id>` override target + renderer dispatch arm. Closes deferred `phase-52.4b-per-run-typography-structural`; subsumed if fork-(b) wins. → §Track E.
- **53.3 — never-parsed ingest render** `[⏳ plan post-fork]`: effects/blendMode (VML/flat fallback), per-node gradient reattach (uses the 52.5 `node_id`), `scaleMode`/`imageTransform` crop, rotation, z-order/overlap → `frame_export`.
- **53.4 — revive or honestly RETIRE the VLM loop** `[⏳ plan post-fork]`: dead on the default path (`vlm_verify_enabled=False`; correction applicator is property-only — cannot add/remove/reorder/merge sections); metric returns 1.0 on empty input. Decide explicitly — no silent "it lifts fidelity" claim.
- **53.5 — decorative vector recovery** `[⏳ plan post-fork]`: standalone VECTOR/LINE nodes fall through extraction (`layout_analyzer.py:1088-1167`) — add a `DocumentVector` class OR rasterize / inline-PNG the subtree.
- **53.7 — honest ceiling doc + numbering supersession** `[Plan Ready]`: per-client ceiling table; correct `docs/fidelity-gap-audit-findings.md`; banner the stale 50–53 labels in `50-converter-fidelity-master.md`; add deferred-items entries (typography `maxItems:200` cap vs LEGO's 234; the asset re-export prerequisite; the circular-gate fix). → §Track E.
- **deferred/ stub promotion (×23)** `[⏳ plan per stub]`: promote only the `.agents/plans/deferred/` Rules-1–11 / composite-slot stubs the chosen fork keeps (folds in old 53.6); each gets a detailed plan at promotion.
**Verify:** per-feature fixtures render within ΔE tolerance OR fall back to a documented flat export; the real A3 metric confirms.
**Plan:** framing in `.agents/plans/53-converter-engine-fix.md` §Track E; **53.3 / 53.4 / 53.5 + each stub ⏳ need plans written** (post-fork).

---

## Phase 50 — Tech Debt Closeout & Audit Reconciliation (remaining: 5)

> Independent workstream. Execution order: 50.6.2 ∥ 50.6.3 ∥ 50.6.4 (parallel-safe) → **50.7 → 50.5** (the only hard chain). 50.1–50.4 + 50.6.1 are shipped (see docs/TODO-completed.md); 50.8 is a SKIP.

### 50.6.2 — Briefs BOLA-by-Creator Isolation Test `[Backend, Testing]` `[Plan Ready]`

**What:** Test that a brief created by user A cannot be read/updated/deleted by user B in the same org, via the route AND the repository.
**Why:** Briefs are per-creator (not org-scoped) and that boundary is untested. Closes deferred entry `tech-debt-03-briefs-user-isolation-test`.
**Implementation:**
- `[⏳ TODO]` Create `app/briefs/tests/test_user_isolation.py` mirroring the pattern in `app/projects/tests/test_bola.py`.
- `[⏳ TODO]` Explicitly assert same-org-different-user as the contrast case.
**Verify:** New test passes; route + repository layers both exercised; `make check` green; deferred entry flipped to `closed`.
**Plan:** ✅ `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.2.

### 50.6.3 — Squawk Python-Migrations Decision + Cleanup `[Backend, DB]` `[Plan Ready]`

**What:** Resolve the misleading "passing" squawk advisory (plan recommends Option b — remove it, document manual review).
**Why:** Squawk doesn't actually lint Python migrations, so the green CI check is false assurance. Closes `tech-debt-squawk-python-migrations`.
**Implementation:**
- `[⏳ TODO]` Remove the squawk hook from `.pre-commit-config.yaml:92-94`.
- `[⏳ TODO]` Drop the squawk job from `.github/workflows/ci.yml:243-272`.
- `[⏳ TODO]` Update/no-op the `migration-lint` Makefile target.
- `[⏳ TODO]` Strip `# squawk-ignore` comments.
- `[⏳ TODO]` Add manual-review guidance to `.claude/rules/architecture.md` or a new `.claude/docs/migration-safety.md`.
**Verify:** No misleading advisory in CI; gap documented; `make check` green; deferred entry flipped.
**Plan:** ✅ `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.3.

### 50.6.4 — DESIGN_SYNC__* Flag Cull (PR-1 only) `[Backend]` `[Plan Ready]`

**What:** Constantize the (constantize) subset of `DesignSyncConfig` fields (61 today) — additive, no behavior change, no test deletion.
**Why:** The config carries far more flags than warranted; PR-1 trims the constant-only set. Closes part of `tech-debt-19-design-sync-flag-cull-deeper`.
**Implementation:**
- `[⏳ TODO]` For each (constantize) field: move it to a `Final` constant in `app/design_sync/tuning.py`, update consumers, delete the config field.
- `[⏳ TODO]` Add a bounded-count regression test (`len(DesignSyncConfig.model_fields) <= 45`) in `app/core/tests/test_config_design_sync.py`.
- _Constraint: do NOT touch (retire-feature) candidates this round._
**Verify:** Field count 45–50 (~15–17 constantized); `make flag-audit` clean; `make check-full` green; a new deferred entry created for the PR-2 (retire-feature) follow-up.
**Plan:** ✅ `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.4. *(PR-2 = ⏳ plan + deferred entry to write when PR-1 ships.)*

### 50.7 — Squash Multi-DB Redesign `[Backend, DB]` `[Plan Ready]` — prerequisite for 50.5

**What:** Rewrite the squash flow so the generated baseline contains `CreateTable` for every model (today its `upgrade()` body is empty `pass`).
**Why:** The current squash autogenerates against the *populated* DB, so a fresh-DB bootstrap (CI, onboarding, DR) creates no schema and the app crashes. Closes known-bug `tech-debt-19-squash-empty-baseline` and unblocks 50.5.
**Implementation:**
- `[⏳ TODO]` Rewrite `scripts/squash-migrations-dryrun.sh` to use three throwaway containers (reference / autogenerate-target / validation) + an `op.create_table` count assertion + a `pg_dump` parity check.
- `[⏳ TODO]` Rewrite `scripts/squash-migrations.sh` to autogenerate against an ephemeral empty container (production untouched until the final stamp).
- `[⏳ TODO]` Update the runbook step 5 + remove its BLOCKED callout.
- `[⏳ TODO]` Flip the deferred entry.
- `[⏳ TODO]` Update `TECH_DEBT_AUDIT.md` F057 BLOCKED→READY.
**Verify:** `bash scripts/squash-migrations-dryrun.sh` exits 0 end-to-end; `grep -c op.create_table` on the baseline == `len(Base.metadata.tables)`; schema diff empty; `make check-full` green.
**Plan:** ✅ `.agents/plans/tech-debt-19-squash-multi-db-redesign.md`.

### 50.5 — Execute Migration Squash `[Backend, DB]` `[BLOCKED on 50.7 — design flaw]`

**What:** Squash the ~46 alembic migrations to a single baseline during a maintenance window.
**Why:** Reduce migration-chain weight. **DO NOT RUN `make db-squash` until 50.7 ships** — the current scripts + runbook share the empty-baseline design flaw (cutover succeeds deceptively; the next fresh-DB bootstrap crashes).
**Implementation:** (after 50.7 ships — BLOCKED until then)
- `[⏳ TODO]` Produce the consolidated baseline (`down_revision = None`).
- `[⏳ TODO]` Archive the historical migrations.
- `[⏳ TODO]` Drop the `2eb1d5b05ad3_merge_heads.py` artifact.
- `[⏳ TODO]` Maintenance-window cutover with snapshot rollback.
**Verify:** `alembic heads` single; `alembic upgrade head` clean on a fresh DB; existing prod DB applies the baseline as a no-op; operator postmortem in `docs/migrations/`.
**Plan:** ⚠️ `.agents/plans/tech-debt-19-runbook-db-squash.md` + `scripts/squash-migrations-dryrun.sh` — **design-broken; must be redesigned by 50.7 before execution.**

---

## Phase 51 — Agentic Security Hardening (remaining: 6 — strictly serial)

> Independent workstream. Execution order: **51.2 → 51.3 → 51.4 → 51.5 → 51.6 → 51.7** (51.4 must precede 51.7). 51.1 (credential revocation on kill) is shipped. All ship behind `SECURITY__*` flags; no regressions to the G1–G5 envelope; ≤50ms p95 overhead; calibration gate within 5pp after each. Plan: `.agents/plans/51-agentic-security-hardening.md`.

### 51.2 — Safe Compaction (Pinned Safety Instructions) `[Backend, Security]` `[Plan Ready]`

**What:** Pin the system prompt + safety constraints so they survive context-window slide / compaction across all blueprint-engine and agent-service operations.
**Why:** OpenClaw-class fix — stops the in-band safety check disappearing mid-loop when context compacts.
**Implementation:**
- `[⏳ TODO]` `app/ai/security/safe_compaction.py` `PinnedPrompt` wrapper.
- `[⏳ TODO]` Integrate into `BaseAgentService.process` (all 9 agents inherit) + `BlueprintEngine` cross-node sliding.
- `[⏳ TODO]` Flag `SECURITY__SAFE_COMPACTION_ENABLED` (default true).
**Verify:** `app/ai/security/tests/test_safe_compaction.py` (~15 tests) incl. a property test (10k random compactions, safety-instruction count ≥1 in every output); `make eval-calibration-gate` no regression.
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.2.

### 51.3 — Tool-Call Cap + Planning Telemetry `[Backend, Security]` `[Plan Ready]`

**What:** A deterministic `SECURITY__AGENT_MAX_TOOL_CALLS` circuit breaker + structured per-step planning telemetry.
**Why:** Completes the K_max trio with the existing run-seconds + token caps; bounds how far an agent can drift before a deterministic stop.
**Implementation:**
- `[⏳ TODO]` Counter in `BaseAgentService.process` raising `AgentKMaxExceededError` (new, in `app/ai/security/exceptions.py`).
- `[⏳ TODO]` Emit `ai.agent_planning_step` per `_execute_from` iteration (step_id + tool_call_count + cumulative_tokens + elapsed_ms).
- `[⏳ TODO]` Add a `bench_security_envelope` case to `make bench`.
**Verify:** `app/ai/security/tests/test_tool_call_cap.py` (at-cap / over-cap / per-agent-override) + telemetry assertions in `test_engine.py`.
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.3.

### 51.4 — Tamper-Evident Append-Only Audit `[Backend, Security]` `[Plan Ready]` — blocks 51.7

**What:** Convert the agent audit log to a chained-hash append-only structure + a replay-verification CLI.
**Why:** The audit trail can no longer be silently rewritten; 51.7's `ai.agent_killed` entries become part of this chain (the dependency).
**Implementation:**
- `[⏳ TODO]` Extend `AgentAuditLog` (`app/ai/agents/audit.py`) with `prev_hash` + `entry_hash` columns (alembic migration).
- `[⏳ TODO]` Insert path computes `entry_hash = sha256(prev_hash || json(entry))` and rejects mismatch.
- `[⏳ TODO]` `app/ai/agents/audit_chain.py::verify_chain()` + `python -m app.ai.agents.audit_chain verify` CLI.
- `[⏳ TODO]` Flag `SECURITY__AUDIT_CHAIN_ENABLED`.
**Verify:** `app/ai/agents/tests/test_audit_chain.py` — append 100 entries + verify; tamper row 50 → verify reports divergence at row 50.
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.4.

### 51.5 — Toxic-Combination Policy DSL `[Backend, Security]` `[Plan Ready]`

**What:** A declarative policy DSL (`DENY tool[internal_db_read] WHEN session.has(tool[outbound_network])`), evaluated per tool invocation, default-deny on ambiguity.
**Why:** Replaces procedural enforcement scattered across agent services with explicit, auditable toxic-combination boundaries.
**Implementation:**
- `[⏳ TODO]` `app/ai/security/policy/` package — `dsl.py` (Lark grammar + `rules.yaml` loader), `evaluator.py` (`Evaluator.check(action, session_context) -> Decision`).
- `[⏳ TODO]` Wire into `BaseAgentService.process` as the pre-dispatch gate.
- `[⏳ TODO]` Ship 5–10 initial toxic-combination rules.
- `[⏳ TODO]` Flag `SECURITY__POLICY_DSL_ENABLED`.
**Verify:** `app/ai/security/policy/tests/test_evaluator.py` (~25 tests, allow/deny/ambiguous) + an integration test through a real agent invocation.
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.5.

### 51.6 — HITL Cryptographic Signatures `[Backend, Frontend, Security]` `[Plan Ready]`

**What:** Require an external Ed25519 signature the agent cannot fabricate for irreversible / high-impact actions (first targets: ESP export, credential rotation).
**Why:** A hard gate on irreversible operations the model can't satisfy on its own.
**Implementation:**
- `[⏳ TODO]` `app/ai/security/hitl.py` (`SignatureChallenge`, `verify_signature(action_id, signature, public_key)`).
- `[⏳ TODO]` New `hitl_approvals` table + migration.
- `[⏳ TODO]` Backend gate checks the signature before dispatch.
- `[⏳ TODO]` WebAuthn signature input in `cms/apps/web/src/components/approvals/approval-decision-bar.tsx`.
- `[⏳ TODO]` Config `SECURITY__HITL_REQUIRED_FOR` (default `["esp_export","credential_rotate"]`).
**Verify:** `app/ai/security/tests/test_hitl.py` (~20 tests, valid/invalid/expired + agent-fabrication rejection); Playwright signature smoke (`approval-signature.spec.ts`).
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.6.

### 51.7 — Infra-Level Kill + Sandboxed Tool Execution `[Backend, DevOps, Security]` `[Plan Ready · blocked on 51.4]`

**What:** Move agent MCP tool execution into an isolated `services/tool-runner/` sidecar; out-of-band kill at the orchestrator layer.
**Why:** Enforces toxic-combination limits at the OS boundary (not in-process); the kill works regardless of the agent's LLM state.
**Implementation:**
- `[⏳ TODO]` `services/tool-runner/` (`POST /execute`) with cgroup/CPU/network-egress limits + seccomp.
- `[⏳ TODO]` Reroute `app/mcp/tools/` invocations through an HTTP client to the sidecar.
- `[⏳ TODO]` `app/ai/security/kill_switch.py::kill_agent()` SIGTERMs the sidecar + writes the `ai.agent_killed` chain entry (consumes 51.4).
- `[⏳ TODO]` Add the service to `docker-compose.yml`.
- `[⏳ TODO]` Flag `SECURITY__SANDBOXED_TOOLS_ENABLED` (default false until soak).
**Verify:** `services/tool-runner/tests/` + `app/mcp/tests/test_sandbox_dispatch.py`; manual kill drill — trigger mid-tool-call, sidecar terminates <1s + audit-chain entry recorded.
**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` §51.7 (blocked on 51.4).

---

## Phase 54 — Activate or Retire the Agent Self-Improvement Loops (optional — DECISION-GATED, not yet committed)

> **Optional, strategic — do not start without ratifying 54.0.** Source: `docs/agentic_rl_memory_handoff_findings.md` (2026-06-05, 5-agent audit). The RL-inspired machinery shipped across P15 (adaptive routing, phase-aware memory, prompt amendments, knowledge prefetch), P32 (cross-agent insight propagation, eval-driven skill updates, visual-QA feedback), P43 (judge feedback loop & self-improving calibration) and P48 (agent pipeline DAG — parked to `prototypes/`) is **built-but-inert**: every online loop ships behind a default-OFF flag, the reward corpus is uncommitted/inert, and memory recall was dead-on-read (deferred-item `tech-debt-03-memory-recall-dead-on-read` — ✅ fixed 2026-06-11, `0b0313aa`; recall now reaches prompts). This phase decides whether to **light it up** (corpus-first) or **delete it** (today it is maintenance cost + false capability). **Scope: the agent-generation pipeline only — it does NOT touch converter fidelity (Phase 52-53); the converter is deterministic and outside the agent loop.**

### 54.0 — DECISION GATE: activate vs. retire (per loop) `[Backend · decision gate]` `[⏳ user call]`

**What:** Decide, per loop, activate-with-measurement vs. delete: inline judge-on-retry, judge-aggregation prompt-patching, recovery-outcome ledger reroute, confidence calibration, insight propagation, adaptive model-tier routing.
**Why:** "Built-but-inert" is the worst state — cost with no benefit and a false sense of capability. Commit to validating it, or remove it.
**Verify:** A written per-loop decision (activate/delete) + the rollout-measurement plan or the deletion list.
**Plan:** ⏳ to be written — basis: `docs/agentic_rl_memory_handoff_findings.md` §3.1/§3.3 (per-component live-vs-inert tables + flag defaults) and §7.3.

### 54.1 — PREREQUISITE: build the reward corpus `[Backend, Eval]` `[⏳ blocked on 54.0 = activate · 1/5 sub-items done]`

**What:** Make the eval/reward corpus real before any online loop is enabled. Sub-items:
- `[⏳ TODO]` Commit (or seed) the gitignored `traces/` so a fresh deploy has `analysis.json` for `failure_warnings`.
- `[⏳ TODO]` Populate the empty/absent `{agent}_human_labels.jsonl` so judges are actually TPR/TNR-calibrated.
- `[⏳ TODO]` Set a small `EVAL__PRODUCTION_SAMPLE_RATE` to collect on-policy verdicts.
- `[✅ Done 2026-06-11]` Land the `tech-debt-03-memory-recall-dead-on-read` fix (`0b0313aa` — all 15 background/agent memory-op sites now open `get_system_db_context`; recall reaches prompts; guarded by `app/tests/test_memory_recall_integration.py`).
- `[⏳ TODO]` Register `MemoryCompactionPoller` in `app/main.py` — defined at `app/memory/compaction.py:60` but never instantiated, so decay/compaction never runs (unbounded growth once writes are turned up).
**Why:** Enabling uncalibrated judges/loops on an empty corpus makes agent output **worse** — the reward signal is noise. Corpus first, always (findings doc §2.1/§2.4 anti-patterns).
**Verify:** clean-worktree test — `get_failure_warnings()` injects a real KNOWN-FAILURE block into an agent prompt; judges hit TPR≥0.85 / TNR≥0.80 on the human-label set; a blueprint run injects a recalled memory (✅ proven by `app/tests/test_memory_recall_integration.py::test_blueprint_engine_recall_injects_memory` — RED before `0b0313aa`, GREEN after).
**Plan:** ⏳ to be written.

### 54.2 — Enable loops behind a measured rollout (or delete) `[Backend, Eval]` `[⏳ blocked on 54.1]`

**What:** For each loop 54.0 kept: flip its flag on behind a before/after `make eval-calibration-gate` + golden-set comparison; keep only loops that lift pass-rate without regressing the 3pp/5pp gates or cost. Delete the rest — plus the inert structured-decision/`plan_merger` path and the adaptive-tier code that never reads `effective_tier`, if not adopted.
**Why:** Each loop earns its place on a real number — same discipline as the converter fork gate (53.1).
**Implementation:** stage `BLUEPRINT__JUDGE_ON_RETRY`, `__RECOVERY_LEDGER_ENABLED`, `__CONFIDENCE_CALIBRATION_ENABLED`, `__JUDGE_AGGREGATION_ENABLED`, `__INSIGHT_PROPAGATION_ENABLED`, `AI__ADAPTIVE_ROUTING_ENABLED`; for adaptive routing also wire nodes to read `metadata["effective_tier"]` (today inert — engine computes it, no node reads it) or delete the loop. Note: structured decisions are doubly dead — `build_plan` never threads between nodes — so reviving `plan_merger`/`TemplateAssembler` is its own sub-task, not a flag flip.
**Verify:** per-loop eval delta recorded via `improvement_tracker`; no regression to calibration/golden gates; cost within budget.
**Plan:** ⏳ to be written.
