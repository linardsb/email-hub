# Plan: tech-debt-19 — Backend sweep (F033/F035/F049/F057/F059/F060/F070)

## Context

Session 19 bundles 7 backend tech-debt items into one branch (`chore/tech-debt-19-backend-sweep`). State-of-the-world check before writing this plan turned up two **already-shipped** items the upstream task description still listed as "needs only the CI gate":

- **F033** is closed. `make check-env-drift` already runs `scripts/generate-env-example.py` against `.env.example` and gates `make check`/`make check-full` (CI line 43, Makefile L28). The original audit comment ("CI parity check") refers to the Settings-vs-.env.example diff, which is what this gate already does.
- **F049** is partially shipped. The `sdk-check` CI job (ci.yml L86–127) exports the OpenAPI spec via `scripts/export-openapi.py` (which calls `app.openapi()` on the in-process FastAPI app) and fails on `git diff cms/packages/sdk/`. The original task says "live OpenAPI from **booted** backend vs snapshot" — the upgrade is to fetch from a running uvicorn rather than the static app object, which catches middleware-injected schema differences.
- **F061** is closed (`app/shared/color.py` exists). Drop from the plan.

This leaves **5 real items**: F035 (flag cull), F049 upgrade (live-fetch OpenAPI), F057 (migration squash — maintenance-window-only), F059 (structlog routing of exception logging + `engine.echo`), F060 (trace module consolidation), F070 (AgentRequest Protocol). F033 stays in the plan as a **closure-only** step (mark as done in the audit doc).

The current branch is `tech-debt/pyright-restore-deprecated` with uncommitted work (9 modified files). The execute step must branch from `main`, not from the current working tree.

## Sequencing & PR Strategy

7 features in 1 PR is too risky. Cluster into 3 PRs on the same branch, each landing independently:

1. **PR-A (low risk, parallel-safe):** F033 (closure note), F049 upgrade, F059, F070
2. **PR-B (medium risk, sequential after PR-A):** F060 (with shim layer)
3. **PR-C (high risk, sequential after PR-B):** F035 (flag cull)
4. **F057 → runbook only.** `make db-squash` is destructive and requires a maintenance window. This plan produces a runbook + dry-run validation script, not the destructive operation itself.

Gate after each PR: `make check-full`. F035 also: `make flag-audit` must pass.

## Files to Create / Modify

### PR-A (F033 closure + F049 + F059 + F070)

| File | Change | Feature |
|------|--------|---------|
| `TECH_DEBT_AUDIT.md` | Mark F033 closed (gate exists), F049 upgraded | F033, F049 |
| `scripts/export-openapi.py` | Add `--live` mode that fetches from a booted uvicorn | F049 |
| `.github/workflows/ci.yml` | `sdk-check` job uses `--live` flag | F049 |
| `app/core/exceptions.py` | Route `app_exception_handler` log through `logger.exception` with `redact_event_dict` already applied via configured structlog | F059 |
| `app/core/config/database.py` | Add explicit `echo: bool = False` comment confirming structlog-bypass concern; keep default off | F059 |
| `app/core/database.py` | Wrap `engine.echo=True` paths so SQL logs route via structlog if ever enabled (or document that echo stays off) | F059 |
| `app/ai/agents/types.py` (new) | `AgentRequest`, `RuntimeAgentRequest` Protocols | F070 |
| `app/ai/agents/base.py` | Replace 9 `getattr(request, ...)` with typed access; method signatures updated to `RuntimeAgentRequest \| Any` | F070 |
| `app/ai/agents/tests/test_agent_request_protocol.py` (new) | Protocol satisfaction tests for all 9 concrete request schemas | F070 |

### PR-B (F060 trace module consolidation)

| File | Change | Feature |
|------|--------|---------|
| `app/design_sync/traces/__init__.py` (new) | Public re-exports | F060 |
| `app/design_sync/traces/writer.py` (new) | `TraceWriter` class | F060 |
| `app/design_sync/traces/converter.py` (new) | `build_trace`, `compute_quality_score`, `format_conversion_quality`, `build_conversion_metadata`, `extract_conversion_insights` | F060 |
| `app/design_sync/traces/regression.py` (new) | `load_traces`, `compute_aggregate_metrics`, `load_baseline`, `save_baseline`, `detect_regressions`, `run_converter_regression` | F060 |
| `app/design_sync/traces/correction.py` (new) | `CorrectionTracker`, `extract_correction_diffs`, dataclasses | F060 |
| `app/design_sync/converter_traces.py` | Thin shim → re-export from `traces.converter` + `traces.writer` | F060 |
| `app/design_sync/converter_insights.py` | Thin shim | F060 |
| `app/design_sync/converter_memory.py` | Thin shim | F060 |
| `app/design_sync/correction_tracker.py` | Thin shim | F060 |
| `app/design_sync/converter_regression.py` | Thin shim | F060 |
| `app/design_sync/tests/test_traces_*` (new) | Tests for `TraceWriter` unified API | F060 |

### PR-C (F035 flag cull)

| File | Change | Feature |
|------|--------|---------|
| `app/core/config/design_sync.py` | Drop ~36 fields (66→30) — see kill list below | F035 |
| `app/core/config/__init__.py` | Re-export changes if any nested-struct introduced | F035 |
| `app/design_sync/tuning.py` (new, optional) | Module-level constants for threshold knobs (≈10) — replaces removed env-tunable fields | F035 |
| `.env.example` | Regenerated via `make .env.example` (CI gate enforces parity) | F035 |
| `data/feature-flags.yaml` | Remove dropped flags (used by `scripts/flag-audit.py`) | F035 |
| `app/design_sync/*.py` (~10 callsites) | Replace `settings.design_sync.<flag>` with constant | F035 |
| `app/core/tests/test_config_design_sync.py` (new or amend) | Assert post-cull field count + presence of survivors | F035 |

### F057 runbook (not executed)

| File | Change | Feature |
|------|--------|---------|
| `.agents/plans/tech-debt-19-runbook-db-squash.md` (new) | Step-by-step maintenance-window runbook | F057 |
| `scripts/squash-migrations-dryrun.sh` (new) | Dry-run that runs `db-squash` flow against a throwaway DB and asserts `alembic check` exits 0 | F057 |

## Implementation Steps

### Setup

1. Branch from `main` (NOT from `tech-debt/pyright-restore-deprecated`): `git checkout main && git pull && git checkout -b chore/tech-debt-19-backend-sweep`.
2. Confirm clean state: `git status` shows no staged/modified files.
3. Run `make check-full` once to confirm baseline green.

---

### F033 — Closure note (already shipped)

1. In `TECH_DEBT_AUDIT.md`, locate the F033 row.
2. Update status to "closed (2026-05-13)" with a one-line note: "`make check-env-drift` (Makefile L28) runs `scripts/generate-env-example.py` and fails on diff; gate runs in `make check`/`check-full` and CI step `.env.example drift gate`."
3. No code change.

---

### F049 — Live-fetch OpenAPI for SDK gate

**Current state:** `scripts/export-openapi.py` calls `app.openapi()` directly on the imported FastAPI app. Static; does not exercise middleware or lifespan.

**Upgrade:** Add `--live` mode that boots uvicorn on an ephemeral port, fetches `GET /openapi.json`, then exits.

1. In `scripts/export-openapi.py`:
   - Add CLI flag `--live` (default off — keep backward compat).
   - When `--live`: import `uvicorn`, start `app.main:app` in a subprocess (or `multiprocessing.Process`) on a free port; poll `GET /openapi.json` with httpx until 200; write response body to `--output`; tear down.
   - When not `--live`: keep current `app.openapi()` path.
2. In `.github/workflows/ci.yml` `sdk-check` job, swap:
   - Old: `run: uv run python scripts/export-openapi.py`
   - New: `run: uv run python scripts/export-openapi.py --live`
3. Verify the generated `openapi.json` is byte-identical to the static path (it should be — middleware doesn't currently alter the schema). If it differs, the live mode is correctly catching a real discrepancy that the static gate missed; investigate before merging.
4. Add a one-line note to the CI step explaining why `--live` is preferred.
5. Update `TECH_DEBT_AUDIT.md` F049 row to "upgraded to live-fetch (2026-05-13)".

**Risk:** Booting the app needs DB connectivity. CI already runs Postgres for the `migrations` job — reuse the service container or guard the boot with `DATABASE__URL=sqlite+aiosqlite:///:memory:` if Settings allows. Confirm by reading `app/main.py` lifespan; if startup hard-requires a real DB, gate `--live` behind a service container.

---

### F059 — Route exception logging through structlog

**Current state:**
- `app/core/exceptions.py:111` uses `logger.error(...)` which already routes through structlog (`get_logger` is structlog-bound).
- `app/core/database.py:24` passes `settings.database.echo` to `create_async_engine` — when True, SQLAlchemy logs raw SQL via stdlib `logging`, bypassing structlog's `redact_event_dict` processor.
- Default is `echo: bool = False`. Risk is non-zero only if someone flips it in `.env` for debugging.

**Steps:**
1. In `app/core/exceptions.py:111`, switch `logger.error` to `logger.exception` so the traceback is attached structurally rather than via `exc_info=True` (structlog-idiomatic). Drop the `exc_info=True` arg.
2. Verify both 401/423 handlers (`invalid_credentials_handler` line 145, `account_locked_handler` line 163) use `logger.warning` consistently — they do, no change needed.
3. In `app/core/database.py`, where `engine.echo=settings.database.echo` is passed:
   - Add a runtime guard: if `settings.database.echo` is True, route stdlib `logging.getLogger("sqlalchemy.engine")` through a structlog handler so SQL output gets PII-redacted before emission.
   - Implementation: add `_route_sqlalchemy_to_structlog()` helper in `app/core/database.py` invoked when `echo=True`. Use `logging.getLogger("sqlalchemy.engine").addHandler(structlog_handler)` and `propagate=False`. Reference: `structlog.stdlib.ProcessorFormatter`.
4. Test: `tests/core/test_database_echo_routes_via_structlog.py` — enable echo in a fixture, run a trivial query, assert the captured log line went through `redact_event_dict`.
5. Document in `app/core/config/database.py` `echo` field comment: "When True, SQLAlchemy SQL logs are routed through structlog so `redact_event_dict` still applies."

**Note:** The CLAUDE.md/database.py comment already flags the concern; this step closes it.

---

### F070 — AgentRequest(Protocol)

**Current state (from research):**
- 9 `getattr(request, ...)` calls in `app/ai/agents/base.py` access: `output_mode`, `run_qa`, `_user_input_fields[*]` (subclass-defined loop), `user_id`, `blueprint_run_id`, `prompt_version`, `effective_tier`, `client_id`.
- Method signatures use `request: Any`.
- Concrete request schemas (`ScaffolderRequest`, `DarkModeRequest`, etc.) declare `run_qa`/`output_mode`/`stream` but **not** orchestrator-injected fields (`user_id`, `blueprint_run_id`, `prompt_version`, `effective_tier`, `client_id`). Those are populated at runtime by the Blueprint engine.

**Steps:**

1. Create `app/ai/agents/types.py`:

   ```python
   from typing import Protocol, runtime_checkable

   @runtime_checkable
   class AgentRequest(Protocol):
       run_qa: bool
       output_mode: str
       stream: bool

   @runtime_checkable
   class RuntimeAgentRequest(AgentRequest, Protocol):
       user_id: str | None
       blueprint_run_id: str | None
       prompt_version: str | None
       effective_tier: str | None
       client_id: str | None
   ```

2. In `app/ai/agents/base.py`:
   - Add `from app.ai.agents.types import RuntimeAgentRequest` at top.
   - Replace `request: Any` with `request: RuntimeAgentRequest` on `process`, `_process_impl`, `_get_output_mode`, `_should_run_qa`, `_scan_request`.
   - **Keep** `_build_user_message(self, request: Any)` as `Any` because subclasses need to access agent-specific fields (brief/html/text) not on the protocol — narrow via `isinstance` or `cast` inside each subclass override.
   - Replace each `getattr(request, "<field>", <default>)`:
     - Line 80: `request.output_mode if hasattr(request, 'output_mode') else self.output_mode_default` — actually since `output_mode` is in `AgentRequest` Protocol and all concrete schemas declare it, drop the fallback: `request.output_mode`.
     - Line 170: same for `run_qa`.
     - Line 251: stays as `getattr(request, field, "")` because `field` is a runtime string from `self._user_input_fields` — this is by-design dynamic; keep but type-annotate as `cast(str, getattr(request, field, ""))`.
     - Lines 328/329/331/405/412/553: optional orchestrator fields — replace with direct attribute access on `RuntimeAgentRequest` (which declares them as `str | None`). For non-runtime requests passing in via tests, `runtime_checkable` Protocol lets `isinstance(request, RuntimeAgentRequest)` guard the access.
3. Add `app/ai/agents/tests/test_agent_request_protocol.py`:
   - For each concrete request schema (Scaffolder, DarkMode, Content, Outlook, Accessibility, Personalisation, CodeReviewer, Knowledge, Innovation):
     - Instantiate with minimal required fields + the orchestrator fields injected via `model_copy(update={...})` or `setattr` (depending on whether Pydantic models forbid extra fields; check `model_config`).
     - Assert `isinstance(req, AgentRequest)` and `isinstance(req, RuntimeAgentRequest)`.
4. **Watch:** Pydantic `model_config = ConfigDict(extra="forbid")` would block setting `user_id` via `setattr`. If any schema forbids extras, the Blueprint engine must be injecting via a wrapper (likely `NodeContext.metadata`), not direct attribute set. Verify before adding tests:
   - `grep -n "extra=" app/ai/agents/*/schemas.py`
   - If `extra="forbid"`: the protocol implementation must read from a wrapper (e.g., `AgentRequestEnvelope(request, runtime_metadata)`) rather than rely on attribute access. In that case, F070 expands to introduce an envelope dataclass — flag this as a fork in the implementation and stop for user input.
5. `mypy --strict` and `pyright --strict` must pass on the new file.

---

### F060 — Consolidate trace modules into `app/design_sync/traces/`

**Current state (from research):**
- 5 files, 1110 LOC total. Public APIs duplicate file I/O (each has its own append-JSONL helper).
- 19 imports across 11 callers. ~5 production callers (`app/ai/blueprints/engine.py`, `app/design_sync/service.py`, `app/design_sync/routes.py`, `app/design_sync/import_service.py`), 1 script, 5 test files.
- All test files map 1:1 to existing modules — they'll continue to work via shims.

**Steps:**

1. Create `app/design_sync/traces/` subpackage:
   - `__init__.py` — exports `TraceWriter`, plus re-exports of every legacy public symbol so callers keep working without import changes.
   - `writer.py` — `TraceWriter` class. Constructor: `(data_dir: Path, settings: DesignSyncConfig)`. Methods: `append(category: str, event: dict[str, Any]) -> None`, `read_jsonl(category: str, last_n: int | None = None) -> Iterator[dict]`, `read_json(name: str) -> dict | None`, `write_json(name: str, data: dict) -> None`. Single source of truth for file paths (resolves `conversion_traces_path`, `data_dir / "correction_patterns.jsonl"`, etc.).
   - `converter.py` — pure-logic functions: `compute_quality_score`, `build_trace`, `extract_conversion_insights`, `format_conversion_quality`, `build_conversion_metadata`. No I/O. Each takes a `TraceWriter` only if it writes (move I/O up to the caller).
   - `regression.py` — pure-logic + bounded I/O: `load_traces`, `compute_aggregate_metrics`, `load_baseline`, `save_baseline`, `detect_regressions`. Internally uses `TraceWriter.read_jsonl` / `read_json`.
   - `correction.py` — `CorrectionTracker` class accepts a `TraceWriter` instead of constructing its own paths. `extract_correction_diffs` stays pure. Dataclasses (`CorrectionDiff`, `CorrectionPattern`, `ConverterRuleSuggestion`) and Pydantic response schemas (`CorrectionPatternResponse`, `ConverterRuleSuggestionResponse`) move here.
2. Persist the async fire-and-forget functions (`persist_converter_trace`, `persist_conversion_insights`, `persist_conversion_quality`) in `traces/__init__.py` as the top-level public API. They take a `TraceWriter` or build a process-wide singleton from `settings`.
3. Add `traces/_singleton.py` for the process-wide `get_trace_writer() -> TraceWriter` cache. Tests reset it via fixture.
4. Convert each legacy module file (`app/design_sync/converter_traces.py`, etc.) into a thin shim:
   ```python
   # app/design_sync/converter_traces.py
   """Shim — moved to app.design_sync.traces.converter / traces.writer in F060."""
   from app.design_sync.traces.converter import (
       append_trace,
       build_trace,
       compute_quality_score,
   )
   from app.design_sync.traces import persist_converter_trace

   __all__ = ["append_trace", "build_trace", "compute_quality_score", "persist_converter_trace"]
   ```
   This keeps all 19 existing import sites working without modification.
5. Add new tests under `app/design_sync/tests/test_traces_writer.py`:
   - `TraceWriter.append` writes correct file per category
   - `TraceWriter.read_jsonl` round-trips
   - Singleton resets cleanly under fixture
6. Keep existing per-module test files in place — they continue to exercise the shim layer. After F060 lands and 1 release passes, follow-up plan can delete shims and migrate test files. Do NOT delete shims in this PR.
7. Verify `make check-full` + the design_sync test suite all pass.

**Why shims:** Touching 19 import sites + 11 caller files in one PR is exactly the kind of "leakage" CLAUDE.md warns against. The shim layer makes the diff scope match the surgical-changes rule.

---

### F035 — Cull `DESIGN_SYNC__*` flags from 66 → ≤30

**Current state:** 66 fields in `app/core/config/design_sync.py`. Target ≤30. 55 references across `app/` + `services/`.

**Cull strategy (3 buckets):**

**Bucket 1 — Drop entirely (≈18 fields)** — last-touched >180 days ago AND zero non-test references:

```
fidelity_enabled, fidelity_ssim_window, fidelity_blur_sigma,
fidelity_critical_threshold, fidelity_warning_threshold, fidelity_figma_scale  (6)
tree_bridge_enabled, wrapper_unwrap_enabled, regression_strict  (3)
penpot_enabled, penpot_base_url, penpot_request_timeout  (3 — penpot deprecated path)
vlm_verify_client, vlm_verify_correction_confidence, vlm_low_confidence_threshold  (3)
custom_component_enabled, custom_component_confidence_threshold,
custom_component_model, custom_component_max_per_email  (4 — if zero callers; verify)
```

Verify zero-callers for each before drop:
```bash
for f in fidelity_enabled fidelity_ssim_window fidelity_blur_sigma \
         tree_bridge_enabled wrapper_unwrap_enabled regression_strict \
         penpot_enabled vlm_verify_client custom_component_enabled ; do
  echo "=== $f ==="
  grep -rn "design_sync.$f\|DESIGN_SYNC__${f^^}" app/ services/ scripts/ 2>/dev/null | grep -v _test
done
```

Any field with non-test references → move to Bucket 2 or 3.

**Bucket 2 — Convert to module-level constants in `app/design_sync/tuning.py` (≈10 fields)** — threshold knobs that should not have been env-tunable:

```
fidelity_critical_threshold (if kept)
nested_card_perceptual_threshold (30)
physical_card_min_signals (2)
sibling_min_group (2)
sibling_similarity_threshold (0.8)
vlm_verify_confidence_threshold (0.7)
vlm_verify_max_iterations (3)
vlm_verify_target_fidelity (0.97)
low_match_confidence_threshold (0.6)
opacity_composite_bg ("#FFFFFF")
```

Each constant is `Final[...]` typed. Update callers to import from `app.design_sync.tuning` instead of `settings.design_sync.<x>`.

**Bucket 3 — Keep (~30 fields)** — referenced from production paths or operationally tunable:
- All `*_enabled` flags that are genuinely runtime-toggleable (converter, figma_variables, ai_layout, figma_webhook, html_import_ai, conversion_memory, conversion_traces, mjml_import, section_cache, vlm_fallback, vlm_classification, vlm_verify, section_cache_redis_ttl, etc.)
- All secrets/URLs: `encryption_key`, `figma_webhook_passcode`, `figma_webhook_callback_url`, `vlm_classification_model`, `vlm_verify_model`, `custom_component_model` (if kept)
- Paths: `asset_storage_path`, `conversion_traces_path`, `regression_dir`
- Numeric ops parameters tied to deployment sizing: `asset_max_width`, `section_cache_memory_max`, `section_cache_redis_ttl`, `html_import_max_size_bytes`, `webhook_debounce_seconds`, `vlm_classification_timeout`, `vlm_verify_timeout`, `vlm_verify_diff_skip_threshold`, `vlm_verify_max_sections`

**Steps:**

1. **Static analysis first** — run the verifier script above. Generate `data/tech-debt-19-cull-candidates.txt` with confirmed-zero-caller fields.
2. For each Bucket 1 field, in a single commit:
   - Delete the field from `app/core/config/design_sync.py`
   - Delete `data/feature-flags.yaml` entries (if present)
   - Regenerate `.env.example`: `make .env.example`
   - Run `make flag-audit` — must pass
3. For each Bucket 2 field, in a separate commit per logical group:
   - Add `Final` constant to `app/design_sync/tuning.py`
   - Replace `settings.design_sync.<field>` with `<TUNING_CONST>` in callers
   - Delete the field from `app/core/config/design_sync.py`
   - Regenerate `.env.example`
4. After all cuts: verify field count: `grep -E "^\s+[a-z_0-9]+:" app/core/config/design_sync.py | wc -l` returns ≤30.
5. Add `app/core/tests/test_config_design_sync.py::test_field_count_under_cap` asserting `len(DesignSyncConfig.model_fields) <= 30`. Locks in the cap so future flag additions trigger a deliberate review.
6. **Deployment safety:** Before merge, grep production-style env file templates for any of the dropped names:
   ```bash
   grep -rn -i "DESIGN_SYNC__" infra/ ops/ k8s/ docker-compose*.yml deploy/ .env* 2>/dev/null
   ```
   Any production-override of a Bucket 1 field → re-classify the field to Bucket 3 and keep it.

**Risk:** Pydantic `extra="ignore"` (Settings config L137) means stale env vars in production won't crash startup, but they will silently no-op. The `_warn_unknown_nested_env_vars()` helper at L236 will log a warning per stale var — good telemetry, no startup failure.

---

### F057 — Migration squash (runbook only)

`make db-squash` is destructive (requires confirmation prompt). Do NOT execute in this PR. Produce:

1. `.agents/plans/tech-debt-19-runbook-db-squash.md` covering:
   - Pre-conditions: confirmed schema-drift entry `tech-debt-alembic-schema-drift` is closed (✅ closed 2026-05-10); confirm `alembic check` exits 0 on a freshly upgraded DB.
   - Backup procedure: full pg_dump of production DB → S3 with retention.
   - Sequence: drop existing migrations → `alembic stamp head` → `alembic revision --autogenerate -m 'baseline'` → manual review → rename to `001_baseline.py`.
   - Rollback: restore from pg_dump; this is the only rollback path.
   - Validation: post-squash, `alembic check` exits 0; `alembic upgrade head` on a fresh DB produces identical schema; full app boot succeeds; QA-engine integration tests pass.
   - Maintenance window estimate: 30 min full app downtime + 15 min validation.
2. `scripts/squash-migrations-dryrun.sh` (new): spins up a throwaway Postgres in Docker, applies current migrations, runs the squash flow against it, asserts `alembic check` exits 0. Safe to run in CI as a smoke test.
3. CI addition (`.github/workflows/ci.yml`): optional `squash-dryrun` job that runs the dry-run script on `pull_request` against `tech-debt/squash` branches. Not gated on every PR.

**Do NOT add `make db-squash` to any CI workflow.** The Makefile target's confirmation prompt is the only safety.

---

## Verification

### Per-PR gates

For each PR (A, B, C):

- [ ] `make check-full` passes (lint + types + tests + frontend + security + golden conformance + flag audit + migration lint + env-drift)
- [ ] `make types` strict-mypy + strict-pyright on touched files
- [ ] No new `getattr(request, ...)` in `app/ai/agents/` (F070 PR)
- [ ] `git diff` scope matches the PR's feature list — no leakage from other branches

### F060-specific

- [ ] All 19 import sites of legacy modules still work (shim test: import each public symbol from its old path)
- [ ] `TraceWriter` round-trip tests pass for all 4 categories
- [ ] `app/design_sync/tests/test_*` all green without modification

### F035-specific

- [ ] `len(DesignSyncConfig.model_fields) <= 30`
- [ ] `make flag-audit` passes (no >90-day flags without removal plan)
- [ ] `.env.example` matches generator output (gated by `make check-env-drift`)
- [ ] No production env file references a dropped flag (grep scan above)

### F049-specific

- [ ] `scripts/export-openapi.py --live` produces byte-identical output to the static path on a clean checkout (or a documented diff exists)
- [ ] CI `sdk-check` job passes with `--live`

### F059-specific

- [ ] `test_database_echo_routes_via_structlog` passes
- [ ] PII redaction tests still cover the SQL-echo path

### F070-specific

- [ ] All 9 concrete request schemas pass `isinstance(req, RuntimeAgentRequest)` in the new test file (OR — if `extra="forbid"` blocks attribute injection — F070 is partially descoped and flagged for envelope follow-up)
- [ ] `app/ai/agents/base.py` contains zero `getattr(request, ...)` except the dynamic `_user_input_fields` loop at L251 (documented exception)

### F057-specific

- [ ] Runbook exists; no destructive operation executed in this branch
- [ ] Dry-run script runs green in CI

## Security Checklist

No new endpoints in this plan. Per-feature security review:

- **F049:** Booted-uvicorn in `--live` mode binds to localhost only, ephemeral port, single CI runner. No external exposure. No auth bypass.
- **F059:** Echo-route-to-structlog adds `redact_event_dict` to SQL logs — strictly **adds** PII protection, removes none.
- **F060:** Trace files contain HTML conversion artifacts. Verify no PII leak: `extract_conversion_insights` and `extract_correction_diffs` operate on HTML structure, not user-supplied content. `format_conversion_quality` reads connection IDs only. No change to data sensitivity profile.
- **F070:** `RuntimeAgentRequest` protocol exposes `user_id`/`client_id` for read access in agents — these are already in `NodeContext.metadata`. No new exposure.
- **F035:** Removing flags removes attack surface (fewer env-tunable code paths). Bucket 1 fields like `penpot_*` removal eliminates a webhook attack surface if not deployed.
- **F033, F057:** No code surface change.

## Deferred-Items Cross-Reference

Matched entries from `.agents/deferred-items.json`:

- `tech-debt-alembic-schema-drift` (closed 2026-05-10) — relevant to F057. Confirmed closed; runbook can proceed without dependency.

No other matching entries for files in this plan's "Files to Create/Modify" list. Re-run the grep at `/preflight-check` step to confirm.

## Open Questions for Preflight

1. **F070 — Pydantic `extra="forbid"`:** Verify whether any concrete agent request schema forbids extras. If yes, F070 cannot inject `user_id`/`client_id`/etc. via `setattr` and the envelope-dataclass alternative is required. Decision point at step 4 of F070.
2. **F049 — DB connectivity in CI for `--live`:** Confirm `app/main.py` lifespan tolerates a missing DB (or wire the `sdk-check` job to the existing postgres service container).
3. **F035 — Production env file overrides:** Run the production-env grep before committing the cull. If anything in Bucket 1 is referenced from `infra/`/`ops/`/`k8s/`/`deploy/`, reclassify before delete.
4. **F060 — Shim lifetime:** This plan keeps shims indefinitely. A follow-up entry should be added to `.agents/deferred-items.json` to remove shims after 1 release confirms no external consumers (no external consumers expected — repo is monorepo).

## Estimated Effort

| Feature | LOC delta | Time |
|---------|-----------|------|
| F033 closure | +3 (audit doc) | 5 min |
| F049 upgrade | +30 (script), +1 (CI) | 1 h |
| F059 | +40 (router + test) | 1.5 h |
| F070 | +60 (Protocol + test), -9 getattrs | 2 h |
| F060 | +400 (new pkg + tests), -1100 (shimmed) net ≈ -700 | 4 h |
| F035 | -200 (config), +50 (constants), +20 (test) net ≈ -130 | 3 h |
| F057 runbook | +150 (doc), +60 (dry-run script) | 1.5 h |
| **Total** | **net ≈ -700 LOC** | **~13 h** |

Plan stays under the 700-line cap.
