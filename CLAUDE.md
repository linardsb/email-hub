# CLAUDE.md

## Project Overview

Centralised email platform with AI agents. FastAPI backend, Next.js 16 frontend, PostgreSQL + Redis. Python 3.12+, strict MyPy + Pyright. **Vertical slice architecture** — features under `app/{feature}/`.

**Codebase map:** `app/` backend (VSA features) · `cms/` Next.js frontend · `services/` sidecars (`maizzle-builder`, `mock-esp`) · `alembic/` migrations · `.claude/` agent rules + docs · `.agents/` plans + deferred-items ledger.

## Definition of Done

Verify before declaring a change complete:

- **Backend → `make check-full`** (lint + types + tests + security + golden conformance + flag audit + migration lint).
- **Frontend → `make check-fe`** (lint + format + type-check + tests).
- **Agents/judges →** also the matching eval gate: `make eval-check` (analysis + regression), `make eval-calibration-gate` (TPR/TNR delta, 5pp threshold), or `make eval-golden` (deterministic CI). Per-agent regression tolerance is 3pp via `AGENT_REGRESSION_TOLERANCE` — not optional.

## Behavioral Guardrails

The four principles in `~/.claude/CLAUDE.md` (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) apply by default. How they bind in this repo:

- **Think Before Coding → grep `.agents/deferred-items.json` before any new plan or execution that touches an existing phase or file** (see `.claude/rules/deferred-items.md`). Surface matching entries in planning output. When TODO.md / PRD.md / `docs/TODO-completed.md` is involved, use jDocMunch `search_sections` per `.claude/rules/doc-and-code-research.md` — don't `Read` 95KB+ files speculatively.
- **Simplicity First → §Development Guidelines.** Plans in `.agents/plans/` capped at 700 lines, compact descriptions and `file:line` references rather than full code blocks. Deferred-items entries must be load-bearing — don't add subjective preferences. **Structured output mode** (Phase 11.22.8) is the simplicity bias for agents: 7 downstream agents return decision schemas, `TemplateAssembler` is the single HTML generation point. Don't add a parallel HTML-generation path.
- **Surgical Changes → §Parallel Work Awareness + §Linter Safety + §HTML Email Structure Rules.** Isolate only the changes relevant to the current phase/task; `git diff` before commit to catch leakage. Never run `ruff --fix` with TCH rules. Never re-introduce `<p>` or `<h1>`-`<h6>` tags into email templates — `sanitize_web_tags_for_email()` will strip them and your assertions about "what the email renders" will be wrong.
- **Goal-Driven Execution → §Definition of Done** is the verifiable success criterion for every change.

When uncertain whether work overlaps an open deferred item, an active plan in `.agents/plans/`, or another contributor's parallel branch, **stop and surface it** before writing code.

## Essential Commands

```bash
make dev          # Backend (:8891) + frontend (:3000)
make check        # Backend: lint + types + tests + security + golden + flag audit
make check-full   # check + migration lint (full backend gate)
make check-fe     # Frontend: lint + format + type-check + tests
make test         # Backend unit tests
make eval-check   # Eval gate (analysis + regression) — when touching agents/judges
```

Full catalogue (lint variants, evals, e2e, rendering, snapshots, DB, ontology): `.claude/docs/commands.md`.

## HTML Email Structure Rules

- **Layout:** `<table>/<tr>/<td>` for ALL structural layout. NEVER use `<div>`/`<p>` for layout (width, flex, float, columns).
- **Text content:** All text directly in `<td>` with inline styles. **NO `<p>` or `<h1>`-`<h6>` tags.** Each `<td>` must include `font-family`, `font-size`, `color`, `line-height`, and `mso-line-height-rule:exactly`.
- **Heading-like text:** Use `<td>` with larger `font-size` and `font-weight:bold` — no semantic heading tags.
- **Simple wrappers:** `<div style="text-align:center;">` inside `<td>` is fine. No layout CSS (width/flex/float) on div.
- **MSO conditionals:** Ghost table pattern for Outlook. `<div>` inside `<!--[if mso]>` blocks is expected.
- **Spacing:** `padding` on `<td>` only (universal safe combo). No margin on text elements.
- **Sanitizer:** `sanitize_web_tags_for_email()` in `app/design_sync/converter.py` — strips ALL `<p>` and `<h>` tags (merging styles into parent `<td>`), strips layout divs, preserves MSO blocks.
- See `.agents/plans/upgrade-design-sync-html-generation.md` for the full plan.

## Known Environment Issues

- External processes (linters, background agents, git hooks) may silently revert file edits. After writing/editing files, verify changes persisted before moving on. If changes disappear, re-apply and identify the reverting process.

## Linter Safety

- Ruff TCH auto-fix breaks runtime imports (SQLAlchemy, Pydantic, datetime). Never run `ruff --fix` with TCH rules enabled. Use `--no-fix` for TCH or exclude them entirely.

## Parallel Work Awareness

- Before committing, check `git diff` carefully for changes from other branches or uncommitted parallel work leaking into the current diff. Isolate only the changes relevant to the current phase/task.

## Development Guidelines

**Key imports:** `get_logger` from `app.core.logging`, `get_db` from `app.core.database`, `TimestampMixin` from `app.shared.models`, `escape_like` from `app.shared.utils`. Roles: admin, developer, viewer.

**Config:** Nested Pydantic settings, `env_nested_delimiter="__"` (e.g. `DATABASE__URL`, `AI__PROVIDER`).

**Plans:** Implementation plans in `.agents/plans/` must not exceed 700 lines. Use compact descriptions, tables, and `file:line` references — not full code blocks.

## Architecture

**9 AI Agents:** Scaffolder, Dark Mode, Content, Outlook Fixer, Accessibility, Personalisation, Code Reviewer, Knowledge, Innovation. All have 5-criteria judges + SKILL.md files. Structured output mode returns decision schemas merged via `plan_merger.py`.

**Per-Agent Sanitization:** `sanitize_html_xss(html, profile=)` applies agent-specific nh3 allowlists. 10 profiles in `app/ai/shared.py`. **Prompt Injection Guard:** `scan_for_injection()` in `app/ai/security/prompt_guard.py` scans user-supplied inputs (brief, HTML, knowledge docs) before they reach agents. 5 pattern categories, 3 modes (`SECURITY__PROMPT_GUARD_ENABLED/MODE`).

For full architecture details see `.claude/docs/architecture-deep-dive.md`. For architecture quick-reference see `.claude/rules/architecture.md`.

## Where to find things

| Need | File |
|------|------|
| Backend conventions (logging, AppError, layer responsibilities) | `.claude/rules/backend.md` |
| Frontend conventions (semantic tokens, SWR, Tailwind v4) | `.claude/rules/frontend.md` |
| API modules + QA gate (14 checks) + 9 agents + design system pipeline + Maizzle sidecar | `.claude/rules/architecture.md` |
| Security rules + Semgrep triage decision tree | `.claude/rules/security.md` |
| Test fixtures, integration markers, factory patterns | `.claude/rules/testing.md` |
| Token-efficient research with jDocMunch / jCodeMunch (TODO.md / PRD.md) | `.claude/rules/doc-and-code-research.md` |
| Deferred-items ledger (acceptance carry-forwards) | `.claude/rules/deferred-items.md` + `.agents/deferred-items.json` |
| Full architecture deep-dive | `.claude/docs/architecture-deep-dive.md` |
| Full `make` command catalogue | `.claude/docs/commands.md` |
| Active backlog | `TODO.md` — 95KB, query via `search_sections` |
| Per-subtask phase history | `docs/TODO-completed.md` (~150KB, phases 40+) + `docs/TODO-completed-archive-2025-h2.md` (~615KB, phases 0–39), query via `search_sections` |
| Product requirements | `PRD.md` — 27KB, query via `search_sections` |
| Tech-debt audit | `TECH_DEBT_AUDIT.md` |

## Roadmap

**Phases 0–49 complete.** Active backlog in `TODO.md`; per-phase history in `docs/TODO-completed.md` (phases 40+) and `docs/TODO-completed-archive-2025-h2.md` (phases 0–39) — query via jDocMunch `search_sections`, never `Read` directly.

## Compact instructions

Preserve: current task + plan path under `.agents/plans/`, modified files, test results, key decisions, active feature flag if gating new work.
