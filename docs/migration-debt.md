# Migration Safety Debt

## Squawk pre-commit hook stays advisory (`|| true` retained)

`.pre-commit-config.yaml:93` runs Squawk against staged migration files but
swallows the exit code:

```yaml
entry: bash -c 'command -v squawk >/dev/null 2>&1 && git diff --cached --name-only --diff-filter=ACM | grep "alembic/versions/.*\.py$" | xargs -I{} squawk --reporter=compact {} || true'
```

### Why it stays advisory in Phase 1b

- **Squawk is not part of the dev-environment baseline.** It is not in
  `pyproject.toml`, not auto-installed by `make install-hooks`, and not
  documented in any developer setup path. Removing `|| true` would silently
  hard-fail commits on every contributor who never installed Squawk.
- **Pre-flight verification of an ignore mechanism (Phase 1b §1.5 Step 6)
  was not feasible** because Squawk was unavailable on the planning machine.
  Without proof that `--exclude-rule` / `.squawk.toml` works reliably, we
  cannot promote it to a hard gate without risk of a 44-migration history
  triggering rules on already-shipped DDL.
- **CI already enforces Squawk** at `.github/workflows/ci.yml:117-139` via
  the `migration-lint` job, scoped to `pull_request` events and to the diff
  vs. base branch. Hard enforcement happens there, where the runner is
  guaranteed to have Squawk installed.

The local hook is a quality-of-life nudge (catches issues before the dev
pushes), not a safety gate. The CI job is the safety gate.

### What unblocks promoting it to a hard gate

1. Add Squawk install to `make install-hooks` (or a shared `make bootstrap`
   target) so every dev has it.
2. Capture the current diff of `squawk --reporter=compact alembic/versions/*.py`
   against the existing migrations. If any rules fire on shipped migrations,
   create a `.squawk.toml` at repo root with `--exclude-rule` entries
   (one per rule) until the historical diff is clean.
3. Replace the `|| true` in `.pre-commit-config.yaml:93` with explicit error
   propagation: `... | xargs -I{} squawk --reporter=compact {}` (no trailing
   `|| true`). Commit the `.squawk.toml` in the same PR.

This unblock is Phase 2 (audit §2.4 `alembic check` work) territory — the
migration-lint job will get hardened alongside the new `alembic check` gate.

## `alembic check` is advisory (Phase 2 §2.4) — **CLOSED 2026-05-10**

Closed by `tech-debt/19-alembic-drift` — see migration
`alembic/versions/normalize_schema_drift.py`. The `migrations` job in
`.github/workflows/ci.yml` is now a hard gate (`continue-on-error: true`
removed). `alembic check` exits 0 against a fresh DB.

What landed:

- **TIMESTAMPTZ conversion** on 12 columns across 6 tables (blueprint
  checkpoints, design connections / import assets / imports / token
  snapshots, esp connections).
- **NOT NULL** on 10 created_at/updated_at columns across 5 tables
  (calibration records / summaries, component qa results, rendering
  screenshots / tests). NULL backfill ran first; local audit found 0
  NULLs.
- **HNSW index parity**: `ix_memory_entries_embedding_hnsw` declared in
  the model `__table_args__` matching the live `vector_cosine_ops` /
  `WITH (m=16, ef_construction=64)` indexdef.
- **Named unique constraint parity**: `qa_overrides_qa_result_id_key`
  declared in `__table_args__`; the redundant `ix_qa_overrides_qa_result_id`
  index dropped (the constraint's auto-index covers the query patterns).
- **Column comment parity**: 5 `collaborative_documents` comments
  written to DB; `design_token_snapshots.document_json` comment added
  to model.
- **JSONB parity**: `design_connections.config_json` model type updated
  from `JSON` to `JSONB`.
- **PK index suppression**: `alembic/env.py` `include_object` filter
  drops noisy `ix_<table>_id` findings for the 7 affected tables.

## Other migration-related deferrals

None at present. `alembic upgrade head` against a fresh DB is exercised in
the e2e-smoke job (in `ci.yml`) AND in the dedicated `migrations` job
introduced in Phase 2 §2.4.
