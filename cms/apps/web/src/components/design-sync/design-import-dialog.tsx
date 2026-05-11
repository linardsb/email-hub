"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@email-hub/ui/components/ui/dialog";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Puzzle,
} from "../icons";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { DesignFileBrowser } from "./design-file-browser";
import {
  useGenerateBrief,
  useCreateDesignImport,
  useDesignImport,
  useDesignComponents,
  useExtractComponents,
} from "@/hooks/use-design-sync";
import { longMutationFetcher } from "@/lib/mutation-fetcher";
import type { GeneratedBrief, DesignImport, ConvertImportArg } from "@/types/design-sync";

// ── Types ──

type ImportTab = "import" | "components";
type ImportStep = "select-frames" | "review-brief" | "converting" | "result";
type ExtractStep = "select-components" | "extracting" | "result";

interface DesignImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connectionId: number;
  connectionName: string;
  initialNodeIds?: string[];
  initialTab?: ImportTab;
}

// ── Status badge ──

function StatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { className: string; label: string }> = {
    pending: { className: "bg-surface-hover text-foreground-muted", label: "Pending" },
    extracting: { className: "bg-status-warning/10 text-status-warning", label: "Extracting" },
    converting: { className: "bg-interactive/10 text-interactive", label: "Converting" },
    completed: { className: "bg-status-success/10 text-status-success", label: "Completed" },
    failed: { className: "bg-status-danger/10 text-status-danger", label: "Failed" },
    cancelled: { className: "bg-surface-hover text-foreground-muted", label: "Cancelled" },
  };
  const fallback = { className: "bg-surface-hover text-foreground-muted", label: "Pending" };
  const info = statusMap[status] ?? fallback;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${info.className}`}
    >
      {info.label}
    </span>
  );
}

// ── Step indicator ──

function StepIndicator({ steps, currentIndex }: { steps: string[]; currentIndex: number }) {
  return (
    <div className="flex items-center gap-2">
      {steps.map((label, i) => (
        <div key={label} className="flex items-center gap-2">
          <div
            className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
              i < currentIndex
                ? "bg-status-success text-foreground-inverse"
                : i === currentIndex
                  ? "bg-interactive text-foreground-inverse"
                  : "bg-surface-hover text-foreground-muted"
            }`}
          >
            {i < currentIndex ? "\u2713" : i + 1}
          </div>
          <span
            className={`text-xs ${
              i === currentIndex ? "text-foreground font-medium" : "text-foreground-muted"
            }`}
          >
            {label}
          </span>
          {i < steps.length - 1 && <div className="bg-card-border h-px w-6" />}
        </div>
      ))}
    </div>
  );
}

// ── Import Design Tab ──

function ImportDesignWizard({
  connectionId,
  initialNodeIds,
}: {
  connectionId: number;
  initialNodeIds: string[];
}) {
  const router = useRouter();
  const hasPreselection = initialNodeIds.length > 0;
  const [step, setStep] = useState<ImportStep>(hasPreselection ? "review-brief" : "select-frames");
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>(initialNodeIds);
  const [briefData, setBriefData] = useState<GeneratedBrief | null>(null);
  const [editedBrief, setEditedBrief] = useState("");
  const [importId, setImportId] = useState<number | null>(null);
  const [importResult, setImportResult] = useState<DesignImport | null>(null);

  const { trigger: generateBrief, isMutating: isGenerating } = useGenerateBrief();
  const { trigger: createImport, isMutating: isCreating } = useCreateDesignImport();
  const { data: polledImport } = useDesignImport(step === "converting" ? importId : null, true);

  // Auto-advance when conversion completes
  useEffect(() => {
    if (!polledImport) return;
    if (polledImport.status === "completed" || polledImport.status === "failed") {
      setImportResult(polledImport);
      setStep("result");
    }
  }, [polledImport]);

  const steps = ["Select Frames", "Review Brief", "Converting", "Result"];
  const stepIndex = ["select-frames", "review-brief", "converting", "result"].indexOf(step);

  const handleGenerateBrief = async () => {
    try {
      const result = await generateBrief({
        connection_id: connectionId,
        selected_node_ids: selectedNodeIds,
        include_tokens: true,
      });
      setBriefData(result);
      setEditedBrief(result.brief);
      setStep("review-brief");
    } catch {
      toast.error("Failed to load file structure");
    }
  };

  // Auto-generate brief when frames were pre-selected from the file browser
  useEffect(() => {
    if (hasPreselection && !briefData && !isGenerating) {
      handleGenerateBrief();
    }
  }, []);

  const handleStartConversion = async () => {
    try {
      const importResp = await createImport({
        connection_id: connectionId,
        brief: editedBrief,
        selected_node_ids: selectedNodeIds,
      });
      setImportId(importResp.id);
      // Call convert directly with the fresh import ID — can't use
      // useConvertImport hook here because importId state hasn't
      // re-rendered yet (stale closure).
      const convertArg: ConvertImportArg = { run_qa: true, output_mode: "structured" };
      await longMutationFetcher<DesignImport>(
        `/api/v1/design-sync/imports/${importResp.id}/convert`,
        { arg: convertArg },
      );
      setStep("converting");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Conversion failed";
      toast.error(message);
    }
  };

  return (
    <div className="space-y-4">
      <StepIndicator steps={steps} currentIndex={stepIndex} />

      {/* Step 1: Select Frames */}
      {step === "select-frames" && (
        <div className="space-y-4">
          <p className="text-foreground-muted text-sm">{"Select frames to import"}</p>
          <DesignFileBrowser
            connectionId={connectionId}
            selectedNodeIds={selectedNodeIds}
            onSelectionChange={setSelectedNodeIds}
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleGenerateBrief}
              disabled={selectedNodeIds.length === 0 || isGenerating}
              className="bg-interactive text-foreground-inverse hover:bg-interactive-hover flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {"Generating brief…"}
                </>
              ) : (
                <>
                  {"Next"}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Review Brief (loading state while auto-generating) */}
      {step === "review-brief" && !briefData && (
        <div className="flex flex-col items-center justify-center gap-3 py-12">
          <Loader2 className="text-foreground-muted h-6 w-6 animate-spin" />
          <p className="text-foreground-muted text-sm">
            {"Analyzing design and generating brief…"}
          </p>
          <p className="text-foreground-muted text-xs">{`${selectedNodeIds.length} frames selected`}</p>
        </div>
      )}

      {/* Step 2: Review Brief (ready) */}
      {step === "review-brief" && briefData && (
        <div className="space-y-4">
          <div className="text-foreground-muted flex items-center gap-4 text-sm">
            <span>{`Layout: ${briefData.layout_summary}`}</span>
            <span>{`${briefData.sections_detected} sections detected`}</span>
          </div>
          <div>
            <label
              htmlFor="import-brief"
              className="text-foreground mb-1.5 block text-sm font-medium"
            >
              {"Campaign Brief"}
            </label>
            <textarea
              id="import-brief"
              value={editedBrief}
              onChange={(e) => setEditedBrief(e.target.value)}
              rows={12}
              className="border-input-border bg-input-bg text-foreground placeholder:text-input-placeholder focus:border-input-focus focus:ring-input-focus w-full rounded-md border px-3 py-2 font-mono text-sm focus:ring-1 focus:outline-none"
            />
            <p className="text-foreground-muted mt-1 text-xs">
              {
                "Edit the generated brief before conversion. The AI Scaffolder will use this to produce your email template."
              }
            </p>
          </div>
          <div className="flex justify-between">
            <button
              type="button"
              onClick={() => setStep("select-frames")}
              className="border-border text-foreground hover:bg-surface-hover flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              {"Back"}
            </button>
            <button
              type="button"
              onClick={handleStartConversion}
              disabled={editedBrief.trim().length < 10 || isCreating}
              className="bg-interactive text-foreground-inverse hover:bg-interactive-hover flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {isCreating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {"Start Conversion"}
                </>
              ) : (
                "Start Conversion"
              )}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Converting */}
      {step === "converting" && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="text-interactive h-8 w-8 animate-spin" />
          <p className="text-foreground text-sm font-medium">
            {"Converting your design to an email template…"}
          </p>
          {polledImport && <StatusBadge status={polledImport.status} />}
        </div>
      )}

      {/* Step 4: Result */}
      {step === "result" && importResult && (
        <div className="flex flex-col items-center gap-4 py-6">
          {importResult.status === "completed" ? (
            <>
              <CheckCircle2 className="text-status-success h-10 w-10" />
              <p className="text-foreground text-sm font-medium">
                {"Template created successfully!"}
              </p>

              {/* Imported assets */}
              {importResult.assets.length > 0 && (
                <div className="w-full">
                  <h4 className="text-foreground mb-2 text-sm font-medium">{"Imported Assets"}</h4>
                  <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                    {importResult.assets.map((asset) => (
                      <div
                        key={asset.id}
                        className="border-card-border bg-card-bg flex flex-col items-center gap-1 rounded-md border p-2"
                      >
                        <div className="bg-surface-hover h-12 w-12 rounded" />
                        <span className="text-foreground-muted truncate text-xs">
                          {asset.node_name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                {importResult.result_template_id && (
                  <button
                    type="button"
                    onClick={() =>
                      router.push(
                        `/projects/${importResult.project_id}/workspace?template=${importResult.result_template_id}&view=code`,
                      )
                    }
                    className="bg-interactive text-foreground-inverse hover:bg-interactive-hover flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors"
                  >
                    <ExternalLink className="h-4 w-4" />
                    {"Open in Workspace"}
                  </button>
                )}
              </div>
            </>
          ) : (
            <>
              <AlertCircle className="text-status-danger h-10 w-10" />
              <p className="text-foreground text-sm font-medium">
                {`Conversion failed: ${importResult.error_message ?? "Unknown error"}`}
              </p>
              <button
                type="button"
                onClick={() => setStep("review-brief")}
                className="border-border text-foreground hover:bg-surface-hover rounded-md border px-3 py-1.5 text-sm transition-colors"
              >
                {"Try Again"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Extract Components Tab ──

function ExtractComponentsWizard({ connectionId }: { connectionId: number }) {
  const [step, setStep] = useState<ExtractStep>("select-components");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [extractImportId, setExtractImportId] = useState<number | null>(null);
  const [totalComponents, setTotalComponents] = useState(0);
  const router = useRouter();

  const { data: componentList, isLoading } = useDesignComponents(connectionId);
  const { trigger: extractComponents, isMutating: isExtracting } =
    useExtractComponents(connectionId);
  const { data: polledImport } = useDesignImport(
    step === "extracting" ? extractImportId : null,
    true,
  );

  const components = componentList?.components ?? [];

  // Auto-advance when extraction completes
  useEffect(() => {
    if (!polledImport) return;
    if (polledImport.status === "completed" || polledImport.status === "failed") {
      setStep("result");
    }
  }, [polledImport]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleAll = () => {
    if (selectedIds.length === components.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(components.map((c) => c.component_id));
    }
  };

  const handleExtract = async () => {
    try {
      const result = await extractComponents({
        component_ids: selectedIds.length === components.length ? undefined : selectedIds,
        generate_html: true,
      });
      setExtractImportId(result.import_id);
      setTotalComponents(result.total_components);
      setStep("extracting");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Component extraction failed";
      toast.error(message);
    }
  };

  // Step 1: Select Components
  if (step === "select-components") {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="text-foreground-muted h-5 w-5 animate-spin" />
        </div>
      );
    }

    if (components.length === 0) {
      return (
        <div className="border-card-border bg-card-bg rounded-lg border px-4 py-8 text-center">
          <Puzzle className="text-foreground-muted mx-auto mb-2 h-8 w-8" />
          <p className="text-foreground-muted text-sm">{"No pages found in this design file"}</p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-foreground-muted text-sm">{"Select components to extract"}</p>
          <button
            type="button"
            onClick={toggleAll}
            className="text-interactive text-xs font-medium hover:underline"
          >
            {selectedIds.length === components.length ? "Deselect All" : "Select All"}
          </button>
        </div>

        <div className="grid max-h-[20rem] grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3">
          {components.map((comp) => {
            const isSelected = selectedIds.includes(comp.component_id);
            return (
              <button
                key={comp.component_id}
                type="button"
                onClick={() => toggleSelect(comp.component_id)}
                className={`flex flex-col items-center gap-2 rounded-lg border-2 p-3 text-left transition-colors ${
                  isSelected
                    ? "border-interactive bg-interactive/5"
                    : "border-card-border bg-card-bg hover:bg-surface-hover"
                }`}
              >
                {comp.thumbnail_url ? (
                  <img
                    src={comp.thumbnail_url}
                    alt={`Thumbnail for ${comp.name}`}
                    className="border-card-border h-16 w-full rounded border object-contain"
                  />
                ) : (
                  <div className="border-card-border bg-surface-hover flex h-16 w-full items-center justify-center rounded border">
                    <Puzzle className="text-foreground-muted h-6 w-6" />
                  </div>
                )}
                <div className="w-full">
                  <p className="text-foreground truncate text-xs font-medium">{comp.name}</p>
                  {comp.containing_page && (
                    <p className="text-foreground-muted truncate text-xs">{comp.containing_page}</p>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleExtract}
            disabled={selectedIds.length === 0 || isExtracting}
            className="bg-interactive text-foreground-inverse hover:bg-interactive-hover flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {isExtracting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {`Extract Selected (${selectedIds.length})`}
          </button>
        </div>
      </div>
    );
  }

  // Step 2: Extracting
  if (step === "extracting") {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <Loader2 className="text-interactive h-8 w-8 animate-spin" />
        <p className="text-foreground text-sm font-medium">
          {"Extracting components and generating HTML…"}
        </p>
        {polledImport && <StatusBadge status={polledImport.status} />}
      </div>
    );
  }

  // Step 3: Result
  return (
    <div className="flex flex-col items-center gap-4 py-6">
      {polledImport?.status === "failed" ? (
        <>
          <AlertCircle className="text-status-danger h-10 w-10" />
          <p className="text-foreground text-sm font-medium">
            {`Conversion failed: ${polledImport.error_message ?? "Unknown error"}`}
          </p>
          <button
            type="button"
            onClick={() => {
              setStep("select-components");
              setExtractImportId(null);
            }}
            className="border-border text-foreground hover:bg-surface-hover rounded-md border px-3 py-1.5 text-sm transition-colors"
          >
            {"Try Again"}
          </button>
        </>
      ) : (
        <>
          <CheckCircle2 className="text-status-success h-10 w-10" />
          <p className="text-foreground text-sm font-medium">
            {`${totalComponents} components extracted successfully!`}
          </p>
          <button
            type="button"
            onClick={() => router.push("/components")}
            className="bg-interactive text-foreground-inverse hover:bg-interactive-hover flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            {"View in Component Library"}
          </button>
        </>
      )}
    </div>
  );
}

// ── Main Dialog ──

export function DesignImportDialog({
  open,
  onOpenChange,
  connectionId,
  connectionName,
  initialNodeIds = [],
  initialTab = "import",
}: DesignImportDialogProps) {
  const [activeTab, setActiveTab] = useState<ImportTab>(initialTab);

  // Reset tab when dialog opens
  const [prevOpen, setPrevOpen] = useState(false);
  if (open && !prevOpen) {
    setActiveTab(initialTab);
  }
  if (open !== prevOpen) {
    setPrevOpen(open);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[48rem]">
        <DialogHeader>
          <DialogTitle>{`Import from ${connectionName}`}</DialogTitle>
          <DialogDescription className="sr-only">{"Import Design"}</DialogDescription>
        </DialogHeader>

        {/* Tab bar */}
        <div className="border-card-border bg-card-bg flex gap-1 rounded-lg border p-1">
          <button
            type="button"
            onClick={() => setActiveTab("import")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === "import"
                ? "bg-interactive text-foreground-inverse"
                : "text-foreground-muted hover:text-foreground hover:bg-surface-hover"
            }`}
          >
            {"Import Design"}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("components")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === "components"
                ? "bg-interactive text-foreground-inverse"
                : "text-foreground-muted hover:text-foreground hover:bg-surface-hover"
            }`}
          >
            {"Extract Components"}
          </button>
        </div>

        {/* Tab content */}
        <div className="min-h-[20rem]">
          {activeTab === "import" ? (
            <ImportDesignWizard connectionId={connectionId} initialNodeIds={initialNodeIds} />
          ) : (
            <ExtractComponentsWizard connectionId={connectionId} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
