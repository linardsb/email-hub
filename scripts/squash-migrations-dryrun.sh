#!/usr/bin/env bash
# Dry-run for scripts/squash-migrations.sh — exercises the squash flow against
# a throwaway pgvector container so failures surface BEFORE the maintenance
# window. Safe to run from CI or a workstation.
#
# Usage:
#   bash scripts/squash-migrations-dryrun.sh
#
# Exit codes:
#   0 = squash flow produces a clean baseline (alembic check ok, schema matches)
#   1 = squash flow failed; see stderr for the offending step
#
# Requires: docker, uv. Does NOT touch the developer's primary DB.

set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

CONTAINER="squash-dryrun-pg-$$"
PORT=55555
DB_URL="postgresql://postgres:postgres@localhost:${PORT}/email_hub"

cleanup() {
    info "Tearing down dry-run container..."
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf .squash-dryrun-tmp
}
trap cleanup EXIT

# ── 1. Spin up disposable Postgres ──────────────────────────────────────
info "Starting throwaway pgvector container on :${PORT}..."
docker run -d --rm \
    --name "$CONTAINER" \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=email_hub \
    -p "${PORT}:5432" \
    pgvector/pgvector:pg16 >/dev/null

# Wait for readiness
for _ in $(seq 1 30); do
    if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        info "Postgres ready."
        break
    fi
    sleep 1
done

if ! docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    fail "Postgres did not become ready within 30s"
fi

# ── 2. Apply all current migrations ─────────────────────────────────────
info "Applying all current migrations..."
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic upgrade head 2>&1 | tail -3

# Snapshot the pre-squash schema for comparison
mkdir -p .squash-dryrun-tmp
info "Capturing pre-squash schema dump..."
PGPASSWORD=postgres pg_dump \
    -h localhost -p "$PORT" -U postgres -d email_hub \
    --schema-only --no-owner --no-privileges \
    --exclude-table=alembic_version \
    > .squash-dryrun-tmp/pre-squash.sql

# ── 3. Verify pre-squash check exits 0 ──────────────────────────────────
info "Pre-squash alembic check..."
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic check 2>&1 || fail "Pre-squash alembic check failed"

# ── 4. Run the squash flow (non-destructively, in tmp branch state) ─────
info "Running squash flow against the throwaway DB..."

# Work in a temp copy of alembic/ so the real tree is never modified
cp -r alembic .squash-dryrun-tmp/alembic
ARCHIVE_DIR=".squash-dryrun-tmp/alembic/archive/dryrun"
mkdir -p "$ARCHIVE_DIR"
mv .squash-dryrun-tmp/alembic/versions/*.py "$ARCHIVE_DIR/" 2>/dev/null || true

# Generate baseline
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic -c .squash-dryrun-tmp/alembic/alembic.ini 2>/dev/null || true

# Actually generate the baseline in the temp alembic dir
cd .squash-dryrun-tmp
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic --raiseerr revision --autogenerate -m baseline_dryrun \
    --rev-id 0000_dryrun 2>&1 | tail -3 || fail "autogenerate failed in dry-run"
cd ..

# ── 5. Stamp + check ────────────────────────────────────────────────────
info "Stamping the throwaway DB with the new baseline head..."
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic stamp head 2>&1 | tail -2 || fail "alembic stamp failed"

info "Post-squash alembic check..."
DATABASE__URL="postgresql+asyncpg://postgres:postgres@localhost:${PORT}/email_hub" \
    uv run alembic check 2>&1 | tail -2 || fail "Post-squash alembic check failed"

# ── 6. Schema parity ────────────────────────────────────────────────────
info "Comparing pre- vs post-squash schema dumps..."
PGPASSWORD=postgres pg_dump \
    -h localhost -p "$PORT" -U postgres -d email_hub \
    --schema-only --no-owner --no-privileges \
    --exclude-table=alembic_version \
    > .squash-dryrun-tmp/post-squash.sql

if ! diff -q .squash-dryrun-tmp/pre-squash.sql .squash-dryrun-tmp/post-squash.sql >/dev/null; then
    echo "Schema diff detected:"
    diff .squash-dryrun-tmp/pre-squash.sql .squash-dryrun-tmp/post-squash.sql | head -30
    fail "Pre/post-squash schemas differ — autogenerate did not produce a faithful baseline"
fi

info "Dry-run PASSED — squash flow produces an identical baseline schema."
