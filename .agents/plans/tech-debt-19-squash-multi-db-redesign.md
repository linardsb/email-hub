# Squash Multi-DB Redesign (F057a — Phase 50.7)

**Status:** Plan Ready. Prerequisite for §50.5 (F057 — Execute Migration Squash). Closes deferred entry `tech-debt-19-squash-empty-baseline`.

## Why

The current squash flow shared by `scripts/squash-migrations.sh`, `scripts/squash-migrations-dryrun.sh`, and the runbook (`.agents/plans/tech-debt-19-runbook-db-squash.md` procedure step 5) runs `alembic revision --autogenerate` against the same DB that has just had all migrations applied. Autogenerate diffs `target_metadata` (Python models) against the live DB schema; when they match — which they always do at this point in the flow, by construction — the generated baseline is empty (`def upgrade(): pass`, zero `op.create_table`).

Production cutover would succeed deceptively (post-squash `alembic check` still passes because schema matches models regardless of baseline content), but the next fresh-DB bootstrap (CI staging, contributor onboarding, DR restore) runs the empty migration to completion with no tables created. First DB-touching request raises `UndefinedTable` / `relation does not exist`.

Empirical reproduction: applied all 47 migrations to a throwaway pgvector container on 2026-05-25, truncated `alembic_version`, ran `alembic revision --autogenerate` against a temp tree with empty `versions/`. Generated file contained `pass` with zero `op.create_table`. See `.agents/deferred-items.json` → `tech-debt-19-squash-empty-baseline` for full context.

## Design — Three-DB Flow

The root cause is conflating two roles in a single DB: "source of the schema we want to capture" and "target the autogenerate diff runs against." Separate them.

| DB | Role | Lifetime |
|----|------|----------|
| **DB-A** (reference) | Apply all current migrations → `pg_dump --schema-only` → reference schema | Throwaway pgvector container |
| **DB-B** (autogenerate target) | Empty pgvector → `alembic revision --autogenerate` runs against B → baseline contains `CreateTable` for every model (because B is empty, the diff = entire target_metadata) | Throwaway pgvector container |
| **DB-C** (validation) | Empty pgvector → apply only the new baseline → `pg_dump --schema-only` → result schema | Throwaway pgvector container |

**Acceptance:** `diff <(schema_A) <(schema_C)` is empty (modulo `alembic_version`). If diff is non-empty, the baseline is wrong; abort and triage.

Why this works: the autogenerate diff (B → models) is the full schema by definition, so it contains every `CreateTable`. Applying that baseline to an empty C and comparing to A proves the baseline faithfully reproduces what the migration sequence produces. Single-DB designs cannot make this claim.

## Files to Modify

| File | Change |
|------|--------|
| `scripts/squash-migrations-dryrun.sh` | Rewrite §4–§6 (squash flow + parity check) to use three containers. Add the `op.create_table` non-empty inline assertion. |
| `scripts/squash-migrations.sh` | Rewrite §6 (autogenerate step) to spin up an ephemeral empty pgvector container for the autogenerate target instead of running against the production DB. Production stays untouched until the stamp step. |
| `.agents/plans/tech-debt-19-runbook-db-squash.md` | Procedure step 5 rewritten to reflect the empty-DB autogenerate. Drop the BLOCKED warning callout once script changes land. Add an explicit operator-side check between steps 5 and 6: `grep -c "op.create_table" alembic/versions/baseline_squash_*.py` must equal the number of `target_metadata.tables` entries. |
| `.agents/deferred-items.json` | Flip `tech-debt-19-squash-empty-baseline.status` from `deferred` to `closed`; add `closed_commit`. |
| `TECH_DEBT_AUDIT.md` | F057 row: `BLOCKED — design flaw` → `READY — multi-DB squash flow validated; execution scheduled for [Phase 50.5 maintenance window]`. |

## Implementation Steps

### Step 1 — `squash-migrations-dryrun.sh` (the testable end-to-end)

Rewrite §4–§6 to:

1. Spin up **container A** on `${PORT_A:-55557}`, run `uv run alembic upgrade head`, `docker exec pg_dump` → `.squash-dryrun-tmp/schema_A.sql`.
2. Spin up **container B** on `${PORT_B:-55558}` (empty, no migrations applied). Copy `alembic/` to `.squash-dryrun-tmp/alembic/` and move existing `versions/*.py` into the archive subdir so `versions/` is empty.
3. Generate a temp `alembic.ini` with `script_location` pointing at `.squash-dryrun-tmp/alembic/` and `prepend_sys_path = $REPO_ROOT` (so `env.py` can `import app.*`).
4. `DATABASE__URL=…container-B… uv run alembic -c .squash-dryrun-tmp/alembic.ini --raiseerr revision --autogenerate -m baseline_dryrun --rev-id 0000_dryrun`.
5. **Inline assertion:** `grep -c "op.create_table" .squash-dryrun-tmp/alembic/versions/0000_dryrun_baseline_dryrun.py` must equal `python -c "from app.shared.models import Base; print(len(Base.metadata.tables))"`. Mismatch → `fail "baseline missing CreateTable for $N tables"`.
6. Spin up **container C** on `${PORT_C:-55559}`. Apply only the new baseline: `DATABASE__URL=…container-C… uv run alembic -c .squash-dryrun-tmp/alembic.ini upgrade head`.
7. `docker exec pg_dump` container C → `.squash-dryrun-tmp/schema_C.sql`.
8. `diff -q schema_A.sql schema_C.sql` → empty → PASS. Non-empty → print first 30 lines of diff and `fail`.

Cleanup: tear down all three containers in the `cleanup()` trap.

### Step 2 — `squash-migrations.sh` (the destructive sibling)

The destructive script doesn't need three DBs because the production DB IS DB-A. But it still needs **DB-B** (ephemeral empty container) for the autogenerate target. Rewrite §6:

```bash
# 6. Create baseline migration via autogenerate against an EMPTY throwaway DB
EPHEMERAL_PORT=$(comm -23 <(seq 55600 55700 | sort) <(lsof -nP -iTCP -sTCP:LISTEN | awk '{print $9}' | sed 's/.*://' | sort -u) | head -1)
EPHEMERAL_CONTAINER="squash-autogen-pg-$$"
docker run -d --rm --name "$EPHEMERAL_CONTAINER" \
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=email_hub \
    -p "${EPHEMERAL_PORT}:5432" pgvector/pgvector:pg16 >/dev/null
trap "docker rm -f $EPHEMERAL_CONTAINER >/dev/null 2>&1 || true" EXIT
# wait for TCP readiness from host…

DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${EPHEMERAL_PORT}/email_hub" \
    uv run alembic revision --autogenerate -m "baseline_squash_${DATESTAMP}"

# 6a. Operator-side assertion
NEW_BASELINE=$(ls -t alembic/versions/baseline_squash_${DATESTAMP}*.py | head -1)
CREATE_TABLE_COUNT=$(grep -c "op.create_table" "$NEW_BASELINE")
EXPECTED_COUNT=$(uv run python -c "from app.shared.models import Base; print(len(Base.metadata.tables))")
if [ "$CREATE_TABLE_COUNT" -lt "$EXPECTED_COUNT" ]; then
    fail "Baseline contains only $CREATE_TABLE_COUNT op.create_table but $EXPECTED_COUNT models exist. Aborting before stamp."
fi
```

The stamp step (`alembic stamp head`) still runs against production — same as today. Only the autogenerate target moves to the ephemeral container.

### Step 3 — Runbook update

Remove the ⚠️ BLOCKED callout at the top. Procedure step 5 becomes:

> **5. Execute the squash.**
> The script will:
> 1. Verify `alembic check` exits 0 against the production DB.
> 2. Take schema-only `pg_dump` to `alembic/baseline_schema_YYYYMMDD.sql`.
> 3. Spin up an ephemeral empty pgvector container.
> 4. Move all current migrations to `alembic/archive/YYYYMMDD/`.
> 5. Run `alembic revision --autogenerate -m baseline_squash_YYYYMMDD` **against the ephemeral container** (not production).
> 6. Verify the generated baseline contains `CreateTable` for every model (operator-side assertion: `op.create_table` count ≥ `len(Base.metadata.tables)`). Abort if not.
> 7. Stamp the production DB with the new baseline head.
> 8. Re-run `alembic check` against production (must exit 0).
> 9. Tear down the ephemeral container.

### Step 4 — Deferred-items closure

Once steps 1–3 ship and the dry-run passes end-to-end, flip `tech-debt-19-squash-empty-baseline`:

```json
{
  "id": "tech-debt-19-squash-empty-baseline",
  "status": "closed",
  "closed_commit": "<merge SHA>",
  "closed_note": "Multi-DB squash flow shipped per .agents/plans/tech-debt-19-squash-multi-db-redesign.md. Both scripts now autogenerate against an empty ephemeral DB; baseline contains op.create_table for every target_metadata table (verified by inline assertion). Dry-run validates schema parity against the all-migrations dump end-to-end."
}
```

## Acceptance Criteria

1. `bash scripts/squash-migrations-dryrun.sh` exits 0 end-to-end. All three containers spin up, baseline generates, parity check passes.
2. `grep -c "op.create_table"` on the dry-run's generated baseline equals `len(Base.metadata.tables)` (currently ~50; verify at implementation time).
3. `diff schema_A.sql schema_C.sql` is empty.
4. `scripts/squash-migrations.sh --i-know-what-i-am-doing` against a local dev DB produces a non-empty baseline + passes the operator-side assertion. Schema unchanged.
5. Existing `make check` / `make check-full` pass (no test regressions).
6. Runbook reads top-to-bottom as an executable procedure without the BLOCKED callout.

## Out of Scope

- Actually executing `make db-squash` against production. That stays in §50.5 — this phase only proves the flow is safe.
- Branch rebase coordination for contributors with open migrations. Still operational.
- Adding the squash to CI as a smoke test. The dry-run is safe to run in CI but adding it is a separate decision (3 pgvector containers per CI run is non-trivial).
- Squashing a second time later. The runbook's existing "out of scope" note stands.

## Risks

- **Risk:** `pgvector/pgvector:pg16` major version drift vs production Postgres. **Mitigation:** Pin the container tag to match production's `pg_version`; verify via `SELECT version()` before autogenerate.
- **Risk:** Models import side effects (e.g., reading `feature-flags.yaml`) fail when running inside the dry-run against a containerized DB. **Mitigation:** The current dry-run already runs `alembic upgrade head` against the container successfully, so `env.py` imports already resolve. Re-verify after the rewrite.
- **Risk:** Three pgvector containers + image pulls inflate dry-run runtime past CI tolerances. **Mitigation:** Reuse the same image (cached after first pull); each container is ~5s startup. Total dry-run target: under 90s.
- **Risk:** `target_metadata` includes tables not created by alembic migrations (e.g., manually created via raw SQL in env.py or seed scripts). **Mitigation:** The operator-side `op.create_table` count assertion catches this — if `len(target_metadata.tables) > op.create_table count`, the assertion fires and the operator triages.

## Effort

~½ dev-day for script rewrites + runbook update + end-to-end dry-run verification.

## Ordering

| Step | Depends on |
|------|-----------|
| 1 (dry-run rewrite) | — |
| 2 (destructive script rewrite) | 1 |
| 3 (runbook update) | 1 + 2 |
| 4 (close deferred-items) | merge SHA |
| 50.5 (execute squash) | this plan complete |
