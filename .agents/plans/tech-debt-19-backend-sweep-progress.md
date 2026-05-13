# Tech-debt-19 Backend Sweep — Progress Note

**Paused:** 2026-05-13 — switched away from `chore/tech-debt-19-backend-sweep` to land the pyright restore PR first.

## Where things stand

- **Branch:** `chore/tech-debt-19-backend-sweep` (exists locally; not pushed)
- **Stash:** `stash@{0}: On chore/tech-debt-19-backend-sweep: WIP chore/tech-debt-19-backend-sweep — paused for pyright restore PR`
  - Captures **all PR-A work** including untracked files (verified via `git stash show -u`)
  - 20 files, 571 insertions, 36 deletions

## What's already done (in stash@{0})

### F033 — closure note
- No code change needed. `TECH_DEBT_AUDIT.md:75` already states "RESOLVED". The CI gate (`make check-env-drift` at Makefile L28, CI step `.env.example drift gate` at `.github/workflows/ci.yml:43`) is live.

### F059 — structlog routing
- `app/core/exceptions.py:111` — `logger.error(..., exc_info=True)` → `logger.exception(...)`
- `app/core/database.py` — added `_StructlogBridgeHandler` (stdlib LogRecord → structlog) and `_route_sqlalchemy_to_structlog()`. Invoked at module-load when `settings.database.echo` is True.
- `app/core/config/database.py:13-15` — comment updated to reflect new routing
- `app/core/tests/test_database_echo_routes_via_structlog.py` — 3 tests, all passing:
  - bridge handler attaches and sets `propagate=False`
  - re-invocation is idempotent
  - emit() routes through `get_logger("sqlalchemy.engine").info(...)`

### F070 — `BaseAgentRequest`
- `app/ai/agents/types.py` (new) — declares `BaseAgentRequest(BaseModel)` with 5 orchestrator-injected fields:
  - `user_id: str | None = None`
  - `blueprint_run_id: str | None = None`
  - `prompt_version: str | None = None`
  - `effective_tier: TaskTier | None = None` (Literal["complex", "standard", "lightweight"])
  - `client_id: str | None = None`
- 11 concrete request schemas migrated to inherit from `BaseAgentRequest`: scaffolder, dark_mode, content, accessibility, code_reviewer, personalisation, outlook_fixer, knowledge, innovation, visual_qa. (NOT migrated: `VariantRequest` — not a `BaseAgentService.process()` consumer; `import_annotator` schemas — dataclass-based, not Pydantic.)
- `app/ai/agents/base.py`:
  - 6 `getattr(request, ...)` orchestrator-field calls replaced with direct attribute access
  - `process` and `stream_process` signatures: `request: Any` → `request: BaseAgentRequest`
  - 3 `getattr` calls preserved: `output_mode` and `run_qa` (agent-specific fields, not on base) and the dynamic `_user_input_fields` loop at line 261 (fundamentally dynamic field name)
- `app/ai/agents/tests/test_agent_request_protocol.py` — 12 tests, all passing
- Pyright: 0 errors, 1 pre-existing warning on `_crag_validate_and_correct` (baseline)

### F049 — `--live` OpenAPI fetch
- `scripts/export-openapi.py` — added `--live` flag that boots uvicorn on an ephemeral 127.0.0.1 port, polls `GET /openapi.json` until 200, returns parsed JSON. Tear-down via `proc.terminate()` with 5s `kill()` fallback.
- `cms/packages/sdk/openapi.json` and `cms/packages/sdk/src/client/types.gen.ts` regenerated — captures the new 5 orchestrator fields per request schema (180 lines openapi diff, 60 lines types diff).
- **Not yet done:** Makefile `sdk-snapshot` target update + CI `sdk-check` job update to use `--live`. Stayed static-mode for the snapshot regen because `--live` needs verification against the lifespan side-effects under CI's container environment.

## What's NOT done

- **F049 CI wiring:** Need to either update `Makefile` `sdk-snapshot` to call `--live` OR add CI env (`AI__PROMPT_STORE_ENABLED=false`, `COLLAB_WS__ENABLED=false`) to the CI step. Static-mode snapshot is regenerated and in-stash.
- **PR-B (F060):** Trace module consolidation. Untouched.
- **PR-C (F035):** DESIGN_SYNC flag cull. Untouched.
- **F057 runbook:** Untouched.

## Resume sequence (when pyright PR ships)

```bash
# 1. Verify pyright branch shipped + merged
git fetch origin
git log origin/main --oneline | head -3

# 2. Switch back to tech-debt-19 branch
git checkout chore/tech-debt-19-backend-sweep

# 3. Pop the stash (PR-A work restored)
git stash pop stash@{0}

# 4. Verify state
git status  # should show ~20 modified/new files
uv run pytest app/core/tests/test_database_echo_routes_via_structlog.py app/ai/agents/tests/test_agent_request_protocol.py -v
uv run pyright app/ai/agents/base.py app/ai/agents/types.py app/core/database.py app/core/exceptions.py

# 5. Continue with F049 CI wiring + PR-A gate (make check-full)
# 6. Open PR-A
# 7. Move to PR-B (F060) and PR-C (F035) per .agents/plans/tech-debt-19-backend-sweep.md
```

## Open questions to revisit on resume

- Does `make check-full` pass with PR-A delta? (Not run during the paused execute.)
- Does `--live` mode actually work in the CI environment, or do we keep static-mode and document the trade-off?
- The F035 production env scan was clean (no `infra/`/`ops/`/`k8s/`/`deploy/`/`helm/` dirs exist) — safe to cull aggressively.
