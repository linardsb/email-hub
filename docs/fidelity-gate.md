# Per-section fidelity gate (CE-1, #419)

A CI check that fails when any section of any converter case renders measurably worse than its committed baseline. Code: `app/design_sync/fidelity_gate.py`; CLI: `scripts/fidelity-gate.py`; baseline: `data/debug/fidelity_baseline.json`.

## What it measures

1. **Convert** each case in `data/debug/<case>/` (`structure.json` + `tokens.json`, committed) with the default render path.
2. **Render** the HTML in Chromium at the case's frame width (600px for cases 5, 7, 8, 10; 640px for 6 and 9), `device_scale_factor=1`, with every non-`file://` request blocked and asset srcs pointed at the committed `data/debug/<case>/assets/<node>.png`.
3. **Cut the render by section markers.** The converter wraps every flat section in `<!-- section:section_<i> --> … <!-- /section:section_<i> -->`. The render box of a section is the DOM `Range` between those two comments. `ConversionResult.section_node_ids[i]` names the Figma node the marker `section_i` wraps.
4. **Cut the design reference by the section's Figma box**: `data/debug/<case>/reference_1x.png` is the design export resized to the frame width, and the crop is the section's `x, y, width, height` minus the frame origin (minimum section x and y).
5. **Score** each pair with the colour-aware metric used by A3 (`visual_scorer._color_similarity`: 1 − mean CIEDE2000 ΔE / 100), after resizing the render crop to the design crop's size.

Scores are keyed by Figma node id, so a grouping change that renumbers markers does not move a baseline onto a different section. A section lost or added fails the gate until it is re-stamped. Layout sections that carry no marker (band-grouping spacers, two mammut dividers) are listed under `unmarked` in the baseline, and `test_unmarked_set_matches_baseline` fails when that set changes.

**Not comparable with A3.** A3 (`scripts/score-fidelity-cases.py`) scores full-resolution references with bands at design-y fractions. The gate uses 1x references and render-measured boxes. Never mix the two sets of numbers.

## Pinned environment

Check and re-stamp both run in `mcr.microsoft.com/playwright/python:v<version>-noble`, where `<version>` is the Playwright version locked in `uv.lock` (the Makefile reads it). The image ships the Chromium build that Playwright release drives, so a Playwright bump changes the image too; if rendering changed, the gate fails on that PR and the bump re-stamps. The baseline records the image and Playwright version it was stamped with.

- `make fidelity-gate`: the check. Runs as a step of the CI `backend` job and as a prerequisite of `make check-full`. Writes `.tmpscratch/fidelity-gate/scores.json` (uploaded by CI as the `fidelity-gate-scores` artifact).
- `make fidelity-restamp REASON="..."`: rewrites the baseline. `CASES="5 6"` limits it to some cases; `FROM=path/scores.json` stamps from a scores file written by another pinned run (e.g. a CI artifact) instead of rendering locally. A blank reason and any run outside the pinned image are refused.
- The pytest test `test_fidelity_gate_holds_baseline` (marker `fidelity_gate`) is skipped everywhere except inside the image.

## The rule

A section **fails** when `baseline − now > margin`, or when it is lost (absent now, or now skipped) or new. A section that rises by more than the margin is reported as `improved` and passes; lock the gain in with a re-stamp.

**Margin: 0.005** (decided at planning, before any implementation proof ran).

- 0.005 is a mean CIEDE2000 change of 0.5 per pixel over the section (derived: score = 1 − mean ΔE / 100), below the 2.3 just-noticeable difference.
- Same-host spread is 0.0000 (observed, below), so the margin only has to absorb cross-host variation.
- It is about half the smallest real regression seen in the spike (0.0106, mammut social with #409 reverted). Disclosure: the value was chosen after that signal was observed.

## Baseline at stamp (observed, `make fidelity-restamp REASON="CE-1 initial baseline"`, 2026-09-30, Playwright 1.63.0 image)

| case | design | frame | sections | min | median | unmarked |
|---|---|---|---|---|---|---|
| 5 | maap-kask | 600 | 15 | 0.6556 | 0.9875 | 0 |
| 6 | starbucks-pumpkin-spice | 640 | 9 | 0.5660 | 0.9675 | 0 |
| 7 | lego-insiders-halloween | 600 | 16 | 0.8207 | 0.9257 | 5 spacers |
| 8 | performance-reimagined | 600 | 11 | 0.8839 | 0.9252 | 0 |
| 9 | slate-newsletter | 640 | 10 | 0.3147 | 0.9445 | 1 spacer |
| 10 | mammut-duvet-day | 600 | 15 | 0.0020 | 0.9125 | 2 dividers |

Low values are real converter defects, not crop errors: mammut's dark footer and 40px black bands render white (crop pairs checked with `scripts/fidelity-gate.py check --dump-crops`). The Lego reference is 40px taller than the section extent (3223 vs 3183); the trailing frame area is never scored.

## Spread

| run | where | head | sections | max abs delta vs baseline |
|---|---|---|---|---|
| 1 | local Docker (linux/amd64), `make fidelity-gate` | `d3040239` | 76 | 0.0000 (observed) |
| 2 | same, second run | `d3040239` | 76 | 0.0000 (observed) |
| CI 1 | GitHub `ubuntu-24.04` runner, PR #446 run 36763777392 (`fidelity-gate-scores` artifact) | `6ed747e6` (merge ref `a3d2f9c`) | 76 | 0.0000, no lost or new section (observed) |
| CI 2 | same runner, PR #446 run 36768480060 attempt 1 (after rebase onto #447) | `17665639` | 76 | 0.0000 (observed) |
| CI 3 | same run, attempt 2 (backend job re-run, same head) | `17665639` | 76 | 0.0000 vs baseline and vs attempt 1 (observed; done check (a)) |

**Cross-host rule.** If the CI-vs-local max per-section delta is ≤ 0.0025 (half the margin), the local stamp stays. If larger, the baseline is re-stamped from the CI artifact (`make fidelity-restamp REASON="CE-1 stamp from CI run <id>" FROM=<artifact>/scores.json`), and CI-vs-CI spread (two runs on one head) is the figure that matters; local `make fidelity-gate` is then a preview. **In force: the local stamp** (CI-vs-local max delta 0.0000 ≤ 0.0025, observed on run 36763777392).

## Proofs

### (b) Sensitivity: #409 reverted

Worktree at `d3040239` with `git revert -n 789b712f` (all 17 code and data paths of #409, not only `_fills_social`; `.agents/deferred-items.json` restored to HEAD to clear the conflict), checked against the committed baseline in the pinned image (observed):

| case | node | baseline | now | delta | status |
|---|---|---|---|---|---|
| 10 | `2833:1270` (mammut social) | 0.0454 | 0.0343 | −0.0111 | **drop → FAIL** |
| 6 | `2833:1470` | 0.9629 | 0.9711 | +0.0082 | improved |
| 8 | `2833:2348` | 0.9130 | 0.9480 | +0.0350 | improved |
| 9 | `2833:2149` | 0.9445 | 0.9499 | +0.0054 | improved |

No section was lost or new; every other section was within the margin. The gate fails on a real drop, not a re-keying. Starbucks does not fall below baseline with the revert (it scores higher), so only the mammut half of the ticket's "Starbucks or mammut" expectation holds.

### (c) Stability: a height-only change

Worktree at `d3040239` with `_SMALL_DECORATION_MAX_PX = 0.0` (`app/design_sync/figma/layout_analyzer.py`), which stops the small-decoration icon cap and changes section heights. "Unchanged" = byte-identical marker HTML between HEAD and the mutation (observed):

| case | changed sections (gate delta) | unchanged | gate max abs delta, unchanged | A3 design-y band max abs delta, same unchanged sections |
|---|---|---|---|---|
| 5 | 0 | 15 | 0.0000 | 0.0000 |
| 6 | 0 | 9 | 0.0000 | 0.0000 |
| 7 | 5 (−0.0015 … +0.0014) | 11 | 0.0000 | 0.1462 |
| 8 | 1 (`2833:2258` −0.1510) | 10 | 0.0000 | 0.1329 |
| 9 | 2 (−0.0027, −0.0011) | 8 | 0.0000 | 0.0185 |
| 10 | 3 (−0.0886, −0.0892, −0.0794) | 12 | 0.0000 | 0.1916 |

All 65 unchanged sections stay at 0.0000 on the gate while the A3 bands over the same sections swing by up to 0.19 (A3 measured with `score_case_fidelity` against the same 1x reference, same image). The gate registers height changes only in the sections that changed.

## Re-stamping

`make fidelity-restamp REASON="<why>"` is legitimate when:

- a section improved and the gain should be locked in;
- an intended converter change moves a section's score, lost or added sections included (state the ticket and the reason for each moved section in the PR);
- a new case is added (see below), or the Playwright version changes.

Each stamp appends `{date, commit, reason, cases}` to `stamps`. `commit` is the host HEAD when the stamp ran; a stamp made on a branch commit that is later squashed names a pre-squash SHA.

## Adding a case (CE-3, CE-5)

1. Commit `data/debug/<case>/structure.json`, `tokens.json` and `manifest.yaml`.
2. Write `data/debug/<case>/reference_1x.png` at frame width (the `scripts/prepare-fidelity-fixtures.py` recipe) and commit the referenced assets (≤ 600px wide), allowlisted per file in `.gitignore`.
3. `make fidelity-restamp REASON="add case <case>" CASES="<case>"`. Until then the check reports its sections as `new` and fails.

## Fixture preparation

`scripts/prepare-fidelity-fixtures.py` (one-shot, needs the untracked design exports) wrote the six references and downscaled the 71 referenced assets of cases 6–10 to ≤ 600px. The full-resolution originals stay at `data/debug/<case>/assets_fullres/` (gitignored); A3 now renders the downscaled copies; for a full-resolution A3 comparison, copy the originals over `assets/` for that run and restore the committed files afterwards with `git checkout -- data/debug`.
