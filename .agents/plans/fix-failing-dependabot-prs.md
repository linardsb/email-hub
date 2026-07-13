# Fix Failing Dependabot PRs — Direct-to-Main Strategy

**Date:** 2026-05-04
**Goal:** Land 17 open dependabot dependency bumps on `main` with zero leftover branches. 12 are already CI-green and just need merging; 5 are red and need supporting code/config fixes.
**Constraint:** User wants "every fix on main, no branches" → push fix commits directly to `main` and close superseded PRs. `main` has no branch protection (`gh api .../branches/main/protection` returns `404 Branch not protected`), so direct push is allowed.

---

## 1. Current state

### 1.1. PRs by status

| Status | Count | PR numbers |
|--------|-------|------------|
| Green (no fix needed) | 12 | #80, #81, #82, #84, #85, #87, #90, #91, #93, #94, #95, #96 |
| Red (needs supporting fix) | 5 | #83, #86, #88, #89, #92 |

### 1.2. Failing PRs — root cause

| PR | Bump | Failing job | Root cause | Severity |
|----|------|-------------|------------|----------|
| #83 | `pyright` 1.1.408 → 1.1.409 | Backend type check (pyright) | Pyright 1.1.409 typeshed bundle treats `@asynccontextmanager` / `@contextmanager` as deprecated. 5 errors at `app/core/database.py:41`, `app/core/scoped_db.py:123,145`, `app/knowledge/graph/tests/test_seed_graph.py:36`, `app/main.py:71`. `[tool.pyright]` in `pyproject.toml` does not pin `reportDeprecated`, and `typeCheckingMode = "strict"` defaults it to `"error"`. | False positive — `@asynccontextmanager` is **not** deprecated in Py 3.12/3.13. |
| #86 | `cachetools` 7.0.6 → 7.1.1 | Backend mypy + Frontend (transient) | (a) cachetools 7.1.1 ships `py.typed` so `# type: ignore[no-any-return]` at `app/core/scoped_db.py:79` is now flagged as `[unused-ignore]`. (b) Frontend "Unable to resolve action `pnpm/action-setup@v6`" was a transient GitHub fetch error — `v6.0.5` exists; other PRs' frontend jobs ran fine in the same window. | Backend: real, one-line fix. Frontend: transient, will pass on rerun. |
| #88 | `@hey-api/openapi-ts` 0.66.7 → 0.97.1 | SDK drift detection | Generator output changed between 0.66 and 0.97. CI runs `make sdk-snapshot && make sdk-local` and diffs `cms/packages/sdk/`; the regenerated files diverge from what's committed. Also touches `client.gen.ts`, `index.ts`, and likely typed wrappers — risks breaking SDK consumers. | Mechanical regen + verify SDK consumers compile. |
| #89 | `prettier-plugin-tailwindcss` 0.6.14 → 0.8.0 | Frontend prettier `format:check` | Major-version sort-order change. 73 files have new ordering. | Mechanical reformat. |
| #92 | `lucide-react` 0.474.0 → 1.14.0 | Frontend `tsc --noEmit` | Lucide v1.0 removed brand icons (`Figma`, etc.) for trademark cleanup. Compiler error: `'lucide-react' has no exported member 'Figma'` at `cms/apps/web/src/components/icons/index.ts:112`. Sole consumer is `cms/apps/web/src/components/figma/figma-connection-card.tsx:3`. | Replace `Figma` icon with a custom SVG component (existing pattern: `cms/apps/web/src/components/icons/generated/<Name>.tsx`). |

### 1.3. Out-of-scope (noted, not addressed by this plan)

- **alembic-check schema drift** in PR #88's run (and likely others) is huge (dozens of `modify_type`/`modify_nullable`/`add_index` operations across `blueprint_checkpoints`, `calibration_records`, `collaborative_documents`, etc.). Step is `continue-on-error: true` at `.github/workflows/ci.yml:200`, so it is **advisory only** and does not fail the PRs. Pre-existing tech debt tracked in `docs/migration-debt.md`. Not introduced by these dependabot bumps.

---

## 2. Strategy

**Direct-to-main, sequenced.**

1. Merge the 12 green PRs first (squash-merge with branch deletion via `gh pr merge --squash --delete-branch`). Doing them first prevents the 5 fix commits from fighting lockfile churn — each green merge updates `pnpm-lock.yaml` or `uv.lock`, and dependabot rebases the rest automatically.
2. For each of the 5 red PRs, push **one focused commit per dep** directly to `main` containing both the version bump and the supporting fix. Bisectability matters because pyright/mypy/SDK-regen interact.
3. Close each red PR with `gh pr close <N> --comment "Superseded by <sha> on main"`. Dependabot will reap the branch.
4. Watch CI on `main` after each commit; do not stack the next commit until the previous one is green.

**Order of fix commits (independent first → most invasive last):**

| Order | Commit | Why this order |
|-------|--------|----------------|
| C1 | pyright config + bump | Independent of all others. Clears 5 phantom errors from backend type-check noise so subsequent pushes get a clean signal. |
| C2 | cachetools bump + remove unused `# type: ignore` | One-line code change. Trivial. Backend-only. |
| C3 | prettier-plugin-tailwindcss bump + reformat 73 files | Mechanical, no semantic risk, but big diff that we want isolated for clean revert if needed. |
| C4 | openapi-ts bump + SDK regen | Highest risk of TS consumer breakage. Need a verify step. Better to land after the easier fixes have proved the workflow. |
| C5 | lucide-react v1 + custom Figma SVG | Most invasive; touches icon barrel + new component file. Save for last so it doesn't block other progress if it needs iteration. |

**Why not one fat commit?** Bisectability. If a regression surfaces in the design-sync flow next week, `git bisect` should land on the lucide commit, not on a 6-package mega-commit.

**Why not feature branches?** User explicitly requested "no branches". Direct push is safe because `main` is unprotected and each commit is mechanically verified locally before push.

---

## 3. Per-commit work breakdown

### C1 — pyright 1.1.408 → 1.1.409 (closes #83)

**Files:**
- `pyproject.toml` — `[tool.pyright]` block: add `reportDeprecated = "warning"`. Bump `pyright` in `[tool.uv.dev-dependencies]` (or wherever pyright is pinned).
- `uv.lock` — regenerate via `uv lock --upgrade-package pyright`.

**Why `"warning"` not `"none"`:** keep visibility of real deprecation issues but don't fail CI on a typeshed false-positive. Alternative `"none"` is acceptable if upstream doesn't fix the typeshed annotation soon.

**Verify locally:**
- `uv run pyright app/` → should report `0 errors, 1463 warnings, 0 informations` (warnings unchanged, errors gone).

**Commit message:**
```
chore(deps-dev): bump pyright 1.1.408 → 1.1.409

Demote reportDeprecated to "warning" in [tool.pyright]; pyright 1.1.409
typeshed treats @asynccontextmanager as deprecated under strict mode,
which is a false positive in Python 3.12.

Closes #83.
```

**PR closure:**
```
gh pr close 83 --comment "Superseded by <sha> on main."
```

---

### C2 — cachetools 7.0.6 → 7.1.1 (closes #86)

**Files:**
- `pyproject.toml` — bump `cachetools` pin.
- `uv.lock` — regenerate via `uv lock --upgrade-package cachetools`.
- `app/core/scoped_db.py:79` — remove the trailing `# type: ignore[no-any-return]  # TTLCache lacks stubs; pyright narrows correctly` comment. The cachetools 7.1 release ships `py.typed`, so the ignore is now flagged unused by mypy.

**Also check:** `app/core/scoped_db.py:26` — `# pyright: ignore[reportMissingTypeStubs]` on the `from cachetools import TTLCache` line may also be unused now. Remove if so. Confirm via `uv run pyright app/core/scoped_db.py` and `uv run mypy app/core/scoped_db.py`.

**Verify locally:**
- `uv run mypy app/` → no `[unused-ignore]` errors.
- `uv run pyright app/` → no new errors.
- `uv run pytest app/core/ -k scoped_db` (if such a test exists; otherwise `app/tests/test_quota.py` exercises this path).

**Commit message:**
```
chore(deps): bump cachetools 7.0.6 → 7.1.1

cachetools 7.1.1 ships py.typed; remove now-unused type: ignore comment
at app/core/scoped_db.py:79.

Closes #86.
```

**Note on transient frontend failure:** PR #86's frontend job failed at `pnpm/action-setup@v6` resolution. This was a transient GitHub registry fetch error — `pnpm/action-setup@v6.0.5` exists and PRs #92/#89 successfully resolved the same action in the same time window. After this commit, the next `main` CI run will pass the frontend job.

---

### C3 — prettier-plugin-tailwindcss 0.6.14 → 0.8.0 (closes #89)

**Files:**
- `cms/apps/web/package.json` — bump `prettier-plugin-tailwindcss` pin in `devDependencies`.
- `cms/pnpm-lock.yaml` — regenerate via `pnpm --filter @email-hub/web install`.
- ~73 files under `cms/apps/web/src/**/*.{ts,tsx}` — reformatted by `pnpm --filter @email-hub/web format`. Full list visible in PR #89's failing log.

**Verify locally:**
- `cd cms && pnpm --filter @email-hub/web format:check` → exit 0.
- `pnpm --filter @email-hub/web type-check` → still passes (formatting shouldn't change semantics, but verify).
- `pnpm --filter @email-hub/web test` → still passes.

**Commit message:**
```
chore(deps-dev): bump prettier-plugin-tailwindcss 0.6.14 → 0.8.0

Major-version sort-order change reformats 73 files. No semantic changes;
diff is whitespace and class-attribute ordering only.

Closes #89.
```

---

### C4 — @hey-api/openapi-ts 0.66.7 → 0.97.1 (closes #88)

**Files (definitely changed):**
- `cms/apps/web/package.json` — bump `@hey-api/openapi-ts` in `devDependencies`.
- `cms/pnpm-lock.yaml` — regenerate.
- `cms/packages/sdk/src/client/client.gen.ts` — regenerated by `make sdk-local`. ~8 line diff per CI log.
- `cms/packages/sdk/src/client/index.ts` — regenerated. ~5 line diff per CI log.
- Other files under `cms/packages/sdk/src/` — likely regenerated; final list unknown until regen runs.

**Files (potentially affected — verify after regen):**
- Any `cms/apps/web/src/**/*.{ts,tsx}` that imports from `@email-hub/sdk` — if the regen renames or restructures exports, consumers may break.

**Steps:**
1. `pnpm --filter @email-hub/sdk add -D @hey-api/openapi-ts@^0.97.1` (or equivalent for whichever package owns the dep).
2. `make sdk-snapshot` — captures the OpenAPI spec from a running backend (CI uses `uv run python -m app.main_export_openapi` or similar; check `Makefile`).
3. `make sdk-local` — runs the generator.
4. `git diff cms/packages/sdk/` — review for unexpected breaking shape changes (renamed exports, dropped clients).
5. `pnpm --filter @email-hub/web type-check` — verify consumers still compile.
6. If consumers break: fix imports/usages in the same commit. If fan-out is large (>10 files), split into a follow-up commit C4b to keep blast radius visible.

**Verify locally:**
- `cd cms && pnpm --filter @email-hub/web type-check` → exit 0.
- `git diff cms/packages/sdk/` should match what CI's "SDK drift detection" step regenerates → next CI run should report "SDK is up to date."

**Commit message:**
```
chore(deps-dev): bump @hey-api/openapi-ts 0.66.7 → 0.97.1

Regenerate cms/packages/sdk/ to match new generator output. <consumer
adjustments if any>.

Closes #88.
```

---

### C5 — lucide-react 0.474.0 → 1.14.0 (closes #92)

**Background:** Lucide 1.0 removed brand icons (Figma, GitHub, Slack, etc.) for trademark reasons. The codebase already has a `cms/apps/web/src/components/icons/generated/` directory with 73 custom SVG icon components (per `cms/apps/web/src/components/icons/index.ts` lines 9-82) — replacements are written in this style.

**Files:**
- `cms/apps/web/package.json` — bump `lucide-react` to `^1.14.0`.
- `cms/pnpm-lock.yaml` — regenerate.
- `cms/apps/web/src/components/icons/generated/Figma.tsx` — **new file**. Copy the structure of any existing generated icon (e.g. `Activity.tsx`) and use the Figma logo SVG path. Reference: official Figma brand asset (the geometric red/orange/green/blue/purple shape) — keep monochrome `currentColor` to match the rest of the icon set.
- `cms/apps/web/src/components/icons/index.ts` — move `Figma` from line 112 (lucide block) into the custom icons block (between lines 36–37, alphabetically). Add `export { Figma } from "./generated/Figma";`. Remove `Figma,` from the lucide-react import on line 112.

**Pre-flight verification (do this BEFORE writing the SVG):**
- `cd cms/apps/web && pnpm add lucide-react@^1.14.0`
- `pnpm type-check` → read the **full** error output, not just the first line.
- Cross-check every name in `cms/apps/web/src/components/icons/index.ts` lines 87–161 against the lucide v1 export list.
- Likely additional casualties: anything brand-shaped. Probably none in this list, but verify before assuming.
- If more icons are missing, extend C5 to cover all of them with custom SVGs, OR fall back to **option B** (see below).

**Option B (fallback):** If lucide v1 broke too many icons (>3 additional casualties or icons that lack obvious SVG equivalents), pin lucide-react to `^0.474.0` and close #92 as **won't-do**. Add an entry to `.agents/deferred-items.json` documenting the trade-off and add `lucide-react` to dependabot's ignore list for major versions in `.github/dependabot.yml`. This is a strategic deferral, not a bug; document the why.

**Verify locally (after fix):**
- `cd cms && pnpm --filter @email-hub/web type-check` → exit 0.
- `pnpm --filter @email-hub/web format:check` → exit 0 (the new file should be auto-formatted).
- `pnpm --filter @email-hub/web build` → succeeds (catches runtime icon-loading issues that `tsc` misses).
- Manual smoke: `pnpm --filter @email-hub/web dev` → load `/figma` page → verify the Figma icon renders correctly in the connection card.

**Commit message:**
```
chore(deps): bump lucide-react 0.474.0 → 1.14.0

Lucide 1.0 removed brand icons. Replace `Figma` lucide import with a
custom SVG icon component matching the existing generated icon style.

Closes #92.
```

---

## 4. Execution checklist (run in order)

### Phase 0 — Repo prep
- [ ] `git checkout main && git pull --ff-only origin main`
- [ ] `git status` clean (the existing `M CLAUDE.md` and skill-version yaml changes are pre-existing and unrelated; either commit them separately first or stash them).
- [ ] Confirm `gh auth status` is logged in as a user with push access to `linardsb/email-hub`.

### Phase 1 — Bulk-merge 12 green PRs
For each of: 80, 81, 82, 84, 85, 87, 90, 91, 93, 94, 95, 96:
- [ ] `gh pr merge <N> --squash --delete-branch --auto` (the `--auto` flag makes them queue if branch is behind; merge happens once required checks finish on the rebased head).

After all 12 are queued/merged:
- [ ] `git pull --ff-only origin main` to fast-forward local main.
- [ ] Wait for the next `main` CI run (auto-triggered by the merge of #80) to confirm green: `gh run watch --repo linardsb/email-hub`.

### Phase 2 — Push fix commits sequentially

For each of C1 → C5 (do NOT batch):

1. [ ] Apply file changes per the breakdown in §3.
2. [ ] Run the local verify commands listed for that commit.
3. [ ] `git diff` — confirm only intended files changed (per `.claude/rules/parallel work awareness`).
4. [ ] `git add <files>` (named, not `-A`); `git commit -m "<message>"`.
5. [ ] `git push origin main`.
6. [ ] `gh run watch --repo linardsb/email-hub` — confirm green before next commit.
7. [ ] `gh pr close <N> --comment "Superseded by $(git rev-parse HEAD) on main."`

### Phase 3 — Final sweep
- [ ] `gh pr list --repo linardsb/email-hub --state open` → should show 0 dependabot PRs.
- [ ] `gh run list --repo linardsb/email-hub --branch main --limit 3` → all green.
- [ ] Quick eyeball of `git log --oneline -20` to confirm 5 fix commits + ~12 squash merges landed in expected order.

---

## 5. Risk register

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `make sdk-snapshot` requires a running backend / live OpenAPI source. May fail offline. | Medium | Read `Makefile` target first; if it requires `docker-compose up db`, do that before C4. |
| Lucide v1 broke more icons than just `Figma`. | Medium | Pre-flight verification step in C5 catches this. Fallback to "pin and decline" path. |
| openapi-ts 0.97 generator changes export shape (e.g. renames `OptionsRequired` → `Options`). | Medium | Step 5 in C4 (`pnpm type-check`) catches this. Fix consumers in same commit; split if fan-out > 10 files. |
| Dependabot opens new PRs while we're working. | Low | Each green merge auto-rebases siblings; new PRs that arrive mid-flight follow the same triage at the end. |
| Pyright `reportDeprecated = "warning"` masks a real deprecation later. | Low | Warnings still printed in CI logs. Revisit when typeshed fixes the `@asynccontextmanager` annotation. |
| Direct push to `main` triggers an unexpected hook. | Low | Branch is unprotected; `make install-hooks` may have client-side pre-commit hooks (formatter/linter) — let them run, fix and re-commit if they reject. Never `--no-verify`. |

---

## 6. What this plan does NOT do

- Does **not** address pre-existing alembic schema drift (advisory step, out of scope).
- Does **not** open follow-up PRs for the lucide v1 fallout if more icons turn out to be removed — that's deferred to C5's "Option B" fallback decision at execution time.
- Does **not** update `.github/dependabot.yml` ignore rules unless C5 falls back to "pin and decline" lucide-react.
- Does **not** modify CI workflows. The `pnpm/action-setup@v6` failure was transient.
- Does **not** rewrite the existing `M CLAUDE.md` / skill-versions.yaml uncommitted changes — those need to be reviewed separately and committed (or reverted) before Phase 0.

---

## 7. Estimated wall-clock

| Phase | Time |
|-------|------|
| Phase 0 prep | 5 min |
| Phase 1 (12 merges, sequential through CI) | 30–60 min (CI-bound; can `--auto` and walk away) |
| Phase 2 C1 (pyright) | 10 min |
| Phase 2 C2 (cachetools) | 10 min |
| Phase 2 C3 (prettier-plugin) | 10 min |
| Phase 2 C4 (openapi-ts) | 30–60 min (regen + consumer-fix risk) |
| Phase 2 C5 (lucide) | 30–60 min (SVG authoring + manual smoke test) |
| Phase 3 sweep | 5 min |
| **Total** | ~2.5–4 hours active, ~5 hours wall-clock with CI |
