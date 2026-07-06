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
| Drop/inner shadow, blur, blend modes | **No** — flat fallback only |
| Gradients | **Partial** — `linear-gradient` + VML fallback; not all clients |
| Rotation, free 2D geometry, z-order / overlap | **No** — not expressible in flow layout |
| SVG / decorative vector | Rasterize or inline PNG only (recovery: 53.5, open) |
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
**2026-07-06 end-to-end validation: the re-run remedy is NOT sufficient on current code.**
A full API re-run on the stale LEGO connection (live token, conversion cache cleared and
bypassed, connection re-synced → fresh snapshot, three fresh imports incl. a forced
legacy-path conversion) still renders 'Explore now' white-on-white/borderless/r4,
byte-identical to the stale April output — the snapshot `_file_structure` serializer and
the protocol `DesignNode` bridge drop the Track-B fields before the renderer ever sees
them, and the fresh-sync `document_json` path converts the whole file (selection ignored).
Harness fixtures are unaffected (same renderer renders the CTA black-on-white + 2px from
`structure.json`). Fixes tracked in §4 (last two rows); until they land, app-side runs
understate converter fidelity **regardless of re-syncing**.

## 4. Residual gaps (tracked, not hidden)

| Residual | Tracker | State |
|---|---|---|
| **Mammut below-candidate under-count (12 vs 18).** The gap sits below the candidate row (raw-tree bands = 12); zero peelable `wrapper → single section → ≥2 column` shapes exist in case 10, so neither the D3 one-level peel **nor a fork-(b) faithful tree walk** reaches the missing 6 sections. Naive deep recursion was prototyped and REJECTED (over-segments: LEGO 8→18, maap 9→19). | `phase-53-d3-mammut-below-candidate-undercount` (deferred-items) | Open — needs a content-aware deep-segmentation seam; no current path to convergence |
| A2 semantic under-count gate: only case 10 still xfails (`SEMANTIC_UNDERCOUNT_CASES = {"10"}`); advisory `collect_metrics` still reads converter-current counts (`regression_runner.py:113`) | `phase-53-a2-advisory-section-gate` (deferred-items) | Strict for 5/6/7/8/9 since the D3 ship (2026-06-12); only the mammut residual + the advisory-metrics circularity remain |
| Typography schema cap: `email-design-document-v1.json` `tokens.typography maxItems:200` vs LEGO's 234 emitted entries — latent because the converter path never calls `EmailDesignDocument.validate()` | `phase-53.7-typography-maxitems-cap` (deferred-items) | Open — fix before schema-validating any persisted document |
| Asset re-export prerequisite: `data/debug/*/assets/` are gitignored; a fresh clone must re-run `scripts/export-case-assets.py` with a `FIGMA_TOKEN`; CI runs the pixel metric on case 5's committed PNGs only | `phase-53.7-asset-reexport-prerequisite` (deferred-items) | Open — same variance class §A1 warned about; surfaced, not resolved |
| VLM verify→correct loop: dead on the default path (`vlm_verify_enabled=False`; correction applicator is property-only — cannot add/remove/reorder/merge sections; internal metric returns 1.0 on empty input) | **53.4 — RETIRED 2026-06-12** (`.agents/plans/53-4-vlm-retirement.md`) | Flag deprecated, cull 2026-09-10; reopen conditions documented; `vlm_fallback_enabled` (matcher classification) unaffected |
| Never-parsed ingest render: effects/blendMode (flat/VML fallback), per-node gradient reattach (52.5 `node_id` captured), `scaleMode`/`imageTransform` crop, rotation, z-order → `frame_export` | TODO.md **53.3** | Open — capture landed (52.5); render pending |
| Decorative standalone VECTOR/LINE nodes fall through extraction (`layout_analyzer.py`) | TODO.md **53.5** | Open — `DocumentVector` class or rasterize/inline-PNG |
| **Column width budget:** column seeds hardcode 600px-context pixel widths (MSO ghost `td width` + div `max-width`); any horizontal inset (band `_cell` padding, F7 card padding) shrinks the live content box below the seed total, so the inline-block columns wrap and **2-col layouts render stacked** (c7 all 6 benefit cards, c8 spec grid, c10 product grid). Detection is correct — A8 fractions redistribute but never rescale the total | `phase-53f-column-width-budget` (deferred-items) | Open — F9-class renderer-side rescale; Track-F close-out finding (plan §4 row 4's "detection widening" is the wrong lever) |
| In-column content ordering: `_build_column_fill_html` emits images→texts→buttons buckets, discarding design y-order (tag pills render below body instead of eyebrow-above-heading; card icons above product names) | `phase-53f-column-category-order` (deferred-items) | Open — y-order merge in the column fill builder |
| **App-side render-field drop:** snapshot `_file_structure` cache + `cached_dict_to_node` protocol schema lack `corner_radius`/`stroke_weight`/`stroke_color`/`text_align` (and `text_color` dies in the protocol→converter bridge) — app conversions render invisible/unstyled CTAs even after a fresh re-sync, while the harness renders the same design correctly | `phase-53f-app-snapshot-serializer-drops-render-fields` (deferred-items) | Open — same inert-serializer-bridge class as RC-A/RC-B; disproves the §3 re-run remedy on current code |
| **Document-path selection bug:** with `snapshot.document_json` present (fresh syncs write one), `run_conversion` converts the whole-file document and ignores `selected_node_ids` (observed: 2MB template with zero email content) | `phase-53f-document-path-ignores-node-selection` (deferred-items) | Open — filter to selection or fall back to legacy path; dev-DB workaround: connection 5's snapshot-20 `document_json` nulled |

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
