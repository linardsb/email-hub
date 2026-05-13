# Plan: Phase 30.1 — Playwright E2E User Journey Suite

## Context

The CLI-based e2e guide (`.claude/commands/e2e-test.md`) covers 13 journeys but requires manual `agent-browser` execution. The current `example.spec.ts` only checks if a page loads. We need automated Playwright tests running in CI on every PR.

**agent-browser assessment:** Cannot replace Playwright. It's a stateful CLI daemon for AI agents — no test framework, no assertions, no CI integration, no parallel execution. Playwright remains the correct choice. agent-browser stays as a complementary exploratory layer (Phase 30.2).

## Existing Infrastructure

- **Playwright v1.50** already installed, config at `cms/apps/web/e2e/playwright.config.ts`
- **Make targets** exist: `make e2e`, `make e2e-ui` (missing `make e2e-report`)
- **Auth:** NextAuth.js JWT + credentials provider, `POST /api/v1/auth/login` → `{ access_token, refresh_token }`
- **Demo user:** `admin@email-hub.dev` / `admin` (via bootstrap endpoint)
- **Backend base URL:** `http://localhost:8891`
- **Frontend base URL:** `http://localhost:3000`
- **Mock ESP:** port 3002, `services/mock-esp/`
- **18 protected routes** under `(dashboard)` group + `/login` + `/projects/[id]/workspace`

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `cms/apps/web/e2e/fixtures/auth.ts` | Login fixture via API, provides `authenticatedPage` |
| `cms/apps/web/e2e/fixtures/api.ts` | API helper — create/delete projects, templates, approvals |
| `cms/apps/web/e2e/fixtures/index.ts` | Re-export all fixtures as extended `test` object |
| `cms/apps/web/e2e/global-setup.ts` | Bootstrap admin user + health checks |
| `cms/apps/web/e2e/global-teardown.ts` | Cleanup test data |
| `cms/apps/web/e2e/auth.spec.ts` | Login/logout tests (3) |
| `cms/apps/web/e2e/dashboard.spec.ts` | Dashboard + project CRUD (3) |
| `cms/apps/web/e2e/workspace.spec.ts` | Template editing + preview (5) |
| `cms/apps/web/e2e/builder.spec.ts` | Visual builder interactions (5) |
| `cms/apps/web/e2e/export.spec.ts` | ESP export flow + gates (5) |
| `cms/apps/web/e2e/approval.spec.ts` | Approval workflow end-to-end (4) |
| `cms/apps/web/e2e/design-sync.spec.ts` | Design tool connection + import (3) |
| `cms/apps/web/e2e/collaboration.spec.ts` | Multi-user presence + CRDT sync (2) |
| `cms/apps/web/e2e/ecosystem.spec.ts` | Ecosystem dashboard tabs (2) |

### Modified Files
| File | Change |
|------|--------|
| `cms/apps/web/e2e/playwright.config.ts` | Add globalSetup/Teardown, screenshot-on-failure, timeout |
| `Makefile` | Add `e2e-report` target |

### Delete
| File | Reason |
|------|--------|
| `cms/apps/web/e2e/example.spec.ts` | Replaced by real tests |

## Implementation Steps

### Step 1: Update Playwright Config

Modify `cms/apps/web/e2e/playwright.config.ts`:

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }]],
  timeout: 30_000,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "pnpm dev",
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
```

### Step 2: Global Setup/Teardown

**`global-setup.ts`** — Runs once before all tests:
1. Wait for backend health: `GET http://localhost:8891/api/v1/health` (retry 10x, 2s interval)
2. Bootstrap admin user: `POST http://localhost:8891/api/v1/auth/bootstrap` (ignore 409 if exists)
3. Login as admin: `POST http://localhost:8891/api/v1/auth/login` with `admin@email-hub.dev` / `admin`
4. Store `access_token` in env file (`.e2e-auth-state`) for fixtures to read
5. Create a shared test project via `POST http://localhost:8891/api/v1/projects` with unique name `e2e-test-{timestamp}`
6. Store `projectId` in same env file

**`global-teardown.ts`** — Runs once after all tests:
1. Read env file, delete test project via `DELETE /api/v1/projects/{id}` (if endpoint exists, otherwise no-op)
2. Remove `.e2e-auth-state` file

### Step 3: Auth Fixture

**`fixtures/auth.ts`** — Extends Playwright's `test` with `authenticatedPage`:

```typescript
import { test as base, type Page } from "@playwright/test";

const API_BASE = process.env.BACKEND_URL || "http://localhost:8891";

type AuthFixtures = {
  authenticatedPage: Page;
  apiToken: string;
};

export const test = base.extend<AuthFixtures>({
  apiToken: async ({}, use) => {
    // Login via API, get JWT token
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "admin@email-hub.dev",
        password: "admin",
      }),
    });
    const data = await res.json();
    await use(data.access_token);
  },

  authenticatedPage: async ({ page, apiToken }, use) => {
    // Set NextAuth session by calling the signin API through the frontend
    // or inject token via cookie/localStorage depending on NextAuth config
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("admin@email-hub.dev");
    await page.getByLabel(/password/i).fill("admin");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\//);
    await use(page);
  },
});
```

Note: The `authenticatedPage` fixture logs in through the UI once per test. If this becomes a bottleneck, optimize by injecting NextAuth session cookies directly (read from `/api/auth/session` after programmatic login).

### Step 4: API Helper Fixture

**`fixtures/api.ts`** — Helper for creating/cleaning test data:

```typescript
type ApiFixtures = {
  api: ApiHelper;
};
```

The `ApiHelper` class provides:
- `createProject(name: string)` → `POST /api/v1/projects` → returns `{ id, name }`
- `createTemplate(projectId: number, name: string)` → `POST /api/v1/email/builds` or appropriate endpoint
- `createApproval(projectId: number, buildId: number)` → `POST /api/v1/approvals`
- `decideApproval(approvalId: number, decision: string)` → `POST /api/v1/approvals/{id}/decide`
- `deleteProject(id: number)` → cleanup
- All methods use the `apiToken` from auth fixture, include `Authorization: Bearer` header and `Content-Type: application/json`

**`fixtures/index.ts`** — Merge auth + api fixtures:
```typescript
import { mergeTests } from "@playwright/test";
import { test as authTest } from "./auth";
import { test as apiTest } from "./api";
export const test = mergeTests(authTest, apiTest);
export { expect } from "@playwright/test";
```

### Step 5: Auth Tests — `auth.spec.ts` (3 tests)

| Test | Steps |
|------|-------|
| Login valid creds | `goto /login` → fill email/password → click Sign In → expect URL `/` → heading visible |
| Login invalid creds | `goto /login` → fill wrong password → click Sign In → expect error toast/message visible |
| Logout | Start as `authenticatedPage` → click sidebar Logout → expect URL `/login` |

Uses base `test` from `@playwright/test` for unauthenticated tests, `test` from fixtures for logout.

### Step 6: Dashboard Tests — `dashboard.spec.ts` (3 tests)

All use `authenticatedPage` fixture.

| Test | Steps |
|------|-------|
| Dashboard loads | `goto /` → expect stat cards or heading visible |
| Create project | Click "New Project" button → fill dialog form (name, description) → submit → expect project card appears in list |
| Search/filter | Type project name in search input → expect matching project visible, non-matching hidden |

### Step 7: Workspace Tests — `workspace.spec.ts` (5 tests)

All use `authenticatedPage` + `api` fixture to create a project first.

| Test | Steps |
|------|-------|
| Open workspace | Navigate to `/projects/{id}/workspace` → expect template list/selector visible |
| Code editor loads | Select template → expect code editor panel visible with HTML content |
| Visual builder | Click "Visual" tab → expect builder canvas visible with rendered preview |
| Preview tab | Click "Preview" tab → expect sandboxed iframe visible |
| QA panel | Click "Run QA" → expect QA results panel with check items (pass/fail badges) |

### Step 8: Builder Tests — `builder.spec.ts` (5 tests)

All use `authenticatedPage` + navigate to workspace visual builder.

| Test | Steps |
|------|-------|
| Palette loads | Expect component palette sidebar with component cards |
| Drag to canvas | Drag component card to canvas drop zone → expect canvas child count increases |
| Property panel | Click component on canvas → expect right sidebar property panel with tabs (Content/Style/Responsive/Advanced) |
| Edit property | Change a text value in property panel → expect preview reflects change |
| Undo/redo | Make change → Ctrl+Z → expect reverted → Ctrl+Shift+Z → expect reapplied |

Note: Drag-and-drop uses Playwright's `page.dragAndDrop()` or `locator.dragTo()`. If DnD is complex (dnd-kit), may need manual mouse event simulation.

### Step 9: Export Tests — `export.spec.ts` (5 tests)

All use `authenticatedPage` + `api` fixture, navigate to workspace.

| Test | Steps |
|------|-------|
| Export dialog opens | Click "Export" → expect dialog with ESP tabs (Raw HTML, Braze, SFMC, Adobe, Taxi) |
| Braze export flow | Click Braze tab → fill content block name → click Export |
| Gate panel appears | After export click → expect QA gate + rendering gate results visible |
| Export succeeds | With valid HTML → gate passes → expect success toast/message |
| Export blocked | Inject broken HTML (missing closing tags) → export → expect block message with remediation |

Relies on mock-esp running on port 3002. `global-setup.ts` verifies mock-esp health.

### Step 10: Approval Tests — `approval.spec.ts` (4 tests)

Uses `authenticatedPage` + `api` fixture.

| Test | Steps |
|------|-------|
| Submit for approval | Via `api.createApproval()` → navigate to `/approvals` → expect card with "pending" badge |
| View approval detail | Click approval card → `/approvals/{id}` → expect build preview + QA results visible |
| Approve | Click "Approve" button → confirm dialog → expect status changes to "approved" |
| Export after approval | Navigate to workspace → export → expect approval gate passes (no block) |

### Step 11: Design Sync Tests — `design-sync.spec.ts` (3 tests)

Uses `authenticatedPage`.

| Test | Steps |
|------|-------|
| Connect dialog | Navigate to `/design-sync` → click "Connect" → expect connection dialog opens |
| Browse files | After mock connection → expect file tree visible → select frame |
| Create template | Click "Convert" or "Import" → expect template created message |

Note: These tests may need mock responses if Penpot/Figma API is unavailable. Use `page.route()` to intercept API calls and return mock data.

### Step 12: Collaboration Tests — `collaboration.spec.ts` (2 tests)

Uses two browser contexts (Playwright's `browser.newContext()`).

| Test | Steps |
|------|-------|
| Presence indicators | Open same workspace in 2 contexts → expect presence indicator shows 2 users |
| CRDT sync | Context A types in editor → expect Context B's editor content updates |

Note: Both contexts login as same or different users. Need WebSocket server running. Use `page.waitForTimeout()` or `expect.poll()` for async sync verification.

### Step 13: Ecosystem Tests — `ecosystem.spec.ts` (2 tests)

Uses `authenticatedPage`.

| Test | Steps |
|------|-------|
| Dashboard tabs | Navigate to `/ecosystem` → expect tabs visible (Overview, Plugins, Workflows, Reports, Penpot) |
| Plugin manager | Click Plugins tab → expect plugin list loads with cards |

### Step 14: Makefile Update

Add to `Makefile`:
```makefile
e2e-report: ## Open last Playwright HTML report
	cd cms && pnpm --filter web exec playwright show-report
```

### Step 15: Delete Example Spec

Remove `cms/apps/web/e2e/example.spec.ts` — its coverage is superseded by `auth.spec.ts` and `dashboard.spec.ts`.

### Step 16: Verify

- [ ] `make e2e` runs all 32 tests headless (Chromium)
- [ ] All pass on clean environment (backend + frontend + mock-esp running)
- [ ] Failures produce screenshots + traces in `cms/apps/web/e2e/test-results/`
- [ ] `make e2e-report` opens HTML report
- [ ] `make e2e-ui` opens interactive runner
- [ ] Total suite completes in <5 minutes
- [ ] No hardcoded secrets in test code (credentials from config/env)
- [ ] Test data isolated per run (unique project names with timestamps)

## Security Checklist

This phase creates no new backend endpoints. Security considerations:

- **Test credentials:** Use bootstrap endpoint (dev-only, zero-users guard) — no production creds
- **Mock ESP:** Captures but doesn't forward — no real ESP credentials
- **Test isolation:** Unique project names per run, cleanup in teardown
- **No secrets in code:** Auth password comes from config default (`admin`), not hardcoded secrets
- **No new API surface:** Tests consume existing endpoints only

## Implementation Notes

- **SWR caching:** Frontend uses stale-while-revalidate. Tests must use explicit element waits (`expect(locator).toBeVisible()`) rather than `waitForLoadState('networkidle')` which is unreliable with SWR.
- **DnD testing:** `dnd-kit` drag operations may need `page.mouse.move()` + `page.mouse.down()` + `page.mouse.up()` sequence instead of `dragTo()`. Test and adjust.
- **Design sync mocking:** Intercept Penpot/Figma API calls with `page.route('**/api/v1/design-sync/**', ...)` returning mock data, since external services won't be running in CI.
- **Collaboration WebSocket:** Requires backend WebSocket server running. If flaky in CI, mark collaboration tests with `test.describe.configure({ retries: 3 })`.
- **Login page selectors:** The login form uses `id="username"` and `id="password"` — use `page.locator('#username')` and `page.locator('#password')` or `getByLabel()`.
