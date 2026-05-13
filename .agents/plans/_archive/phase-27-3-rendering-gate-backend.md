# Plan: Phase 27.3 — Pre-Send Rendering Gate (Backend)

## Context

The frontend (gate-panel, hooks, types, export/push-to-ESP integration) is **done**. This plan covers the backend service, schemas, routes, config, migration, connector integration, and tests needed to serve those frontend contracts.

**Frontend contract** (`cms/apps/web/src/types/rendering-gate.ts`):
- `POST /api/v1/rendering/gate/evaluate` → `GateResult`
- `GET /api/v1/rendering/gate/config/{project_id}` → `RenderingGateConfig`
- `PUT /api/v1/rendering/gate/config/{project_id}` → `RenderingGateConfig`

## Files to Create/Modify

| Action | File | What |
|--------|------|------|
| **Create** | `app/rendering/gate.py` | `RenderingSendGate` service — evaluate gate, produce verdict |
| **Create** | `app/rendering/gate_schemas.py` | Pydantic schemas matching frontend types |
| **Modify** | `app/rendering/exceptions.py` | Add `RenderingGateBlockedError`, `InvalidGateConfigError` |
| **Modify** | `app/rendering/routes.py` | Add 3 gate endpoints |
| **Modify** | `app/rendering/service.py` | Add gate delegation methods |
| **Modify** | `app/core/config.py` | Add gate fields to `RenderingConfig` |
| **Modify** | `app/projects/models.py` | Add `rendering_gate_config` JSON column |
| **Modify** | `app/connectors/service.py` | Pre-export gate check in `export()` |
| **Create** | `alembic/versions/w8x9y0z1a2b3_add_rendering_gate_config.py` | Migration for new column |
| **Create** | `app/rendering/tests/test_gate.py` | Unit tests |

## Implementation Steps

### Step 1: Add config fields to `RenderingConfig`

In `app/core/config.py`, add to `RenderingConfig` (after `calibration` field at line 245):

```python
# Gate settings (Phase 27.3)
gate_mode: str = "warn"  # enforce | warn | skip
gate_tier1_threshold: float = 85.0
gate_tier2_threshold: float = 70.0
gate_tier3_threshold: float = 60.0
```

### Step 2: Add exceptions

In `app/rendering/exceptions.py`, append:

```python
class RenderingGateBlockedError(DomainValidationError):
    """Raised when rendering gate blocks an export in enforce mode."""


class InvalidGateConfigError(DomainValidationError):
    """Raised when gate config values are invalid."""
```

### Step 3: Create gate schemas (`app/rendering/gate_schemas.py`)

Must match frontend types exactly. Fields/types:

```python
"""Pydantic schemas for the pre-send rendering gate."""
from __future__ import annotations

import datetime
from enum import Enum

from pydantic import BaseModel, Field


class GateMode(str, Enum):
    enforce = "enforce"
    warn = "warn"
    skip = "skip"


class GateVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class GateEvaluateRequest(BaseModel):
    html: str = Field(..., min_length=1, max_length=500_000)
    target_clients: list[str] | None = None
    project_id: int | None = None


class ClientGateResult(BaseModel):
    client_name: str
    confidence_score: float  # 0-100
    threshold: float  # 0-100
    passed: bool
    tier: str  # "tier_1" | "tier_2" | "tier_3"
    blocking_reasons: list[str] = []
    remediation: list[str] = []


class GateResult(BaseModel):
    passed: bool
    verdict: GateVerdict
    mode: GateMode
    client_results: list[ClientGateResult] = []
    blocking_clients: list[str] = []
    recommendations: list[str] = []
    evaluated_at: str  # ISO datetime string


class RenderingGateConfigSchema(BaseModel):
    """Project-level gate configuration."""
    mode: GateMode = GateMode.warn
    tier_thresholds: dict[str, float] = Field(
        default_factory=lambda: {"tier_1": 85.0, "tier_2": 70.0, "tier_3": 60.0}
    )
    target_clients: list[str] = Field(default_factory=list)
    require_external_validation: list[str] = Field(default_factory=list)


class GateConfigUpdateRequest(BaseModel):
    """Partial update for gate config."""
    mode: GateMode | None = None
    tier_thresholds: dict[str, float] | None = None
    target_clients: list[str] | None = None
    require_external_validation: list[str] | None = None
```

### Step 4: Create gate service (`app/rendering/gate.py`)

Core logic:

```python
"""Pre-send rendering gate — evaluates rendering confidence against thresholds."""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rendering.gate_schemas import (
    ClientGateResult,
    GateEvaluateRequest,
    GateMode,
    GateResult,
    GateVerdict,
    RenderingGateConfigSchema,
)
from app.rendering.local.confidence import RenderingConfidenceScorer
from app.rendering.local.profiles import CLIENT_PROFILES

logger = get_logger(__name__)
```

**Client → tier mapping** (module-level constant):

```python
CLIENT_TIERS: dict[str, str] = {
    "gmail_web": "tier_1",
    "outlook_desktop": "tier_1",
    "apple_mail": "tier_1",
    "outlook_2019": "tier_1",
    "yahoo_web": "tier_2",
    "yahoo_mobile": "tier_2",
    "samsung_mail": "tier_2",
    "thunderbird": "tier_2",
    "android_gmail": "tier_3",
    "outlook_web": "tier_3",
    "outlook_dark": "tier_3",
    "samsung_mail_dark": "tier_3",
    "android_gmail_dark": "tier_3",
    "mobile_ios": "tier_3",
}
```

**Default target clients** (used when no project config or request override):

```python
DEFAULT_GATE_CLIENTS: list[str] = [
    "gmail_web", "outlook_desktop", "apple_mail",
    "yahoo_web", "samsung_mail", "thunderbird",
    "android_gmail", "outlook_web",
]
```

**`RenderingSendGate` class:**

```python
class RenderingSendGate:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._scorer = RenderingConfidenceScorer()

    async def evaluate(self, request: GateEvaluateRequest) -> GateResult:
        """Evaluate rendering confidence against gate thresholds."""
        config = await self._resolve_config(request.project_id)

        if config.mode == GateMode.skip:
            return GateResult(
                passed=True, verdict=GateVerdict.PASS, mode=config.mode,
                evaluated_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )

        # Determine target clients (request override > project config > defaults)
        clients = request.target_clients or config.target_clients or DEFAULT_GATE_CLIENTS
        thresholds = config.tier_thresholds

        client_results: list[ClientGateResult] = []
        blocking: list[str] = []
        all_recommendations: list[str] = []

        for client_id in clients:
            profile = CLIENT_PROFILES.get(client_id)
            if not profile:
                continue

            # Score using existing confidence system
            confidence = self._scorer.score(request.html, profile)
            tier = CLIENT_TIERS.get(client_id, "tier_3")
            threshold = thresholds.get(tier, 60.0)
            passed = confidence.score >= threshold

            # Build blocking reasons from confidence breakdown
            reasons = self._blocking_reasons(confidence, client_id, threshold)
            remediation = self._remediation(confidence, client_id)

            if not passed:
                blocking.append(client_id)

            all_recommendations.extend(confidence.recommendations)

            client_results.append(ClientGateResult(
                client_name=client_id,
                confidence_score=confidence.score,
                threshold=threshold,
                passed=passed,
                tier=tier,
                blocking_reasons=reasons if not passed else [],
                remediation=remediation if not passed else [],
            ))

        # Determine verdict
        has_blocking = len(blocking) > 0
        if not has_blocking:
            verdict = GateVerdict.PASS
        elif config.mode == GateMode.warn:
            verdict = GateVerdict.WARN
        else:
            verdict = GateVerdict.BLOCK

        gate_passed = verdict != GateVerdict.BLOCK

        # Deduplicate recommendations
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recommendations:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return GateResult(
            passed=gate_passed,
            verdict=verdict,
            mode=config.mode,
            client_results=client_results,
            blocking_clients=blocking,
            recommendations=unique_recs[:10],
            evaluated_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
```

**Config resolution** (`_resolve_config`):
1. If `project_id` provided → query `Project.rendering_gate_config` JSON column
2. Parse into `RenderingGateConfigSchema` if present
3. Fall back to global defaults from `settings.rendering.gate_*`

```python
    async def _resolve_config(self, project_id: int | None) -> RenderingGateConfigSchema:
        settings = get_settings()
        defaults = RenderingGateConfigSchema(
            mode=GateMode(settings.rendering.gate_mode),
            tier_thresholds={
                "tier_1": settings.rendering.gate_tier1_threshold,
                "tier_2": settings.rendering.gate_tier2_threshold,
                "tier_3": settings.rendering.gate_tier3_threshold,
            },
        )
        if project_id is None:
            return defaults

        from app.projects.models import Project
        from sqlalchemy import select

        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project or not project.rendering_gate_config:
            return defaults

        try:
            return RenderingGateConfigSchema.model_validate(project.rendering_gate_config)
        except Exception:
            logger.warning("gate.invalid_project_config", project_id=project_id)
            return defaults
```

**Blocking reasons** (`_blocking_reasons`): Generate human-readable reasons from confidence breakdown:
- `css_compatibility < 0.7` → "Some CSS properties unsupported by {client}"
- `emulator_coverage < 0.5` → "Limited emulator coverage for {client}"
- `calibration_accuracy < 0.6` → "Low calibration accuracy — external validation recommended"
- `layout_complexity > 0.5` → "Complex layout reduces emulator accuracy"
- Include known blind spots from breakdown

**Remediation** (`_remediation`): Generate actionable suggestions:
- Low CSS compat on `outlook_desktop` → "Add MSO conditional with table-based fallback"
- Low overall → "Validate with Litmus or Email on Acid for {client}"
- Flexbox detected + Outlook → "Replace flexbox with table layout for Outlook clients"
- Client in `require_external_validation` → "External validation required for {client}"

### Step 5: Add `rendering_gate_config` column to Project model

In `app/projects/models.py`, add after `template_config` column:

```python
rendering_gate_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
```

### Step 6: Create Alembic migration

File: `alembic/versions/w8x9y0z1a2b3_add_rendering_gate_config.py`

Standard migration adding `rendering_gate_config` JSON column (nullable) to `projects` table. Follow pattern of existing migrations (e.g., `i4j5k6l7m8n9_add_template_config_to_project.py`).

### Step 7: Add gate methods to `RenderingService`

In `app/rendering/service.py`, add three methods:

```python
async def evaluate_gate(self, request: GateEvaluateRequest) -> GateResult:
    gate = RenderingSendGate(self.db)
    return await gate.evaluate(request)

async def get_gate_config(self, project_id: int) -> RenderingGateConfigSchema:
    gate = RenderingSendGate(self.db)
    return await gate._resolve_config(project_id)

async def update_gate_config(
    self, project_id: int, update: GateConfigUpdateRequest,
) -> RenderingGateConfigSchema:
    from app.projects.models import Project
    result = await self.db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    # Merge update into existing config (or defaults)
    current = await self.get_gate_config(project_id)
    merged = current.model_dump()
    update_data = update.model_dump(exclude_none=True)
    merged.update(update_data)

    # Validate merged config
    validated = RenderingGateConfigSchema.model_validate(merged)
    project.rendering_gate_config = validated.model_dump()
    await self.db.commit()
    return validated
```

Add necessary imports: `GateEvaluateRequest`, `GateResult`, `RenderingGateConfigSchema`, `GateConfigUpdateRequest` from `gate_schemas`, `RenderingSendGate` from `gate`, `NotFoundError` from `core.exceptions`.

### Step 8: Add gate routes to `app/rendering/routes.py`

Add 3 endpoints after the calibration section:

```python
# ── Gate endpoints (Phase 27.3) ──

@router.post("/gate/evaluate", response_model=GateResult)
@limiter.limit("10/minute")
async def evaluate_gate(
    request: Request,
    data: GateEvaluateRequest,
    service: RenderingService = Depends(get_service),
    _current_user: User = Depends(require_role("developer")),
) -> GateResult:
    """Evaluate rendering gate for given HTML."""
    _ = request
    return await service.evaluate_gate(data)


@router.get("/gate/config/{project_id}", response_model=RenderingGateConfigSchema)
@limiter.limit("30/minute")
async def get_gate_config(
    request: Request,
    project_id: int,
    service: RenderingService = Depends(get_service),
    _current_user: User = Depends(get_current_user),
) -> RenderingGateConfigSchema:
    """Get project-level gate configuration."""
    _ = request
    return await service.get_gate_config(project_id)


@router.put("/gate/config/{project_id}", response_model=RenderingGateConfigSchema)
@limiter.limit("10/minute")
async def update_gate_config(
    request: Request,
    project_id: int,
    data: GateConfigUpdateRequest,
    service: RenderingService = Depends(get_service),
    _current_user: User = Depends(require_role("admin")),
) -> RenderingGateConfigSchema:
    """Update project-level gate configuration (admin only)."""
    _ = request
    return await service.update_gate_config(project_id, data)
```

Add imports for `GateEvaluateRequest`, `GateResult`, `RenderingGateConfigSchema`, `GateConfigUpdateRequest` from `app.rendering.gate_schemas`.

### Step 9: Integrate gate into `ConnectorService.export()`

In `app/connectors/service.py`, modify `export()` method. **Before** calling `provider.export()` (around line 112, after `html = await self._resolve_html(data, user)`):

```python
# ── Rendering gate check (Phase 27.3) ──
settings = get_settings()
if settings.rendering.gate_mode != "skip":
    from app.rendering.gate import RenderingSendGate
    from app.rendering.gate_schemas import GateEvaluateRequest, GateMode, GateVerdict
    from app.rendering.exceptions import RenderingGateBlockedError

    gate = RenderingSendGate(self.db)
    # Resolve project_id from build or connection
    gate_project_id = await self._resolve_project_id(data, user)
    gate_result = await gate.evaluate(GateEvaluateRequest(
        html=html, project_id=gate_project_id,
    ))

    if gate_result.verdict == GateVerdict.BLOCK:
        logger.warning(
            "connectors.export_gate_blocked",
            blocking_clients=gate_result.blocking_clients,
            build_id=data.build_id,
        )
        raise RenderingGateBlockedError(
            f"Rendering gate blocked export: {', '.join(gate_result.blocking_clients)} "
            f"below confidence threshold"
        )

    if gate_result.verdict == GateVerdict.WARN:
        logger.info(
            "connectors.export_gate_warning",
            blocking_clients=gate_result.blocking_clients,
            build_id=data.build_id,
        )
```

Add `_resolve_project_id` helper to `ConnectorService`:

```python
async def _resolve_project_id(self, data: ExportRequest, user: User) -> int | None:
    """Extract project_id from build or connection for gate evaluation."""
    if data.build_id:
        result = await self.db.execute(
            select(EmailBuild.project_id).where(EmailBuild.id == data.build_id)
        )
        row = result.scalar_one_or_none()
        return row if row else None
    if data.connection_id:
        result = await self.db.execute(
            select(ESPConnection.project_id).where(ESPConnection.id == data.connection_id)
        )
        return result.scalar_one_or_none()
    return None
```

### Step 10: Tests (`app/rendering/tests/test_gate.py`)

Test cases using `RenderingConfidenceScorer` with real golden templates from `app/ai/templates/library/`:

| Test | What |
|------|------|
| `test_gate_skip_mode_always_passes` | Mode=skip → passed=True, verdict="pass" |
| `test_gate_simple_html_passes_all_tiers` | Simple table-based HTML → all clients pass |
| `test_gate_flexbox_blocks_outlook` | HTML with `display:flex` → outlook_desktop blocked |
| `test_gate_warn_mode_passes_with_warnings` | Mode=warn + low confidence → verdict="warn", passed=True |
| `test_gate_enforce_mode_blocks` | Mode=enforce + low confidence → verdict="block", passed=False |
| `test_gate_project_config_override` | Per-project thresholds override globals |
| `test_gate_default_clients_used` | No target_clients → DEFAULT_GATE_CLIENTS used |
| `test_gate_request_clients_override` | Request target_clients override project config |
| `test_blocking_reasons_populated` | Failed client has non-empty blocking_reasons |
| `test_remediation_populated` | Failed client has non-empty remediation |
| `test_gate_config_crud` | get/update gate config round-trip |
| `test_connector_export_gate_block` | Export with enforce mode → RenderingGateBlockedError |
| `test_connector_export_gate_skip` | Export with skip mode → no gate check |

Use `AsyncMock` for DB sessions. Load test HTML from `Path("app/ai/templates/library").glob("*.html")` for realistic tests. For the flexbox test, use minimal synthetic HTML: `<table><tr><td style="display:flex">test</td></tr></table>`.

## Security Checklist

| Endpoint | Auth | Rate Limit | Input Validation | Error Sanitization |
|----------|------|------------|------------------|--------------------|
| `POST /gate/evaluate` | `require_role("developer")` | 10/min | `html` max 500k, `target_clients` validated against `CLIENT_PROFILES` | Generic error via `AppError` handlers |
| `GET /gate/config/{id}` | `get_current_user` | 30/min | `project_id` int path param | NotFoundError if project missing |
| `PUT /gate/config/{id}` | `require_role("admin")` | 10/min | Pydantic validation on `GateConfigUpdateRequest` | InvalidGateConfigError for bad thresholds |

- Gate evaluation is **read-only analysis** — no side effects
- Config update requires **admin role**
- No new external network calls — uses existing local confidence scorer
- `rendering_gate_config` JSON column is nullable — no migration risk
- Connector gate check uses existing `DomainValidationError` subclass → 422 response with safe message

## Verification

- [ ] `make check` passes (lint + types + tests + frontend + security)
- [ ] `POST /gate/evaluate` returns `GateResult` matching frontend types
- [ ] `GET/PUT /gate/config/{id}` returns `RenderingGateConfig` matching frontend types
- [ ] Export with enforce mode + low confidence → 422 with gate blocked error
- [ ] Export with warn mode → succeeds with logged warning
- [ ] Export with skip mode → no gate evaluation
- [ ] Per-project config overrides global defaults
- [ ] Frontend gate panel renders correctly with backend responses
