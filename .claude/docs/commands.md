# Command Reference

Full `make` target catalogue for merkle-email-hub. The common targets (`dev`, `check`,
`check-full`, `check-fe`, `test`, `eval-check`) are inlined in the root `CLAUDE.md`;
everything else lives here. Run from the repo root.

## Dev & core gates

| Command | Purpose |
|---------|---------|
| `make dev` | Backend (:8891) + frontend (:3000) |
| `make check` | All backend checks (lint + types + tests + security + golden conformance + flag audit) |
| `make check-full` | `make check` + migration lint (full backend gate) |
| `make check-fe` | Frontend lint + format + type-check + tests |
| `make test` | Backend unit tests |

## Lint, types, security

| Command | Purpose |
|---------|---------|
| `make lint` | Format + lint (ruff — 26 rule sets) |
| `make lint-fe` | Format + lint frontend (ESLint + Prettier) |
| `make types` | mypy + pyright (both strict) |
| `make security-check` | Ruff Bandit security rules |
| `make lint-numeric` | Falsy-numeric anti-pattern check (design_sync) |
| `make lint-polling` | Check for hardcoded polling intervals in hooks |
| `make migration-lint` | Squawk PostgreSQL migration safety |
| `make install-hooks` | Install pre-commit hooks (format, lint, security, secrets, commit msg) |

## Tests & benchmarks

| Command | Purpose |
|---------|---------|
| `make bench` | Performance benchmarks (CSS pipeline) |
| `make test-collab` | CRDT collaboration tests (convergence + Hypothesis property-based) |
| `make snapshot-test` | Snapshot regression tests (included in `make test`; standalone convenience) |
| `make snapshot-capture CASE=5` | Capture converter output for visual review |
| `make snapshot-visual` | Visual fidelity metrics (requires Playwright, separate from CI) |

## Golden / conformance

| Command | Purpose |
|---------|---------|
| `make golden-conformance` | Golden template conformance gate (design_sync) |
| `make flag-audit` | Feature flag lifecycle audit (warns >90d, errors >180d) |

## Evals

| Command | Purpose |
|---------|---------|
| `make eval-full` | Full eval pipeline (requires LLM) |
| `make eval-check` | Eval gate (analysis + regression) |
| `make eval-golden` | CI golden test (deterministic, no LLM) |
| `make eval-qa-coverage` | Deterministic micro-judges coverage |
| `make eval-corrections` | Generate judge correction YAML from calibration disagreements |
| `make eval-calibration-gate` | Calibration regression gate (TPR/TNR delta check) |
| `make eval-knowledge` | Generate calibration insights for Knowledge agent RAG |
| `make eval-adversarial` | Adversarial eval cases (hostile inputs across 7 attack types) |

## E2E & rendering

| Command | Purpose |
|---------|---------|
| `make e2e-report` | Open last Playwright HTML report |
| `make e2e-smoke` | Smoke E2E tests (@smoke tagged, Chromium only) |
| `make e2e-all-browsers` | E2E tests on all browsers (Chromium + Firefox + WebKit) |
| `make rendering-baselines` | Regenerate visual regression baselines |
| `make rendering-regression` | Run visual regression tests vs baselines |

## DB & ontology

| Command | Purpose |
|---------|---------|
| `make db-migrate` | Run migrations |
| `make db-squash` | Squash migrations to single baseline (destructive, confirmation required) |
| `make sync-ontology` | Sync ontology YAML → sidecar JSON |
