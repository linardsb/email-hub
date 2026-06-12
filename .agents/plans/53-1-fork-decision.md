# Decision Doc — 53.1 Strategy Fork (converter engine direction)

> Scope: the **GATE output** prescribed by `.agents/plans/53-converter-engine-fix.md` §Gate.
> Inputs: the A1 ladder (fresh re-run 2026-06-12, flag off + on), the A3 live pixel metric
> (fresh run 2026-06-12, **all 6 fixtures**, flag off + on), the Track C spike result
> (`docs/phase-53-track-c-spike.md`), and the fork-(b) feasibility findings
> (`.tmpscratch/fork_b_feasibility_findings.md`, 2026-06-02 primary-source verification).
> Branch `spike/phase-53-track-c-band-grouping` at `a6d2afa1`. Every number below was
> **measured this session**, not quoted from the audits.
>
> **Status: DECIDED + RATIFIED — fork (a)** (user ratification 2026-06-12; the gate is
> "the user's call, on a real number" — the numbers are below). Chosen sub-plan:
> `.agents/plans/53-d-fork-a-execution.md`. The gate is **closed**; Track D is unblocked.

## The question

Choose the engine direction: **(a)** keep fixed-seed + Track C band-grouping patch ·
**(b)** restore the recursive renderer · **(c)** per-frame raster — with **segmentation as
the explicit success criterion**, on live numbers from the committed fixtures.

## Measured evidence

### A1 structural ladder (deterministic, `python -m app.design_sync.tests.ladder_harness`)

| case | name | target | candidates¹ | rendered, flag OFF | rendered, **C1+C2a ON** |
|---|---|---:|---:|---:|---:|
| 7 | lego-insiders-halloween | 8 | 8 | 17² | **8 ✅ exact** |
| 9 | slate-newsletter | 8 | 8 | 10 | **8 ✅ exact** |
| 8 | performance-reimagined | 10 | 10 | 11 | **10 ✅ exact** |
| 5 | maap-kask | 13 | 9 | 11 | 9 ✗ under |
| 6 | starbucks-pumpkin-spice | 9 | 5 | 5 | 5 ✗ under |
| 10 | mammut-duvet-day | 18 | 12 | 14 | 12 ✗ under |

¹ `len(_get_section_candidates)` = the raw tree's own band count = **the count a fork-(b)
recursive walk would emit by construction** (it has no semantic merge/split — feasibility
findings §D: "faithfully reproduces whatever the tree is").
² Partly the flat-count reporting bug; the real flag-OFF structural state is ~13 rendered
blocks (similarity detection already collapses 2 bands). See spike doc §"Honest before/after".

### A3 advisory pixel fidelity (live metric, CIEDE2000 color similarity 0–1, all 6 fixtures)

Rendered fresh via `render_case_png` (Playwright, node-keyed `assets/` resolving on all 6 —
A4 complete) and scored with `score_case_fidelity` against the design reference PNGs under
`email-templates/training_HTML/for_converter_engine/`. Raw rows in
`.tmpscratch/gate_53_1_fidelity_{off,on}.json`.

| case | full-image OFF | full-image **ON** | Δ | section-median OFF→ON |
|---|---:|---:|---:|---|
| 5 | 0.8666 | 0.8792 | **+0.013** | 0.887 → 0.870 |
| 6 | 0.7586 | 0.7586 | 0.000 | 0.694 → 0.694 |
| 7 | 0.6156 | 0.6235 | **+0.008** | 0.671 → 0.683 |
| 8 | 0.6896 | 0.7014 | **+0.012** | 0.661 → 0.678 |
| 9 | 0.6343 | 0.6397 | +0.005 | 0.756 → 0.696 |
| 10 | 0.6788 | 0.6786 | −0.000 | 0.779 → 0.777 |

Caveats (stated, not hidden): advisory per plan §A3 — never a gate. The per-section bands
used for scoring come from `result.layout.sections` (pre-grouping), so flag-ON section
scores band-map a *re-grouped* render against *ungrouped* bands — the small section-level
drops (case 5/9 median, LEGO `section_min` 0.333→0.300) are banding-alignment artifacts of
the scorer, not visual regressions (the LEGO flag-ON HTML was inspected in the spike: all
16 sections correctly nested, wrapper fills right). `full_image` is the apples-to-apples
comparator. Case 10 carries a 0.087 broken-band outlier in both runs (one unresolved band —
pre-existing, fork-independent).

**Load-bearing reading: the pixel metric does not discriminate the forks.** Correct band
structure moves full-image ≤ +0.013. The residual gap (all cases sit 0.62–0.88) is
dominated by per-section content fidelity — typography (RC-D′), ingest losses (RC-E,
landed at `a6d2afa1` capture-side), imagery — which is **fork-independent Track E work**.
The structural (A1) criterion therefore decides the fork, exactly as the plan §Gate
prescribed ("segmentation as the explicit success criterion").

## The three findings that decide it

1. **Over-segmentation — the dominant structural defect (3/6) — is closed, today, under
   fork-(a).** C1+C2a lands LEGO/slate/perf **exact** with HTML-verified nested bands
   (spike doc §HTML-verified). Fork-(b)'s headline advantage — correct count by
   construction — is now worth zero on this class: it was achieved in ~3 spike-days,
   gated, flag-off byte-identical to `main`.

2. **Under-segmentation (3/6) is SEMANTIC and no structural engine closes it — including
   fork-(b).** The C2b prototype pinned it: starbucks (4 content cards → target 4
   sections) and perf (4 stat columns → target 1 section) are the **identical
   `mj-wrapper → mj-section → 4 mj-column` shape with identical geometry and opposite
   correct answers** (spike doc §C2b). And the measured candidates row refutes the gate
   table's "(b) closes segmentation: Yes by construction" for this class: the raw tree
   itself counts 9/5/12 vs targets 13/9/18 — a faithful tree walk reproduces the
   under-count. Closing it requires a content-semantic judgement (what the columns
   *mean*), i.e. a VLM/role-classification seam — attachable to **either** engine, weeks
   cheaper on the one we have.

3. **Fork-(b)'s residual unique value is reachable cheaper inside fork-(a).** What (b)
   still offers — proportional/asymmetric columns, per-node typography, radii — maps to
   already-specced fork-(a) work: **A8** per-column-width override (~1–1.5 wk, master plan
   Track D-(a)) and **RC-D′** per-run typography (2–3 d, Track E, closes
   `phase-52.4b-per-run-typography-structural`). The 2.5–4 eng-week tree re-plumb +
   renderer rebuild + ~4,490 LOC test rebuild buys no defect class the measurements leave
   open.

## Decision

**Fork (a): keep the fixed-seed engine + the Track C band-grouping patch.** Productionize
C1+C2a, add A8 asymmetric columns, and route the under-count residual to a **semantic
segmentation seam** (VLM/role classification deciding `mj-section → N mj-column` = 1 vs N)
— not to an engine rebuild. Sub-plan: `.agents/plans/53-d-fork-a-execution.md`.

**Fork (b): declined-for-now**, with explicit reopen conditions (both must hold):
- the corpus gains designs where the **seed grammar itself** caps fidelity (heterogeneous
  bands / layouts no seed + override can express) — i.e. a defect class that is structural
  and *not* closable by A8/RC-D′-style overrides; **and**
- the by-then multi-fixture, trusted A3 metric attributes a concrete gap to that cap
  rather than to ingest/typography/imagery.
Effort if reopened: ~2.5–4 eng-weeks via the `convert_from_structure` tree-persistence
entry + rebuild re-wired to the extracted helpers (feasibility findings §C/§D — not a
verbatim restore).

**Fork (c): ratified as never-the-default** (per all three audits): destroys
editability/ESP hooks; per-frame PNGs 0.64–2.4 MB blow the file-size QA gate and Gmail's
102 KB clip. Remains a **per-subtree escape hatch** for non-reproducible subtrees
(effects/rotation/overlap), gated on the RC-E reproducibility classifier (53.3/53.5
territory, ~2–3 wk prerequisite on its own — do not start it for this).

### Effort ledger (recorded per gate requirement)

| Option | Measured/specced effort | Closes over-count (3/6) | Closes under-count (3/6) |
|---|---|---|---|
| (a) + Track C | spike **done**; productionize ≈ 2–3 d; A8 ≈ 1–1.5 wk; semantic seam spike ≈ 1 wk | **Yes — measured exact** | No structurally; **seam is the only path** |
| (b) rebuild | 2.5–4 eng-wk | Yes (redundant now) | **No — measured** (candidates 9/5/12 vs 13/9/18) |
| (c) raster | 2–3 wk classifier prerequisite alone | n/a (image) | n/a (kills editability) |

## Deferred items touched (per `.claude/rules/deferred-items.md`)

- `phase-53-a2-advisory-section-gate` (open, soft) — D1 of the sub-plan partially closes
  it: flag-ON makes the over-segmenters XPASS the xfail target gate; D1 flips those cases
  to strict. The per-block-vs-band metric concession is resolved by C1's
  `sections_count = len(grouped_sections)` fix (flag-on).
- `phase-52.4b-per-run-typography-structural` (open, known-bug) — **stays open**, now
  unconditionally fork-(a) scoped (the "subsumed if fork-(b)" branch is dead). Closes in
  Track E RC-D′.

## Sign-off

- [x] Decision recorded with measured ΔE + effort per option (this doc)
- [x] Chosen-fork sub-plan written: `.agents/plans/53-d-fork-a-execution.md`
- [x] **Stakeholder (user) ratification** — given 2026-06-12. `band_grouping_enabled`
  may now flip on via sub-plan D1 (flag default-on lands with the A2 strict re-pin
  + baseline regen, not before).
