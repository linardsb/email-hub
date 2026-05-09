"use client";

import { useCallback, useState } from "react";
import { Zap, CheckCircle2, XCircle, AlertTriangle, Clock, Ban, RotateCcw } from "../../icons";
import { Badge } from "@email-hub/ui/components/ui/badge";
import { Button } from "@email-hub/ui/components/ui/button";
import { useBlueprintRuns } from "@/hooks/use-blueprint-runs";
import { formatDuration } from "./shared";
import { RunDetailDialog } from "./run-detail-dialog";
import type { BlueprintRunRecord, BlueprintRunsFilter } from "@/types/blueprint-runs";

const FILTER_OPTIONS: { value: BlueprintRunsFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "completed", label: "Completed" },
  { value: "completed_with_warnings", label: "Warnings" },
  { value: "needs_review", label: "Needs Review" },
  { value: "failed", label: "Failed" },
  { value: "cost_cap_exceeded", label: "Cost Cap" },
];

const STATUS_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  completed: CheckCircle2,
  completed_with_warnings: AlertTriangle,
  needs_review: Clock,
  cost_cap_exceeded: Ban,
  failed: XCircle,
  running: Clock,
};

const STATUS_COLOR: Record<string, string> = {
  completed: "text-chart-2",
  completed_with_warnings: "text-accent-foreground",
  needs_review: "text-accent-foreground",
  cost_cap_exceeded: "text-destructive",
  failed: "text-destructive",
  running: "text-muted-foreground",
};

interface BlueprintRunsListProps {
  projectId: number;
  onApplyResult?: (html: string) => void;
  onResumeRun?: (run: BlueprintRunRecord) => void;
}

export function BlueprintRunsList({
  projectId,
  onApplyResult,
  onResumeRun,
}: BlueprintRunsListProps) {
  const [filter, setFilter] = useState<BlueprintRunsFilter>("all");
  const [selectedRun, setSelectedRun] = useState<BlueprintRunRecord | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const { data, isLoading } = useBlueprintRuns(projectId, filter);
  const runs = data?.items ?? [];

  const handleOpenDetail = useCallback((run: BlueprintRunRecord) => {
    setSelectedRun(run);
    setDetailOpen(true);
  }, []);

  return (
    <div className="bg-background flex h-full flex-col">
      {/* Filter bar */}
      <div className="border-border flex scrollbar-none items-center gap-1 overflow-x-auto border-b px-3 py-2">
        {FILTER_OPTIONS.map((opt) => (
          <Button
            key={opt.value}
            variant="ghost"
            size="sm"
            className={`h-7 shrink-0 px-2 text-xs ${
              filter === opt.value ? "bg-accent text-accent-foreground" : ""
            }`}
            onClick={() => setFilter(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {/* Runs list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="border-muted border-t-primary h-5 w-5 animate-spin rounded-full border-2" />
          </div>
        )}

        {!isLoading && runs.length === 0 && (
          <div className="text-muted-foreground flex flex-col items-center justify-center gap-2 py-8">
            <Zap className="h-5 w-5" />
            <p className="text-sm">
              {"No blueprint runs yet. Run a pipeline to see history here."}
            </p>
          </div>
        )}

        {!isLoading && runs.length > 0 && (
          <div className="divide-border divide-y">
            {runs.map((run) => {
              const Icon = STATUS_ICON[run.status] ?? Clock;
              const colorClass = STATUS_COLOR[run.status] ?? "text-muted-foreground";
              const date = new Date(run.created_at);
              const timeAgo = formatRelativeTime(date);
              const isResumable =
                (run.status === "failed" || run.status === "cost_cap_exceeded") &&
                run.checkpoint_count > 0;

              return (
                <button
                  key={run.id}
                  type="button"
                  onClick={() => handleOpenDetail(run)}
                  className="hover:bg-accent/50 flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors"
                >
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${colorClass}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground truncate text-sm font-medium">
                      {run.brief_excerpt}
                    </p>
                    <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-2 text-xs">
                      <span>{timeAgo}</span>
                      <span>·</span>
                      <span>{formatDuration(run.duration_ms)}</span>
                      <span>·</span>
                      <span>{`${run.total_tokens.toLocaleString()} tokens`}</span>
                      {run.qa_passed === true && (
                        <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                          {"QA Pass"}
                        </Badge>
                      )}
                      {run.qa_passed === false && (
                        <Badge variant="destructive" className="px-1.5 py-0 text-[10px]">
                          {"QA Fail"}
                        </Badge>
                      )}
                      {run.resumed_from && (
                        <Badge
                          variant="outline"
                          className="border-primary/50 text-primary px-1.5 py-0 text-[10px]"
                        >
                          {"Resumed"}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {isResumable && onResumeRun && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 shrink-0 px-2 text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        onResumeRun(run);
                      }}
                    >
                      <RotateCcw className="mr-1 h-3 w-3" />
                      {"Resume"}
                    </Button>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <RunDetailDialog
        run={selectedRun}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onApplyResult={onApplyResult}
        onResumeRun={onResumeRun}
      />
    </div>
  );
}

function formatRelativeTime(date: Date): string {
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}
