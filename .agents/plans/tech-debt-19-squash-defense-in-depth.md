# Squash Defense-in-Depth (F057b — Phase 50.8)

**Status:** Plan Ready. Optional tripwire layer. Reverts as part of §50.7's PR once the redesign lands.

## Execution Order Context

| | |
|---|---|
| **TODO.md ref** | §50.8 |
| **Step in Phase 50** | **Optional** — skip if §50.7 ships within ~3 days |
| **Prerequisites** | none (additive, runnable any time before §50.7 merges) |
| **Parallel with** | §50.6 and §50.7 (no file overlap with §50.6; overlaps with §50.7's `scripts/squash-migrations.sh` rewrites — see "Coordination" below) |
| **Blocks downstream** | nothing |
| **Effort estimate** | ~30 min |

### When to actually do this
Only if §50.7 is going to slip past ~3 days from now. The point is to prevent an accidental `make db-squash` execution during the window when the design flaw is known but not yet fixed. If §50.7 lands fast, the existing TODO.md / runbook / deferred-items signals are sufficient — adding more warnings is overkill.

### When to skip this
- §50.7 is the next thing being worked on and will merge within the week.
- The team has process discipline around `make db-squash` (e.g., it's gated on a runbook checklist someone reads anyway).
- You'd rather not maintain a temporary safety check that §50.7 then has to revert.

### Done signal
- `make db-squash` invoked without the new flag aborts with a clear error message pointing at §50.7.
- CLAUDE.md and alembic/CLAUDE.md `make db-squash` mentions carry an inline `(BLOCKED — see §50.5)` note.

### Cleanup signal (post-§50.7)
- The hard-abort and the `--design-flaw-acknowledged` flag are removed from `scripts/squash-migrations.sh` as part of §50.7's PR.
- The inline `(BLOCKED — see §50.5)` notes are removed from CLAUDE.md and alembic/CLAUDE.md as part of §50.7's PR.
- F057 is unblocked in §50.5.

## Coordination with §50.7

If both §50.7 and §50.8 are in flight at the same time, **§50.8 lands first** (smaller, faster). §50.7's PR then drops the §50.8 additions in the same patch that ships the redesigned scripts. Don't run both simultaneously on the same branch — the script edits will conflict.

If §50.7 lands first, §50.8 is moot and should be skipped entirely.

## Tasks

### Task 1 — `scripts/squash-migrations.sh` hard-abort gate

Add a second safety gate after the existing `--i-know-what-i-am-doing` block. The new gate requires `--design-flaw-acknowledged` AND points at the deferred-items entry.

Insert after the existing safety gate (around line 50, after the `if [[ ! $REPLY =~ ^[Yy]$ ]]` block) and before the pre-flight checks:

```bash
# ── Design-flaw block (tech-debt-19-squash-empty-baseline) ──
# Remove this entire block as part of the §50.7 PR.
DESIGN_FLAW_ACK=false
for arg in "$@"; do
    if [ "$arg" = "--design-flaw-acknowledged" ]; then
        DESIGN_FLAW_ACK=true
    fi
done

if [ "$DESIGN_FLAW_ACK" = false ]; then
    cat >&2 <<'WARN'

╔══════════════════════════════════════════════════════════════╗
║  ⚠  SQUASH DESIGN FLAW — DO NOT RUN                          ║
║                                                              ║
║  This script's autogenerate step runs against the populated  ║
║  DB, producing an empty baseline (def upgrade(): pass).      ║
║  Cutover would succeed deceptively; next fresh-DB deploy     ║
║  would create no schema.                                     ║
║                                                              ║
║  See:  .agents/deferred-items.json                           ║
║        → tech-debt-19-squash-empty-baseline                  ║
║                                                              ║
║  Fix is tracked under §50.7 in TODO.md. Wait for that PR.    ║
║                                                              ║
║  If you genuinely need to override (testing the fix locally  ║
║  in a sandbox, never production), pass:                      ║
║      --design-flaw-acknowledged                              ║
╚══════════════════════════════════════════════════════════════╝

WARN
    exit 1
fi
```

### Task 2 — CLAUDE.md inline note

In `CLAUDE.md`, find the Essential Commands table around line 39:

```diff
- make db-squash       # Squash migrations to single baseline (destructive, confirmation required)
+ make db-squash       # Squash migrations to single baseline (BLOCKED — see §50.5; destructive, confirmation required)
```

### Task 3 — `alembic/CLAUDE.md` inline note

Around line 25 in `alembic/CLAUDE.md`:

```diff
- make db-squash                                              # Interactive (confirmation prompt)
+ make db-squash                                              # BLOCKED — see TODO.md §50.5; interactive when unblocked
```

### Task 4 — Verify

```bash
# Hard-abort fires by default
bash scripts/squash-migrations.sh --i-know-what-i-am-doing 2>&1 | grep -q "SQUASH DESIGN FLAW" && echo "✓ block message shown"
echo $?  # last command should be 0 → block worked; non-zero means the gate didn't fire

# Override path works
bash scripts/squash-migrations.sh --i-know-what-i-am-doing --design-flaw-acknowledged 2>&1 | head -5
# Should proceed into the migration-state check (Step 1 of the script)
```

Do NOT run the override path against a production-like DB. The script is still design-broken — the override exists only for testing §50.7's fix in a sandboxed environment.

## Acceptance

- `make db-squash` invoked normally → aborts with the boxed warning, exit code 1.
- `make db-squash` invoked with `--design-flaw-acknowledged` → proceeds to step 1 of the existing script.
- `CLAUDE.md` and `alembic/CLAUDE.md` carry the `(BLOCKED — see §50.5)` note next to `make db-squash`.
- No other files changed.

## Files Touched

| File | Lines | Type |
|------|-------|------|
| `scripts/squash-migrations.sh` | +~25 (the design-flaw block) | New code |
| `CLAUDE.md` line 39 | edit existing line | Text |
| `alembic/CLAUDE.md` line 25 | edit existing line | Text |

## Out of Scope

- Modifying `scripts/squash-migrations-dryrun.sh` — the dry-run already fails fast on bug #3 (script_location), so it's not a runaway-execution risk. Don't gate it.
- Modifying `Makefile` — the `db-squash` target just shells to the script; the script-level gate is sufficient.
- Anything else in `CLAUDE.md` / `alembic/CLAUDE.md` — surgical, only the `make db-squash` line.
- Persisting the safety gate beyond §50.7. The whole point is it's temporary.
