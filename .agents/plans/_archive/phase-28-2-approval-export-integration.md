# Plan: Phase 28.2 — Approval Workflow → Export Integration

## Context

The approval system (`app/approval/`) has a full state machine (`pending → approved/rejected/revision_requested`), audit trail, and BOLA checks — but is completely disconnected from the export pipeline. This wires approval as an optional third gate in `ConnectorService.export()`, alongside the QA gate (28.1) and rendering gate (27.3).

## Key Findings from Research

- **ApprovalRequest model** (`app/approval/models.py:10`): has `build_id` FK to `email_builds`, `project_id`, `status` (String(20)), `reviewed_by_id`, `review_note`
- **ApprovalRepository** (`app/approval/repository.py`): has `get()`, `list_by_project()` — no `get_by_build_id()` yet
- **ConnectorService.export()** (`app/connectors/service.py:131`): runs QA gate → rendering gate → ESP call. Uses lazy imports for gates. `_resolve_project_id()` already extracts project_id from build/connection
- **ExportRequest** (`app/connectors/schemas.py:10`): has `build_id`, `template_version_id`, `skip_qa_gate`
- **ExportResponse** (`app/connectors/schemas.py:35`): has `qa_gate_result` — needs `approval_result`
- **Project model** (`app/projects/models.py:27`): has JSON columns for `qa_profile`, `design_system`, `template_config`, `rendering_gate_config`, `export_qa_config` — no `require_approval_for_export` yet
- **ProjectUpdate schema** (`app/projects/schemas.py:44`): missing `require_approval_for_export`
- **Pre-check** (`app/connectors/service.py:299`): returns `ExportPreCheckResponse(qa, rendering, can_export)` — needs `approval`
- **ExportPreCheckRequest** (`app/connectors/qa_gate_schemas.py:70`): has `html`, `project_id`, `target_clients` — needs `build_id` for approval lookup
- **Test pattern** (`app/connectors/tests/test_qa_gate.py`): AsyncMock db, MagicMock users, `patch.object` for internal methods, `patch("module.Class")` for gate classes

## Files to Create

| File | Purpose |
|------|---------|
| `app/connectors/approval_gate.py` | `ExportApprovalGate` class |
| `app/connectors/approval_gate_schemas.py` | `ApprovalGateResult` schema |
| `app/connectors/tests/test_approval_gate.py` | 12+ unit tests |
| `alembic/versions/z0a1b2c3d4e5_add_require_approval_to_projects.py` | Migration |

## Files to Modify

| File | Change |
|------|--------|
| `app/approval/repository.py` | Add `get_by_build_id()` method |
| `app/connectors/service.py` | Add approval gate (3rd gate) in `export()` + approval in `pre_check()` |
| `app/connectors/schemas.py` | Add `skip_approval` to `ExportRequest`, `approval_result` to `ExportResponse` |
| `app/connectors/qa_gate_schemas.py` | Add `approval` field + `build_id` to `ExportPreCheckRequest`/`Response` |
| `app/connectors/exceptions.py` | Add `ApprovalRequiredError` |
| `app/projects/models.py` | Add `require_approval_for_export` column |
| `app/projects/schemas.py` | Add field to `ProjectUpdate` and `ProjectResponse` |

## Implementation Steps

### Step 1: Approval gate schemas (`app/connectors/approval_gate_schemas.py`)

```python
"""Pydantic schemas for the export approval gate."""
from __future__ import annotations
import datetime
from pydantic import BaseModel

class ApprovalGateResult(BaseModel):
    """Result of the export approval gate evaluation."""
    required: bool
    passed: bool
    reason: str | None = None
    approval_id: int | None = None
    approved_by: str | None = None
    approved_at: datetime.datetime | None = None
```

### Step 2: Add `ApprovalRequiredError` to `app/connectors/exceptions.py`

```python
class ApprovalRequiredError(DomainValidationError):
    """Raised when approval is required but not yet granted."""
```

### Step 3: Add `get_by_build_id()` to `app/approval/repository.py`

After existing `get()` method (~line 21):

```python
async def get_latest_by_build_id(self, build_id: int) -> ApprovalRequest | None:
    result = await self.db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.build_id == build_id)
        .where(ApprovalRequest.deleted_at.is_(None))
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
```

### Step 4: Create `app/connectors/approval_gate.py`

Pattern follows `ExportQAGate` (`app/connectors/qa_gate.py`):

```python
"""Export approval gate — checks approval status before ESP export."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.approval.models import ApprovalRequest
from app.auth.models import User
from app.connectors.approval_gate_schemas import ApprovalGateResult
from app.core.logging import get_logger

logger = get_logger(__name__)

class ExportApprovalGate:
    """Evaluates approval status for export gate."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate(
        self, build_id: int | None, project_id: int | None
    ) -> ApprovalGateResult:
        # No build_id → template_version export, skip approval
        if build_id is None:
            return ApprovalGateResult(required=False, passed=True)

        # Check if project requires approval
        if not await self._project_requires_approval(project_id):
            return ApprovalGateResult(required=False, passed=True)

        # Look up latest approval for this build
        from app.approval.repository import ApprovalRepository
        repo = ApprovalRepository(self.db)
        approval = await repo.get_latest_by_build_id(build_id)

        if approval is None:
            return ApprovalGateResult(
                required=True, passed=False,
                reason="No approval request submitted",
            )

        status_map = {
            "pending": "Approval pending review",
            "revision_requested": "Revisions requested",
            "rejected": "Approval rejected",
        }
        if approval.status in status_map:
            return ApprovalGateResult(
                required=True, passed=False,
                approval_id=approval.id,
                reason=status_map[approval.status],
            )

        # approved
        return ApprovalGateResult(
            required=True, passed=True,
            approval_id=approval.id,
            approved_by=str(approval.reviewed_by_id),
            approved_at=approval.updated_at,  # pyright: ignore[reportAttributeAccessIssue]
        )

    async def _project_requires_approval(self, project_id: int | None) -> bool:
        if project_id is None:
            return False
        from app.projects.models import Project
        result = await self.db.execute(
            select(Project.require_approval_for_export)
            .where(Project.id == project_id)
        )
        value = result.scalar_one_or_none()
        return bool(value)
```

### Step 5: Add `require_approval_for_export` to Project model

In `app/projects/models.py`, after `export_qa_config` column (~line 76):

```python
require_approval_for_export: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False,
    comment="Require approval before ESP export",
)
```

### Step 6: Alembic migration

```python
"""Add require_approval_for_export to projects."""
# revision: z0a1b2c3d4e5
def upgrade():
    op.add_column("projects", sa.Column(
        "require_approval_for_export", sa.Boolean(),
        nullable=False, server_default=sa.text("false"),
        comment="Require approval before ESP export",
    ))

def downgrade():
    op.drop_column("projects", "require_approval_for_export")
```

### Step 7: Update project schemas (`app/projects/schemas.py`)

Add to `ProjectUpdate` (~line 49): `require_approval_for_export: bool | None = None`

Add to `ProjectResponse` (~line 59): `require_approval_for_export: bool = False`

### Step 8: Update connector schemas

**`app/connectors/schemas.py`** — Add to `ExportRequest`:
```python
skip_approval: bool = Field(default=False, description="Admin override to skip approval gate")
```

Add to `ExportResponse`:
```python
approval_result: ApprovalGateResult | None = None
```
(Import `ApprovalGateResult` from `app.connectors.approval_gate_schemas`)

**`app/connectors/qa_gate_schemas.py`** — Add to `ExportPreCheckRequest`:
```python
build_id: int | None = None
```

Add to `ExportPreCheckResponse`:
```python
approval: ApprovalGateResult | None = None
```
(Update `can_export` computation in service to include approval)

### Step 9: Wire approval gate into `ConnectorService.export()`

In `app/connectors/service.py`, after the admin `skip_qa_gate` check (~line 134), add parallel admin check for `skip_approval`:

```python
if data.skip_approval and user.role != "admin":
    raise ForbiddenError("Only admins can skip approval gate")
```

After the rendering gate block (~line 205), before credential resolution (~line 207), add:

```python
# ── Approval gate check (Phase 28.2) ──
approval_result: ApprovalGateResult | None = None
if not data.skip_approval:
    from app.connectors.approval_gate import ExportApprovalGate
    from app.connectors.exceptions import ApprovalRequiredError

    approval_gate = ExportApprovalGate(self.db)
    gate_project_id = gate_project_id or await self._resolve_project_id(data, user)
    approval_result = await approval_gate.evaluate(data.build_id, gate_project_id)

    if not approval_result.passed and approval_result.required:
        logger.warning(
            "connectors.export_approval_gate_blocked",
            reason=approval_result.reason,
            build_id=data.build_id,
        )
        raise ApprovalRequiredError(
            f"Approval required: {approval_result.reason}"
        )
elif data.skip_approval:
    logger.warning(
        "connectors.export_approval_skipped",
        user_id=user.id,
        build_id=data.build_id,
    )
```

Add `approval_result=approval_result` to both `ExportResponse(...)` returns.

**Note:** Reuse `gate_project_id` from QA gate — avoid duplicate DB lookup. Move `gate_project_id = await self._resolve_project_id(data, user)` before the QA gate block so all three gates share it.

### Step 10: Wire approval into `ConnectorService.pre_check()`

After rendering gate evaluation (~line 322), add:

```python
approval_result = None
if data.build_id is not None:
    from app.connectors.approval_gate import ExportApprovalGate
    approval_gate = ExportApprovalGate(self.db)
    approval_result = await approval_gate.evaluate(data.build_id, data.project_id)

can_export = (
    qa_result.passed
    and (render_result is None or render_result.passed)
    and (approval_result is None or approval_result.passed)
)
return ExportPreCheckResponse(
    qa=qa_result, rendering=render_result,
    approval=approval_result, can_export=can_export,
)
```

### Step 11: Tests (`app/connectors/tests/test_approval_gate.py`)

Follow pattern from `test_qa_gate.py`. Key test cases:

**`TestExportApprovalGateEvaluate`** (unit tests on `ExportApprovalGate.evaluate()`):
1. `test_no_build_id_skips_approval` — `build_id=None` → `required=False, passed=True`
2. `test_project_not_requiring_approval_passes` — `require_approval_for_export=False` → `required=False, passed=True`
3. `test_no_approval_request_blocks` — required project, no ApprovalRequest → `passed=False, reason="No approval request submitted"`
4. `test_pending_approval_blocks` — status=pending → `passed=False`
5. `test_approved_passes` — status=approved → `passed=True, approved_by set`
6. `test_rejected_blocks` — status=rejected → `passed=False`
7. `test_revision_requested_blocks` — status=revision_requested → `passed=False`

**`TestApprovalGateIntegration`** (in `ConnectorService.export()`):
8. `test_approval_required_no_request_raises` — `ApprovalRequiredError` raised
9. `test_approval_not_required_proceeds` — export succeeds when project doesn't require approval
10. `test_skip_approval_admin_proceeds` — admin `skip_approval=True` bypasses
11. `test_skip_approval_non_admin_forbidden` — `ForbiddenError`
12. `test_template_version_export_skips_approval` — `template_version_id` without `build_id` → approval gate not invoked
13. `test_qa_passes_rendering_passes_approval_blocks` — all gates run, approval blocks last
14. `test_pre_check_includes_approval_result` — `pre_check()` returns `approval` field

## Security Checklist

| Item | Status |
|------|--------|
| Auth on endpoints | No new endpoints — existing `export` and `pre-check` already require `developer` role |
| BOLA | Approval gate uses read-only `ApprovalRepository.get_latest_by_build_id()` — no cross-tenant leak (approval stores `project_id`, build lookup is by build_id which is already BOLA-checked in `_resolve_html`) |
| Rate limiting | Existing rate limits on `/export` and `/export/pre-check` apply |
| Admin override audit | `skip_approval=True` logged with `user_id` and `build_id` |
| Input validation | `skip_approval` is `bool` field with default `False` — no injection vector |
| Error messages | `ApprovalRequiredError` messages expose only approval status, not internals |

## Verification

- [ ] `make check` passes (lint, types, tests, security-check)
- [ ] New column migration applies cleanly (`make db-migrate`)
- [ ] Export with `require_approval=true`, no approval → `ApprovalRequiredError`
- [ ] Export with `require_approval=true`, approved → succeeds
- [ ] Export with `require_approval=false` → proceeds without approval check
- [ ] Admin `skip_approval=true` → proceeds with audit log
- [ ] Template version export (no build_id) → approval gate skipped
- [ ] Pre-check includes all three gate results
- [ ] `make test` passes
