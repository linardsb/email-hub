# Plan: Phase 27.6 — Frontend Rendering Dashboard & Tests

## Context
All rendering intelligence (27.1–27.5) needs a user-facing surface. The existing `/renderings` page shows test history + failure patterns. This plan adds a **third tab** ("Dashboard") with unified rendering intelligence: preview grid, confidence summary, gate status, and calibration health. Also adds frontend tests for new + existing rendering components.

**Existing assets discovered:**
- `components/rendering/` — 3 files: `gate-panel.tsx`, `gate-client-row.tsx`, `gate-summary-badge.tsx` (27.3 frontend done)
- `hooks/use-rendering-gate.ts` — `useGateEvaluate`, `useGateConfig`, `useUpdateGateConfig`
- `hooks/use-renderings.ts` — `useRenderingTests`, `useRequestRendering`, `useRenderingComparison`
- `types/rendering-gate.ts` — all gate types
- `types/rendering.ts` — screenshot types, visual diff types, `ClientProfile` union (outdated — only 5 clients)
- Backend schemas: `ConfidenceBreakdownSchema`, `ClientConfidenceResponse`, `ScreenshotClientResult` (with confidence fields)
- Renderings page (`renderings/page.tsx`) — 2 tabs: "Rendering Tests" + "Failure Patterns"
- Middleware RBAC: `/renderings` → all roles. No separate `/rendering` route needed.
- 8 emulators in `_EMULATORS` dict, 14 profiles in `profiles.py`

## Files to Create/Modify

### New Files
| # | File | Purpose |
|---|------|---------|
| 1 | `types/rendering-dashboard.ts` | Dashboard-specific types: `CalibrationSummary`, `CalibrationHistory`, `ConfidenceBreakdown`, expanded `ClientProfile` |
| 2 | `hooks/use-rendering-dashboard.ts` | SWR hooks: `useScreenshotsWithConfidence`, `useCalibrationSummary`, `useCalibrationHistory`, `useTriggerCalibration` |
| 3 | `components/rendering/confidence-bar.tsx` | Reusable confidence bar with threshold marker + color zones |
| 4 | `components/rendering/client-preview-card.tsx` | Client card: screenshot thumbnail, confidence badge, expand to full view |
| 5 | `components/rendering/confidence-summary-bar.tsx` | Horizontal segmented bar — per-client, colored by tier, tooltip on hover |
| 6 | `components/rendering/calibration-health-panel.tsx` | Admin-only collapsible: accuracy trends, last calibrated, regression alerts |
| 7 | `components/rendering/rendering-dashboard.tsx` | Main dashboard tab content: preview grid + summary bar + gate panel + calibration |
| 8 | `components/rendering/__tests__/rendering-dashboard.test.tsx` | Tests for dashboard component |
| 9 | `components/rendering/__tests__/gate-panel.test.tsx` | Tests for existing gate panel |
| 10 | `components/rendering/__tests__/confidence-bar.test.tsx` | Tests for confidence bar |

### Modified Files
| # | File | Change |
|---|------|--------|
| 11 | `types/rendering.ts` | Expand `ClientProfile` to 14 profiles, update `CLIENT_DISPLAY_NAMES` |
| 12 | `app/(dashboard)/renderings/page.tsx` | Add "Dashboard" as third tab, import `RenderingDashboard` |
| 13 | `components/rendering/gate-client-row.tsx` | Extract confidence bar into shared `ConfidenceBar` (dedup) |

## Implementation Steps

### Step 1: Expand Types (`types/rendering.ts`)

Update `ClientProfile` union and `CLIENT_DISPLAY_NAMES` to match backend's 14 profiles:

```typescript
export type ClientProfile =
  | "gmail_web" | "gmail_web_dark"
  | "outlook_web" | "outlook_web_dark"
  | "apple_mail" | "apple_mail_dark"
  | "mobile_ios" | "mobile_ios_dark"
  | "yahoo_web" | "yahoo_mobile"
  | "samsung_mail" | "samsung_mail_dark"
  | "outlook_desktop" | "thunderbird";
```

Add `CLIENT_MARKET_SHARE: Record<ClientProfile, number>` for summary bar segment widths. Source from backend emulator data (approximate: Gmail 30%, Apple 28%, Outlook 10%, Yahoo 6%, Samsung 5%, etc.).

### Step 2: Create Dashboard Types (`types/rendering-dashboard.ts`)

```typescript
export interface ConfidenceBreakdown {
  emulator_coverage: number;    // 0-1
  css_compatibility: number;    // 0-1
  calibration_accuracy: number; // 0-1
  layout_complexity: number;    // 0-1
  known_blind_spots: string[];
}

export interface ClientConfidence {
  client_id: string;
  accuracy: number;
  sample_count: number;
  last_calibrated: string;
  known_blind_spots: string[];
  emulator_rule_count: number;
  profiles: string[];
}

export interface CalibrationSummaryItem {
  client_id: string;
  current_accuracy: number;     // 0-100
  sample_count: number;
  last_calibrated: string;
  accuracy_trend: number[];     // last 10 values
  regression_alert: boolean;    // accuracy dropped >10%
}

export interface CalibrationSummaryResponse {
  items: CalibrationSummaryItem[];
}

export interface CalibrationHistoryEntry {
  id: number;
  measured_accuracy: number;
  smoothed_accuracy: number;
  diff_percentage: number;
  created_at: string;
}

export interface CalibrationHistoryResponse {
  client_id: string;
  entries: CalibrationHistoryEntry[];
}
```

Matches backend schemas: `ConfidenceBreakdownSchema` (schemas.py:111-118), `ClientConfidenceResponse` (schemas.py:121-130), calibration models.

### Step 3: Create Dashboard Hooks (`hooks/use-rendering-dashboard.ts`)

Pattern: follow `use-rendering-gate.ts` (useSWR + useSWRMutation with `fetcher`/`longMutationFetcher`).

| Hook | Method | Endpoint | Returns |
|------|--------|----------|---------|
| `useScreenshotsWithConfidence(html, clients)` | `useSWRMutation` POST | `/api/v1/rendering/screenshots` | `ScreenshotResponse` (includes confidence) |
| `useCalibrationSummary()` | `useSWR` GET | `/api/v1/rendering/calibration/summary` | `CalibrationSummaryResponse` |
| `useCalibrationHistory(clientId)` | `useSWR` GET | `/api/v1/rendering/calibration/history/{clientId}` | `CalibrationHistoryResponse` |
| `useTriggerCalibration()` | `useSWRMutation` POST | `/api/v1/rendering/calibration/trigger` | `{ triggered: boolean }` |

Pass `null` key when `clientId` is null (SWR conditional fetching pattern).

### Step 4: Create `ConfidenceBar` Component

Extract from `gate-client-row.tsx` lines 50-63 into a standalone component:

```typescript
interface ConfidenceBarProps {
  score: number;       // 0-100
  threshold?: number;  // 0-100, optional threshold marker
  label?: string;
  breakdown?: ConfidenceBreakdown;
  size?: "sm" | "md";  // sm=h-2 (default), md=h-3
}
```

- Color: `bg-status-success` (>85), `bg-status-warning` (60-85), `bg-status-danger` (<60)
- Threshold marker: `bg-foreground-muted` vertical line at threshold position
- Breakdown tooltip: show 4 component scores on hover (use `title` attr or simple popover)
- Update `gate-client-row.tsx` to import and use `ConfidenceBar` instead of inline bar

### Step 5: Create `ClientPreviewCard` Component

```typescript
interface ClientPreviewCardProps {
  clientId: string;
  clientName: string;
  screenshot: string | null;  // base64 or null if not yet rendered
  confidence: number;
  breakdown?: ConfidenceBreakdown;
  hasDarkVariant?: boolean;
  onViewFull: (clientId: string) => void;
}
```

Structure:
- Card: `rounded-lg border border-card-border bg-card-bg p-3`
- Top: screenshot thumbnail (aspect-ratio 4/3, `object-cover`, sandbox if iframe needed — but base64 img is safe)
- Bottom: client name, `ConfidenceBar`, score badge
- Click → `onViewFull` callback (parent handles Dialog)
- Dark mode toggle pill if `hasDarkVariant` (switches between e.g. `gmail_web` and `gmail_web_dark`)

### Step 6: Create `ConfidenceSummaryBar` Component

```typescript
interface ConfidenceSummaryBarProps {
  clientResults: Array<{ client_id: string; score: number; market_share: number }>;
  overallScore: number;
}
```

- Horizontal bar: segments proportional to `market_share`, colored by tier (green/yellow/red)
- Hover segment → tooltip: client name, confidence %, blind spots
- Below bar: "Overall rendering confidence: {overallScore}%" text
- Use `CLIENT_MARKET_SHARE` from types for segment widths

### Step 7: Create `CalibrationHealthPanel` Component

```typescript
interface CalibrationHealthPanelProps {
  summary: CalibrationSummaryResponse | undefined;
  isLoading: boolean;
  onRecalibrate: (clientId: string) => void;
  isAdmin: boolean;
}
```

- Collapsible section (Chevron toggle, default collapsed)
- Only rendered when `isAdmin`
- Per-client row: name, accuracy sparkline (last 10 values as inline SVG polyline), last calibrated date, regression alert badge
- "Recalibrate" button per client → calls `onRecalibrate`
- Use Skeleton loading pattern from `EcosystemDashboard`

### Step 8: Create `RenderingDashboard` Component

Main orchestrator component.

```typescript
interface RenderingDashboardProps {
  html: string | null;        // current email HTML from parent
  projectId: number | null;
}
```

**State management:**
- `useScreenshotsWithConfidence` — triggered when html is provided
- `useGateEvaluate` — reuse existing hook from `use-rendering-gate.ts`
- `useCalibrationSummary` — GET on mount
- `useSession` — check admin role for calibration panel

**Layout:**
1. **Confidence Summary Bar** — top, full width
2. **Preview Grid** — `grid grid-cols-2 gap-4 lg:grid-cols-4` with `ClientPreviewCard`s
3. **Gate Status Panel** — reuse `GateSummaryBadge` + `GateClientRow` list (existing components)
4. **Calibration Health** — admin collapsible at bottom

**Empty state:** If `html` is null, show `EmptyState` with "Select a project and build an email to see rendering previews."

**Screenshot dialog:** When user clicks "View Full" on a card, open `RenderingScreenshotDialog` (existing component from `renderings/`) with that client's screenshot.

### Step 9: Add Dashboard Tab to Renderings Page

Modify `app/(dashboard)/renderings/page.tsx`:

- Expand `Tab` type: `"tests" | "patterns" | "dashboard"`
- Add third tab button "Dashboard" in tab bar
- Add `{tab === "dashboard" && <RenderingDashboard ... />}` section
- Dashboard doesn't need HTML to be passed from this page (it's a standalone overview) — pass `html={null}` initially. Users can trigger rendering from the dashboard itself via the existing "Request Rendering Test" dialog.

### Step 10: Frontend Tests

**Test pattern:** Follow `ecosystem-dashboard.test.tsx` — mock hooks with `vi.mock`, factory functions for test data, test rendering states (loading, data, empty, error).

#### `__tests__/confidence-bar.test.tsx` (~8 tests)
- Renders green bar when score > 85
- Renders yellow bar when score 60-85
- Renders red bar when score < 60
- Renders threshold marker at correct position
- Does not render threshold when not provided
- Clamps score to 0-100 range
- Renders with "sm" and "md" sizes
- Shows breakdown in tooltip when provided

#### `__tests__/gate-panel.test.tsx` (~8 tests)
- Mock `useGateEvaluate` + `useSession`
- Renders loading spinner during evaluation
- Shows error state with retry button
- Displays pass verdict with proceed button
- Displays block verdict with override button for admin
- Hides override button for non-admin when blocked
- Shows recommendations when present
- Renders client rows for each result

#### `__tests__/rendering-dashboard.test.tsx` (~10 tests)
- Mock `useScreenshotsWithConfidence`, `useCalibrationSummary`, `useGateEvaluate`, `useSession`
- Shows empty state when html is null
- Renders preview grid with correct number of cards
- Renders confidence summary bar
- Shows gate status section
- Shows calibration panel only for admin
- Hides calibration panel for non-admin
- Loading skeletons during data fetch
- Error state with retry
- Click on card triggers full-view dialog

## Security Checklist
- [ ] No `(x as any)` type casts — use proper type augmentation
- [ ] API calls use `authFetch` via SWR hooks (never raw `fetch`)
- [ ] No `dangerouslySetInnerHTML` — screenshots are base64 `<img>` tags (safe)
- [ ] Token handling uses existing `authFetch` JWT mechanism
- [ ] Session role check via `useSession().data?.user?.role` (same as `gate-panel.tsx:34`)
- [ ] Preview images are `<img src="data:image/png;base64,...">` — no iframe needed, no XSS risk

## Verification
- [ ] `make check-fe` passes (TypeScript + tests)
- [ ] No TypeScript errors in new files
- [ ] Semantic Tailwind tokens only (no primitive colors)
- [ ] All 14 client profiles represented in type union + display names
- [ ] Confidence bar reused in gate-client-row (no duplication)
- [ ] Admin-only calibration panel hidden for developer/viewer roles
- [ ] ~26 frontend tests across 3 test files
- [ ] Dashboard tab accessible from existing `/renderings` route (no middleware change needed)
