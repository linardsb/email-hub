# Tech Debt 09c — Kill `@ts-nocheck` in Frontend Tests (F043)

**Source:** Carved out of `tech-debt-09-frontend-cleanup.md` Part C.
**Sibling plans:** `tech-debt-09a-icons-split.md` (Part A) — independent, can run in parallel.
**Prerequisite:** `tech-debt-09-frontend-cleanup.md` Parts B/D/E/F/G already landed on `refactor/tech-debt-09-frontend`. Branch off `main` after that PR merges, OR off the same branch if working in parallel.
**Scope:** Remove every `// @ts-nocheck` directive from `cms/apps/web/src/**` test files and replace the underlying mock-typing with `vi.mocked()` patterns.
**Goal:** Zero `@ts-nocheck` directives in `cms/apps/web/src/` (excluding `**/*.gen.*`). `pnpm --filter web type-check` green. All 774 existing tests still pass.
**Estimated effort:** Full session (12 files, 5,095 LOC of test code, real type bugs likely surfaced).

## Execution structure

Session 16 — Frontend test types + middleware default-deny
- Findings: F051, F068
- Effort: M
- Plan: extend tech-debt-09c-ts-strict-tests.md (F051 + F068 sections appended below; F043 stays as the existing plan body and is verify-only at Session 16 time)
- Branch: refactor/tech-debt-09c-fe-test-types
- Scope:
  - F051: cms/apps/web/middleware.ts:7-21,53-72 — default-deny for routes not in ROLE_PERMISSIONS; log the catch
  - F068: split cms/apps/web/src/hooks/__tests__/use-data-hooks{,-2,-3}.test.ts (615+715+990 LOC numbered split) → co-locate per-hook (use-projects.test.ts etc.) with shared __tests__/setup.ts

F043 (the existing plan body) runs as its own session on `refactor/tech-debt-09c-ts-strict-tests` (26 commits already staged); Session 16 verifies its closure via `grep -rl "@ts-nocheck" cms/apps/web/src` returning zero before merging F051/F068.

## Risk warning (from parent plan)

> *"Part C type fixes will surface real bugs. The whole reason `@ts-nocheck` was added was to defer them. Budget time to fix the underlying type mismatches."*

Per-file commits so any surfaced fix is reviewable in isolation. Do **not** squash until the PR is ready.

## Pre-flight

```bash
git checkout -b refactor/tech-debt-09c-ts-strict-tests
cd cms && pnpm install
pnpm --filter web type-check  # baseline: should be 0 errors
pnpm --filter web test        # baseline: 774 passing
```

## Inventory

12 files (5,095 LOC total) carry `// @ts-nocheck` on line 1:

| File | LOC | Notes |
|---|---|---|
| `src/components/__tests__/feature-components.test.tsx` | 455 | feature components rendering |
| `src/components/__tests__/ui-components.test.tsx` | 356 | shared UI components |
| `src/components/__tests__/workspace-components.test.tsx` | 630 | workspace toolbar/panels |
| `src/components/__tests__/editor-panel-sync.test.tsx` | 165 | editor sync flow |
| `src/components/approvals/__tests__/approval-components.test.tsx` | 216 | approval UI |
| `src/hooks/__tests__/use-data-hooks.test.ts` | 615 | SWR hooks set 1 |
| `src/hooks/__tests__/use-data-hooks-2.test.ts` | 715 | SWR hooks set 2 |
| `src/hooks/__tests__/use-data-hooks-3.test.ts` | 990 | SWR hooks set 3 (largest) |
| `src/hooks/__tests__/use-complex-hooks.test.ts` | 651 | builder + collab |
| `src/hooks/__tests__/use-progress.test.ts` | 79 | smallest — tackle first as warm-up |
| `src/hooks/__tests__/use-export-pre-check.test.ts` | 49 | smallest #2 |
| `src/hooks/__tests__/use-smart-polling-migration.test.ts` | 174 | migration smoke |

Verify with: `grep -rln "@ts-nocheck" cms/apps/web/src`

## Per-file fix pattern

The escape hatch was added wholesale because mocking `useSWR` and module imports without typing is verbose. Replace with `vi.mocked()`.

### SWR hook tests

```typescript
import { vi, type Mocked } from "vitest";
import * as swrModule from "swr";

vi.mock("swr");
const useSWR = vi.mocked(swrModule.default);

// In each test:
useSWR.mockReturnValue({
  data: { id: 1 },
  error: null,
  isLoading: false,
  mutate: vi.fn(),
} as ReturnType<typeof swrModule.default>);
```

For `useSWRMutation`, do the same against `swr/mutation`.

### Module-wide mocks

```typescript
vi.mock("@/lib/sdk", () => ({
  default: { getProjects: vi.fn() } satisfies Partial<typeof import("@/lib/sdk").default>,
}));
```

The `satisfies Partial<typeof ...>` pattern is the key — it gives full IDE autocomplete inside the factory while not requiring the mock to implement every member.

### authFetch mocks

```typescript
import * as authFetchModule from "@/lib/auth-fetch";

vi.mock("@/lib/auth-fetch");
const authFetch = vi.mocked(authFetchModule.authFetch);

authFetch.mockResolvedValue(
  new Response(JSON.stringify({ id: 1 }), { status: 200 }),
);
```

### Async handlers passed to components

If a test asserts that a handler was called with a specific shape, type the mock:

```typescript
const onSelect = vi.fn<(t: TemplateResponse) => void>();
```

instead of `const onSelect = vi.fn();`.

## Workflow per file

1. Pick a file (start with the two smallest: `use-progress.test.ts` (79 LOC), `use-export-pre-check.test.ts` (49 LOC)).
2. Remove the `// @ts-nocheck` line.
3. Run `pnpm --filter web type-check` — read every error.
4. For each error, ask: **is this a test issue or a production-code issue?**
   - **Test-only (most common):** missing fields in a mock, wrong vi.fn signature, missing `as ReturnType<typeof ...>` cast. Fix in the test.
   - **Production-code issue (the surfaced bugs):** the production type is genuinely wrong, or it changed and the test was hiding the drift. Fix in production code in a *separate commit* on this branch with a `fix(web): ...` prefix so it stands out from the test work. The plan's risk note says these will appear — when they do, log them in the PR description.
5. Run the affected tests: `pnpm --filter web test src/path/to/file.test.ts` — must pass.
6. Run `pnpm exec eslint src/path/to/file.test.ts` — must be clean.
7. Commit per file: `test(cms): re-type X without @ts-nocheck (F043)`.

## Suggested order (smallest first)

```
1.  hooks/__tests__/use-export-pre-check.test.ts          (49)
2.  hooks/__tests__/use-progress.test.ts                  (79)
3.  components/__tests__/editor-panel-sync.test.tsx       (165)
4.  hooks/__tests__/use-smart-polling-migration.test.ts   (174)
5.  components/approvals/__tests__/approval-components.test.tsx (216)
6.  components/__tests__/ui-components.test.tsx           (356)
7.  components/__tests__/feature-components.test.tsx      (455)
8.  hooks/__tests__/use-data-hooks.test.ts                (615)
9.  components/__tests__/workspace-components.test.tsx    (630)
10. hooks/__tests__/use-complex-hooks.test.ts             (651)
11. hooks/__tests__/use-data-hooks-2.test.ts              (715)
12. hooks/__tests__/use-data-hooks-3.test.ts              (990)
```

After each file, the global error count must not regress relative to the previous step.

## Verification

```bash
cd cms
grep -rl "@ts-nocheck" apps/web/src        # must produce zero output
pnpm --filter web type-check                # zero errors
pnpm --filter web test                      # all 774+ tests green
pnpm --filter web lint                      # clean
```

CI gate: add an `eslint` rule (or grep step) to fail PRs that re-introduce `@ts-nocheck` in `apps/web/src/**`. Optional but recommended.

## Done when

- [ ] Zero `@ts-nocheck` directives in `cms/apps/web/src/` (excluding any `**/*.gen.*`).
- [ ] `pnpm --filter web type-check` exits 0.
- [ ] `pnpm --filter web test` reports the same passing count as the baseline (or higher if surfaced-bug fixes added new tests).
- [ ] Surfaced production-code bugs are documented in the PR description with their `fix(web): ...` commit hashes.
- [ ] PR title: `test(cms): remove @ts-nocheck from frontend tests (F043)`.
- [ ] Mark **F043 as RESOLVED** in `TECH_DEBT_AUDIT.md`.

## Rollback

Per-file commits make this trivial — revert individual commits if a fix turns out to mask a real production bug that needs deeper investigation.

## Notes for the agent

- Do **not** add a global `as any` to side-step a typing problem — that's the same anti-pattern this work is removing.
- Do **not** use `// eslint-disable-next-line @typescript-eslint/no-explicit-any` either.
- If a mock requires a complex type that's only used in one test, define it locally as `interface MockX extends Partial<RealX> { ... }` rather than reaching for `any`.
- React 19 components don't take `forwardRef` — if a test asserts a ref shape, check the production component first.
- Do **not** run `pnpm --filter web lint:fix` over the whole project — it has been observed to mangle JSX `eslint-disable-next-line` comments into empty `{}` expressions. Run targeted: `pnpm exec eslint <files> --fix` from `cms/apps/web/`.
