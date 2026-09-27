# email-hub — Global Rules

Centralised email platform with AI agents: Figma/design → email HTML (design_sync converter), agent pipeline, QA gate, ESP connectors. FastAPI + SQLAlchemy/Alembic backend (Python 3.12+, strict mypy + pyright), Next.js frontend in a pnpm workspace, PostgreSQL + Redis, `uv` for Python deps.

## Architecture map

```
app/<feature>/          # vertical slices (routes → service → repository, tests in app/<feature>/tests/)
app/core/               # config (nested Pydantic settings), logging, database, exceptions
app/shared/             # cross-slice models/utils (TimestampMixin, escape_like)
app/ai/                 # agents + evals (app/ai/agents/, .../evals/), blueprints/, security/ (prompt guard), shared.py (sanitization)
app/design_sync/        # Figma → email HTML converter; sanitizers.py = web-tag stripper
app/qa_engine/          # QA checks (app/qa_engine/checks/) + repair pipeline
app/main.py             # FastAPI entry point
cms/                    # Next.js frontend (web app = @email-hub/web)
services/               # sidecars: maizzle-builder (Node, CSS/MJML build), mock-esp
alembic/                # migrations (squawk-linted)
.agents/                # plans/ (implementation plans) + deferred-items.json (open-gap ledger)
.claude/                # rules/, docs/, commands/, skills/, hooks/, PIV artefacts
```

## Ground rules

- **Email HTML is table-only.** `<table>/<tr>/<td>` for all layout; never `<div>`/`<p>` for layout (width/flex/float/columns). Text sits directly in `<td>` with inline `font-family`, `font-size`, `color`, `line-height`, `mso-line-height-rule:exactly`. **No `<p>` or `<h1>`–`<h6>`** — heading-like text = `<td>` with larger `font-size` + `font-weight:bold`. `<div style="text-align:center;">` inside a `<td>` is fine; `<div>` inside `<!--[if mso]>` ghost tables is expected. Spacing = `padding` on `<td>` only, no margins on text.
- **Sanitizer:** `sanitize_web_tags_for_email()` in `app/design_sync/sanitizers.py` strips every `<p>`/`<h*>` (merging styles into the parent `<td>`), converts layout divs, preserves MSO blocks. Assertions about "what the email renders" must account for it.
- **One HTML generation point for agents.** In structured-output mode, downstream agents return decision schemas (`app/ai/agents/schemas/*_decisions.py`), merged by `app/ai/agents/scaffolder/plan_merger.py`; `TemplateAssembler` (`app/ai/agents/scaffolder/assembler.py`) is the only HTML writer. Don't add a parallel path.
- **Agent output is sanitized per agent:** `sanitize_html_xss(html, profile=<agent>)` (`app/ai/shared.py`). User inputs to agents pass `scan_for_injection()` (`app/ai/security/prompt_guard.py`, modes warn/strip/block via `SECURITY__PROMPT_GUARD_MODE`).
- **Backend imports:** `get_logger` from `app.core.logging`, `get_db` from `app.core.database`, `TimestampMixin` from `app.shared.models`, `escape_like` from `app.shared.utils`. Roles: admin, developer, viewer.
- **Config:** nested Pydantic settings, `env_nested_delimiter="__"` (`DATABASE__URL`, `AI__PROVIDER`). `.env.example` is generated from Settings — change Settings, then `make .env.example` (CI fails on drift).
- **Linter safety:** Ruff TC (type-checking-import) rules are not selected. Keep it that way — TC auto-fix moves SQLAlchemy/Pydantic/datetime runtime imports under `TYPE_CHECKING` and breaks them. Never run `ruff --fix` with TC enabled. Note `make lint` runs `ruff format` + `ruff check --fix` and rewrites files.
- **Claims:** a number or guarantee in a plan, report, commit, comment or PR body is a claim. Tag each one `observed` (name the run/command that produced it), `derived` (show the arithmetic and the condition it assumes) or `expected` (not yet run). Figures copied from a plan into a report or PR are re-derived, not inherited. A figure under an "observed" heading that no run produced is a defect even when the arithmetic is right.

## Working principles

Elicited from the user 2026-09-27. The four general principles (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) live in `~/.claude/CLAUDE.md`; these are the email-hub bindings.

- **Plan when it spans or risks.** Write a plan in `.agents/plans/` for any change to more than one file, a migration, or the converter. A one-file fix goes straight to implement → validate.
- **Ambiguity stops the work.** If a requirement has more than one reasonable reading, ask with 2–3 options, recommended first. Never pick silently.
- **Stay in the ticket.** An unrelated bug found mid-task is logged (deferred-items entry if load-bearing, else a note in the report), not fixed inline.
- **Evidence = the real gate on real data.** "Works" means the Definition of Done gate ran on this head (tagged `observed`) against real fixtures: golden templates, component seeds, `data/debug` cases. Never synthetic email HTML.
- **Failed fix → research, not retry.** After one failed attempt, read the library/API or code path before trying again; never repeat the same approach. After two failures, stop and report.
- **One ticket = one branch = one draft PR.** Commit at each green checkpoint with a conventional message; show `git diff --stat origin/main...HEAD` before each commit.
- **DB: upgrade only.** The agent may write Alembic revisions and run `upgrade` locally. Never downgrade, squash, drop, truncate or touch Docker volumes (the PreToolUse hook enforces this); any destructive step needs the user's explicit OK in chat.
- **Converter changes carry full-corpus A3.** Report before/after A3 scores on the whole case corpus. A non-target regression beyond scorer jitter stops for the user's ratification before commit.
- **Show progress.** Keep a task list updated step by step; one-line status at each checkpoint.

## Commands

```bash
make dev              # backend :8891 + frontend :3100
make test             # backend unit tests (no integration/benchmark/visual/collab)
make check-full       # full local gate: lint(rewrites!) + mypy + pyright + tests + check-fe + security + migration lint + overlays + numeric lint + golden conformance + flag audit + env drift
make ci-fe            # frontend gate, mirrors CI: frozen install + lint + format:check + type-check + vitest
make eval-check       # eval gate: analysis + regression + calibration
make db-migrate       # alembic upgrade head
```

Full catalogue: `.claude/docs/commands.md` (its `dev` port and `check-fe` rows are stale).

## Definition of Done

- **Backend → `make check-full`** green, then `git diff` again: `make lint` inside it rewrites files.
- **Frontend → `make ci-fe`**, not `make check-fe` — `check-fe` swallows lint and format failures (`|| true`).
- **Agents/judges →** also the matching eval gate: `make eval-check`, `make eval-calibration-gate` (TPR/TNR drop > 5pp fails) or `make eval-golden` (deterministic). Per-agent regression tolerance is 3pp (`AGENT_REGRESSION_TOLERANCE`) — not optional.

## Workflow (PIV loop)

Research → Plan → Implement → Validate, one ticket per loop. Skills in `.claude/skills/` and commands in `.claude/commands/` carry their own descriptions.

| Artefact | Path |
|---|---|
| Implementation plans (≤ 700 lines; tables + `file:line`, not code blocks) | `.agents/plans/` |
| Implementation reports | `.claude/reports/` |
| PR reviews (`pr-<N>-review.md`) | `.claude/code-reviews/` |
| Execution reports | `.claude/execution-reports/` |
| System/evolution reviews + remedy ledger | `.claude/system-reviews/` |

- **Before planning or executing on an existing phase or file, grep `.agents/deferred-items.json`** (`.claude/rules/deferred-items.md`) and surface matching entries. If work overlaps an open deferred item, an active plan in `.agents/plans/`, or a parallel branch, stop and surface it before writing code.
- **Parallel work:** before committing, read `git diff` for leakage from other branches or uncommitted parallel work; stage only this task's files.
- **Git:** never commit on `main` (pre-commit `no-commit-to-branch`); conventional-commit messages (commit-msg hook).

## PR flow

`expected` — lands with the AI-layer import (plan `.agents/plans/ai-layer-import.md` D3/D4, S8 PR B); not live yet.
1. The agent opens every PR as a **draft**.
2. CI's `ready` job flips the draft to ready only when all checks pass on that head commit.
3. **Only the user merges.** The agent never runs `gh pr merge` or `gh pr ready`.

## On-demand context

| When touching | Read first |
|---|---|
| Backend Python (logging, AppError, layers) | `.claude/rules/backend.md` |
| Frontend (semantic tokens, SWR, Tailwind v4) | `.claude/rules/frontend.md` |
| Tests (markers, fixtures, factories) | `.claude/rules/testing.md` |
| Security / Semgrep triage | `.claude/rules/security.md` |
| API modules, QA checks, agents, design-system pipeline, Maizzle sidecar | `.claude/rules/architecture.md`, `.claude/docs/architecture-deep-dive.md` |
| Evals / QA engine / design system | `.claude/docs/eval-system-guide.md`, `qa-engine-guide.md`, `design-system-guide.md` |
| Deferred items (add / close) | `.claude/rules/deferred-items.md` + `.agents/deferred-items.json` |
| Large docs (`PRD.md`, `docs/TODO-completed*.md`, gitignored `TODO.md`) | jDocMunch `search_sections` → `get_section`, never `Read` whole; see `.claude/rules/doc-and-code-research.md` |
| Commit / PR / review conventions, log event names | `.claude/references/conventions.md`, `.claude/references/logging-standard.md` |
| Design-sync HTML generation plan | `.agents/plans/upgrade-design-sync-html-generation.md` |
| Tech debt | `TECH_DEBT_AUDIT.md` |

## Known environment issues

- External processes (linters, git hooks, background agents) may silently revert edits. After writing a file, confirm the change persisted.

## Compact instructions

Preserve: current task + plan path under `.agents/plans/`, modified files, test results, key decisions, active feature flag if gating new work.
