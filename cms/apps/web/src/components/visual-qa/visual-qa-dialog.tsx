"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Camera, GitCompareArrows, Loader2 } from "../icons";
import { toast } from "sonner";
import { useCaptureScreenshots, useVisualDiff, useBaselines } from "@/hooks/use-visual-qa";
import { ClientComparisonGrid } from "./client-comparison-grid";
import { DiffOverlay } from "./diff-overlay";
import { BaselineManager } from "./baseline-manager";
import type { ClientScreenshot, VisualDiffResponse, VisualQAEntityType } from "@/types/rendering";

type Tab = "screenshots" | "diff" | "baselines";

interface VisualQADialogProps {
  open: boolean;
  onClose: () => void;
  html: string;
  entityType: VisualQAEntityType;
  entityId: number;
}

export function VisualQADialog({ open, onClose, html, entityType, entityId }: VisualQADialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  const [activeTab, setActiveTab] = useState<Tab>("screenshots");
  const [selectedClient, setSelectedClient] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [screenshots, setScreenshots] = useState<ClientScreenshot[]>([]);
  const [diffResult, setDiffResult] = useState<VisualDiffResponse | null>(null);

  const { trigger: captureScreenshots, isMutating: isCapturing } = useCaptureScreenshots();
  const { trigger: runVisualDiff, isMutating: isDiffing } = useVisualDiff();
  const { data: baselinesData } = useBaselines(
    entityId > 0 ? entityType : null,
    entityId > 0 ? entityId : null,
  );

  // Dialog open/close sync
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleCapture = useCallback(async () => {
    try {
      const result = await captureScreenshots({ html });
      setScreenshots(result.screenshots);
      if (result.clients_failed > 0) {
        toast.warning(`${result.clients_failed} client(s) failed to render`);
      }
    } catch {
      toast.error("Failed to capture screenshots");
    }
  }, [captureScreenshots, html]);

  // Auto-capture on first open if no screenshots
  useEffect(() => {
    if (open && screenshots.length === 0 && html.length > 0) {
      handleCapture();
    }
  }, [open, handleCapture]);

  const handleRunDiff = useCallback(
    async (clientName: string) => {
      const screenshot = screenshots.find((s) => s.client_name === clientName);
      const baseline = baselinesData?.baselines.find((b) => b.client_name === clientName);

      if (!screenshot || !baseline) {
        setDiffResult(null);
        return;
      }

      // We need the baseline image — but the API only stores hash, not image.
      // The visual-diff endpoint takes two base64 images, so we need the baseline image.
      // For now, we'll show "no baseline" state since getting baseline image data
      // requires the entity to have stored the actual image bytes.
      // The API returns BaselineResponse with hash only, not image data.
      // TODO: When baseline GET returns image_base64, wire this up.
      toast.info("No baseline set for this client");
      setDiffResult(null);
    },
    [screenshots, baselinesData],
  );

  // Run diff when switching to diff tab with a selected client
  useEffect(() => {
    if (activeTab === "diff" && selectedClient) {
      handleRunDiff(selectedClient);
    }
  }, [activeTab, selectedClient]);

  const handleRunDiffAll = useCallback(async () => {
    if (selectedClient) {
      await handleRunDiff(selectedClient);
    } else if (screenshots.length > 0 && screenshots[0]) {
      setSelectedClient(screenshots[0].client_name);
      setActiveTab("diff");
    }
  }, [selectedClient, screenshots, handleRunDiff]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "screenshots", label: "Screenshots" },
    { key: "diff", label: "Diff Analysis" },
    { key: "baselines", label: "Baselines" },
  ];

  const selectedScreenshot = screenshots.find((s) => s.client_name === selectedClient);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="border-border bg-card fixed inset-0 m-auto h-[90vh] w-[90vw] max-w-[96rem] rounded-xl border p-0 shadow-2xl backdrop:bg-black/50"
    >
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="border-border flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-foreground text-lg font-semibold">{"Visual QA Results"}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-foreground-muted hover:bg-surface-hover hover:text-foreground rounded p-1 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab bar */}
        <div className="border-border flex gap-1 border-b px-6" role="tablist">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? "border-interactive text-foreground border-b-2"
                  : "text-foreground-muted hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {activeTab === "screenshots" && (
            <ClientComparisonGrid
              screenshots={screenshots}
              onSelectClient={(client) => {
                setSelectedClient(client);
                setActiveTab("diff");
              }}
              selectedClient={selectedClient}
            />
          )}

          {activeTab === "diff" && (
            <div>
              {!selectedScreenshot ? (
                <p className="text-foreground-muted py-12 text-center text-sm">
                  {"Select a client from the Screenshots tab to compare"}
                </p>
              ) : diffResult ? (
                <DiffOverlay
                  originalBase64={selectedScreenshot.image_base64}
                  diffBase64={diffResult.diff_image}
                  diffPercentage={diffResult.diff_percentage}
                  changedRegions={diffResult.changed_regions}
                  showDiff={showDiff}
                  onToggleDiff={() => setShowDiff((v) => !v)}
                />
              ) : isDiffing ? (
                <div className="text-foreground-muted flex items-center justify-center gap-2 py-12">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span className="text-sm">{"Running diff…"}</span>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-foreground-muted text-sm">
                    {"No baseline set for this client"}
                  </p>
                  {/* Show the screenshot even without diff */}
                  <div className="border-border overflow-hidden rounded-lg border">
                    <img
                      src={`data:image/png;base64,${selectedScreenshot.image_base64}`}
                      alt={selectedClient ?? ""}
                      className="h-auto max-h-[32rem] w-full object-contain"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "baselines" && (
            <BaselineManager
              entityType={entityType}
              entityId={entityId}
              currentScreenshots={screenshots}
            />
          )}
        </div>

        {/* Footer */}
        <div className="border-border flex items-center justify-end gap-3 border-t px-6 py-3">
          <button
            type="button"
            onClick={handleCapture}
            disabled={isCapturing}
            className="border-border text-foreground hover:bg-surface-hover inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {isCapturing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Camera className="h-4 w-4" />
            )}
            {"Capture Screenshots"}
          </button>
          <button
            type="button"
            onClick={handleRunDiffAll}
            disabled={isDiffing || screenshots.length === 0}
            className="bg-interactive text-on-interactive hover:bg-interactive-hover inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {isDiffing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GitCompareArrows className="h-4 w-4" />
            )}
            {"Run Diff All"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
