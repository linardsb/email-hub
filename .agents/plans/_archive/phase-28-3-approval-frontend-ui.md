# Plan: Phase 28.3 — Approval Frontend UI

## Context

The approval backend (28.1 QA gate + 28.2 approval gate) is complete. The frontend already has **most approval components built** in `components/approvals/` — status badge, card, decision bar, feedback panel, audit timeline, preview, version compare. Hooks (`use-approvals.ts`) cover all 7 CRUD operations. List page (`/approvals`) and detail page (`/approvals/[id]`) exist.

**What's missing:** approval request dialog (submit build for approval), export dialog approval gate integration, workspace page wiring, project settings toggle, types file, and tests.

## Existing Assets (do NOT recreate)

| Asset | Location | Status |
|-------|----------|--------|
| `ApprovalStatusBadge` | `components/approvals/approval-status-badge.tsx` | Complete |
| `ApprovalCard` | `components/approvals/approval-card.tsx` | Complete |
| `ApprovalDecisionBar` | `components/approvals/approval-decision-bar.tsx` | Complete |
| `ApprovalFeedbackPanel` | `components/approvals/approval-feedback-panel.tsx` | Complete |
| `ApprovalAuditTimeline` | `components/approvals/approval-audit-timeline.tsx` | Complete |
| `ApprovalPreview` | `components/approvals/approval-preview.tsx` | Complete |
| `VersionCompareDialog` | `components/approvals/version-compare-dialog.tsx` | Complete |
| 8 SWR hooks | `hooks/use-approvals.ts` | Complete |
| List page | `app/(dashboard)/approvals/page.tsx` | Complete |
| Detail page | `app/(dashboard)/approvals/[id]/page.tsx` | Complete |
| Deliver menu item | `components/workspace/toolbar/deliver-menu.tsx` | Wired (`onSubmitForApproval` prop) |
| Toolbar prop | `components/workspace/workspace-toolbar.tsx` | Wired (`onSubmitForApproval` prop) |

## Files to Create

1. `cms/apps/web/src/types/approval.ts` — TypeScript types for approval domain
2. `cms/apps/web/src/components/approvals/approval-request-dialog.tsx` — submit build for approval dialog
3. `cms/apps/web/src/components/approvals/approval-gate-panel.tsx` — approval gate panel for export dialogs
4. `cms/apps/web/src/hooks/use-export-pre-check.ts` — hook for combined QA + rendering + approval pre-check
5. `cms/apps/web/src/components/approvals/__tests__/approval-components.test.tsx` — component tests
6. `cms/apps/web/src/hooks/__tests__/use-export-pre-check.test.ts` — hook tests

## Files to Modify

1. `cms/apps/web/src/app/projects/[id]/workspace/page.tsx` — wire approval dialog + handler
2. `cms/apps/web/src/components/connectors/export-dialog.tsx` — add approval gate check
3. `cms/apps/web/src/components/connectors/push-to-esp-dialog.tsx` — add approval gate check

## Backend API Reference

### Approval Endpoints (base: `/api/v1/approvals`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/` | query: `project_id` | `ApprovalResponse[]` |
| POST | `/` | `{ build_id, project_id }` | `ApprovalResponse` |
| GET | `/{id}` | — | `ApprovalResponse` |
| POST | `/{id}/decide` | `{ status, review_note? }` | `ApprovalResponse` |
| POST | `/{id}/feedback` | `{ content, feedback_type? }` | `FeedbackResponse` |
| GET | `/{id}/feedback` | — | `FeedbackResponse[]` |
| GET | `/{id}/audit` | — | `AuditResponse[]` |

### Export Pre-Check Endpoint

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/v1/connectors/export/pre-check` | `{ html, project_id, target_clients? }` | `{ qa: QAGateResult, rendering: GateResult, approval: ApprovalGateResult, can_export: bool }` |

### Response Schemas

**ApprovalResponse:** `id: number`, `build_id: number`, `project_id: number`, `status: "pending"|"approved"|"rejected"|"revision_requested"`, `requested_by_id: number`, `reviewed_by_id: number|null`, `review_note: string|null`, `created_at: string`, `updated_at: string`

**ApprovalGateResult:** `required: boolean`, `passed: boolean`, `reason: string|null`, `approval_id: number|null`, `approved_by: string|null`, `approved_at: string|null`

**FeedbackResponse:** `id: number`, `approval_id: number`, `author_id: number`, `content: string`, `feedback_type: string`, `created_at: string`

**AuditResponse:** `id: number`, `approval_id: number`, `action: string`, `actor_id: number`, `details: string|null`, `created_at: string`

## Implementation Steps

### Step 1: Create Types (`types/approval.ts`)

Define TypeScript interfaces matching backend schemas above:
- `ApprovalStatus` — union type of 4 status strings
- `ApprovalResponse`, `ApprovalCreate`, `ApprovalDecision`
- `FeedbackResponse`, `FeedbackCreate`
- `AuditResponse`
- `ApprovalGateResult` — the gate result nested in export pre-check
- `ExportPreCheckResponse` — `{ qa: QAGateResult, rendering: GateResult, approval: ApprovalGateResult, can_export: boolean }`

Import `QAGateResult` from existing connectors types if available, otherwise define inline. Import `GateResult` from `types/rendering-gate.ts` (already exists with `GateVerdict`, `GateResult`, `GateEvaluateRequest`).

### Step 2: Create Export Pre-Check Hook (`hooks/use-export-pre-check.ts`)

SWR mutation hook for combined gate pre-check before export:

```typescript
const BASE = "/api/v1/connectors/export";

export function useExportPreCheck() {
  return useSWRMutation<ExportPreCheckResponse, ApiError, string, ExportPreCheckRequest>(
    `${BASE}/pre-check`,
    mutationFetcher,
  );
}
```

Request type: `{ html: string; project_id: number; target_clients?: string[] }`
Response type: `ExportPreCheckResponse` from Step 1.

Follow pattern in `hooks/use-esp-sync.ts` — same `useSWRMutation` + `mutationFetcher` pattern.

### Step 3: Create Approval Request Dialog (`components/approvals/approval-request-dialog.tsx`)

Dialog for submitting a build for approval. Triggered from workspace "Deliver" menu.

**Props:** `open: boolean`, `onOpenChange: (open: boolean) => void`, `buildId: number`, `projectId: number`, `onSubmitted: () => void`

**Structure:**
- `Dialog` → `DialogContent` (max-w-[32rem] — form dialog)
- `DialogHeader`: title "Submit for Approval", description "Submit this build for review before export"
- Body:
  - Build info summary (build ID, project)
  - Optional `<textarea>` for reviewer note (placeholder: "Add context for the reviewer...")
  - If pre-check data available: show QA summary badges (pass/warn/fail counts)
- Footer:
  - Cancel button (secondary)
  - "Submit for Approval" button (primary, uses `bg-interactive` token)
  - Loading state: `Loader2 animate-spin` + disabled when `isMutating`

**Hooks used:**
- `useCreateApproval()` from existing `hooks/use-approvals.ts`
- `useExportPreCheck()` from Step 2 (trigger on mount to show QA summary)

**On submit:**
1. `await trigger({ build_id: buildId, project_id: projectId })`
2. `toast.success("Build submitted for approval")`
3. Call `onSubmitted()`, close dialog

**Error handling:** catch `ApiError`, show `toast.error(err.message)`.

Follow dialog pattern in `components/workspace/qa-override-dialog.tsx` (same Dialog imports, layout, loading states, toast pattern).

### Step 4: Create Approval Gate Panel (`components/approvals/approval-gate-panel.tsx`)

Inline panel shown in export/push dialogs when approval is required but not yet granted.

**Props:** `approvalResult: ApprovalGateResult`, `onRequestApproval: () => void`

**Structure:**
- Container div with `rounded-lg border border-border p-4`
- Header: shield icon + "Approval Required"
- If `approvalResult.required && !approvalResult.passed`:
  - Show reason text (`text-foreground-muted`)
  - Status: use `ApprovalStatusBadge` if approval exists
  - "Submit for Approval" link button (`text-interactive`) → calls `onRequestApproval`
- If `approvalResult.passed`:
  - Green checkmark + "Approved" + approved_by + approved_at
- If `!approvalResult.required`:
  - Don't render (return null)

Use semantic tokens: `text-status-success` for approved, `text-status-warning` for pending, `text-status-danger` for rejected.

### Step 5: Modify Export Dialog (`components/connectors/export-dialog.tsx`)

**Current flow:** user clicks ESP → `handleEspExportClick()` → shows rendering `GatePanel` → `handleGateApproved()` → exports.

**New flow:** user clicks ESP → `handleEspExportClick()` → trigger pre-check → if approval required & not passed, show `ApprovalGatePanel` above `GatePanel` → if all gates pass, proceed.

Changes:
1. Import `useExportPreCheck` and `ApprovalGatePanel`
2. Add state: `const [approvalDialogOpen, setApprovalDialogOpen] = useState(false)`
3. In `handleEspExportClick()`: trigger pre-check, store result
4. In gate panel section (lines ~273-281): add `ApprovalGatePanel` above existing `GatePanel` when `preCheckResult?.approval?.required`
5. Modify proceed logic: only allow export when `preCheckResult?.can_export` is true (or admin override)
6. Add `ApprovalRequestDialog` rendered at bottom of dialog, opened when user clicks "Submit for Approval" in gate panel

**Key integration point** (around line 273):
```tsx
{showGate && (
  <div className="space-y-4">
    {preCheckResult?.approval?.required && (
      <ApprovalGatePanel
        approvalResult={preCheckResult.approval}
        onRequestApproval={() => setApprovalDialogOpen(true)}
      />
    )}
    <GatePanel
      html={compiledHtml}
      projectId={projectId}
      onApproved={handleGateApproved}
      onCancel={() => setShowGate(false)}
    />
  </div>
)}
```

Disable the "Proceed" flow in `handleGateApproved` if approval is required but not passed — show toast: "Approval required before export".

### Step 6: Modify Push to ESP Dialog (`components/connectors/push-to-esp-dialog.tsx`)

Same pattern as Step 5. The push dialog (162 lines) has a simpler structure:

1. Import `useExportPreCheck` and `ApprovalGatePanel`
2. In `handlePushClick()`: trigger pre-check
3. Before `GatePanel`, render `ApprovalGatePanel` if approval required
4. Block proceed if approval not passed

### Step 7: Wire Workspace Page (`app/projects/[id]/workspace/page.tsx`)

The toolbar already has `onSubmitForApproval` prop wired through to `DeliverMenu`. Add:

1. State: `const [approvalDialogOpen, setApprovalDialogOpen] = useState(false)`
2. Handler:
```typescript
const handleSubmitForApproval = useCallback(() => {
  if (!compiledHtml?.trim()) {
    toast.error("Compile the template first before submitting for approval");
    return;
  }
  setApprovalDialogOpen(true);
}, [compiledHtml]);
```
3. Pass to toolbar: `onSubmitForApproval={handleSubmitForApproval}`
4. Render dialog at bottom (alongside existing ExportDialog and PushToEspDialog):
```tsx
<ApprovalRequestDialog
  open={approvalDialogOpen}
  onOpenChange={setApprovalDialogOpen}
  buildId={currentBuildId}
  projectId={projectId}
  onSubmitted={() => {
    setApprovalDialogOpen(false);
    toast.success("Build submitted for approval");
  }}
/>
```

Note: Need `currentBuildId` — check if workspace page already tracks the current build ID from the last email build. If not, add state from `useEmailBuild` result. The `useEmailBuild` hook returns `buildId` on successful build — store it.

### Step 8: Component Tests (`components/approvals/__tests__/approval-components.test.tsx`)

Test `ApprovalRequestDialog` and `ApprovalGatePanel`:

**ApprovalRequestDialog tests:**
- Renders dialog with title and submit button
- Submit button is disabled when `isMutating`
- Calls `useCreateApproval().trigger` with correct `{ build_id, project_id }`
- Shows toast on success + calls `onSubmitted`
- Shows toast.error on API failure
- Optional note is included in submission when provided

**ApprovalGatePanel tests:**
- Returns null when `required === false`
- Shows "Approved" with green checkmark when `passed === true`
- Shows "Approval Required" with reason when `passed === false`
- Shows "Submit for Approval" link that calls `onRequestApproval`

Mock pattern — follow `components/__tests__/feature-components.test.tsx`:
```typescript
vi.mock("@/hooks/use-approvals", () => ({ useCreateApproval: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
```

### Step 9: Hook Tests (`hooks/__tests__/use-export-pre-check.test.ts`)

Follow pattern in `hooks/__tests__/use-data-hooks.test.ts`:
- Mock SWR + fetchers
- Verify `useExportPreCheck` passes correct URL key (`/api/v1/connectors/export/pre-check`)
- Verify it uses `mutationFetcher`
- Verify trigger passes request body through

## Security Checklist

- [x] No `(x as any)` type casts — proper types in `types/approval.ts`
- [x] API calls use `authFetch` via `mutationFetcher` / `fetcher` (never raw `fetch`)
- [x] No `dangerouslySetInnerHTML` — approval preview already uses sandboxed `srcDoc` iframe
- [x] Token handling uses existing NextAuth JWT flow (no custom token logic)
- [x] Approval enforcement is backend-only — frontend hides buttons by role but never bypasses server checks
- [x] Preview iframes use `sandbox` attribute (existing `ApprovalPreview` pattern)
- [x] RBAC: decision buttons hidden for non-admin/non-reviewer roles (existing `ApprovalDecisionBar` pattern)

## Verification

- [ ] `make check-fe` passes (TypeScript + tests)
- [ ] No TypeScript errors in new/modified files
- [ ] Semantic Tailwind tokens only (no primitive colors)
- [ ] "Submit for Approval" in Deliver menu opens dialog correctly
- [ ] Dialog submits to API, shows toast, closes
- [ ] Export dialog shows approval gate panel when approval required
- [ ] Export blocked when approval not granted (non-admin)
- [ ] Admin can override approval gate (server-side enforcement)
- [ ] Push to ESP dialog same behavior as export dialog
- [ ] Approvals list page shows new submissions
- [ ] Approval detail page allows review/decide/feedback
- [ ] No `as any` casts in changed files
