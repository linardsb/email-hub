"use client";

import { forwardRef, useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, FileCode, Loader2 } from "../icons";
import type { CodeEditorHandle } from "@/hooks/use-editor-bridge";
import type { SaveStatus } from "./save-indicator";
import type { BrandConfig } from "@/types/brand";
import type { Doc as YDoc } from "yjs";
import type { Awareness } from "y-protocols/awareness";
import { useBuilderSync } from "@/hooks/use-builder-sync";
import { ViewSwitcher, type ViewMode } from "./view-switcher";
import { ImportDialog } from "@/components/builder/import-dialog";

const CodeEditor = dynamic(
  () => import("@/components/workspace/editor/code-editor").then((mod) => mod.CodeEditor),
  {
    ssr: false,
    loading: () => <EditorLoading />,
  },
);

const VisualBuilderPanel = dynamic(
  () => import("@/components/builder/visual-builder-panel").then((mod) => mod.VisualBuilderPanel),
  {
    ssr: false,
    loading: () => <EditorLoading />,
  },
);

function EditorLoading() {
  return (
    <div className="bg-background flex h-full items-center justify-center">
      <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
      <span className="text-muted-foreground ml-2 text-sm">{"Loading editor..."}</span>
    </div>
  );
}

type EditorTab = ViewMode;

interface EditorPanelProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  saveStatus?: SaveStatus;
  readOnly?: boolean;
  brandConfig?: BrandConfig | null;
  onBrandViolationsChange?: (count: number) => void;
  onCursorOffsetChange?: (offset: number) => void;
  onSelectionChange?: (hasSelection: boolean) => void;
  collaborative?: {
    doc: YDoc;
    awareness: Awareness;
    user: { name: string; color: string; role: string };
    fieldName?: string;
  };
  projectId?: number;
  onViewChange?: (view: ViewMode) => void;
  /** When set, overrides localStorage-persisted view for this mount (e.g. from ?view=code) */
  initialView?: ViewMode;
  /** Builder-specific callbacks passed through to VisualBuilderPanel */
  builderProps?: {
    onRunQA?: () => void;
    isRunningQA?: boolean;
    onAISuggest?: () => void;
    onCopyHtml?: () => void;
    onDownloadHtml?: () => void;
    onPushToESP?: () => void;
    onHighlightSection?: (sectionId: string) => void;
  };
}

export const EditorPanel = forwardRef<CodeEditorHandle, EditorPanelProps>(function EditorPanel(
  {
    value,
    onChange,
    onSave,
    saveStatus,
    readOnly,
    brandConfig,
    onBrandViolationsChange,
    onCursorOffsetChange,
    onSelectionChange,
    collaborative,
    projectId,
    onViewChange,
    initialView,
    builderProps,
  }: EditorPanelProps,
  ref,
) {
  // Persist view mode per project in localStorage.
  // initialView prop (from ?view= query param) takes precedence over stored value.
  const storageKey = projectId ? `editor-view-${projectId}` : null;
  const [activeTab, setActiveTab] = useState<EditorTab>(() => {
    if (initialView) return initialView;
    if (typeof window === "undefined" || !storageKey) return "code";
    const stored = localStorage.getItem(storageKey);
    if (stored === "code" || stored === "builder" || stored === "split") return stored;
    return "code";
  });

  useEffect(() => {
    if (storageKey) localStorage.setItem(storageKey, activeTab);
  }, [activeTab, storageKey]);

  const handleTabChange = useCallback(
    (tab: EditorTab) => {
      setActiveTab(tab);
      onViewChange?.(tab);
    },
    [onViewChange],
  );

  // Import HTML dialog (available in code mode)
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const handleImportAccept = useCallback(
    (annotatedHtml: string) => {
      onChange(annotatedHtml);
    },
    [onChange],
  );

  // Sync engine — only active in split mode
  const isSplit = activeTab === "split";
  const {
    syncStatus,
    parseError,
    handleCodeChange: syncCodeChange,
    parsedSections,
    serializedHtml,
    dismissParseError,
  } = useBuilderSync({ enabled: isSplit });

  // When entering split mode, seed the sync engine with current content
  // so it captures the template shell and parses initial sections
  useEffect(() => {
    if (isSplit && value) {
      syncCodeChange(value);
    }
  }, [isSplit]);

  // When sync engine produces new HTML from builder changes, push to parent
  useEffect(() => {
    if (serializedHtml !== null && isSplit) {
      onChange(serializedHtml);
    }
  }, [serializedHtml, isSplit, onChange]);

  // Wrap onChange to also feed sync engine in split mode
  const handleSyncedCodeChange = useCallback(
    (html: string) => {
      onChange(html);
      if (isSplit) syncCodeChange(html);
    },
    [onChange, isSplit, syncCodeChange],
  );

  // Builder code change handler — HTML flows to parent in all modes.
  // In split mode, code→builder direction uses the sync engine (parsedSections).
  // Builder→code uses the HTML path (useBuilderPreview is higher fidelity).
  const handleSyncedBuilderChange = useCallback(
    (html: string) => {
      onChange(html);
    },
    [onChange],
  );

  return (
    <div className="bg-background flex h-full flex-col overflow-hidden">
      {/* View switcher + Import HTML */}
      <div className="border-default bg-surface flex items-center justify-between border-b">
        <ViewSwitcher
          activeView={activeTab}
          onViewChange={handleTabChange}
          syncStatus={isSplit ? syncStatus : undefined}
        />
        {activeTab === "code" && !readOnly && (
          <button
            type="button"
            onClick={() => setImportDialogOpen(true)}
            className="border-input text-muted-foreground hover:bg-accent hover:text-foreground mr-2 flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium"
            title="Import HTML email"
          >
            <FileCode className="h-3.5 w-3.5" />
            <span>Import HTML</span>
          </button>
        )}
      </div>

      {/* Parse error banner (split mode) */}
      {isSplit && parseError && (
        <div className="border-border bg-muted text-muted-foreground flex items-center gap-2 border-b px-3 py-1.5 text-xs">
          <AlertTriangle className="text-destructive h-3.5 w-3.5 flex-shrink-0" />
          <span className="flex-1">{parseError}</span>
          <button
            type="button"
            onClick={dismissParseError}
            className="text-muted-foreground hover:text-foreground text-xs underline"
          >
            {"Dismiss"}
          </button>
        </div>
      )}

      {/* Panel content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "code" && (
          <CodeEditor
            ref={ref}
            value={value}
            onChange={onChange}
            onSave={onSave}
            saveStatus={saveStatus}
            readOnly={readOnly}
            brandConfig={brandConfig}
            onBrandViolationsChange={onBrandViolationsChange}
            onCursorOffsetChange={onCursorOffsetChange}
            onSelectionChange={onSelectionChange}
            collaborative={collaborative}
          />
        )}

        {activeTab === "builder" && (
          <VisualBuilderPanel
            code={value}
            onCodeChange={onChange}
            projectId={projectId}
            onRunQA={builderProps?.onRunQA}
            isRunningQA={builderProps?.isRunningQA}
            onAISuggest={builderProps?.onAISuggest}
            onCopyHtml={builderProps?.onCopyHtml}
            onDownloadHtml={builderProps?.onDownloadHtml}
            onPushToESP={builderProps?.onPushToESP}
            onHighlightSection={builderProps?.onHighlightSection}
          />
        )}

        {activeTab === "split" && (
          <div className="flex h-full overflow-hidden">
            <div className="border-default w-1/2 overflow-hidden border-r">
              <CodeEditor
                ref={ref}
                value={value}
                onChange={handleSyncedCodeChange}
                onSave={onSave}
                saveStatus={saveStatus}
                readOnly={readOnly}
                brandConfig={brandConfig}
                onBrandViolationsChange={onBrandViolationsChange}
                onCursorOffsetChange={onCursorOffsetChange}
                onSelectionChange={onSelectionChange}
                collaborative={undefined /* collab disabled in split — sync engine manages state */}
              />
            </div>
            <div className="w-1/2 overflow-hidden">
              <VisualBuilderPanel
                code={value}
                onCodeChange={handleSyncedBuilderChange}
                projectId={projectId}
                syncedSections={parsedSections}
                /* onSectionsChange not wired — builder→code flows via
                   useBuilderPreview HTML (higher fidelity than sync engine's sectionsToHtml) */
                onRunQA={builderProps?.onRunQA}
                isRunningQA={builderProps?.isRunningQA}
                onAISuggest={builderProps?.onAISuggest}
                onCopyHtml={builderProps?.onCopyHtml}
                onDownloadHtml={builderProps?.onDownloadHtml}
                onPushToESP={builderProps?.onPushToESP}
                onHighlightSection={builderProps?.onHighlightSection}
              />
            </div>
          </div>
        )}
      </div>

      {/* Import HTML dialog */}
      <ImportDialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        onAccept={handleImportAccept}
      />
    </div>
  );
});
