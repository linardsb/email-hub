# Phase 53 — Track C segmentation spike result

> Feeds the **53.1 fork gate**. Companion to `.agents/plans/53-converter-engine-fix.md` §Track C.
> **Not a commit** — the engine change ships behind `DESIGN_SYNC__BAND_GROUPING_ENABLED`
> (default **off**); flag-off output is byte-identical to `main`.

## What shipped (flag-gated, off by default)

**C1 — explicit band grouping by `parent_wrapper_id`.** `group_by_wrapper()` in
`sibling_detector.py` regroups sections sharing the exact `parent_wrapper_id` the
Phase-50.3 wrapper-unwrap pre-pass already stamps, instead of re-deriving similarity.
Wired into `_match_phase` (`converter_service.py`) behind `band_grouping_enabled`.
The rendered-block count was also corrected: `sections_count` was `len(match.matches)`
(flat — counts every exploded card), now reports `len(grouped_sections)` (bands) when
the flag is on.

**C2a — SPACER absorption.** `group_by_wrapper(absorb_spacers=True)` drops
SPACER/DIVIDER pseudo-sections inside a band (they are inter-card padding, not rows).

**Design-agnostic.** No fixture references in code. C1/C2a key only on wrapper
membership + section type — the same structural tags every MJML-named Figma design
carries. LEGO is the *measurement* fixture (A1 ladder), never a code path.

## A1 ladder (deterministic, no assets) — `python -m app.design_sync.tests.ladder_harness`

| case | name | target | flag OFF (`main`) | **C1+C2a ON** | verdict |
|------|------|-------:|------------------:|--------------:|---------|
| 7 | lego-insiders-halloween | 8 | 17 | **8** | ✅ exact (over-segmenter fixed) |
| 9 | slate-newsletter | 8 | 10 | **8** | ✅ exact |
| 8 | performance-reimagined | 10 | 11 | **10** | ✅ exact |
| 5 | maap-kask | 13 | 11 | 9 | ✗ under (worse on count) |
| 6 | starbucks-pumpkin-spice | 9 | 5 | 5 | ✗ under (unchanged) |
| 10 | mammut-duvet-day | 18 | 14 | 12 | ✗ under |

**C1 closes the over-segmentation defect: LEGO renders 8 top-level blocks with
correctly nested bands, plus slate and perf exact.** The renderer already nests
(`render_repeating_group`), confirming audit_2's refuted claim — a fork-(a) patch is
buildable, not structurally throwaway.

### Honest before/after (the "17" is partly the flat-count bug)

The flag-OFF ladder reads **17** for LEGO, but that is `len(match.matches)` — the
*flat* count of exploded cards, a pre-existing reporting bug. Similarity detection is
on by default and already collapses LEGO into 2 bands (`repeat_count=2` + `=4`), so
flag-OFF actually renders **~13 top-level blocks**, not 17. So the real structural
delta C1 delivers is **≈13 → 8 rendered blocks**; the reported-count delta is **17 → 8**
(C1 fixes segmentation *and* the flat-count bug, switching `sections_count` to
`len(grouped_sections)`).

### HTML verified (not just the count)

Rendered `data/debug/7` HTML inspected both ways. Flag-ON, LEGO is **4 solo blocks +
3 band tables (1897, 1941, 2040) + 1 solo**, each band a
`<table style="background-color:…">` carrying the wrapper fill (lime `#AFCA01`, purple
`#4E3092`, grey `#F4F4F4`); all 16 non-spacer sections present and correctly nested;
inter-card spacing preserved (`render_repeating_group` emits `20px/16px` row padding).
The 8 is a real block count, not just the tautological `band_descriptor` cross-check.

## C2b — single-child wrapper recursion: prototyped and REJECTED

The under-segmenters share one shape: `mj-wrapper → single mj-section → N grandkids`.
The `≥2`-section-child unwrap predicate sees one direct child, so the grandkids never
surface. Two segmentation attempts were prototyped and measured:

1. **Naive deep recursion** (peel + explode at the first ≥2-section level, depth 4):
   **over-segments badly** (LEGO 8→18, maap 9→19). `_is_section_child` is arity-based
   (`FRAME with children`) and once recursion descends it explodes content frames.
2. **Constrained one-level peel** (only `wrapper → single mj-section → ≥2 grandchildren`,
   grandchildren as distinct sections, no deep walk): **fixed maap 9→13 and starbucks
   5→9 exactly** — but **regressed perf 10→13**.

### The load-bearing finding for 53.1 — the boundary is *semantic*, not structural

The constrained peel pinned it precisely. The under- and over-count cases are the
**identical structure** with **opposite correct answers**:

| | starbucks (peel ✓ wanted) | perf (peel ✗ regression) |
|---|---|---|
| shape | `mj-wrapper → mj-section → 4 mj-column` | `mj-wrapper → mj-section → 4 mj-column` |
| geometry | 4 columns side-by-side, same `y` | 4 columns side-by-side, same `y` |
| column height | 232 / 64 px (content cards) | 30 px (stat numbers) |
| `target_sections` wants | **4 sections** (each card) | **1 section** (one 4-col row) |

By MJML semantics an `mj-section` with N `mj-column`s **is one section** — so perf's
count is structurally correct and starbucks' `target=9` counts each card *visually*.
No deterministic structural/geometric rule separates "4 cards → 4 sections" from "4
stats → 1 section"; the only signal is **what the columns mean** (content scale /
imagery), which is a VLM/semantic judgement. The peel imposes one design's reading and
regresses the other — so it is **not shipped**.

This is the **definitive fork signal**: closing the under-count requires
content-semantic segmentation (fork-(b)'s native tree walk + VLM/role classification),
not another structural heuristic on the flattened section list. The earlier "untried
discriminator" caveat is now closed — it was tried (directness + geometry) and the
boundary is genuinely semantic.

## Spike exit criteria (per plan §Track C)

- All-6 ladder after C1+C2a: **above**.
- Does the renderer emit nested bands cleanly? **Yes** — confirmed by inspecting the
  rendered LEGO HTML (3 band tables with correct wrapper fills, all 16 sections
  nested, spacing preserved), not only the count.
- Residual: **the under-segmenters (maap/starbucks/mammut)** — sections hidden below
  single-child wrappers. Closing them requires deciding whether `mj-section → N
  mj-column` is one section or N, which the spike proved is a **semantic** call
  (content scale), not a structural one. Genuine fork-(b)/VLM territory.

## Recommendation into the gate

Adopt **C1 + C2a** regardless of fork (clean, gated, fixes 3/6 exactly, HTML verified).
Note C1 moves the under-segmenter *counts* further from target (maap 11→9) — that is
correct-but-insufficient, not a regression: the grouping it does is visually right;
those fixtures are simply still missing the sections single-child wrappers hide.
**Do not enable `band_grouping_enabled` in production until the 53.1 fork is chosen**
and the A2 gate is re-pinned to `target_sections` (it would flip the over-segmenters
green and the under-segmenters red — correctly measuring the remaining defect).
