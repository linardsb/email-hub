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
**Result (2026-07-04, `fix/phase-53f-f1-multi-image`):** `_select_primary_image` (largest by
area, ties→earliest) + `_stacked_image_rows`/`_stacked_image_row` (`component_matcher.py`) fill
the seed's image slot with the largest image and stack the rest as `<tr><td><img>` rows in tree
order — those preceding the primary above it, those after below — sized by the inline F3 width
rule (`<540px` → natural width, else `width:100%`). `SlotFill` gains `stacked_before`/
`stacked_after` (render-time only, no bridge sites); `_splice_stacked_rows`
(`component_renderer.py`) injects them around the primary img's `<tr>` from `_fill_image_slot`.
Splice is **verified only for full-width-image** (tested + both corpus cases); article-card and
logo-header are wired but reached by no fixture — logo-header's `<img>` is a standalone top-level
`<tr>` (splice structurally correct), but article-card's sits in a 280px column cell so stacked
rows there would be column-constrained, not full-width — unvalidated. image-block (renderer
special-case) + hero-block (CSS/VML background, no `<img>` anchor) get largest-primary selection
only; no corpus fixture routes a multi-image section to either → stacked rows deferred.
**Step 3 (skip images inside an already-imaged FRAME) intentionally not implemented:**
`ImagePlaceholder` carries no geometry at the builder layer so containment is uncomputable there,
the 53.5 §1 predicate the plan says to reuse does not exist yet, and the corpus has no
frame-child duplication — the guard belongs in extraction, not the fill builders. Corpus: exactly **2**
qualifying sections, both `full-width-image` (c7 §1, c8 §0), both `[strip, hero]` with the hero
last → **hero promoted to primary, strip stacked above; c7 `2833:1881` + c8 `2833:2264` now
emitted as `<img>` (absent before, incl. from the old baselines) — HTML-verified.** Baselines
7/8 regenerated (18-line intended diff, audited line-by-line); ladder **13/9/8/10/8/12 held**;
c5/6/9/10 byte-identical (no F1-builder multi-image sections). 5 unit tests RED→GREEN (2-img
emission, largest-primary, before/after ordering, ≤540 width rule). **Limitation (asset gap):**
the hero PNGs (`2833:1881`, `2833:2264`) were never exported — the pre-F1 converter referenced
only `images[0]` (the strips) — and are unrecoverable this session (c7 cached S3 URL 403, c8
uncached, no `FIGMA_TOKEN`), so the fidelity scorer renders them **blank**. Pixel deltas are
therefore asset-artifacts, **not** F1's win: **c7 0.623→0.612** (broken-image gap replaces the
stretched strip), **c8 0.793→0.802** (section_min 0.668→0.688). Real win pending hero re-export
(`phase-53.7-asset-reexport-prerequisite`). The inline width rule is synthetic-test-only (both
corpus extras are 600px → full-width); the audit's "64×64 icon stretched to 600px" is ingest-side
(`layout_analyzer` reports `2833:2262` as 600×68), unfixed by F1.

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
**Result (2026-07-05, `fix/phase-53f-f3-image-widths`, off post-F6 main 3a626dcd — F6 merged
mid-lane so F3 sits sequentially on top, not parallel):** Design width threaded through every
image emission, scoped to the plan's 2 files. `_image_fills_column` (new predicate) +
`_column_image_row` (now takes `column_width=group.width` from `_build_column_fill_html`): a
column image ≤64px OR narrower than 0.9× its column drops `width:100%` and emits `width="{w}"` +
`width:{w}px;max-width:{w}px`; column-filling images keep `width:100%` (responsive `bannerimg`);
unknown width degrades to the pre-F3 default. `overrides["width"]`/`["height"]` added to
`_fills_image_block`/`_fills_hero`/`_fills_image_grid`/`_fills_product_grid` (mirrors
`_fills_logo_header`; `_fills_hero` is **inert** — hero-block is a CSS/VML bg, no `<img>` anchor,
documented like F1). `_fill_image_slot` clamps inline `max-width` to the design width via
`_clamp_img_max_width` (keeps `width:100%`, so a full-bleed 600px image stays **byte-identical**
via value-equality no-op while a small icon renders at natural size); the image-block `image_url`
branch now **delegates to `_fill_image_slot`** (was direct-src, could not size). 17 unit tests
(`test_image_width_fidelity.py`) cover both directions; 2 proven RED pre-fix (34px column icon →
`width:100%` giant; 40px image-block → `max-width:600`). **c9 wins (HTML + composite verified):
pins/thermometer `2833:2094/2103` 270px→34px, grid arrow `2833:2143` 292px→48px; c7 LEGO
decorations — 26 imgs `width:100%`→26/30px.** Ladder **13/9/8/10/8/12 held**; design_sync+components
**3026 passed**; golden-conformance 26 passed; mypy+pyright 0 errors; scoped security lint clean.
Baselines 5/6/7/8/9 regen (diff-audited: only max-width/width value changes, no structural drift);
**c10 byte-identical**. **Correctness win, not pixels (§6):** the height-sensitive band scorer
*penalises* the now-shorter renders — collapsing the oversized icons removes spurious height that
was masking the still-missing RC-F7 card structure (c9 render aspect **3.31→2.63** vs reference →
resize distortion; per-section confirms the drop is the height-shifted bands, not a render defect).
**c10 nav arrows deferred (user-ratified scope):** their width is inflated 28px→268px at ingest
(`layout_analyzer.py:1318`, frame-wrap branch uses the frame width), outside F3's matcher/renderer
scope → carried forward under `phase-53f-decorative-image-flag` (53.3d). **Known latent (Outlook,
not fidelity-scored):** a shrunk grid image keeps the seed cell's `width="292"` attr while the
inline `max-width` drops to the design width — Chromium honours the CSS cap so the render is
correct, but Outlook obeys the HTML attr and would show it at the 292px cell width. Out of the
Chromium-scored path, so it neither blocks nor regresses the ladder; flagged for a later
attr/style reconciliation. **Merge note:** F3 is now
the last Track-F pixel item on main; F7 remains.

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
**Result (2026-07-04, `fix/phase-53f-f4-seed-leaks`):** All 4 sub-items landed and committed one-at-a-time with green gates between each. Full corpus **leak-free** — `Shop Now|Learn More|Read More|fakeimg|Feature icon|📅|📍` zero on cases 5-10 (both numeric-entity `&#128197;`/`&#128205;` and literal-UTF-8 forms). Ladder **13/9/8/10/8/12 held**; scores are a correctness win, not pixels (see §6).
- **F4a** (`36b5eba3`): `_fills_cta` emits explicit empty `cta_text`/`cta_url` when `section.buttons` is empty (text-link keeps its single slot); `_fills_hero` always emits the CTA block (empty when no buttons). `_prune_unfilled_ctas` (in `_fill_slots`, after the blank pass) prunes any `<a>…<span data-slot=X>…</span>…</a>` whose X has no non-empty fill, and strips the empty cta-btn/ghost/primary/secondary table + its MSO `<v:roundrect>` twin (B3 no-empty-anchor). Baselines 5/6/10 regen (diff-audited); 4 guards RED→GREEN; 5 partial-fill tests gained realistic `cta_text`.
- **F4b** (`7bc7a057`): new `_fills_col_icon` builder (was mis-routed to `_fills_text_block` → 0/4 slot-id fill) emits `icon_N_url` (real `/api` src + derived alt) + `heading_N` per column; `_strip_placeholder_urls` rewritten to drop the whole `<img>` (+ sole-child wrapping `<a>`) for any absolute-http src (real converter assets are always relative `/api/v1/design-sync/assets/…`). Case 9: fakeimg 8→0, "Feature icon" 8→0, 2 headings recovered. Baseline 9 regen; 3 guards RED→GREEN.
- **F4c** (`f3374ae5`): moved 📅/📍 inside the `date`/`location` spans in `event-card.html` so a real fill replaces the emoji and an empty fill blanks it. Case 6: 📅 1→0, orphaned 📍 gone. Baseline 6 regen (emoji-only diff); 2 guards RED→GREEN.
- **F4d** (`617326d3`): removed the 5 builder-less slugs (`countdown-timer`/`testimonial`/`pricing-table`/`video-placeholder`/`zigzag-alternating`) from `_score_extended_candidates` plus their now-dead patterns/params. **Converter scorer only** — the 5 stay valid component-library components (`component_manifest.yaml` + seeds + `test_new_components.py` untouched, 696 pass). No corpus fixture matched any (0 baseline change); 6 guards RED→GREEN; deferred-items `phase-53-f4d-extended-candidate-orphans` closed by inspection. Adjacent open item `phase-53-b8-text-block-solid-cta-text-color` surfaced, left orthogonal.

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
**Result (2026-07-04, `fix/phase-53f-f5-footer`):** email-footer seed's `footer_content`
cell split into `footer_editorial` (Figma text via `_fills_footer`) + `footer_legal`
(unsub/preferences/address rows, in `_PRESERVE_UNFILLED_SLOTS`, never filled). Renderer's
false BrandRepair comment deleted; `_PRESERVE_UNFILLED_SLOTS` swaps `footer_content`→
`footer_legal` (keeps `copyright`/`company_name`/`company_address`/`unsub_text` for the other
footer seeds). Manifest `email-footer` slot_definitions → the two new slots (+selectors).
`{{unsubscribeUrl}}`/`{{preferencesUrl}}` stay as literal ESP merge tags ONLY inside
footer_legal (**QA confirm, empirical:** `liquid_syntax` passes clean; `personalisation_syntax`
returns 0.9 "platform unknown" — a **library-wide** soft signal the raw seed + every `{{ }}`
template scores identically, so it's seed-faithful not an F5 regression; **2 per case, zero
leak outside** on c5/c7). Depth-balanced `_find_matching_close` untouched — editorial is
simple text, legal is never filled → **truncation risk eliminated, not reintroduced**
(`TestFooterContentNoTruncation` rewritten: editorial-fills / legal-survives / tags-balanced,
+ unfilled-keeps-legal). RepairPipeline deliberately NOT wired (decision 4). **Reality: only
c5/c7 carry a footer section** — 6/8/9/10 end in `social-icons` (no footer → outside F5's
reach; verified **byte-identical**). Both now emit the unsub link row (previously **wiped** by
the whole-cell fill). **Compliance win, not pixels:** **c5 0.877→0.844** (−0.033; off-design
legal boilerplate "© Company Name"/"123 Business Street" + links now render on maap's dark
footer — the accepted compliance/fidelity trade, cf. F4), **c7 0.612→0.615** (+0.003, editorial
now in a styled `footer-text` cell); c6/8/9/10 unchanged. Ladder **13/9/8/10/8/12 held**;
design_sync+components **2777 passed**. Ceiling note: v1 does NOT dedupe a design's own unsub
text against the legal row (c5/c7 render both); footer_legal keeps the seed's hardcoded
"© Company Name"/"123 Business Street" **literals** — no per-brand substitution (RepairPipeline
unwired) → deferred `phase-53f-brandrepair-footer-gaps` + `phase-53f-decorative-image-flag`.

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
**Result (2026-07-04, `fix/phase-53f-f6-eyebrow-order`):** `_pre_heading_body_texts`
(flat/single-col: body nodes before the first `is_heading` in source order) +
`_pre_heading_rows_html` (bare `<tr><td data-node-id>` rows using the `padding-bottom`
LONGHAND — never the `padding:` shorthand — so the section's `_cell` shorthand override still
lands on the heading `<td>`, not the spliced eyebrow) in `component_matcher.py`.
`_fills_text_block`/`_fills_hero` split pre/post-heading: pre-heading eyebrows ride the
heading/headline `SlotFill.stacked_before` (reusing F1's render-time field, docstring
generalized); the body/subtext slot keeps only post-heading texts. `_per_node_body_texts`
forces per-node anchoring whenever an eyebrow is lifted (else a lone post-heading paragraph
would inherit the shared `_body` target = the *eyebrow's* typography and mis-render). Renderer
`_fill_text_slot` consumes `stacked_before` via `_splice_rows_before_slot` (mirrors F1's
`_splice_stacked_rows`, anchored on `<td data-slot>`); the existing `_text_<node_id>` upsert arm
styles the spliced anchors → **per-node typography preserved**. `_detect_content_hierarchy`
untouched (no corpus-wide reclassification). **Acceptance met (HTML + side-by-side composite vs
reference):** c8 both `FERRARI 849 TESTAROSSA` / `…SPIDER` eyebrows above their headings, c5
`New Season Collaboration` above `MAAP x KASK`; 12px `#DA291C` centered / Courier-New 12px
typography intact; heading `_cell` padding intact (longhand dodge, disk-verified). **Only c5/c8
carry pre-heading eyebrows — 6/7/9/10 byte-identical.** 7 guards (`test_eyebrow_order.py`)
RED→GREEN (4 order/stacked_before RED pre-fix) + 3 preserved (typography, heading-padding-
survives-splice, heading-first-unchanged). **Correctness win, not pixels** (§6): full_image flat
on all 6, **c8 section_median 0.859→0.868** (+0.009); c5 flat (a ~12px eyebrow reposition is
sub-rounding on the 5036px composite). Ladder **13/9/8/10/8/12 held**; design_sync **1977 passed**
/ components **807 passed** / golden-conformance / mypy+pyright 0 errors. **Scope:** flat
single-column path only (no corpus fixture carries a grouped/multi-column eyebrow); hero path
wired + unit-tested (no corpus hero eyebrow). **Limitation:** the longhand dodge protects the
`_cell` *shorthand* path (both acceptance cases are 4-side padding); a *partial*-padding section
would route `_cell` per-side longhands to the eyebrow row via `_upsert_first_td_css_prop` — not
exercised by corpus. The pre-existing F8-noted heading trailing-whitespace (stash-proven
pre-existing, not F6) is stripped by the pre-commit hook and normalized by the snapshot
comparison, so the committed c8 baseline changes are eyebrow-rows-only; it moves again when
F3 (Lane A, still unshipped — no Result/§6 row) lands (merge-second protocol).

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
**Investigation (2026-07-05, `fix/phase-53f-f7-cards-pills`) — HALTED, premise misaligned; NO code landed:**
Pre-implementation fixture audit (BEFORE scores c5 0.844 / c6 0.802 / c7 0.636 / c8 0.802 / c9 0.679 /
c10 0.678; per-section diag via `from_legacy`→`analyze_layout`→`match_section`) shows **both halves' stated
mechanisms don't reach the corpus**:
- **Half-1 inert (LEGO cards).** c7 card sections [5,7,9,11,13,15] ALREADY carry `inner_bg=#FFFFFF` (existing
  direct path, `node.fill_color`≠`container_bg`) yet render on bare lime. They match `column-layout-2`; the
  membership card [19] matches `image-gallery` — **neither seed has `class="_inner"`** (only 6/151 seeds do:
  article-card, editorial-2, event-card, pricing-table, zigzag-image-{left,right}), so the `_inner` override
  no-ops (0 `_inner` in `data/debug/7/expected.html`). And because `inner_bg` is truthy the `elif
  section.bg_color`→`_outer` fallback (`component_matcher.py:2056`) is skipped → white surface dropped
  entirely. Child-frame promotion would set *more* `inner_bg` but paint nothing; the white card is
  STRUCTURAL (column seed needs a card wrapper) = 51.1 composite-slot work (§4), not F7. Dropping the
  `container_bg` precondition also WIDENS physical-card detection (`layout_analyzer.py:433` `if inner_bg is
  not None`) → dark-mode regression surface for zero render gain.
- **Half-2 misdiagnosed (maap pills).** All 8 maap `mj-button`s carry a clean SCALAR `cornerRadius:25.0` in
  `data/debug/5/raw_figma.json` that the EXISTING `border_radius=node.corner_radius`
  (`layout_analyzer.py:1438`) already renders (proven by c6/c7 buttons `br=25.0`). But
  `data/debug/5/structure.json` (6 Jun, old adapter) is STALE and dropped ALL radius (0 occurrences); **no
  corpus button carries the per-corner `corner_radius_spec` the plan's "uniform→scalar" mechanism targets.**
  Root cause is fixture staleness, not extraction — implementing the plan's mechanism would fix nothing and
  claim a win for the wrong fix.
- **Real fixes (both outside F7's `layout_analyzer`/`component_matcher` file scope):** (a) re-ingest
  `data/debug/5/structure.json` from raw_figma → existing code rounds the pills (bigger scope; case-5
  ladder/segmentation diff-audit risk); (b) 51.x composite-slot chain gives column seeds an `_inner`/card
  wrapper → LEGO cards render. F7's two acceptance criteria are **unmeetable** via the plan's stated code
  changes. User decision (2026-07-05): HALT & report; branch left clean (no source, no baseline, no Result).
  Re-scope pending; new blockers logged in §5.
**Result (2026-07-05, `fix/phase-53f-f7-pills-radius`) — pill radius RECOVERED (fixture, no code):**
Re-scoped from the halt: half-2 is a stale-fixture recovery, not the plan's per-corner mechanism. A surgical
text-insertion patched the scalar `"corner_radius": 25.0` into exactly the 8 maap `mj-button` nodes in
`data/debug/5/structure.json` (`git diff --numstat` = **`8  0`**; **no `json.dumps` round-trip** — c5 is
old-schema, 26 keys/node, so a re-serialize would have rewritten all 123 nodes with ~10 defaulted keys).
`snapshot-capture 5 --overwrite`: the **7 city pills (Melbourne/Amsterdam/Seoul/Singapore/Hong Kong/Berlin/
Taipei) flip `border-radius:4px`→`25px`** via the existing `_column_cta_row` (`component_matcher.py:843`) —
expected.html diff is **7 border-radius values, nothing else**; ladder **13** held; **c6–c10 byte-identical**.
**c5 0.844→0.845** (section_median 0.806→**0.821**; section_min 0.492 flat — a 152px pill rounding is
sub-rounding on the 5036px composite). The 8th button — section [1] **'Discover →' stays 4px**: its
`border_radius=25.0` reaches the document model (verified via `from_legacy`) but it renders through
`_fills_text_block`'s CTA-append, which **hardcodes `border-radius:4px`** (`component_matcher.py:1345`),
discarding it — a **pre-existing corpus-wide bug** (also c6 'Order your fall favorite', c7 'Explore now').
**User-ratified (2026-07-05):** recover the 7 column pills here; defer the shared render-path fix
(`phase-53f-f7-text-block-cta-hardcoded-radius`, §5) so c6/c7 baselines don't move. **No regression test** —
`test_cta_fidelity.py::test_column_fill_uses_button_radius` already covers
`ButtonElement.border_radius`→`_column_cta_row`→`border-radius:{r}px` end-to-end. `rendered_w600.png` left
frozen (advisory-only, already stale since F5/F6 — regenerating would fold their visual drift into this commit).
Closes `phase-53f-f7-stale-case5-fixture-drops-pill-radius` (§5); the LEGO-card half-1 remains open
(`phase-53f-f7-column-seed-no-inner`).

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
- `phase-53f-f7-stale-case5-fixture-drops-pill-radius` (known-bug, from F7 halt 2026-07-05) — **CLOSED 2026-07-05 (`fix/phase-53f-f7-pills-radius`)**:
  `data/debug/5/structure.json` (6 Jun, old adapter) dropped the scalar `cornerRadius:25.0` present on all 8
  maap `mj-button`s in `raw_figma.json`. The existing `border_radius=node.corner_radius`
  (`layout_analyzer.py:1438`) + `_column_cta_row` (`component_matcher.py:843`) render 25px pills once the
  fixture carries the data (proven by c6/c7). **Closure:** a surgical `+8  0` patch inserted the scalar into
  the 8 nodes → the 7 column pills render 25px (ladder 13 held, c6–c10 byte-identical, c5 0.844→0.845). The
  section-[1] 'Discover →' residual is a separate render-path bug, not fixture staleness →
  `phase-53f-f7-text-block-cta-hardcoded-radius`.
- `phase-53f-f7-text-block-cta-hardcoded-radius` (known-bug, from F7 recovery 2026-07-05; also in
  `.agents/deferred-items.json`): `_fills_text_block`'s CTA-append (`component_matcher.py:1345`) emits a
  **hardcoded `border-radius:4px`**, discarding `btn.border_radius` (which the model carries). The sibling
  `_column_cta_row` (`:843`) honors it. Corpus-wide: c5 'Discover →', c6 'Order your fall favorite', c7
  'Explore now' render 4px despite a 25.0 design radius. Fix = thread `btn.border_radius` (fallback '4') like
  `_column_cta_row`, then regen c5/c6/c7 baselines + diff-audit. Deferred (user-ratified 2026-07-05) to keep
  the pill recovery surgical (c6–c10 byte-identical).
- `phase-53f-f7-column-seed-no-inner` (confirmed, from F7 halt 2026-07-05): LEGO card sections carry
  `inner_bg` (50.4 direct path) but match `column-layout-2` / `image-gallery`, which lack `class="_inner"`,
  so the 50.4 nested-card render path (`component_matcher.py:2054`→`component_renderer.py:1124`) no-ops and
  the white surface is dropped (`elif section.bg_color` skipped because `inner_bg` is truthy). Blocks F7
  half-1 "LEGO cards reappear". Real fix = 51.1 composite-slot card wrapper on the column seeds, not
  `_detect_inner_bg` promotion.

## 6. A3 score log (append per landed item)

| Date | Item | c5 | c6 | c7 | c8 | c9 | c10 | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-07-03 | baseline (audit-4) | 0.879 | 0.801 | 0.624 | 0.702 | 0.640 | 0.679 | full_image; section_min 0.63/0.48/0.30/0.30/0.36/0.09 |
| 2026-07-04 | F2+F8 | 0.879 | 0.801 | 0.623 | 0.793 | 0.732 | 0.679 | F2 dark bands hold: **c8 +0.091, c9 +0.092** (section_min c8 0.30→0.67, c9 0.36→0.53); 5/6/10 neutral (explicit==implicit white, byte-changed/score-flat); c7 −0.001 noise (residual is F1/F4). F8 corpus byte-identical. BEFORE row reproduced audit-4 exactly. |
| 2026-07-04 | F1 | 0.879 | 0.801 | 0.612 | 0.802 | 0.732 | 0.679 | full_image; section_min 0.634/0.480/**0.271**/**0.688**/0.527/0.087. Heroes now emitted as `<img>` (c7 `2833:1881`, c8 `2833:2264` — HTML-verified, in regen baselines). **Pixel deltas are asset-artifacts, not the win:** hero PNGs absent from fixtures (pre-F1 exported only `images[0]`), unrecoverable (c7 cache URL 403, c8 uncached, no `FIGMA_TOKEN`) → scorer renders heroes blank. c7 **−0.011** (blank gap replaces stretched strip), c8 **+0.009** (median 0.790→0.859). c5/6/9/10 byte-identical (no F1-builder multi-image sections). Real win pending hero re-export (`phase-53.7-asset-reexport-prerequisite`). |
| 2026-07-04 | F4a-d | 0.877 | 0.814 | 0.612 | 0.802 | 0.723 | 0.678 | **Correctness win, not pixels.** Zero leaks on all 6 (`Shop Now`/`Learn More`/`Read More`/fakeimg/`Feature icon`/📅/📍, entity+UTF-8). **c6 +0.013** (F4a empty cta-fill + F4c emoji-in-span; median 0.682→0.698). c9 (F4b col-icon): median **0.776→0.833** (2 headings recovered from the text-block mis-route) but full −0.009 / section_min 0.527→**0.353** (sections [7]/[8], both col-icon) — F4b fills the real `/api` icon src (`2833:2113`/`2126`), but those assets are **absent from the fixture (disk-verified missing; the render shows a broken-image box)**, which pixel-matches slate's real icon worse than the prior fakeimg grey rectangle did. Production serves these assets; this is a fixture asset-gap (same as F1 heroes) with the table structure intact (verified in the render) — not a code regression. c5/c10 −0.002/−0.001 noise (F4a dropped a non-design seed CTA). c7/c8 byte-identical (untouched). F4d: 5 builder-less slugs removed from the converter scorer (library intact), 0 baseline change. Ladder 13/9/8/10/8/12 held. |
| 2026-07-04 | F5 | 0.844 | 0.814 | 0.615 | 0.802 | 0.723 | 0.678 | **Compliance win, not pixels.** Footer legal/unsub row now preserved (was wiped by whole-cell fill). Only **c5/c7** have a footer section (6/8/9/10 end in `social-icons` → outside F5's reach, **byte-identical**). **c5 −0.033** (0.877→0.844; section_min 0.632→0.492): off-design legal boilerplate ("© Company Name"/"123 Business Street") + unsub links now render on maap's dark footer — accepted compliance/fidelity trade (cf. F4). **c7 +0.003** (0.612→0.615; editorial now in styled `footer-text` cell). Ladder 13/9/8/10/8/12 held. Merge tags `{{unsubscribeUrl}}`/`{{preferencesUrl}}` contained to footer_legal (2/case, zero leak outside). c8 pre-existing heading trailing-whitespace drift (F8-noted) normalized by regression; c8 baseline untouched. |
| 2026-07-05 | F3 | 0.844 | 0.802 | 0.636 | 0.802 | 0.679 | 0.678 | **Correctness win, not pixels.** Design width threaded through every image emission (`_column_image_row`+`_image_fills_column`; `overrides["width"]`+`_clamp_img_max_width` on image-block/hero/grid/product; full-bleed keeps `width:100%`, byte-identical). **c9 giants fixed (composite-verified): pins/thermometer 270→34px, grid arrow 292→48px; c7 LEGO decorations →26/30px** (**+0.021**, section_min 0.280→0.338). c8 flat (median 0.859→0.868, 504px Ferrari correct); c5 flat (200px maap neutral). **c9 −0.044 (section_min held 0.353) / c6 −0.012 are scorer artifacts:** shrinking the oversized icons drops render height (c9 aspect 3.31→2.63) below the reference's card-inflated height (RC-F7 cards still missing), so the resize-based band scorer distorts — per-section shows only the height-shifted bands moved (sec3 0.922→0.492), no render defect. **c10 arrows unchanged** — width inflated 28→268px at ingest (`layout_analyzer.py:1318`), outside F3's 2-file scope → deferred `phase-53f-decorative-image-flag`. Ladder 13/9/8/10/8/12 held; c10 byte-identical. |
| 2026-07-04 | F6 | 0.844 | 0.814 | 0.615 | 0.802 | 0.723 | 0.678 | **Correctness win, not pixels.** Eyebrow/kicker order flipped: pre-heading body texts render ABOVE the heading (HTML + composite verified vs reference — c8 `FERRARI 849 TESTAROSSA`/`…SPIDER` above their headings, c5 `New Season Collaboration` above `MAAP x KASK`). Only **c5/c8** carry pre-heading eyebrows (**6/7/9/10 byte-identical**). full_image flat on all 6; **c8 section_median 0.859→0.868** (+0.009, the eyebrow section now matches the design's reading order); c5 flat (0.844/0.492/0.806 — a ~12px eyebrow reposition is sub-rounding on the 5036px composite). Per-node typography preserved (12px `#DA291C` center on c8; Courier New 12px on c5); heading `_cell` padding intact (`padding-bottom` longhand dodges the `padding:`-shorthand override). Ladder **13/9/8/10/8/12 held**. Pre-existing F8-noted heading trailing-whitespace (not F6) stripped by pre-commit hook + normalized by snapshot comparison → committed c8 baseline changes are eyebrow-rows-only; moves again when F3 (Lane A, unshipped) lands. |
| 2026-07-05 | F7 (pills) | 0.845 | 0.802 | 0.636 | 0.802 | 0.679 | 0.678 | **Fixture recovery (maap pill radius), not code.** Stale c5 `structure.json` (6 Jun) dropped the scalar `cornerRadius:25.0` on all 8 `mj-button`s; surgically re-inserted (`+8  0` diff, no `json.dumps` round-trip). **7 city pills 4px→25px** via the existing `_column_cta_row` — **c5 0.844→0.845** (section_median 0.806→**0.821**; section_min 0.492 flat — a 152px pill rounding is sub-rounding on the 5036px composite). **c6–c10 byte-identical** (only c5 `expected.html` touched; scores unchanged). 8th button section [1] 'Discover →' stays 4px — it renders via `_fills_text_block`, which **hardcodes `border-radius:4px`** (`component_matcher.py:1345`), a pre-existing corpus-wide bug (also c6 'Order your fall favorite', c7 'Explore now') → deferred `phase-53f-f7-text-block-cta-hardcoded-radius` (user-ratified). Ladder **13/9/8/10/8/12 held**; `rendered_w600.png` left frozen (advisory-only, stale since F5/F6). |
