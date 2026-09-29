---
name: piv-validate
description: Runs this project's full validation gate for every surface the change touches — backend `make check-full`, frontend `make ci-fe` when `cms/` changed, and the eval gate when agents or judges changed — records the result against the commit, and reports one PASS/FAIL verdict. Use before committing, before opening a PR, or after finishing a chunk of work to confirm zero regressions.
---

# Validate

Run every gate the change's surfaces need and report a single PASS/FAIL verdict. This skill reports; it
does not fix. Unit tests only: never run `make db`, `db-migrate`, `db-revision`, `db-squash`,
`seed-demo`, `demo`, `test-integration`, or anything that touches a database or migration state.

**The gates are Makefile targets, run from the repo root** (CLAUDE.md § Definition of Done):

| Surface (paths in the diff) | Gate | Why this one |
|---|---|---|
| anything outside `cms/` and docs (`app/`, `alembic/`, `services/`, `scripts/`, `pyproject.toml`, `uv.lock`, `Makefile`, …) | `make check-full` (Makefile:182) | lint + types + unit tests + check-fe + security + migration-lint + overlays + numeric lint + golden conformance + flag audit + env drift |
| `cms/` | `make ci-fe` (Makefile:195) | CI mirror: frozen install, lint, format:check, type-check, test. **Not `make check-fe`** — its lint and format:check end in `\|\| true` (Makefile:138-139), so they cannot fail it |
| `app/design_sync/`, `email-templates/components/`, `data/debug/` (converter) | `make check-full`, plus the `converter-fix` evidence | `check-full` already runs the snapshot, ladder and golden tests. The baseline audit, empty non-target scratch diffs and the A3 before/after (advisory, never a ship gate) come from `.claude/skills/converter-fix/SKILL.md` and must exist before this gate |
| `app/ai/agents/` (incl. `evals/judges/`, SKILL.md files, `skill-versions.yaml` edits), `app/ai/blueprints/inline_judge.py`, `traces/` | eval gate, below | per-agent 3pp regression tolerance is part of Done, not optional |

Find the surfaces from the branch diff plus the working tree:

```bash
git diff --name-only origin/main...HEAD; git status --porcelain
```

**Two things `make check-full` does that a checker must account for** (`observed` at S0 of the AI-layer
import, 2026-09-27):

- It runs `lint` first (Makefile:182), and `lint` is `ruff format .` + `ruff check --fix .` (Makefile:130-131):
  it **rewrites files**. A run that reformatted the tree validated a tree HEAD does not contain, and CI's
  `ruff format --check` will fail on the committed one.
- `make test` rewrites the `date:` line of `app/ai/agents/*/skill-versions.yaml` (seen on `dark_mode` and
  `scaffolder`). That is gate noise, not a change: restore each such file **only if it was clean before
  the run**, then compare the tree.

`record-gate.sh` handles both: it samples the tree before and after, restores the clean-before
`skill-versions.yaml` files, and marks the record short if anything else changed.

Keep going after a failure so the report covers everything, and keep the log of any command that fails.

## 1. Frontend — only if `cms/` changed

```bash
.claude/skills/piv-create-pr/scripts/record-gate.sh -- make ci-fe
```

Run it before the backend gate: each `record-gate.sh` run overwrites `.claude/last-gate.json`, and the
record `piv-create-pr` reads should be the backend one. Read the JSON straight after this run and note
its verdict fields in the report.

## 2. Backend — the gate

```bash
.claude/skills/piv-create-pr/scripts/record-gate.sh      # default: make check-full
```

Cap the Bash timeout at 10 min: the backend part took 362 s and `check-fe` 57 s at S0 (`observed`, one run
each; derived total about 7 min). Run it in the background or with a long timeout, and read the verdict
from `.claude/last-gate.json` and the log path it prints (under `.claude/state/gate/`, gitignored), not
from the scrolled terminal.

**Expected:** `exit_code` 0, `make_errors` empty, `short_gate` false. `pytest_passed` is the `make test`
run's count (Makefile:86), not the smaller `golden-conformance` run that prints after it (Makefile:155);
the parser attributes each pytest summary to the command above it. A count under 8,000 is a *short* gate,
not a pass (S0 `observed` 8492 passed, 115 skipped, in the AI-layer worktree). Exit 3 from
the script means make exited 0 but the record is short: read `short_reasons`.

Untracked files under the four PIV artefact directories (`.claude/reports/`, `.claude/code-reviews/`,
`.claude/execution-reports/`, `.claude/system-reviews/`) do not mark the record dirty; every other new
file does, and so does a tracked edit inside those directories.

Do not start a second gate while one runs: two `make check-full` runs in one tree collide (both run
`ruff format .`, both rewrite `skill-versions.yaml`), and a parallel agent editing the tree mid-run makes
the tree-changed check fire for a reason that is not the gate.

## 3. Eval gate — only if agents or judges changed

Pick by what changed (`.claude/docs/eval-system-guide.md`; Makefile targets opened):

| Change | Run | What it checks |
|---|---|---|
| Any agent, scaffolder, `TemplateAssembler` or template-assembly code | `make eval-golden` (Makefile:440) | deterministic golden cases, no LLM, seconds |
| Agent behaviour, SKILL.md, judge prompts/criteria, or `traces/` | `make eval-check` (Makefile:338) | `eval-analysis` + `eval-regression` (3pp per agent, `AGENT_REGRESSION_TOLERANCE` in `app/ai/agents/evals/regression.py:31`) + `eval-calibration-gate` |
| Judge prompts/criteria only, re-checking calibration alone | `make eval-calibration-gate` (Makefile:335) | TPR/TNR drop over 5pp (`CALIBRATION_REGRESSION_THRESHOLD`, `app/ai/agents/evals/calibration_tracker.py:28`) |

- These gates diff the **committed** traces in `traces/`; they do not generate new ones. A change whose
  effect needs fresh LLM traces (`make eval-full`, Makefile:417, needs an LLM provider) is not measured by
  them: report it as "not measured", never as a pass. This skill does not run `eval-full`.
- `eval-check` starts with `eval-analysis`, which **writes the tracked `traces/analysis.json`**
  (Makefile:327). Sample `git status --porcelain traces/` before; if the file was clean before and the
  task is not a trace refresh, report the diff and `git checkout -- traces/analysis.json`. Any other tree
  change after an eval run is a FAIL.
- A regression beyond tolerance is a FAIL even if every unit test is green.

## 4. Environment or code? (classify before touching the diff)

None of these signatures is your diff — report it with the log line as evidence, do not edit toward green.

- `ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL` with `node_modules missing`, or `tsc: command not found` — `cms/`
  dependencies are not installed in this checkout (`observed` at S0 in a fresh worktree; `check-fe` then
  errored at type-check after its `|| true` lint and format:check had already "passed"). `cd cms && pnpm
  install --frozen-lockfile`, re-run.
- `Install squawk: brew install sbdchd/squawk/squawk` — `migration-lint` (Makefile:510) needs squawk on
  PATH. The user installs it; it is not a code failure.
- A lower pytest count than on the main checkout with nothing red — not converter data: the case inputs
  (`structure.json`, `tokens.json`, `expected.html`, `rendered_w600.png`) are tracked (`.gitignore:138-146`),
  so the converter tests run the same in a fresh worktree and in CI. Only `scripts/score-fidelity-cases.py`
  (A3, not a test) needs local-only reference PNGs and assets. Compare counts only between runs in the same
  checkout.
- `.claude/last-gate.json` names another `head` — the record predates a commit or rebase. Re-run.

## 5. Optional — live API smoke test

Only when the change touches app bootstrap, routing, or middleware (`app/main.py`, `app/core/`); skip
when the unit tests already exercise the route in-process. Start `make dev-be` in a second shell, check
the startup log is clean and the API answers over HTTP on `:8891`, then stop it. A running process is not
the signal; an HTTP response is.

## 6. Summary report

One line per gate run, each with its command, `head_short`, exit code and counts **copied from
`.claude/last-gate.json` or the Validation block `record-gate.sh` printed** — never retyped from memory, a
plan, or an earlier run:

- backend `make check-full` — PASS / FAIL / SHORT (+ `short_reasons`)
- frontend `make ci-fe` — PASS / FAIL / SHORT, or "not run: no `cms/` change"
- eval gate(s) — PASS / FAIL, or "not run: no agent/judge change", or "not measured" (needs fresh traces)
- tree after the runs — unchanged / changed (list paths)
- **Overall: PASS or FAIL.** PASS needs every applicable gate green, no short record, and an unchanged tree.

For every FAIL or SHORT, include the failing command, the `make_errors` / `short_reasons`, and the
relevant log lines. Tag every figure `observed` (from a run at this head) — a figure from any other run
is not evidence for this one.

## Notes

- Keep this skill honest before fast. `make check` is `check-full` minus `migration-lint`; dropping a
  target to save a minute is dropping a check. Run the full gate before any PASS this skill reports.
- A checker that cannot fail is worthless. If the gate passes suspiciously fast, read the log: the pytest
  summary line (`N passed, … in Ns`) and vitest's `Tests  N passed (N)` are where you read that tests ran,
  and `record-gate.sh` marks a missing summary or a target that never ran as short.
- **A green gate is not a green CI.** CI runs `ci.yml`'s jobs, which differ from `check-full` (CI's backend
  job adds pip-audit; `sdk-check`, `trivy`, `migrations`, `integration`, `e2e-smoke` have no local
  equivalent here). On a PR that touches `.github/workflows/*.yml`, `docker-compose*.yml`, `alembic/`,
  or the OpenAPI surface, run `gh run list --branch $(git branch --show-current) --limit 1` and report
  CI's verdict beside your own.
