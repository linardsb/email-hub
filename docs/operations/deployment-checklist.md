# Deployment Checklist

Step-by-step procedure for deploying the Email Hub. Run through each section in order.

---

## 1. Pre-Deploy Checks

Run all quality gates before deploying. Every check must pass.

```bash
# Full quality gate (lint + types + tests + security + golden conformance + flag audit)
make check-full
```

If any check fails, fix the issue before proceeding. Key sub-checks:

| Check | Command | What It Catches |
|-------|---------|-----------------|
| Lint + format | `make lint` | Code style, 26 ruff rule sets |
| Type safety | `make types` | mypy + pyright strict errors |
| Unit tests | `make test` | Functional regressions |
| Frontend | `make check-fe` | ESLint + Prettier + tsc + vitest |
| Security | `make security-check` | Bandit rules via ruff `--select=S` |
| Migration safety | `make migration-lint` | Squawk: unsafe DDL, missing down(), long locks |
| Feature flags | `make flag-audit` | Warns >90d stale, errors >180d stale |
| Golden conformance | `make golden-conformance` | Design system template drift |

### Verify Migration Count

```bash
# Check pending migrations
uv run alembic history --verbose | head -20
uv run alembic current
```

Expected: `current` shows the latest revision matching `HEAD` in `alembic/versions/`.

### Review Feature Flags

```bash
# Check for stale flags
make flag-audit
```

If any flag is >180 days old, it must be removed or marked permanent before deploy.

---

## 2. Database Migration

### Development / Staging

```bash
# Run all pending migrations
make db-migrate
# Equivalent: uv run alembic upgrade head

# Verify migration applied
uv run alembic current
```

Expected output: `<revision_hash> (head)` — confirms database is at latest schema.

### Production

Always use the safe wrapper, which blocks accidental downgrades:

```bash
# Safe upgrade (passes through to alembic)
./scripts/safe_alembic.sh upgrade head

# Verify
./scripts/safe_alembic.sh current
```

### Docker (Automatic)

In docker-compose, the `migrate` service runs automatically before `app` starts:

```yaml
migrate:
  command: ["alembic", "upgrade", "head"]
  depends_on:
    db: { condition: service_healthy }
```

The `app` service waits for `migrate` to complete (`service_completed_successfully`).

---

## 3. Service Startup Order

Services must start in dependency order. Docker Compose handles this via health checks.

```
1. db        (PostgreSQL — healthy when pg_isready succeeds)
2. redis     (Redis — healthy when redis-cli ping succeeds)
3. migrate   (one-shot — runs alembic upgrade head, then exits)
4. app       (FastAPI — healthy when GET /health returns 200)
5. cms       (Next.js — healthy when GET / returns 200)
6. nginx     (reverse proxy — healthy when GET /health returns 200)
```

Sidecars start independently:
- `maizzle-builder` — email template compiler (port 3001)
- `mock-esp` — dev/test only (port 3002)

### Start All Services

```bash
# Development
make dev          # Backend (:8891) + frontend (:3000), no Docker

# Docker (all services)
docker compose up -d

# Monitor startup
docker compose logs -f

# Check all services are healthy
docker compose ps
```

Expected: all services show `healthy` or `running` status. The `migrate` service shows `exited (0)`.

### Start Infrastructure Only

```bash
# PostgreSQL + Redis only (for local development)
make db
```

---

## 4. Post-Deploy Verification

### Health Checks

Run each health endpoint and verify the expected response:

```bash
# Basic liveness
curl -s http://localhost:8891/health
# Expected: {"status":"healthy","service":"api"}

# Database connectivity
curl -s http://localhost:8891/health/db
# Expected: {"status":"healthy","service":"database"}

# Redis connectivity
curl -s http://localhost:8891/health/redis
# Expected: {"status":"healthy","service":"redis"}

# Full readiness (all dependencies)
curl -s http://localhost:8891/health/ready
# Expected: {"status":"ready","database":"connected","redis":"connected"}
```

If any returns 503, check the specific service logs:

```bash
docker compose logs db --tail 20
docker compose logs redis --tail 20
docker compose logs app --tail 20
```

### Smoke Test

```bash
# Via nginx (production path)
curl -s http://localhost/health

# Frontend accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Expected: 200

# Maizzle sidecar
curl -s http://localhost:3001/health
```

### Resource Check

```bash
# Container resource usage
docker stats --no-stream
```

| Service | CPU Limit | Memory Limit |
|---------|-----------|-------------|
| db | 0.5 | 256M |
| redis | 0.25 | 128M |
| app | 1.0 | 1024M |
| cms | 0.5 | 512M |
| maizzle-builder | 0.5 | 256M |
| nginx | 0.25 | 128M |

---

## 5. Rollback Procedure

### Migration Rollback

The safe wrapper blocks accidental downgrades. To intentionally rollback:

```bash
# Rollback one migration (creates automatic backup first)
./scripts/safe_alembic.sh downgrade -1 --i-know-what-i-am-doing

# Verify rollback
./scripts/safe_alembic.sh current
```

The wrapper automatically runs `scripts/backup_db.sh` before any downgrade.

### Application Rollback

```bash
# Stop current containers
docker compose down

# Redeploy previous image tag
# Edit docker-compose.yml or .env to pin the previous image version
docker compose up -d

# Verify health
curl -s http://localhost:8891/health/ready
```

### Full Rollback (Migration + Application)

1. Stop the application: `docker compose down`
2. Rollback migration: `./scripts/safe_alembic.sh downgrade -1 --i-know-what-i-am-doing`
3. Redeploy previous version: `docker compose up -d`
4. Verify: `curl -s http://localhost:8891/health/ready`

---

## 6. Environment Promotion

### Dev to Staging

- [ ] `make check-full` passes on the branch
- [ ] Feature flags reviewed — no unintended flags enabled
- [ ] Migration tested against staging database copy
- [ ] CORS origins updated: `ALLOWED_ORIGINS=["https://staging.example.com"]`

### Staging to Production

- [ ] All staging smoke tests pass
- [ ] Secrets rotated (not reusing staging credentials):
  - `AUTH__JWT_SECRET_KEY` — minimum 32 characters, cryptographically random
  - `POSTGRES_PASSWORD` — not the default `postgres`
  - `REDIS_PASSWORD` — not the default `devpassword`
  - `AI__API_KEY` — production provider key
- [ ] `ENVIRONMENT=production` set
- [ ] `ALLOWED_ORIGINS` restricted to production domain(s)
- [ ] SSL certificates configured in nginx
- [ ] Database backup verified: `scripts/backup-db.sh` runs successfully
- [ ] Monitoring/alerting configured for health endpoints
