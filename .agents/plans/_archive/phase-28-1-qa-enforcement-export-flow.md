# Plan: Phase 28.1 — QA Enforcement in Export Flow

## Context

`ConnectorService.export()` calls the ESP provider directly with only a rendering gate check (Phase 27.3). QA check failures (HTML validation, spam score, broken links, etc.) are completely ignored during export. This adds a parallel QA gate alongside the rendering gate, with per-project configuration and admin override.

## Existing Patterns (reference)

- **Rendering gate integration:** `app/connectors/service.py:131-161` — lazy import, `RenderingSendGate(db).evaluate()`, verdict-based branching (BLOCK → raise, WARN → log)
- **Gate schemas:** `app/rendering/gate_schemas.py` — `GateMode(StrEnum)`, `GateVerdict(StrEnum)`, `GateResult(BaseModel)`
- **Gate config resolution:** `app/rendering/gate.py:140-164` — settings defaults → project JSON column override
- **QA check names:** `html_validation`, `css_support`, `css_audit`, `file_size`, `link_validation`, `spam_score`, `dark_mode`, `accessibility`, `fallback`, `image_optimization`, `brand_compliance`, `personalisation_syntax`, `deliverability`, `liquid_syntax` (14 total, from `app/qa_engine/checks/__init__.py`)
- **QA run interface:** `QAEngineService(db).run_checks(QARunRequest(html=..., project_id=...)) -> QAResultResponse`
- **Project model JSON columns:** `qa_profile`, `design_system`, `template_config`, `rendering_gate_config` — all `JSON, nullable=True`
- **Connector route pattern:** `app/connectors/routes.py` — `require_role("developer")`, `@limiter.limit("10/minute")`

## Files to Create

| File | Purpose |
|------|---------|
| `app/connectors/qa_gate.py` | `ExportQAGate` — evaluates QA checks and classifies as blocking/warning |
| `app/connectors/qa_gate_schemas.py` | Schemas: `ExportQAConfig`, `QAGateResult`, `QAGateVerdict`, `QACheckSummary`, `ExportPreCheckRequest`, `ExportPreCheckResponse` |
| `app/connectors/tests/test_qa_gate.py` | 15+ unit tests for the QA gate |
| `alembic/versions/w7x8y9z0a1b2_add_export_qa_config_to_projects.py` | Migration: add `export_qa_config` JSON column |

## Files to Modify

| File | Change |
|------|--------|
| `app/connectors/service.py` | Add QA gate check in `export()`, add `skip_qa_gate` support |
| `app/connectors/schemas.py` | Add `skip_qa_gate` to `ExportRequest`, `qa_gate_result` to `ExportResponse` |
| `app/connectors/routes.py` | Add `POST /export/pre-check` endpoint |
| `app/connectors/exceptions.py` | Add `ExportQAGateBlockedError` |
| `app/core/config.py` | Add `ExportConfig` with QA gate defaults |
| `app/projects/models.py` | Add `export_qa_config` JSON column |

## Implementation Steps

### Step 1: Config — `app/core/config.py`

Add `ExportConfig` class after `VariantsConfig` (line ~506):

```python
class ExportConfig(BaseModel):
    """Export pipeline gate settings."""
    qa_gate_mode: str = "warn"  # enforce | warn | skip
    qa_blocking_checks: list[str] = Field(default_factory=lambda: [
        "html_validation", "link_validation", "spam_score",
        "personalisation_syntax", "liquid_syntax",
    ])
    qa_warning_checks: list[str] = Field(default_factory=lambda: [
        "accessibility", "dark_mode", "image_optimization", "file_size",
    ])
```

Add `export: ExportConfig = ExportConfig()` to `Settings` class.

### Step 2: Schemas — `app/connectors/qa_gate_schemas.py`

```python
class QAGateMode(StrEnum):
    enforce = "enforce"
    warn = "warn"
    skip = "skip"

class QAGateVerdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"

class QACheckSummary(BaseModel):
    check_name: str
    passed: bool
    score: float  # 0.0-1.0
    severity: str  # "blocking" | "warning"
    details: str | None = None

class QAGateResult(BaseModel):
    passed: bool
    verdict: QAGateVerdict
    mode: QAGateMode
    blocking_failures: list[QACheckSummary] = []
    warnings: list[QACheckSummary] = []
    checks_run: int = 0
    evaluated_at: str  # ISO datetime

class ExportQAConfig(BaseModel):
    """Per-project export QA gate configuration."""
    mode: QAGateMode = QAGateMode.warn
    blocking_checks: list[str] = Field(default_factory=lambda: [
        "html_validation", "link_validation", "spam_score",
        "personalisation_syntax", "liquid_syntax",
    ])
    warning_checks: list[str] = Field(default_factory=lambda: [
        "accessibility", "dark_mode", "image_optimization", "file_size",
    ])
    ignored_checks: list[str] = Field(default_factory=list)

class ExportPreCheckRequest(BaseModel):
    html: str = Field(..., min_length=1, max_length=500_000)
    project_id: int | None = None
    target_clients: list[str] | None = None

class ExportPreCheckResponse(BaseModel):
    qa: QAGateResult
    rendering: GateResult | None = None  # from rendering gate_schemas
    can_export: bool
```

### Step 3: Exception — `app/connectors/exceptions.py`

Add after `ESPConflictError`:
```python
class ExportQAGateBlockedError(DomainValidationError):
    """Raised when QA gate blocks export in enforce mode."""
```

### Step 4: Gate logic — `app/connectors/qa_gate.py`

```python
class ExportQAGate:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate(self, html: str, project_id: int | None = None) -> QAGateResult:
        config = await self._resolve_config(project_id)
        if config.mode == QAGateMode.skip:
            return QAGateResult(passed=True, verdict=QAGateVerdict.PASS, mode=config.mode, evaluated_at=...)

        # Run QA checks
        qa_service = QAEngineService(self.db)
        result = await qa_service.run_checks(QARunRequest(html=html, project_id=project_id))

        # Classify each check result
        blocking_failures: list[QACheckSummary] = []
        warnings: list[QACheckSummary] = []
        for check in result.checks:
            if check.check_name in config.ignored_checks:
                continue
            summary = QACheckSummary(
                check_name=check.check_name, passed=check.passed,
                score=check.score, severity="blocking" if check.check_name in config.blocking_checks else "warning",
                details=check.details,
            )
            if not check.passed and check.check_name in config.blocking_checks:
                blocking_failures.append(summary)
            elif not check.passed and check.check_name in config.warning_checks:
                warnings.append(summary)

        # Determine verdict
        has_blocking = len(blocking_failures) > 0
        if not has_blocking:
            verdict = QAGateVerdict.PASS
        elif config.mode == QAGateMode.warn:
            verdict = QAGateVerdict.WARN
        else:
            verdict = QAGateVerdict.BLOCK

        return QAGateResult(
            passed=verdict != QAGateVerdict.BLOCK,
            verdict=verdict,
            mode=config.mode,
            blocking_failures=blocking_failures,
            warnings=warnings,
            checks_run=len(result.checks),
            evaluated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    async def _resolve_config(self, project_id: int | None) -> ExportQAConfig:
        # Settings defaults → project JSON column override (same pattern as rendering gate.py:140-164)
        settings = get_settings()
        defaults = ExportQAConfig(
            mode=QAGateMode(settings.export.qa_gate_mode),
            blocking_checks=settings.export.qa_blocking_checks,
            warning_checks=settings.export.qa_warning_checks,
        )
        if project_id is None:
            return defaults
        from app.projects.models import Project
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project or not project.export_qa_config:
            return defaults
        try:
            return ExportQAConfig.model_validate(project.export_qa_config)
        except Exception:
            logger.warning("qa_gate.invalid_project_config", project_id=project_id)
            return defaults
```

### Step 5: Modify `app/connectors/schemas.py`

Add to `ExportRequest`:
- `skip_qa_gate: bool = Field(default=False, description="Admin override to skip QA gate")`

Add to `ExportResponse`:
- `qa_gate_result: QAGateResult | None = None`
- Import `QAGateResult` from `app.connectors.qa_gate_schemas`

### Step 6: Modify `app/connectors/service.py` — `export()` method

Insert QA gate check **before** the existing rendering gate block (line 131). Pattern mirrors the rendering gate:

```python
# ── QA gate check (Phase 28.1) ──
settings = get_settings()
qa_gate_result: QAGateResult | None = None
if settings.export.qa_gate_mode != "skip" and not data.skip_qa_gate:
    from app.connectors.exceptions import ExportQAGateBlockedError
    from app.connectors.qa_gate import ExportQAGate
    from app.connectors.qa_gate_schemas import QAGateVerdict as QAVerdict

    qa_gate = ExportQAGate(self.db)
    gate_project_id = await self._resolve_project_id(data, user)
    qa_gate_result = await qa_gate.evaluate(html, gate_project_id)

    if qa_gate_result.verdict == QAVerdict.BLOCK:
        logger.warning(
            "connectors.export_qa_gate_blocked",
            blocking_checks=[f.check_name for f in qa_gate_result.blocking_failures],
            build_id=data.build_id,
        )
        raise ExportQAGateBlockedError(
            f"QA gate blocked export: "
            f"{', '.join(f.check_name for f in qa_gate_result.blocking_failures)} failed"
        )
elif data.skip_qa_gate:
    # Audit log for admin override
    logger.warning(
        "connectors.export_qa_gate_skipped",
        user_id=user.id,
        build_id=data.build_id,
    )
```

Attach `qa_gate_result` to both `ExportResponse` return paths.

**Admin enforcement for `skip_qa_gate`:** Add role check at the top of `export()`:
```python
if data.skip_qa_gate and user.role != "admin":
    raise ForbiddenError("Only admins can skip QA gate")
```

### Step 7: Pre-check endpoint — `app/connectors/routes.py`

Add after the existing export route:

```python
@router.post("/export/pre-check", response_model=ExportPreCheckResponse)
@limiter.limit("10/minute")
async def export_pre_check(
    request: Request,
    data: ExportPreCheckRequest,
    service: ConnectorService = Depends(get_service),
    _current_user: User = Depends(require_role("developer")),
) -> ExportPreCheckResponse:
    """Dry-run QA + rendering gates without exporting."""
    _ = request
    return await service.pre_check(data)
```

Add `pre_check()` method to `ConnectorService`:
- Run `ExportQAGate.evaluate(html, project_id)`
- Run `RenderingSendGate.evaluate(GateEvaluateRequest(html=html, project_id=project_id, target_clients=target_clients))` if rendering gate not skipped
- Return `ExportPreCheckResponse(qa=qa_result, rendering=render_result, can_export=qa_result.passed and (render_result is None or render_result.passed))`

### Step 8: Project model — `app/projects/models.py`

Add after `rendering_gate_config` (line 70):
```python
export_qa_config: Mapped[dict[str, Any] | None] = mapped_column(
    JSON, nullable=True, default=None,
    comment="Per-project export QA gate configuration (mode, blocking/warning checks)",
)
```

### Step 9: Migration

Create `alembic/versions/w7x8y9z0a1b2_add_export_qa_config_to_projects.py`:
- `op.add_column("projects", sa.Column("export_qa_config", sa.JSON(), nullable=True))`
- Downgrade: `op.drop_column("projects", "export_qa_config")`

### Step 10: Tests — `app/connectors/tests/test_qa_gate.py`

Use `AsyncMock` for db sessions. Test cases:

**ExportQAGate.evaluate():**
1. All checks pass → `QAGateVerdict.PASS`
2. Blocking check fails, mode=enforce → `QAGateVerdict.BLOCK`
3. Blocking check fails, mode=warn → `QAGateVerdict.WARN`, `passed=True`
4. Warning check fails → `QAGateVerdict.PASS` (warnings don't block)
5. Mode=skip → `QAGateVerdict.PASS` without running checks
6. Ignored check fails → not counted
7. Per-project config overrides global defaults

**ConnectorService.export() integration:**
8. QA gate blocks → `ExportQAGateBlockedError` raised
9. QA gate warns → export proceeds, `qa_gate_result` in response
10. `skip_qa_gate=True` with admin → proceeds with audit log
11. `skip_qa_gate=True` with non-admin → `ForbiddenError`
12. QA blocks + rendering passes → still blocked
13. Both gates pass → export succeeds

**Pre-check endpoint:**
14. Returns combined QA + rendering results
15. `can_export=False` when QA blocks

## Security Checklist

| Item | Status |
|------|--------|
| Auth on new endpoint | `require_role("developer")` on `/export/pre-check` |
| Rate limiting | `@limiter.limit("10/minute")` |
| Admin-only override | `skip_qa_gate` validated server-side: `user.role != "admin"` → `ForbiddenError` |
| Audit trail | `skip_qa_gate` logged with `user_id`, `build_id` |
| Input validation | `html: max_length=500_000` on pre-check request (matches existing) |
| No secret leakage | Error messages use check names only, no internal details |
| SQL injection | No raw SQL — all via SQLAlchemy ORM |
| BOLA | Pre-check has no project-scoped data access; export inherits existing BOLA checks |

## Verification

- [ ] `make check` passes (lint, types, tests, security)
- [ ] `make test` — all 15+ new tests pass
- [ ] New endpoint has auth + rate limiting
- [ ] Admin override logged to structured logger
- [ ] Per-project config falls back to global defaults
- [ ] Error responses don't leak internal types
