---
name: converter-fix
description: >-
  Runs the email-hub Figma-to-email converter fix cycle: RED-first tests, audited snapshot-baseline regen,
  byte-identity of non-target cases, the section-count ladder, full-corpus A3 fidelity scoring with the
  jitter rule, ledger updates, then the PIV hand-off. Use whenever a change touches `app/design_sync/**`,
  `email-templates/components/**` or `data/debug/**`, even if the user never says "converter": "fix a
  converter / design-sync fidelity gap", "Track G item", "Track H item", "regen the snapshot baselines",
  "expected.html changed", "A3 score dropped", "the ladder drifted", "snapshot test is red", or /converter-fix.
  Do NOT use for agent or judge work (`app/ai/**`) or for Dependabot bumps.
argument-hint: "[plan path or item, e.g. .agents/plans/53-g13-x.md | 'G13 card padding']"
---

# Converter fix

Drive one converter (design_sync) fix from plan to a validated, committed PR: RED tests, audited
baselines, a held ladder, full-corpus A3 reported, the ledger updated. The fix itself is the plan's; this
skill is the cycle around it and the traps each Track-G PR paid for (#352 to #365).

Target: `$ARGUMENTS`

## Vocabulary

- **Corpus:** the six converter cases `data/debug/{5,6,7,8,9,10}` (active in `data/debug/manifest.yaml`).
  `reframe` is `reference_only`, never converted.
- **Target cases:** the cases the fix is meant to move. **Non-target:** every other corpus case. Name both
  before writing code; the non-targets are the regression guard.
- **Ladder:** the per-case section-count ladder committed in `data/debug/ladder_snapshot.json`, enforced
  by `TestSectionLadder.test_ladder_no_drift` (`app/design_sync/tests/test_converter_data_regression.py:266`).
  Report it as "unchanged from base", never as remembered numbers.
- **A3:** the advisory pixel-fidelity score from `scripts/score-fidelity-cases.py`. Reported on every
  converter change, never a ship gate.

## Workflow

### 0. Plan and preflight

1. Require a plan in `.agents/plans/` (a converter change always needs one, per CLAUDE.md "Plan when it
   spans or risks"). No plan: stop and hand off to `piv-plan-implementation`.
2. Run `/preflight-check <plan>`. Its Step 2 does the deferred-items cross-reference
   (`.claude/commands/preflight-check.md:13`); carry its "Deferred Items Touching This Plan" table forward.
3. Record the base: `git rev-parse origin/main`. Every "unchanged", "byte-identical" and A3 "before" is
   against this base.
4. Write down target and non-target cases and which render path the fix touches (default renderer, or the
   tree-bridge path behind `DESIGN_SYNC__TREE_BRIDGE_ENABLED`, default off at
   `app/core/config/design_sync.py:105`).

### 1. Tests first, proven RED

1. Write unit tests that assert strings impossible under the old code (#353 asserted `padding:5px 10px` and
   `border-radius:0px` against a hardcoded `10px 24px`). A test that passes on the old code guards nothing.
2. Run them against the unchanged code and keep the failing output: they must fail on the assertion, not on
   an ImportError.
3. If tests had to be written after the code, prove RED by neutering the fix, running, and reverting (#356).
   Say "RED-first post-hoc" in the report.
4. Use real fixtures (golden templates, component seeds, `data/debug` cases), never synthetic email HTML.
   Guards over `data/debug` inputs are real CI gates: see `references/baselines-and-gates.md` § What runs in CI.

### 2. Implement

Make the smallest change that turns the tests green. While iterating, lint only the changed files:
`uv run ruff check --no-fix <files>` and `uv run ruff format --check <files>`. The full gate comes in step 6.
Keep email HTML table-only (CLAUDE.md "Email HTML is table-only"); `make golden-conformance`
(Makefile:154) enforces it.

### 3. Regenerate and audit the baselines

Follow `references/baselines-and-gates.md` § Regen-and-audit exactly. In short: capture every corpus case
to a temp path with `scripts/snapshot-capture.py <case> --output <tmp>`, diff against the committed
`expected.html`, trace every changed line to the fix, and only then `--overwrite` the target cases. Never
use `make snapshot-capture` for this (it hardcodes `--overwrite`) and never follow the test's
`cp actual.html expected.html` hint.

### 4. Hold the non-targets and the ladder

1. Non-target cases are byte-identical modulo whitespace. Evidence is both of: the step-3 scratch diffs
   for every non-target case are empty under `--ignore-all-space`, and `make snapshot-test` (Makefile:157)
   is green after the overwrite (`test_snapshot_matches` compares live output with the committed
   `expected.html` for all six cases, as CI does). A working-tree `git diff` of `data/debug/` proves
   nothing here: only targets were overwritten. A whitespace-only diff on a committed baseline is the known
   c8 churn, not a change: restore it, do not commit it.
2. Ladder: `git diff origin/main -- data/debug/ladder_snapshot.json` is empty and
   `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder` is green. A fix that
   is meant to move the ladder regenerates it (`python -m app.design_sync.tests.ladder_harness --write`),
   commits it, and says so; an unintended ladder move is a stop.
3. Fast loops while iterating: `make snapshot-test`, `make converter-data-regression` (Makefile:170;
   `CASE=<n>` to narrow). Both are already inside `make test`; they are not extra ship gates.

### 5. Score A3 on the full corpus (advisory)

Follow `references/a3-scoring.md`. The load-bearing points:

- A fresh worktree scores only case 5: the other five reference PNGs and assets are gitignored. Copy them
  in first (the recipe is in the reference). A table with fewer than six rows is a short run, not a
  full-corpus A3.
- Score before (fix stashed) and after, same checkout, same command:
  `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`.
- **Jitter rule.** A per-section drop on a target case is a scorer artifact until proven otherwise. Trust,
  in order: non-target flatness, the side-by-side composites, `structure.json` geometry. A non-target
  regression beyond jitter, or any per-band trade on a target, stops for the user's ratification before
  commit (CLAUDE.md "Converter changes carry full-corpus A3"). Record the ratification in the PR body.

### 6. Validate

Run `piv-validate` (it runs `make check-full` through `record-gate.sh`). While iterating, the converter
subset is `uv run pytest app/design_sync/tests/ app/components/tests/` plus `make types` (Makefile:133);
the ship gate is `piv-validate` only. The diff-scoped gates that bite converter work are in
`.claude/commands/be-validate.md` Level 7 (`make lint-numeric` and `make golden-conformance` for
`app/design_sync/**`); read the table there instead of re-deriving it.

### 7. Update the ledger

Use the `deferred-items` skill (`.claude/skills/deferred-items/`) to close the entries this fix satisfies
and to add entries for deliberate scope lines. Two recurring shapes from Track G:

- **Tree-path deferral.** When a fill cannot round-trip through the non-default tree-bridge path, skip it
  there (return `None`, keep the compile valid) and ledger the gap, instead of emitting something that
  fails `validate_tree_against_manifest` and poisons the whole tree compile (#354). A variant: degrade the
  fill in the tree path only, as #357 did by stripping the card to plain text, and ledger it (ledger ids
  `phase-53g-g4-tree-html-slot-row-shape`, `phase-53g6-card-tree-path-text-only`).
- **Partial acceptance.** When a mechanism is correct but the corpus never exercises it, say so, prove it
  with a unit test on the real pipeline, and ledger the upstream cause (#365 item 1). Never claim a corpus
  win the baselines do not show.

If the fix moves a measured number in `docs/converter-fidelity-ceiling.md` § 3 or closes a § 4 residual,
append to that doc (append-only, dated). Follow its § 5 contract for how to state fidelity numbers.

### 8. Hand off

`piv-validate` → `piv-commit` → `piv-create-pr`. `piv-commit` already restores the gate's
`skill-versions.yaml` auto-stamps (`.claude/skills/piv-commit/SKILL.md:19`); do not restore them by hand
here. Base the PR on `origin/main`, never on another unmerged converter branch: a PR stacked on a base
that merges first lands in the dead branch, not main (#358 → #359, #361 → #362).

## PR body: what reviewers expect

Suggested shape, not a mandate: What changed · RED-proven tests (names, count) · baseline diff audit
(which cases moved, `+N/-M`, and that every line traces to the fix) · non-target byte-identity · ladder
"unchanged from base" · A3 before/after table for all six cases with ratified trades named ·
`make check-full` result from `piv-validate` · deviations from the plan · ledger ids closed and added.
Tag every figure `observed` (name the run), `derived` or `expected` (CLAUDE.md "Claims").

## Gotchas

- `make check-full` starts with `make lint`, which rewrites files repo-wide. That is fine in a clean
  worktree; run it through `piv-validate` so the tree-changed check catches it.
- Adding a serialized field to a `Document*` dataclass needs a matching `/$defs` entry in
  `data/schemas/email-design-document-v1.json` (`additionalProperties: false`), or the app path rejects
  it (#359, #353).

## Resources

- `references/baselines-and-gates.md`: read at steps 1, 3 and 4. The regen-and-audit recipe, the c8
  whitespace mechanism, ladder regen, and exactly which converter tests run in CI and why.
- `references/a3-scoring.md`: read at step 5. Asset setup for a worktree, the before/after stash recipe,
  the CLI and stale-`scores.json` trap, the section-cache flag, and the jitter rule in full.
- `docs/converter-fidelity-ceiling.md`: the fidelity contract and residual register (external; § 5 before
  quoting any number).
- `.claude/commands/be-validate.md` Level 7 and `.claude/commands/preflight-check.md` Step 2: pointed to,
  not restated.
