# Deferred-Items Ledger Cleanup (Phase 50.6)

**Status:** Plan Ready. Drains the four pre-existing open entries in `.agents/deferred-items.json`. Orthogonal to the F057 thread — runs in parallel with §50.7.

## Execution Order Context

| | |
|---|---|
| **TODO.md ref** | §50.6 |
| **Step in Phase 50** | **Step 1b** — parallel with §50.7 (the F057 redesign). |
| **Prerequisites** | Step 0 (branch hygiene) decided. No code prerequisites. |
| **Parallel with** | §50.7 — different files, different reviewer. Safe to assign to a second contributor. |
| **Blocks downstream** | nothing |
| **Effort estimate** | ~½ dev-day total (≤2h per sub-item) |

### Start signal
Branch hygiene is resolved and a clean branch is checked out for this work.

### Done signal
- All four target entries in `.agents/deferred-items.json` have `status: "closed"` + populated `closed_commit` + a `closed_note` per entry.
- Each entry's `closes_when` condition is empirically satisfied (not just claimed).
- `make check-full` green after each sub-item.

## Recommended Sub-Order (smallest first, easiest review)

Items are independent — you can do them in any order or assign in parallel. Recommended order minimises context switching and lets the smallest, most testable items ship first to validate the workflow:

1. **§50.6.1** — `tech-debt-03-memory-isolation-embedding-stub` (~30min, smallest, isolated fixture)
2. **§50.6.2** — `tech-debt-03-briefs-user-isolation-test` (~45min, one new test file)
3. **§50.6.3** — `tech-debt-squawk-python-migrations` (~1h, includes a decision)
4. **§50.6.4** — `tech-debt-19-design-sync-flag-cull-deeper` (~2h, biggest, may split across two PRs)

---

## 50.6.1 — `tech-debt-03-memory-isolation-embedding-stub`

### What's broken
`app/tests/test_tenant_isolation.py` parametrises Memory rows alongside other entities for a cross-entity tenant-isolation regression, but the Memory branch is xfail (`@pytest.mark.xfail(strict=False)`) because `POST /memory/` calls `get_embedding_provider(settings)` and there's no test-time stub. Real embedding calls in CI would be expensive and flaky.

### Concrete tasks

> ⚠️ The original sketch had **three bugs**, all verified against source in preflight (2026-05-30): wrong stub signature, wrong monkeypatch target, wrong vector dim. Use the corrected version below verbatim.

1. **Add an `embedding_stub` fixture** in `app/tests/conftest.py` (the conftest that already backs this file's `db` fixture). Model it on the existing reusable mock at `app/memory/tests/test_service.py:50` (`embed → [[…]*1024]`).
   ```python
   @pytest.fixture
   def embedding_stub(monkeypatch: pytest.MonkeyPatch) -> None:
       """Deterministic zero-vector embedding provider for tenant-isolation tests."""

       class _StubProvider:
           # Signature MUST match the EmbeddingProvider protocol
           # (app/knowledge/embedding.py:26): embed(texts: list[str]) ->
           # list[list[float]]. MemoryService.store calls
           # `await self.embedding.embed([data.content])` (service.py:49)
           # and reads embeddings[0] (service.py:50) — a flat list would
           # store the scalar 0.0, not a vector.
           async def embed(self, texts: list[str]) -> list[list[float]]:
               return [[0.0] * 1024 for _ in texts]

       # Patch the name in the ROUTE module, not the source module.
       # app/memory/routes.py:12 does `from app.knowledge.embedding import
       # get_embedding_provider`, binding the symbol into app.memory.routes
       # at import time; _get_service (routes.py:27) calls that route-local
       # name. Patching app.knowledge.embedding would not rebind it.
       monkeypatch.setattr(
           "app.memory.routes.get_embedding_provider",
           lambda _settings: _StubProvider(),
       )
   ```
   - **Dim = 1024, not 1536.** The memory column is `Vector(1024)` (`app/memory/models.py:30`) and pgvector rejects a dimension mismatch on INSERT. `1536` is `ai.dimension` (OpenAI default) — the wrong knob; memory uses `knowledge.embedding_dimension = 1024`. (`embedding.py:177` is the *factory*, not the memory dim — ignore that pointer.)
   - **Do not** override the `_get_service` FastAPI dependency instead: it wraps `get_scoped_db` (`routes.py:25`), which is the exact scoping under test — replacing it would make the test vacuous. The deferred entry's `closes_when` sketch (`dependency_overrides[get_embedding_provider]`) is likewise wrong: `get_embedding_provider` is not a `Depends()` target.
2. **Flip the xfail to a passing assertion**: drop `marks=pytest.mark.xfail(...)` from the `memory` `pytest.param` (`test_tenant_isolation.py:186-196`) → plain `pytest.param("memory", id="memory")`. Add `embedding_stub` to the `test_no_cross_org_read` signature (harmless for the other rows — the patch only touches the memory route's provider lookup).
3. **Run under the integration harness** — this file module-skips without a live DB (`app/tests/conftest.py:101-116`):
   ```bash
   make test-integration   # sets TEST_DATABASE__URL + DATABASE__URL against live Postgres
   # scoped: TEST_DATABASE__URL=… DATABASE__URL=… uv run pytest \
   #   app/tests/test_tenant_isolation.py -k memory -v
   ```
   The memory row must **PASS** (not skip, not xpass). `make check` / a bare `-k memory` without those env vars collect-skips and proves nothing. The `GET /memory/{memory_id}` route exists and is scoped (`routes.py:68` → `_get_service` → `get_scoped_db`), so the `403/404` assertion is genuine — not a universal-404.
4. **Update the deferred entry** `tech-debt-03-memory-isolation-embedding-stub`: `status: "closed"`, `closed_commit: <SHA>`, `closed_note: "embedding_stub fixture monkeypatches app.memory.routes.get_embedding_provider with a 1024-dim stub; memory row promoted from xfail and asserts org-isolation positively under make test-integration. No production code touched."`

### Acceptance
- xfail removed; memory row **passes** (not skips, not xpasses) under `make test-integration`.
- `make check` green (memory row collect-skips in the unit job — expected).
- No production code changed (test-only PR).

### Files touched
| File | Change |
|------|--------|
| `app/tests/conftest.py` (or nearest applicable conftest) | Add `embedding_stub` fixture |
| `app/tests/test_tenant_isolation.py` | Drop the `@pytest.mark.xfail` on the Memory parametrise; thread the new fixture in |
| `.agents/deferred-items.json` | Flip entry to `closed` |

---

## 50.6.2 — `tech-debt-03-briefs-user-isolation-test`

### What's broken
Briefs are per-creator resources, not per-org, so the tenant-isolation harness checks the wrong thing for them. The deferred entry says the Briefs branch is currently `xfail(strict=False)` for the same reason. A real regression test for BOLA-by-creator on briefs doesn't exist.

### Concrete tasks
1. **Read `app/projects/tests/test_bola.py`** — this is the reference pattern for BOLA-by-creator regressions in the codebase. Mirror its structure.
2. **Create `app/briefs/tests/test_user_isolation.py`** with a test that:
   - Creates two users (A and B) via the existing test factory.
   - User A creates a brief via the brief service or repository.
   - As user B, attempt to read user A's brief via the `briefs` route — expect 404 or 403 (match what the existing brief routes return; do NOT silently leak existence).
   - As user B, attempt to update / delete the brief — expect the same.
3. **Verify filtering happens at the repository layer**, not just the route. Add an assertion that calls `app/briefs/repository.py` directly with user B's context and confirms no row is returned. This catches future bugs where someone removes the route-level check but the repository still leaks.
4. **Verify org isolation does NOT matter**: explicitly test that two users in the *same* org cannot read each other's briefs (this distinguishes briefs from org-scoped resources).
5. **Run** `uv run pytest app/briefs/tests/test_user_isolation.py -v`.
6. **Update the deferred entry**: `closed_commit: <SHA>`, `closed_note: "Created app/briefs/tests/test_user_isolation.py asserting BOLA-by-creator. Covers route-level and repository-level isolation; explicitly tests same-org-different-user as the contrast case."`

### Acceptance
- New test file exists and passes.
- Test exercises both route and repository layers.
- Same-org-different-user case is in the assertions.
- `make check` green.

### Files touched
| File | Change |
|------|--------|
| `app/briefs/tests/test_user_isolation.py` | New file |
| `.agents/deferred-items.json` | Flip entry to `closed` |

---

## 50.6.3 — `tech-debt-squawk-python-migrations`

### What's broken
The `migration-lint` job (Makefile + `.github/workflows/ci.yml` + `.pre-commit-config.yaml:94`) runs `squawk` over alembic migrations, but squawk v2.x only parses SQL — it can't read Python alembic migrations (`op.add_column`, `op.drop_column`, etc.), so the job is advisory (`continue-on-error: true` or `|| true`). The `# squawk-ignore` comments in `alembic/versions/normalize_schema_drift.py` are dead annotations waiting for a linter that respects them.

### Decision to make first (do this before coding)
Two paths — pick before writing code:

- **Option (a) — replace squawk with a Python-aware migration linter.** Examples: a small ruff custom rule, a hand-rolled AST checker that looks for `op.add_column(...nullable=False...)` without a default, or an existing tool like [migra](https://github.com/djrobstep/migra) (compares schemas, not migrations — different shape; evaluate). Effort: ~3-4h if writing a ruff plugin from scratch.
- **Option (b) — document the gap and remove the misleading CI signal.** Drop the squawk job from CI + pre-commit; replace with a one-line ADR / runbook note that says "migration safety is reviewed manually until a Python-aware linter exists." Effort: ~30min.

**Recommended:** **Option (b)** unless someone has empirical evidence that real migration bugs are slipping through. Squawk's value-prop is catching unsafe operations on large tables (long-locking ALTERs, etc.); if no migration in the last year actually caused production lock contention, the cost of building a replacement isn't justified.

### Concrete tasks — Option (a)
1. Write a custom checker that walks alembic migrations' AST looking for known-unsafe patterns: `op.add_column(..., nullable=False)` without a default, `op.drop_column`, `op.alter_column(type_=...)` on large tables, etc.
2. Wire into pre-commit + CI replacing the squawk hook.
3. Add tests against `alembic/versions/normalize_schema_drift.py` (which currently has `# squawk-ignore` comments).
4. Update `.agents/deferred-items.json` entry.

### Concrete tasks — Option (b)
1. **Remove the squawk hook** from `.pre-commit-config.yaml` (line 94).
2. **Drop the squawk job** from `.github/workflows/ci.yml`.
3. **Update the Makefile** `migration-lint` target — either remove it or replace with a no-op + comment explaining the gap.
4. **Strip `# squawk-ignore` comments** from `alembic/versions/normalize_schema_drift.py` (they were aspirational; no linter reads them).
5. **Add a runbook note** to `.claude/rules/architecture.md` or a new `.claude/docs/migration-safety.md`: "Migration safety is reviewed at PR time by the migration owner. Patterns to flag manually: NOT NULL adds without backfill, type changes on tables >1M rows, schema-wide locks."
6. **Update the deferred entry**: `closed_commit: <SHA>`, `closed_note: "Option (b) taken. squawk hook removed from CI + pre-commit; manual-review guidance documented at <path>. Re-evaluate when a Python-aware alembic linter exists."`

### Acceptance
- CI no longer reports a misleading "passing" advisory squawk check.
- Either: a real Python-aware linter exists and runs (a), or the gap is documented (b).
- `make check` green; pre-commit clean.

### Files touched (varies by option)
| File | Option (a) | Option (b) |
|------|-----------|-----------|
| `.pre-commit-config.yaml:94` | replace squawk hook | remove squawk hook |
| `.github/workflows/ci.yml` | swap CI step | remove CI step |
| `Makefile` (`migration-lint`) | repoint target | remove or no-op |
| `alembic/versions/normalize_schema_drift.py` | keep `# squawk-ignore` if linter respects them | strip dead comments |
| `.claude/rules/architecture.md` or new doc | optional | required (manual-review guidance) |
| `.agents/deferred-items.json` | flip to closed | flip to closed |

---

## 50.6.4 — `tech-debt-19-design-sync-flag-cull-deeper`

### What's broken
`app/core/config/design_sync.py` has 62 fields. The original tech-debt-19 sweep cut 66→62 (PR-C). Target is ≤30. Remaining cuts need feature retirement (deleting code + tests + flags together), not just constant-ization.

### Concrete tasks
1. **Inventory.** Read `app/core/config/design_sync.py` and `feature-flags.yaml`. For each field, classify into one of:
   - **(constantize)** — feature is keeper, the knob is over-engineering → promote to `Final` constant in `app/design_sync/tuning.py` and delete the config field.
   - **(retire-feature)** — feature is test-only-gated or unused in production → delete the feature code, its tests, and the config field together.
   - **(keep)** — actually used as a per-deployment knob → leave alone.
2. **Candidates from the deferred entry's `closes_when`:** `custom_component_*`, `wrapper_unwrap`, `vlm_verify_*` tuning knobs, `sibling_*` parameterized tests, `regression_strict`, `vlm_low_confidence_threshold`, `vlm_verify_client`. Verify each is actually test-only-gated by `grep -rn` the field name in `app/` excluding `tests/` — if zero hits, retire the feature.
3. **Split into two PRs** so any breakage is bisectable:
   - **PR 1:** the constantize set (additive — moves knobs to constants, no behavior change).
   - **PR 2:** the retire-feature set (deletes code + tests + flags together).
4. **Per PR:** run `make flag-audit`, `make check-full`, and verify the new field count is on the projected path (62 → ~45 after PR 1, ~45 → ≤30 after PR 2).
5. **Add a regression test** in `app/core/tests/test_config_design_sync.py`:
   ```python
   def test_design_sync_field_count_bounded():
       from app.core.config.design_sync import DesignSyncConfig
       assert len(DesignSyncConfig.model_fields) <= 30, "DESIGN_SYNC__* surface grew — see tech-debt-19-design-sync-flag-cull-deeper"
   ```
6. **Update the deferred entry** after PR 2 merges.

### Acceptance
- `len(DesignSyncConfig.model_fields) <= 30` and a test asserts it.
- `make flag-audit` clean.
- `make check-full` green.
- `feature-flags.yaml` entries for retired flags removed.

### Files touched
Varies — minimum:
| File | Change |
|------|--------|
| `app/core/config/design_sync.py` | Delete retired/constantized fields |
| `app/design_sync/tuning.py` | Add constants for the constantize set |
| `app/design_sync/{various}.py` | Update references — constants for (constantize); deletions for (retire) |
| `app/design_sync/tests/{test_custom_component_generator,test_wrapper_unwrap,…}.py` | Delete for the (retire) set |
| `feature-flags.yaml` | Drop retired entries |
| `app/core/tests/test_config_design_sync.py` | Add bounded-count test |
| `.agents/deferred-items.json` | Flip entry to `closed` |

### Risk
The biggest item by far. Read each candidate's actual usage (`grep -rn` in `app/`) before deletion — a "test-only-gated" field that has one non-test consumer becomes a production bug. If unsure on any specific field, leave it in PR 1's keep list.

---

## Out of Scope

- Adding new deferred items discovered during this work — those are separate phases.
- Touching `tech-debt-19-squash-empty-baseline` — that's §50.7's responsibility.
- Reformatting the deferred-items.json beyond the necessary status flips.
