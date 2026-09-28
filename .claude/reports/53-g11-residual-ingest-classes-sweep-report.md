# Implementation Report — G11: Residual ingest classes sweep (Track G · closes 3 ledger items)

**Plan**: `.agents/plans/53-g11-residual-ingest-classes-sweep.md`
**Branch**: `feature/g11-residual-ingest-classes-sweep` (off `origin/main` `5e14429`)
**Status**: COMPLETE (with one documented, verified deviation on item 1 case 8)

## Summary

Three independent converter (Figma→email HTML) fidelity gaps, each an open deferred-items entry.
Shipped as three ordered commits (item 3 → 2 → 1) so each item's corpus diff-audit stayed isolated
(case 10 is hit by both item 1 and item 2). Item 3 (loader parity) and item 2 (decoration width) land
fully; item 1's band-absorbed divider renders on the corpus (c10), and its in-column divider category is
wired + unit-proven but has zero corpus fires — the one case-8 divider sits in a `social`-classified
section that discards all non-icon column content (an upstream segmentation gap now separately tracked).

## Commits (three ordered, per plan)

- `d3e7ae48` — item 3: `report.py` loader round-trips `line_height_relative`
- `ad88ecf0` — item 2: frame-wrapped decorations ≤64px export at child size
- `405f17d0` — item 1: nested mj-divider rules (band-absorbed c10 + in-column category)

## Tasks completed

- **Item 3** → `app/design_sync/diagnose/report.py` (UPDATE, +1 kwarg), `tests/test_diagnose_roundtrip.py` (CREATE)
- **Item 2** → `app/design_sync/figma/layout_analyzer.py` (UPDATE, frame-wrap branch + `_SMALL_DECORATION_MAX_PX`),
  `tests/test_image_width_fidelity.py` (EXTEND), `data/debug/{7,8,9,10}/expected.html` (regen)
- **Item 1** → `layout_analyzer.py` (`ColumnDivider`, `ColumnGroup.dividers`, `_column_divider_lines`,
  `_column_content_order`, 2 capture sites), `email_design_document.py` (`DocumentColumn.dividers` ×4 methods),
  `component_matcher.py` (`_ordered_column_elements`, `_group_spec_pairs`, `_is_spec_icon/label`,
  `_column_divider_row`, `_build_column_fill_html`), `sibling_detector.py` (`BandRule`,
  `RepeatingGroup.internal_rules`, `group_by_wrapper` capture), `component_renderer.py`
  (`_band_internal_rule_row`, `render_repeating_group` injection + equal-length guard),
  `tests/test_nested_divider_render.py` (CREATE), `data/debug/10/expected.html` (regen)
- **Close-out** → `.agents/deferred-items.json` (3 closed/adjusted + 2 new entries), plan file, this report.

## Tests added

- `test_diagnose_roundtrip.py` — 3 tests: full-field parity over `dataclasses.fields(DesignNode)` through
  `report.py`'s serializer (RED on `line_height_relative`, confirmed sole gap), children survive, focused reload test.
- `test_image_width_fidelity.py::TestFrameWrapDecorationWidth` — 5 tests: small decoration → child width+export
  (RED at 268), radius-only wrapper still child-exports + keeps radius (RED at 60), 3 controls (>64 cap,
  `img==frame` FILL, baked bg-fill wrapper all keep frame export).
- `test_nested_divider_render.py` — 2 end-to-end tests: case 8 drives the real column pipeline
  (`_detect_mj_columns` → DocumentColumn round-trip → `_build_column_fill_html`) asserting a `border-top`
  rule between the two texts; case 10 drives `group_by_wrapper` → `render_repeating_group` asserting a
  `border-top` rule row between members with member count preserved. Both confirmed RED before the fix.

## Validation results

- **Unit** — item-3 (3), item-2 (22 incl. controls), item-1 divider/column/sibling/repeating suite (71): all GREEN.
- **`uv run pyright` / `uv run ruff --no-fix`** on all touched files: 0 errors (2 pre-existing unused-function
  warnings in layout_analyzer, not mine).
- **`make snapshot-test`**: 34 passed, 1 xfailed. Moved baselines diff-audited to only the intended change:
  c7/c8/c9 decoration shrinks, c10 arrows→28 + 2 divider rule rows. c8 divider baseline UNCHANGED (see deviation).
- **`make converter-data-regression`** (A2 ladder): 73 passed, 1 xfailed — section counts UNCHANGED for all
  cases (AC #4); the c10 `test_rendered_matches_target` xfail still xfails.
- **`make check-full`**: (see foot of report / PR checks).

## A3 pixel fidelity (advisory, non-gating — reachable on this machine, ran all 6 cases)

| case | baseline full_image | after G11 | note |
|---|---|---|---|
| 5 maap | 0.866 | 0.866 | flat (0 fires) |
| 6 Starbucks | 0.820 | 0.820 | flat (frame-wrap fires inert — social render path) |
| 7 Lego | 0.856 | 0.840 | item-2 shrink → scorer re-alignment jitter (composites match reference) |
| 8 perf | 0.785 | 0.822 | **improved** (64px icon un-ballooned) |
| 9 slate | 0.684 | 0.681 | within noise; section_min +0.03 |
| 10 mammut | 0.754 | 0.720 | item-2 arrow jitter; item-1 rules flat (0.719→0.720) |

**AC #5 holds**: non-targets c5/c6 flat, c9 within noise (the cases AC #5 guards). Details in *Deviations*.

## Deviations from the plan

1. **Item 2 — A3 drops on TARGET cases c7/c10 are scorer artifacts, not regressions** (the plan predicted
   these as wins but never actually ran A3, believing it unreachable; it is reachable here). The fidelity
   scorer scales the render to the reference height and scores fixed design-fraction bands, so shrinking
   decorations redistributes content vertically and every band jitters bidirectionally (measured: c10
   sections swing −0.54 to +0.14; c7 min section 3 sits above every shrink so its HTML is unchanged yet it
   moved). Verified via before/after per-section arrays + side-by-side composites (c7 icons + c10 arrows match
   the reference; c8 clearly improves) + design geometry (a 28px image in a 268px frame rendered at 268 is a
   10× upscale — objectively wrong). AC #5 guards only the NON-targets (c6/c9), which hold. Saved as memory
   `reference_a3_scorer_section_instability`. Not a defect.

2. **Item 1 case 8 — in-column divider category wired + unit-proven, but 0 corpus fires (does NOT render on
   c8)**. Root cause (verified, not assumed): c8's only in-column divider (`2833:2365`) sits in section
   `2833:2348`, which classifies as `social` and renders via `_fills_social` (social links only). That path
   discards ALL non-icon column content — the two flanking legal texts (`2833:2363`, `2833:2367`) are ALSO
   absent from c8 output — so it never traverses `_build_column_fills`. This is an upstream
   segmentation/classification gap (G12 territory), not a divider-category defect: the category is correct and
   proven end-to-end by `TestColumnChildDivider` driving the real column pipeline. On this 6-case corpus every
   column-divider happens to sit in a `social`- or `divider`-typed section, so the category has no corpus fire.
   **c8 baseline UNCHANGED** (no regen, no claimed case-8 corpus win). Tracked as new ledger entry
   `phase-53g-g11-social-section-drops-column-content` (blocked_by 53.5). AC #1 is therefore **partially met**:
   case 10 renders on corpus; case 8 is a wired-but-upstream-blocked capability.

3. **Item 1 — ContentGroup third column path ledgered, not fixed** (Simplicity First). The
   `_build_column_fills_from_content_groups` path builds `ColumnGroup` from a `ContentGroup` (no `dividers`
   field) → a divider-bearing column taking that fallback would re-drop. The corpus flows through
   `column_groups`, so it is latent. Tracked as `phase-53g-g11-contentgroup-column-divider-gap`.

4. **Item 2 — implemented `export_node_id=_crop_export_id(img)` (idiomatic), not the plan's literal
   `export_node_id == child_id` assertion**. For a non-cropped child, `_crop_export_id` returns `None`, and
   `import_service.py` falls the export target back to `node_id` (== child), exactly like a plain IMAGE node.
   The test asserts the *effective* export target (`export_node_id or node_id == child`), which is the correct
   invariant. Same render behavior, avoids a redundant explicit id.

## Ledger changes (`.agents/deferred-items.json`)

- `phase-53.3-line-height-relative-loader-gap` → **closed** (`d3e7ae48`).
- `phase-53f-decorative-image-flag` → **frame-wrap half closed** in notes; entry stays **deferred** for the
  remaining large-decorative-photo / z-order-role half (`closes_when` narrowed).
- `phase-53.5-nested-divider-render-gap` → **closed** (`405f17d0`, both render categories wired), with an
  explicit residual note superseding into the social-under-render entry for c8's corpus symptom.
- **NEW** `phase-53g-g11-social-section-drops-column-content` (known-bug) — the c8 root cause.
- **NEW** `phase-53g-g11-contentgroup-column-divider-gap` (speculative) — the third-path latent re-drop.

## Issues encountered

- The docs-branch WIP edit to `.claude/code-reviews/pr-364-review.md` was parked in a git stash
  (`docs-branch pr-364-review.md WIP (parked during G11)`) before branching off `origin/main`, to keep it out
  of this PR. **It must be restored** on `docs/track-g-artifacts-backfill` via `git stash pop` (or `git stash
  list` → apply) once G11 is done — otherwise that docs work is orphaned.
