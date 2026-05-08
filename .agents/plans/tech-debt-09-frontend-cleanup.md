# Tech Debt 09 — Frontend Cleanup

**Source:** `TECH_DEBT_AUDIT.md`
**Scope:** Six frontend findings: icon dump, workspace god component, `@ts-nocheck` cluster, builder hook split, collab WS auth, SDK drift CI gate.
**Goal:** No `@ts-nocheck` outside generated code. Workspace page composed of focused hooks. SDK drift caught in CI. Collab WS authenticated.
**Estimated effort:** Full session.
**Prerequisite:** Plan 01 landed (kills `cms/apps/web/src/types/{outlook,chaos,css-compiler}.ts` duplicates).

## Execution structure

Session 9 — Workspace decomposition
- Findings: F042
- Effort: M (single session — F042 is the only finding still owned by this plan)
- Plan: tech-debt-09-frontend-cleanup.md §B
- Branch: refactor/tech-debt-09-frontend (10 commits ahead of main, no PR — F042 hook extraction staged in `962cf10b`, mixed with off-scope F044/F045/F048/F049 commits that belong to other sessions; rebase or cherry-pick the F042 commit onto a fresh branch before opening the PR)
- Scope:
  - F042: extract `useWorkspaceTemplate`, `useWorkspaceDialogs`, `useWorkspaceFollowMode`, `useAgentMode` hooks from `cms/apps/web/src/app/projects/[id]/workspace/page.tsx`; slim the page to a thin composition root (target <150 LOC, currently 771); preserve existing per-hook tests and add hook-isolation tests that fail if a hook leaks state into the page

Status of carved/closed findings (do **not** re-execute under this plan):
- F041 → closed via `tech-debt-09a-icons-split.md` (PR #48 merged)
- F043 → moved to `tech-debt-09c-ts-strict-tests.md` (Session 16)
- F044 → marked landed in `tech-debt-00-status-and-roadmap.md` Phase 1 (verify before re-attempting; commit `57b973ea` on branch)
- F045 → moved to Session 3 (`tech-debt-01-quick-wins.md` frontend subset)
- F048 → marked landed in roadmap Phase 1 (verify; commit `f06bc431` on branch)
- F049 → moved to Session 19 backend sweep (`tech-debt-19-backend-sweep.md`)

## Findings addressed

F041 (`custom-icons.tsx` 9882 LOC) — Critical
F042 (`workspace/page.tsx` 848 LOC god component) — High
F043 (12 `@ts-nocheck` test files) — High
F044 (`use-builder.ts` 630 LOC) — High
F048 (collab WS connects without auth) — High
F049 (SDK regen has no CI drift gate) — Medium
F045 (token cache never invalidated on 401) — Medium

## Pre-flight

```bash
git checkout -b refactor/tech-debt-09-frontend
cd cms && pnpm install
make check-fe
```

## Part A — `custom-icons.tsx` split (F041)

### A1. Audit usage

```bash
cd cms/apps/web/src
grep -roE "from '@/components/icons[^']*'" --include="*.tsx" --include="*.ts" \
  | sed -E "s/.*from '(@\/components\/icons[^']*)'/\1/" | sort -u
```
Expected: ~130 distinct icon imports out of 332.

### A2. Generator script

`scripts/generate-icons.mjs` (referenced in `custom-icons.tsx` header) — confirm it exists and rewrite to:
- Emit one file per icon: `cms/apps/web/src/components/icons/generated/{IconName}.tsx`.
- Drop `forwardRef` (React 19 doesn't need it for new code; address F039 audit).
- Generate the barrel `cms/apps/web/src/components/icons/index.ts` mapping name → dynamic import.

### A3. Migrate imports

Run a codemod (jscodeshift or simple regex):
```bash
# old
import { Brain, Bot } from "@/components/icons/custom-icons"
# new
import { Brain } from "@/components/icons/generated/Brain"
import { Bot } from "@/components/icons/generated/Bot"
```

OR keep the barrel and rely on tree-shaking — Next 16 + Turbopack handles this. Verify build size before/after.

### A4. Delete the monolith

After all imports migrated, delete `custom-icons.tsx`. ~9.8k LOC out of TypeScript checking budget per build.

## Part B — `workspace/page.tsx` decomposition (F042)

### B1. Extract hooks

Current `workspace/page.tsx:75-580` has 23 `useState` and 5 `useEffect` calls. Group:

| New hook | Owns |
|---|---|
| `useAgentMode()` | `searchParams.agent` parsing (`:75-89`) |
| `useWorkspaceTemplate()` | template list, active template, version selection (`:101-128`) |
| `useWorkspaceDialogs()` | 6 dialog booleans (`:146-160`) |
| `useWorkspaceFollowMode()` | follow-mode scroll logic (`:560-580`) |
| `useEditorState()` | editor content + dirty flag (`:129-131`) |

Each hook lives in `cms/apps/web/src/hooks/workspace/`. Each ≤ 100 LOC.

### B2. Slim the page component

After extraction, `workspace/page.tsx` becomes a layout shell + composed hooks. Target ≤ 200 LOC.

### B3. Replace deep relative import

`workspace/page.tsx:43` — `../../../../components/icons` → `@/components/icons`. Apply to the 4 deep-relative-import files (audit F022 frontend).

### B4. Tests

`cms/apps/web/src/hooks/workspace/__tests__/` — one file per hook, fully typed.

## Part C — Kill `@ts-nocheck` (F043)

### C1. Inventory

12 files all in `cms/apps/web/src/{hooks,components}/__tests__/`. List from audit F043.

### C2. Per-file fix pattern

The escape hatch was added wholesale because mocking `useSWR` and module imports without typing is verbose. Replace with:

```typescript
import { vi, type Mocked } from "vitest"
import * as swrModule from "swr"

vi.mock("swr")
const useSWR = vi.mocked(swrModule.default)

// In each test:
useSWR.mockReturnValue({ data: { id: 1 }, error: null, isLoading: false, mutate: vi.fn() })
```

For module-wide mocks:
```typescript
vi.mock("@/lib/sdk", () => ({
  default: { getProjects: vi.fn() } satisfies Partial<typeof import("@/lib/sdk").default>
}))
```

### C3. Remove `// @ts-nocheck` line

After typing, delete the directive. `pnpm check-types` must pass.

## Part D — `use-builder.ts` split (F044)

### D1. Extract HTML assembler

`cms/apps/web/src/hooks/use-builder.ts:270-549` — pure functions:
- `processSection`
- `buildResponsiveCss`
- `buildDarkModeCss`
- `wrapMsoGhostTable`
- `assembleDocument`

Move to **new file:** `cms/apps/web/src/lib/builder/html-assembler.ts`. These functions are pure (no React state); they belong in `lib/`, not `hooks/`.

### D2. Hook becomes state-only

`use-builder.ts` keeps the reducer (`:26-130`), `INITIAL_STATE`, `MAX_HISTORY`, and `useBuilderPreview` (which calls the assembler).

### D3. Tests

**New file:** `cms/apps/web/src/lib/builder/__tests__/html-assembler.test.ts` — snapshot tests for each pure function. Was previously untested.

## Part E — Collab WS authentication (F048)

### E1. Pass JWT to the WS connection

`cms/apps/web/src/hooks/use-collaboration.ts:41` — TODO present. Get the session token via `getToken()` from `auth-fetch.ts` and append as a query param OR use a subprotocol header (browsers can't set `Authorization` on WebSocket connect; query param is standard).

### E2. Backend verifies on accept

`app/streaming/websocket/routes.py` (the CRDT collab WS, NOT the orphan one deleted in Plan 01) — already has auth check pattern. Verify it actually validates the token and rejects on missing/invalid.

### E3. Tests

E2E test: open the collab WS without a token → connection rejected. With token → accepted.

## Part F — SDK drift CI gate (F049)

### F1. Generate canonical OpenAPI from booted backend

`Makefile`:
```make
sdk-check:
	@uv run uvicorn app.main:app --port 18891 &
	@sleep 5
	@curl -s http://localhost:18891/openapi.json > /tmp/openapi.live.json
	@kill %1 2>/dev/null || true
	@diff <(jq -S . cms/packages/sdk/openapi.json) <(jq -S . /tmp/openapi.live.json) \
	  || (echo "SDK drift detected — run 'make sdk-regen'" && exit 1)
```

### F2. Wire into CI

`.github/workflows/ci.yml` — add `make sdk-check` to the backend job (after migrations). Fails the build on drift.

### F3. Document regen

`docs/sdk.md` (new): "When you change a route or schema, run `make sdk-regen` (or `pnpm generate-sdk:fetch`) and commit the regenerated `openapi.json` + `types.gen.ts` + `sdk.gen.ts`."

## Part G — Token cache invalidation (F045)

### G1. Wire `clearTokenCache` into the 401 interceptor

`cms/apps/web/src/lib/sdk.ts:25` — when the SDK gets a 401, call `clearTokenCache()` from `auth-fetch.ts:97` before retrying. Also route the 429 retry through `authFetch` (currently uses raw `fetch(request)`).

## Verification

```bash
cd cms
pnpm check-types  # zero errors, zero @ts-nocheck (in src; tests OK temporarily)
pnpm lint
pnpm test
pnpm e2e:smoke

# In repo root:
make sdk-check  # green
make check-fe
```

## Rollback

Each part is independent. Most surgical: revert per file. Part A (icon split) may need a coordinated revert with the codemod's import changes.

## Risk notes

- **Part A bundle size**: Verify production `next build` output before/after. If the new structure tree-shakes less efficiently, revert and just split the file (keep barrel pattern).
- **Part C type fixes will surface real bugs.** The whole reason `@ts-nocheck` was added was to defer them. Budget time to fix the underlying type mismatches.
- **Part E breaks tests** that connect to `/ws/collab` without a token. Update fixtures.
- **Part F may flake** if the booted backend takes longer than 5s. Use `wait-on` or a polling loop on `/health`.

## Done when

- [ ] Zero `@ts-nocheck` directives in `cms/apps/web/src/` (excluding `**/*.gen.*`).
- [ ] `custom-icons.tsx` deleted; per-icon files exist; production build size unchanged or smaller.
- [ ] `workspace/page.tsx` ≤ 200 LOC.
- [ ] `use-builder.ts` ≤ 200 LOC; assembler in `lib/builder/`.
- [ ] Collab WS rejects unauth'd connections.
- [ ] `make sdk-check` runs in CI.
- [ ] `clearTokenCache` is called on 401.
- [ ] `make check-fe` green; `pnpm e2e:smoke` green.
- [ ] PR(s): `refactor(cms): icons split + workspace decomposition + ts-strict tests + builder split (F041 F042 F043 F044)` and `sec(cms): collab WS auth + token cache + SDK drift gate (F048 F049 F045)`.
- [ ] Mark F041, F042, F043, F044, F045, F048, F049 as **RESOLVED**.
