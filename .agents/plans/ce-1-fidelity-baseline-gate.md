# Feature: per-section fidelity baseline gate (CE-1, #419)

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay attention to the names of existing utils, types and models, and import from the right files.

**D1 = yes** (user, 2026-09-30, at `/piv-implement`). Execution started on `feat/ce-1-fidelity-gate`.

Base: origin/main `31598a90` (observed: `git fetch` 2026-09-30). All `file:line` refs below were read at that head.

**One-pass confidence: 9/10.** Every design risk was measured in a spike (below) or has a pre-decided branch. The remaining point is the CI-runner render delta, which cannot be measured before a push; Task 13 handles either outcome without a user decision.

## Spike evidence (pre-implementation, observed 2026-09-30)

A throwaway prototype of the gate was run in the pinned image before this plan was finalised, so the plan's risky assumptions are measured, not assumed. Code: `.tmpscratch/ce1/proto.py` (scorer), `run.sh` (container runner), `diff.py` (section comparison). The directory is gitignored (`.gitignore:205`) and stays on this machine as the reference implementation for Tasks 6–9. Outputs: `.tmpscratch/ce1/{run1,run2,revert409,g11}.json`. The prototype gets the flat node-id list by wrapping `component_matcher.match_all`; the shipped code uses the Task 1 field instead.

| # | Question | Result (observed) |
|---|---|---|
| E1 | Same-host run-to-run spread | two container runs, 76 scored sections (15+9+16+11+10+15), max per-section abs delta = **0.0000** |
| E2 | Marker structure | every case: no nesting (max depth 1); markers = flat sections (15/9/16/11/10/15); `match.matches[i].section_idx == i` asserted true |
| E3 | Layout sections without a marker | case 7: 5 spacers; case 9: 1 spacer; case 10: **2 dividers** (`2833:1248`, `2833:1259`, 46px tall each); cases 5, 6, 8: none |
| E4 | Proof (b), full #409 revert | no lost or new section in any case. mammut social `2833:1270`: **−0.0106**. Starbucks social `2833:1470` +0.0082 and `2833:1475` +0.0039, slate social `2833:2149` +0.0055, performance social `2833:2348` +0.0350 (the revert scores higher on these). All 71 unchanged-HTML sections: 0.0000 (derived count: 76 − 5 changed) |
| E5 | Proof (c), `_SMALL_DECORATION_MAX_PX = 0.0` | 11 sections changed HTML (cases 7, 8, 9, 10). All 65 unchanged-HTML sections: max abs delta **0.0000**, although their render position moved by up to 693px (case 10) and 536px (case 8) |
| E6 | Score range at HEAD | per-case min/median: 5: 0.656/0.988, 6: 0.566/0.968, 7: 0.821/0.926, 8: 0.884/0.925, 9: 0.315/0.944, 10: 0.055/0.913. The low values are real converter defects, not crop errors (e.g. mammut social: design 370px tall, render 191px) |
| E7 | Revert mechanics | `git revert -n 789b712f` **conflicts** in `.agents/deferred-items.json` only (the scout had said clean). Resolve with `git restore --source=HEAD --staged --worktree .agents/deferred-items.json`; 17 code/data paths stay reverted |
| E8 | Container | `pip install uv==0.9.18` works in the image (Python 3.12.3). No local secrets file is needed: conversion ran in a fresh worktree without one. Full six-case run about 75 s on the local Docker host (Ubuntu 24.04, 4 CPU) |

Findings that change the ticket's expectations (report them in the PR body):

- **F1.** Starbucks does **not** fall below baseline when #409 is reverted; by this metric the revert scores higher on Starbucks, slate and performance. The done check says "Starbucks **or** mammut", and mammut satisfies it. The brief's "wrong if" names both, so its Starbucks half is contradicted by observation.
- **F2.** The #409 signal on mammut is small (0.0106). The margin must be well below it; see Task 13.
- **F3.** Two 46px mammut dividers have no section marker, so their pixels are never scored as sections. Logged here, not fixed (a converter question for CE-6/CE-16); the baseline pins the unmarked set so any change to it forces a re-stamp.

## Feature Description

A CI gate that renders every converter case in a pinned Chromium, cuts the render into sections by the converter's own section markers, scores each section against a committed design reference with the existing colour-aware metric, and fails when any section drops more than a set margin below its own committed baseline. A make target re-stamps the baseline with a required reason. The gate replaces "someone ran A3 locally and eyeballed it" with a per-section number that every later converter ticket (CE-3 … CE-19) must hold or explicitly re-stamp.

## User Story

As the converter maintainer
I want a CI check that fails when any section of any fixture renders measurably worse than its recorded baseline
So that styling regressions (colour, padding, widths, buttons) are caught on the PR that causes them, and every improvement is locked in by a re-stamp with a stated reason.

## Problem Statement

- A3 (`scripts/score-fidelity-cases.py`) is local-only: five of six reference PNGs and the assets of cases 6–10 are untracked (`.gitignore:138`), so CI can score only case 5, and only as an advisory number (`app/design_sync/fidelity_case_scorer.py:1-33`).
- `score_fidelity` slices both images at the same design-y band (`app/design_sync/visual_scorer.py:179-196`). Any vertical redistribution (an icon shrinks, a row grows) moves every later band onto the wrong content, so per-section scores jitter both ways on unchanged sections (G11 item 2, `60c98bc6`/#365, observed in memory note `reference_a3_scorer_section_instability`).
- CI's backend job has no browser (`.github/workflows/ci.yml:22-58`); only the e2e job installs Chromium (`ci.yml:367-368`).
- `regression_runner.collect_metrics` reports two metrics hardcoded to 1.0 (`app/design_sync/tests/regression_runner.py:121`, `:136`) that inflate `overall_score` by 0.40 (derived: weights 0.25 + 0.15 at `:139-145`).

## Solution Statement

1. **Section-id slicing.** The converter wraps each rendered section in `<!-- section:section_<idx> --> … <!-- /section:section_<idx> -->` (`component_renderer.py:2401-2403`). `idx` indexes the post-grouping `flat_sections` list (`converter_service.py:705-722`), not `layout.sections`. Marker structure (observed, `scratchpad/probe2.py` at `31598a90`): **no marker is nested in another in any case**; top-level markers per case 5–10 = 15/9/16/11/10/15 against 15/9/21/11/11/17 layout sections; case 6 emits `section_3` before `section_2`. Repeating-group and peel-row members each carry their own marker, and the group/peel wrappers carry none (derived from the counts: markers = layout sections − absorbed spacers, with no nesting; Task 2 asserts it). The layout sections without a marker are band-grouping absorbed spacers (case 7: `absorbed=1+3+1` in the `sibling.wrapper_band_grouped` log = 21 − 16, observed; cases 9/10 confirmed in Task 2). Add one additive field, `ConversionResult.section_node_ids: tuple[str, ...]` (Figma node id per flat index, so marker `section_i` → `section_node_ids[i]`). HTML bytes do not change.
2. **Peel-row members sit side by side** (cases 5 and 6, 6 members each, observed: e.g. case 6 `2833:1455/1460/1465/1470` at x −1252/−1098/−944/−790, same y). Crops therefore use x **and** y. **Render crop** = the DOM `Range` between the open and close comment nodes (`range.getBoundingClientRect()`: left, top, width, height, plus scroll offsets), measured in Playwright. **Design crop** = the section's own box: `x − frame_x0`, `y − frame_y0`, `width`, `height`, where `frame_x0`/`frame_y0` are the minimum `x_position`/`y_position` over the case's sections (observed: equals the frame's left edge in cases 5, 6, 7; `fidelity_case_scorer._origin_correct` `:75-88` does the y half). Resize the render crop to the design crop's size, then score with the existing `_color_similarity` (`visual_scorer.py:104-116`).
3. **Baseline key** = the section's Figma `node_id` (stable when grouping renumbers `idx`). The marker id is stored for display only.
4. **References and renders at 1x frame width** (user decision 2026-09-30): 600px for cases 5, 7, 8, 10; 640px for 6 and 9. The render viewport equals the frame width, `device_scale_factor=1`.
5. **Pinned environment.** Both the CI step and the local re-stamp run inside `mcr.microsoft.com/playwright/python:v1.61.0-noble` (Playwright 1.61.0 = `uv.lock:3581-3589`), via one `make` target. A baseline stamped on macOS fonts would fail on the first Ubuntu run.
6. **Assets committed** (user decision): the node-keyed PNGs every case's current output references, downscaled to ≤ 600px wide, allowlisted per file in `.gitignore` as case 5 already is (`.gitignore:147-156`).
7. **Lego included** (user decision): its untracked reference (600×3223, observed) and its 23 assets are committed, so all six cases are gated.

## Out of Scope / Non-Goals

- Not changing converter HTML output. The only converter-module change is the additive `section_node_ids` field; `expected.html`, `ladder_snapshot.json` and the snapshot tests stay byte-identical.
- Not changing `score_fidelity`'s signature or behaviour (the live `fidelity_service` and `test_fidelity_case_scorer.py:73-92` call it). The gate adds a separate entry point.
- Not changing `scripts/score-fidelity-cases.py` scoring code. Gate scores and A3 scores are never mixed (ticket "Comparability"). Caveat: Task 4 replaces the local full-resolution assets of cases 6–10 with ≤ 600px copies, so a local A3 render after this ticket can differ slightly from one before it for asset-level reasons (images display at ≤ 640 CSS px at DPR 1, so the expected difference is small). The originals are kept under `data/debug/<c>/assets_fullres/` (gitignored) so an A3 run can restore them.
- Not making the A2 section-count gate strict (`phase-53-a2-advisory-section-gate`, carried forward; see ledger table).
- Not adding reframe (CE-3 #421) or held-out cases (CE-5 #423). The baseline schema must accept new cases without code changes.
- Not adding a new CI job or touching branch protection. The gate is a step in the existing `backend` job, so `ready.needs` (`ci.yml:521`) already covers it.
- Not scoring the tree-bridge path (`DESIGN_SYNC__TREE_BRIDGE_ENABLED`, off by default). The gate runs the default render path only.

## Feature Metadata

**Feature Type**: New Capability (measurement)
**Estimated Complexity**: High
**Primary Systems Affected**: `app/design_sync/` (converter result, new gate module), `data/debug/` fixtures, `.github/workflows/ci.yml`, `Makefile`, `.gitignore`
**Dependencies**: Playwright 1.61.0 (already in `pyproject.toml:104`), Docker on the CI runner and locally (local server is `linux/amd64`, observed `docker version`), `mcr.microsoft.com/playwright/python:v1.61.0-noble`

## Related Work

**Implements**: #419 (CE-1) · **Epic**: #439; slices and inherited decisions in `.agents/plans/converter-epic-slices.md:68-84`

**Back-references**:

- `.agents/plans/converter-epic-slices.md` - Why: CE-1 scope, conventions table, comparability rule, "wrong if" line.
- `.agents/plans/53-g11-residual-ingest-classes-sweep.md` - Why: the icon-shrink change whose design-y jitter motivates section-id slicing.
- `.claude/skills/converter-fix/SKILL.md:66-101` - Why: snapshot byte-identity and A3 jitter rule that this ticket's converter-field change must pass.

**Forward-references**:

- CE-3 #421 re-stamps via `make fidelity-restamp`; CE-5 #423 adds a `held_out` flag to baseline cases; every converter ticket after merge runs the gate.

## Deferred Items Touching This Plan

Grepped `.agents/deferred-items.json` 2026-09-30 for every file below plus "fidelity", "A3", "asset", "Chromium" (observed, scout pass).

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `phase-53.7-asset-reexport-prerequisite` | assets for fixtures are local-only | **close** | closes_when "per-case assets committed for every reported fixture": Task 4 commits assets for 6–10 (5 already committed). Apply the Close step of `.claude/skills/deferred-items/SKILL.md` with `closed_commit: pending`. |
| `phase-53-a2-advisory-section-gate` | `regression_runner.py`, `test_converter_data_regression.py` | carry forward | Epic asked for a decision at planning: CE-1 is a pixel gate; making A2 strict needs D3 convergence on 5/6/10, which this ticket does not touch. |
| `phase-53g-g9-img-not-rescaled-with-column` | mentions Chromium rendering | avoid | Converter bug in column rescalers (CE-16 #434); the gate will measure it, not fix it. |
| `phase-53g-band-item-spacing-defaults-vs-wrapper-padding` | mentions A3 | avoid | Converter spacing (CE-6/CE-16). |
| `phase-53f-decorative-image-flag` | mentions A3; G11 constant used in proof (c) | avoid | Proof (c) mutates `_SMALL_DECORATION_MAX_PX` only in a throwaway worktree; nothing lands. |
| `phase-53-d3-mammut-below-candidate-undercount`, `phase-53g6-card-tree-path-text-only`, `phase-54.1-llm-judge-calibration-uncertified`, `tech-debt-19-*`, `tech-debt-squawk-python-migrations` | keyword noise | avoid | Not touched by this plan. |

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/visual_scorer.py:104-116` - `_color_similarity`, the metric to reuse unchanged; `:31` `_MIN_SECTION_HEIGHT_PX = 8`.
- `app/design_sync/fidelity_case_scorer.py:75-88` (`_origin_correct`), `:164-186` (`_ASSET_SRC_RE`, `_rewrite_asset_srcs`), `:193-242` (`render_case_png`, the Playwright recipe to mirror).
- `app/design_sync/converter_service.py:134-145` (`ConversionResult`), `:670-727` (`_match_phase`, `flat_sections`), `:840-935` (render loop: group branch `:854-885`, peel-row branch `:887-930`, then single-section path below `:930`).
- `app/design_sync/component_renderer.py:276-284` (`RenderedSection`), `:2396-2410` (`_add_annotations`, marker text).
- `app/design_sync/tests/regression_runner.py:48-61` (`run_case_conversion`), `:95-154` (`CaseMetrics`, `collect_metrics`).
- `app/design_sync/tests/test_fidelity_case_scorer.py:60-92` - skipif-on-missing-fixture pattern and the "corrupted render scores lower" test shape.
- `app/design_sync/tests/test_converter_data_regression.py:233`, `:266` - `test_ladder_no_drift`; must stay green.
- `app/design_sync/figma/layout_analyzer.py:1491`, `:1631-1640` - `_SMALL_DECORATION_MAX_PX` and the `is_small_decoration` check (proof (c) mutation).
- `.github/workflows/ci.yml:22-58` (backend job), `:367-368` (existing Chromium install), `:519-557` (`ready`).
- `Makefile:85-86` (`test` excludes `visual_regression`), `:163-164` (`snapshot-visual`), `:182` (`check-full`).
- `.gitignore:130-156` - `data/debug/*/*` ignore and the case-5 per-file asset allowlist to mirror.
- `pyproject.toml:291-297` - pytest markers.

### New Files to Create

- `app/design_sync/fidelity_gate.py` - baseline model, render-with-section-boxes, crop scoring, compare, stamp.
- `app/design_sync/tests/test_fidelity_gate.py` - unit tests (always run) + the pinned-env gate test (`fidelity_gate` marker).
- `scripts/fidelity-gate.py` - CLI: `check` (default) and `restamp --reason "<text>"`.
- `scripts/prepare-fidelity-fixtures.py` - one-shot: downscale references and assets into `data/debug/<case>/`, print the `.gitignore` allowlist lines.
- `data/debug/fidelity_baseline.json` - the baseline.
- `data/debug/{5,6,7,8,9,10}/reference_1x.png` - design references at 1x frame width.
- `data/debug/{6,7,8,9,10}/assets/<node>.png` - 71 downscaled assets (observed count: 8 + 23 + 10 + 13 + 17 from `expected.html` srcs, all present on disk).
- `docs/fidelity-gate.md` - margin, how it was chosen, observed spread, proofs (b) and (c), re-stamp procedure.

### Patterns to Follow

- **Logging**: `get_logger(__name__)` from `app.core.logging`; event names `design_sync.<noun>_<verb>` (`fidelity_case_scorer.py:141`, `design_sync.case_fidelity_scored`). New events: `design_sync.fidelity_gate_scored`, `design_sync.fidelity_baseline_stamped`.
- **Dataclasses**: `@dataclass(frozen=True)` for results (`visual_scorer.py:44-64`); baseline file schema as a Pydantic model (mirror `app/design_sync/tests/manifest_schema.py` `CaseManifest`) so a malformed baseline fails loudly.
- **Images**: open with `safe_image_open` from `app.shared.imaging` (`visual_scorer.py:27`), resize with `Image.Resampling.LANCZOS` (`fidelity_case_scorer.py:129`).
- **Playwright**: lazy import inside the async function (`fidelity_case_scorer.py:217`); temp `file://` document, not `set_content` (`:233-236`, Chromium refuses `file://` subresources otherwise).
- **Scripts**: `REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))` + `# noqa: E402` imports (`scripts/score-fidelity-cases.py:25-31`).
- **Lint**: `print` in scripts is fine (`scripts/` pattern); in `app/` use the logger or `# noqa: T201` as `regression_runner.py:170` does. Pyright header pragmas for numpy/PIL untyped values mirror `visual_scorer.py:1-2`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (converter field, stub removal)

Additive `section_node_ids` on `ConversionResult`; delete the two stub metrics. Both are pure Python and testable without a browser.

### Phase 2: Fixtures

**Independent of:** Phase 1 (data only). Reference PNGs and assets downscaled and allowlisted.

### Phase 3: Gate core

**Depends on:** Phases 1 and 2. Render with section boxes, crop, score, compare, stamp.

### Phase 4: Pinned environment, CI, make targets

**Depends on:** Phase 3.

### Phase 5: Margin, proofs, report, ledger

**Depends on:** Phase 4 (proofs run in the pinned image).

---

## STEP-BY-STEP TASKS

### Task 0: BRANCH

- **IMPLEMENT**: after D1 = yes: `git fetch && git switch -c feat/ce-1-fidelity-gate origin/main`. Leave the dirty `app/ai/agents/*/skill-versions.yaml`, `email-hub-deploy/public/` and `.claude/{code-reviews,reports}/pr-413-*` alone.
- **VALIDATE**: `git status --short` shows only the pre-existing dirty files.

### Task 1: UPDATE `app/design_sync/converter_service.py` — `section_node_ids`

- **IMPLEMENT**: add `section_node_ids: tuple[str, ...] = ()` to `ConversionResult` (`:134-145`). Where the default render path holds the `MatchPhase` (`match.matches`, built at `:715-727` and consumed in the render loop `:854`), set `section_node_ids=tuple(m.section.node_id for m in match.matches)` on every `ConversionResult(...)` that path returns (`:488`, `:545`; confirm which one carries the rendered HTML). Other constructors (tree bridge, empty results) keep the default.
- **PATTERN**: dataclass defaults at `:140-145`.
- **GOTCHA**: do not change marker text or any HTML. `match.matches[i].section_idx == i` by construction (`component_matcher.py:141-162`, `enumerate(sections)`); Task 2 asserts it rather than trusting it.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py app/design_sync/tests/test_snapshot_regression.py -q` green and `git status --short data/debug` shows no tracked change (snapshot byte-identity, converter-fix `SKILL.md:66-80`).
- **SATISFIES**: AC 2.

### Task 2: ADD test for `section_node_ids` in `app/design_sync/tests/test_fidelity_gate.py`

- **IMPLEMENT**: parametrised over cases 5–10 (skip when `structure.json` is missing, mirror `test_fidelity_case_scorer.py:60`): `run_case_conversion(case)`; parse markers with `re.finditer(r"<!-- (/?)section:section_(\d+) -->")` and a depth counter. Assert: (1) no marker is nested (depth never exceeds 1); (2) the set of marker indices == `set(range(len(result.section_node_ids)))`; (3) every id in `section_node_ids` is a `layout.sections` node id and appears once; (4) the layout sections **not** in `section_node_ids` equal the committed baseline's `unmarked` map for that case (E3: 5 spacers in case 7, 1 spacer in case 9, 2 dividers in case 10, none elsewhere). A change in that set fails with "unmarked set changed: re-stamp needed", so newly dropped content cannot go unnoticed.
- **GOTCHA**: real converter output on committed fixtures, not synthetic HTML. (1) pins the observed no-nesting fact; if a later ticket introduces nesting, this test forces the gate to be revisited instead of silently double-scoring.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_fidelity_gate.py -k section_node_ids -q`; then temporarily reverse the tuple in Task 1 and confirm assertion (3) or the Task 8 box mapping goes red (record which).
- **SATISFIES**: AC 2.

### Task 2b: RUN full-corpus A3 before/after Task 1 (CLAUDE.md "converter changes carry full-corpus A3")

- **IMPLEMENT**: with the local untracked references and full-resolution assets still in place (before Task 4), run `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` with Task 1 stashed, then applied (recipe `.claude/skills/converter-fix/references/a3-scoring.md`). Six rows each.
- **GOTCHA**: the output is byte-identical, so every figure must match exactly. Any difference means Task 1 changed output: stop.
- **VALIDATE**: before/after table (observed) pasted into the report and PR body.
- **SATISFIES**: CLAUDE.md working principle; AC 2.

### Task 3: REMOVE stub metrics — `app/design_sync/tests/regression_runner.py`

- **IMPLEMENT**: delete `component_match_accuracy` (`:100`) and `token_compliance` (`:103`) fields, their computations (`:120-121`, `:135-136`) and kwargs (`:149`, `:152`). Reweight: `overall = (section_acc * 0.25 + sfr * 0.15 + content_cov * 0.20) / 0.60` (derived: the three surviving weights sum to 0.60; dividing keeps `overall` on 0–1).
- **GOTCHA**: only consumers are `test_converter_data_regression.py:433` (warning text) and `:451` (`>= 0.0`), per scout grep; re-grep `component_match_accuracy|token_compliance` across `app/ scripts/ tests/ cms/ docs/` before deleting. `report.json` files are untracked (`.gitignore:138`), nothing to regenerate.
- **VALIDATE**: `grep -rn "component_match_accuracy\|token_compliance" app scripts tests` returns nothing; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -q` green.
- **SATISFIES**: AC 6.

### Task 4: CREATE `scripts/prepare-fidelity-fixtures.py` and the fixtures

- **IMPLEMENT**:
  - Frame width per case = max `EmailSection.width` over `layout.sections` (observed 600/640/600/600/640/600 for cases 5–10, `geom.py` probe). Reference source: `email-templates/training_HTML/for_converter_engine/<design>/*ual_design.png` (glob handles Lego's `viaual_` typo, `score-fidelity-cases.py:36`). Resize to width = frame width (maap 1200→600, Starbucks 960→640, performance 1200→600, slate 1280→640, mammut 1200→600, Lego unchanged), LANCZOS, `save(optimize=True)` → `data/debug/<case>/reference_1x.png`.
  - Assets: the node ids the **current** converter output references (`_ASSET_SRC_RE` over `run_case_conversion(case).html`, not `expected.html`), for cases 6–10. Back up originals first to a durable gitignored path (`cp -R data/debug/<c>/assets data/debug/<c>/assets_fullres`; covered by `data/debug/*/*`, `.gitignore:138`; not the scratchpad, which is session-scoped and the originals cannot be re-exported without the Figma token), then overwrite in place with ≤ 600px-wide PNGs (only images wider than 600 are resized: 1/1/7/4/2/4 for cases 5–10, observed). Case 5 assets are already tracked: leave them untouched.
  - Print the `.gitignore` block: `!data/debug/*/reference_1x.png`, and per case `!data/debug/<c>/assets/` + `data/debug/<c>/assets/*` + one `!…/<node>.png` line per referenced asset (mirror `.gitignore:147-156`).
- **GOTCHA**: downscaling is expected to be near-lossless for the render (every image displays at ≤ 640 CSS px at DPR 1; not measured). Unreferenced local assets (e.g. 32 on disk vs 8 referenced for case 6) must not be committed; the per-file allowlist enforces that.
- **VALIDATE**: `git add -n data/debug` lists exactly 6 references + 71 assets + no other PNG; `du -ch` of the staged PNGs recorded in the report (expected ≈ 14 MB: 6.9 MB assets observed + ≈ 7.5 MB references, derived from the 600px measurement; 640px refs are slightly larger).
- **SATISFIES**: AC 3.

### Task 5: UPDATE `.gitignore`

- **IMPLEMENT**: paste the block printed by Task 4 under the case-5 allowlist with a comment naming CE-1 #419.
- **VALIDATE**: `git check-ignore -v data/debug/6/reference_1x.png` exits 1 (not ignored); `git check-ignore data/debug/6/raw_figma.json` still ignored.
- **SATISFIES**: AC 3.

### Task 6: CREATE `app/design_sync/fidelity_gate.py` — model and scoring (no browser)

- **IMPLEMENT**:
  - Pydantic `FidelityBaseline`: `schema_version: int = 1`, `margin: float`, `environment: {image: str, playwright: str}`, `stamps: list[{date, commit, reason, cases}]` (append-only history), `cases: dict[str, CaseBaseline]`. `CaseBaseline`: `design: str`, `frame_width: int`, `reference: str` (repo-relative path), `sections: dict[str, SectionBaseline]` keyed by node id, `skipped: dict[str, str]` (node id → reason, e.g. "design crop < 8px"), `unmarked: dict[str, str]` (layout node id → section type, the absorbed spacers from Task 2). `SectionBaseline`: `marker: str`, `score: float`, `design_box: tuple[int, int, int, int]` (x, y, w, h).
  - `design_box(section, frame_x0, frame_y0) -> tuple[int, int, int, int]`: `(x − frame_x0, y − frame_y0, width, height)`, rounded; `frame_x0`/`frame_y0` = min `x_position`/`y_position` over the case's sections. Scale is 1.0 because references are at 1x frame width. Clip to the reference bounds.
  - `score_section(reference_rgb, rendered_rgb, design_box, render_box) -> float`: crop both by (x, y, w, h), resize render crop to the design crop's (w, h) with LANCZOS, `_color_similarity`, round to 4 dp. Import `_color_similarity` from `visual_scorer` (a private import across one package; add a public alias `color_similarity = _color_similarity` in `visual_scorer.py` if pyright `reportPrivateUsage` flags it).
  - `compare(baseline, scores) -> GateReport`: per section `drop = baseline.score - now`; **fail** when `drop > margin`; **fail** when a baseline id is absent now ("section lost or re-keyed: re-stamp needed"); **fail** when a new id appears ("new section: re-stamp needed"); **improved** (pass, printed) when `now - baseline > margin`. Report lists every section with baseline, now, delta.
- **GOTCHA**: sections with design crop < `_MIN_SECTION_HEIGHT_PX` or a zero-height render box go to `skipped` with the reason, never silently dropped. The render box can have zero height when a section renders empty; record that as its own reason.
- **VALIDATE**: unit tests in Task 7.
- **SATISFIES**: AC 1, AC 2.

### Task 7: ADD unit tests (no browser) in `test_fidelity_gate.py`

- **IMPLEMENT**: (a) `compare` fails on drop > margin, passes on drop == margin, fails on lost id, fails on new id, reports improved; (b) `design_box` for the case-6 peel-row members `2833:1455/1460/1465/1470` gives four side-by-side boxes, x ascending, same y, all inside `[0, frame_width)`; and for every case every box lies inside the frame (checks the `frame_x0` assumption); (c) `score_section` on the committed case-5 reference against itself = 1.0 and against an inverted copy < 0.5 (mirror `test_fidelity_case_scorer.py:92`); (d) baseline JSON round-trips and rejects a missing `reason` in a stamp; (e) every `reference` path in the committed baseline exists and its width equals `frame_width`; (f) every asset src in the current output of every baselined case has a committed file (fails listing the missing node ids).
- **GOTCHA**: images come from committed fixtures, never generated HTML.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_fidelity_gate.py -m "not fidelity_gate" -q`.
- **SATISFIES**: AC 1, AC 3.

### Task 8: ADD render with section boxes — `fidelity_gate.py`

- **IMPLEMENT**: `async def render_case_sections(case_dir, width) -> RenderedCase` (png bytes, `boxes: dict[marker, (left, top, width, height)]`, `result: ConversionResult`). Mirror `render_case_png` (`fidelity_case_scorer.py:193-242`) with: viewport `{"width": width, "height": 1000}`, `device_scale_factor=1`; `page.route("**/*", …)` aborting every request whose URL is not `file://`; after `goto(..., wait_until="networkidle")` await `document.fonts.ready`; then `page.evaluate` a script that walks comment nodes (`document.createTreeWalker(document, NodeFilter.SHOW_COMMENT)`), pairs `section:X` with `/section:X`, keeps pairs not nested in another pair, and returns `range.setStartAfter(open); range.setEndBefore(close); getBoundingClientRect()` left/top/width/height plus `window.scrollX`/`scrollY` (page coordinates for the full-page screenshot). Screenshot `full_page=True`.
- **GOTCHA**: comment ranges inside `<!--[if mso]>` blocks are comments themselves and never match the `section:` pattern; keep the regex anchored (`^\s*section:(section_\d+)\s*$`). Do not change `render_case_png`: it regenerates the committed `rendered_w600.png` (`fidelity_case_scorer.py:26-28`).
- **VALIDATE**: in the pinned image (Task 11), `{int(k.split('_')[1]) for k in boxes} == set(range(len(result.section_node_ids)))` for all six cases, every box has width and height > 0, and the case-6 peel members' boxes are side by side (same top ±2px, left ascending).
- **SATISFIES**: AC 2.

### Task 9: ADD stamp and check entry points — `fidelity_gate.py` + `scripts/fidelity-gate.py`

- **IMPLEMENT**: `score_case(case) -> dict[node_id, score]` (render, map `section_i` → `section_node_ids[i]`, score each). Keep the browser-only code (render + `page.evaluate`) small: it never runs in the CI Test step, which enforces `--cov-fail-under=88` (`ci.yml:53`); the scoring, compare and stamp logic it calls is unit-tested. `--dump-crops` writes each section's design/render crop pair to `.tmpscratch/fidelity-gate/crops/<case>/<node>.png` (used by Level 4 step 2). `check()` loads `data/debug/fidelity_baseline.json`, scores every case in it, runs `compare`, prints the table, writes `.tmpscratch/fidelity-gate/scores.json` (for spread measurement and CI artifact), exits 1 on any fail. `restamp(reason)` requires a non-empty `reason` (argparse `required=True`; reject blank), refuses to run unless `FIDELITY_GATE_ENV=pinned` (set only by the make target), rewrites `sections`/`skipped` for every case, appends a `stamps` row with `git rev-parse --short HEAD`, today's date and the reason, and prints a before/after table. `restamp --from <scores.json>` stamps from a scores file written by another pinned run (e.g. the `fidelity-gate-scores` CI artifact) instead of rendering locally; it checks that the file's `environment.image` equals the baseline's.
- **GOTCHA**: run with `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` (converter-fix `SKILL.md:95-97`) so cache hits cannot change output. `restamp --cases 5 6` re-stamps a subset and keeps the rest untouched (CE-3 needs one case).
- **VALIDATE**: `uv run python scripts/fidelity-gate.py restamp --reason ""` exits non-zero with a message; the same outside the pinned env exits non-zero naming `make fidelity-restamp`.
- **SATISFIES**: AC 4, AC 5.

### Task 10: ADD the pinned-env gate test and marker

- **IMPLEMENT**: register marker `fidelity_gate: per-section fidelity gate; runs only in the pinned Playwright image (make fidelity-gate)` in `pyproject.toml:291-297`. In `test_fidelity_gate.py`, `test_fidelity_gate_holds_baseline` (`@pytest.mark.fidelity_gate`) skips unless `os.environ.get("FIDELITY_GATE_ENV") == "pinned"`, then calls `check()` and asserts no failures, printing the report on failure.
- **GOTCHA**: CI's backend Test step runs `-m "not integration"` (`ci.yml:52-53`), so this test is collected there and must skip (the host runner is not the pinned env). `make test` also skips it; `make check-full` runs it through its `fidelity-gate` prerequisite (Task 11), which enters the pinned image.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_fidelity_gate.py -q -rs` shows the gate test as skipped with the env reason.
- **SATISFIES**: AC 1.

### Task 11: ADD make targets — `Makefile`

- **IMPLEMENT** (near `snapshot-visual`, `Makefile:163`), mirroring the proven `.tmpscratch/ce1/run.sh`:
  - `FIDELITY_IMAGE := mcr.microsoft.com/playwright/python:v1.61.0-noble`
  - `FIDELITY_RUN = docker run --rm --ipc=host -v "$(CURDIR)":/work -w /work -e UV_PROJECT_ENVIRONMENT=/work/.tmpscratch/fidelity-venv -e UV_CACHE_DIR=/work/.tmpscratch/fidelity-uvcache -e FIDELITY_GATE_ENV=pinned -e DESIGN_SYNC__SECTION_CACHE_ENABLED=false $(FIDELITY_IMAGE) bash -lc` (venv and cache under gitignored `.tmpscratch/` so repeat runs skip the install; the host `.venv` is untouched).
  - `fidelity-gate: ## Per-section fidelity gate in the pinned Playwright image` → `$(FIDELITY_RUN) "pip install -q uv==0.9.18 && uv sync --frozen -q && uv run pytest -m fidelity_gate app/design_sync/tests/test_fidelity_gate.py -v"`.
  - `fidelity-restamp: ## Re-stamp the fidelity baseline (REASON="..." required; CASES="5 6", FROM=path optional)` → `@test -n "$(REASON)" || (echo 'REASON="..." is required'; exit 1)`, then the same container running `uv run python scripts/fidelity-gate.py restamp --reason "$(REASON)" $(if $(CASES),--cases $(CASES)) $(if $(FROM),--from $(FROM))`.
  - Add `fidelity-gate` to the `check-full` prerequisites (`Makefile:182`), so the Definition of Done gate runs it locally. Docker is already required by the local stack.
- **GOTCHA**: uv install in the image observed working (E8). Files written from the container are root-owned on a Linux host; the CI runner is ephemeral, and on the local Docker host ownership maps to the user (observed: `.tmpscratch/ce1/` outputs are editable). No secrets file is needed (E8).
- **VALIDATE**: `make fidelity-restamp` without REASON fails with the message; `make fidelity-gate` runs (it fails with "no baseline" until Task 13).
- **SATISFIES**: AC 4, AC 5.

### Task 12: UPDATE `.github/workflows/ci.yml` — backend job

- **IMPLEMENT**: `runs-on: ubuntu-24.04` for `backend` (`ci.yml:24`). Add step after Test: `- name: Fidelity gate (pinned Playwright 1.61.0 image)` `run: make fidelity-gate`. Add `- uses: actions/upload-artifact@v7` (the version `ci.yml:432` already uses) with `if: always()`, path `.tmpscratch/fidelity-gate/`, name `fidelity-gate-scores` (the run-to-run spread evidence for done check (a)).
- **GOTCHA**: this is "Chromium in the backend job" via the pinned container (ticket scope 4); no host `playwright install`.
- **VALIDATE**: `actionlint .github/workflows/ci.yml` if installed, else `uv run python -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"`; the real check is the PR's CI run.
- **SATISFIES**: AC 1.

### Task 13: STAMP the baseline and confirm the margin

- **MARGIN (decided at planning, fixed): 0.005.** Written into `docs/fidelity-gate.md` and the baseline before any implementation proof runs. Basis: same-host spread is 0.0000 (E1, E5), so the margin only has to absorb cross-host variation. 0.005 is a mean CIEDE2000 change of 0.5 per pixel over a section (derived: score = 1 − mean ΔE / 100, `visual_scorer.py:41`, `:115`), below the 2.3 just-noticeable difference quoted at `visual_scorer.py:40`. It is about half the smallest real regression signal seen (E4: 0.0106). Disclosure for the report: the value was chosen after E4 was observed.
- **IMPLEMENT**: `make fidelity-restamp REASON="CE-1 initial baseline"`; `make fidelity-gate` twice (local spread, expected 0.0000 per E1); push the draft PR; download the CI `fidelity-gate-scores` artifact and diff it against the local scores with the `diff.py` logic (cross-host spread).
- **DECISION RULE (cross-host)**: if the CI-vs-local max per-section delta is ≤ 0.0025 (half the margin), keep the local stamp. If it is larger, re-stamp from CI: `make fidelity-restamp REASON="CE-1 stamp from CI run <id>" FROM=<artifact>/scores.json`, push, and confirm the next CI run passes. The baseline is then CI-stamped, and CI-vs-CI spread is what matters (done check (a)). Local `make fidelity-gate` stays a preview on that path; `docs/fidelity-gate.md` states which path is in force. Neither branch needs a user decision.
- **VALIDATE**: `docs/fidelity-gate.md` lists each run (where, head SHA, max abs delta) tagged observed; CI re-run once on the same head for done check (a).
- **SATISFIES**: AC 1, done check (a), (d).

### Task 14: RUN proof (b) — #409 revert sensitivity (re-run of E4 on the shipped code)

- **IMPLEMENT**: `git worktree add --detach ../eh-proof-b HEAD && git -C ../eh-proof-b revert -n 789b712f`; it conflicts in `.agents/deferred-items.json` only (E7): `git -C ../eh-proof-b restore --source=HEAD --staged --worktree .agents/deferred-items.json`. The revert covers all of #409's code and data paths, not only `_fills_social` (`component_matcher.py:2530`); record that. Run `scripts/fidelity-gate.py check` in the pinned image against the worktree code with the main checkout's committed fixtures (mount both, as `run.sh` does with `/proofs`).
- **PASS CONDITION**: a row with `drop > 0.005` on case 6 or 10, on a node id present before and after. Expected (E4): mammut `2833:1270` drops about 0.0106; no lost or new ids. A red caused only by lost/new ids does not count.
- **GOTCHA**: Starbucks is expected to score **higher** with the revert (E4, F1). That does not fail this proof.
- **VALIDATE**: record the rows in `docs/fidelity-gate.md`; `git worktree remove --force ../eh-proof-b`.
- **SATISFIES**: done check (b).

### Task 15: RUN proof (c) — height-only change (re-run of E5 on the shipped code)

- **IMPLEMENT**: worktree; set `_SMALL_DECORATION_MAX_PX = 0.0` (`layout_analyzer.py:1491`; the check at `:1633` then never matches, because every real image has width > 0). Run the check with `--dump-crops` and per-marker HTML capture. "Unchanged section" = byte-identical marker HTML.
- **PASS CONDITION**: every unchanged section within the margin. Expected (E5): 65 unchanged sections at 0.0000, 11 changed.
- **GOTCHA**: do not use commit `60c98bc6` (G11): it also shipped column-image and divider changes.
- **VALIDATE**: table in `docs/fidelity-gate.md`; for contrast, the design-y A3 band deltas on the same mutation (`score_case_fidelity`, same image). Remove the worktree.
- **SATISFIES**: done check (c).

### Task 16: CREATE `docs/fidelity-gate.md`

- **IMPLEMENT**: sections: what the gate measures (section-id slicing, 1x frame references, pinned image, comparability note: gate scores ≠ A3 full-res figures), the margin rule and its value, observed spread table, proofs (b) and (c), how to re-stamp (`make fidelity-restamp REASON="…"`, when a re-stamp is legitimate: an improved section, an intended change, a new case), how to add a case (CE-3/CE-5).
- **VALIDATE**: every figure tagged observed/derived/expected.
- **SATISFIES**: done check (d).

### Task 17: UPDATE `.agents/deferred-items.json`

- **IMPLEMENT**: close `phase-53.7-asset-reexport-prerequisite` (`status: closed`, `closed_commit: "pending"`, note: assets for 6–10 committed in CE-1 #419) per `.claude/skills/deferred-items/SKILL.md` Close step.
- **VALIDATE**: `uv run python -c "import json;json.load(open('.agents/deferred-items.json'))"`.
- **SATISFIES**: ledger hygiene.

### Task 18: VALIDATE the whole ticket

- **IMPLEMENT**: `make check-full` (includes `fidelity-gate` after Task 11; then `git diff` again: `make lint` rewrites files; restore `app/ai/agents/*/skill-versions.yaml` date churn from `make test`), `make fidelity-gate`, `git diff --stat origin/main...HEAD`.
- **SATISFIES**: all ACs.

---

## TESTING STRATEGY

### Unit Tests

`app/design_sync/tests/test_fidelity_gate.py`, no browser: `section_node_ids` invariants over the six real cases (Task 2), `compare` rules, crop bounds, `score_section` identity/inversion on the committed case-5 reference, baseline schema, reference width and asset completeness (Task 7). These run in `make test` and the CI Test step.

### Integration Tests

`test_fidelity_gate_holds_baseline` (`fidelity_gate` marker), pinned image only, via `make fidelity-gate` locally and the backend CI step. Its render order matches production use: convert → rewrite asset srcs → write temp file → `goto` → measure → screenshot.

### Edge Cases

| Edge case | Verified in |
|---|---|
| Repeating-group members (each carries its own marker, observed) | Task 2 (2)–(3) |
| Peel-row members side by side (cases 5, 6) | Task 7 (b), Task 8 box assertion |
| A future nested marker | Task 2 (1) fails and forces a gate revisit |
| Layout section with no marker (absorbed spacer) | Task 2 (4); listed under `unmarked` in the baseline |
| Out-of-order markers (case 6 renders `section_3` before `section_2`, observed probe) | Task 2 test (set equality, order-free), keyed by node id |
| Section renders empty (zero-height box) | Task 6 skipped reason; Task 7 (a)-style unit test |
| Design crop < 8px | Task 6 skipped reason |
| Baseline id disappears / new id appears | Task 7 (a) |
| Missing committed asset for a referenced src | Task 7 (f) |
| Re-stamp with blank reason or outside pinned env | Task 9 VALIDATE |
| Lego reference 40px taller than section extent (3223 vs 3183, observed) | Design crops use section y only; trailing frame area is never scored (documented in the report) |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync scripts` and `uv run ruff check --no-fix app/design_sync scripts`
- `uv run mypy app/` and `uv run pyright app/`

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_fidelity_gate.py app/design_sync/tests/test_fidelity_case_scorer.py app/design_sync/tests/test_converter_data_regression.py -q`
- `make snapshot-test` (byte-identity of converter output after Task 1)

### Level 3: Integration Tests

- `make fidelity-gate` (pinned image; green on the stamped baseline)
- `make check-full` — final backend gate (runs `fidelity-gate` via Task 11).

### Level 4: Manual Validation

1. `make fidelity-restamp REASON="smoke"` on a clean head: `git diff data/debug/fidelity_baseline.json` shows only a new `stamps` row (scores unchanged within margin). Discard with `git checkout -- data/debug/fidelity_baseline.json`.
2. Open `.tmpscratch/fidelity-gate/` crops for one case (`scripts/fidelity-gate.py check --dump-crops`, Task 9) and confirm a section's two crops show the same content.
3. Proofs (b) and (c) as Tasks 14–15.

### Level 5: Additional Validation

- CI run on the draft PR: backend job green with the gate step; re-run the job once for the second same-head run (done check (a)).

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: `data/debug/fidelity_baseline.json` committed with per-case, per-section scores for cases 5–10; CI fails when any section drops more than the margin below its baseline, or a section is lost or new. Two CI runs on the same head produce scores within the margin (done check (a)).
- [ ] AC 2: sections are sliced by the converter's section markers mapped to Figma node ids (`section_node_ids`), not by design y; converter HTML byte-identical (`make snapshot-test` green, ladder unchanged).
- [ ] AC 3: references at 1x frame width for all six cases and all assets referenced by current output for cases 6–10 committed; nothing in the gate reads `raw_figma.json` or an untracked file.
- [ ] AC 4: backend CI job runs the gate in `mcr.microsoft.com/playwright/python:v1.61.0-noble` on `ubuntu-24.04`.
- [ ] AC 5: `make fidelity-restamp REASON="…"` documented; blank reason and non-pinned env are refused; each stamp is logged in `stamps`.
- [ ] AC 6: the two stub metrics are gone and `overall_score` is reweighted over the three real ones.
- [ ] Done check (b): #409 revert fails the gate on case 6 or 10 (observed, recorded).
- [ ] Done check (c): under the icon-size mutation, every byte-identical section stays within the margin (observed, recorded).
- [ ] Done check (d): `docs/fidelity-gate.md` with margin, rule, observed spread.
- [ ] `make check-full` green on the head; `phase-53.7-asset-reexport-prerequisite` closed.

---

## COMPLETION CHECKLIST

- [ ] Tasks 0–18 done in order, each VALIDATE run
- [ ] Margin 0.005 recorded in the baseline and `docs/fidelity-gate.md` before Tasks 14–15 ran
- [ ] `make check-full` and `make fidelity-gate` green (observed, named in the report)
- [ ] Draft PR opened; CI re-run once for the same-head spread
- [ ] Report at `.claude/reports/ce-1-fidelity-baseline-gate.md`

---

## OPEN QUESTIONS / ASSUMPTIONS

No open question blocks execution apart from D1. Every earlier risk now has a measured answer or a pre-decided branch:

| Risk | Status |
|---|---|
| R1 cross-host determinism | Same-host spread measured at 0.0000 (E1). The one thing not measurable before a CI run is the runner-vs-local delta. Task 13 has a fixed rule for both outcomes (keep the local stamp, or stamp from the CI artifact through the built-in `FROM=`), so the result cannot stall the ticket. |
| R2 proof (b) may only re-key | Measured: no re-keying, and mammut drops 0.0106 (E4). Margin 0.005 leaves about 2x headroom (derived: 0.0106 / 0.005 = 2.1). |
| R3 unscored content | Measured (E3): spacers plus two mammut dividers. The unmarked set is pinned in the baseline and checked (Task 2 (4)). |
| R4 gate absent from `check-full` | Closed: `check-full` depends on `fidelity-gate` (Task 11). |
| Q2 ticket divergence | User-ratified 2026-09-30: 1x frame width (640 for 6 and 9), Lego included. Record it in the PR body. |

Assumptions (each checked by a test):

- **A1.** Frame width = max `EmailSection.width`, and frame origin = min x/y over sections. This holds for all six cases (observed); Task 7 (b) and (e) fail loudly for a future case where it does not.
- **A2.** Resizing a render crop to the design crop's size scores a height error as a fidelity error in that section only (E5 shows no leakage into other sections).
- **A3.** Repo growth is about 14 MB of PNG (derived in Task 4), accepted by the user.

## NOTES

- Why not change the marker text to carry node ids: every `expected.html` (6 cases) and the snapshot tests would move, and later tickets would diff noise. The additive field costs one tuple and no bytes.
- Why not a separate CI job: `ready.needs` (`ci.yml:521`) and the 10 required branch-protection checks would need editing; the latter is a user action. A step in `backend` inherits both.
- Why a Docker step and not `playwright install --with-deps` on the host runner: the re-stamp has to run in the same environment as the check. The host runner's font set is not reproducible on a laptop; the image is.
- Why key by node id: `section_<idx>` renumbers every later section when grouping changes; node ids survive that. A section that disappears or appears shows up as lost/new and forces an explicit re-stamp.
- Probe data (observed, 2026-09-30): layout sections vs markers per case 5–10 = 15/15, 9/9, 21/16, 11/11, 11/10, 17/15, all top-level (E2).

## AMENDMENTS

- 2026-09-30 — spike run before execution (E1–E8): markers proven one-per-flat-section, peel rows side by side (x+y crops), margin fixed at 0.005, `FROM=` CI-artifact stamping added, `fidelity-gate` added to `check-full`, proof (b) revert conflict recipe, findings F1–F3.
- 2026-09-30 — superseded during implementation (report `.claude/reports/ce-1-fidelity-baseline-gate-report.md`, Deviations 1–10):
  - Image pin: `uv.lock` moved to Playwright 1.63.0 after planning, so the 1.61.0 image no longer launches. The Makefile derives the tag from `uv.lock` (`FIDELITY_PLAYWRIGHT`), and every "v1.61.0-noble" above reads as `v<uv.lock version>-noble` (1.63.0 at stamp).
  - Task 1: the field is set in `_assemble_phase` (the HTML-bearing constructor), not at `:488`/`:545`; the VLM-verification copy passes it through.
  - Task 2: added `test_marker_wraps_its_own_node`, because a reversed tuple passed the set-based assertions.
  - Task 4/5: `.pre-commit-config.yaml` `check-added-large-files` exclude extended to `reference_1x.png`.
  - Task 7 (e): the baseline test checks baseline cases == gated cases and margin > 0 (case-agnostic), and checks inputs against the git index.
  - Task 11: `FIDELITY_COMMIT` is passed from the host (no git in the container).
  - Task 17: `phase-53.7-asset-reexport-prerequisite` stays **deferred** with a CE-1 note instead of closing, because A3 on a fresh clone still prints `NO reference PNG` (observed).
  - Task 13: the CI cross-host comparison and the second same-head CI run are pending the draft PR.
