# Phase 53 Track F — Render fidelity: close the seed-fill defect classes

> **Source:** `docs/converter_audit_4.md` (2026-07-03; fresh conversion + Playwright render +
> CIEDE2000 scoring of all 6 fixtures + 4 file:line code traces). Segmentation is DONE
> (ladder 5-of-6 exact); this track fixes what renders *inside* the sections.
> Extends the operative plan `.agents/plans/53-converter-engine-fix.md` (Tracks A–E) under
> the ratified fork (a). Supersedes nothing; 53.3 / 53.5 plans stay valid and are sequenced
> in §4.

## 0. Ground rules (from Tracks B–E, unchanged)

- **Baselines are self-referential.** After EVERY fix: regen `data/debug/*/expected.html`
  (`python scripts/snapshot-capture.py <case> --overwrite`) only after a manual
  intended-vs-structural diff audit (Track-B playbook,
  [[reference_converter_trackb_playbook]]). Never assert-unchanged.
- **Record A3 pixel scores before/after each item** (all 6 cases locally; case 5 in CI).
  Track F's headline metric is the per-case `full_image` + `section_min` delta table, not
  test-green.
- Ladder counts must stay 13/9/8/10/8/12 on all 6 (A2 strict; mammut xfail untouched).
- Gates per fix: `make types` · design_sync + components suites · golden-conformance ·
  scoped lint. `make test` before ship. `make test` rewrites
  `app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` stamps — `git checkout --` them.
- Bridge trap (RC-A class): any new `EmailSection`/`DocumentSection` field needs all 4
  bridge sites (`email_design_document.py` to/from_json + to/from_email_section) + schema.

## 1. Fix items (ordered by pixel-impact per effort)

### F1 — Emit ALL images in a section, with their widths `[M, ~2d]` — biggest visible win
**Defect:** RC-F1. Single-image builders take `section.images[0]` and drop the rest; case 7
and case 8 heroes vanish; case 8's 64×64 icon stretches to 600px in the hero's place.
**Files:** `app/design_sync/component_matcher.py` — `_fills_full_width_image` (~:1505),
`_fills_hero` (~:984), `_fills_image_block` (~:1266), `_fills_article_card` (~:1216),
`_fills_logo_header` (~:955).
**Implementation:**
1. Shared helper `_stacked_image_rows(images)` that renders images[1:] as additional
   stacked `<tr><td><img …>` rows appended after the seed's primary image slot (one
   `full-width-image`-style row per extra image, `data-node-id` stamped, width per F3 rule,
   alt via `_derive_image_alt`). Vertically-stacked is correct per audit (tree order ==
   y order in these sections); do NOT route to `image-grid` (side-by-side).
2. Primary slot selection: pick the LARGEST image (by area) for the seed's `image_url`
   slot instead of `[0]`; remaining images render in y-order around it (before/after by
   tree position). This fixes "icon-as-hero" without a new seed.
3. Guard: skip images fully contained in an already-imaged FRAME (double-capture rule from
   53.5 §1) — reuse/extract that predicate rather than re-deriving.
**Verify:** case 7 hero node `2833:1881` and case 8 hero `2833:2264` present in output;
A3 full_image on 7/8 moves up materially; baselines 7/8 (+ any case with multi-image
sections) regen after diff audit; new unit test: 2-image section → 2 `<img>` in output.

### F2 — Insert section background when the seed has none `[S, ~0.5d]`
**Defect:** RC-F2. `_outer` bg override no-ops on bg-less seeds (image seeds) → dark bands
flip white on cases 8/9/10.
**Files:** `app/design_sync/component_renderer.py:933-944` (`_apply_token_overrides` `_outer`
fallback), `_replace_first_css_prop`.
**Implementation:** when the `_outer` `background-color` override finds neither an `_outer`
class nor an existing `background-color` declaration, **insert** the declaration into the
first `<table role="presentation">`'s style (and stamp `bgcolor` attr for Outlook parity,
mirroring `_replace_outer_bg_color`). Renderer-side only — fixes every bg-less seed at once;
do NOT hand-edit the 3 image seeds (drift risk, and custom seeds would still break).
**Verify:** case 8's `full-width-image` sections emit `#181818`; case 9 dark bands hold;
white-band count in side-by-side drops; baselines 8/9/10 regen after diff audit; unit test:
bg-less seed + `_outer` override → inserted declaration + bgcolor attr.
**Result (2026-07-04, `fix/phase-53f-f2-f8`):** `_insert_first_table_bg_color`
(`component_renderer.py`) injects `background-color` + `bgcolor` into the first *visible*
(`width="100%"`) presentation table — MSO ghost (fixed-width) skipped — gated on the existing
replace no-oping (`replaced == result`) so it only fires on genuinely bg-less seeds. Fires on
all 6 (plan's "every bg-less seed"); dark wins **c8 0.702→0.793, c9 0.640→0.732** (section_min
c8 0.30→0.67, c9 0.36→0.53), 5/6/10 neutral (explicit==implicit white), c7 −0.001 (noise;
its residual is F1/F4 broken images). 3 unit tests: real full-width-image (styled table) +
image-block (no style attr) seeds + replace-not-insert gate. Limitation: the `width="100%"`
discriminator no-ops on a bg-less seed whose outer table isn't `width="100%"` (no regression;
all 3 current image seeds qualify).

### F3 — Thread design width through every image emission `[S-M, ~1d]`
**Defect:** RC-F3. Column images hardcode `width:100%`; most single-image builders drop
`img.width` → giant pixelated icons/arrows/logos (cases 8/9/10, LEGO decorations).
**Files:** `component_matcher.py` `_column_image_row` (:826-840), `_fills_image_block`,
`_fills_hero`, `_fills_image_grid`, `_fills_product_grid` (mirror `_fills_logo_header`
:966-969); `component_renderer.py` `_fill_image_slot` (:857-879).
**Implementation:**
1. Column path: emit `width="{int(img.width)}"` + `style="…max-width:{w}px…"` and drop the
   unconditional `width:100%` when `img.width` < ~0.9× the column's px width; keep `100%`
   for genuinely column-filling images (the responsive `bannerimg` behaviour).
2. Single-image builders: add the `overrides["width"]` line everywhere it's missing.
3. `_fill_image_slot`: when a width override is present, also clamp the inline
   `width:`/`max-width:` style values (attr alone loses to the seed's `width:100%`).
4. Icon guard: `img.width <= 64` never stretches (aligns with the button-icon precedent).
**Verify:** slate pin/thermometer + mammut arrows render at design size; no regression on
true full-bleed images (case 7 banner strip stays 600); baselines regen after diff audit;
unit tests for both paths (small icon in column; small image in image-block seed).

### F4 — Stop seed-default leakage `[M, ~2d]`
**Defect:** RC-F4. Unfilled `<span>`/`<a>`/`<img>` slots keep seed literals; slot-id
mismatches guarantee 0-fill; 5 slugs have no builder at all.
**Files:** `component_renderer.py` `_blank_unfilled_text_slots` (:784-820, `_TEXT_SLOT_OPEN_RE`
:28), `_strip_placeholder_urls` (:1507-1513); `component_matcher.py` `_fills_cta` (:1364-1404),
`_fills_text_block` dispatch (:569), builders dict (:506-578), `_build_token_overrides`
(:1948-1962); seeds `email-templates/components/{cta-button,event-card,col-icon}.html`.
**Implementation (sub-items, each independently shippable):**
1. **F4a** — `_fills_cta`/`_fills_hero` emit explicit EMPTY `cta_text`/`cta_url` fills when
   `section.buttons` is empty (the B8 cta-pair empty-fill discipline), and the blank pass
   gains a span/anchor arm: an unfilled `<a>…<span data-slot>…</span>…</a>` block is pruned
   whole (no empty clickable anchors — B3's advisor rule). Kills "Shop Now"/"Learn More"/
   "Read More" leaks AND the seed-blue buttons (nothing left to style).
2. **F4b** — `col-icon` gets a real builder emitting the seed's actual slot ids
   (`heading_N`, `icon_N_url` from `section.images`/`texts`), or —if the corpus can't fill
   icons— unfilled `icon_N_url` imgs are BLANKED (remove the `<img>` row). Extend
   `_strip_placeholder_urls` to strip any `data-slot` img whose src host isn't the API
   (generalizes past the 3-host list; `fakeimg.pl` dies as a side effect).
3. **F4c** — `event-card.html`: move 📅/📌 inside the `date`/`location` slot spans so the
   existing empty-fill blanking removes them.
4. **F4d** — the 5 orphan slugs (`countdown-timer`, `testimonial`, `pricing-table`,
   `video-placeholder`, `zigzag-alternating`): either wire minimal builders or remove them
   from `_score_extended_candidates` (:389) so they can't be matched into placeholder
   output. Removing is the Simplicity-First default unless a fixture exercises them.
**Verify:** grep output corpus for `Shop Now|Learn More|Read More|fakeimg|Feature icon|
&#128197;` → zero on all 6 cases (except genuine design copy); `low_slot_fill_rate`
warnings drop; unit guards per sub-item (RED pre-fix); baselines regen after diff audit.

### F5 — Compliant footer fill `[M, ~1.5d]`
**Defect:** RC-F5. `_fills_footer` wipes legal/unsub rows; empty branch leaks raw
`{{unsubscribeUrl}}`; BrandRepair never runs in design-sync and wouldn't fix it.
**Files:** `component_matcher.py` `_fills_footer` (:1407-1425); `component_renderer.py`
`_PRESERVE_UNFILLED_SLOTS` (:36-44) + the false comment (:30-35);
`email-templates/components/email-footer.html`.
**Implementation:**
1. Split the seed's `footer_content` cell into two slots: `footer_editorial` (Figma text
   lands here) and `footer_legal` (unsub/preferences/address rows — NEVER overwritten;
   stays in `_PRESERVE_UNFILLED_SLOTS`).
2. `_fills_footer` fills only `footer_editorial`; drop the false BrandRepair comment.
3. Merge tags: leave `{{unsubscribeUrl}}`/`{{preferencesUrl}}` as literals in the HTML —
   they are ESP merge tags by design (ast-mapper preserves them; ESPs resolve them) — but
   ONLY inside `footer_legal`, and confirm the QA `personalisation_syntax` check accepts
   them. If a case's design carries its own unsub text, editorial wins and legal row stays
   (dedupe is a non-goal for v1; note in ceiling doc).
4. Decision recorded here: the converter stays self-sufficient — do NOT wire RepairPipeline
   into `convert_document` (Simplicity First; BrandRepair's own gaps are a separate
   qa_engine concern; add a deferred entry instead — §5).
**Verify:** all 6 outputs contain an unsubscribe link row; no raw-merge-tag leak OUTSIDE
footer_legal; footer editorial text from the design still lands; golden-conformance +
seed-slot manifest (`component_manifest.yaml`) updated; baselines regen after diff audit.

### F6 — Eyebrow/kicker order `[S-M, ~1d]`
**Defect:** RC-F6. Small-text-above-heading renders below the heading (maap, Ferrari) —
builders bucket by `is_heading` and seeds hardcode heading-row-first.
**Files:** `component_matcher.py` `_fills_text_block` (:1126-1204) + `_fills_hero`
(:1007-1010); `layout_analyzer.py` `_detect_content_hierarchy` (:1580).
**Implementation:** texts already arrive in tree/y order. In `_fills_text_block`, when
body-classed texts PRECEDE the first heading in source order, emit them into a `kicker`
position: reuse the RC-D-prime per-node `<td data-node-id>` anchor pattern to inject the
pre-heading texts as rows ABOVE the heading row (upsert arm in the renderer mirrors
`_text_<node_id>`). No new seed slot needed; no reordering of the heading/body slots
themselves. Same treatment in `_fills_hero` for `subtext`-before-`headline`.
**Verify:** case 8 eyebrows render above headings (`data/debug/8/actual.html` order flips);
case 5 intro order matches design; per-node typography preserved; baselines 5/8 regen after
diff audit; unit test with an eyebrow-above-heading synthetic section (RED pre-fix).

### F7 — Card + pill fidelity (fixable half of the structural ceiling) `[M-L, ~2-3d]`
**Defect:** RC-F7 fixable subset. Child-frame cards invisible (LEGO); pill radius ignored.
**Files:** `layout_analyzer.py` `_detect_inner_bg` (:1665-1703); `component_matcher.py`
`_column_cta_row` (:843-856), `_build_token_overrides` (:1844-1856).
**Implementation:**
1. `_detect_inner_bg`: walk one level of child frames — a child FRAME covering ≥60% of the
   section area with a solid fill distinct from the section bg becomes `inner_bg` (+
   `inner_radius` from its cornerRadius). Drop the `container_bg` precondition (:1694) —
   audit shows real cards exist without it. Feeds the existing `_inner` override path.
2. Pill radius: capture scalar `border_radius` for ButtonElements from cornerRadius when
   `corner_radius_spec` is uniform; `_column_cta_row` uses it (fallback stays `"4"`). Full
   per-corner tag/pill slot stays with the 51.x composite chain (§4) — do not build it here.
**Verify:** LEGO white cards reappear behind card content (A3 case 7 section scores);
maap pills round; no dark-mode regression (`bgcolor-*` class contract, 41.3); baselines
regen after diff audit.

### F8 — Latent imageRef capture `[S, ~0.5h]` — hygiene
`figma/service.py:607-612`: capture `imageRef` in the RECTANGLE→IMAGE reclassification
branch (mirror the FRAME branch :614-618). No visible output change expected (assets
resolve by node-id) — corpus byte-diff must be empty; unit test on a synthetic RECTANGLE
node. Closes the trap under the FRAME-bg gate (`layout_analyzer.py:1287`) before 53.3
builds on it.
**Result (2026-07-04):** `imageRef` captured in the reclassify branch (`figma/service.py`,
mirrors the FRAME branch). Corpus regen byte-identical — the only diff on any case is the
pre-existing c8 heading trailing-whitespace drift (converter text-join, unrelated to F8).
The existing `test_parse_props.py` reclassify test was asserting the dropped-ref bug (comment
"reclassifies, not extracts"); updated to expect the ref + added a no-`imageRef` case.

## 2. Sequencing & batching

```
F2 (0.5d) → F3 (1d) → F1 (2d)     # pixel-dominant trio; each independently shippable
→ F4a-d (2d) → F5 (1.5d)          # leak + compliance batch
→ F6 (1d) → F7 (2-3d) → F8 (0.5h) # order, cards, hygiene
```
~10 working days total. F2/F3/F8 are near-risk-free; F1/F4/F5 change baselines materially
(budget diff-audit time); F7 carries the most regression surface (dark-mode + column paths)
— give it its own context window (Track-B rule for broad fixes).

### Parallel option (two lanes, ~6d wall clock)

```
Lane A (pixel):    F2+F8 → F3 → F1 → F7      # F3→F1 hard dep (width rule + same builders);
Lane B (content):  F4a-d → F5 → F6           # F4b reroutes col-icon out of _fills_text_block
                                             # before F6 rewrites it — keep B ordered.
Close-out only after BOTH lanes merged.
```
Hard rules for parallel execution:
- **Never parallelize within a lane.** Cross-lane code barely collides (distinct functions);
  the contention is `data/debug/*/expected.html` — whole-file regens.
- **Merge-second protocol:** the later-merging branch must rebase onto main, re-run its unit
  tests, RE-REGEN its touched baselines, re-diff-audit, re-run the scorer, and fix its §6
  row before merging. Never resolve an `expected.html` conflict by hand-merging hunks —
  always regen from the rebased converter.
- **Worktree setup:** lane B runs in `git worktree add ../merkle-email-hub-laneB <branch>`.
  The gitignored `data/debug/*/assets/` do NOT follow the worktree — copy them in
  (`for c in 5 6 7 8 9 10; do cp -R data/debug/$c/assets ../merkle-email-hub-laneB/data/debug/$c/; done`)
  or the render/scorer breaks (`phase-53.7-asset-reexport-prerequisite` class).
- §6 log rows gain a lane marker (A/B) while lanes are in flight; the close-out session
  reconciles the table sequentially by merge date.

## 3. Measurement contract (per item, no exceptions)

1. Before/after A3 table (all 6 cases, `full_image`/`section_min`/`section_median`) appended
   to this file's §6 log. Expected end-state: cases 7/8/9 full_image from 0.62–0.70 into
   the ≥0.80 band (maap/starbucks level); no case regresses.
2. Ladder unchanged (12 stays mammut's number — count work is OUT of scope here).
3. Visual spot-check of the regenerated side-by-sides for the cases each item touches —
   the pixel metric is advisory; eyes are the gate. Harness:
   `uv run python scripts/score-fidelity-cases.py` (renders, scores, writes side-by-side
   composites to `.tmpscratch/fidelity/`; Read the composite images for the touched cases).

## 4. Structural follow-on (after Track F, separate efforts)

| Order | Work | Plan | Note |
|---|---|---|---|
| 1 | Ratify stub triage → promote **51.1 composite-slot infrastructure**, then 51.2/51.3 | `deferred/TRIAGE-2026-06-12.md` | The real lifter for RC-F7's structural half (card-with-N-children, tag/pill slot, vertical nav). USER RATIFICATION still pending since 2026-06-12. |
| 2 | 53.3 ingest render (gradient reattach → crop → rotation/z-order frame_export → effects warnings) | `53-3-ingest-render.md` | Unchanged, still valid. F8 lands first (imageRef trap). |
| 3 | 53.5 vector recovery (divider stroke fidelity + icon rasterize path) | `53-5-vector-recovery.md` | Unchanged. Note: audit-4's "giant icons" were NOT this class (they render, wrongly sized → F3). |
| 4 | Column detection widening (bare IMAGE+TEXT columns; peel beyond `mj-wrapper` naming) | ⏳ new plan | Only if post-F corpus still shows stacked 2-cols; needs non-MJML fixtures first (53.6 stub). |

## 5. Deferred-items to add at ship time

- `phase-53f-brandrepair-footer-gaps` (speculative): `BrandRepair._repair_footer` early-returns
  on any `footer` class and never injects unsub links — dead as a compliance backstop
  (`qa_engine/repair/brand.py:141-172`). Surfaced by audit-4; F5 makes the converter
  self-sufficient instead. Symptom-if-broken: scaffolder-pipeline emails missing unsub when
  the template carries a decorative footer class.
- `phase-53f-decorative-image-flag` (soft): plain IMAGE decorations are indistinguishable
  from content photos at extraction (`is_background` only for frame fills). F3's size
  heuristic is a stopgap; real fix is z-order/role capture (53.3d territory).
- Close-check at F4d: if orphan slugs are deleted, close by inspection; if wired, each needs
  a fixture or a synthetic test.

## 6. A3 score log (append per landed item)

| Date | Item | c5 | c6 | c7 | c8 | c9 | c10 | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-07-03 | baseline (audit-4) | 0.879 | 0.801 | 0.624 | 0.702 | 0.640 | 0.679 | full_image; section_min 0.63/0.48/0.30/0.30/0.36/0.09 |
| 2026-07-04 | F2+F8 | 0.879 | 0.801 | 0.623 | 0.793 | 0.732 | 0.679 | F2 dark bands hold: **c8 +0.091, c9 +0.092** (section_min c8 0.30→0.67, c9 0.36→0.53); 5/6/10 neutral (explicit==implicit white, byte-changed/score-flat); c7 −0.001 noise (residual is F1/F4). F8 corpus byte-identical. BEFORE row reproduced audit-4 exactly. |
