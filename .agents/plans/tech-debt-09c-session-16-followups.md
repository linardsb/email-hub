# Tech Debt 09c — Session 16 Follow-ups (F051 + F068)

**Source:** Carved out of `tech-debt-09c-ts-strict-tests.md` (the F043 plan body) after F043 was closed by `53f1a0ad` on main (2026-05-04). F043 verification is no longer the gate — `rg -l "@ts-nocheck" cms/apps/web/src` is already 0 on main.
**Prerequisite:** None — branch off current `main`.
**Branch:** `refactor/tech-debt-09c-fe-test-types` (per original Session 16 spec).
**Audit refs:** `TECH_DEBT_AUDIT.md` rows F051 and F068.

## F051 — Middleware default-deny

**File:** `cms/apps/web/middleware.ts`

**Current behaviour (lines 38–76):** `getRouteKey(pathname)` returns the first key in `ROLE_PERMISSIONS` that matches `pathname === route || startsWith(route + "/")`. When no key matches, `routeKey` is `null` and the RBAC block is skipped — authenticated users reach **any** route not in the allowlist. The outer `try/catch` (lines 53–73) swallows auth errors silently.

**Goal:** Default-deny + log.

**Changes:**

1. **Default-deny on unknown routes.** After the `getRouteKey(pathname)` call, if `routeKey === null`, redirect to `/unauthorized` (admin escape hatch can be added by listing the route explicitly).
2. **Defensive guard for unknown `allowedRoles`.** If `routeKey` matches but `ROLE_PERMISSIONS[routeKey]` is `undefined` (Map drift), treat as default-deny — same `/unauthorized` redirect.
3. **Log the swallow.** Replace the bare `catch {}` at lines 71–73 with `catch (err)` that emits a structured log line (`console.warn` with `{ pathname, err: err instanceof Error ? err.message : String(err) }`). Do not change the fall-through behaviour — preserving the "let the login page handle its own redirect" intent — but make the silent failure observable.

**Tests:** Add `middleware.test.ts` covering:
- known route + allowed role → next()
- known route + denied role → /unauthorized
- unknown route + any role → /unauthorized (the new default-deny)
- public route → next() (unchanged)
- auth() throws → next() + warn logged

**Done when:**
- `cms/apps/web/middleware.ts` no longer falls through for routes not in `ROLE_PERMISSIONS`.
- The bare `catch {}` is gone.
- F051 row in `TECH_DEBT_AUDIT.md` flipped to **RESOLVED**.

## F068 — Split `use-data-hooks{,-2,-3}.test.ts`

**Files:**
- `cms/apps/web/src/hooks/__tests__/use-data-hooks.test.ts` (615 LOC)
- `cms/apps/web/src/hooks/__tests__/use-data-hooks-2.test.ts` (715 LOC)
- `cms/apps/web/src/hooks/__tests__/use-data-hooks-3.test.ts` (990 LOC)

**Current state:** Numbered split with no semantic basis. 30+ LOC SWR mock boilerplate duplicated 3× (one block per file). All three files now type-clean after F043.

**Goal:** Co-locate per-hook with a shared setup module.

**Changes:**

1. **Shared setup module.** Create `cms/apps/web/src/hooks/__tests__/setup.ts` exporting:
   - `mockSWR()` — returns the typed `vi.mocked(swrModule.default)` already configured.
   - `mockSWRMutation()` — same for `swr/mutation`.
   - `mockAuthFetch()` — typed `vi.mocked(authFetchModule.authFetch)` helper.
   - `okResponse<T>(body: T, status = 200): Response` — typed JSON Response builder.
2. **Per-hook split.** One `*.test.ts` per `useXxx` hook tested. Naming mirrors source (`use-projects.test.ts`, `use-templates.test.ts`, etc.). Move each `describe()` block + its specs from the numbered file into the matching per-hook file. Import shared helpers from `./setup`.
3. **Delete the three numbered files** after the migration. No stub re-exports.

**Tests:** No new test logic; the migrated `it()` blocks must all still pass. `pnpm --filter web test` count must stay ≥ post-F043 baseline.

**Done when:**
- `use-data-hooks.test.ts`, `use-data-hooks-2.test.ts`, `use-data-hooks-3.test.ts` deleted.
- New per-hook files green; `pnpm --filter web test` passing.
- Shared `__tests__/setup.ts` is the only place SWR mocks are typed.
- F068 row in `TECH_DEBT_AUDIT.md` flipped to **RESOLVED**.

## Verification gate (both findings)

```bash
cd cms
pnpm --filter web type-check    # 0 errors
pnpm --filter web test          # ≥ post-F043 baseline (774 + any F043-surfaced additions)
pnpm --filter web lint          # clean
rg -l "@ts-nocheck" apps/web/src  # 0
```

## Commit conventions

- F051 commits: `fix(web): default-deny unknown routes in middleware (F051)`, `test(cms): cover middleware default-deny (F051)`.
- F068 commits: `test(cms): extract shared SWR setup (F068)`, then one `test(cms): split use-data-hooks/X (F068)` per migrated hook, then `test(cms): drop numbered use-data-hooks files (F068)`.
