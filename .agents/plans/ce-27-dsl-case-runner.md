# Feature: CE-27 case runner into the CE-1 fidelity gate

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay attention to the exact names of existing types and functions in `app/design_sync/fidelity_gate.py`; import from that module, never re-implement its pieces.

## Feature Description

A small runner that scores **any** `ConversionResult` for a corpus case through the CE-1 per-section fidelity gate and compares it with the committed baseline. Today the gate can only score the template path, because `score_cases` calls `run_case_conversion` itself (`app/design_sync/fidelity_gate.py:477`). The runner takes the result as an argument, checks that its section ids are exactly the baseline's ids for the case, renders it with the gate's own renderer, scores it with the gate's own scorer, and returns the gate's own report. It is exercised on the template path's output so it is proven before any DSL compiler exists (CE-19 #437 is its first real caller).

## User Story

As the engineer running the DSL spike (CE-19 #437)
I want to score a second converter path's output against the committed CE-1 baseline, section by section
So that the S5 verdict rule ("no section below baseline by more than the margin") can be read with the same instrument that gates the template path.

## Problem Statement

The CE-1 gate is the epic's single acceptance harness (`docs/architecture/dsl-compiler.md` §Key decisions), but its only entry point converts the case itself through the template path (`fidelity_gate.py:470-483`). A second path has no way in. Also, `compare` (`fidelity_gate.py:315`) reports a section whose id changed as `lost` + `new` with "re-stamp needed", which for a new path hides the real problem: the path did not mark the analyser's sections. The spec (S4, S5) requires a pre-scoring assertion that the id sets match, with a named error.

## Solution Statement

New module `app/design_sync/fidelity_runner.py` (outside `dsl/`: it scores any path):

| Symbol | Does |
|---|---|
| `SectionIdMismatch(GateError)` | Named error. Message lists `missing` (in baseline, not in result), `extra` (in result, not in baseline) and `duplicates`, each sorted. Subclassing `GateError` keeps `scripts/fidelity-gate.py`'s exit-2 path (`scripts/fidelity-gate.py:47-49`) valid for any future CLI use. |
| `baseline_node_ids(case: CaseBaseline) -> frozenset[str]` | `sections.keys() | skipped.keys()`. Both come from `section_node_ids` in `score_rendered_case` (`fidelity_gate.py:208-224`); `unmarked` does not (`:165-172`) and is excluded. |
| `assert_section_ids(case, result, baseline: FidelityBaseline) -> None` | `GateError` if the case is not in the baseline; `SectionIdMismatch` if `result.section_node_ids` has duplicates or its set differs from `baseline_node_ids`. No I/O, no browser. |
| `score_conversion(case, result, *, baseline: FidelityBaseline \| None = None) -> CaseBaseline` | `baseline = baseline or load_baseline()`; `assert_section_ids` **first**; `GateError` if `result.layout is None`; then `asyncio.run(render_case_sections(case, result, frame_width(result.layout.sections)))` and `score_rendered_case(case, rendered)`. Same three calls, same order, as `score_cases` (`:477-482`). |
| `check_conversion(case, result, *, baseline: FidelityBaseline \| None = None) -> GateReport` | `score_conversion`, wrap in a one-case `ScoreRun(environment=current_environment(), commit=current_commit(), cases={case: scored})`, filter the baseline to that case (pattern `fidelity_gate.py:500-502`), return `compare(...)`. |

No gate code changes (S5: "No gate code changes"). One Makefile line changes so CI collects the new pinned test.

## Out of Scope / Non-Goals

- Not included: the DSL compiler, tree builder, `compile_tree`, the `dsl_compiler_enabled` flag (CE-19 #437 / M3, M4).
- Not included: a CLI subcommand or `make` target for the runner; CE-19 calls it from Python. Add one there if the spike wants it.
- Not changing: `fidelity_gate.py` (no refactor of `score_cases` to delegate to the runner; see Q2), the baseline file (no re-stamp), converter output (byte-identical by construction: no converter file is touched).
- Not included: held-out case support (CE-5 #423 adds the case through the add-a-case recipe; the runner needs nothing extra).

## Feature Metadata

**Feature Type**: New Capability (test/measurement harness)
**Estimated Complexity**: Low
**Primary Systems Affected**: `app/design_sync/` fidelity gate (read-only use), `Makefile` `fidelity-gate` target, `docs/fidelity-gate.md`
**Dependencies**: none new (Playwright, Pillow, numpy already used by the gate)

## Related Work

**Implements**: #467 (CE-27)   ·   **Epic**: #439; spec `docs/architecture/dsl-compiler.md` S4, S5, M5; slices `.agents/plans/dsl-epic-slices.md:46-50`

**Back-references**:
- `.agents/plans/ce-1-fidelity-baseline-gate.md` — the gate, baseline schema and pinned-image rules this runner reuses.
- `.agents/plans/ce-26-document-schema-v2.md` — sibling groundwork (CE-26 #466, merged #475 `c07dfc15`); the v2 document the DSL path will read.

**Forward-references**:
- CE-19 (#437) spike — first non-template caller of `check_conversion`.

## Deferred Items Touching This Plan

Grep run 2026-10-05 over `.agents/deferred-items.json` (`items`, `status: deferred`) for `fidelity_gate`, `fidelity_baseline`, `regression_runner`, `ce-26`, `ce-27`, `dsl/`, and every file in this plan.

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `phase-53.7-asset-reexport-prerequisite` | indirect: the runner renders through `render_case_sections`, which rewrites asset srcs via `fidelity_case_scorer._rewrite_asset_srcs` | carry forward | Concerns A3 on a fresh clone; the gate's committed ≤600px assets already cover the runner. Nothing here changes asset handling. |
| `phase-53-a2-advisory-section-gate` | code_ref `regression_runner.py:113` (file read, not modified) | avoid | The runner calls `run_case_conversion` (`:48`) only in tests; it never reads `manifest.sections.count`. |
| `ce-26-whole-file-documents-exceed-v1-caps` | phase `ce-26` (sibling) | avoid | Schema caps on persisted rows; the runner takes a `ConversionResult`, not a document. |

No `ce-27` phase entries exist.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `app/design_sync/fidelity_gate.py:66-67` — `GateError(AppError)`; the base of the new error.
- `app/design_sync/fidelity_gate.py:77-117` — `SectionBaseline`, `CaseBaseline` (`sections`, `skipped`, `unmarked`), `FidelityBaseline`, `ScoreRun`.
- `app/design_sync/fidelity_gate.py:130-132` — `frame_width`.
- `app/design_sync/fidelity_gate.py:165-172` — `unmarked_sections`: layout sections with no marker; why `unmarked` is not part of the id set.
- `app/design_sync/fidelity_gate.py:175-243` — `RenderedCase`, `score_rendered_case`. Note `by_node[node_id]` at `:211` raises `KeyError` on an id that is not a layout section; the pre-check turns that into a named error instead.
- `app/design_sync/fidelity_gate.py:315-360` — `compare`; `lost`/`new` rows.
- `app/design_sync/fidelity_gate.py:396-428` — `render_case_sections(case, result, width)`; already takes any `ConversionResult`.
- `app/design_sync/fidelity_gate.py:441-467` — `current_environment`, `current_commit`, `load_baseline`.
- `app/design_sync/fidelity_gate.py:470-503` — `score_cases` (the three calls to mirror) and `check` (baseline filter at `:500-502`).
- `app/design_sync/converter_service.py:135-160` — `ConversionResult`, `@dataclass(frozen=True)`; `section_node_ids: tuple[str, ...] = ()` at `:160`. Tests build mismatches with `dataclasses.replace`.
- `app/design_sync/tests/regression_runner.py:48-62` — `run_case_conversion(case_dir) -> ConversionResult | None`; the template path.
- `app/design_sync/tests/test_fidelity_gate.py:54-64` — `CASES`, cached `_convert` with skip on missing inputs: mirror.
- `app/design_sync/tests/test_fidelity_gate.py:211-228` — `_case`/`_baseline` builders for synthetic `CaseBaseline`/`FidelityBaseline`: mirror for the unit tests.
- `app/design_sync/tests/test_fidelity_gate.py:371-379` — the pinned-test decorator pair (`@pytest.mark.fidelity_gate` + `skipif FIDELITY_GATE_ENV != "pinned"`): mirror exactly.
- `Makefile:180-181` — `fidelity-gate` target; collects **only** `test_fidelity_gate.py`. The new pinned test is invisible to CI until this line changes.
- `Makefile:174-178` — `FIDELITY_RUN`/`FIDELITY_SETUP` (pinned image, `FIDELITY_GATE_ENV=pinned`, section cache off).
- `.github/workflows/ci.yml:58-68` — CI `backend` job runs `make fidelity-gate` and uploads `.tmpscratch/fidelity-gate/`.
- `pyproject.toml:304` — `fidelity_gate` marker is registered; no change.
- `docs/fidelity-gate.md` — §The rule (margin 0.005, same-host 0.0000), §Adding a case; gets a new section.
- `data/debug/fidelity_baseline.json` — read-only. Observed 2026-10-05 (reading the file): 7 cases; sections 5:15, 6:9, 7:16, 8:11, 9:10, 10:15, reframe:16; `skipped` empty everywhere; `unmarked` 7:5, 9:1, 10:2; margin 0.005; last stamp 2026-10-04 `6c5c6f18` (CE-7).

### New Files to Create

- `app/design_sync/fidelity_runner.py` — the runner (table above).
- `app/design_sync/tests/test_fidelity_runner.py` — browser-free unit tests + one pinned test class.

### Files to Modify

- `Makefile:181` — add `app/design_sync/tests/test_fidelity_runner.py` to the pytest paths.
- `docs/fidelity-gate.md` — new section "Scoring another converter path (CE-27)".

### Relevant Documentation

- `docs/architecture/dsl-compiler.md` S4 (§Section markers) and S5 (§Scoring) — the id-set rule and "No gate code changes".
- `docs/fidelity-gate.md` §The rule, §Spread — what "within jitter" means (0.0000 same-host, observed in CE-1).
- `.claude/rules/backend.md` — `AppError` subclassing, `get_logger`.
- `.claude/rules/testing.md` — markers, no synthetic email HTML (the tests use the real cases; synthetic objects are only `CaseBaseline` pydantic models, as the gate tests already do).

### Patterns to Follow

- **Module header**: one docstring paragraph naming the ticket and the docs file, as `fidelity_gate.py:1-20`. Copy its pyright pragma only if pyright actually reports unknown types (it should not: the runner touches no PIL/numpy).
- **Errors**: `raise GateError(f"case {case}: ...")` message shape (`fidelity_gate.py:193`, `:479`).
- **Private imports**: none needed; every symbol above is public.
- **Logging**: no new event. `score_rendered_case` already logs `design_sync.fidelity_gate_scored` (`:229-235`).
- **Lint**: ruff rules in `pyproject.toml:126`; `asyncio.run` inside a sync function mirrors `score_cases` (`:472`, `:481`), so no rule flags it. No `TYPE_CHECKING` imports (CLAUDE.md "Linter safety").

---

## IMPLEMENTATION PLAN

### Phase 0: Branch

**Done at planning (2026-10-05).** Branch `feature/ce-27-dsl-case-runner` created from `origin/main` `c07dfc15`, tracking `origin/main`. The working tree carries unrelated modified `.claude/skills/*` and two `app/ai/agents/*/skill-versions.yaml` files from before this ticket: never stage them (stage by explicit path, never `git add -A`).

### Phase 1: RED unit tests (no browser)

Tests for the id-set check and its position, failing on import until Phase 2.

### Phase 2: Runner module

**Depends on:** Phase 1.

### Phase 3: Pinned test, Makefile, docs

**Depends on:** Phase 2. Measures CI cost before/after.

---

## STEP-BY-STEP TASKS

### 1. CREATE branch

- **DONE AT PLANNING**: `git switch -c feature/ce-27-dsl-case-runner origin/main` ran (observed). If main moved since, `git rebase origin/main` before task 3.
- **VALIDATE**: `git branch --show-current` = `feature/ce-27-dsl-case-runner`; `git log --oneline -1` shows `c07dfc15` or a later main head.
- **SATISFIES**: process (one ticket = one branch).

### 2. MEASURE baseline gate runtime

- **DONE AT PLANNING (observed, 2026-10-05, head `c07dfc15`, local Docker 29.2.1, image `playwright/python:v1.63.0-noble`)**: `/usr/bin/time -p make fidelity-gate` exit 0, `1 passed, 75 deselected in 21.34s`, wall 36.43s. Re-run only if main moved.
- **VALIDATE**: exit 0 and `test_fidelity_gate_holds_baseline PASSED`. (The gate prints its table only on failure: pytest captures the `print` at `test_fidelity_gate.py:378`, so do not look for a `PASS` line.)
- **SATISFIES**: AC 6 (cost stated with provenance).

### 3. CREATE `app/design_sync/tests/test_fidelity_runner.py` (RED)

- **IMPLEMENT** (browser-free part; module docstring says which tests need the pinned image):
  - `_convert(case)` cached, as `test_fidelity_gate.py:59-64`; `CASES = ["5", "6", "7", "8", "9", "10", "reframe"]`.
  - `TestBaselineNodeIds.test_includes_skipped_excludes_unmarked`: a `CaseBaseline` with `sections={"a"}`, `skipped={"b": "x"}`, `unmarked={"c": "spacer"}` → `{"a", "b"}`.
  - `TestAssertSectionIds.test_template_path_matches_baseline[case]` (parametrized `CASES`): `assert_section_ids(case, _convert(case), load_baseline())` raises nothing. This is the browser-free half of the done check: the template path's ids equal the baseline's on every case.
  - `test_missing_id_named`: `replace(result, section_node_ids=result.section_node_ids[1:])` on case 5 → `SectionIdMismatch`, message contains the dropped id and `missing`.
  - `test_extra_id_named`: append an id that is a layout section but unmarked — use case 9's single `unmarked` key from the committed baseline (read it, never hard-code) → `SectionIdMismatch`, message contains `extra`.
  - `test_duplicate_id_named`: duplicate the first id on case 5 → `SectionIdMismatch`, message contains `duplicate`.
  - `test_no_layout_raises`: `replace(result, layout=None)` on case 5 (ids unchanged) → `GateError` with "no layout", raised by `score_conversion` before rendering.
  - `test_uncased_baseline_raises`: baseline built with `_baseline(...)` for case "5" only, call with case "6" → `GateError` (and not `SectionIdMismatch`) with "not in the fidelity baseline".
  - `test_check_conversion_wraps_compare`: see task 5 (browser-free).
  - `test_mismatch_raises_before_render`: `monkeypatch.setattr(fidelity_runner, "render_case_sections", boom)` where `boom` raises `AssertionError("rendered")`; `score_conversion` on a mismatched result raises `SectionIdMismatch`, not `AssertionError`. Proves the check precedes rendering, so a bad DSL output fails fast with a name, not a `KeyError` from `score_rendered_case:211`.
- **PATTERN**: `test_fidelity_gate.py:54-64`, `:211-228`.
- **IMPORTS**: `from dataclasses import replace`; `from app.design_sync import fidelity_runner`; `from app.design_sync.fidelity_runner import SectionIdMismatch, assert_section_ids, baseline_node_ids, check_conversion, score_conversion`; gate symbols from `app.design_sync.fidelity_gate`.
- **GOTCHA**: `monkeypatch.setattr` must target `fidelity_runner.render_case_sections` (the name bound in the runner module), so the runner imports it as `from app.design_sync.fidelity_gate import render_case_sections` and calls it by that bare name.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_fidelity_runner.py -q` fails at import (`ModuleNotFoundError: app.design_sync.fidelity_runner`) — RED observed.
- **SATISFIES**: AC 2, AC 3.

### 4. CREATE `app/design_sync/fidelity_runner.py`

- **IMPLEMENT**: the five symbols in the Solution table. Message shape: `f"case {case}: section ids differ from the fidelity baseline (missing: [...]; extra: [...]; duplicates: [...]): the path must mark exactly the baseline's sections, or re-stamp"`. Omit empty groups only if it keeps the message readable; tests match on the group names that are non-empty.
- **PATTERN**: `fidelity_gate.py:470-483` (call order), `:493-503` (filter + compare).
- **IMPORTS**: `asyncio`; from `app.design_sync.converter_service` `ConversionResult`; from `app.design_sync.fidelity_gate` `CaseBaseline, FidelityBaseline, GateError, GateReport, ScoreRun, compare, current_commit, current_environment, frame_width, load_baseline, render_case_sections, score_rendered_case`.
- **GOTCHA**: do not import from `app.design_sync.tests.*` in the module: the runner takes the result; only tests call `run_case_conversion`.
- **GOTCHA**: `baseline or load_baseline()` would treat an empty-but-valid model as falsy only if pydantic defined `__bool__`; it does not, but write `baseline if baseline is not None else load_baseline()` to be explicit.
- **VALIDATE**:
  - `uv run pytest app/design_sync/tests/test_fidelity_runner.py -q` → all browser-free tests pass; the pinned class (task 5) skips.
  - Mutation run (both halves, per the plan rule): change `baseline_node_ids` to return `frozenset(case.sections)` only. Expect `test_includes_skipped_excludes_unmarked` **red** and `test_template_path_matches_baseline[*]` **green** (skipped is empty in every committed case). Record both results; revert.
  - Mutation run: move `assert_section_ids` after `render_case_sections` in `score_conversion`. Expect `test_mismatch_raises_before_render` **red** and `test_missing_id_named` **green** (it calls `assert_section_ids` directly). Record both; revert.
  - `uv run ruff format --check app/design_sync/fidelity_runner.py app/design_sync/tests/test_fidelity_runner.py && uv run ruff check --no-fix` same paths; `uv run mypy app/design_sync/fidelity_runner.py`; `uv run pyright app/design_sync/fidelity_runner.py app/design_sync/tests/test_fidelity_runner.py`.
- **SATISFIES**: AC 1, AC 2, AC 3.

### 5. ADD pinned test class to `test_fidelity_runner.py`

- **IMPLEMENT**: `TestRunnerReproducesGate`, decorated exactly as `test_fidelity_gate.py:371-375`, parametrized over `gated_cases()`:
  - One test, `test_reproduces_gate_and_baseline[case]` (one runner render per case, not two): `ours = score_conversion(case, _convert(case))`; `assert ours == score_cases([case]).cases[case]` (the "wrong if" made executable: runner and gate score the same template output; any difference is a defect); then `report = compare(<baseline filtered to case>, ScoreRun(environment=current_environment(), commit=current_commit(), cases={case: ours}))`, print `report.format()` and `assert not report.failed, report.format()`.
  - `check_conversion` is then not run in the pinned image; it is `score_conversion` + `compare`, so cover it browser-free in task 3: `test_check_conversion_wraps_compare` monkeypatches `fidelity_runner.score_conversion` to return the committed case-5 `CaseBaseline` and asserts the report has 15 rows, all `pass`.
- **GOTCHA**: `score_cases` converts the case itself, so `ours == gates` also asserts the template conversion is deterministic between two calls in one process (the section cache is off in `FIDELITY_RUN`, `Makefile:177`). If this ever flakes, the cause is conversion non-determinism, not the runner: report it, do not loosen the assertion.
- **GOTCHA**: "within jitter" is asserted as `not report.failed` (margin 0.005), not as max |delta| == 0.0000. A later ticket that moves a score inside the margin without re-stamping must not break this test; the observed max delta goes in the report instead (Q3).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_fidelity_runner.py -q` locally → pinned class skipped (reason names `make fidelity-gate`).
- **SATISFIES**: AC 1, AC 4.

### 6. UPDATE `Makefile:181`

- **IMPLEMENT**: `uv run pytest -m fidelity_gate app/design_sync/tests/test_fidelity_gate.py app/design_sync/tests/test_fidelity_runner.py -v -p no:cacheprovider`.
- **GOTCHA**: without this, the pinned class passes in nobody's run: `make fidelity-gate` and CI collect only the gate file today.
- **CHECKED (planning)**: `.claude/skills/piv-create-pr/scripts/record-gate.sh:169-195` keys pytest summaries by the preceding command line and picks the main `uv run pytest` summary; it expects no fixed count from the docker run, so 1 → 8 gate tests needs no script change.
- **VALIDATE**: `/usr/bin/time -p make fidelity-gate` → exit 0; output lists `test_fidelity_gate_holds_baseline PASSED` plus 7 `TestRunnerReproducesGate` items PASSED (derived: 7 gated cases × 1 test). Record wall time; delta vs task 2 is the added CI cost (observed). Expected ≈ +41s pytest time: the planning spike ran the exact runner sequence plus `score_cases` for all 7 cases in 40.7s (observed, below). Under +90s is in line; above that, stop and report before committing.
- **SATISFIES**: AC 1, AC 4, AC 6.

### 7. UPDATE `docs/fidelity-gate.md`

- **IMPLEMENT**: new section after §Adding a case, "Scoring another converter path (CE-27)", ≤ 12 lines: `check_conversion(case, result)` usage; the id rule (`sections ∪ skipped`, `unmarked` excluded); `SectionIdMismatch` meaning; that a path which marks a currently-unmarked section (cases 7, 9, 10) needs a re-stamp decision; that the pinned tests prove runner == gate on the template path.
- **VALIDATE**: `grep -n "CE-27" docs/fidelity-gate.md`.
- **SATISFIES**: AC 5.

### 8. RUN full gate

- **IMPLEMENT**: `make check-full` (includes `make fidelity-gate`), then `git diff` (lint rewrites files) and restore any `app/ai/agents/*/skill-versions.yaml` date churn from `make test`.
- **VALIDATE**: `make check-full` exit 0 (observed, name the head SHA); `git diff --stat origin/main...HEAD` shows exactly: `app/design_sync/fidelity_runner.py`, `app/design_sync/tests/test_fidelity_runner.py`, `Makefile`, `docs/fidelity-gate.md`, `.agents/plans/ce-27-dsl-case-runner.md` (the `.html` brief and the report stay untracked).
- **SATISFIES**: AC 6, AC 7.

---

## TESTING STRATEGY

### Unit Tests (run in `make test` and CI Test step)

`test_fidelity_runner.py` browser-free tests (task 3). Real cases for result objects; synthetic objects only for pydantic `CaseBaseline`/`FidelityBaseline`, as `test_fidelity_gate.py` already does. No email HTML is fabricated.

### Integration Tests (pinned image only)

`TestRunnerReproducesGate` (task 5), collected by `make fidelity-gate` after task 6, so it runs in CI's `backend` job and in `make check-full`.

### Edge Cases

| Edge case | Verified by |
|---|---|
| Missing id | `test_missing_id_named` |
| Extra id that is a real (unmarked) layout section | `test_extra_id_named` |
| Duplicate id (set equality would hide it) | `test_duplicate_id_named` |
| Case not in baseline | `test_uncased_baseline_raises` |
| Baseline section skipped (render box empty) still counts as a baseline id | `test_includes_skipped_excludes_unmarked` |
| Mismatch must not reach rendering / `score_rendered_case:211` `KeyError` | `test_mismatch_raises_before_render` |
| `result.layout is None` | `test_no_layout_raises` |
| Runner and gate disagree on same output | `test_reproduces_gate_and_baseline[*]` (pinned) |
| `check_conversion` wiring | `test_check_conversion_wraps_compare` |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync/fidelity_runner.py app/design_sync/tests/test_fidelity_runner.py`
- `uv run ruff check --no-fix app/design_sync/fidelity_runner.py app/design_sync/tests/test_fidelity_runner.py`
- `uv run mypy app/` and `uv run pyright app/` (`make types`)

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_fidelity_runner.py app/design_sync/tests/test_fidelity_gate.py -q`
- `make test` (restore `skill-versions.yaml` dates afterwards)

### Level 3: Integration

- `make fidelity-gate` (pinned image; includes the new class after task 6)
- `make check-full`

### Level 4: Manual Validation

1. In a Python shell inside the pinned image (`$(FIDELITY_RUN) "$(FIDELITY_SETUP) && uv run python -c ..."`), call `check_conversion("5", run_case_conversion(DEBUG_DIR / "5"))` and print `.format()`: 15 rows, PASS. Performable: case 5 inputs are committed.
2. Same, with `replace(result, section_node_ids=result.section_node_ids[:-1])`: `SectionIdMismatch` naming the last id under `missing`.

### Level 5: Converter blast radius (converter-fix skill inputs)

- Target / non-target cases: none. No converter or template file changes, so output is byte-identical on every case by construction; `test_converter_data_regression.py` (inside `make check-full`) confirms it, ladder 13/9/8/10/8/12 untouched.
- Render path: neither (no converter change). Full-corpus A3: not applicable, no output change. Baseline re-stamp: none.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1 — On the template path, the runner reproduces the committed baseline for every gated case: `test_reproduces_gate_and_baseline[*]` PASS in `make fidelity-gate` (observed on the head), max |delta| recorded in the report.
- [ ] AC 2 — Before scoring, `set(section_node_ids)` must equal `sections ∪ skipped` of the case's baseline, with no duplicates; the template path satisfies it on all 7 cases (`test_template_path_matches_baseline[*]`).
- [ ] AC 3 — A mismatched id set fails with `SectionIdMismatch` (a `GateError`) naming missing/extra/duplicate ids, before any render.
- [ ] AC 4 — "Wrong if" executed: runner scores equal `score_cases` scores on the same template output, every case (`test_reproduces_gate_and_baseline[*]`).
- [ ] AC 5 — `docs/fidelity-gate.md` documents the runner and the id rule.
- [ ] AC 6 — Added CI time from the pinned class stated with provenance (task 2 vs task 6); planning figure ≈ +41s (observed spike, 40.7s).
- [ ] AC 7 — `make check-full` green on the head; no change to `fidelity_gate.py`, the baseline, or converter output.

---

## COMPLETION CHECKLIST

- [ ] Tasks 1–8 in order, each VALIDATE recorded
- [ ] Both mutation runs in task 4 recorded (red half and green half)
- [ ] `make fidelity-gate` and `make check-full` green on the head (observed)
- [ ] Staged set = the five files named in task 8; no `.claude/skills/*` or `skill-versions.yaml`
- [ ] Report at `.claude/reports/ce-27-dsl-case-runner-report.md`, figures tagged

---

## OPEN QUESTIONS / ASSUMPTIONS

- **Q1 — Unmarked sections (decided: reject, verified).** Cases 7, 9, 10 have analyser sections with no marker on the template path (`unmarked` 5/1/2, observed from the baseline). Spec S4 says the DSL emits one pair per analyser section; if it marks those, the runner raises `SectionIdMismatch` (extra ids) on those cases. That is the intended behaviour: the spike runs maap (case 5, `unmarked` empty), and adding sections to a case is a re-stamp decision, not something the runner should allow silently. Verified at planning: every `unmarked` id in cases 7, 9, 10 is a real layout section of the template conversion (observed, planning script), so `test_extra_id_named` exercises the exact failure CE-19 would hit, not a fake id. `docs/fidelity-gate.md` (task 7) states the rule so CE-19 meets it as documented behaviour.
- **Q2 — Extra renders (decided: accept).** The pinned test renders each case twice (runner + `score_cases`), on top of the gate's own pass (derived: 7 cases × 2 = 14 extra renders). Alternative: refactor `score_cases` to call `score_conversion`, which makes "runner == gate" true by construction and drops the equality test. Rejected for this ticket because S5 says "No gate code changes". Cost measured at planning: 40.7s for 7 cases × (runner render + `score_cases` render) in the pinned image (observed spike), against the gate's 21.34s. Threshold in task 6.
- **Q3 — "Within jitter" (decided).** Asserted as `not report.failed` at margin 0.005, not as delta == 0.0000, so a later in-margin score move without a re-stamp does not break this test. The observed max delta is reported. Observed at planning: max |delta| 0.0000 on every case (spike, head `c07dfc15`).
- **Assumption.** The DSL path will produce a `ConversionResult` with `layout` set to the analyser's layout (approach B keeps section roots equal to the analyser's, spec S5 §Tree source). `score_rendered_case` needs it for design boxes (`:192-211`).

## PLANNING SPIKES (observed, 2026-10-05, head `c07dfc15`)

Run before the plan was finalised to remove the risks the first draft carried. Scripts kept in the session scratchpad, not the repo.

| # | What | Command / where | Result |
|---|---|---|---|
| S1 | Template ids equal `sections ∪ skipped`, no duplicates, all 7 cases | local `uv run python` script calling `run_case_conversion` + `load_baseline` | `eq nodup` on 5, 6, 7, 8, 9, 10, reframe |
| S2 | Template conversion deterministic across two calls in one process (premise of `ours == score_cases(...)`) | same script, `(html, section_node_ids)` compared, `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` | `deterministic` on all 7 |
| S3 | Every baseline `unmarked` id is a layout section | same script | true; counts 7:5, 9:1, 10:2 |
| S4 | Gate runtime today | `/usr/bin/time -p make fidelity-gate` | PASS, 21.34s pytest, 36.43s wall |
| S5 | Runner call sequence (`render_case_sections` → `score_rendered_case` → `compare` on a one-case filtered baseline) equals `score_cases` and holds the baseline | the `FIDELITY_RUN` docker command with a one-off script | `runner==gate`, `pass`, max abs delta 0.0000 on all 7 cases; 40.7s |

S5 is the ticket's "wrong if" run once by hand: the implementation only has to wrap those exact calls in named functions and add the id check.

## NOTES

- Placement outside `dsl/`: the runner scores any path, and CE-19's slice note (`dsl-epic-slices.md:101`) keeps CE-27 merged even if the spike says "stay on templates".
- Why a pre-check and not just `compare`: `compare` keys by node id, so a path that marks the wrong sections shows up as `lost` + `new` with "re-stamp needed", which invites a re-stamp that would bake the path's error into the baseline. A named error before rendering points at the path instead. It also avoids the bare `KeyError` at `score_rendered_case:211` for an id that is not a layout section.

## AMENDMENTS

- 2026-10-05 — Risks R1–R3 retired at planning. R1 (CI time): measured, ≈ +41s (S4, S5), threshold added to task 6. R2 (unmarked sections): decided as reject, premise verified (S3). R3 (branch): branch created from `origin/main` `c07dfc15`; tasks 1–2 marked done. Also fixed task 2's VALIDATE, which looked for a `PASS` line pytest never prints.
- 2026-10-05 (implementation) — Shipped as planned; report `.claude/reports/ce-27-dsl-case-runner-report.md`. Task 4: `SectionIdMismatch` omits empty groups (allowed by task 4). Task 3: browser-free tests split into `TestAssertSectionIds`, `TestScoreConversion`, `TestCheckConversion` (names unchanged). Level 4: the manual run covered all 7 gated cases to record AC 1's max |delta| (0.0000, observed), since the pinned test's `print` is captured on pass. Task 6 cost: +37.32s pytest (observed `make fidelity-gate` 58.66s vs 21.34s).
- 2026-10-06 (PR #476 review fixes, `.claude/reports/pr-476-review-fixes.md`) — F1: the `:80` / `:325` claim that the pre-check avoids the `score_rendered_case:211` `KeyError` held only for the template path; `score_conversion` now also raises a named `GateError` before rendering when a marked id is not a `layout.sections` node id (`test_layout_missing_marked_section_raises_before_render`). F2: task 5's hard-coded 15 rows dropped from `test_check_conversion_wraps_compare`. F3: task 5's pinned test now calls `check_conversion` unmocked (spy on `score_conversion`, no extra render) instead of rebuilding the filter + `compare`. F4: task 4's message now ends "fix the path to mark exactly the baseline's sections rather than re-stamping over it". Browser-free tests 15 → 16.
