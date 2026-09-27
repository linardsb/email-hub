# AI layer derived from the taxi repo (2026-09-27)

Source: `~/Desktop/taxi/.claude/` at commit `f2cc6c4` (2026-09-22). Derived for email-hub: six skills are copied
unchanged (first row), the rest adapted, rewritten or new. Every taxi coupling (pnpm/turbo gate, `apps/`/`packages/` paths, Drizzle, the anketa `app/` fence, CodeQL
issue #165 references) was either rewritten against email-hub's own gates and paths or dropped. Job plan,
decisions (D1–D11, V1–V15) and the progress log: `.agents/plans/ai-layer-import.md`. Architecture:
`.agents/plans/ai-layer-architecture.md`.

## Provenance per file

| Path | Status | What changed from taxi |
|---|---|---|
| `skills/opportunity-scan`, `piv-next`, `piv-review-changes`, `plan-create-prd`, `rules-check-drift`, `system-execution-report` | as-is | none |
| `skills/piv-commit` | adapted | scoped staging; restores auto-stamped `app/ai/agents/*/skill-versions.yaml`; `wip:` → `chore(wip):` (commit-msg hook rejects `wip:`) |
| `skills/hooks-create`, `skills-create` | adapted | `SKILL.md` only (hook-fence + heredoc note; YAML-valid frontmatter); `skills-create/references/` and `templates/` as-is |
| `skills/piv-slice-epic` | adapted | template matches `piv-next/next.sh` rows; `epic` label |
| `skills/prime-codebase` | adapted | probes `pyproject.toml`, `uv.lock`, `Makefile`, `cms/package.json` instead of turbo/pnpm-workspace/.expo |
| `skills/piv-run-full-loop`, `piv-investigate-issue`, `piv-implement-issue`, `vertical-slice-audit`, `system-evolution-review` | adapted | `.agents/plans/`; `Explore` agent; `make` gates; `app/{feature}/` slice with `exceptions.py` |
| `skills/piv-fix-review-findings`, `piv-review-pr` | adapted | deferrals → `.agents/deferred-items.json`; Semgrep instead of the taxi CodeQL feed; `gh pr review --comment` on self-authored PRs; dead-base guard for stacked PRs |
| `skills/piv-validate` | rewritten | `make check-full`, `make ci-fe` (not `check-fe`), eval gate for agents/judges, converter row, tree-changed check |
| `skills/piv-create-pr` (+ `scripts/record-gate.sh` rewritten, `scripts/inherited-figures.sh` taxi issue refs dropped) | rewritten | pytest/vitest parser instead of turbo; `short_gate` rules; `Closes #N`; dead-base check; draft flow kept |
| `skills/piv-implement`, `piv-plan-implementation` | adapted | alembic awareness, worktree recipe, 700-line plan cap, mandatory deferred-items grep, `file:line` over code blocks |
| `skills/converter-fix`, `deferred-items` | new | email-hub only (Track B/G converter cycle; ledger add/close/SHA-stamp) |
| `agents/code-reviewer.md` | rewritten | from `.claude/rules/*` + HTML email rules; Critical/High/Medium/Low |
| `hooks/pre_tool_use.py` | adapted | anketa fence and `rm -rf` guard dropped; DB guards added (alembic downgrade, dropdb, TRUNCATE, volume removal); gate-settings writes blocked; Semgrep suppressions blocked; branch-protection / auto-merge `gh api` writes blocked; plain `python3` |
| `hooks/stop_check.py` | rewritten | ruff on every changed `.py`, mypy/pyright on `app/`, nearest pytest, `uv lock --check` when lockfiles change, all on files changed since session start; `pnpm type-check` for `cms/`; never passes silently |
| `references/conventions.md`, `logging-standard.md` | rewritten | taxi files of the same name, content re-sourced from email-hub's commit command, pre-commit config, PR history and backend rules |
| `settings.json` | merged | new hook entries alongside the existing `block-dangerous.sh` / `pre-commit-security.sh`; two read-only allows added (`gh pr view`, `gh issue view`) |
| `system-reviews/REMEDY-LEDGER.md` | reset | taxi rows dropped; empty ledger |
| `execution-reports/` | reset | taxi's 11 reports dropped; empty dir (`.gitkeep`) |

## Email-hub files changed, not from taxi

| Path | Change |
|---|---|
| `CLAUDE.md` | PIV workflow, artefact table and PR flow modelled on taxi `CLAUDE.md` `## Workflow (PIV loop)`; working principles from the S3 interview; existing rules kept |
| `.claude/rules/*.md` (6) | `globs:` → `paths:`; jCodeMunch repo id → `linardsb/email-hub` |
| `.gitignore` | `.mcp.json` un-ignored; `.mcp.local.json`, `.claude/last-gate.json`, `.claude/state/` added |
| `.mcp.json` | new: jcodemunch-mcp + jdocmunch-mcp via `uvx` |

Not taken: taxi `plan-architecture` (the global skill is used), `prime-app` (email-hub has `be-prime`/`fe-prime`), the taxi-domain
references `dispatch-strategies`, `realtime-events`, `ride-state-machine`, `ui-decisions`,
taxi CLAUDE.md's `.claude/`-only artefact rule (email-hub plans live in `.agents/plans/`).
The CI half (`codeql` job, `codeql-gate.sh`, `ready` job) ships in a separate PR.
