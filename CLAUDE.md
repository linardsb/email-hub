# CLAUDE.md

## Project Overview

Centralised email platform with AI agents. FastAPI backend, Next.js 16 frontend, PostgreSQL + Redis. Python 3.12+, strict MyPy + Pyright. **Vertical slice architecture** — features under `app/{feature}/`.

## Behavioral Guardrails

The four principles in `~/.claude/CLAUDE.md` (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) apply by default. How they bind in this repo:

- **Think Before Coding → grep `.agents/deferred-items.json` before any new plan or execution that touches an existing phase or file** (see `.claude/rules/deferred-items.md`). Surface matching entries in planning output. When TODO.md / PRD.md / `docs/TODO-completed.md` is involved, use jDocMunch `search_sections` per `.claude/rules/doc-and-code-research.md` — don't `Read` 95KB+ files speculatively.
- **Simplicity First → §Development Guidelines.** Plans in `.agents/plans/` capped at 700 lines, compact descriptions and `file:line` references rather than full code blocks. Deferred-items entries must be load-bearing — don't add subjective preferences. **Structured output mode** (Phase 11.22.8) is the simplicity bias for agents: 7 downstream agents return decision schemas, `TemplateAssembler` is the single HTML generation point. Don't add a parallel HTML-generation path.
- **Surgical Changes → §Parallel Work Awareness + §Linter Safety + §HTML Email Structure Rules.** Isolate only the changes relevant to the current phase/task; `git diff` before commit to catch leakage. Never run `ruff --fix` with TCH rules. Never re-introduce `<p>` or `<h1>`-`<h6>` tags into email templates — `sanitize_web_tags_for_email()` will strip them and your assertions about "what the email renders" will be wrong.
- **Goal-Driven Execution → `make check-full` is the verifiable success criterion for backend changes; `make check-fe` for frontend.** When you touch agents or judges, also run the matching eval gate: `make eval-check` (analysis + regression), `make eval-calibration-gate` (TPR/TNR delta, 5pp threshold), or `make eval-golden` (deterministic CI). Per-agent regression tolerance is 3pp via `AGENT_REGRESSION_TOLERANCE` — not optional.

When uncertain whether work overlaps an open deferred item, an active plan in `.agents/plans/`, or another contributor's parallel branch, **stop and surface it** before writing code.

## Essential Commands

```bash
make dev             # Backend (:8891) + frontend (:3000)
make check           # All checks (lint + types + tests + security + golden conformance + flag audit)
make check-full      # All checks + migration lint
make golden-conformance  # Golden template conformance gate (design_sync)
make flag-audit      # Feature flag lifecycle audit (warns >90d, errors >180d)
make test            # Backend unit tests
make bench           # Performance benchmarks (CSS pipeline)
make test-collab     # CRDT collaboration tests (convergence + Hypothesis property-based)
make lint            # Format + lint (ruff — 26 rule sets)
make lint-fe         # Format + lint frontend (ESLint + Prettier)
make types           # mypy + pyright (both strict)
make check-fe        # Frontend lint + format + type-check + tests
make security-check  # Ruff Bandit security rules
make lint-numeric    # Falsy-numeric anti-pattern check (design_sync)
make lint-polling    # Check for hardcoded polling intervals in hooks
make migration-lint  # Squawk PostgreSQL migration safety
make install-hooks   # Install pre-commit hooks (format, lint, security, secrets, commit msg)
make db-migrate      # Run migrations
make db-squash       # Squash migrations to single baseline (destructive, confirmation required)
make eval-full       # Full eval pipeline (requires LLM)
make eval-check      # Eval gate (analysis + regression)
make eval-golden     # CI golden test (deterministic, no LLM)
make eval-qa-coverage # Deterministic micro-judges coverage
make eval-corrections # Generate judge correction YAML from calibration disagreements
make eval-calibration-gate # Calibration regression gate (TPR/TNR delta check)
make eval-knowledge  # Generate calibration insights for Knowledge agent RAG
make eval-adversarial # Adversarial eval cases (hostile inputs across 7 attack types)
make sync-ontology   # Sync ontology YAML → sidecar JSON
make e2e-report      # Open last Playwright HTML report
make e2e-smoke         # Smoke E2E tests (@smoke tagged, Chromium only)
make e2e-all-browsers # E2E tests on all browsers (Chromium + Firefox + WebKit)
make rendering-baselines  # Regenerate visual regression baselines
make rendering-regression # Run visual regression tests vs baselines
make snapshot-test        # Snapshot regression tests (included in make test; standalone convenience)
make snapshot-capture CASE=5  # Capture converter output for visual review
make snapshot-visual      # Visual fidelity metrics (requires Playwright, separate from CI)
```

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

Backend: `app/` (VSA features). Frontend: `cms/`. Sidecars: `services/maizzle-builder/`, `services/mock-esp/`. Migrations: `alembic/`.

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
| Active backlog | `TODO.md` — 95KB, query via `search_sections` |
| Per-subtask phase history | `docs/TODO-completed.md` (~150KB, phases 40+) + `docs/TODO-completed-archive-2025-h2.md` (~615KB, phases 0–39), query via `search_sections` |
| Product requirements | `PRD.md` — 27KB, query via `search_sections` |
| Tech-debt audit | `TECH_DEBT_AUDIT.md` |

## Roadmap

**Phases 0–49 complete.** Per-subtask history: phases 40+ live in `docs/TODO-completed.md` (~150KB), phases 0–39 in `docs/TODO-completed-archive-2025-h2.md` (~615KB). Query via jDocMunch `search_sections` — never `Read` the archive directly.

Recent themes:
- **P47 — VLM visual verification loop + component library expansion (89→150 components).** Render→compare→correct iteration with deterministic correction applicator. Fidelity ladder: ~85% (P40) → ~93% (P41) → ~97% (P47 verify loop) → ~99% (P47 component expansion).
- **P48 — Tree-mode scaffolder + QA meta-eval + MCP cache (DAG/evaluator/hooks parked).** Shipped to `app/`: `EmailTree` schema + deterministic `TreeCompiler` (`app/components/tree_schema.py`, `tree_compiler.py` — 48.6/48.8); scaffolder tree mode (`app/ai/agents/scaffolder/tree_builder.py`, gated by `AI__SCAFFOLDER_TREE_MODE` — 48.7); QA meta-evaluation framework + synthetic adversarial generator (`app/qa_engine/meta_eval.py`, `synthetic_generator.py` — 48.9/48.10); MCP response cache + schema compression (`app/mcp/optimization.py` — 48.11); standalone proactive failure-warning extraction (`app/knowledge/proactive_qa.py` — 48.12, pipeline-injection seam dropped). **Parked to `prototypes/ai-pipeline/`** (commit `8f7ca91f`, F008/F009, see `docs/phase-48-status.md`): DAG pipeline executor + artifacts + contracts (48.1–48.5), `EvaluatorAgentService` + adversarial gate, agent execution hook system + builtins (48.13). Re-import gated on producing an evaluator calibration baseline.
- **P49 — design-sync converter structural fidelity.** Sibling/repeating-group detection, content-group role hints, expanded token overrides + CTA-specific tokens, Figma node-scoped token sync, tree-bridge converter output, Pydantic regression manifest.
- **P42–46 ops + quality plumbing.** ETag + smart polling + SWR presets; judge corrections + calibration regression gate + adversarial eval; cron scheduler + multi-channel notifications + Redis-backed debouncer; credential rotation pool + plugin connector bridge.

Active work continues in `TODO.md`.

## Compact instructions

Preserve: current task + plan path under `.agents/plans/`, modified files, test results, key decisions, active feature flag if gating new work.
