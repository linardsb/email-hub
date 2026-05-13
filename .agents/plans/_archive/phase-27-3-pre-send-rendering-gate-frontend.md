# Plan: Phase 27.3 — Pre-Send Rendering Gate (Frontend)

## Context

The platform currently has no rendering quality gate before ESP sync or email export. Phase 27.1 added 8 email client emulators with 14 profiles, and 27.2 added per-client confidence scoring. This phase integrates all rendering intelligence into a single go/no-go gate with a frontend panel that shows traffic-light results, per-client confidence bars, blocking reasons, and remediation suggestions. The gate intercepts both the ESP sync and export flows.

**Backend provides** (built separately):
- `POST /api/v1/rendering/gate/evaluate` — run gate evaluation (returns `GateResult`)
- `GET /api/v1/rendering/gate/config/{project_id}` — get project gate config
- `PUT /api/v1/rendering/gate/config/{project_id}` — update project gate config (admin)
- Gate integrated into connector sync and email export services

## Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `cms/apps/web/src/types/rendering-gate.ts` | TypeScript types for gate API |
| 2 | `cms/apps/web/src/hooks/use-rendering-gate.ts` | SWR hooks for gate evaluate + config |
| 3 | `cms/apps/web/src/components/rendering/gate-panel.tsx` | Main gate results panel component |
| 4 | `cms/apps/web/src/components/rendering/gate-client-row.tsx` | Per-client confidence row |
| 5 | `cms/apps/web/src/components/rendering/gate-summary-badge.tsx` | Traffic-light summary badge |

## Files to Modify

| # | File | Change |
|---|------|--------|
| 6 | `cms/apps/web/src/components/connectors/export-dialog.tsx` | Wire gate panel before export |
| 7 | `cms/apps/web/src/components/connectors/push-to-esp-dialog.tsx` | Wire gate panel before push |

## Implementation Steps

### Step 1 — Types (`types/rendering-gate.ts`)

```typescript
// ── Gate types (27.3) ────────────────────────────────────

export type GateMode = "enforce" | "warn" | "skip";

export type GateVerdict = "pass" | "warn" | "block";

export interface ClientGateResult {
  client_name: string;
  confidence_score: number;      // 0-100
  threshold: number;             // 0-100
  passed: boolean;
  tier: string;                  // "tier_1" | "tier_2" | "tier_3"
  blocking_reasons: string[];
  remediation: string[];
}

export interface GateResult {
  passed: boolean;
  verdict: GateVerdict;          // "pass" | "warn" | "block"
  mode: GateMode;
  client_results: ClientGateResult[];
  blocking_clients: string[];
  recommendations: string[];
  evaluated_at: string;          // ISO datetime
}

export interface GateEvaluateRequest {
  html: string;
  target_clients?: string[];
  project_id?: number;
}

export interface RenderingGateConfig {
  mode: GateMode;
  tier_thresholds: Record<string, number>;  // { tier_1: 85, tier_2: 70, tier_3: 60 }
  target_clients: string[];
  require_external_validation: string[];
}

export interface GateConfigUpdateRequest {
  mode?: GateMode;
  tier_thresholds?: Record<string, number>;
  target_clients?: string[];
  require_external_validation?: string[];
}
```

### Step 2 — Hooks (`hooks/use-rendering-gate.ts`)

Follow patterns from `use-renderings.ts` (SWR reads) and `mutation-fetcher.ts` (mutations).

```typescript
"use client";

import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { fetcher } from "@/lib/swr-fetcher";
import { longMutationFetcher, mutationFetcher } from "@/lib/mutation-fetcher";
import type { ApiError } from "@/lib/api-error";
import type {
  GateResult,
  GateEvaluateRequest,
  RenderingGateConfig,
  GateConfigUpdateRequest,
} from "@/types/rendering-gate";

const BASE = "/api/v1/rendering/gate";

/** Trigger gate evaluation (POST — mutation, not cached read). */
export function useGateEvaluate() {
  return useSWRMutation<GateResult, ApiError, string, GateEvaluateRequest>(
    `${BASE}/evaluate`,
    longMutationFetcher,
  );
}

/** Read project gate config. Pass null to skip. */
export function useGateConfig(projectId: number | null) {
  return useSWR<RenderingGateConfig, ApiError>(
    projectId ? `${BASE}/config/${projectId}` : null,
    fetcher,
  );
}

/** Update project gate config (admin only). */
export function useUpdateGateConfig(projectId: number | null) {
  // PUT-based mutation — need a custom fetcher since mutationFetcher uses POST
  return useSWRMutation<RenderingGateConfig, ApiError, string, GateConfigUpdateRequest>(
    projectId ? `${BASE}/config/${projectId}` : "",
    putMutationFetcher,
  );
}
```

**Note:** `putMutationFetcher` — add to `mutation-fetcher.ts` or inline in this file. It's the same as `mutationFetcher` but with `method: "PUT"`. Follow the pattern:

```typescript
import { authFetch } from "@/lib/auth-fetch";
import { ApiError } from "@/lib/api-error";

async function putMutationFetcher<T>(
  url: string,
  { arg }: { arg: unknown },
): Promise<T> {
  const res = await authFetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) {
    let message = "Request failed";
    let code: string | undefined;
    try {
      const body = await res.json();
      if (body.error) message = body.error;
      if (body.type) code = body.type;
    } catch {
      message = res.statusText || message;
    }
    throw new ApiError(res.status, message, code);
  }
  return res.json();
}
```

Keep `putMutationFetcher` **local to this hook file** (not exported from `mutation-fetcher.ts`) to avoid scope creep. If other hooks later need PUT, then refactor.

### Step 3 — Gate Summary Badge (`components/rendering/gate-summary-badge.tsx`)

Traffic-light badge: green = pass, yellow = warn, red = block.

```typescript
"use client";

import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import type { GateVerdict } from "@/types/rendering-gate";

const VERDICT_STYLES: Record<GateVerdict, { bg: string; text: string; icon: typeof CheckCircle2; label: string }> = {
  pass: {
    bg: "bg-badge-success-bg",
    text: "text-badge-success-text",
    icon: CheckCircle2,
    label: "All Clients Pass",
  },
  warn: {
    bg: "bg-badge-warning-bg",
    text: "text-badge-warning-text",
    icon: AlertTriangle,
    label: "Warnings",
  },
  block: {
    bg: "bg-badge-danger-bg",
    text: "text-badge-danger-text",
    icon: XCircle,
    label: "Blocked",
  },
};

interface Props {
  verdict: GateVerdict;
  blockingCount?: number;
}

export function GateSummaryBadge({ verdict, blockingCount }: Props) {
  const style = VERDICT_STYLES[verdict];
  const Icon = style.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${style.bg} ${style.text}`}>
      <Icon className="h-3.5 w-3.5" />
      {style.label}
      {verdict === "block" && blockingCount ? ` (${blockingCount})` : ""}
    </span>
  );
}
```

### Step 4 — Gate Client Row (`components/rendering/gate-client-row.tsx`)

Per-client row with confidence bar, threshold marker, pass/fail badge, expandable reasons.

```typescript
"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import type { ClientGateResult } from "@/types/rendering-gate";

/** Map tier names to human-readable labels. */
const TIER_LABELS: Record<string, string> = {
  tier_1: "Tier 1",
  tier_2: "Tier 2",
  tier_3: "Tier 3",
};

interface Props {
  result: ClientGateResult;
}

export function GateClientRow({ result }: Props) {
  const [expanded, setExpanded] = useState(!result.passed);
  const hasDetails = result.blocking_reasons.length > 0 || result.remediation.length > 0;

  // Confidence bar color based on pass/fail
  const barColor = result.passed ? "bg-status-success" : "bg-status-danger";
  const barWidth = Math.max(0, Math.min(100, result.confidence_score));
  // Threshold marker position
  const thresholdLeft = Math.max(0, Math.min(100, result.threshold));

  return (
    <div className="rounded-md border border-card-border bg-card-bg">
      {/* Header row — always visible */}
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((prev) => !prev)}
        disabled={!hasDetails}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm"
      >
        {/* Expand chevron */}
        <span className="w-4 shrink-0 text-foreground-muted">
          {hasDetails ? (
            expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
          ) : null}
        </span>

        {/* Client name + tier */}
        <span className="w-40 shrink-0">
          <span className="font-medium text-foreground">{result.client_name}</span>
          <span className="ml-1.5 text-xs text-foreground-muted">
            {TIER_LABELS[result.tier] ?? result.tier}
          </span>
        </span>

        {/* Confidence bar */}
        <span className="relative flex-1">
          <span className="block h-2 w-full rounded-full bg-surface-muted">
            <span
              className={`block h-2 rounded-full ${barColor} transition-all`}
              style={{ width: `${barWidth}%` }}
            />
          </span>
          {/* Threshold marker */}
          <span
            className="absolute top-0 h-2 w-0.5 bg-foreground-muted"
            style={{ left: `${thresholdLeft}%` }}
            title={`Threshold: ${result.threshold}%`}
          />
        </span>

        {/* Score */}
        <span className="w-14 shrink-0 text-right font-mono text-xs text-foreground-muted">
          {result.confidence_score.toFixed(0)}%
        </span>

        {/* Pass/fail badge */}
        <span
          className={`w-14 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-medium ${
            result.passed
              ? "bg-badge-success-bg text-badge-success-text"
              : "bg-badge-danger-bg text-badge-danger-text"
          }`}
        >
          {result.passed ? "Pass" : "Fail"}
        </span>
      </button>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div className="border-t border-card-border px-3 py-2.5 pl-10 text-xs">
          {result.blocking_reasons.length > 0 && (
            <div className="mb-2">
              <p className="mb-1 font-medium text-foreground">Blocking Reasons</p>
              <ul className="list-inside list-disc space-y-0.5 text-foreground-muted">
                {result.blocking_reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
          {result.remediation.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-foreground">Remediation</p>
              <ul className="list-inside list-disc space-y-0.5 text-foreground-muted">
                {result.remediation.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### Step 5 — Gate Panel (`components/rendering/gate-panel.tsx`)

Main gate results panel. Handles three states: idle (trigger evaluation), loading, and results. Includes override button for admins.

```typescript
"use client";

import { useCallback } from "react";
import { Loader2, ShieldCheck, ShieldAlert, SkipForward } from "lucide-react";
import { useSession } from "next-auth/react";
import { useGateEvaluate } from "@/hooks/use-rendering-gate";
import { GateSummaryBadge } from "./gate-summary-badge";
import { GateClientRow } from "./gate-client-row";
import type { GateResult } from "@/types/rendering-gate";

interface GatePanelProps {
  /** HTML to evaluate. Panel auto-triggers when html changes and is non-null. */
  html: string | null;
  /** Project ID for loading project-specific thresholds. */
  projectId: number;
  /** Target clients to evaluate (optional — backend defaults to project targets). */
  targetClients?: string[];
  /** Called when user explicitly approves (either gate passed or admin override). */
  onApproved: () => void;
  /** Called when user cancels. */
  onCancel: () => void;
  /** Label for the approve button (e.g. "Export", "Push to ESP"). */
  approveLabel?: string;
}

export function GatePanel({
  html,
  projectId,
  targetClients,
  onApproved,
  onCancel,
  approveLabel = "Continue",
}: GatePanelProps) {
  const session = useSession();
  const isAdmin = session.data?.user?.role === "admin";

  const { data: gateResult, trigger, isMutating, error } = useGateEvaluate();

  const runEvaluation = useCallback(() => {
    if (!html) return;
    trigger({
      html,
      project_id: projectId,
      target_clients: targetClients,
    });
  }, [html, projectId, targetClients, trigger]);

  // Auto-trigger on mount if html is ready and no result yet
  // Using React 19 pattern — derive from props, no useEffect
  const needsEvaluation = html && !gateResult && !isMutating && !error;

  // -- Idle / needs evaluation --
  if (needsEvaluation) {
    // Trigger immediately
    runEvaluation();
  }

  // -- Loading --
  if (isMutating) {
    return (
      <div className="flex flex-col items-center gap-3 py-6">
        <Loader2 className="h-6 w-6 animate-spin text-foreground-muted" />
        <p className="text-sm text-foreground-muted">Evaluating rendering confidence...</p>
      </div>
    );
  }

  // -- Error --
  if (error) {
    return (
      <div className="space-y-3">
        <div className="rounded-md bg-status-danger/10 p-3 text-sm text-status-danger">
          Gate evaluation failed: {error.message}
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-surface-hover"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={runEvaluation}
            className="rounded-md bg-interactive px-3 py-1.5 text-sm font-medium text-foreground-inverse hover:bg-interactive-hover"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // -- No result yet (waiting for auto-trigger) --
  if (!gateResult) {
    return null;
  }

  // -- Results --
  const canProceed = gateResult.passed || gateResult.verdict === "warn";
  const isBlocked = gateResult.verdict === "block";

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isBlocked ? (
            <ShieldAlert className="h-5 w-5 text-status-danger" />
          ) : (
            <ShieldCheck className="h-5 w-5 text-status-success" />
          )}
          <span className="text-sm font-medium text-foreground">Rendering Gate</span>
        </div>
        <GateSummaryBadge
          verdict={gateResult.verdict}
          blockingCount={gateResult.blocking_clients.length}
        />
      </div>

      {/* Client results list */}
      <div className="space-y-1.5">
        {gateResult.client_results.map((cr) => (
          <GateClientRow key={cr.client_name} result={cr} />
        ))}
      </div>

      {/* Global recommendations */}
      {gateResult.recommendations.length > 0 && (
        <div className="rounded-md bg-status-warning/10 p-3 text-xs text-foreground-muted">
          <p className="mb-1 font-medium text-foreground">Recommendations</p>
          <ul className="list-inside list-disc space-y-0.5">
            {gateResult.recommendations.map((rec, i) => (
              <li key={i}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 border-t border-card-border pt-3">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-surface-hover"
        >
          Cancel
        </button>

        {/* Admin override when blocked */}
        {isBlocked && isAdmin && (
          <button
            type="button"
            onClick={onApproved}
            className="flex items-center gap-1.5 rounded-md border border-status-warning px-3 py-1.5 text-sm font-medium text-status-warning hover:bg-status-warning/10"
          >
            <SkipForward className="h-4 w-4" />
            Override & Send Anyway
          </button>
        )}

        {/* Normal proceed when allowed */}
        {canProceed && (
          <button
            type="button"
            onClick={onApproved}
            className="rounded-md bg-interactive px-3 py-1.5 text-sm font-medium text-foreground-inverse hover:bg-interactive-hover"
          >
            {approveLabel}
          </button>
        )}

        {/* Blocked non-admin — no proceed button, only cancel */}
        {isBlocked && !isAdmin && (
          <p className="text-xs text-foreground-muted">
            Blocked — ask an admin to override or fix the issues above.
          </p>
        )}
      </div>
    </div>
  );
}
```

**Key design decisions:**
- `needsEvaluation` triggers the API call on first render (React 19 — no `useEffect` for derived state)
- Failed clients auto-expand their details; passing clients are collapsed
- Admin override uses `session.data?.user?.role === "admin"` (same as `PluginRow.tsx`)
- Semantic tokens only: `bg-badge-success-bg`, `text-status-danger`, `bg-surface-muted`, etc.

### Step 6 — Wire into Export Dialog (`export-dialog.tsx`)

Add a gate step between the user clicking "Export" and the actual export execution. Insert a two-phase flow: first show gate results, then proceed with export if gate passes or admin overrides.

**Changes to `export-dialog.tsx`:**

1. Add import at top:
```typescript
import { GatePanel } from "@/components/rendering/gate-panel";
```

2. Add state for gate phase:
```typescript
const [showGate, setShowGate] = useState(false);
const [gatePassedFor, setGatePassedFor] = useState<string | null>(null);
```

3. Modify `handleEspExport` — instead of immediately exporting, first show the gate panel:
```typescript
const handleEspExportClick = useCallback((cfg: ConnectorConfig) => {
  const state = espStatesRef.current[cfg.id] ?? initialEspState;
  if (!state.name.trim()) return;
  // Show gate panel first
  setGatePassedFor(null);
  setShowGate(true);
  setPendingExportCfg(cfg);
}, []);
```

4. Add a `pendingExportCfg` ref:
```typescript
const [pendingExportCfg, setPendingExportCfg] = useState<ConnectorConfig | null>(null);
```

5. When gate approves, proceed with original `handleEspExport`:
```typescript
const handleGateApproved = useCallback(() => {
  setShowGate(false);
  if (pendingExportCfg) {
    handleEspExport(pendingExportCfg);
  }
}, [pendingExportCfg, handleEspExport]);
```

6. Render the gate panel conditionally above the export form, or as a sub-view when `showGate` is true:
```tsx
{showGate && (
  <div className="border-t border-card-border p-4">
    <GatePanel
      html={compiledHtml}
      projectId={projectId}
      onApproved={handleGateApproved}
      onCancel={() => setShowGate(false)}
      approveLabel={pendingExportCfg?.exportButton ?? "Export"}
    />
  </div>
)}
```

7. Reset `showGate` when dialog closes (add to the existing `useEffect` that resets state on `!open`):
```typescript
setShowGate(false);
setPendingExportCfg(null);
```

### Step 7 — Wire into Push to ESP Dialog (`push-to-esp-dialog.tsx`)

Same pattern. Add gate evaluation before the push.

**Changes to `push-to-esp-dialog.tsx`:**

1. Add imports:
```typescript
import { GatePanel } from "@/components/rendering/gate-panel";
```

2. Add HTML prop (the dialog needs the compiled HTML to evaluate):
```typescript
interface PushToESPDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: number;
  templateName: string;
  projectId: number;
  compiledHtml: string | null;  // NEW — pass from parent
}
```

3. Add gate state:
```typescript
const [showGate, setShowGate] = useState(false);
```

4. Modify `handlePush` to show gate first:
```typescript
const handlePushClick = () => {
  if (!selectedId || !selectedConnection) return;
  setShowGate(true);
};

const handleGateApproved = async () => {
  setShowGate(false);
  // Original push logic
  if (!selectedId || !selectedConnection) return;
  try {
    await trigger({ template_id: templateId });
    const espLabel = ESP_LABELS[selectedConnection.esp_type]?.label ?? selectedConnection.esp_type;
    toast.success(`Template pushed to ${espLabel}`);
    onOpenChange(false);
  } catch {
    toast.error("Failed to push template");
  }
};
```

5. Render gate panel when `showGate` is true (replace the connection list with gate panel):
```tsx
{showGate ? (
  <GatePanel
    html={compiledHtml}
    projectId={projectId}
    onApproved={handleGateApproved}
    onCancel={() => setShowGate(false)}
    approveLabel="Push Template"
  />
) : (
  /* existing connection selection UI */
)}
```

6. Reset gate state when dialog reopens (in the existing open-change detection block):
```typescript
if (open && !prevOpen) {
  setSelectedId(null);
  setShowGate(false);
}
```

**Note on `compiledHtml` prop:** The parent component rendering `PushToESPDialog` needs to pass the compiled HTML. Check where `PushToESPDialog` is used and ensure `compiledHtml` is available in that context. If the parent doesn't have it, the gate panel shows a loading state and the caller can use `useEmailBuild` to compile first, or the gate endpoint can accept `template_id` as an alternative input.

## Security Checklist

For files in this plan only:
- [x] No `(x as any)` type casts — all types are explicit interfaces
- [x] API calls use `authFetch` via SWR hooks (never raw `fetch`)
- [x] No `dangerouslySetInnerHTML` — all content rendered as text nodes
- [x] Admin-only override gated by `session.data?.user?.role === "admin"` (same as `PluginRow.tsx`)
- [x] Gate evaluation is read-only analysis — no destructive operations
- [x] Override logged server-side (backend responsibility)
- [x] No preview iframes in gate panel — only text/SVG rendering
- [x] Semantic Tailwind tokens only — no primitive colors

## Verification

- [ ] `make check-fe` passes (TypeScript + tests)
- [ ] No TypeScript errors in new files
- [ ] Semantic Tailwind tokens only — grep for `text-gray`, `bg-blue`, etc. returns 0 hits in new files
- [ ] Gate panel shows green/yellow/red correctly based on API response
- [ ] Blocked state shows admin override button only for admin role
- [ ] Non-admin sees "ask an admin" message when blocked
- [ ] Export dialog shows gate before exporting
- [ ] Push-to-ESP dialog shows gate before pushing
- [ ] Cancel from gate panel returns to previous dialog state
- [ ] Gate auto-triggers evaluation when HTML is available
- [ ] Error state shows retry button
- [ ] `make test` passes (backend unchanged by this plan)

## Testing Notes

Unit tests for the gate panel should mock `useGateEvaluate` and `useSession`. Key scenarios:
1. All clients pass → green badge, proceed button visible
2. Some clients warn → yellow badge, proceed button visible
3. Blocking clients → red badge, no proceed for non-admin, override for admin
4. API error → error message + retry button
5. Loading state → spinner
6. Empty HTML → no evaluation triggered

Follow the mocking pattern from `cms/apps/web/src/components/ecosystem/__tests__/plugin-manager.test.tsx` which mocks SWR hooks and session role.
