# Phase 53 — Figma→Email Converter Engine Fix ("for good")

> Companion to `.agents/plans/52-converter-foundation.md` (Phase 52 = property *plumbing*, largely shipped). **This plan is the ENGINE** — the layer that dominates *perceived* fidelity. It **supersedes** the stale 50–53 numbering in `.agents/plans/50-converter-fidelity-master.md` (the 52.7 supersession action; do not cite that file's 85→99% ladder).
>
> **Provenance.** Grounded in three converging same-day audits — `docs/converter_autid_1.md` (24-agent, per-section render layer), `docs/converter_audit_2.md` (17-agent, live pipeline + passthrough control), `docs/converter_audit_3.md` (34-agent, per-stage count ladder) — **plus four current-code verification sub-agents (2026-06-02)** that **corrected** the audits in load-bearing places (§2). Every code claim is at `file:line` on branch `tech-debt/phase-52-converter-foundation`.

---

## 0. How to read this plan

The work is **not** a linear 53.1→53.7 march. It is **two fork-independent tracks + a decision gate + the chosen-fork build**, sequenced by *dependency*, not by subtask number. The spine is forced by one fact: **you cannot choose or validate the engine until the measurement is trustworthy, and today it is both circular and inverted (§2).** So measurement leads, cheap visible wins and a de-risking spike run in parallel, the fork is chosen on a real number, then the structural fix lands.

Mapping to the existing numbering (nothing orphaned): **Track A** = 52.1-finish + 52.7 + new asset work · **Track B** = old 53.6 cheap fixes, pulled early · **Track C** = old 53.2 segmentation, done spike-first · **Gate** = 53.1 · **Track D** = 53.2 (full, per chosen fork) · **Track E** = 52.5 / 53.3 / 53.4 / 53.5 / 53.7 + the deferred 52.4b per-run typography.

---

## 1. The honest definition of "for good" (read before scoping)

"For good" **cannot** mean pixel-perfect. Email is `table`/`td` + inline CSS + MSO ghost tables. Hard, fork-independent caps (all three audits agree):

| Design feature | Reproducible in email? |
|---|---|
| Stacked bands, columns (equal — or asymmetric after A8), typography, solid fills, links, CTAs | **Yes** |
| Outlook/Word rendering | **~95% floor** regardless of engine (table + VML) |
| Drop/inner shadow, blur, blend modes | No — flat fallback only |
| Gradients | Partial — `linear-gradient` + VML fallback; not all clients |
| Rotation, free 2D geometry, z-order / overlap | No — not expressible in flow layout |
| SVG / decorative vector | Rasterize or inline PNG only |
| True opacity over non-white | Dies at ingest today; approximate even if fixed |

**"For good" therefore means:** (1) **correct band grouping** on the real fixtures (the dominant defect, §2); (2) **high Gmail-class typography/spacing/color fidelity** (P52 plumbing now reaches output); (3) a **trustworthy, running metric** that can no longer self-score broken output 1.0; (4) a **documented per-client ceiling** + an explicit "cannot reproduce in email" list. **Express outcomes by defect-class closure, never a fidelity %** until the metric is wired (§Track A). Citing the historical 85→93→97→99% ladder launders a blind metric.

---

## 2. Corrected diagnosis (what the sub-agents changed vs the audits)

Two structural layers sit on top of the now-fixed P52 plumbing:

**Layer 1 — SEGMENTATION (dominant *structural* defect; 5/6 fixtures).** The converter cuts the design into the wrong number of sections. Pinned cause: the Phase-50.3 wrapper-unwrap pre-pass `_expand_container_wrappers`, gated by `_is_container_wrapper` = *(non-default fill AND ≥2 section-children)* (`app/design_sync/figma/layout_analyzer.py:579-584`). **Asymmetric**: single-child wrappers stay merged → **under-count** (Starbucks 5/9, maap 11/13, mammut 14/18); multi-child card wrappers explode each child to a top-level section → **over-count** (LEGO 17/8, slate 10/8). `component_matcher.match_all` (`component_matcher.py:96-113`) is strict 1:1, so the count is frozen upstream. Disabling the pass is **not** the fix — audit_2's `passthrough_all.py` control proves it fixes 7/8/9 exactly but regresses 5/10 (it relocates the error). The count ladder for LEGO is **8 candidates → 21 post-`analyze_layout` → 17 rendered**.

**Layer 2 — Per-section RENDER bugs (visible, individually cheap).** Mode B column collapse (orphan `<tr>` in `col_N`), Mode A slot-fill placeholder leaks + footer regex truncation, Mode E-alt Figma-layer-name in `alt`, Mode D 640px overflow, phantom `faq-accordion` slug, single-CTA collapse. All in-engine, all small (§Track B).

**Five corrections the 2026-06-02 sub-agents made to the audits — these change the plan:**

1. **The fixed-seed renderer CAN already emit a nested band-group.** The compose primitive exists and is on the live path: `render_repeating_group` (`component_renderer.py:514-528`) emits an outer colored band `<table>` wrapping N card renders; and 6 seeds carry the `_outer`→`_inner` rounded-white-card surface (`article-card.html:7-8`, mutated via `_replace_inner_bg_color`/`_replace_inner_radius` `:724-734`). **This refutes audit_2's claim** that emitting the nested group "may exceed what the seed renderer can render." ⟹ **A fork-(a) segmentation patch is real, not structurally throwaway** — the throwaway risk is purely *strategic* (fork-b would replace the pipeline). De-risks Track C.

2. **The measurement headline is a CIRCULAR gate, not just a blind pixel metric.** Per-case `manifest.yaml` `count` is pinned to the converter's **own current (broken) output**, and `test_section_count` (`test_converter_data_regression.py:222-231`) passes *because* the converter mis-segments. The design target already exists as a **separate `target_sections` field** in each manifest (5→13, 6→9, 7→8, 10→18). Re-pinning the gate to `target_sections` would correctly **fail 5/6 cases** — finally measuring the real defect.

3. **The asset partition FLIPPED.** Only **case 5 (maap)** binds today (6/6 srcs via on-disk `assets/`). Cases 6/10 *have* asset dirs but the converter emits node-ids that **don't exist on disk** (stale export, Apr 24, before current segmentation). Cases 7/8/9 (incl. flagship LEGO) have **no** assets dir. The colon→underscore normalization the audits proposed **already exists in production** (`assets.py:24-26`, `import_service.py:517`) — it was never the missing piece; the broken-image render is a converter **fallback** URL (`component_matcher.py:831-841 _resolve_image_url` returns a conn-less `/assets/{node_id}.png` "will 404 but keeps node_id for debugging"). **Reference PNGs are not committed to git at all.**

4. **"Survives any fork" is the wrong axis.** Every per-section *code* fix dies under fork-b (it replaces segmentation/matcher/seed-renderer wholesale). The honest axis is **cheap-throwaway (ship now) vs expensive-throwaway (gate on fork)**. The **only** genuinely fork-surviving fixes are **seed-asset edits** — `email-templates/components/*.html` also feed the DB component library via `file_loader.py`/`seeds.py`, a path independent of the converter.

5. **No empirical conflict (resolved).** A sub-agent reported `analyze_layout` returns 8 for LEGO, seemingly contradicting the 8→21→17 over-segmentation. It is an **exact match to the pre-unwrap `_get_section_candidates` row** (9/5/8/10/8/12 across cases 5–10) — it measured the stage *before* `_expand_container_wrappers` and mislabeled it. The over-segmentation stands (three audits + the file:line mechanism + the passthrough control). Its derived conclusion ("fork-b's value narrows") is discarded. **Mitigation: §A1 commits a reproducible ladder so this class of variance cannot recur.**

---

## 3. Audit comparison (one table)

| Dimension | audit_1 (24-agent) | audit_2 (17-agent) | audit_3 (34-agent) | Reconciled verdict |
|---|---|---|---|---|
| Headline | per-section render bugs (orig. "structure mostly OK", **self-corrected** in §4.0) | segmentation root cause pinned + passthrough control | per-stage count ladder; bidirectional | **Segmentation is the dominant structural defect; render bugs are the dominant *visible* per-section defect.** Both real. |
| Unique value-add | mode B = single-function bug (not RC-C); footer-regex truncation; alt mechanism | live passthrough control (disable → relocates error); fork-b LEGO spike → 8 bands | count ladder target→candidates→analyze→rendered; refutes the naming-convention story | Combine: §Track B (render) + §Track C (segmentation) + §A1 (ladder) |
| Fork-independence of segmentation | "requirement independent, impl not" | **NOT cleanly independent** (fork-b does it natively) | orig. "ship now", **corrected to agree with audit_2** | **Strategic, not structural** (sub-agent §2.1): the renderer *can* nest, so a fork-(a) patch is buildable — but may be throwaway if fork-b wins. Do Track C **as a spike** to inform the gate. |
| Metric | blind (5-string regex) | blind in practice (blur 1.0, unwired, asset-inverted) | blind + circular manifest | **Circular gate (§2.2) + inverted pixel metric (§2.3).** Both must be fixed before the fork gate. |
| Fork rec | (a) cheap layer + (b) leading for segmentation, NOT (c) default | (b)-with-(c)-escape-hatch long-term, but **decide only on a real number** | characterized a/b/c, **explicitly does not decide** | **Gate it (53.1) on the live metric + segmentation success criterion. Not decidable today.** |

---

## 4. The plan

### TRACK A — Make the failure measurable *(precondition; fork-independent)*

> Split into **two sub-tracks with different dependencies** (advisor): the **structural ladder** needs no assets/pixels/Figma and is **sufficient to validate Tracks B and C**; the **pixel/ΔE metric** is blocked on a Figma re-export and is needed **only** for the Track-D fork gate. Do not let "assets aren't resolved" stall B/C.

**A1 — Reproducible structural count-ladder harness `[S, ~1d]` — RUN FIRST as a go/no-go (no assets, no pixels).**
Build/commit a deterministic ladder per fixture: `target_sections → len(_get_section_candidates) → len(analyze_layout().sections) → rendered sections_count`, plus per-section element bags (t/i/b counts) and a band-grouping descriptor. Lives beside `app/design_sync/tests/regression_runner.py`. **Commit case-5 (+ ideally all 6) `structure.json`/`tokens.json` un-gitignored** so CI and every future session measure the *same* input — this is what kills the §2.5 variance class. Entry point already exists: `run_case_conversion(Path("data/debug/<N>"))`. **Why first:** this is the *first independent* confirmation of the 8→21→17 LEGO ladder that all of Track C hinges on — neither prior sub-agent cleanly reproduced it (one couldn't run the gitignored fixture, one measured the pre-unwrap *candidates* row). The arithmetic says LEGO over-segments, but **run it**; build C1 only after the ladder confirms LEGO currently renders ~17. If it surprises and LEGO already groups to ~8, Track C's premise changes.

**A2 — Un-circular the structural gate `[S, ~1d]` (52.7 core).**
Re-pin the regression gate from `manifest.count` (= converter's own output) to **`target_sections`**, expressed as a **band-structure / tolerance assertion, NOT hard `count == target`** (audit_2/3: LEGO is "17 blocks within 8 *bands*" — a flat-number gate chases the wrong target). Expect 5/6 cases to flip **red**; that is the point — the gate now measures the dominant defect. Keep the existing topology assertions (`test_no_empty_sections`, `test_no_bare_layout_divs`, placeholder-leak). File: `app/design_sync/tests/test_converter_data_regression.py` + `manifest_schema.py`.

**A3 — Case-5 pixel number, advisory `[M, ~1-2d]` (52.1-finish, scoped down).**
The metric *code* is already correct (`visual_scorer.py`: CIEDE2000 in LAB `:111-116`, MIN-agg `:212`, blur default 0.0 `:142`). The blur-1.0 path is **latent** (`fidelity_service.py:80` runs only via disabled `score_import`). Minimal wiring: (1) promote `.tmpscratch/fidelity_case_scorer.WIP.py` + its test to `app/design_sync/`; (2) commit case-5 `assets/` (6 PNGs) + reference `…/for_converter_engine/maap/visual_design.png`; (3) land the **test-harness-only src-rewrite** (`/assets/<node>.png` → `file://…/data/debug/5/assets/<node : → _>.png`) before screenshot; (4) drop the WIP test's `0.4 < full_image < 0.95` assertion (it rubber-stamps a number). **Advisory only — never a gate** until ≥2 fixtures resolve. Case 5 is an *under*-segmenter, so it yields *a* number, **not** the over-segmentation verdict.

**A4 — Node-id-keyed Figma RE-EXPORT for cases 6/7/8/9/10 `[long pole; possible USER action]`.**
This is the real blocker for a trustworthy fork decision. The converter's emitted node-ids have **no on-disk image map** for these cases. Two paths per case: (a) re-export each frame from Figma keyed by the node-ids the converter currently emits (needs the Figma file + a PAT); (b) hand-map the semantic PNGs → node-ids (LEGO ≈ 24 PNGs → 22 node-ids). **Separate structure from images** (do not conflate): LEGO's *structure* (`structure.json`) is recoverable offline by re-parsing the cached `.agents/figma-cache/node_2833_1869.json` (228 KB) via `figma_to_design_node()` — that supports §A1 — **but its image assets are NOT in the cache** (HANDOFF: the `imageRef` hash "appears nowhere else"; the on-disk `lego-insiders-halloween-assets/*.png` are semantic hand-names, not node-keyed), so LEGO *images* still need path (a) or the (b) hand-map. perf/slate need live Figma for both (per `phase-50-stranded-templates`). **Flag to the user early** — on the critical path for §53.1. **Tension to state plainly:** the fixture you most want for the fork verdict is **LEGO** (the flagship over-segmenter fork-b was spiked on) — and LEGO is exactly the case with no on-disk image assets.

---

### TRACK B — Cheap, ship-now render fixes *(validated by the A1 ladder; cheap-throwaway)*

> All but the seed edits die under fork-b — but they fix **real defects in today's shipped output** at ≤1d each, and the §A2 gate finally *sees* them. **Seed-asset edits (B1) first** — they are the only fork-surviving fixes. Every fix changes `expected.html`; each ends with **baseline regen + `snapshot_diff_audit.py` intended-vs-structural review** (never assert-unchanged; this is what caught the 52.4c double-`style=` bug).

| # | Fix | File:line (current) | Effort | Baseline blast radius |
|---|---|---|---|---|
| **B1** | **Seed-literal cleanup** (FORK-SURVIVING): blank non-slotted `Headline 1/2` (`col-icon.html:73,106`), `alt="Grid image 1/2"` (`image-grid.html:16,30`); retire dead `data-slot-alt` (`logo-header.html:8`, `article-card.html:18`, `full-width-image.html:9` — read by nothing) | seed HTML under `email-templates/components/` | S (<1d) | narrow |
| **B2** | **Inner-table column builder** (Mode B, highest visible impact): wrap img/text/CTA as rows in one inner `<table>` in `_build_column_fill_html` (+ round-robin `_build_column_fills:1461`) | `component_matcher.py:784`; rows from `_column_text_row:759` | S (≤1d) | **BROAD — shared helper** `_column_text_row` (every column baseline) |
| **B3** | **Post-fill blank pass** (Mode A1): subtract filled-slot ids from template-slot ids, blank leftover TEXT slots (keep `<td data-slot>` element — it's the builder/ESP hook); generalize the `_fills_event_card` empty-fill pattern | `component_renderer.py:551 _fill_slots`; matcher gates `:980-982`,`:1052-1054` | S (~1d) | **BROAD** — every unfilled-slot component |
| **B4** | **Footer regex fix** (Mode A2): tag-balanced match OR have `_fills_footer` emit the whole inner table — stop `.*?`+`count=1` terminating at the first nested `</td>` | `component_renderer.py:601 _fill_text_slot` | S (≤1d) | moderate (cases 5,7). **Sequence with B3** (shared `_fill_text_slot`) |
| **B5** | **Alt derivation** (Mode E-alt): the leak is the **column path** (`component_matcher.py:795 alt="{node_name}"` + round-robin `:1455`), NOT `_fill_image_slot` (which *does* apply alt `:651-656`); route real alt / `alt=""` for decorative, never the Figma layer name | `component_matcher.py:795,1455` | S | moderate (image baselines) |
| **B6** | **Width clamp** (Mode D): generalize `_update_mso_widths` to catch `max-width:640px`/`640`, not only `width="600"` | `component_renderer.py:1172,1179` | S | **BROAD** (every MSO section) |
| **B7** | **Phantom slug**: map `faq-accordion`→real `faq-item`/`faq-list` or stop emitting it (absent from `component_manifest.yaml` → falls to generic text-block) | `component_matcher.py:474` | S (<1d) | narrow |
| **B8** | **Multi-CTA**: emit all `section.buttons`, not `buttons[0]` (cta-pair seed has `primary_*`/`secondary_*` slots) | `component_matcher.py:930,1002,1062,1189,1286,1671` | S (~1d) | moderate (multi-button sections) |

**Order:** B1 → B7 → B5 → B8 (low-conflict) → then the shared-helper trio B2, then B3+B4 (sequence — both touch `_fill_text_slot`), then B6. Caution on B3: verify footer **legally-required** fields aren't blanked to empty. **Track-B total ≈ 1 week.**

---

### TRACK C — Segmentation SPIKE *(de-risks the fork decision; feeds the 53.1 gate)*

> Sub-agent §2.1 showed the renderer already nests, and named the **one riskiest unknown**: does `detect_repeating_groups` actually fire on the wrapper-*exploded*, image/text-*alternating* children? If not, leaning on downstream similarity re-detection is the wrong seam. **Resolve it as a cheap spike, validated by the A1 ladder alone — no assets needed.** The spike output is a direct input to 53.1.

**C1 — Construct the `RepeatingGroup` explicitly at explosion time `[M, ~2-3d]`.** In `_expand_container_wrappers` (`layout_analyzer.py:540-576`), when a multi-child wrapper is unwrapped, emit a **tagged band group** (the wrapper knows its children are siblings) instead of flat top-level sections — rather than re-deriving similarity later (`sibling_detector.py`, threshold 0.8, which the alternating image/text explosion likely defeats). Feed it into the already-group-aware `_match_phase`/`render_repeating_group` path (`converter_service.py:610-638`; `component_renderer.py:514-528`). **Success = LEGO 17→8 with correctly nested bands, measured on the A1 ladder.** Also steer repeated cards to an `_inner`-bearing seed (`article-card`), not `text-block` (the "flat cards" defect, a *seed-match* gap).

**C2 — Recurse single-child wrappers + absorb SPACER `[M, within C1]`.** For under-count (Starbucks/maap/mammut), recurse the single-child wrappers the `≥2` predicate leaves merged (`:584`). Absorb `SPACER` pseudo-sections into adjacent band padding (LEGO's 5 phantom sections + the `_is_section_child` leak `:587-598`). **Reuse the bounded subtree-walker** shipped for `phase-50.8-nested-physical-cards` (`physical_card_detector.find_physical_card_in_subtree`, depth≤4) rather than writing a new one.

**Spike exit criteria (feeds 53.1):** the ladder for all 6 fixtures after C1+C2; a yes/no on whether the renderer emits the nested bands cleanly; the residual cases fork-(b) would still beat (heterogeneous bands, asymmetric columns). **Do NOT full-commit Track C before the gate** unless the user elects a deliberate fork-(a) investment.

---

### GATE — 53.1 STRATEGY-FORK DECISION *(the user's call, on a real number)*

> Unblocked only when §A3 (≥1 trustworthy number) + ideally §A4 (LEGO resolves) + §Track C (spike result) are in hand. Re-run the fork-b spike on the **committed fixtures (not just LEGO)** with the live metric and **segmentation as the explicit success criterion**.

| Criterion | (a) Keep fixed-seed + Track C patch | (b) Recursive renderer | (c) Per-frame raster |
|---|---|---|---|
| Closes segmentation (5/6) | **Yes** — Track C is buildable (renderer nests, §2.1); risk = heterogeneous bands | **Yes by construction** (walks tree, skips `analyze_layout`; LEGO spike → 8 bands) | Yes (whole frame as image) |
| Closes render bugs A/B/D/E-alt | Yes (Track B) | Yes (no seed defaults) | n/a (image) |
| Asymmetric columns / proportions | Only via A8 override | **Yes** natively | Yes (pixel) |
| Effects/geometry/pixel | No (RC-C ceiling) | No (middle tier) | Yes for rastered subtree only |
| **Editability / ESP hooks** | **Preserved/improved** | Preserved if tree→table keeps `data-slot` | **Destroyed per frame** |
| Effort | Track B+C ≈ 2-3wk | **~2.5-4 eng-weeks** (tree re-plumb is the real cost) | Medium-high + infra |
| Throwaway of Track C if this wins | n/a | **Track C is subsumed** | Track C subsumed |

**Fork-(b) feasibility, corrected (sub-agent §B):** the deleted renderer (`git show d9132c7c^:app/design_sync/converter.py`, 1625 LOC) **cannot be restored verbatim** — commit `d9132c7c` Part-1 pre-extracted ~8 helpers (now live in `shared/color.py`, `sanitizers.py`, `token_transforms.py`, `protocol.py`); a verbatim restore duplicates symbols and breaks imports. **Reusable today (orphaned, lowers cost):** `render_context.py` (`RenderContext`, 160 LOC), `converter_service._collect_frames:1059`, `_build_props_map_from_nodes:1088`. **The real cost is tree-persistence:** the `DesignNode` tree is dropped at `from_legacy` (`email_design_document.py:1381`) and never reaches the snapshot (no `children`/`tree` field); `convert_document` passes `_frames=[]` (`converter_service.py:315`). **Minimal re-plumb (cleaner than a `raw_node` field):** add a `convert_from_structure(structure)` entry on `DesignConverterService` that keeps the tree, reuses the orphaned scaffolding, and bypasses `from_legacy`/`analyze_layout`. The literal "build forward on `tree_bridge.py`" is a strawman — `tree_bridge` consumes `ComponentMatch` (downstream of the bypassed stages); the real build-forward steelman is **`TreeCompiler` as emitter** (`tree_compiler.py`; `TreeSection.children` + `custom_html` exist) — but `custom_html` forfeits slot injection (dark-mode/personalization/Liquid/a11y), so the walker must emit slot-typed `TreeSection`s, shrinking the reuse win. **Riskiest unknown:** only LEGO was spiked; band-grouping fidelity of fork-b on the *under*-segmenting cases 5/6/10 is unverified — re-measure all 6 before committing the weeks.

**Output:** a 53.1 decision doc + the chosen sub-plan. **Recommended posture (the audits' consensus, for the user to ratify):** Track A+B regardless; run Track C as a spike; lean toward **(b) long-term with (c) as a per-subtree escape hatch** *only if* the metric + multi-fixture spike confirm it beats the Track-C patch by enough to justify 2.5-4 weeks. Explicitly **not (c) as the default engine** (kills editability/ESP hooks; PNGs 0.64-2.4 MB blow the file-size gate + Gmail 102 KB clip).

---

### TRACK D — Execute the chosen fork *(the structural "for good" fix)* — `[53.2]`

- **If (a):** full-commit Track C across all 6 fixtures; add the **per-column-width override** + plumb `ColumnGroup.width` to the matcher so asymmetric splits aren't forced to equal seeds (A8 — `component_renderer.py:699-781`,`:973-978`; `component_matcher.py:183-190`; `layout_analyzer.py:926-965`). Effort ~1-1.5 wk on top of B+C.
- **If (b):** land the `convert_from_structure` tree-persistence entry; rebuild the recursive renderer (NOT verbatim — re-wire to the extracted helpers); rebuild the ~4,490 LOC of tests `d9132c7c` deleted (or a slimmer fixture-driven subset); keep `data-slot` hooks so editability survives. Effort ~2.5-4 eng-weeks. Gate every step on the A1 ladder + A3 metric.
- **If (c):** wire only as a per-subtree fallback behind a reproducibility classifier (the classifier needs RC-E ingest extension — `_parse_node` reads 0 effect/gradient/vector keys today, so "deciding which subtree" is ~2-3 weeks, not days). Never the primary path.

---

### TRACK E — Ingest correctness + remaining plumbing *(fork-dependent / latent)*

- **52.5 — RC-E lossless capture `[2-3d, fork-independent]`:** composite alpha vs the **real backdrop** (not hard `#FFFFFF`, `figma/service.py:265-291`); `node_id` on `ExtractedGradient`/`DocumentGradient`; **non-button strokes** onto `DocumentSection`/`DocumentImage` (already read at `:619`, no field to hold them); AUTO/% line-height. **Latent on the frozen corpus** (the regression loads frozen `structure.json`, never runs `_parse_node`) — capturing now stops irreversible loss; render lands in 53.3. Only **non-button strokes** are exercised by the 6 fixtures.
- **RC-D′ — per-run typography `[2-3d]` (closes deferred `phase-52.4b-per-run-typography-structural`):** the *structural* sub-project, not a quick fix. Stop the `'<br><br>'.join` in `_fills_text_block` (`component_matcher.py ~954/964`); emit one `data-node-id` `<td>` per text node; add a `_text_<node_id>` override target + renderer dispatch arm (mirror `_image_<node_id>` at `component_renderer.py ~735-741`). `style_runs` is the **wrong lever** (intra-node char spans). Also fix per-side padding shorthand. **Subsumed if fork-(b) wins** (it emits per-node typography natively).
- **53.3 — Never-parsed ingest render `[fork-dependent]`:** effects/blendMode (VML/flat fallback), per-node gradient reattach (uses 52.5 `node_id`), scaleMode/imageTransform crop, rotation, z-order/overlap → `frame_export` for non-reproducible subtrees.
- **53.4 — VLM loop (RC-G): revive or honestly RETIRE.** Dead on the default path (`vlm_verify_enabled=False`; `convert_document` discards screenshots `:286`; `correction_applicator` is property-only and **cannot add/remove/reorder/merge sections** `:35-37,:158,:327`). Its internal metric returns 1.0 on empty input → false-perfect on broken renders. **Do not revive until assets resolve.** Decide explicitly; no silent "it lifts fidelity" claim.
- **53.5 — Decorative vector recovery** (rasterize vector subtrees or inline PNG).
- **53.7 — Honest-ceiling doc + numbering supersession `[1-2d]`:** the §1 per-client table as a contractual artifact; correct `docs/fidelity-gap-audit-findings.md`; banner `.agents/plans/50-converter-fidelity-master.md` 50–53 labels stale; add deferred-items entries (typography `maxItems:200` schema cap that the converter's 234-on-LEGO would fail; the asset-re-export prerequisite; the circular-gate fix).

---

## 5. Deferred items touching this plan *(mandatory cross-reference, per `.claude/rules/deferred-items.md`)*

| id | status | relevance | action |
|---|---|---|---|
| `phase-52.4b-per-run-typography-structural` | **deferred** (known-bug) | Per-run typography needs per-node `<td>` anchors | **Close in Track E (RC-D′)** — or note subsumed if fork-(b) wins |
| `phase-50.8-nested-physical-cards` | closed | Carries a Rule-9 **descendant-granularity** debt; shipped a reusable bounded subtree-walker (`find_physical_card_in_subtree`, depth≤4) | **Reuse the walker in Track C2/D**; revisit Rule-9 dark-flip granularity when segmentation changes section boundaries |
| `phase-50.7-ac-4` | closed | LEGO = `data/debug/7/`, node 2833-1869; cached raw Figma at `.agents/figma-cache/node_2833_1869.json` | **§A4 seed — STRUCTURE only**: cached JSON re-parses to `structure.json` offline; LEGO **image assets are NOT in the cache** → hand-map ~24 PNGs→22 node-ids, or live re-export |
| `phase-50-stranded-templates` | closed | LEGO/perf/slate promoted to `data/debug/7,8,9`; **perf + slate need live Figma** for §A4 | Plan the re-export access accordingly |

No deferred entry **blocks** Tracks A/B/C. The two open-relevant items are *closed by* this plan (RC-D′) or *reused by* it (subtree-walker).

---

## 6. Dependency graph (the hard chain)

```
A1 ladder [GO/NO-GO: confirm LEGO renders ~17] ──┬─► B (render fixes)      ─┐
   (no assets, run FIRST)                        └─► C (segmentation spike) ─┤
A2 un-circular gate ───────────────────────────────────────────────────────┤ ──► 53.1 FORK GATE ──► D (fork) ──► E
A4 Figma re-export ──► A3 live pixel metric ───────────────────────────────┘          ▲
   (long pole; USER)                                                                   └─ segmentation = success criterion
```

- **First, alone (go/no-go, ~1d, no assets):** A1 — independently confirm the 8→21→17 LEGO ladder *before* building Track C against it. The arithmetic settles that the prior sub-agent mismeasured, but "confident from arithmetic" ≠ "we ran it."
- **Then parallel (no assets):** A2, B1-B8, C1-C2.
- **Critical path to the gate:** A4 (Figma re-export) → A3 (live metric on ≥2 fixtures incl. an over-segmenter) → 53.1.
- **Gated on 53.1:** Track D, and the fork-sensitive parts of E (53.3 render, RC-D′ if fork-b).

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| §A2 un-circular gate turns CI red on 5/6 cases | Land as **advisory/xfail** first; it is *measuring*, not regressing — pair with a tracking note that red = the real defect surfacing |
| Track-B fixes change many baselines (B2/B3/B6 broad) | `snapshot_diff_audit.py` intended-vs-structural review **before** every regen; sequence shared-helper fixes (B3+B4) |
| Track C de-risk spike still can't make all 6 exact under fork-(a) | That *is* the 53.1 signal — the residual is the fork-(b) case; don't over-invest Track C before the gate |
| Figma re-export (A4) blocked on user/Figma access | Start it **first**; LEGO resolvable from the cached JSON without live Figma; flag perf/slate as needing access |
| Committing a green metric on blind/inverted data re-poisons trust | A3 is **advisory, case-5-only**; no gate until ≥2 fixtures (incl. an over-segmenter) resolve — HANDOFF + advisor explicit |
| fork-(b) verbatim restore breaks imports (helpers pre-extracted) | Rebuild re-wired to live helpers; `convert_from_structure` entry, not a `raw_node` field |
| Typography schema cap (`maxItems:200`, LEGO emits 234) | Note in 53.7 deferred-items; converter path doesn't call `validate()`, so no runtime break — fix before schema-validating a persisted doc |

---

## 8. Open decisions for the user (surface, do not pre-decide)

1. **Figma re-export (A4)** — the long pole. Can you provide Figma access / a fresh node-id-keyed export for cases 6/7/8/9/10? (LEGO *structure* re-parses from the cached JSON, but its **image assets** still need a live export or a ~24-PNG hand-map.) Without it the fork decision rests on case-5 (an under-segmenter) only.
2. **Track C posture** — run segmentation as a **spike-to-inform-the-gate** (recommended), or commit a deliberate fork-(a) investment now (risk: throwaway if fork-b wins)?
3. **The 53.1 fork itself** — not decidable today; ratify the sequencing (A+B now, gate on the metric). The audits lean (b)-long-term + (c)-escape-hatch; confirm you want that framing carried into the spike.
4. **Scope of the immediate next step** — this is a *plan*. Execute Track A+B now, or review/adjust the plan first?
