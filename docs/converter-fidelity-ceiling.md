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
| 5 | maap | 9 (13 with peel flag — **exact**) | 13 | xfail (semantic, peel ship/park gate open) |
| 6 | starbucks | 5 (9 with peel flag — **exact**) | 9 | xfail (semantic, peel ship/park gate open) |
| 7 | LEGO | **8** | 8 | **strict** |
| 8 | performance_reimagined | **10** | 10 | **strict** |
| 9 | slate | **8** | 8 | **strict** |
| 10 | mammut | 12 | 18 | xfail — **below-candidate residual, see §4** |

- Band grouping (`DESIGN_SYNC__BAND_GROUPING_ENABLED`) default **ON** since D1 (`50c691b2`);
  env var is the kill switch, cull by 2026-09-10.
- Semantic peel (`DESIGN_SYNC__SEMANTIC_PEEL_ENABLED`, D3 `f632b8df`) default **OFF**;
  flips maap/starbucks to exact. Ship/park is an open user gate: counts exact and starbucks
  full-image +0.018, but maap −0.026 (peeled side-by-side cards render stacked;
  section_median rises 0.870→0.917).
- A3 pixel metric (CIEDE2000 in LAB, MIN-aggregated, blur 0.0): **advisory only, never a
  ship gate.** CI scores committed case-5 fixtures (first trustworthy numbers at `3c1ba9f7`:
  full_image 0.867 · section_min 0.642 · section_median 0.887); all 6 fixtures resolve
  locally since A4, but their assets are **gitignored — CI cannot score them** (tracked,
  §4). The metric did not discriminate the 53.1 forks (Δ ≤ +0.013) — the ladder decides.
- Per-run typography (RC-D-prime, `8c5cffd7`): every body text node renders its own
  font/size/weight/color via `<td data-node-id>` anchors + `_text_<node_id>` overrides;
  closed `phase-52.4b-per-run-typography-structural`.

## 4. Residual gaps (tracked, not hidden)

| Residual | Tracker | State |
|---|---|---|
| **Mammut below-candidate under-count (12 vs 18).** The gap sits below the candidate row (raw-tree bands = 12); zero peelable `wrapper → single section → ≥2 column` shapes exist in case 10, so neither the D3 one-level peel **nor a fork-(b) faithful tree walk** reaches the missing 6 sections. Naive deep recursion was prototyped and REJECTED (over-segments: LEGO 8→18, maap 9→19). | `phase-53-d3-mammut-below-candidate-undercount` (deferred-items) | Open — needs a content-aware deep-segmentation seam; no current path to convergence |
| A2 semantic under-count gate: cases 5/6/10 xfail, keyed on `SEMANTIC_UNDERCOUNT_CASES` (`ladder_harness.py`); advisory `collect_metrics` still reads converter-current counts (`regression_runner.py:113`) | `phase-53-a2-advisory-section-gate` (deferred-items) | Partially closed (strict for 7/8/9 since D1); 5/6 close if the D3 peel ships |
| Typography schema cap: `email-design-document-v1.json` `tokens.typography maxItems:200` vs LEGO's 234 emitted entries — latent because the converter path never calls `EmailDesignDocument.validate()` | `phase-53.7-typography-maxitems-cap` (deferred-items) | Open — fix before schema-validating any persisted document |
| Asset re-export prerequisite: `data/debug/*/assets/` are gitignored; a fresh clone must re-run `scripts/export-case-assets.py` with a `FIGMA_TOKEN`; CI runs the pixel metric on case 5's committed PNGs only | `phase-53.7-asset-reexport-prerequisite` (deferred-items) | Open — same variance class §A1 warned about; surfaced, not resolved |
| VLM verify→correct loop: dead on the default path (`vlm_verify_enabled=False`; correction applicator is property-only — cannot add/remove/reorder/merge sections; internal metric returns 1.0 on empty input) | **53.4 — RETIRED 2026-06-12** (`.agents/plans/53-4-vlm-retirement.md`) | Flag deprecated, cull 2026-09-10; reopen conditions documented; `vlm_fallback_enabled` (matcher classification) unaffected |
| Never-parsed ingest render: effects/blendMode (flat/VML fallback), per-node gradient reattach (52.5 `node_id` captured), `scaleMode`/`imageTransform` crop, rotation, z-order → `frame_export` | TODO.md **53.3** | Open — capture landed (52.5); render pending |
| Decorative standalone VECTOR/LINE nodes fall through extraction (`layout_analyzer.py`) | TODO.md **53.5** | Open — `DocumentVector` class or rasterize/inline-PNG |

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
