# Disaster Recovery

Procedures for backing up, restoring, and recovering the Email Hub.

---

## 1. State Classification

Understand what lives where before recovering anything.

### PostgreSQL (persistent, authoritative)

All application data. Loss requires restore from backup.

| Data | Table(s) | Impact of Loss |
|------|----------|---------------|
| Users & auth | `users` | All accounts gone, re-registration required |
| Projects | `projects` | All project config, design systems lost |
| Components | `components`, `component_versions` | Component library lost |
| Templates | `email_templates` | Template registry lost |
| Eval data | `eval_*` | Judge verdicts, calibration baselines lost |
| Knowledge | `knowledge_*` | Knowledge base documents lost |
| Migrations | `alembic_version` | Schema version tracking lost |

### Redis (ephemeral + semi-persistent)

Most Redis data rebuilds automatically. Feature flags are the exception.

| Key Pattern | Data Type | Rebuilds Automatically? | Impact of Loss |
|------------|-----------|------------------------|----------------|
| `slowapi:*` | Rate limit counters | Yes (reset to zero) | Brief rate limit reset, no user impact |
| `flags:{name}` | Feature flags | No — must re-set manually | Flags revert to `.env` / config.py defaults |
| `ws:*` | WebSocket pub/sub | Yes (reconnects) | Brief WebSocket disconnection |
| `collab:*` | CRDT collaboration state | Yes (re-syncs) | Brief collaboration interruption |
| `design_sync:section:*` | Converter cache | Yes (rebuilds on demand) | Slower first conversion, then normal |
| `cognee:prefetch:*` | Knowledge prefetch | Yes (re-fetches) | Slower first knowledge query |

---

## 2. PostgreSQL Backup

### Automated Backups (Cron)

The `scripts/backup-db.sh` script creates compressed SQL dumps with rotation.

```bash
# Manual run
./scripts/backup-db.sh
```

**What it does:**
1. Finds the running DB container
2. Runs `pg_dump -U emailhub email_hub --no-owner --no-acl`
3. Compresses with gzip
4. Saves to `/data/backups/email-hub/email_hub_YYYYMMDD_HHMMSS.sql.gz`
5. Rotates: keeps last 10 backups (~60 hours of history)

**Output:**
```
Backup created: /data/backups/email-hub/email_hub_20260331_060000.sql.gz (2.1M)
Backups on disk: 10
```

### Cron Schedule (Production)

Add to the server's crontab:

```bash
# Every 6 hours
0 */6 * * * /data/scripts/backup-db.sh >> /var/log/backup-db.log 2>&1
```

### Manual Backup (Before Risky Operations)

Always backup before migrations, schema changes, or data imports:

```bash
./scripts/backup-db.sh
```

### Verify Backup Integrity

```bash
# List available backups
ls -lh /data/backups/email-hub/email_hub_*.sql.gz

# Test decompression (without restoring)
gunzip -t /data/backups/email-hub/email_hub_YYYYMMDD_HHMMSS.sql.gz
# No output = file is valid
```

---

## 3. PostgreSQL Restore

### Using the Restore Script

```bash
# Restore latest backup
./scripts/restore-db.sh

# Restore specific backup
./scripts/restore-db.sh /data/backups/email-hub/email_hub_20260331_060000.sql.gz
```

**What it does:**
1. Prompts for confirmation (interactive — requires `y` to proceed)
2. Truncates all tables except `alembic_version` (preserves migration history)
3. Restores data from the compressed dump
4. Verifies by printing row counts for `components`, `projects`, `users`

**Expected output:**
```
Restoring from: /data/backups/email-hub/email_hub_20260331_060000.sql.gz
Target: email-hub-db-1 / email_hub
This will OVERWRITE the current database. Continue? [y/N] y
Tables truncated.
Restore complete. Verifying...
    tbl     | count
------------+-------
 components |    89
 projects   |     3
 users      |     5
```

### Manual Restore (If Script Fails)

```bash
# Find the DB container
CONTAINER=$(docker ps --format '{{.Names}}' | grep db-1)

# Decompress and restore
gunzip -c /data/backups/email-hub/email_hub_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i "$CONTAINER" psql -U emailhub email_hub --quiet

# Verify
docker exec "$CONTAINER" psql -U emailhub email_hub \
  -c "SELECT 'users' as tbl, COUNT(*) FROM users;"
```

### Post-Restore Steps

1. Verify migration state matches: `uv run alembic current`
2. If migration mismatch, run: `uv run alembic stamp <expected_revision>`
3. Restart the application: `docker compose restart app`
4. Check health: `curl -s http://localhost:8891/health/ready`

---

## 4. WAL Archiving (Recommended for Production)

For point-in-time recovery (PITR), enable WAL archiving in PostgreSQL.

### Enable in `postgresql.conf`

```ini
wal_level = replica
archive_mode = on
archive_command = 'cp %p /data/wal-archive/%f'
archive_timeout = 300
```

### Create Archive Directory

```bash
mkdir -p /data/wal-archive
chown postgres:postgres /data/wal-archive
```

### Point-in-Time Recovery

```bash
# Stop PostgreSQL
docker compose stop db

# Create recovery.conf (or recovery.signal for PG12+)
cat > /var/lib/postgresql/data/recovery.signal <<EOF
EOF

cat >> /var/lib/postgresql/data/postgresql.conf <<EOF
restore_command = 'cp /data/wal-archive/%f %p'
recovery_target_time = '2026-03-31 14:00:00 UTC'
EOF

# Start PostgreSQL — it will replay WAL to the target time
docker compose start db

# Verify
docker compose exec db psql -U emailhub email_hub \
  -c "SELECT pg_last_xact_replay_timestamp();"
```

---

## 5. Redis Recovery

### Restart Redis

Most Redis data is ephemeral. A restart is usually sufficient:

```bash
docker compose restart redis

# Verify
curl -s http://localhost:8891/health/redis
# Expected: {"status":"healthy","service":"redis"}
```

### Re-Set Feature Flags

Feature flags stored in Redis do not auto-rebuild. After a Redis data loss, flags revert to their defaults in `.env` / `config.py`. To restore non-default flag states:

```bash
# Connect to Redis
docker compose exec redis redis-cli

# Re-enable flags that were on
SET flags:KNOWLEDGE__CRAG_ENABLED 1
SET flags:AI__ADAPTIVE_ROUTING_ENABLED 1
# ... repeat for each flag that was enabled
```

Check `feature-flags.yaml` for the complete flag inventory and their expected states.

### Redis Persistence Configuration

**RDB snapshots** (default — periodic full dumps):

```bash
# Check current config
docker compose exec redis redis-cli CONFIG GET save
# Default: "3600 1 300 100 60 10000"
# Meaning: save after 3600s if 1 key changed, 300s if 100 keys, 60s if 10000 keys
```

**AOF (recommended for production)** — logs every write operation:

```bash
docker compose exec redis redis-cli CONFIG SET appendonly yes
docker compose exec redis redis-cli CONFIG SET appendfsync everysec
```

To persist these settings, add to the Redis service in `docker-compose.yml`:

```yaml
redis:
  command: redis-server --appendonly yes --appendfsync everysec
```

---

## 6. Recovery Time Objectives

| Component | RTO | Recovery Method | Data Loss (RPO) |
|-----------|-----|-----------------|-----------------|
| PostgreSQL | <1 hour | Restore from `backup-db.sh` dump | Up to 6 hours (cron interval) |
| PostgreSQL (PITR) | <1 hour | WAL replay to target timestamp | Seconds (last archived WAL) |
| Redis | <5 minutes | Restart container, re-set flags | Rate limits reset, cache cold |
| Application | <10 minutes | `docker compose restart app` | None (stateless) |
| Full stack | <1 hour | `docker compose down && up -d` + DB restore | Depends on backup freshness |

### Reducing RPO

- Increase backup frequency: change cron from `*/6` to `*/2` (every 2 hours)
- Enable WAL archiving for continuous protection (seconds RPO)
- Enable Redis AOF for write-level persistence

---

## 7. Complete Disaster Recovery Procedure

If the entire stack is down and data needs restoration:

```bash
# 1. Start infrastructure
docker compose up -d db redis
docker compose logs -f db redis
# Wait for healthy status

# 2. Restore database from backup
./scripts/restore-db.sh
# Select backup file, confirm restoration

# 3. Verify migration state
uv run alembic current
# If mismatched: uv run alembic stamp <expected_revision>

# 4. Run any pending migrations
uv run alembic upgrade head

# 5. Start application services
docker compose up -d

# 6. Verify all health checks
curl -s http://localhost:8891/health/ready
# Expected: {"status":"ready","database":"connected","redis":"connected"}

# 7. Re-set feature flags if needed (see section 5)

# 8. Run smoke test
curl -s http://localhost:8891/health
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"
```
