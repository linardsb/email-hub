# Implementation Report — CE-9 icon + label columns stop routing as CTAs (#427)

**Plan**: `.agents/plans/ce-9-nav-columns-not-cta.md`   **Branch**: `feat/ce-9-nav-columns-not-cta` (from `origin/main` `1a891e70`)   **Status**: COMPLETE (T1–T10; T11 = `piv-commit` → `piv-validate` → `piv-create-pr`, next)

## Summary

Ported the spike (`.tmpscratch/ce9/spike.diff`, worktree commit `fb3b4beb`) task by task. A peeled icon + label column (case-6 nav band: APP, ORDER, OFFERS, REWARDS) now matches the `td` seed with an icon-over-label tile instead of `cta-button`/`social-icons`; `_match_by_type` no longer sends a button-less CTA type to a CTA seed; the VLM fallback cannot pick a CTA-family slug for a button-less section. Case 6 regenerated, its three icon assets committed, case 6 re-stamped with four gains and no drops.

## Tasks completed

- T1 branch from `origin/main` → base `1a891e70` (observed: `git fetch` + `git log -1 origin/main`); `git diff --stat 1a891e70 origin/main -- app/design_sync/ app/components/ data/debug/ email-templates/components/` empty.
- T2 tests → `app/design_sync/tests/test_icon_label_columns.py` (CREATE), `app/design_sync/tests/test_social_section_content.py` (UPDATE, F5 retarget = T6).
- T3 matcher → `app/design_sync/component_matcher.py` (UPDATE): tile route in `match_section`, VLM guard, CTA guard in `_match_by_type`, `padding`/`align` kwargs on the column row builders, `_CTA_FAMILY_SLUGS`, `_is_icon_label_tile`, `_tile_labels`, `_fills_icon_label_tile`, `_icon_label_gap`.
- T4 baseline → `data/debug/6/expected.html` (UPDATE).
- T5 assets → `data/debug/6/assets/2833_1457.png`, `_1462.png`, `_1467.png` (CREATE); `.gitignore` (UPDATE, three allowlist lines).
- T8 ledger → `.agents/deferred-items.json` (UPDATE).
- T9 re-stamp → `data/debug/fidelity_baseline.json` (UPDATE).

## Tests added

`test_icon_label_columns.py`: 36 tests (observed, `pytest -q` count). RED under stubs (`_is_icon_label_tile` → False, `_fills_icon_label_tile` → `[]`, full `_CTA_FAMILY_SLUGS`): 14 failed / 22 passed, no ImportError (observed):

- `TestNodeTreeRouting::test_icon_label_row_routes_to_tiles_not_cta`
- `TestMatcherRules::test_cta_typed_tile_routes_to_td`, `test_social_typed_peel_tile_routes_to_td`, `test_header_typed_peel_tile_routes_to_td`, `test_cta_without_button_is_not_a_cta_component`
- `TestTileHtml::test_icon_centred_at_design_width_above_styled_label`, `test_label_gap_from_column_geometry`, `test_label_gap_zero_without_line_height`, `test_two_labels_gap_above_first_only`, `test_tree_path_keeps_the_icon`
- `TestVlmGuard::test_vlm_cta_slug_rejected_without_button`
- `TestCorpusInvariants::test_cta_component_implies_a_button[6]`, `test_icon_label_rows_reach_the_output[6]`
- `test_c6_nav_tiles_compile_on_the_tree_path`

14 = S3's 10 + the four added after S3 (derived: plan T2). 9 failed on `AssertionError`, 5 on `ValueError: not enough values to unpack` (the tile-HTML tests unpacking the stub's empty fill list; an assertion on output shape, not an import failure). After T3: 36/36 green.

### Mutations (T7, `uv run python .tmpscratch/ce9/mutate.py`, observed; `component_matcher.py` restored byte-identical, `diff -q` clean)

| Mutation | Failed | RED | Stays green (by design) |
|---|---|---|---|
| M1 drop CTA guard | 1 | `test_cta_without_button_is_not_a_cta_component` | `test_cta_component_implies_a_button[6]` (tile route catches c6 first) |
| M2 drop peel-row requirement | 1 | `test_standalone_social_link_keeps_social_icons` | tile routing tests |
| M3 tile slug → `cta-button` | 7 | node-tree routing, CTA/SOCIAL/HEADER tile routing, both c6 corpus invariants, c6 tree compile | — |
| M4 drop icon row | 5 | tile HTML, node-tree routing, c6 output invariant, unit tree test, c6 tree compile | — |
| M5 `slot_type="text"` | 2 | `test_tree_path_keeps_the_icon`, `test_c6_nav_tiles_compile_on_the_tree_path` | default-path tests |
| M6 drop VLM guard | 1 | `test_vlm_cta_slug_rejected_without_button` | — |
| M7 gap forced to 0 | 1 | `test_label_gap_from_column_geometry` | — |
| M8 predicate counts raw texts | 2 | `[placeholder-label]`, `[blank-label]` | — |

Identical to the plan's S14 totals.

## Validation results (all observed on this branch)

| Check | Result |
|---|---|
| T3 targeted: `test_icon_label_columns`, `test_component_matcher`, `test_cta_fidelity`, `test_social_section_content` | 256 passed |
| `ruff format --check` (3 files), `ruff check --no-fix app/design_sync/` | clean |
| `make types` | mypy passed, pyright 0 errors |
| Baseline audit (`snapshot-capture.py <case> --output .tmpscratch/ce9/cap3/<case>.html`, `diff --ignore-all-space`) | 5, 7, 8, 9, 10, reframe: 0 changed lines; c6: 72 |
| c6 diff confinement | changed lines 229–318 of the new file, all inside `section_4`–`section_7` markers (228–326) |
| c6 vs spike baseline | `cmp` identical |
| `grep -c "padding:6px 0 0"` / `grep -ci "follow us"` on c6 | 4 / 0 |
| `make snapshot-test` | 38 passed, 12 skipped, 2 xfailed |
| ladder `-k ladder` | 7 passed; `ladder_snapshot.json` diff vs `origin/main` empty |
| `make golden-conformance` | 26 passed, 9 skipped |
| `test_content_checks.py` | 56 passed |
| `make lint-numeric` | rc 0 |
| `TestCommittedFixtures`; `git check-ignore data/debug/6/assets/2833_1457.png` | 15 passed; rc 1 |
| Icon PNGs vs spike (`cmp`) | 1457, 1462, 1467 identical (891 / 1073 / 1249 bytes) |
| `test_social_section_content.py` | 15 passed |
| Ledger byte round-trip | ok |
| `pytest app/design_sync/tests/ app/components/tests/` | 3411 passed, 115 skipped, 10 xfailed, 0 failed |
| `make converter-data-regression` | 85 passed, 48 skipped, 8 xfailed |
| `make test` | 8903 passed, 118 skipped, 10 xfailed, 0 failed |
| `make fidelity-gate` on base `1a891e70` | passed in main's CI run 37063674884 (`test_fidelity_gate_holds_baseline PASSED`, observed via `gh run view --log`) |
| `make fidelity-gate` on branch before re-stamp / after | 1 passed / 1 passed |
| `make check-full` | not run here; `piv-validate` runs it on the committed head |

### A3, full corpus (`DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`, vs `.tmpscratch/ce9/a3_before/scores.json`; observed)

| Case | full | min | median | max per-section Δ |
|---|---|---|---|---|
| 5 | 0.8660 → 0.8660 | 0.6632 → 0.6632 | 0.8852 → 0.8852 | 0.000 |
| 6 | 0.8126 → 0.8131 | 0.4661 → 0.4661 | 0.7573 → 0.7573 | +0.002 (section 8) |
| 7 | 0.8403 → 0.8403 | 0.5459 → 0.5459 | 0.8679 → 0.8679 | 0.000 |
| 8 | 0.8632 → 0.8632 | 0.8081 → 0.8081 | 0.8645 → 0.8645 | 0.000 |
| 9 | 0.7089 → 0.7089 | 0.3033 → 0.3033 | 0.7614 → 0.7614 | 0.000 |
| 10 | 0.7361 → 0.7361 | 0.0639 → 0.0639 | 0.8336 → 0.8336 | 0.000 |
| reframe | 0.8437 → 0.8437 | 0.5505 → 0.5505 | 0.8779 → 0.8779 | 0.000 |

`before` re-derived on this branch: base matcher swapped in (`git show origin/main:app/design_sync/component_matcher.py > …`), same command, then restored (`git diff --quiet HEAD -- app/design_sync/` clean). Its `scores.json` is identical to the spike's `a3_before/scores.json` (observed, dict equality). Only the matcher differs from base at that point; the swapped run used the regenerated c6 baseline, which the scorer does not read (it renders live output).

### CE-1 gate rows (`scripts/fidelity-gate.py check` in the pinned image, before re-stamp; observed)

| Node | Marker | base | now | Δ | status |
|---|---|---|---|---|---|
| 2833:1455 | section_4 | 0.9827 | 0.9891 | +0.0064 | improved |
| 2833:1460 | section_5 | 0.9740 | 0.9787 | +0.0047 | pass |
| 2833:1465 | section_6 | 0.9765 | 0.9781 | +0.0016 | pass |
| 2833:1470 | section_7 | 0.9629 | 0.9802 | +0.0173 | improved |

Every other section in all seven cases +0.0000. No drop, so U4's stop rule did not trigger. Re-stamp: `make fidelity-restamp CASES="6"` with the plan's reason string (figures unchanged); `fidelity_baseline.json` +12/−4, stamp `commit` = `e2a0b56c` (the WIP commit), not `1a891e70`.

### Screenshots (`.tmpscratch/ce9/shots.py`, Chromium light; observed)

- 640px: peel-row table box 640×64; four icons, each above its label.
- 375px: four centred tiles stacked, height 256 (derived: 4 × 64); box width 463 = the pre-existing page overflow (R5, ledger `ce-9-c6-mobile-page-overflow`).

## Deviations from the plan

- **Report path**: `.claude/reports/ce-9-nav-columns-not-cta-report.md` (piv-implement's `<plan-slug>-report.md`) instead of the plan's `ce-9-nav-columns-report.md`, so `piv-create-pr` finds it by plan slug.
- **Preflight run after implementation, not before** (T1). Step 2b (`jq` over `origin/main`'s ledger for `component_matcher`, `component_renderer`, `layout_analyzer`, `data/debug/6`, `test_social_section_content`, `fidelity_baseline`) returned the plan's table plus one entry the plan omits: `phase-53-d3-mammut-below-candidate-undercount` (matched on `layout_analyzer.py`). Decision: **avoid**; this diff does not touch `layout_analyzer.py` (U1) or case 10 (0-line audit). Open PRs touching `component_matcher.py`/`component_renderer.py`/`data/debug/6`: none (`gh pr list --state open`, observed), so no merge-order conflict with CE-8 #426 / CE-11 #429.
- **`docs/converter-fidelity-ceiling.md` not appended.** Its § 3 is a dated Track-G snapshot; CE-1 and CE-3 did not append either, and c6 moves by +0.0005 full-image only. Say if the doc should carry CE-era figures.
- **Report tracked** in the PR (CE-1's precedent; the plan allows either).
- **RED failure kinds**: the plan says "RED on assertions"; 5 of the 14 fail on `ValueError` (unpacking the stub's empty fill list). They fail on the stubbed behaviour, not on imports, so the RED proof holds.
- **T11 not run here**: `piv-commit`, `piv-validate` (`make check-full`), `piv-create-pr` and CI watch are the next skills, per the piv-implement hand-off.

## Issues encountered

- The main checkout carried uncommitted `app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` from `plan/dsl-spec`; they moved with the branch switch and are never staged.
- No migrations; `alembic heads` not relevant.
- PR body must state F8: button-less CTA sections of any origin now match as CONTENT (corpus-neutral, observed via the 0-line non-target audit).
