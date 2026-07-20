# Figma→Email Converter — Honest Fidelity Ceiling

**Status:** contractual artifact (Phase 53.7). This is the document of record for what the
design-sync converter **can and cannot** reproduce, per client, and where the residual gaps
are tracked. It supersedes every fidelity-% claim that predates it.

**Date:** 2026-06-12 · **Engine:** fork (a) — fixed-seed + band grouping (53.1 gate,
ratified 2026-06-12; decision doc `.agents/plans/53-1-fork-decision.md`).

---

## 1. Numbering supersession (read first)

- The "Phase 50–53" labels in `.agents/plans/50-converter-fidelity-master.md` are **stale**
  and superseded — the operative roadmap was **Phase 52 (foundation)** + **Phase 53 (engine)**
  in `TODO.md`; full plans in `.agents/plans/52-converter-foundation.md` and
  `.agents/plans/53-converter-engine-fix.md`.
- The historical **"85% → 93% → 97% → 99% fidelity ladder" is void.** It was computed by a
  grayscale, blurred, gmail-only, off-by-default SSIM that could not see color, gradient,
  shadow, or sub-pixel spacing (see `docs/fidelity-gap-audit-findings.md`). Express converter
  progress by **defect-class closure**, never by a percentage.

## 2. What email can and cannot reproduce (fork-independent caps)

| Design feature | Reproducible in email? |
|---|---|
| Stacked bands, columns (equal — or asymmetric via A8 per-column widths), typography (incl. per-run since RC-D-prime), solid fills, links, CTAs | **Yes** |
| Outlook/Word rendering | **~95% floor** regardless of engine (table + VML) |
| Drop/inner shadow, blur, blend modes | **No** — flat fallback; loss surfaced as a `design_sync.effects_dropped` conversion warning since 53.3a |
| Gradients | **Partial** — 53.3b renders `linear-gradient` on the outer band with the solid midpoint as fallback (incl. MSO `bgcolor`); VML `v:fill type="gradient"` is an open follow-up; radial/angular/diamond stay solid-only |
| Rotation, free 2D geometry, z-order / overlap | **No** in flow layout — 53.3d's `DESIGN_SYNC__FRAME_EXPORT_FALLBACK_ENABLED` (default off) rasters such subtrees to one exported frame image when enabled |
| SVG / decorative vector | Rasterize only (53.5, shipped 2026-07-06): standalone vectors ≥ 8×8 px export as PNG via the node render; zero-area `mj-divider` LINEs thread their stroke into the divider seed's rule (section-level only — nested dividers tracked in `phase-53.5-nested-divider-render-gap`) |
| True opacity over non-white backdrops | Approximate — 52.5 composites against the real backdrop at ingest; still a flattened hex |

Per-client notes:

- **Gmail-class (Gmail web/iOS/Android, Apple Mail, modern webmail):** the high-fidelity
  target. Typography/spacing/color plumbing (P52) reaches output; band structure matches the
  design on 5 of 6 fixtures (see §3).
- **Outlook/Word engine:** hard ~95% ceiling — MSO ghost tables, no border-radius on tables,
  no background-image without VML, per-node `<td>` anchors carry explicit
  `mso-line-height-rule:exactly`. **The pixel metric renders gmail_web only; the Outlook
  floor is asserted, not scored** (carried in the A3 advisory caveats).
- **Anything rendering through `sanitize_web_tags_for_email()`:** no `<p>`/`<h*>`/layout
  `<div>` survives by design (`.claude/rules` + `CLAUDE.md` HTML email rules).

## 3. Measured state (2026-06-12, default config unless flagged)

Section-count ladder (`data/debug/ladder_snapshot.json`, A2 target gate):

| Case | Fixture | Rendered | Target | Gate |
|---|---|---|---|---|
| 5 | maap | **13** | 13 | **strict** |
| 6 | starbucks | **9** | 9 | **strict** |
| 7 | LEGO | **8** | 8 | **strict** |
| 8 | performance_reimagined | **10** | 10 | **strict** |
| 9 | slate | **8** | 8 | **strict** |
| 10 | mammut | 12 | 18 | xfail — **below-candidate residual, see §4** |

- Band grouping (`DESIGN_SYNC__BAND_GROUPING_ENABLED`) default **ON** since D1 (`50c691b2`);
  env var is the kill switch, cull by 2026-09-10.
- Semantic peel (`DESIGN_SYNC__SEMANTIC_PEEL_ENABLED`, D3 `f632b8df`) default **ON** since
  2026-06-12: the D3 follow-up composes peeled same-row siblings side-by-side (one
  `peel_row_id` per visual row; MSO ghost cells + inline-block columns) while each card
  still counts as its own section. A3 verdict: maap full-image fully recovered
  (0.8789 vs 0.8788 flag-off; the stacked spike was −0.026), starbucks full-image
  **+0.042**; cases 7/9/10 byte-identical.
- A3 pixel metric (CIEDE2000 in LAB, MIN-aggregated, blur 0.0): **advisory only, never a
  ship gate.** CI scores committed case-5 fixtures (first trustworthy numbers at `3c1ba9f7`:
  full_image 0.867 · section_min 0.642 · section_median 0.887); all 6 fixtures resolve
  locally since A4, but their assets are **gitignored — CI cannot score them** (tracked,
  §4). The metric did not discriminate the 53.1 forks (Δ ≤ +0.013) — the ladder decides.
- Per-run typography (RC-D-prime, `8c5cffd7`): every body text node renders its own
  font/size/weight/color via `<td data-node-id>` anchors + `_text_<node_id>` overrides;
  closed `phase-52.4b-per-run-typography-structural`.

**Track F close-out (2026-07-05, branch `fix/phase-53f-f7-pills-radius`; full log
`.agents/plans/53-f-render-fidelity.md` §6):** the seed-fill render-defect classes
RC-F1–F8 are closed or ledgered. Metric: **A3 advisory pixel score** (CIEDE2000 in LAB,
MIN-aggregated, blur 0.0, **gmail_web render only**), local 6-fixture corpus (assets
gitignored — CI still scores case 5 only):

| Fixture (client) | full_image | section_min | section_median | Δ full_image vs audit-4 (2026-07-03) |
|---|---|---|---|---|
| 5 maap | 0.845 | 0.492 | 0.821 | −0.034 — F5 compliance trade, accepted at ship |
| 6 starbucks | 0.802 | 0.477 | 0.699 | +0.001 |
| 7 LEGO | 0.719 | 0.351 | 0.804 | **+0.095** |
| 8 performance_reimagined (Ferrari) | 0.802 | 0.688 | 0.868 | **+0.100** |
| 9 slate | 0.679 | 0.353 | 0.745 | +0.039 |
| 10 mammut | 0.678 | 0.087 | 0.777 | −0.001 |

Pixel movers were F2 (bg-less-seed background insert — dark bands hold on c8/c9) and
F7-cards (column card surfaces — c7 +0.083). F1/F3/F4/F5/F6/F7-pills/F8 are
correctness/compliance wins the band scorer under-prices: fixture asset gaps render F1
heroes / F4b icons as blank boxes (`phase-53.7-asset-reexport-prerequisite`), and F3's
icon shrink removes render height the reference's still-unbuilt card structure inflates.
Plan §3 band target (c7/c8/c9 full_image ≥0.80): **c8 met; c7/c9 missed** — remaining
mechanisms recorded honestly in plan §6 close-out; the dominant one is the **column
width-budget** residual (§4). Ladder unchanged (13/9/8/10/8/12). **Ops caveat:** app-side
design runs ingested before the Track B–F extraction upgrades render *below* these numbers
on identical renderer code — their DB-stored structures lack radius/stroke/text-color/
alignment fields (observed on a 2026-04-03 LEGO run: invisible outlined CTA, 4px pills,
left-aligned headings). Re-run design-sync on stale runs before judging fidelity.
**2026-07-06 end-to-end validation → fixed same day.** The morning validation DISPROVED
the re-run remedy on then-current code: a full API re-run (live token, cache cleared and
bypassed, re-sync, three fresh imports incl. a forced legacy-path conversion) still
rendered 'Explore now' white-on-white/borderless/r4 — the snapshot `_file_structure`
serializer dropped the Track-B fields, the `_fix_text_contrast` post-pass repainted the
label against the band instead of the pill's own background, and a fresh-sync
`document_json` hijacked selected-node imports into whole-file conversions. All four
mechanisms were fixed the same day (`fix/phase-53f-app-render-field-parity`): the cache
serializer round-trips every `DesignNode` render field (parity-guarded test), selected-node
imports always take the legacy filtered path, the text-block CTA threads the designed
radius, and the contrast fixer honours an element's own background. Post-fix, `POST
/connections/sync` + re-import renders the LEGO CTA **black-on-white + 2px + r25** with
centered headings — harness parity through the API, screenshot-verified. **Ops note:**
runs synced before this fix still serve field-less snapshots — one re-sync + re-import
per connection after deploy.

**Track G close-out (2026-07-20, main `baf5beaf`; full log
`.agents/plans/53-g-production-readiness-prompt-sequence.md`).** G1–G9 closed render-mistake
classes M1–M10 — band-spacing continuity (M1/G1), empty-slot + single-text heading ghosts
(M2·M9/G2), button box geometry + per-corner pill radius (M3/G3+G5), composite-slot infra +
own-row CTA (M8/G4), spec mini-table + hug-row centering (M4·M6/G7), the membership
card-with-N-children composite (M5/G6), the composite footer + legal policy (M7/G8), and the
Outlook ghost-width arithmetic gate (M10/G9). Corpus re-scored on current main —
`render_case_png` re-runs the converter live, so this is the HEAD `baf5beaf` measurement, not a
replay. Metric identical to Track F: **A3 advisory pixel score, CIEDE2000 in LAB,
MIN-aggregated, blur 0.0, gmail_web render only**, local 6-fixture corpus (assets gitignored —
CI still scores case 5 only):

| Fixture (client) | full_image | section_min | section_median | Δ full_image vs Track-F (2026-07-05) |
|---|---|---|---|---|
| 5 maap | 0.866 | 0.663 | 0.885 | +0.021 |
| 6 starbucks | 0.820 | 0.477 | 0.698 | +0.018 |
| 7 LEGO | 0.856 | 0.684 | 0.896 | **+0.137** |
| 8 performance_reimagined (Ferrari) | 0.785 | 0.676 | 0.786 | −0.017 |
| 9 slate | 0.684 | 0.418 | 0.762 | +0.005 |
| 10 mammut | 0.754 | 0.067 | 0.857 | +0.076 |

The **c7 +0.137** jump (largest, Track-F 0.719 → HEAD 0.856) is dominated by the G6
membership-card composite (c7 full_image 0.771→0.893 post-G6, per its result block) **plus** the
now-closed column-width-budget and column-category-order residuals (§4) that had rendered c7's
six benefit cards stacked and image-above-text; G7–G9 then netted c7 back to the final 0.856.
c8's −0.017 is a minor hero/spacing trade (the Ferrari mark renders large; no
content loss). The section-count ladder is **unchanged at 13/9/8/10/8/12**
(`data/debug/ladder_snapshot.json`) — G1–G9 is render-only work and does not move section
counts; the mammut 12-vs-18 under-count (§4) stands, and c10's `section_min 0.067` is that
region's oversized decorative nav arrows, not a blank.

*Composite eyeball (asset-coverage sanity, all 6 fixtures):* every design image renders except
maap's two MAAP×KASK product-gallery photos (nodes `2833:1645`/`2833:1652`), which the converter
emits as a **`background-image`** on the hero-block table (both assets present on disk,
330 KB / 251 KB). The fidelity *scorer* rewrites only `src="…"` attributes to local file URLs —
not `background-image: url(…)` — so those two boxes render blank **in the harness only**. The
converter emits the same `/api/v1/design-sync/assets/…` path for `src` and `background-image`
alike, and the shipped app serves that path (the app-parity export below served all 23 of the
LEGO fixture's asset refs) — so a real client (or the app preview) fetches the background-image
and renders it. The blank is the harness rewrite-regex's limitation, not an app or converter
defect. c5's true gmail-class fidelity is therefore modestly above the measured 0.866; every
other fixture is blank-free, so the numbers are trustworthy.

**App-parity re-verified — M11 closed (2026-07-20, through the API).** Full path on a
freshly-synced connection-5 snapshot: `POST /connections/sync` → `POST /imports`
(`selected_node_ids=["2833:1869"]`, legacy filtered path) → `POST /imports/{id}/convert`
(`output_mode="html"`) → stored template HTML (`converter_output_v3.html`, 70865 B). A
URL-normalized structural diff vs `data/debug/7/expected.html` (every asset-URL surface — `src`,
`background-image: url()`, `background=`, MSO `v:fill src`, VML `v:image src` — collapsed to one
token; `data-node-id` left intact) is **empty** across 23 asset refs and 4 matching node
anchors ⇒ **#327 structural parity holds byte-for-byte**. Asset correctness (M11): the app
serves by exported node key (`…/assets/5/2833_1878.png`) with a systematic off-by-one vs the
harness key (`…/assets/2833:1879.png`). 3 sampled nodes serve the **same design image** — the
named `2833_1878`↔`2833:1879` pair is **pixel-identical**; the other two are visually identical
(verified by eye), differing only in intrinsic resolution / sub-0.1% edge antialiasing vs the
**14-day-stale (2026-07-06) on-disk harness export** (the app's fresh sync re-rendered the same
nodes). So the key offset is a benign naming convention, not a wrong export; byte-md5 differs
only because the harness assets are the older export. **Ops caveat (extends the 2026-07-06 note):** connections synced before #327
serve field-less snapshots — re-sync once before judging fidelity or parity.

## 4. Residual gaps (tracked, not hidden)

| Residual | Tracker | State |
|---|---|---|
| **Mammut below-candidate under-count (12 vs 18).** The gap sits below the candidate row (raw-tree bands = 12); zero peelable `wrapper → single section → ≥2 column` shapes exist in case 10, so neither the D3 one-level peel **nor a fork-(b) faithful tree walk** reaches the missing 6 sections. Naive deep recursion was prototyped and REJECTED (over-segments: LEGO 8→18, maap 9→19). | `phase-53-d3-mammut-below-candidate-undercount` (deferred-items) | Open — needs a content-aware deep-segmentation seam; no current path to convergence |
| A2 semantic under-count gate: only case 10 still xfails (`SEMANTIC_UNDERCOUNT_CASES = {"10"}`); advisory `collect_metrics` still reads converter-current counts (`regression_runner.py:113`) | `phase-53-a2-advisory-section-gate` (deferred-items) | Strict for 5/6/7/8/9 since the D3 ship (2026-06-12); only the mammut residual + the advisory-metrics circularity remain |
| Typography schema cap: `email-design-document-v1.json` `tokens.typography maxItems:200` vs LEGO's 234 emitted entries — latent because the converter path never calls `EmailDesignDocument.validate()` | `phase-53.7-typography-maxitems-cap` (deferred-items) | Open — fix before schema-validating any persisted document |
| Asset re-export prerequisite: `data/debug/*/assets/` are gitignored; a fresh clone must re-run `scripts/export-case-assets.py` with a `FIGMA_TOKEN`; CI runs the pixel metric on case 5's committed PNGs only | `phase-53.7-asset-reexport-prerequisite` (deferred-items) | Open — same variance class §A1 warned about; surfaced, not resolved |
| VLM verify→correct loop: dead on the default path (`vlm_verify_enabled=False`; correction applicator is property-only — cannot add/remove/reorder/merge sections; internal metric returns 1.0 on empty input) | **53.4 — RETIRED 2026-06-12** (`.agents/plans/53-4-vlm-retirement.md`) | Flag deprecated, cull 2026-09-10; reopen conditions documented; `vlm_fallback_enabled` (matcher classification) unaffected |
| Never-parsed ingest render: effects/blendMode (flat/VML fallback), per-node gradient reattach (52.5 `node_id` captured), `scaleMode`/`imageTransform` crop, rotation, z-order → `frame_export` | TODO.md **53.3** | **Shipped 2026-07-06** (`fix/phase-53.3-ingest-render`): linear-gradient reattach on the outer band (solid midpoint + MSO `bgcolor` fallback), non-FILL `scaleMode` crops export the node itself, rotation/overlap reproducibility classifier behind `DESIGN_SYNC__FRAME_EXPORT_FALLBACK_ENABLED` (default off), effects/blend loss → `design_sync.effects_dropped` warnings. Still open: VML gradient, radial+ gradients, `imageTransform` matrix (subsumed by scaleMode export). Corpus carries none of these — synthetic-test coverage only, baselines byte-identical |
| Decorative standalone VECTOR/LINE nodes fall through extraction (`layout_analyzer.py`) | TODO.md **53.5** | **Shipped 2026-07-06** (`fix/phase-53.5-vector-recovery`): ≥8×8 px vectors rasterize via node export (guards: inside-imaged-frame skip, sub-8px skip, Figma auto-name alt rejection); zero-area LINE strokes thread into the divider seed (`border-top`), recovering case 9's two rules (+0.001 full-image). Residual: nested (column-child / band-absorbed) dividers — `phase-53.5-nested-divider-render-gap`; corpus has no icon vectors, so the rasterize half is synthetic-coverage only |
| **Column width budget:** column seeds hardcode 600px-context pixel widths (MSO ghost `td width` + div `max-width`); any horizontal inset (band `_cell` padding, F7 card padding) shrinks the live content box below the seed total, so the inline-block columns wrap and **2-col layouts render stacked** (c7 all 6 benefit cards, c8 spec grid, c10 product grid). Detection is correct — A8 fractions redistribute but never rescale the total | `phase-53f-column-width-budget` (deferred-items) | **Closed (F9, `e6812b44` / #328)** — the renderer rescales the column ghost `td width` / `div max-width` / ghost-table total to the effective (padded) content box, so multi-column sections hold side-by-side inside padded bands/cards; contributed to c7's Track-G **+0.137** (with G6). Latent sibling `phase-53g-g9-img-not-rescaled-with-column` (below) tracks the un-rescaled `<img>` |
| In-column content ordering: `_build_column_fill_html` emits images→texts→buttons buckets, discarding design y-order (tag pills render below body instead of eyebrow-above-heading; card icons above product names) | `phase-53f-column-category-order` (deferred-items) | **Closed (`12aebee1`)** — the column fill builder emits in design y-order; eyebrow pills render above the heading and card icons below the product name |
| **App-side render-field drop:** snapshot `_file_structure` cache + `cached_dict_to_node` protocol schema lacked `corner_radius`/`stroke_weight`/`stroke_color`/`text_align`, and the `_fix_text_contrast` post-pass repainted CTA labels against the band instead of the pill's own background (the filing's "protocol bridge" hypothesis was wrong — the bridges are lossless) | `phase-53f-app-snapshot-serializer-drops-render-fields` (deferred-items) | **CLOSED 2026-07-06** (`fix/phase-53f-app-render-field-parity`) — serializer round-trips all render fields (dataclass-parity test) + contrast fixer honours own-background; LEGO CTA harness parity through the API |
| **Document-path selection bug:** with `snapshot.document_json` present (fresh syncs write one), `run_conversion` converted the whole-file document and ignored `selected_node_ids` (observed: 2MB template with zero email content) | `phase-53f-document-path-ignores-node-selection` (deferred-items) | **CLOSED 2026-07-06** (same branch) — selected-node imports always take the legacy filtered path; document path reserved for whole-file imports (both directions tested) |
| **Membership card [19] surface-less:** the LEGO Insiders card matched the image-gallery seed, which has no `_inner`/col-bg target, so RC-F7's card-surface wrap never fired and the barcode card rendered directly on the lime band | `phase-53f-f7-image-gallery-membership-card` (deferred-items) | **Closed (G6 / #357)** — card-with-N-children composite renders the white r18 shell + 440px hug; c7 full_image 0.771→0.893 post-G6 |
| **BrandRepair footer backstop dead:** `RepairPipeline` is never invoked from any design-sync path and `_repair_footer` early-returns on the seed's footer class and never injects an unsubscribe link | `phase-53f-brandrepair-footer-gaps` (deferred-items) | **Closed (G8 / #360)** — converter is self-sufficient: the email-footer seed's `footer_legal` cell (unsub/preferences/address rows) is preserved verbatim, never overwritten by `_fills_footer` |
| **RC-F7 card wrapper overflows the 600px MSO ghost:** the relocated `_cell` padding landed on the 100%-width wrapper `<td>` outside the ghost, so Word rendered the card ~40px too wide (Chromium-correct, so no gate caught it) | `phase-53f-f7-card-wrapper-outlook-ghost-overflow` (deferred-items) | **Closed (G9 / #362)** — MSO ghost Word-box arithmetic gate reconciles wrapper padding against the fixed 600px column |
| **Column rescalers don't shrink the contained `<img>`:** F9/A8/G7 rewrite a shrunk column's ghost `td width`, `div max-width`, and ghost-table total together but never the `<img>` inside — a design-width image can overflow its shrunk cell in Outlook while the G9 attr==max-width gate stays green | `phase-53g-g9-img-not-rescaled-with-column` (deferred-items) | Open — G9's deliberately-deferred sibling; latent-not-manifest (no corpus img exceeds its shrunk column today), rewrite the `<img>` width on column shrink |

## 5. How to talk about converter fidelity (the contract)

1. **Never cite a percentage** without naming the metric, the fixture set, and the client.
   The only trustworthy numbers today are the A3 advisory scores on the committed fixtures.
2. **Per-client ceilings are caps, not targets:** Outlook ~95% is a floor *assumption*
   (unscored); gmail-class is where the measured numbers live.
3. **"Cannot reproduce" is a feature list, not a bug list** (§2 table): shadows, blends,
   rotation, overlap, true opacity-over-color, arbitrary vectors. Designs that avoid them
   convert at the measured numbers; designs that use them get documented flat fallbacks.
4. New residuals go to `.agents/deferred-items.json` (load-bearing) or TODO.md Phase 53
   Track E (work items) — not into prose claims.
