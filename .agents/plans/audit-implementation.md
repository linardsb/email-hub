# Plan: Code Quality & Security Audit Implementation

Source audit: `docs/email-hub-audit.md` (sections 3.1–3.13). Three phases by priority tier; one phase = one tracked deliverable. Total budget: ~3 weeks of focused work, gated by user approval between phases.

## Context

The audit graded the codebase 8/10 and identified 13 gaps across CI/CD, auth, secrets, container security, DAST, frontend, mutation testing, input validation, load testing, observability, dependency hygiene, migration safety, and secret rotation. **Research corrected several audit assumptions** — see "Audit corrections" below — so this plan implements only the *real* gaps, not the assumed ones.

## Audit corrections (do not implement)

The audit was written without read access to several files. Research established the following are **already done**:

| Audit claim | Reality | Citation |
|---|---|---|
| 3.1 "CI/CD unknown state" | CI exists with 6 jobs (backend lint/types/tests, frontend, SDK drift, migration lint, commit lint, e2e smoke) | `.github/workflows/ci.yml` |
| 3.2 "verify `algorithms=['HS256']` explicit" | Already explicit; module-level constant `_JWT_ALGORITHM = "HS256"` used at both encode and decode | `app/auth/token.py:18,52,76,141` |
| 3.6 "add `eslint-plugin-security`" | Already imported and active via `security.configs.recommended` | `cms/apps/web/eslint.config.mjs:4,28` |
| 3.6 "add Next.js security headers" | All recommended headers (HSTS, CSP, X-Frame, X-Content-Type, Referrer-Policy, X-XSS) present | `cms/apps/web/next.config.ts:7-48` |
| 3.10 "structured log aggregation" | Loki + Promtail + Grafana stack already wired | `docker-compose.observability.yml` |
| 3.12 "transactions in `run_migrations_online()`" | Already wrapped via `context.begin_transaction()` | `alembic/env.py:27,37` |

## Out of scope (note, do not implement here)

| Item | Why deferred | Owner |
|---|---|---|
| CSP `unsafe-inline`/`unsafe-eval` removal | Multi-week effort: requires nonces/hashes across every inline style/script. Audit only asked for header presence. | Separate plan |
| HS256 → RS256/EdDSA migration | Audit says "evaluate", not "implement". Treat as ADR decision. | ADR ticket |
| Auth test suite (`app/auth/tests/` is empty) | Substantive effort: ~30 test functions across token/service/routes/dependencies/repository. **Fork point — see Phase 2 §2.3.** | TBD by user |
| Quarterly process items (threat model, pen test, RLS review) | Process, not code | Security ops |
| `pip` CVE-2026-3219 (only outstanding pip-audit finding) | No fix released; document only | Phase 2 §2.6 |
| GitHub branch protection rules (audit 3.1: "require passing CI, require review, no force-push to main") | Requires GitHub admin (Settings → Branches), not code | User to configure manually post-Phase 1 once CI gates are stable |
| README CI badge (audit 3.1) | Trivial follow-up; one line addition to `README.md` after `ci.yml` is finalized | Phase 1 cleanup commit |

## Type-check baseline (rerun after every phase)

All six audit-target modules currently type-clean — every new error introduced is the audit's:

| Module | pyright | mypy |
|---|---|---|
| `app/auth/` | 0 | 0 |
| `app/core/config.py` + `app/core/exceptions.py` | 0 | 0 |
| `app/ai/security/` + `app/ai/shared.py` | 0 | 0 |

Gate per phase: `make types` returns 0 errors on touched modules.

## Test landscape (informs Phase 2 mutmut + load targets)

| Surface | Tests | Hypothesis | Factories | Notes |
|---|---|---|---|---|
| `app/auth/` | **0** (only `__init__.py`) | — | — | Mutmut blocked until tests exist |
| `app/qa_engine/` | 34 files | yes (`property_testing/`) | `make_qa_result/check/override` (`tests/conftest.py:12-65`) | Highest-value mutmut target |
| `app/connectors/` | 27 files | — | AsyncMock + `app.dependency_overrides` (`test_sync_routes.py:84-93`) | Second mutmut target |
| `app/design_sync/` + `app/streaming/` | property tests via Hypothesis | yes | — | Already mutation-resistant |
| Frontend | 0 unit (Vitest configured); 11 Playwright e2e specs | — | — | E2E suite is the only fail-on-error frontend test |
| Conventions (`.claude/rules/testing.md`) | All confirmed in code | — | — | New tests must follow: AsyncMock for db, factories, save/restore overrides, `clear_user_cache()`, `limiter.enabled = False` |

## Pre-commit `|| true` registry (Phase 1 §1.5 backlog source)

| Hook | File:line | Risk |
|---|---|---|
| Squawk migration lint | `.pre-commit-config.yaml:93` | Migration safety findings silently swallowed |
| Frontend ESLint | `.pre-commit-config.yaml:103` | Lint backlog hidden |
| Frontend Prettier | `.pre-commit-config.yaml:109` | Format drift accepted |
| CI ESLint | `.github/workflows/ci.yml:64` | Lint backlog hidden in CI too |
| CI Prettier | `.github/workflows/ci.yml:67` | Format drift accepted in CI too |

---

# Phase 1 — Critical (~5 days, split into 1a / 1b / 1c)

**Sub-phase split rationale:** §1.5 was originally scoped as "remove `|| true`", but pre-flight discovery (during planning) found the frontend tooling itself is broken — `next lint --max-warnings=0` errors under Next.js 16, and Prettier is not installed in any workspace `package.json`. This means removing `|| true` requires a frontend-lint migration first. To prevent §1.4 (`make ci`) from going red the moment it lands, Phase 1 is split:

| Sub-phase | Scope | Estimate | Independence |
|---|---|---|---|
| **1a — Security mechanical** | §1.1 Docker secrets, §1.2 JWT entropy, §1.3 Pillow guard | ~2 days | Each item is independent of the others and of 1b/1c. Can ship as 1 PR or 3 small PRs. |
| **1b — Frontend tooling spike** | §1.5 (lint migration + Prettier install + autofix + ESLint backlog triage) | ~2-3 days | Self-contained; touches only `cms/`. Must merge before 1c. |
| **1c — CI parity** | §1.4 `make ci` + `\|\| true` removal at all 5 sites + README CI badge | ~half day | Depends on 1b being merged so the new gates don't break CI on day 1. |

Total Phase 1: **~5 days**, gated by 1b completing before 1c.

## §1.1 Docker default-password fallbacks (audit 3.3) — Phase 1a

**Discovered architectural mismatch:** the Coolify production deploy reads `docker-compose.yml` (per `docs/deploy-hetzner-coolify.md:73,140`), not `docker-compose.prod.yml`. The audit's "fix prod compose" recommendation hardens a file the actual deploy doesn't use. Plan therefore hardens **both** files and treats `docker-compose.prod.yml` as deprecated.

**Files & changes:**

| File | Change | Lines |
|---|---|---|
| `docker-compose.yml` | `${VAR:-default}` → `${VAR:?VAR is required}` for all credentials | 8 (POSTGRES_PASSWORD), 38 (REDIS_PASSWORD redis-server), 44 (REDIS_PASSWORD healthcheck), 73 (DATABASE__URL), 103 (DATABASE__URL frontend), 104 (REDIS__URL), 107 (AUTH__DEMO_USER_PASSWORD) |
| `docker-compose.prod.yml` | **delete entirely** (dead code; not invoked anywhere — verified via `grep` of Makefile/.github/scripts/docs) | full file |
| `.env.example` | Verify all newly-required vars are documented; add any missing | as needed |
| `Makefile` | Add `bootstrap` target (auto-generate dev `.env` with random secrets) | new target |
| `Makefile:37,187` | Update `make dev` / `make dev-bg` to depend on `bootstrap` | 2 lines |

**`make bootstrap` implementation:**
```
bootstrap: ## Create .env with random dev secrets if missing (idempotent)
	@if [ ! -f .env ]; then \
		echo "Generating .env from .env.example with random dev secrets..."; \
		cp .env.example .env; \
		sed -i.bak "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$(openssl rand -base64 24 | tr -d '/+=' )|" .env; \
		sed -i.bak "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$$(openssl rand -base64 24 | tr -d '/+=' )|" .env; \
		sed -i.bak "s|^AUTH__JWT_SECRET_KEY=.*|AUTH__JWT_SECRET_KEY=$$(openssl rand -base64 48 | tr -d '/+=' )|" .env; \
		sed -i.bak "s|^AUTH__DEMO_USER_PASSWORD=.*|AUTH__DEMO_USER_PASSWORD=dev-$$(openssl rand -hex 8)|" .env; \
		rm -f .env.bak; \
		echo ".env created. Confirm it is gitignored before committing."; \
	else \
		echo ".env already exists, skipping bootstrap."; \
	fi

dev: bootstrap  ## Backend (:8891) + frontend (:3000)
	docker-compose up -d --build
```

**`.gitignore` check:** confirm `.env` is gitignored (it should be already; verify before shipping `make bootstrap`).

**CI gate:** `scripts/check-env-example.sh` (small bash) — extracts `${VAR:?...}` names from `docker-compose.yml`, diffs against `^VAR=` lines in `.env.example`, exits non-zero if any missing. Invoked from `make ci-be` and the `ci.yml` backend job:
```
#!/usr/bin/env bash
set -euo pipefail
required=$(grep -oE '\${[A-Z_]+:\?' docker-compose.yml | tr -d '${:?' | sort -u)
documented=$(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort -u)
missing=$(comm -23 <(echo "$required") <(echo "$documented"))
if [ -n "$missing" ]; then
  echo "Missing from .env.example: $missing" >&2
  exit 1
fi
```

**Verification:**
- `docker compose --env-file /dev/null config 2>&1 | grep "is required"` lists every credential variable
- `make bootstrap && make dev` works on a clean checkout (no pre-existing `.env`)
- `make bootstrap && make bootstrap` is idempotent (second run says "skipping")
- `bash scripts/check-env-example.sh` exits 0
- `git ls-files | grep -F docker-compose.prod.yml` returns empty (file deleted)

## §1.2 JWT secret entropy validation (audit 3.2) — Phase 1a

**Two-layer defense — independent validations that catch different failure modes:**

| Layer | Where | Catches | When it fires |
|---|---|---|---|
| `Field(min_length=32)` | `AuthConfig.jwt_secret_key` (`app/core/config.py:32`) | Short user-supplied secrets in any env | Every `Settings()` instantiation |
| `model_validator(mode="after")` on **root** `Settings` (~`app/core/config.py:870`) | Production sentinel — refuses default secret AND default demo password when `environment == "production"` | Only when env=production |

**Subtle bug to avoid (caught during planning):** the current default `"CHANGE-ME-IN-PRODUCTION"` is 23 chars. Adding `min_length=32` would break **every test** that uses default settings (most of the suite — only the `mock_settings` fixture overrides). Mitigation: lengthen the default placeholder so it passes the length check but still trips the production sentinel.

**Change at `app/core/config.py:32`:**
```
jwt_secret_key: str = Field(
    default="CHANGE-ME-IN-PRODUCTION-this-is-not-a-real-secret",  # 49 chars; passes min_length, trips prod sentinel
    min_length=32,
    description="HS256 signing key; ≥32 chars (256 bits) required.",
)
```

**Add validator on root `Settings` (after the nested-config field declarations, ~line 870):**
```
@model_validator(mode="after")
def _validate_production_secrets(self) -> "Settings":
    if self.environment == "production":
        if self.auth.jwt_secret_key.startswith("CHANGE-ME-IN-PRODUCTION"):
            raise ValueError("AUTH__JWT_SECRET_KEY must not be the default placeholder in production")
        if self.auth.demo_user_password == "admin":  # pragma: allowlist secret
            raise ValueError("AUTH__DEMO_USER_PASSWORD must not be 'admin' in production")
    return self
```

Place on root (not `AuthConfig`) because `environment` lives on root; `AuthConfig` can't see it.

**Why the `startswith` check** (not `==`): the dev `make bootstrap` target may keep the placeholder as-is for `make dev`, but a developer might rotate to a different placeholder. Sentinel match should be loose to catch all known-default variants.

**Test file `app/core/tests/test_config_security.py` (~5 tests):**
1. `environment="development"` + default jwt_secret_key + default demo_user_password → instantiates fine
2. `environment="production"` + default jwt_secret_key → raises `ValueError`
3. `environment="production"` + custom jwt_secret_key (≥32 chars) + `demo_user_password="admin"` → raises `ValueError` <!-- pragma: allowlist secret -->
4. `environment="production"` + custom jwt_secret_key + custom demo_user_password → instantiates fine
5. Any environment + jwt_secret_key shorter than 32 chars → raises `ValidationError` (Field-level)

Tests follow `app/core/tests/test_credentials.py` pattern (existing); use `monkeypatch.setenv` + `Settings()` rather than `get_settings()` to bypass the lru_cache. Existing `mock_settings` fixture sets `ENVIRONMENT="test"` (`conftest.py:45`) — confirmed not `"production"`, so the rest of the test suite is unaffected.

**Verification:** `uv run pytest app/core/tests/test_config_security.py && make types && uv run pytest -v -m "not integration"` (the last command confirms no other test broke from the longer default).

## §1.3 Pillow decompression-bomb guard (audit 3.8) — Phase 1a

**Problem:** `Image.MAX_IMAGE_PIXELS` unset → 11 `Image.open()` call sites accept images that can OOM the worker.

**Solution:** single shared helper, not 11 patches.

**New file:** `app/shared/imaging.py` (~20 lines):
```
from PIL import Image
MAX_IMAGE_PIXELS = 64_000_000  # ~64 MP — well under PIL default 89 MP, well above any legitimate email asset

def safe_image_open(source) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    return Image.open(source)
```

**Migrate 3 prod-critical sites:**
- `app/knowledge/processing.py:211`
- `app/templates/upload/image_importer.py:269`
- `app/design_sync/assets.py:54`

**Migrate remaining 8 sites:** grep `Image.open(` in `app/`, replace with `safe_image_open()`. Add `from PIL import Image` linter ban via Ruff `flake8-tidy-imports.banned-api` once migration complete (optional polish — defer if it lights up too many false positives).

**Test:** `app/shared/tests/test_imaging.py` — feed in a 100MP synthetic image, assert `Image.DecompressionBombError`.

**Verification:** `grep -r "Image.open(" app/ --include="*.py"` returns only `app/shared/imaging.py`.

## §1.5 Frontend tooling migration + `|| true` removal (audit 3.6) — Phase 1b

**Pre-flight discovery (executed during planning) — the wrappers are masking broken tooling, not just findings:**

| Hook | Pre-flight result | Implication |
|---|---|---|
| `cd cms && pnpm --filter web lint --max-warnings=0` | **errors** — Next.js 16 `next lint` does not accept `--max-warnings` (deprecated) | Migrate `lint` script away from `next lint` to direct `eslint .` invocation |
| `cd cms && pnpm exec prettier --check --ignore-unknown` | **errors** — `Command "prettier" not found` (binary not installed in any workspace `package.json`, only `cms/.prettierrc.json` config exists) | Add `prettier` + `prettier-plugin-tailwindcss` to workspace devDeps |
| `squawk` invocation | `command -v squawk` short-circuits when binary missing → hook silently passes | Verify Squawk install path in pre-commit env AND CI; verify `--exclude-rule` support before promoting to hard gate |

**Existing assets (no change needed):**
- `cms/apps/web/eslint.config.mjs:1-108` — already a flat config with explicit `nextPlugin`, `jsxA11y`, `security`, `reactHooks`, `eslint-config-prettier` (line 6). Migrating from `next lint` → `eslint .` loses no rules because `next lint` was just a thin wrapper around the same flat config.
- `cms/.prettierrc.json` — existing Prettier config with `semi:true`, `singleQuote:false`, `trailingComma:"all"`, `tabWidth:2`, `printWidth:100`, `prettier-plugin-tailwindcss` plugin. Reuse as-is.

### Phase 1b implementation steps

**Step 1 — Install Prettier in workspace.** Edit `cms/apps/web/package.json` devDeps:
```
"prettier": "^3.4.0",
"prettier-plugin-tailwindcss": "^0.6.0",
"eslint": "^9.20.0"   // if not already top-level (eslint config imports it)
```
Run `cd cms && pnpm install` to update lockfile.

Verify: `cd cms && pnpm exec prettier --version` prints `3.x.x`.

**Step 2 — Migrate `lint` script away from `next lint`.** Edit `cms/apps/web/package.json:9`:
```
"lint": "eslint .",
"lint:fix": "eslint . --fix",
"format": "prettier --write \"**/*.{ts,tsx,js,jsx,json,css,md}\" --ignore-unknown",
"format:check": "prettier --check \"**/*.{ts,tsx,js,jsx,json,css,md}\" --ignore-unknown",
```
Verify: `cd cms && pnpm --filter web lint` invokes ESLint directly and respects `eslint.config.mjs` (test by introducing a deliberate `==` violation — must error on `eqeqeq`).

**Step 3 — Verify the `--max-warnings=0` intent is preserved.** ESLint's flat-config equivalent is the CLI flag `--max-warnings 0`, which is supported. Update the lint script:
```
"lint": "eslint . --max-warnings 0",
```

**Step 4 — Run Prettier autofix across `cms/`.** This is potentially hundreds of files (the workspace has never had Prettier enforced). Run once, commit the diff as a separate "chore: prettier autofix workspace" commit so reviewers can scroll past it:
```
cd cms && pnpm exec prettier --write "**/*.{ts,tsx,js,jsx,json,css,md}" --ignore-unknown --ignore-path .gitignore
```
Verify: `cd cms && pnpm exec prettier --check ...` exits 0.

**Step 5 — Capture ESLint backlog.** Run the (now-functional) lint and count findings:
```
cd cms && pnpm --filter web lint > /tmp/eslint-backlog.log 2>&1; tail -3 /tmp/eslint-backlog.log
```
Decision branch on count:

| Backlog | Action |
|---|---|
| 0 errors / <10 warnings | Skip to step 7. |
| <50 findings total | Fix mechanically: `cd cms && pnpm --filter web lint:fix`, then review residue case-by-case. |
| ≥50 findings | Fix `eslint --fix`-able findings; for the rest, append rule + file:line to `docs/eslint-debt.md` AND add inline `// eslint-disable-next-line <rule> -- tracked in eslint-debt.md`. **Do not block on fixing all of them in this phase.** The goal is "wrapper-removable", not "zero ESLint debt". |

**Step 6 — Verify Squawk ignore mechanism + install path.** Run:
```
squawk --help 2>&1 | grep -iE "exclude|ignore|config"
which squawk || brew install squawk   # or document install in docs/dev-setup.md
```
Decision branch on Squawk capability:

| Squawk supports | Action |
|---|---|
| `--exclude-rule` and/or `.squawk.toml` config file | Create `.squawk.toml` ignoring rules that fire on immutable historical migrations; remove `\|\| true` at `.pre-commit-config.yaml:93`; add Squawk install to `docs/dev-setup.md` and to CI runner setup. |
| Per-file ignores only | Add `# squawk-ignore-file` comments to historical migrations; remove `\|\| true`. |
| **No ignore mechanism at all** | **Keep `\|\| true` at `.pre-commit-config.yaml:93` and document why in `docs/migration-debt.md`.** Squawk stays advisory. Do NOT block 1c on this. |

**Step 7 — Remove `|| true` at the verified-safe locations:**
- `.pre-commit-config.yaml:103` (frontend-lint) — only after step 5 passes locally
- `.pre-commit-config.yaml:109` (frontend-format) — only after step 4 + step 1 done
- `.github/workflows/ci.yml:64` (ESLint) — paired with above
- `.github/workflows/ci.yml:67` (Prettier) — paired with above
- `.pre-commit-config.yaml:93` (Squawk) — only if step 6 confirmed ignore mechanism

**Step 8 — Update CI to use the new script names.** Edit `.github/workflows/ci.yml:64,67`:
```
- name: ESLint
  run: cd cms && pnpm --filter web lint
- name: Prettier format check
  run: cd cms && pnpm --filter web format:check
```
(both with `|| true` already removed)

### Phase 1b acceptance

- [ ] `cd cms && pnpm exec prettier --version` returns 3.x
- [ ] `cd cms && pnpm --filter web lint` runs ESLint directly (not via `next lint`) and exits 0 (or with documented debt entries)
- [ ] `cd cms && pnpm --filter web format:check` exits 0
- [ ] No `|| true` remains in pre-commit/CI for frontend hooks
- [ ] Squawk decision documented (either ignore mechanism wired OR `|| true` retained with rationale)
- [ ] `docs/eslint-debt.md` exists (or empty if backlog was clean)

## §1.4 `make ci` target + README badge (audit 3.1) — Phase 1c

**Depends on Phase 1b** — must merge after 1b so the new gates don't immediately redline.

**Edit `Makefile`** (add target):
```
ci: ## Mirror CI exactly: lint, types, tests, security, frontend gates
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pyright
	uv run pytest -v -m "not integration" --cov=app --cov-report=term
	uv run bandit -c pyproject.toml -r app/
	uv run pip-audit --strict
	cd cms && pnpm install --frozen-lockfile
	cd cms && pnpm --filter web lint
	cd cms && pnpm --filter web format:check
	cd cms && pnpm --filter web type-check
	cd cms && pnpm --filter web test

ci-be: ## Backend-only CI mirror (skip pnpm install — faster iteration)
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pyright
	uv run pytest -v -m "not integration"
	uv run bandit -c pyproject.toml -r app/

ci-fe: ## Frontend-only CI mirror
	cd cms && pnpm install --frozen-lockfile
	cd cms && pnpm --filter web lint
	cd cms && pnpm --filter web format:check
	cd cms && pnpm --filter web type-check
	cd cms && pnpm --filter web test
```

The `ci-be` / `ci-fe` split exists because `make ci` includes `pnpm install --frozen-lockfile` (~20-40s) which devs will skip if forced on every backend-only iteration. Two narrower targets give them an opt-in.

**Add CI badge to `README.md`** (one-liner, after the title):
```
[![CI](https://github.com/<org>/email-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/<org>/email-hub/actions/workflows/ci.yml)
```
Substitute `<org>` with the actual GitHub organization at PR time.

**Coverage flag note:** `--cov=app --cov-report=term` in `make ci` is a placeholder until Phase 2 §2.5 sets the threshold. For now it just prints; Phase 2 swaps in `--cov-fail-under=N`.

### Phase 1c acceptance

- [ ] `make ci` passes locally on a clean checkout
- [ ] `make ci-be` and `make ci-fe` work as standalone targets
- [ ] README CI badge renders on GitHub
- [ ] No `|| true` anywhere in `Makefile`, `.pre-commit-config.yaml`, or `.github/workflows/ci.yml` for the targeted hooks
- [ ] Run `pre-commit run --all-files` end-to-end — exits 0 (with documented debt allowed)


## Phase 1 overall acceptance (rolls up 1a + 1b + 1c)

**1a (security mechanical):**
- [ ] `docker compose --env-file /dev/null config` fails with explicit "X is required" messages for every credential
- [ ] `git ls-files | grep -F docker-compose.prod.yml` returns empty (deleted)
- [ ] `make bootstrap && make dev` works on a clean checkout (no pre-existing `.env`); second `make bootstrap` is idempotent
- [ ] `bash scripts/check-env-example.sh` exits 0
- [ ] `app/core/tests/test_config_security.py` passes; pyright + mypy clean on `app/core/config.py`
- [ ] `grep -r "Image.open(" app/ --include="*.py"` returns only `app/shared/imaging.py`

**1b (frontend tooling spike):**
- [ ] `cd cms && pnpm --filter web lint` runs ESLint directly via `eslint .`, exits 0 (or with documented debt)
- [ ] `cd cms && pnpm --filter web format:check` exits 0
- [ ] `grep -n "|| true" .pre-commit-config.yaml .github/workflows/ci.yml` returns empty for frontend hooks
- [ ] Squawk decision documented (either ignore mechanism wired OR `|| true` retained with rationale in `docs/migration-debt.md`)
- [ ] `docs/eslint-debt.md` exists (or empty if backlog clean)

**1c (CI parity):**
- [ ] `make ci` passes locally on a clean checkout
- [ ] `make ci-be` and `make ci-fe` work as standalone targets
- [ ] README CI badge renders on GitHub
- [ ] `pre-commit run --all-files` exits 0

---

# Phase 2 — High priority (CI gates, 1–2 weeks)

New CI jobs and tooling; each step is independently shippable.

## §2.1 Trivy container vulnerability scanning (audit 3.4)

**Add to `.github/workflows/ci.yml`** as a new job after backend builds:
```
trivy:
  name: Trivy image scan
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - name: Build app image
      run: docker build -t email-hub:ci .
    - name: Build db image
      run: docker build -t merkle-db:ci -f db/Dockerfile db/
    - name: Trivy scan app
      uses: aquasecurity/trivy-action@0.28.0
      with:
        image-ref: email-hub:ci
        exit-code: 1
        severity: HIGH,CRITICAL
        ignore-unfixed: true
    - name: Trivy scan db
      uses: aquasecurity/trivy-action@0.28.0
      with:
        image-ref: merkle-db:ci
        exit-code: 1
        severity: HIGH,CRITICAL
        ignore-unfixed: true
```

**Pin base image digests** (audit also asks for this):
- `Dockerfile` line with `FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim` → resolve current digest with `docker buildx imagetools inspect ghcr.io/astral-sh/uv:python3.12-bookworm-slim` and pin: `FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:<digest>`
- `db/Dockerfile` `FROM pgvector/pgvector:pg16` → same treatment.
- Add Renovate config snippet so Renovate updates the digests with PRs.

**Risk:** first scan will likely surface base-image CVEs. Triage step before merging:
- If unfixed → `.trivyignore` entry with justification + expiration date.
- If fixed in newer base image → bump digest in same PR.

## §2.2 pip-audit in CI (audit 3.11)

**Already in dev deps** (`pyproject.toml` lists `pip-audit>=2.7.0`).

**Add to `ci.yml` backend job** after `pytest`:
```
- name: pip-audit
  run: uv run pip-audit --strict --ignore-vuln GHSA-<pip-self-cve-id>
```

**Document the pip self-CVE deferral** in `docs/dependency-debt.md`: CVE-2026-3219 (pip 26.0.1) — no fix available, ignore until upstream patches.

## §2.3 Mutation testing — qa_engine + connectors (audit 3.7)

**Fork point — surface to user before implementation:**

> **Auth (`app/auth/`) has zero tests** (only `__init__.py`). The audit asks mutmut to start with auth, but mutmut needs tests to mutate against. Two options:
>
> **A.** Write the auth test suite (~30 tests) in this plan as Phase 2 §2.3a, then run mutmut against auth in Phase 2 §2.3b. Adds ~3 days.
>
> **B.** Defer auth from this audit, run mutmut against `qa_engine/checks/` and `connectors/` only (61 existing tests, factories, Hypothesis already in place). Auth tests become a follow-up plan.
>
> **Default: option B.** Auth test suite is its own design effort and would dominate this plan.

**Implementation (option B):**

Add `mutmut>=3.0` to `[dependency-groups].dev` in `pyproject.toml`.

Create `mutmut_config.py` at repo root:
```
def init():
    import os
    os.environ["TESTING"] = "1"

paths_to_mutate = "app/qa_engine/checks/,app/connectors/"
runner = "uv run pytest -x -q -m 'not integration'"
tests_dir = "app/qa_engine/tests/,app/connectors/tests/"
```

Add `make mutate` target to Makefile. **Do not gate CI on mutmut** — run it monthly via scheduled workflow:
```
# .github/workflows/mutmut.yml
on:
  schedule: [{cron: '0 6 1 * *'}]  # first of each month
```

Outputs `.mutmut-cache`; commit results to `docs/mutation-report.md` for review.

**Runtime budget:** mutmut on the full `qa_engine/checks/` + `connectors/` surface against ~600 tests is ~10+ hours per run on a 4-core runner (exceeds GitHub Actions free-tier 6h job limit). Mitigations applied to `paths_to_mutate`: **start tightly scoped** to 2–3 high-criticality files (e.g. `qa_engine/checks/scoring.py` + `connectors/sync/protocol.py`), expand later. **Use `--rerun-all=false`** so subsequent runs only mutate changed files (mutmut 3.x caches results). If monthly job still exceeds budget, escalate to self-hosted runner.

**Acceptance:** first mutmut run completes within GitHub Actions job time limit; report file written; baseline mutation score recorded for trend tracking. No threshold enforced this phase.

## §2.4 `alembic check` standalone gate (audit 3.12)

**Pre-flight verification** (per advisor): with 44 migrations, run `uv run alembic upgrade head` against a fresh DB **manually** before promoting to gate. If it fails, fix migration ordering before adding the gate.

**New CI job in `ci.yml`:**
```
migrations:
  name: Migration safety
  runs-on: ubuntu-latest
  services:
    db:
      image: pgvector/pgvector:pg16
      env:
        POSTGRES_PASSWORD: ci-test
      ports: [5432:5432]
  steps:
    - uses: actions/checkout@v6
    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh
    - name: alembic upgrade head
      run: uv run alembic upgrade head
      env:
        DATABASE__URL: postgresql+asyncpg://postgres:ci-test@localhost:5432/postgres  # pragma: allowlist secret
    - name: alembic check
      run: uv run alembic check
      env:
        DATABASE__URL: postgresql+asyncpg://postgres:ci-test@localhost:5432/postgres  # pragma: allowlist secret
```

This runs on every PR independently of e2e-smoke (currently the only place migrations are exercised, post-approval).

## §2.5 pytest coverage baseline + ratchet (audit 3.1)

**Sequencing (per advisor — do not pick arbitrary threshold):**

1. **Measure** — `uv run pytest -m "not integration" --cov=app --cov-report=term | tail -5` → record total %.
2. **Set threshold** at `(measured − 1)%` rounded down (e.g., 67% measured → 66% threshold) in `pyproject.toml [tool.pytest.ini_options].addopts` as `--cov-fail-under=66`.
3. **Update CI** — `pytest -v -m "not integration"` → `pytest -v -m "not integration" --cov=app --cov-fail-under=66 --cov-report=term`.
4. **Track ratchet** — quarterly review can bump threshold by 1–2 percentage points.

**Acceptance:** baseline % committed to `docs/coverage-baseline.md`; CI green at baseline.

## §2.6 Document existing dependency-debt deferrals (audit 3.11, 3.13)

Single new file `docs/dependency-debt.md` lists every deferred SCA finding with: package, CVE, severity, why deferred, expected fix date, owner. Initial entries:
- `pip` 26.0.1 — CVE-2026-3219 — no upstream fix yet
- (any items surfaced by Trivy in §2.1)
- (any items surfaced by removing stale mypy ignores in §3.5)

## Phase 2 acceptance

- [ ] Trivy job green; both images scanned; digests pinned in Dockerfiles
- [ ] pip-audit job green; documented exceptions in `docs/dependency-debt.md`
- [ ] `make mutate` runs end-to-end; baseline score in `docs/mutation-report.md`
- [ ] Migrations job green on fresh DB; `alembic check` returns clean
- [ ] Coverage gate enforced at baseline %; documented in `docs/coverage-baseline.md`
- [ ] `make ci` updated to mirror new gates; passes locally

---

# Phase 3 — Medium priority (larger / partially out-of-code, scope-dependent)

These items have substantial setup; some require infra access (staging env, Sentry account). User confirmation needed per item before starting.

## §3.1 OWASP ZAP baseline DAST (audit 3.5)

**Prerequisite:** staging environment URL + auth credentials available to CI.

**New workflow** `.github/workflows/dast.yml`:
```
name: DAST baseline
on:
  schedule: [{cron: '0 4 * * 1'}]  # weekly Monday 04:00
  workflow_dispatch:
jobs:
  zap:
    runs-on: ubuntu-latest
    steps:
      - name: ZAP baseline scan
        uses: zaproxy/action-baseline@v0.13.0
        with:
          target: ${{ secrets.STAGING_URL }}
          rules_file_name: '.zap/rules.tsv'
          fail_action: true
```

**Add `.zap/rules.tsv`** to suppress known false positives (CSP `unsafe-inline` is acknowledged out-of-scope per top of plan).

**Authenticated scan** (separate, monthly): use ZAP with login script via `zap-full-scan.py -t URL -r report.html -z "auth.loginurl=...".

**Acceptance:** weekly baseline scan runs; HTML report uploaded as artifact; failures surface to `#security` Slack (if hook available) or GitHub issue.

## §3.2 Locust load testing — Maizzle + WebSocket (audit 3.9)

**Add `locust>=2.32` to dev deps.**

**New file `tests/load/locustfile.py`:**
```
from locust import HttpUser, task, between

class MaizzleBuilder(HttpUser):
    host = "http://localhost:3001"
    wait_time = between(1, 3)

    @task
    def build_template(self):
        self.client.post("/build", json={"source": <real-template-from-app/ai/templates/library/>})
```

Use **real golden templates** from `app/ai/templates/library/` (11 files: `newsletter_1col.html`, `promotional_hero.html`, etc.) as load payloads — never fabricate HTML (per memory rule).

**WebSocket CRDT load** — separate file `tests/load/locust_ws.py` using `locust-plugins` `SocketIOUser` against `pycrdt-websocket` endpoint.

**Run locally first** (`uv run locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 60s`), capture baseline RPS + p95 in `docs/load-baseline.md`.

**Do not gate CI** on load tests — run before each release as a `make load-test` target.

## §3.3 Sentry + OpenTelemetry observability (audit 3.10)

Two independent additions; can ship separately.

**Sentry (Python):**
- Add `sentry-sdk[fastapi]>=2.20` to deps.
- New `app/core/observability.py`: init Sentry in `app/main.py:lifespan` startup, only when `SENTRY__DSN` env var set (so dev runs without it).
- Settings group: `class SentryConfig(BaseModel): dsn: str | None = None; environment: str = "development"; traces_sample_rate: float = 0.1`.

**Sentry (Next.js):** `pnpm add @sentry/nextjs` in `cms/apps/web/`, run `npx @sentry/wizard@latest -i nextjs`. Source-map upload via Sentry CLI in CI (frontend job).

**OpenTelemetry:** `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-asyncpg` + `opentelemetry-exporter-otlp` to deps. Add to existing `app/core/observability.py`. Wire to Loki/Grafana via Tempo (extend `docker-compose.observability.yml`).

**Acceptance:** uncaught exception in dev surfaces in local Sentry (or self-hosted GlitchTip if user prefers); trace appears in Grafana for an HTTP request → Maizzle sidecar.

## §3.4 Secrets rotation procedures (audit 3.13)

**No code change for rotation mechanism in this phase** (JWT grace-period rotation deferred unless user asks).

**New doc** `docs/security/secret-rotation.md` covering each secret:
- DB password, Redis password, JWT secret, AES encryption key, Anthropic/OpenAI API keys
- For each: where stored, who has access, rotation procedure (step-by-step), estimated downtime, last-rotated date.

**Full-history secret scan** (one-shot):
```
uv run detect-secrets scan --all-files --baseline .secrets.baseline.full-history.json
```
Triage findings; if any real leaks: rotate the leaked secret, then `git filter-repo` or BFG to redact (separate, gated decision).

**Acceptance:** doc exists; full-history scan completed; any findings triaged.

## §3.5 mypy stub-gap audit (audit 3.11)

For each `[[tool.mypy.overrides]]` block at `pyproject.toml:207-276` (17 modules), test removability:

| Module | Line | Likely stale | Test |
|---|---|---|---|
| `slowapi` | 207-208 | unknown | remove → `make types` → revert if breaks |
| `redis` | 211-212 | likely stale (redis ≥5 has stubs) | same |
| `cachetools` | 215-216 | unknown | same |
| `gunicorn` | 219-220 | likely | same |
| `pgvector` | 223-224 | unknown | same |
| `pytesseract` | 227-228 | unknown | same |
| `docx` | 231-232 | python-docx ships py.typed | same |
| `fitz` | 235-236 | PyMuPDF ≥1.24 has stubs | same |
| `anthropic` | 239-240 | **likely stale (≥0.43 has py.typed)** | high-priority test |
| `cognee` | 243-244 | unknown | same |
| `yaml` | 247-248 | **likely stale (PyYAML ≥6 + types-PyYAML)** | high-priority test |
| `liquid` | 251-252 | unknown | same |
| `cryptography` | 255-256 | **likely stale (cryptography ships py.typed)** | high-priority test |
| `cssutils` | 259-260 | unknown | same |
| `hypothesis` | 263-264 | hypothesis ships py.typed | same |
| `mcp` | 267-268 | unknown | same |
| `croniter` | 275-276 | types-croniter exists | same |

**Procedure:** test removable in batches (3 modules per PR). Where a stub is missing, add `types-X` to deps if available (e.g. `types-croniter`, `types-PyYAML`).

**Acceptance:** override count reduced; each remaining override has a one-line comment justifying it.

## §3.6 Cognee dependency surface isolation (audit 3.11) — exploratory

**Investigate first, decide later.** Cognee pulls `litellm`, `onnx`, `pypdf` as transitives — all have had advisories. The audit suggests isolating cognee in a separate Docker service.

**Phase 3 §3.6 scope:** discovery only — read `app/knowledge/`, identify all cognee call sites, draft an ADR comparing in-process vs sidecar isolation. **No code changes** in this plan; ADR feeds a future plan.

## Phase 3 acceptance

- [ ] DAST workflow runs weekly against staging; report archived
- [ ] Locust scripts run locally; baseline RPS/p95 documented
- [ ] Sentry receives a test exception from both Python and Next.js
- [ ] `docs/security/secret-rotation.md` reviewed by user
- [ ] mypy override count reduced; remaining overrides justified inline
- [ ] Cognee isolation ADR drafted

---

# Files to Create

| Phase | File | Purpose |
|---|---|---|
| 1 | `app/shared/imaging.py` | `safe_image_open()` helper |
| 1 | `app/shared/tests/test_imaging.py` | Decompression-bomb test |
| 1 | `app/core/tests/test_config_security.py` | JWT secret + demo password validation |
| 1 | `docs/eslint-debt.md` | Tracked ESLint deferrals |
| 1 | `docs/migration-debt.md` | Tracked Squawk deferrals |
| 2 | `mutmut_config.py` | Mutation testing config |
| 2 | `.github/workflows/mutmut.yml` | Monthly mutation run |
| 2 | `docs/dependency-debt.md` | Deferred SCA findings |
| 2 | `docs/coverage-baseline.md` | Coverage threshold rationale |
| 3 | `.github/workflows/dast.yml` | Weekly ZAP scan |
| 3 | `.zap/rules.tsv` | ZAP false-positive suppressions |
| 3 | `tests/load/locustfile.py` | Maizzle load test |
| 3 | `tests/load/locust_ws.py` | WebSocket CRDT load test |
| 3 | `docs/load-baseline.md` | RPS/p95 baselines |
| 3 | `app/core/observability.py` | Sentry + OTEL init |
| 3 | `docs/security/secret-rotation.md` | Per-secret rotation procedures |

# Files to Modify

| Phase | File:line | Change |
|---|---|---|
| 1 | `docker-compose.yml:8,38,44,73,103,104,107` | `${VAR:-default}` → `${VAR:?VAR is required}` (covers actual Coolify deploy path) |
| 1 | `docker-compose.prod.yml` | **delete entire file** (dead code; not invoked anywhere) |
| 1 | `Makefile:37,187` + new `bootstrap` target | `make bootstrap` auto-generates dev `.env` with random secrets; `make dev` depends on it |
| 1 | `scripts/check-env-example.sh` (new) | Validates every `${VAR:?...}` in compose has matching `.env.example` entry |
| 1 | `app/core/config.py:32` | `Field(min_length=32)` + production sentinel validator |
| 1 | `app/knowledge/processing.py:211`, `app/templates/upload/image_importer.py:269`, `app/design_sync/assets.py:54` + 8 other `Image.open(` sites | `Image.open` → `safe_image_open` |
| 1 | `Makefile` | Add `ci` target |
| 1 | `.pre-commit-config.yaml:93,103,109` | Remove `\|\| true` |
| 1 | `.github/workflows/ci.yml:64,67` | Remove `\|\| true` |
| 2 | `.github/workflows/ci.yml` | Add `trivy`, `migrations` jobs; add pip-audit step; switch pytest to `--cov-fail-under=N` |
| 2 | `Dockerfile`, `db/Dockerfile` | Pin base image digests |
| 2 | `pyproject.toml [dependency-groups].dev` | Add `mutmut`, `locust` (Phase 3) |
| 2 | `pyproject.toml [tool.pytest.ini_options].addopts` | Add `--cov-fail-under=N` |
| 3 | `pyproject.toml:207-276` | Drop stale mypy `ignore_missing_imports` overrides |
| 3 | `app/main.py` lifespan | Init Sentry + OTEL |
| 3 | `cms/apps/web/` | `@sentry/nextjs` integration |

# Preflight Warnings (carried from existing test patterns)

- Tests must use `AsyncMock` for db sessions (`app/connectors/tests/test_export_fix.py:47` — example)
- New route tests must `limiter.enabled = False` (`app/connectors/tests/test_sync_routes.py:75-77` — example) and restore in teardown
- Save/restore `app.dependency_overrides` (`app/connectors/tests/test_sync_routes.py:84-86` — example)
- `clear_user_cache()` is autouse via root `conftest.py:20-24` — do not call manually
- Never fabricate email HTML in load tests; use `app/ai/templates/library/*.html` (11 real templates)
- Never use `Image.open` directly after Phase 1 — use `app/shared/imaging.py:safe_image_open`

# Security Checklist (every new endpoint or external surface)

- [ ] Auth: `Depends(get_current_user)` or `require_role(...)` — no public state-changing routes
- [ ] Rate limit: `@limiter.limit(...)` per `app/core/rate_limit.py` policy
- [ ] Input validation: Pydantic schema with explicit `Field(max_length=...)` for any free-text
- [ ] HTML inputs: route through `sanitize_html_xss(html, profile=...)` (`app/ai/shared.py:370`)
- [ ] LLM-prompt inputs: route through `scan_for_injection(text, mode=...)` (`app/ai/security/prompt_guard.py:102`)
- [ ] Image inputs: `safe_image_open()` (after Phase 1 §1.3)
- [ ] Errors: `AppError` subclass from `app/core/exceptions.py` — never bare `Exception`; never expose internal types in 500 responses
- [ ] Logging: `get_logger(__name__)` with `domain.action_state` event names (per `.claude/rules/backend.md`)
- [ ] Audit trail: state changes write to audit log (per audit "Audit trail on state-changing API calls")

# Verification (per phase)

After **every** phase:
- [ ] `make check` passes (= `make lint` + `make types` + `make test` + `make security-check` + golden conformance + flag audit)
- [ ] `make ci` passes locally (introduced in §1.4)
- [ ] Pyright errors = 0 on touched modules (baseline at top of plan)
- [ ] No new `|| true` introduced anywhere
- [ ] Type-check baselines re-confirmed for `app/auth/`, `app/core/config.py`, `app/core/exceptions.py`, `app/ai/security/`, `app/ai/shared.py`

After **Phase 1**:
- [x] `docker compose -f docker-compose.prod.yml --env-file /dev/null config` fails loudly
- [x] `app/core/tests/test_config_security.py` passes
- [x] Pillow guard active at all 11 sites; bomb test passes

After **Phase 2**:
- [x] Trivy CI job green (or all findings tracked in `dependency-debt.md`)
- [x] pip-audit CI job green
- [x] Coverage gate enforced
- [x] `alembic check` runs clean on fresh DB
- [x] First mutmut run completes; report committed

After **Phase 3**:
- [ ] DAST workflow scheduled and successful first run
- [ ] Sentry receives test exception
- [ ] mypy override count reduced (target: ≥3 of the 3 likely-stale removed)
- [ ] All new docs reviewed by user

---

# Open Questions for User

1. **Auth tests scope (Phase 2 §2.3 fork):** option B (defer auth, mutmut on qa_engine + connectors only) or option A (write auth suite first)? **Default: B.**
2. **Sentry hosting:** SaaS (sentry.io) or self-hosted GlitchTip? Affects Phase 3 §3.3 setup.
3. **Staging URL availability:** does CI have a staging URL it can hit for ZAP (Phase 3 §3.1)? If not, defer DAST until staging exists.
4. **Phase ordering authority:** OK to ship Phase 1 immediately as a single PR, or break into per-item PRs for review granularity?
