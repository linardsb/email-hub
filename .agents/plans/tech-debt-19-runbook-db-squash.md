# Runbook: Migration Squash (F057)

**Status:** Maintenance-window only. NOT executed by `/be-execute`. This runbook documents the procedure; the destructive operation runs under human supervision.

## When to run

Run **once** to collapse the current ~49 migrations in `alembic/versions/` into a single baseline. Triggers:

- After all open phase work converges on `main` (no rebase risk).
- When `alembic upgrade head` from an empty DB takes long enough to slow CI startup.
- When a developer reports "too many migrations to grep" — i.e., the linear log is consuming review time.

**Prerequisites:**

- ✅ `tech-debt-alembic-schema-drift` deferred entry is closed (was closed 2026-05-10).
- ✅ `alembic check` exits 0 against a fresh DB at head. Verify locally:
  ```bash
  uv run alembic upgrade head
  uv run alembic check
  # exit 0 required
  ```
- ✅ A full production pg_dump is uploaded to long-term storage (S3 or equivalent with ≥30-day retention).
- ✅ All active branches with new migrations have either merged or been rebased onto `main` (the squash invalidates branch migrations).

## Estimated impact

| Item | Value |
|------|-------|
| Production downtime | 30 min (app stopped) + 15 min (validation) |
| Reversibility window | Until pg_dump restore — assume 30 days |
| Files removed | ~49 from `alembic/versions/`, archived to `alembic/archive/YYYYMMDD/` |
| Files added | 1 baseline migration + 1 `baseline_schema_YYYYMMDD.sql` reference |
| Active branches blocked | All — every contributor must `git rebase main` after merge |

## Procedure

### 1. Announce the maintenance window

Post in `#engineering` 24h ahead with:
- Window start/end
- Branch freeze (no new migrations during the window)
- Link to this runbook

### 2. Take the production backup

```bash
# On the production host or a host with pg credentials:
PGPASSWORD="$PROD_DB_PASS" pg_dump \
  -h "$PROD_DB_HOST" \
  -p "$PROD_DB_PORT" \
  -U "$PROD_DB_USER" \
  -d "$PROD_DB_NAME" \
  --format=custom \
  --file=pre-squash-$(date +%Y%m%d).dump

# Upload to long-term storage and verify integrity
aws s3 cp pre-squash-*.dump s3://backups/db/long-term/
aws s3 ls s3://backups/db/long-term/ | tail
```

### 3. Validate the squash flow locally

Run the dry-run script (introduced alongside this runbook):

```bash
bash scripts/squash-migrations-dryrun.sh
# Exit 0 = the squash flow produces a clean baseline that:
#   (a) `alembic upgrade head` applies without error from an empty DB
#   (b) `alembic check` exits 0 post-upgrade
#   (c) `pg_dump --schema-only` of the squashed DB matches the pre-squash dump
```

If the dry-run fails, **STOP** and triage. The dry-run uses a disposable Postgres in Docker — failures there are guaranteed to break production.

### 4. Stop the application

```bash
# Production:
kubectl scale deployment email-hub --replicas=0
# OR Docker:
docker compose -f docker-compose.prod.yml stop app
```

Verify no active DB sessions:

```bash
psql -c "SELECT pid, state, query FROM pg_stat_activity WHERE datname='email_hub' AND pid <> pg_backend_pid();"
```

### 5. Execute the squash

```bash
# On a workstation with branch checked out at main:
git checkout main && git pull
bash scripts/squash-migrations.sh
# Confirms interactively — answer "y" to proceed.
```

The script will:

1. Verify `alembic check` exits 0
2. Take a schema-only `pg_dump` to `alembic/baseline_schema_YYYYMMDD.sql`
3. Move all current migrations to `alembic/archive/YYYYMMDD/`
4. Run `alembic revision --autogenerate -m baseline_squash_YYYYMMDD`
5. Stamp the DB with the new baseline head
6. Re-run `alembic check` (must exit 0)

### 6. Validate

```bash
uv run alembic check                        # exit 0
uv run alembic history                      # one revision, the new baseline
uv run pytest -m "not integration" -q       # full test suite green
docker compose up -d                        # boot the app
curl -sf http://localhost:8891/health       # 200 OK
```

If any validation step fails, jump to **Rollback**.

### 7. Commit + push

```bash
git add alembic/versions/ alembic/archive/ alembic/baseline_schema_*.sql
git commit -m "chore(migrations): squash to baseline_squash_$(date +%Y%m%d) (F057)"
git push origin main
```

### 8. Restart production

```bash
kubectl scale deployment email-hub --replicas=N    # N = pre-window replica count
# OR
docker compose -f docker-compose.prod.yml start app
```

Watch the logs for 5 minutes. `app.error` and `database.connection_initialized` are the key markers.

### 9. Notify

Post in `#engineering`:
- Window closed
- All contributors: `git checkout main && git pull && git rebase main` on every open branch with alembic changes
- Squash commit SHA + baseline schema file path

## Rollback

**Path 1 — squash flow failed before stamping (script step 4 or 5):**

The DB is untouched (only files on disk moved). Restore manually:

```bash
mv alembic/archive/YYYYMMDD/*.py alembic/versions/
rm alembic/versions/*_baseline_squash_*.py
rm alembic/baseline_schema_YYYYMMDD.sql
rmdir alembic/archive/YYYYMMDD
# git restore is also fine
git checkout -- alembic/
```

Restart the application — no DB action needed.

**Path 2 — squash flow stamped the DB but validation failed (script step 6 or runbook step 6):**

The DB schema matches the squashed migration but `alembic_version` table now references the new head. Restore from pg_dump:

```bash
# Verify the long-term backup exists
aws s3 ls s3://backups/db/long-term/pre-squash-YYYYMMDD.dump

# Drop and restore (production DB only after confirming with team)
psql -c "DROP DATABASE email_hub WITH (FORCE);"
psql -c "CREATE DATABASE email_hub;"
PGPASSWORD="$PROD_DB_PASS" pg_restore \
  -h "$PROD_DB_HOST" -p "$PROD_DB_PORT" -U "$PROD_DB_USER" \
  -d email_hub \
  --no-owner --no-privileges \
  pre-squash-YYYYMMDD.dump
```

Then revert the squash commit on `main`:

```bash
git revert <squash_commit_sha>
git push origin main
```

Restart the application. Estimated rollback time: 20 min (pg_restore of a 50M-row schema).

## Out of scope

- **CI gating** — `make db-squash` must never appear in a CI workflow. The confirmation prompt is the only safety. The dry-run script (`scripts/squash-migrations-dryrun.sh`) is the only safe CI smoke.
- **Branch rebase automation** — contributors handle their own rebase. No script attempts it.
- **Squash a second time** — this runbook covers the first squash. Once a baseline exists, future squashes need a separate plan.

## Cross-references

- Squash script: `scripts/squash-migrations.sh` (existed pre-tech-debt-19)
- Dry-run script: `scripts/squash-migrations-dryrun.sh` (new, this PR)
- Makefile target: `make db-squash` (interactive, NOT in CI)
- Schema-drift entry that gated this work: `.agents/deferred-items.json` → `tech-debt-alembic-schema-drift` (closed 2026-05-10)
