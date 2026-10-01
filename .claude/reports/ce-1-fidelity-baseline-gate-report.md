# Implementation Report — per-section fidelity baseline gate (CE-1, #419)

**Plan**: `.agents/plans/ce-1-fidelity-baseline-gate.md`   **Branch**: `feat/ce-1-fidelity-gate`   **Status**: PARTIAL: every task done locally; the cross-host part of Task 13 and the second same-head CI run (done check (a)) need the draft PR's CI, which has not run yet.

## Summary

A CI step in the `backend` job renders all six converter cases in a pinned Playwright image, cuts each render by the converter's section markers (mapped to Figma node ids through the new `ConversionResult.section_node_ids`), scores each section against a committed 1x design reference, and fails when any section drops more than 0.005 below its baseline, or when a section is lost or new. `make fidelity-restamp REASON="..."` rewrites the baseline and logs each stamp. Fixtures (6 references, 71 assets) are committed, the two stub regression metrics are gone, and the asset ledger entry records that the gate half is resolved.

## Tasks completed

- Task 0: branch `feat/ce-1-fidelity-gate` from origin/main `31598a90`.
- Task 1: `section_node_ids` on `ConversionResult`, set in `_assemble_phase` and carried through the VLM-verification copy → `app/design_sync/converter_service.py` (UPDATE)
- Task 2 + 2b: marker/node-id tests; A3 before/after → `app/design_sync/tests/test_fidelity_gate.py` (CREATE)
- Task 3: stub metrics removed, `overall_score` reweighted over the three real metrics → `app/design_sync/tests/regression_runner.py` (UPDATE)
- Task 4: `scripts/prepare-fidelity-fixtures.py` (CREATE); `data/debug/{5..10}/reference_1x.png` + 71 assets for cases 6–10 (CREATE)
- Task 5: allowlist block → `.gitignore` (UPDATE)
- Tasks 6, 8, 9: `app/design_sync/fidelity_gate.py` (CREATE), `scripts/fidelity-gate.py` (CREATE)
- Task 10: `fidelity_gate` marker → `pyproject.toml` (UPDATE); pinned-env test in `test_fidelity_gate.py`
- Task 11: `fidelity-gate`, `fidelity-restamp` targets; `fidelity-gate` added to `check-full` → `Makefile` (UPDATE)
- Task 12: `backend` on `ubuntu-24.04`, gate step + `fidelity-gate-scores` artifact → `.github/workflows/ci.yml` (UPDATE)
- Task 13: baseline stamped → `data/debug/fidelity_baseline.json` (CREATE); local spread measured; CI part pending
- Tasks 14–15: proofs (b) and (c) run and recorded
- Task 16: `docs/fidelity-gate.md` (CREATE)
- Task 17: `phase-53.7-asset-reexport-prerequisite` left **deferred** with a CE-1 note (see Deviations) → `.agents/deferred-items.json` (UPDATE)

## Tests added

`app/design_sync/tests/test_fidelity_gate.py`: 67 unit tests plus the pinned gate test.

- Marker mapping over the six real cases: flat markers, one marker per node id, ids unique and in the layout, **marker `section_i` holds the text of `section_node_ids[i]`**, and the unmarked set matches the baseline.
- Geometry: case-6 peel-row boxes side by side, every box inside the frame, clipping.
- Scoring: identity = 1.0, inversion < 0.5, render crop resized to the design crop, and `score_rendered_case` on real case 5 with the reference standing in as the render (all 1.0; a missing render box is recorded as skipped).
- `compare`: drop > margin fails, drop == margin passes, lost fails, new fails, improved passes, a missing case loses every section.
- Schema: round-trip, reason required, unknown field rejected.
- Committed fixtures (read from the git index): baseline covers 5–10 with margin 0.005; structure, tokens and reference committed per case with reference width == frame width; every asset the current output references is committed.
- Re-stamp: blank reason refused, non-pinned env refused, `--from` stamping appends a stamp, `--from` with another image refused.
- `test_fidelity_gate_holds_baseline` (`fidelity_gate` marker): skipped outside the image; passes inside it.

Results (observed): `uv run pytest app/design_sync/tests/test_fidelity_gate.py app/design_sync/tests/test_fidelity_case_scorer.py app/design_sync/tests/test_converter_data_regression.py -q` → 142 passed, 49 skipped, 1 xfailed.

Mutation check for Task 2 (observed): reversing `section_node_ids` left the plan's set-based assertions green. The added order test (`test_marker_wraps_its_own_node`) went red in all six cases. Restored.

## Validation results

- Ruff format and lint, mypy (1386 files), pyright (0 errors): clean (observed).
- `make snapshot-test`: 34 passed, 10 skipped, 1 xfailed (observed, after Task 1); `git status data/debug` showed no tracked change.
- A3 before/after Task 1 (observed, `score-fidelity-cases.py`, all six cases, full-resolution assets before Task 4): `scores.json` byte-identical (`cmp`). Table (both runs):

| case | full_image | section_min | section_median |
|---|---|---|---|
| 5 | 0.866 | 0.663 | 0.885 |
| 6 | 0.813 | 0.466 | 0.757 |
| 7 | 0.840 | 0.542 | 0.865 |
| 8 | 0.863 | 0.808 | 0.865 |
| 9 | 0.710 | 0.303 | 0.761 |
| 10 | 0.736 | 0.064 | 0.834 |

- `make fidelity-gate` ×2 at `d3040239`: 1 passed each; 76 sections, max abs delta vs baseline 0.0000 (observed).
- Task 8 box check in the image (observed): every case has marker indices == `range(len(section_node_ids))` and every box has width and height > 0. Case-6 peel row at top 1257 with left 0/157/314/471.
- Proof (b) (observed): #409 reverted → mammut `2833:1270` 0.0454 → 0.0343 (−0.0111) FAIL; no lost or new ids. Starbucks, performance and slate scored higher.
- Proof (c) (observed): `_SMALL_DECORATION_MAX_PX = 0.0` → 11 changed sections, 65 unchanged with gate delta 0.0000. On those same 65 sections the A3 design-y bands moved up to 0.1916.
- `make check-full` at `dfbe4cb3`: exit 0 (observed). Tests: 8657 passed, 116 skipped, 2 xfailed. The `fidelity-gate` prerequisite: 1 passed. `make lint` rewrote no files.
- Not run: plan Level 4 step 1 (a smoke re-stamp on a clean head); the unchanged local re-checks already show 0.0000.

## Deviations from the plan

1. **Playwright image 1.63.0, not 1.61.0.** Since the plan was written, `uv.lock` moved to playwright 1.63.0 (Dependabot PRs #407/#414/#416). The 1.61.0 image then refuses to launch ("Executable doesn't exist … required: v1.63.0-noble"). The Makefile now reads the tag from `uv.lock` (`FIDELITY_PLAYWRIGHT`), so the image always matches the lock. A future Playwright bump fails the gate on its own PR if rendering changes, and that PR re-stamps. AC 4's literal image name therefore reads `v1.63.0-noble`.
2. **`.pre-commit-config.yaml` updated.** `check-added-large-files` (500 KB) rejected five of the six references (up to 1.97 MB). The hook's `exclude` already exempts curated pixel fixtures (case assets, `rendered_w600.png`, design exports), so `reference_1x.png` was added to that exclude. Not in the plan's file list.
3. **Marker order test added.** Task 2's assertions are set-based, so a reversed `section_node_ids` passed them; the plan asked to record which check went red. Rather than rely on the browser gate alone, `test_marker_wraps_its_own_node` checks order without a browser.
4. **`section_node_ids` placement.** The plan named constructors `:488`/`:545`. The HTML-bearing constructor is `_assemble_phase` (`converter_service.py` ~:1076). The VLM-verification copy (~:486) passes the field through; the MJML, tree-bridge and empty results keep the default.
5. **Commit SHA inside the container.** The Makefile passes `FIDELITY_COMMIT=$(git rev-parse --short HEAD)` into the container rather than running git there. The initial stamp's `commit` is `31598a90` (the head before the first WIP commit); later squashing makes any branch SHA stale anyway (documented in `docs/fidelity-gate.md`).
6. **`GateError` subclasses `AppError`** (backend rule: no bare `Exception`). Private imports (`_color_similarity`, `_MIN_SECTION_HEIGHT_PX`, `_rewrite_asset_srcs`) use the inline `pyright: ignore[reportPrivateUsage]` idiom rather than new public aliases, so `visual_scorer.py` and `fidelity_case_scorer.py` stay untouched.
7. **`check` also fails on a gated case missing from the baseline.** A case directory with a `reference_1x.png` but no baseline entry reports its sections as `new`. This is how CE-3 and CE-5 add cases.
8. **Scores differ from the spike in image-bearing sections** (e.g. mammut `2833:1218` 0.0852 → 0.0020, case 8 ±0.01–0.017). The spike used full-resolution assets and Playwright 1.61. Crops were inspected: the images load, and the low mammut scores are dark bands that render white. The baseline is stamped on the shipped environment.

9. **`phase-53.7-asset-reexport-prerequisite` not closed (plan said close).** Its `symptom_if_broken` concerns A3. On a fresh clone (clean worktree at `dfbe4cb3`), `score-fidelity-cases.py --cases 6` still prints `NO reference PNG` (observed), because A3 reads the untracked full-resolution exports. Per `.claude/rules/deferred-items.md` a partly met entry stays `deferred` and gets a `notes` line; that note records the gate half as resolved.
10. **Baseline test is case-agnostic.** `test_baseline_covers_every_case` asserts baseline cases == gated cases (every case with a `reference_1x.png`) and margin > 0, so CE-3/CE-5 can add cases without editing it.

## Additional validation

- CI's Test-step command `pytest -m "not integration" --cov=app --cov-fail-under=88`: 8696 passed, total coverage 89.60% (observed; `fidelity_gate.py` 76%, the uncovered lines are the browser path).
- `make fidelity-gate` from a clean worktree without local secrets (what CI sees): 1 passed (observed). `ci.yml` has no workflow-level `env:` block.

## Issues encountered

- **Pending CI (Task 13 cross-host, done check (a)).** Push the draft PR, download `fidelity-gate-scores`, and diff it against `data/debug/fidelity_baseline.json`. If the max delta is ≤ 0.0025, keep the stamp. Otherwise run `make fidelity-restamp REASON="CE-1 stamp from CI run <id>" FROM=<artifact>/scores.json` and push. Then re-run the backend job once on the same head and update the Spread table in `docs/fidelity-gate.md`.
- **D1 recorded in this plan only.** The epic plan `converter-epic-slices.md` (branch `plan/converter-epic-slices`) and #439 still say D1 is open; update them on that branch or as a comment on #439.
- **Findings for the PR body (from the plan's spike, re-observed here):**
  - F1: Starbucks does not drop with #409 reverted.
  - F2: the #409 signal on mammut is small (0.0111 vs margin 0.005).
  - F3: two 46px mammut dividers carry no section marker (pinned under `unmarked`).
- The full-resolution originals of the case 6–10 assets are backed up at `data/debug/<c>/assets_fullres/` (gitignored). Local A3 now renders the downscaled copies.
- No migration; alembic head untouched.
- Pre-existing dirty files left alone: `app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml`, `email-hub-deploy/public/`, `.claude/{code-reviews,reports}/pr-413-*`.
