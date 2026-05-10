# Tech-Debt — Restore `reportDeprecated = "error"`

**Cluster:** E (lowest severity — speculative; mechanical fix gated on upstream).
**Closes:** `phase-deps-pyright-asynccontextmanager-deprecation`.
**Branch:** `tech-debt/pyright-restore-deprecated`.
**Estimated effort:** 30–60 min (mostly waiting on upstream pyright/typeshed
release; verification is fast).

## Problem

`pyproject.toml:324` carries `reportDeprecated = "warning"` with the comment:

> pyright 1.1.409 typeshed flags @asynccontextmanager / @contextmanager as deprecated;
> false positive in Python 3.12. Demote to warning until upstream typeshed fixes.

The 5 cited call sites (per the deferred-items entry):

| File | Line | Decorator | Return annotation |
|---|---|---|---|
| `app/core/database.py` | 41 | `@asynccontextmanager` | `AsyncIterator[AsyncSession]` |
| `app/core/scoped_db.py` | 115 | `@asynccontextmanager` (line 113) | `AsyncGenerator[AsyncSession, None]` |
| `app/core/scoped_db.py` | 145 | `@asynccontextmanager` (line 130) | `AsyncIterator[AsyncSession]` |
| `app/main.py` | 71 | `@asynccontextmanager` | `AsyncIterator[None]` |
| `app/knowledge/graph/tests/test_seed_graph.py` | 36 | `@contextmanager` | `Iterator[None]` |

The risk: a *real* deprecation (e.g. Pydantic v3 removing v1-style validators,
SQLAlchemy 2.x deprecating a Mapped form) lands during a future bump and pyright
logs it as a warning instead of failing `make types`. Less severe but possible:
another upstream false-positive deprecation goes unnoticed because the
project-wide demote masks it.

## Approach: prefer the upstream fix; fall back to local annotation sweep

The closes-when clause has two paths:

1. **Upstream typeshed fix.** Bump pyright and re-run `make types`. If
   `reportDeprecated = "error"` works, restore it.
2. **Local annotation sweep.** If upstream still flags, change all 5 call
   sites to `AsyncGenerator[T, None]` / `Generator[T, None]` (some are already
   in this form — only `database.py:41` and `scoped_db.py:145` and `main.py:71`
   use `AsyncIterator`). Verify pyright stops complaining, then restore
   `reportDeprecated = "error"`.

Path 1 is preferred because it removes the workaround entirely. Path 2 is the
fallback if the typeshed fix is more than a few weeks out.

## Files

| File | Change |
|---|---|
| `pyproject.toml:324` | Drop `reportDeprecated = "warning"` line + the 2-line preceding comment block |
| `app/core/database.py:41` | Possibly switch `AsyncIterator` → `AsyncGenerator[…, None]` |
| `app/core/scoped_db.py:131` | Possibly switch `AsyncIterator` → `AsyncGenerator[…, None]` |
| `app/main.py:72` | Possibly switch `AsyncIterator[None]` → `AsyncGenerator[None, None]` |

## Steps

### 1. Pre-flight — try upstream first

```bash
git checkout -b tech-debt/pyright-restore-deprecated
uv run pyright --version
# Check current pinned version against latest:
uv pip index versions pyright
```

If a newer pyright is available, bump it:

```bash
# Locate pyright pin (typically dev-dependencies in pyproject.toml or
# a pyright-version comment in CI yml).
rg -n "pyright" pyproject.toml uv.lock .github/workflows/*.yml
# Bump and re-lock.
uv lock --upgrade-package pyright
```

Apply the candidate fix (drop the warning demotion):

```bash
# Edit pyproject.toml — delete lines 322-324 (comment + the
# reportDeprecated="warning" line). Keep all surrounding rules unchanged.
make types
```

### 2. Decide based on `make types` output

**Case A — `make types` passes with `reportDeprecated = "error"` restored.**
- Upstream typeshed fix landed.
- Skip to §4.

**Case B — pyright still flags the 5 sites.**
- Re-add the demotion. Change strategy to Path 2 (annotation sweep). Continue
  to §3.

### 3. Annotation sweep (Path 2)

For each `AsyncIterator[T]` annotation on an `@asynccontextmanager`-decorated
function, switch to `AsyncGenerator[T, None]`. Same for `Iterator[T]` →
`Generator[T, None, None]` on `@contextmanager`.

Apply edits:

```python
# app/core/database.py:41
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    ...

# app/core/scoped_db.py:130
@asynccontextmanager
async def get_scoped_db_context(user: User) -> AsyncGenerator[AsyncSession, None]:
    ...

# app/main.py:71
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    ...
```

Update the imports to drop `AsyncIterator` if it's no longer referenced.

`scoped_db.py:115` (`get_scoped_db`, no `@asynccontextmanager`) is already
`AsyncGenerator[AsyncSession, None]` — leave alone; the FastAPI dependency is
`yield`-driven and not in scope for this fix.

`test_seed_graph.py:36` is already `Iterator[None]` per existing source — but
verify against the current grep:

```bash
rg -n "@(async)?contextmanager" app/ --type py -A2 | grep -E "Iterator|Generator"
```

Anything not in the form `(Async)?Generator[T, None]` (or `Generator[T, None,
None]`) on a `@(async)?contextmanager` site needs converting.

Re-run:

```bash
make types
```

If still flagged, the issue is upstream and Path 2 isn't sufficient — leave
the demotion in place and update the comment in `pyproject.toml` to point at the
specific upstream issue:

```toml
# pyright 1.1.<X> still flags @asynccontextmanager despite upstream typeshed
# changes — see https://github.com/microsoft/pyright/issues/<NNNN>.
# Demote to warning until tracked issue resolves.
reportDeprecated = "warning"
```

That keeps the deferred entry alive but pinned to a concrete upstream tracker.

### 4. Restore the rule (Case A or successful Path 2)

`pyproject.toml:322-324` — delete the comment block and the
`reportDeprecated = "warning"` line. Run:

```bash
make types
make check-full
```

Both must be green.

### 5. PR checklist

- [ ] If Case A or Path 2 succeeded:
      - [ ] `.agents/deferred-items.json` — close
            `phase-deps-pyright-asynccontextmanager-deprecation` with
            `closure_note: "Pyright vX.Y.Z + typeshed fix"` or
            `closure_note: "Migrated 3 call sites to AsyncGenerator[…, None]"`.
      - [ ] `.agents/plans/deferred-items-tracker.md` — strike Cluster E.
- [ ] If neither path worked:
      - [ ] Update the deferred-items entry's `notes` field with the upstream
            issue link and the pyright version where it was last verified
            broken.
      - [ ] **Do not close the entry.** Leave Cluster E in the tracker.
- [ ] `make check-full` green either way.

## Risk

- **Bumping pyright surfaces unrelated strict-mode regressions.** If the bump
  catches new genuine strictness violations elsewhere, scope splits: revert the
  pyright bump in this PR and open a separate "fix new pyright findings" PR.
  Don't bundle.
- **`AsyncGenerator[…, None]` works but reads worse.** It does. The annotation
  sweep is the lesser path; prefer the upstream fix even if it means waiting a
  cycle.

## Out of scope

- Other `reportXxx` rule restorations that may be demoted elsewhere in
  `pyproject.toml`. This plan touches only the one rule cited in the deferred
  entry.
