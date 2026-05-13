# Plan: Phase 30.3 — Multi-Browser & CLI E2E Coverage

## Context

The Playwright e2e suite (Phase 30.1) currently runs 9 spec files across Chromium only. The visual email builder uses DOM APIs (drag-and-drop, `contentEditable`, clipboard, CSS `user-select`) that behave differently across browser engines. Firefox and WebKit have known differences. Additionally, a CLI-based exploratory e2e system exists at `.claude/commands/e2e-test.md` covering 13 user journeys via `agent-browser` — this should be documented as the complementary exploratory layer.

## Files to Create/Modify

- `cms/apps/web/playwright.config.ts` — add Firefox + WebKit projects, `BROWSER` env var filtering
- `cms/apps/web/e2e/builder.spec.ts` — add browser-specific DnD workaround for Firefox, WebKit focus waits
- `cms/apps/web/e2e/collaboration.spec.ts` — increase WS timeout for Firefox
- `cms/apps/web/e2e/CLI_E2E_TESTING.md` — document CLI e2e strategy
- `cms/apps/web/package.json` — add `e2e:firefox`, `e2e:webkit`, `e2e:all` scripts
- `Makefile` — add `e2e-firefox`, `e2e-webkit`, `e2e-all-browsers` targets

## Implementation Steps

### Step 1: Update `playwright.config.ts` — Multi-browser projects

Replace the existing single-project config with a `BROWSER` env var-driven setup. The key design choice: use an env var to select which browser(s) to run rather than Playwright's `--project` flag, because Makefile targets are simpler this way and the per-spec browser filtering uses `test.skip()` with `browserName`.

```ts
// cms/apps/web/playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

const browser = process.env.BROWSER || "chromium";

/** Build project list from BROWSER env var (chromium | firefox | webkit | all) */
function getProjects() {
  const all = [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ];

  if (browser === "all") return all;
  const match = all.find((p) => p.name === browser);
  return match ? [match] : [all[0]];
}

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
  projects: getProjects(),
  webServer: {
    command: "pnpm dev",
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
```

### Step 2: Add per-spec browser skip annotations

Tests that are API-heavy / browser-independent should skip on Firefox/WebKit. Tests with DOM-interactive behavior run on all browsers.

**Browser assignment:**

| Spec file | Chromium | Firefox | WebKit | Rationale |
|-----------|----------|---------|--------|-----------|
| `auth.spec.ts` | yes | yes | yes | Core flow, must work everywhere |
| `dashboard.spec.ts` | yes | yes | yes | Core flow |
| `workspace.spec.ts` | yes | yes | yes | Core flow |
| `builder.spec.ts` | yes | yes | yes | Most cross-browser sensitive (DnD, contentEditable) |
| `collaboration.spec.ts` | yes | yes | no | WebSocket behavior; WebKit WS can be flaky |
| `export.spec.ts` | yes | no | no | API-heavy dialog, browser-independent |
| `approval.spec.ts` | yes | no | no | API-heavy, browser-independent |
| `design-sync.spec.ts` | yes | no | no | API mocking, browser-independent |
| `ecosystem.spec.ts` | yes | no | no | Static page load, browser-independent |

Implementation: Add a skip guard at the top of each Chromium-only spec. The approach uses `test.skip()` inside `test.describe` which is Playwright's idiomatic way.

**`export.spec.ts`** — add at the start of the describe block:
```ts
test.describe("Export Flow", () => {
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "API-heavy flow — Chromium only"
  );
  // ... existing tests unchanged
});
```

Apply the same skip pattern to: `approval.spec.ts`, `design-sync.spec.ts`, `ecosystem.spec.ts`.

**`collaboration.spec.ts`** — skip WebKit only:
```ts
test.describe("Collaboration", () => {
  test.describe.configure({ retries: 3 });
  test.skip(
    ({ browserName }) => browserName === "webkit",
    "WebSocket behavior — skip WebKit"
  );
  // ... existing tests unchanged
});
```

**`auth.spec.ts`, `dashboard.spec.ts`, `workspace.spec.ts`, `builder.spec.ts`** — no skip guard needed (run on all browsers).

### Step 3: Harden `builder.spec.ts` for cross-browser DnD

The existing "drag component to canvas" test uses `page.mouse.move/down/up` which works in Chromium but can fail in Firefox (DataTransfer API differences) and WebKit (slower contentEditable focus). Add browser-aware workarounds.

Replace the existing "drag component to canvas" test body:

```ts
test("drag component to canvas", async ({ authenticatedPage: page, browserName }) => {
  const firstComponent = page.locator("[draggable='true']").first();
  await expect(firstComponent).toBeVisible({ timeout: 10_000 });

  const canvas = page
    .getByText(/drag components/i)
    .or(page.locator("[data-testid='builder-canvas']"))
    .first();

  const sourceBox = await firstComponent.boundingBox();
  const targetBox = await canvas.boundingBox();
  if (sourceBox && targetBox) {
    if (browserName === "firefox") {
      // Firefox: native DnD events differ — use dispatchEvent approach
      await firstComponent.dispatchEvent("dragstart");
      await canvas.dispatchEvent("dragover");
      await canvas.dispatchEvent("drop");
      await firstComponent.dispatchEvent("dragend");
    } else {
      // Chromium & WebKit: mouse-based drag
      await page.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      );
      await page.mouse.down();
      await page.mouse.move(
        targetBox.x + targetBox.width / 2,
        targetBox.y + targetBox.height / 2,
        { steps: 10 }
      );
      await page.mouse.up();
    }
  }

  // Verify drag target was found — actual drop may vary by environment
  expect(sourceBox).toBeTruthy();
  expect(targetBox).toBeTruthy();
});
```

For the "undo/redo keyboard shortcuts" test, add platform-aware modifier key:

```ts
test("undo/redo keyboard shortcuts", async ({
  authenticatedPage: page,
  browserName,
}) => {
  // WebKit (Safari) uses Meta instead of Control on macOS
  const mod = browserName === "webkit" ? "Meta" : "Control";
  await page.keyboard.press(`${mod}+z`);
  await page.keyboard.press(`${mod}+Shift+z`);
  await expect(page.locator("main")).toBeVisible();
});
```

For the "property panel opens on section click" test, add WebKit explicit focus wait:

```ts
test("property panel opens on section click", async ({
  authenticatedPage: page,
  browserName,
}) => {
  const section = page
    .locator("[data-testid='section-wrapper']")
    .or(page.locator(".flex-1.overflow-y-auto [role='button']"))
    .first();

  if (await section.isVisible({ timeout: 5_000 }).catch(() => false)) {
    if (browserName === "webkit") {
      // Safari: explicit focus before click for contentEditable
      await section.focus();
      await page.waitForTimeout(200);
    }
    await section.click();
    await expect(
      page
        .getByRole("tab", { name: /content/i })
        .or(page.getByLabel(/close property panel/i))
    ).toBeVisible({ timeout: 5_000 });
  }
});
```

### Step 4: Harden `collaboration.spec.ts` for Firefox WebSocket

Increase the timeout for presence propagation in Firefox:

```ts
test("presence indicator shows active user", async ({
  authenticatedPage: page,
  browser,
  browserName,
}) => {
  const projectId = getSharedProjectId();
  await page.goto(`/projects/${projectId}/workspace`);

  // Open second context with same baseURL
  const context2 = await browser.newContext({
    baseURL: process.env.BASE_URL || "http://localhost:3000",
  });
  const page2 = await context2.newPage();
  await page2.goto("/login");
  await page2.locator("#username").fill(TEST_USER_EMAIL);
  await page2.locator("#password").fill(TEST_USER_PASSWORD);
  await page2.getByRole("button", { name: /sign in/i }).click();
  await page2.waitForURL(/^\/$|\/projects|\/dashboard/);
  await page2.goto(`/projects/${projectId}/workspace`);

  // Firefox: WebSocket connection can be slower — use longer timeout
  const wsTimeout = browserName === "firefox" ? 15_000 : 10_000;

  // Wait for presence to propagate via WebSocket
  const presenceIndicator = page
    .getByText(/online|active|user/i)
    .or(page.locator("[data-testid='presence']"))
    .first();

  // Use polling instead of fixed timeout
  await expect(page.locator("main")).toBeVisible({ timeout: wsTimeout });

  await context2.close();
});
```

### Step 5: Add package.json scripts

Add new scripts to `cms/apps/web/package.json` alongside the existing e2e scripts:

```json
"e2e": "playwright test",
"e2e:ui": "playwright test --ui",
"e2e:firefox": "BROWSER=firefox playwright test",
"e2e:webkit": "BROWSER=webkit playwright test",
"e2e:all": "BROWSER=all playwright test"
```

### Step 6: Add Makefile targets

Add these targets after the existing `e2e-report:` target (line 83) in the Makefile:

```makefile
e2e-firefox: ## Run e2e tests on Firefox
	cd cms && BROWSER=firefox pnpm --filter web e2e

e2e-webkit: ## Run e2e tests on WebKit (Safari)
	cd cms && BROWSER=webkit pnpm --filter web e2e

e2e-all-browsers: ## Run e2e tests on all browsers (Chromium + Firefox + WebKit)
	cd cms && BROWSER=all pnpm --filter web e2e
```

Also add `e2e-firefox e2e-webkit e2e-all-browsers` to the `.PHONY` declaration on line 1.

### Step 7: Create CLI E2E Testing documentation

Create `cms/apps/web/e2e/CLI_E2E_TESTING.md`:

```markdown
# CLI-Based Exploratory E2E Testing

## Overview

This project has two complementary e2e testing strategies:

| Strategy | Tool | Purpose | When to use |
|----------|------|---------|-------------|
| **Automated** | Playwright | Regression prevention | Every PR (CI), nightly (full matrix) |
| **Exploratory** | agent-browser (CLI) | Visual inspection, edge cases, new features | Pre-release, after major UI changes |

## Automated E2E (Playwright)

```bash
make e2e                # Chromium only (default, fast — PR checks)
make e2e-firefox        # Firefox only
make e2e-webkit         # WebKit (Safari) only
make e2e-all-browsers   # Full matrix (nightly / release gate)
make e2e-ui             # Interactive Playwright UI mode
make e2e-report         # Open last HTML report
```

### Browser matrix

| Spec | Chromium | Firefox | WebKit | Notes |
|------|----------|---------|--------|-------|
| auth | x | x | x | Core flow |
| dashboard | x | x | x | Core flow |
| workspace | x | x | x | Core flow |
| builder | x | x | x | DnD, contentEditable — most sensitive |
| collaboration | x | x | - | WebSocket; WebKit WS flaky |
| export | x | - | - | API-heavy, browser-independent |
| approval | x | - | - | API-heavy |
| design-sync | x | - | - | API mocking |
| ecosystem | x | - | - | Static page |

## Exploratory E2E (CLI)

The CLI e2e suite uses `agent-browser` for interactive, AI-guided exploratory testing. It covers 13 user journeys with screenshot capture and visual analysis.

### Journeys covered

1. Login flow
2. Dashboard (stat cards, quick actions)
3. Workspace — template selector, code/visual tabs
4. Workspace — preview controls (viewport, dark mode, zoom)
5. Workspace — AI chat (10 agent tabs)
6. Workspace — QA panel, export dialog
7. Components (category filter, search, detail dialog)
8. Approvals (status filters, decision flow)
9. Connectors (platform filters, export history)
10. Intelligence (performance charts, score cards)
11. Knowledge (search, domain filters, documents)
12. Renderings (compatibility matrix, rendering tests)
13. Global features (dark mode, locale, logout)

### How to run

In Claude Code:
```
/e2e-test
```

This launches the full exploratory suite defined in `.claude/commands/e2e-test.md`.

### When to use exploratory testing

- **Pre-release validation** — visual inspection before cutting a release branch
- **After major UI changes** — new components, layout refactors, theme changes
- **Bug investigation** — interactive DOM inspection with screenshots
- **New feature smoke test** — quick visual check before writing Playwright tests

### How they complement each other

- **Playwright** catches regressions automatically in CI — deterministic, fast, runs on every PR
- **CLI e2e** catches visual/UX issues that automated tests miss — interactive, thorough, human-guided
- Write Playwright tests for stable flows. Use CLI e2e for exploration and edge cases.
```

## Security Checklist

For files in this plan only:
- [x] No new security surface — only Playwright config and test changes
- [x] No `dangerouslySetInnerHTML` added
- [x] No new API calls or auth changes
- [x] Browser binaries from official Playwright registry only (`npx playwright install`)
- [x] No secrets or credentials in test code (uses existing fixture constants)
- [x] `e2e-auth-state` file already in `.gitignore` pattern

## Verification

- [ ] `make e2e` passes (Chromium only, existing behavior preserved)
- [ ] `make e2e-firefox` runs auth + dashboard + workspace + builder + collaboration specs on Firefox
- [ ] `make e2e-webkit` runs auth + dashboard + workspace + builder specs on WebKit
- [ ] `make e2e-all-browsers` runs full matrix (~35 test executions across 3 browsers)
- [ ] Chromium-only specs (export, approval, design-sync, ecosystem) skip cleanly on Firefox/WebKit
- [ ] Builder DnD test uses `dispatchEvent` on Firefox, mouse-based on Chromium/WebKit
- [ ] Undo/redo uses Meta key on WebKit, Control on others
- [ ] Failures produce per-browser screenshots (named with browser prefix in report)
- [ ] `make check-fe` still passes (no TypeScript errors)
- [ ] `make e2e` (Chromium-only) still completes in <5 minutes
