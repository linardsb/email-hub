# Phase 53 Track D — Fork-(a) Execution: fixed-seed + band grouping

> The chosen-fork sub-plan produced by the **53.1 gate** (`.agents/plans/53-1-fork-decision.md`,
> 2026-06-12). Companion to `.agents/plans/53-converter-engine-fix.md` §Track D-(a).
> **Fork decision ratified by the user 2026-06-12 — Track D is unblocked.** All work below
> assumes branch `spike/phase-53-track-c-band-grouping` (C1+C2a at `e3d010b3`, gated off)
> merges first.
>
> Success criterion carried from the gate: the **A1 ladder**
> (`python -m app.design_sync.tests.ladder_harness`), with the A3 pixel metric advisory.

## Scope

Three workstreams + close-out. D1 is mechanical productionization of the measured spike;
D2 is the asymmetric-columns gap fork-(b) would have closed natively; D3 is the only path
to the under-count residual (proven semantic — no structural rule exists, spike doc §C2b).
RC-D′ per-run typography stays in Track E (unchanged), now unconditionally scoped.

---

## D1 — Productionize C1+C2a `[S, ~2–3d]`

Flip `band_grouping_enabled` default `False → True` (`app/core/config/design_sync.py:92`)
and make the gates measure the new reality.

1. Default-on the flag; keep `DESIGN_SYNC__BAND_GROUPING_ENABLED` as the kill switch.
   Update `.env.example` comment (flag stays for ≤90d per `make flag-audit` lifecycle;
   add a cull note dated +90d).
2. Regenerate per-case baselines (`expected.html`) for the cases whose render changes
   (7, 9, 8; verify 5/10 grouping deltas) — **`snapshot_diff_audit.py`
   intended-vs-structural review before every regen** (master plan §Track B rule; this
   caught the 52.4c double-`style=` bug).
3. Regen the A2 drift snapshot: `python -m app.design_sync.tests.ladder_harness --write`
   → commit `data/debug/ladder_snapshot.json`.
4. Re-pin the A2 target gate: cases 7/8/9 flip from `xfail` to **strict assertions**
   (`test_converter_data_regression.py:281` — parametrize per-case strictness; 5/6/10 stay
   xfail with the semantic-residual reason string pointing at D3). Update the per-case
   `manifest.yaml` `sections:` counts (the converter-current values change: 7→8, 9→8,
   8→10, 5→9, 10→12).
5. Deferred items: mark the over-segmenter half of `phase-53-a2-advisory-section-gate`
   closed (strict gate now enforces; per-block-vs-band concession resolved by C1's
   `sections_count = len(grouped_sections)`); leave the under-segmenter half open,
   `closes_when` re-pointed at D3.

**Verify:** ladder ON-row reproduces the gate table (8/8/10 exact); `make snapshot-test`;
`make golden-conformance`; `make check-full`; A3 driver re-run shows no full-image drop
beyond noise (≤0.005) on any case.

---

## D2 — A8 per-column-width override `[M, ~1–1.5wk]`

Asymmetric column splits are currently forced to equal-width seeds. Plumb the measured
column proportions through (the fork-(b) capability worth keeping, at patch cost).

- `app/design_sync/figma/layout_analyzer.py:926-965` — `ColumnGroup` already measures
  child x/width; surface a `width_fractions` (normalized) field.
- `app/design_sync/component_matcher.py:183-190` — carry fractions onto the match so the
  renderer sees them (mirror how `parent_wrapper_id` flows post-C1).
- `app/design_sync/component_renderer.py:699-781, 973-978` — emit per-`<td>` `width`
  (+ MSO ghost-table widths) from fractions; fall back to equal when fractions are
  within tolerance (~5%) of equal, so existing baselines stay byte-stable.
- Tolerance + falsy-numeric care: fractions are floats — follow `make lint-numeric`
  rules (no `if fraction:`).

**Verify:** new unit tests on the fraction plumb (analyzer → matcher → renderer); ladder
unchanged on all 6 (A8 must not move section counts); baseline diffs reviewed
(`snapshot_diff_audit.py`) — only width attrs/MSO widths may change; `make check-full`.

---

## D3 — Semantic segmentation seam (under-count residual) `[spike ~1wk, then gate]`

The gate's load-bearing finding: `mj-section → N mj-column` = 1 section (perf stats) or
N sections (starbucks cards) is decided by **content meaning**, not structure. The
actuator already exists — the C2b **constrained one-level peel** (prototyped: fixes maap
9→13 and starbucks 5→9 exactly, regresses perf 10→13 when applied blindly). What is
missing is the **discriminator**.

1. Spike a per-wrapper classification call: given the single-child wrapper's grandkid
   geometry + content bags (text scale, imagery presence), classify `peel` vs `keep`.
   Reuse the existing VLM classification seam (`vlm_classifications.json` fixtures exist
   for cases 5/6/10) — coordinate with the 53.4 VLM-loop decision (master plan Track E);
   this is a *segmentation-time* classification, not the render-verify loop, but the same
   provider plumbing. A deterministic heuristic baseline (column height/content-scale
   threshold: 232/64px cards vs 30px stats) goes in first so the spike has a
   no-LLM fallback to measure against.
2. Gate behind `DESIGN_SYNC__SEMANTIC_PEEL_ENABLED` (default off), same spike discipline
   as C1: flag-off byte-identical, ladder measures flag-on.
3. **Exit criteria:** ladder ON → maap 13, starbucks 9, mammut 18 **without** regressing
   7/8/9 (8/10/8); classification is design-agnostic (no fixture-keyed rules — the C1
   "design-agnostic" bar, spike doc §What shipped); decide ship vs park on those numbers.
4. If the heuristic baseline alone hits the exit criteria, ship it and record the VLM
   variant as not-needed; if neither hits, the residual is documented in the 53.7
   honest-ceiling doc as a known cap — **not** a reopen trigger for fork-(b) (the
   decision doc's reopen conditions are seed-grammar caps, not this).

**Verify:** ladder both ways; `make snapshot-test`; A2 strict set extended to whichever
of 5/6/10 converge; A3 advisory re-run.

---

## D4 — Close-out `[S, ≤1d]`

- Update master plan §Gate status block + §Track D with results; banner the gate table's
  "(b) Yes by construction" cell as refuted-on-fixtures (point at the decision doc).
- Deferred items: close/update per D1.5 and D3 outcomes; add an entry if D3 parks with a
  known residual.
- `docs/TODO-completed.md` entry only when the full phase closes (per house rule).
- Hand the per-client honest-ceiling doc to Track E 53.7 (unchanged scope).

## Sequencing & verification gates

```
ratify 53.1 ──► D1 (2–3d) ──► D2 (1–1.5wk) ──► D4
                   └──► D3 spike (1wk, parallel to D2) ──► D3 gate ─┘
```

Every step: `make check-full` + ladder harness; render-affecting steps add
`make snapshot-test` + `snapshot_diff_audit.py` review + `make golden-conformance`;
A3 driver (`.tmpscratch/gate_53_1_fidelity_run.py`) re-run at D1/D3 exit as the advisory
pixel cross-check.

## Risks

| Risk | Mitigation |
|---|---|
| D1 baseline regen masks an unintended render change | `snapshot_diff_audit.py` review per regen; A3 noise bound (≤0.005 drop) |
| D2 width fractions destabilize every column baseline | equal-within-tolerance fallback keeps existing baselines byte-stable |
| D3 classifier overfits the 3 fixtures | design-agnostic bar (no fixture-keyed rules) + 7/8/9 non-regression in exit criteria |
| Flag soak: two new flags accumulate | flag-audit cull notes dated at creation (90d warn / 180d error) |
