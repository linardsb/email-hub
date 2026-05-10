# Tech Debt 10 — Config Split + Observability Cleanup

**Source:** `TECH_DEBT_AUDIT.md`
**Scope:** `app/core/config.py` is 928 LOC and the #1 most-churned file. `.env.example` covers ~65 of 371 settings. Logging consistency drifts. Several misc High/Medium findings folded in.
**Goal:** Per-domain config files; auto-generated `.env.example`; drift-detection in CI; consistent structured logging.
**Estimated effort:** ½ day.
**Prerequisite:** Plans 01 + 05 landed (they delete dead config flags first, simplifying the split).

## Findings addressed

F032 (`app/core/config.py` 928 LOC, 50 nested classes) — High
F033 (`.env.example` 82% drift) — High
F034 (`extra="ignore"` silently drops typo'd env vars) — Medium
F035 (flag sprawl across BlueprintConfig/AIConfig/PipelineConfig/DESIGN_SYNC) — High
F036 (DB pool size 8 connections) — High
F058 (dynamic event names break `domain.action_state`) — Medium (already fixed in Plan 01)
F059 (PII redaction not applied to SQL echo + stdlib `extra=`) — Medium
F037 (Maizzle no retry/circuit breaker) — High — **✅ already shipped** (verified during /preflight; see Part F + Preflight Findings)
F038 (scheduler leader-lock uses `os.getpid()` identity, no CAS-on-release) — High
F039 (`_evaluate_jobs` blocks the loop on slow jobs — sequential `await`) — High
F055 (repair pipeline stage failure has no explicit rollback marker) — Medium
F036 connector finding (untested, deferred)

## Pre-flight

```bash
git checkout -b refactor/tech-debt-10-config-obs
make check
```

Snapshot all current settings:
```bash
python -c "from app.core.config import get_settings; \
  import json; print(json.dumps(get_settings().model_dump(mode='json'), indent=2))" \
  > /tmp/settings.before.json
```

## Part A — Split `app/core/config.py` (F032)

### A1. New layout

```
app/core/
  config/
    __init__.py        ← Settings root, get_settings(), env loading
    auth.py            ← AuthConfig
    database.py        ← DatabaseConfig
    ai.py              ← AIConfig + EmbeddingConfig + RerankerConfig + EvaluatorConfig
    blueprint.py       ← BlueprintConfig + (PipelineConfig if shipping; else delete per Plan 05)
    qa.py              ← QA*Config (8 sub-configs, see audit F036)
    design_sync.py     ← DesignSyncConfig (47 fields)
    knowledge.py       ← KnowledgeConfig
    connectors.py      ← ESPSyncConfig + CredentialsConfig + per-vendor configs
    notifications.py   ← NotificationsConfig
    scheduling.py      ← SchedulingConfig + DebounceConfig
    security.py        ← SecurityConfig
    rendering.py       ← RenderingConfig + visual diff
    misc.py            ← anything left over (LoggingConfig, EvalConfig, etc.)
```

`app/core/config.py` becomes a 5-line shim re-exporting `Settings` and `get_settings()` for backward compat OR is deleted.

### A2. Migration

For each sub-config:
1. Move the class definition.
2. Move its docstring.
3. Update `Settings` to nest it via field annotation.
4. Run `make types` to verify imports resolve.

### A3. Verify settings parity

```bash
python -c "from app.core.config import get_settings; \
  import json; print(json.dumps(get_settings().model_dump(mode='json'), indent=2))" \
  > /tmp/settings.after.json
diff /tmp/settings.before.json /tmp/settings.after.json  # MUST be empty
```

## Part B — Auto-generate `.env.example` (F033)

### B1. Generator script

**New file:** `scripts/generate-env-example.py`:
```python
"""Generate .env.example from Pydantic Settings model."""
from app.core.config import Settings, get_settings_default

def emit_field(name: str, field: FieldInfo, prefix: str = ""):
    env_name = f"{prefix}{name.upper()}"
    if field.is_complex():  # nested BaseSettings
        for sub_name, sub_field in field.annotation.model_fields.items():
            yield from emit_field(sub_name, sub_field, prefix=f"{env_name}__")
    else:
        default = field.default if field.default is not PydanticUndefined else "<required>"
        yield f"# {field.description or ''}"
        yield f"{env_name}={default}"

def main():
    for field_name, field in Settings.model_fields.items():
        for line in emit_field(field_name, field):
            print(line)
        print()

if __name__ == "__main__":
    main()
```

Wire into Make:
```make
.env.example: app/core/config/*.py
	uv run python scripts/generate-env-example.py > .env.example.tmp
	mv .env.example.tmp .env.example
```

### B2. CI drift gate

`.github/workflows/ci.yml`:
```yaml
- name: Check .env.example drift
  run: |
    uv run python scripts/generate-env-example.py > /tmp/env.generated
    diff .env.example /tmp/env.generated || \
      (echo "::error::.env.example out of sync — run 'make .env.example'" && exit 1)
```

## Part C — Strict env-var parsing (F034)

### C1. Switch to `extra="forbid"` outside test

`app/core/config/__init__.py`:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="forbid" if os.getenv("ENVIRONMENT") != "test" else "ignore",
        env_file=".env",
    )
```

OR — preferred — keep `extra="ignore"` but add a startup hook that warns on unknown `*__*` env vars by listing the actual env keys and diffing against the model's expected keys.

### C2. Test

Set a typo'd env var (`AUT__JWT_SECRET_KEY=foo`); confirm startup either fails (forbid) or logs a warning (ignore + warn).

## Part D — Flag sprawl audit (F035)

### D1. Run `make flag-audit`

This target exists per CLAUDE.md. Output is at `traces/flag_audit.json` — per-flag age, last-modified date, hits.

### D2. Apply the 90-day / 180-day rule

Per `make flag-audit` output:
- Flags untouched > 180 days → delete the flag + the disabled branch.
- Flags 90-180 days → either flip the default or schedule removal in `feature-flags.yaml`.

Specific candidates for deletion (from audit):
- `DESIGN_SYNC__PENPOT_CONVERTER_ENABLED` (Plan 01 already deletes)
- Other unused `BlueprintConfig` flags (see audit F035 list)

### D3. Group experimental flags

Move `_enabled: bool = False` flags that are genuine experiments into a `BlueprintExperimentsConfig` sub-model so the production `BlueprintConfig` is shorter.

## Part E — DB pool sizing (F036)

### E1. Adjust defaults

`app/core/config/database.py`:
```python
pool_size: int = Field(default=20, ge=1)
max_overflow: int = Field(default=20, ge=0)
pool_recycle: int = 1800  # 30 min
pool_pre_ping: bool = True
```

Total = 40 connections. Postgres default `max_connections` is 100; this leaves headroom for the maizzle sidecar's parallel dev, etc.

### E2. Document

`docs/scaling.md` (new section): explain pool sizing, when to increase, monitoring queries.

## Part F — Maizzle resilience (F037) — ✅ ALREADY IMPLEMENTED

> Status: shipped before this plan. `app/email_engine/service.py:47-64` defines `_post_to_builder` with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...), retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)), reraise=True)` and `_maizzle_breaker = CircuitBreaker(name="maizzle", failure_threshold=5, reset_timeout=30.0)`. `_call_builder` (line 274) delegates and translates `CircuitOpenError` → `BuildServiceUnavailableError`. **No code change for F037 in the Session 10 PR — verify-only.** The original prescription below is kept for historical context.

### F1. Wrap `_call_builder` with retries + circuit breaker

`app/email_engine/service.py:264`:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.resilience import CircuitBreaker

_maizzle_cb = CircuitBreaker(name="maizzle", failure_threshold=5, recovery_timeout=30)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
)
async def _call_builder(self, ...):
    async with _maizzle_cb:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ...
```

Mirrors `app/rendering/service.py:16` pattern.

### F2. Stop snapshotting URL at import time

`app/email_engine/service.py:35-37` — move `MAIZZLE_BUILDER_URL = settings.maizzle_builder_url` into `_call_builder` body.

## Part G — Logging consistency (F058 + F059)

### G1. F058 was fixed in Plan 01

Verify no new dynamic event names introduced:
```bash
rg 'logger\.(info|warning|error)\(f"[a-z_.]+\.\{' app/ --type py
# Should return 0 hits.
```

### G2. F059: SQL echo bypasses redaction

`app/core/config/database.py`:
```python
echo: bool = False  # never enable in shared logs; structlog redaction does not cover SQLAlchemy logger
```

If dev-time SQL inspection is needed, wire SQLAlchemy logger through structlog's `processors.UnicodeDecoder` + `redact_event_dict`.

### G3. F059: stdlib `logger.error(extra=…)` in `app/core/exceptions.py:111`

Replace stdlib calls with `structlog.get_logger().error(...)` so `redact_event_dict` runs.

## Part H — Scheduling leader-lock CAS (F038)

`app/scheduling/engine.py:74-84` (`_acquire_leader`) sets `LEADER_KEY` to `os.getpid()` via `SET NX EX`. Two problems:

1. **No release path.** When a leader exits cleanly, the lock waits for TTL (`check_interval_seconds * 1.5`) before another worker can take over.
2. **Pid is not a stable cross-host identity.** Two containers with `pid=1` collide; a stale-lock check based on identity would mis-fire.

### H1. UUID identity persisted on the instance

`engine.py` `__init__`:
```python
import uuid
self._identity = f"{os.getenv('HOSTNAME', 'unknown')}:{uuid.uuid4()}"
```

`_acquire_leader` (engine.py:79): replace `identity = str(os.getpid())` with `identity = self._identity`. Log `scheduling.leader_acquired` with `identity=self._identity` on success.

### H2. Atomic CAS release via Lua

Add module-level constant + method:

```python
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
else
  return 0
end
"""

async def _release_leader(self) -> None:
    """Release leader lock only if we still own it (compare-and-swap)."""
    try:
        redis = await get_redis()
        released = await redis.eval(_RELEASE_LUA, 1, LEADER_KEY, self._identity)
        if released:
            logger.info("scheduling.leader_released", identity=self._identity)
        else:
            logger.warning("scheduling.leader_release_no_op", identity=self._identity)
    except Exception:
        logger.warning("scheduling.leader_release_redis_error", exc_info=True)
```

### H3. Wire into the loop and stop()

`_loop` (engine.py:58-68) — release after the tick's drain:

```python
if await self._acquire_leader():
    try:
        await self._evaluate_jobs()
        await self.drain()        # see Part I — bounds in-flight to one tick
    finally:
        await self._release_leader()
```

`stop()` (engine.py:44-52) — call `await self._release_leader()` after `self._task = None`, in case shutdown happened mid-tick while we held the lock. Wrap in `contextlib.suppress(Exception)` so a Redis outage during shutdown doesn't surface.

### H4. Tests (`app/scheduling/tests/test_engine.py`)

- `test_release_when_owner` — mock `redis.eval` returning `1`; assert one `scheduling.leader_released` log via `caplog`.
- `test_release_no_op_when_stolen` — mock `redis.eval` returning `0`; assert `scheduling.leader_release_no_op` log; `redis.delete` is NOT called directly.
- `test_identity_is_unique_per_instance` — two `CronScheduler(scheduling_config)` → assert their `_identity` strings differ.
- Update existing fixtures to add `mock_redis.eval = AsyncMock(return_value=1)` so `_release_leader` doesn't `AttributeError` during `stop()`. The shared `mock_redis` fixture in the scheduling `conftest.py` is the single seam.

### H5. Done when

- `_acquire_leader` writes `self._identity` (UUID), not pid.
- `_release_leader` exists, is called from `_loop` (finally) and `stop()`, and uses Lua CAS.
- `scheduling.leader_acquired` / `leader_released` / `leader_release_no_op` events are emitted via `domain.action_state` pattern.

## Part I — Non-blocking job execution (F039)

`app/scheduling/engine.py:90-141` (`_evaluate_jobs`) awaits `_execute_job(name, key)` inline at line 141. A long-running job blocks the loop iteration, so other due jobs miss their tick and the leader lock TTL pressure increases. `_execute_job` already has its own try/except + Redis bookkeeping, so it is safe to fire-and-forget.

### I1. Pending-task set + drain helper

`engine.py` `__init__`:
```python
self._pending_tasks: set[asyncio.Task[None]] = set()
```

Replace inline await at engine.py:141:
```python
if next_run <= now:
    if len(self._pending_tasks) >= self._config.max_concurrent_jobs:
        logger.warning(
            "scheduling.max_concurrent_reached",
            limit=self._config.max_concurrent_jobs,
            job=name,
        )
        continue
    task = asyncio.create_task(
        self._execute_job(name, key), name=f"scheduling.job:{name}"
    )
    self._pending_tasks.add(task)
    task.add_done_callback(self._pending_tasks.discard)
    logger.info("scheduling.job_scheduled", job=name)
```

Add public method:
```python
async def drain(self) -> None:
    """Await every in-flight job task. Test seam + clean-shutdown helper."""
    if not self._pending_tasks:
        return
    pending = list(self._pending_tasks)
    logger.info("scheduling.drain_started", in_flight=len(pending))
    await asyncio.gather(*pending, return_exceptions=True)
    logger.info("scheduling.drain_completed")
```

### I2. Config

`app/core/config/scheduling.py` — add to `SchedulingConfig`:
```python
max_concurrent_jobs: int = Field(
    default=10, ge=1,
    description="Max in-flight scheduled jobs per worker. Excess due jobs are skipped this tick.",
)
```

Defaults must keep `make .env.example` (Part B) happy — add a one-line description so the generator emits a comment.

### I3. Loop wiring

Per Part H3, `drain()` is called inside the leader-held block, before `_release_leader`. This bounds concurrency to one tick's worth and ensures lock release happens only after every job spawned during this tick has terminated. Stop path: `stop()` calls `await self.drain()` BEFORE `self._task.cancel()` (so already-spawned jobs run to completion under the same identity).

### I4. Tests (`app/scheduling/tests/test_engine.py`)

Existing test update (required from preflight):
- `test_fires_due_job` (line 66) — insert `await scheduler.drain()` between `await scheduler._evaluate_jobs()` and `assert executed is True`.

New tests:
- `test_evaluate_jobs_returns_before_slow_job_completes` — register a callable that awaits `asyncio.sleep(0.5)`; using `time.perf_counter()`, assert `_evaluate_jobs()` returns in < 0.1s while `len(scheduler._pending_tasks) == 1`.
- `test_drain_awaits_all_pending` — schedule 3 due jobs (varying sleeps); call `await scheduler.drain()`; assert all 3 ran AND `scheduler._pending_tasks` is empty.
- `test_max_concurrent_jobs_caps_inflight` — set `scheduling_config.max_concurrent_jobs = 2`; mock 5 due jobs all with sleeping callables; assert `len(scheduler._pending_tasks) <= 2` and `scheduling.max_concurrent_reached` was logged ≥ 3 times.
- `test_stop_drains_before_cancel` — start scheduler; schedule a job that takes 0.2s; call `stop()` immediately; assert the job's success was recorded in Redis (via `mock_redis.hset` calls).

### I5. Done when

- `_evaluate_jobs` does not block on `_execute_job`.
- `drain()` is the only supported wait mechanism; tests use it (no private `_pending_tasks` access except for assertions).
- `max_concurrent_jobs` config is wired and audited via `make .env.example`.
- All existing scheduling tests still pass after the `drain()` insert.

## Part J — Repair pipeline stage rollback (F055)

`app/qa_engine/repair/pipeline.py:47-78` (`RepairPipeline.run`) currently keeps `current` unchanged on stage failure (the assignment `current = result.html` only happens after a successful `stage.repair(current)`), but:

1. The failure path doesn't capture a snapshot, so a stage that mutates a *passed-in mutable* (e.g., a shared `BeautifulSoup` tree if a future stage refactor introduces one) could leak partial state into the next stage.
2. The "rollback" is implicit — neither the log event (`repair.stage_failed`) nor the warning string (`"{name}: repair failed (...)"`) tell a reader that no html change took effect.

**Chosen semantics — option (c) from preflight: explicit snapshot + restore.** Subsequent stages still run (preserves `test_stage_failure_does_not_crash`), the rollback is observable in logs and warnings, and the snapshot defends against the future-mutation scenario.

### J1. Snapshot + restore

`pipeline.py:47-78`:
```python
def run(self, html: str) -> RepairResult:
    all_repairs: list[str] = []
    all_warnings: list[str] = []
    current = html

    for stage in self._stages:
        snapshot = current
        try:
            result = stage.repair(current)
            current = result.html
            all_repairs.extend(result.repairs_applied)
            all_warnings.extend(result.warnings)
            if result.repairs_applied:
                logger.info(
                    "repair.stage_applied",
                    stage=stage.name,
                    count=len(result.repairs_applied),
                    repairs=result.repairs_applied,
                )
        except Exception as e:
            current = snapshot
            logger.warning(
                "repair.stage_rolled_back",
                stage=stage.name,
                error=str(e),
            )
            all_warnings.append(f"{stage.name}: rolled back ({e})")

    return RepairResult(
        html=current, repairs_applied=all_repairs, warnings=all_warnings,
    )
```

Diff vs current code: rename `repair.stage_failed` → `repair.stage_rolled_back`; add `snapshot = current` at top of loop body; add `current = snapshot` in `except`; warning string changes from `"... repair failed (...)"` to `"... rolled back (...)"`.

### J2. Tests (`app/qa_engine/repair/tests/test_pipeline.py`)

Existing test update (required from preflight):
- `test_stage_failure_does_not_crash` (line 35-39) — change `assert any("failed" in w for w in result.warnings)` to `assert any("rolled back" in w for w in result.warnings)`.

New tests:
- `test_stage_failure_does_not_leak_partial_html` — define a stage that returns a `RepairResult.html = "<corrupt>"` from a side effect (mutate a shared list to record the call) and *then* raises; followed by a `_NoOpStage` that records the html it received. Assert the `_NoOpStage` saw `snapshot`, not `"<corrupt>"`.
- `test_rolled_back_warning_emits_log` — using `caplog.at_level("WARNING")`, run pipeline with `_FailingStage`; assert exactly one log record with `event == "repair.stage_rolled_back"` and `stage == "failing"`.
- `test_repairs_applied_unchanged_on_failure` — run pipeline with `_FailingStage` between two `_NoOpStage`s that report a repair; assert `result.repairs_applied` contains only the two no-op stages' entries.

### J3. Done when

- `pipeline.py` emits `repair.stage_rolled_back` (not `repair.stage_failed`) on stage exceptions.
- Warning string is `"{stage.name}: rolled back ({e})"`.
- `current` is restored from `snapshot` in the except branch.
- All existing repair pipeline + RepairNode tests pass after the warning-string update.

## Verification

```bash
make check
diff /tmp/settings.before.json /tmp/settings.after.json    # empty
make .env.example                                          # regen clean
git diff .env.example                                      # only intentional changes
make flag-audit                                            # passes thresholds
```

### Resilience cluster (Session 10 PR — `refactor/tech-debt-10-resilience`)

```bash
make check-full                                                       # gate per Session 10 args
uv run pytest app/scheduling/tests/test_engine.py -v                  # F038 + F039 coverage
uv run pytest app/qa_engine/repair/tests/test_pipeline.py -v          # F055 coverage
uv run pytest -m integration -k scheduling                            # scheduling integration test
uv run pyright app/scheduling/engine.py app/qa_engine/repair/pipeline.py app/email_engine/service.py
# → must remain 0 errors (preflight baseline)
```

## Rollback

Each part is an independent revert. Part A (config split) is the most invasive; if anything fails, revert and the shim re-export keeps existing imports working.

## Risk notes

- **Part A breaks every `from app.core.config import …` of a sub-config.** Run `rg "from app.core.config import" app/` before; update each importer in the same PR.
- **Part B `.env.example` regen will produce a large diff** the first time. Review carefully — operators rely on this file. Don't lose comments.
- **Part C `extra="forbid"` is risky** in environments that set platform-specific env vars (PaaS-injected). Keep `ignore` + warning instead if your hosting platform injects extras.
- **Part E pool size bump** can saturate Postgres. Coordinate with infra; check `pg_stat_activity` after deploy.
- **Part F retry on Maizzle** can mask real failures. Add metric `maizzle.retry_count` and alert if >X/min.

## Preflight Findings — Session 10 (Resilience cluster F037/F038/F039/F055)

Captured by `/preflight-check` before `/be-planning --extend`. Re-run preflight after the plan body is extended with F038/F039/F055 sections.

### Plan-state findings (must address before `/be-execute`)

| # | Finding | Action |
|---|---------|--------|
| 1 | **F037 IS ALREADY IMPLEMENTED.** `app/email_engine/service.py:47-64` defines `_post_to_builder` with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...), retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)), reraise=True)` and `_maizzle_breaker = CircuitBreaker(name="maizzle", failure_threshold=5, reset_timeout=30.0)`. `_call_builder` (line 274) delegates to it and handles `CircuitOpenError`. The Session 10 args description ("`_call_builder` has no tenacity decorator") matches the direct-decorator shape but misses that resilience already exists on the inner function. | **Drop F037 from scope** — same as F036. Verify-only under "Done when"; no code changes. |
| 2 | **Plan body does not contain F038/F039/F055 sections.** `/be-planning --extend` has not run (or did not persist). | Run `/be-planning --extend` first; this preflight only scans the target files. |

### Deferred Items Touching This Plan

| ID | Phase | Severity | Title | Action |
|----|-------|----------|-------|--------|
| _none_ | — | — | _No deferred items reference `app/email_engine/service.py`, `app/scheduling/engine.py`, or `app/qa_engine/repair/pipeline.py`._ | — |

Searched `.agents/deferred-items.json` by `code_refs` containing each target file, and by phase prefixes `tech-debt-10`, `F037`, `F038`, `F039`, `F055`. Zero matches.

### Patterns Found in Test Files

| File | Line | Pattern | Plan Impact | Action |
|------|------|---------|-------------|--------|
| `app/email_engine/tests/test_passthrough.py` | 51, 65, 84 | `_html, _opt, passthrough = await service._call_builder(...)` | Safe — F037 already shipped; `_call_builder` signature unchanged | None |
| `app/scheduling/tests/test_engine.py` | 66 | `await scheduler._evaluate_jobs(); assert executed is True` | 🚨 BREAKS under F039. If `_evaluate_jobs` schedules `_execute_job` via `asyncio.create_task` (fire-and-forget), `await _evaluate_jobs()` returns *before* the task body runs — `assert executed is True` becomes flaky/false. | Plan must spec how tests await spawned tasks (e.g. expose `_pending_tasks: set[asyncio.Task]` on `CronScheduler` and `await asyncio.gather(*scheduler._pending_tasks)` in tests, or add `await scheduler.drain()` helper). Pre-fix in plan, not now. |
| `app/scheduling/tests/test_engine.py` | 17, 61, 114, 139 | `mock_redis.set = AsyncMock(return_value=True)` (leader lock) | Mostly safe. F038 keeps `SET NX EX` semantics; UUID identity is internal. But CAS-on-release needs new mock surface (Lua `eval` or GET+DEL). Existing tests don't release the lock so they pass. New tests will be needed. | Plan must add `_release_leader` test coverage. No auto-fix. |
| `app/qa_engine/repair/tests/test_pipeline.py` | 35-39 | `test_stage_failure_does_not_crash` asserts subsequent `_NoOpStage` runs after failing stage; `result.html == input` | 🚨 SEMANTIC AMBIGUITY in F055. Current behavior: stage failure → log + add warning + skip stage's mutation, continue with next stage (test enshrines this). F055 "rollback on stage failure" is ambiguous: (a) roll back stage's partial mutations (already done — `current` only updates after success), (b) abort pipeline on first failure (would break this test), (c) snapshot/restore around each stage (no behavior change visible to test). | Clarify F055 semantics in the planning extend before any code change. Don't auto-fix the test until intent is locked. |
| All test files | — | Hardcoded count assertions (`== \d+`), tuple unpacking against changing signatures, hardcoded long strings, `Field(default_factory=)` without annotations | None found in scope. | No fixes needed. |

### Pyright Baseline

```
uv run pyright app/email_engine/service.py app/scheduling/engine.py app/qa_engine/repair/pipeline.py
→ 0 errors, 0 warnings, 0 informations
```

Any pyright error on these three files after `/be-execute` is a regression introduced by this work. `app/scheduling/engine.py` already has top-of-file pyright suppressions (`reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportGeneralTypeIssues=false`) — preserve them when editing.

### Gate before `/be-execute`

1. F037 dropped from scope (verify-only).
2. Plan body extended with F038, F039, F055 sections — each spec'ing test-shape implications above.
3. `/preflight-check` re-run and clean.

## Done when

- [ ] `app/core/config/` package exists; root `config.py` is a shim or removed.
- [ ] `make .env.example` regenerates clean; CI gate added.
- [ ] Typo'd env var either fails startup or logs a warning.
- [ ] `make flag-audit` passes (no flags >180d untouched).
- [ ] DB pool 20+ connections.
- [ ] Maizzle calls wrapped in tenacity + circuit breaker.
- [ ] Zero dynamic-name `domain.{value}.event` log calls.
- [ ] `make check` green.
- [ ] PR titled `refactor(core): split config + .env drift gate + Maizzle resilience (F032 F033 F036 F037)`.
- [ ] Mark F032, F033, F034, F035, F036, F037, F058, F059 as **RESOLVED**.

### Done when (Resilience cluster — Session 10 PR scope)

This subset ships independently on `refactor/tech-debt-10-resilience`. Configuration / observability work (Parts A–G) is NOT in scope for this PR.

- [ ] **F037** — verified already shipped (`app/email_engine/service.py:47-64`); no code change in this PR.
- [ ] **F038** — `CronScheduler` uses UUID identity; `_release_leader` uses Lua CAS; release wired into `_loop` finally + `stop()`.
- [ ] **F039** — `_evaluate_jobs` is non-blocking; `_pending_tasks` + `drain()` exist; `max_concurrent_jobs` config gate enforced; `stop()` drains before cancelling.
- [ ] **F055** — `RepairPipeline.run` snapshots `current` before each stage and restores on exception; `repair.stage_rolled_back` log event live; warning string updated to `"rolled back"`.
- [ ] `make check-full` green.
- [ ] Scheduling integration test (`pytest -m integration -k scheduling`) green.
- [ ] Pyright clean on the three target files (matches preflight baseline of 0).
- [ ] PR title: `fix(scheduling+qa): leader-lock CAS, non-blocking jobs, repair stage rollback (F038 F039 F055; F037 verified)`.
- [ ] `TECH_DEBT_AUDIT.md` annotations: F037 — VERIFIED-NO-CHANGE; F038, F039, F055 — RESOLVED with PR ref.
