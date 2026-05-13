# Plan: Phase 27.4 — Emulator Calibration Loop

## Context

Emulator rules approximate real client sanitizers. Without ground-truth calibration, they silently drift. This phase compares local emulator screenshots against external provider (Litmus/EoA/sandbox) screenshots, computes per-emulator accuracy via EMA, and updates confidence seeds. Samples builds to amortize external costs.

**Dependency:** Phase 27.2 confidence scoring is implemented. `RenderingConfidenceScorer` uses `calibration_accuracy` at 0.35 weight (highest). All 8 emulators have `sample_count: 0` in `confidence_seeds.yaml`. This phase makes those seeds dynamic.

## Files to Create

1. `app/rendering/calibration/__init__.py` — empty
2. `app/rendering/calibration/models.py` — `CalibrationRecord`, `CalibrationSummary`
3. `app/rendering/calibration/repository.py` — DB operations
4. `app/rendering/calibration/schemas.py` — request/response schemas
5. `app/rendering/calibration/calibrator.py` — `EmulatorCalibrator`
6. `app/rendering/calibration/sampler.py` — `CalibrationSampler`
7. `app/rendering/calibration/tests/__init__.py` — empty
8. `app/rendering/calibration/tests/test_calibrator.py`
9. `app/rendering/calibration/tests/test_sampler.py`
10. `alembic/versions/x8y9z0a1b2c3_add_calibration_tables.py`

## Files to Modify

1. `app/core/config.py` — add `CalibrationConfig` nested in `RenderingConfig`
2. `app/rendering/exceptions.py` — add `CalibrationError`
3. `app/rendering/routes.py` — add 3 calibration endpoints
4. `app/rendering/service.py` — add calibration methods, make `get_client_confidence` async
5. `app/rendering/local/confidence.py` — add `get_seed_with_db()` for DB-first lookup

## Implementation Steps

### Step 1: Config — `app/core/config.py`

Insert `CalibrationConfig` after `SandboxConfig` (line 214). Add `calibration` field to `RenderingConfig` after `sandbox` (line 233).

```python
class CalibrationConfig(BaseModel):
    """Emulator calibration loop settings."""
    enabled: bool = False
    rate_per_client_per_day: int = 3
    monthly_budget: float = 0.0  # 0 = disabled
    regression_threshold: float = 10.0  # % drop that triggers warning
    ema_alpha: float = 0.3
    max_history: int = 100
```

Add to `RenderingConfig`: `calibration: CalibrationConfig = CalibrationConfig()`

### Step 2: Exceptions — `app/rendering/exceptions.py`

Append:

```python
class CalibrationError(AppError):
    """Raised when calibration comparison fails."""
```

### Step 3: Models — `app/rendering/calibration/models.py`

Two models following `ScreenshotBaseline` pattern from `app/rendering/models.py`:

**`CalibrationRecord`** — individual measurement:
- `id`, `client_id` (String(50), indexed), `html_hash` (String(64) — SHA-256, no raw HTML), `diff_percentage` (Float), `accuracy_score` (Float), `pixel_count` (Integer), `external_provider` (String(50) — "litmus"|"emailonacid"|"sandbox"|"manual"), `emulator_version` (String(64) — hash of rules at calibration time), `error_message` (Text, nullable)
- Inherits `TimestampMixin`

**`CalibrationSummary`** — aggregate per client:
- `id`, `client_id` (String(50), indexed, unique constraint `uq_calibration_summary_client`), `current_accuracy` (Float, default 50.0), `sample_count` (Integer, default 0), `accuracy_trend` (JSON — last 10 values), `known_blind_spots` (JSON), `last_provider` (String(50))
- `last_calibrated` derived from `updated_at` (via `TimestampMixin`)

### Step 4: Repository — `app/rendering/calibration/repository.py`

Follow `ScreenshotBaselineRepository` pattern from `app/rendering/repository.py`.

**`CalibrationRepository(db: AsyncSession)`:**
- `create_record(**kwargs) -> CalibrationRecord`
- `list_records(client_id, limit=20, offset=0) -> Sequence[CalibrationRecord]` — ordered by `created_at.desc()`
- `count_records(client_id) -> int`
- `count_today(client_id) -> int` — filter `func.date(created_at) == func.current_date()`
- `get_summary(client_id) -> CalibrationSummary | None`
- `list_summaries() -> Sequence[CalibrationSummary]` — ordered by `client_id`
- `upsert_summary(**kwargs) -> CalibrationSummary` — update existing or create new (same pattern as `ScreenshotBaselineRepository.upsert`)

### Step 5: Schemas — `app/rendering/calibration/schemas.py`

```python
class CalibrationResultSchema(BaseModel):
    client_id: str
    diff_percentage: float = Field(ge=0.0, le=100.0)
    accuracy_score: float = Field(ge=0.0, le=100.0)
    pixel_count: int = 0
    regression: bool = False
    regression_details: str | None = None

class CalibrationRecordResponse(BaseModel):
    id: int; client_id: str; html_hash: str; diff_percentage: float
    accuracy_score: float; pixel_count: int; external_provider: str
    emulator_version: str; created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class CalibrationSummaryResponse(BaseModel):
    client_id: str; current_accuracy: float; sample_count: int
    accuracy_trend: list[float] = []; known_blind_spots: list[str] = []
    last_provider: str = ""; last_calibrated: datetime.datetime | None = None
    model_config = ConfigDict(from_attributes=True)

class CalibrationSummaryListResponse(BaseModel):
    summaries: list[CalibrationSummaryResponse]

class CalibrationTriggerRequest(BaseModel):
    html: str = Field(..., min_length=1, max_length=500_000)
    client_ids: list[str] = Field(..., min_length=1, max_length=20)
    external_provider: str = Field(default="sandbox", pattern=r"^(litmus|emailonacid|sandbox|manual)$")

class CalibrationTriggerResponse(BaseModel):
    results: list[CalibrationResultSchema]; records_created: int

class CalibrationHistoryResponse(BaseModel):
    client_id: str; records: list[CalibrationRecordResponse]; total: int
```

### Step 6: Calibrator — `app/rendering/calibration/calibrator.py`

**Helper:** `_emulator_version_hash(client_id) -> str` — hash rule names from `_EMULATORS[client_id]` for drift detection. Returns `"no-emulator"` if not found.

**`EmulatorCalibrator(db: AsyncSession)`** with `self.repo = CalibrationRepository(db)`:

**`calibrate(html, client_id, local_screenshot, external_screenshot, external_provider) -> CalibrationResultSchema`:**
1. Compute `html_hash = sha256(html)`, `emulator_version = _emulator_version_hash(client_id)`
2. Call `compare_images(local_screenshot, external_screenshot)` from `app.rendering.visual_diff`
3. Accuracy formula: `max(0, 100 - diff_percentage * 2)` — 0% diff = 100, 50% diff = 0
4. Check regression: load `repo.get_summary(client_id)`, if `(old_accuracy - accuracy) > settings.rendering.calibration.regression_threshold` → regression=True, log `calibration.regression_detected`
5. Persist via `repo.create_record()`
6. Return `CalibrationResultSchema`

**`calibrate_batch(html, local_screenshots: dict[str, bytes], external_screenshots: dict[str, bytes], external_provider) -> list[CalibrationResultSchema]`:**
- Match by `set(local) & set(external)`, log unmatched clients, call `calibrate()` for each match

**`update_seeds(results: list[CalibrationResultSchema]) -> None`:**
- For each result, load summary from DB
- EMA: `new_accuracy = (1 - alpha) * old_accuracy + alpha * measured_accuracy` (alpha from config, default 0.3)
- First calibration (no summary): use measured directly, load `known_blind_spots` from YAML seeds via `_load_seeds()`
- Update `accuracy_trend` (keep last 10), increment `sample_count`
- Persist via `repo.upsert_summary()`

### Step 7: Sampler — `app/rendering/calibration/sampler.py`

**`CalibrationSampler(db: AsyncSession)`:**

**`should_calibrate(client_id) -> bool`:**
1. Return False if `calibration.enabled` is False
2. Get `count_today(client_id)` from repo
3. New emulators (`sample_count < 10`): 3x rate limit
4. Stale (`updated_at > 7 days ago`): 2x rate limit
5. Otherwise: standard `rate_per_client_per_day` check

**`select_html_for_calibration(candidates, client_id, max_selections=1) -> list[str]`:**
- Deduplicate by SHA-256 hash prefix, return up to `max_selections`

### Step 8: Confidence Scorer — `app/rendering/local/confidence.py`

Add async method to `RenderingConfidenceScorer`:

```python
async def get_seed_with_db(self, emulator_id: str, db: AsyncSession) -> dict[str, Any]:
    """DB-first seed lookup, YAML fallback."""
    from app.rendering.calibration.repository import CalibrationRepository
    repo = CalibrationRepository(db)
    summary = await repo.get_summary(emulator_id)
    if summary and summary.sample_count > 0:
        return {
            "accuracy": summary.current_accuracy / 100.0,  # normalize to 0-1
            "sample_count": summary.sample_count,
            "last_calibrated": summary.updated_at.isoformat() if summary.updated_at else "",
            "known_blind_spots": list(summary.known_blind_spots),
        }
    return self.get_seed(emulator_id)
```

Existing sync `get_seed()` stays unchanged for the sync `score()` path.

### Step 9: Routes — `app/rendering/routes.py`

Add 3 endpoints after sandbox endpoints (line 191). Import calibration schemas.

| Endpoint | Method | Auth | Rate | Description |
|----------|--------|------|------|-------------|
| `/calibration/summary` | GET | `get_current_user` | 30/min | All client calibration states |
| `/calibration/trigger` | POST | `require_role("admin")` | 3/min | Force calibration on HTML |
| `/calibration/history/{client_id}` | GET | `get_current_user` | 30/min | Per-client record history |

Follow exact pattern from existing endpoints (e.g., `sandbox_test`). `client_id` path param validated with `pattern=r"^[a-z][a-z0-9_]{1,50}$"`. History endpoint takes `limit: int = Query(20, ge=1, le=100)`.

### Step 10: Service — `app/rendering/service.py`

Add 3 new methods to `RenderingService`:

**`get_calibration_summary() -> CalibrationSummaryListResponse`** — list all summaries, map to response (use `s.updated_at` for `last_calibrated`)

**`get_calibration_history(client_id, limit=20) -> CalibrationHistoryResponse`** — list records + count total

**`trigger_calibration(data: CalibrationTriggerRequest) -> CalibrationTriggerResponse`:**
1. Render locally via `LocalRenderingProvider().render_screenshots(data.html, data.client_ids)`
2. Build `local_map: dict[str, bytes]` from results
3. For sandbox provider: use `SandboxRunner().capture_screenshots(data.html)` → `external_map`
4. For litmus/eoa: submit via `_get_provider()`, return empty response (async poll not implemented in trigger)
5. Call `calibrator.calibrate_batch()` then `calibrator.update_seeds()`

**Make `get_client_confidence` async** — change to use `await scorer.get_seed_with_db(client_id, self.db)`. Update the route call site (line 125) to `return await service.get_client_confidence(client_id)`.

### Step 11: Migration

File: `alembic/versions/x8y9z0a1b2c3_add_calibration_tables.py`
Revises: `w7x8y9z0a1b2`

Two tables: `calibration_records` and `calibration_summaries` with columns matching the models from Step 3. Follow the pattern from `w7x8y9z0a1b2_add_confidence_to_screenshots.py`. Use `sa.func.now()` for `server_default` on timestamps.

### Step 12: Tests — `test_calibrator.py`

Follow class-based pattern from `app/rendering/local/tests/test_confidence.py`. Mock `db` with `AsyncMock()`.

**`TestEmulatorVersionHash`** (4 tests):
- Known emulator → 16-char hex hash
- Unknown → `"no-emulator"`
- Same emulator → deterministic
- Different emulators → different hashes

**`TestEmulatorCalibrator`** (5 tests, mock `compare_images` + repo methods):
- Identical images → 0% diff, 100% accuracy, no regression
- 50% diff → 0% accuracy (linear cap)
- Accuracy drop > threshold → `regression=True` with details
- Batch matches by client_id, skips unmatched
- EMA update: `0.7 * 80 + 0.3 * 90 = 83.0`, sample_count incremented

### Step 13: Tests — `test_sampler.py`

**`TestCalibrationSampler`** (4 tests):
- Disabled → False
- Under rate limit → True
- At rate limit → False
- `select_html_for_calibration` deduplicates, respects max

## Security Checklist

| Endpoint | Auth | Rate | Input Validation | Notes |
|----------|------|------|------------------|-------|
| `GET /calibration/summary` | `get_current_user` | 30/min | None needed | Read-only aggregates |
| `POST /calibration/trigger` | `require_role("admin")` | 3/min | html 500KB, client_ids max 20, provider regex | Expensive op |
| `GET /calibration/history/{client_id}` | `get_current_user` | 30/min | client_id regex, limit 1-100 | html_hash only, no raw HTML |

- All queries use SQLAlchemy ORM — no `sa.text()` with user input
- HTML hashes stored in `CalibrationRecord`, never raw content (privacy)
- Calibration data is system-wide (not tenant-scoped) — no BOLA concern
- Budget cap (`monthly_budget`) prevents runaway external API costs
- Error classes inherit `AppError` hierarchy — no internal type leakage

## Verification

- [ ] `make check` passes
- [ ] 3 new endpoints have auth + rate limiting
- [ ] `GET /calibration/summary` returns per-client accuracy data
- [ ] `POST /calibration/trigger` creates CalibrationRecords with correct diff %
- [ ] EMA: `0.7 * old + 0.3 * measured` produces expected values
- [ ] Budget `$0.0` → no auto calibrations (manual trigger only)
- [ ] Accuracy regression >10% → `calibration.regression_detected` warning logged
- [ ] YAML seeds work as fallback when no DB calibration data exists
- [ ] HTML hashes stored, never raw HTML
