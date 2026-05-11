"use client";

import { useRef, useEffect } from "react";
import { X, Loader2, AlertTriangle, CheckCircle, ImageOff } from "../icons";
import { useRenderingComparison } from "@/hooks/use-renderings";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  baselineTestId: number | null;
  currentTestId: number | null;
}

function diffBadge(pct: number) {
  if (pct < 2)
    return { label: "< 2% diff", className: "bg-badge-success-bg text-badge-success-text" };
  if (pct < 5)
    return { label: "2-5% diff", className: "bg-badge-warning-bg text-badge-warning-text" };
  return { label: "> 5% diff", className: "bg-badge-danger-bg text-badge-danger-text" };
}

export function VisualRegressionDialog({
  open,
  onOpenChange,
  baselineTestId,
  currentTestId,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const { trigger, data, isMutating, error } = useRenderingComparison();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      if (baselineTestId && currentTestId) {
        trigger({ baseline_test_id: baselineTestId, current_test_id: currentTestId });
      }
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="border-card-border bg-card-bg w-full max-w-[56rem] rounded-lg border p-0 shadow-xl backdrop:bg-black/50"
      onClose={() => onOpenChange(false)}
    >
      {/* Header */}
      <div className="border-card-border flex items-center justify-between border-b p-4">
        <h2 className="text-foreground text-lg font-semibold">
          {"Visual Regression"}: #{baselineTestId} vs #{currentTestId}
        </h2>
        <button
          onClick={() => onOpenChange(false)}
          className="text-foreground-muted hover:bg-surface-muted hover:text-foreground rounded p-1"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-4">
        {isMutating && (
          <div className="flex flex-col items-center gap-4 py-12">
            <Loader2 className="text-foreground-accent h-8 w-8 animate-spin" />
            <p className="text-foreground-muted text-sm">{"Processing"}</p>
          </div>
        )}

        {error && !isMutating && (
          <div className="flex flex-col items-center gap-4 py-12">
            <AlertTriangle className="text-status-danger h-8 w-8" />
            <p className="text-foreground text-sm">{"Failed to load rendering data"}</p>
          </div>
        )}

        {data && !isMutating && (
          <>
            {/* Summary */}
            <div className="border-card-border bg-surface-muted/30 mb-4 flex items-center gap-3 rounded-lg border p-3">
              {data.regressions_found > 0 ? (
                <AlertTriangle className="text-status-warning h-5 w-5" />
              ) : (
                <CheckCircle className="text-status-success h-5 w-5" />
              )}
              <span className="text-foreground text-sm">
                {data.regressions_found > 0
                  ? `${data.regressions_found} regressions found across ${data.total_clients} clients`
                  : "No regressions detected"}
              </span>
            </div>

            {/* Diff grid */}
            <div className="space-y-4">
              {(data.diffs ?? []).map((diff) => {
                const badge = diffBadge(diff.diff_percentage);
                return (
                  <div key={diff.client_name} className="border-card-border rounded-lg border p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-foreground text-sm font-medium">
                        {diff.client_name}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
                        >
                          {diff.diff_percentage.toFixed(1)}% — {badge.label}
                        </span>
                        {diff.has_regression && (
                          <span className="bg-badge-danger-bg text-badge-danger-text rounded-full px-2 py-0.5 text-xs font-medium">
                            {"Regression"}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-foreground-muted mb-1 text-xs">{"Baseline"}</p>
                        {diff.baseline_url ? (
                          <img
                            src={diff.baseline_url}
                            alt={`${diff.client_name} baseline`}
                            className="border-card-border w-full rounded border object-contain"
                            loading="lazy"
                          />
                        ) : (
                          <div className="border-card-border bg-surface-muted flex aspect-[3/2] items-center justify-center rounded border">
                            <ImageOff className="text-foreground-muted/40 h-6 w-6" />
                          </div>
                        )}
                      </div>
                      <div>
                        <p className="text-foreground-muted mb-1 text-xs">{"Current"}</p>
                        {diff.current_url ? (
                          <img
                            src={diff.current_url}
                            alt={`${diff.client_name} current`}
                            className="border-card-border w-full rounded border object-contain"
                            loading="lazy"
                          />
                        ) : (
                          <div className="border-card-border bg-surface-muted flex aspect-[3/2] items-center justify-center rounded border">
                            <ImageOff className="text-foreground-muted/40 h-6 w-6" />
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Close */}
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => onOpenChange(false)}
                className="text-foreground-muted hover:text-foreground rounded px-4 py-2 text-sm font-medium"
              >
                {"Close"}
              </button>
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}
