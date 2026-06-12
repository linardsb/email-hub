# 53.4 — VLM verify→correct loop (RC-G): RETIRED

**Decision (2026-06-12):** the VLM render→compare→correct loop is **retired** as a fidelity
mechanism. No fidelity claim may credit it. Document of record for fidelity:
`docs/converter-fidelity-ceiling.md`.

## Evidence

1. **Dead on the default path, triply.** `vlm_verify_enabled = False`
   (`app/core/config/design_sync.py:58`); `convert_document` accepts and discards
   screenshots (`converter_service.py:284-286`); the loop is reachable only via the
   non-default `convert_document_mjml` → `_apply_verification`
   (`converter_service.py:375-396`), which short-circuits without per-section screenshots
   that `import_service` never passes.
2. **Structurally cannot fix what mattered.** `correction_applicator.py` is property-only —
   style props `color/font/spacing` + simple layout props `width/max-width/min-width/
   text-align/vertical-align` (`:34-38`). It cannot add, remove, reorder, or merge
   sections. Segmentation was the dominant defect class (5/6 fixtures) and was closed
   **deterministically**: band grouping default-on (D1 `50c691b2`) closed the
   over-segmenters exactly; the D3 content-scale peel heuristic hit maap 13 and
   starbucks 9 **exactly without VLM** (`f632b8df`, sub-plan §D3.4 explicitly recorded
   "VLM variant not needed for the count targets").
3. **Self-deceiving metric.** `visual_verify.py:183-186`:
   `avg_diff = sum(section_scores.values()) / max(len(section_scores), 1)` — empty input
   ⇒ `avg_diff = 0` ⇒ `fidelity_score = 1.0`. The loop reports false-perfect exactly when
   it has measured nothing (e.g. on broken renders that produced no comparable sections).
4. **Its measurement role is now redundant.** The "do not revive until assets resolve"
   precondition resolved at A4 — and what that unlocked was the **A3 metric**
   (CIEDE2000/LAB, MIN-aggregated, advisory in CI), which measures fidelity independently
   of any correction loop. The loop's residual value proposition — property-level nudges —
   is the class of defect P52/P53 fixed at the source (typography trio, RC-D-prime per-run
   typography, per-side padding, A8 column widths).

## What retirement means concretely

- `DESIGN_SYNC__VLM_VERIFY_ENABLED` stays default-off and is registered **deprecated** in
  `feature-flags.yaml` with removal date 2026-09-10 (aligned with the band-grouping kill
  switch cull).
- Code stays in-tree, gated off, until the removal date: `visual_verify.py` loop,
  `correction_applicator.py`, `correction_tracker.py`, the `_apply_verification` seam, and
  their tests. Removal sketch at cull: delete those modules + the `vlm_verify_*` settings
  block; **keep `vlm_classifier.py`** — it serves the separate, unretired
  `vlm_fallback_enabled` matcher-classification fallback (`match_section_with_vlm_fallback`).
- `docs/converter-fidelity-ceiling.md` §4 row updated from "decision pending" to RETIRED.

## Reopen conditions (any revival must also fix evidence-#3 first)

1. A recurring defect class that is property-shaped (colors/fonts/spacing/simple widths)
   AND demonstrably not fixable deterministically at the matcher/renderer source; or
2. the correction applicator gains structural operations (section add/remove/reorder/merge)
   with a real eval; or
3. per-section design screenshots become available on the **default** import path, making
   the loop's input exist where output ships.
