# Migration Squash Cadence

## When to Squash
- After every ~5 phase completions (e.g., after Phase 45, 50, 55...)
- When migration count exceeds ~50 files
- Never during active feature branches — coordinate with team first

## How to Squash
```bash
make db-squash                                              # Interactive (confirmation prompt)
./scripts/squash-migrations.sh --i-know-what-i-am-doing     # CI/scripted (skip prompt)
```

## What It Does
1. Verifies DB is up-to-date (`alembic check`)
2. Creates pre-squash backup via `scripts/backup_db.sh`
3. Dumps current schema to `alembic/baseline_schema_YYYYMMDD.sql`
4. Archives all migrations to `alembic/archive/YYYYMMDD/`
5. Generates single baseline migration via `alembic revision --autogenerate`
6. Stamps DB with new head (skips running — schema already matches)

## Post-Squash Checklist
- [ ] All active branches must rebase onto the squash commit
- [ ] Test fresh DB: `uv run alembic upgrade head` on empty database
- [ ] Verify: `uv run alembic check` passes
- [ ] Commit archived migrations (preserves git-blame history)

## Archive Structure
```
alembic/
├── archive/
│   └── 20260331/          # Date-stamped archive
│       ├── 2bac390231df_add_email_hub_models.py
│       └── ... (all previous migrations)
├── versions/
│   └── abc123_baseline_squash_20260331.py  # Single baseline
├── baseline_schema_20260331.sql            # Schema dump (audit reference)
├── env.py
└── CLAUDE.md
```

## Safety
- Schema dump excludes `alembic_version` table, ownership, and privileges
- Archived migrations retained in `alembic/archive/` for audit trail and git-blame
- Pre-squash backup created automatically
- Confirmation prompt required (or `--i-know-what-i-am-doing` flag)
