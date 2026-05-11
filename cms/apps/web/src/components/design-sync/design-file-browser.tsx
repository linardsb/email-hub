"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  ChevronRight,
  ChevronDown,
  FileText,
  Frame,
  Group,
  Component,
  Type,
  Square,
  Loader2,
} from "../icons";
import { useDesignFileStructure } from "@/hooks/use-design-sync";
import type { DesignNode } from "@/types/design-sync";

interface DesignFileBrowserProps {
  connectionId: number;
  selectedNodeIds: string[];
  onSelectionChange: (nodeIds: string[]) => void;
}

const SELECTABLE_TYPES = new Set([
  "FRAME",
  "GROUP",
  "COMPONENT",
  "COMPONENT_SET",
  "INSTANCE",
  "SECTION",
]);

/** Generic Figma node names that carry no semantic meaning */
const GENERIC_NAMES = new Set([
  "mj-wrapper",
  "mj-section",
  "mj-column",
  "mj-body",
  "mj-hero",
  "wrapper",
  "frame",
  "group",
  "section",
  "component",
  "row",
  "container",
]);

/**
 * Infer a meaningful section label for children of an email wrapper frame.
 * Mirrors the backend layout_analyzer classification logic.
 */
function inferSectionLabel(node: DesignNode, index: number, total: number): string | null {
  const rawName = node.name.toLowerCase().trim();
  if (!GENERIC_NAMES.has(rawName) && !rawName.startsWith("frame ")) return null;

  const h = node.height ?? 0;
  if (h <= 30) return "Spacer";
  if (h > 30 && h <= 60) return "Divider";
  if (index === 0) return "Header / Navigation";
  if (index === total - 1) return "Footer";
  if (index === total - 2 && h <= 150) return "Social Links";
  if (index === 1 && h >= 300) return "Hero Section";
  if (h > 60 && h <= 150) return "CTA Module";
  return "Content Module";
}

function getNodeIcon(type: string) {
  switch (type) {
    case "PAGE":
    case "CANVAS":
      return FileText;
    case "FRAME":
    case "SECTION":
      return Frame;
    case "GROUP":
      return Group;
    case "COMPONENT":
    case "COMPONENT_SET":
      return Component;
    case "TEXT":
      return Type;
    default:
      return Square;
  }
}

/** Collect all selectable descendant IDs from a node */
function collectSelectableIds(node: DesignNode): string[] {
  const ids: string[] = [];
  if (SELECTABLE_TYPES.has(node.type)) {
    ids.push(node.id);
  }
  for (const child of node.children) {
    ids.push(...collectSelectableIds(child));
  }
  return ids;
}

interface TreeNodeProps {
  node: DesignNode;
  depth: number;
  selectedIds: Set<string>;
  expandedIds: Set<string>;
  thumbnails: Map<string, string>;
  onToggleExpand: (id: string) => void;
  onToggleSelect: (node: DesignNode) => void;
  /** Index among siblings — used for section label inference */
  siblingIndex?: number;
  /** Total sibling count */
  siblingCount?: number;
}

function TreeNode({
  node,
  depth,
  selectedIds,
  expandedIds,
  thumbnails,
  onToggleExpand,
  onToggleSelect,
  siblingIndex,
  siblingCount,
}: TreeNodeProps) {
  const Icon = getNodeIcon(node.type);
  const hasChildren = node.children.length > 0;
  const isExpanded = expandedIds.has(node.id);
  const isSelectable = SELECTABLE_TYPES.has(node.type);
  const isSelected = selectedIds.has(node.id);
  const isPage = node.type === "PAGE" || node.type === "CANVAS";
  const thumbnail = thumbnails.get(node.id);

  // Infer a meaningful display name for generic section nodes
  const sectionLabel =
    siblingIndex !== undefined && siblingCount !== undefined
      ? inferSectionLabel(node, siblingIndex, siblingCount)
      : null;
  const displayName = sectionLabel ?? node.name;

  // Check partial selection (some children selected, not all)
  const selectableChildren = collectSelectableIds(node);
  const selectedChildCount = selectableChildren.filter((id) => selectedIds.has(id)).length;
  const isIndeterminate =
    !isSelected && selectedChildCount > 0 && selectedChildCount < selectableChildren.length;

  return (
    <div>
      <div
        className="hover:bg-surface-hover flex items-center gap-1.5 rounded-md px-1.5 py-1"
        style={{ paddingLeft: `${depth * 1.25 + 0.375}rem` }}
      >
        {/* Expand/collapse toggle */}
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggleExpand(node.id)}
            className="text-foreground-muted flex h-5 w-5 shrink-0 items-center justify-center"
          >
            {isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <span className="w-5 shrink-0" />
        )}

        {/* Checkbox (only for selectable types) */}
        {isSelectable ? (
          <input
            type="checkbox"
            checked={isSelected}
            ref={(el) => {
              if (el) el.indeterminate = isIndeterminate;
            }}
            onChange={() => onToggleSelect(node)}
            className="border-input-border accent-interactive h-3.5 w-3.5 shrink-0 rounded"
          />
        ) : (
          <span className="w-3.5 shrink-0" />
        )}

        {/* Thumbnail or icon — clicking thumbnail toggles selection */}
        {thumbnail ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (isSelectable) onToggleSelect(node);
            }}
            className={`bg-surface-sunken h-24 w-32 shrink-0 overflow-hidden rounded border-2 transition-colors ${
              isSelected ? "border-interactive" : "border-card-border hover:border-foreground-muted"
            }`}
          >
            <img
              src={thumbnail}
              alt={node.name}
              className="h-full w-full object-cover object-top"
            />
          </button>
        ) : (
          <Icon
            className={`h-4 w-4 shrink-0 ${isPage ? "text-foreground" : "text-foreground-muted"}`}
          />
        )}

        {/* Node name — clickable to expand/collapse */}
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggleExpand(node.id)}
            className={`truncate text-left text-sm ${isPage ? "text-foreground font-medium" : "text-foreground"} hover:underline`}
          >
            {displayName}
          </button>
        ) : (
          <span
            className={`truncate text-sm ${isPage ? "text-foreground font-medium" : "text-foreground"}`}
          >
            {displayName}
          </span>
        )}

        {/* Dimensions */}
        {node.width !== null && node.height !== null && !isPage && (
          <span className="text-foreground-muted shrink-0 text-xs">
            {Math.round(node.width)}&times;{Math.round(node.height)}
          </span>
        )}
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child, idx) => {
            // Pass sibling context so children of email wrappers get section labels
            const isEmailWrapper =
              !isPage &&
              node.children.length >= 2 &&
              (node.height ?? 0) > 500 &&
              (node.width ?? 0) >= 500;
            return (
              <TreeNode
                key={child.id}
                node={child}
                depth={depth + 1}
                selectedIds={selectedIds}
                expandedIds={expandedIds}
                thumbnails={thumbnails}
                onToggleExpand={onToggleExpand}
                onToggleSelect={onToggleSelect}
                siblingIndex={isEmailWrapper ? idx : undefined}
                siblingCount={isEmailWrapper ? node.children.length : undefined}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export function DesignFileBrowser({
  connectionId,
  selectedNodeIds,
  onSelectionChange,
}: DesignFileBrowserProps) {
  const { data: structure, isLoading, error } = useDesignFileStructure(connectionId);

  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const selectedSet = new Set(selectedNodeIds);

  // Thumbnails come directly from the file-structure response (cached during sync)
  const thumbnails = useMemo(() => {
    const map = new Map<string, string>();
    if (structure?.thumbnails) {
      for (const [nodeId, url] of Object.entries(structure.thumbnails)) {
        map.set(nodeId, url);
      }
    }
    return map;
  }, [structure]);

  // Stable ref for use in callbacks (avoids recreating callback on every selection change)
  const selectedNodeIdsRef = useRef(selectedNodeIds);
  selectedNodeIdsRef.current = selectedNodeIds;

  // Pages start collapsed — user expands what they need
  useEffect(() => {
    if (structure?.pages) {
      setExpandedIds(new Set());
    }
  }, [structure]);

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleToggleSelect = useCallback(
    (node: DesignNode) => {
      const currentIds = selectedNodeIdsRef.current;
      const currentSet = new Set(currentIds);
      const descendantIds = collectSelectableIds(node);
      const allSelected = descendantIds.every((id) => currentSet.has(id));

      const next = new Set(currentIds);
      if (allSelected) {
        for (const id of descendantIds) next.delete(id);
      } else {
        for (const id of descendantIds) next.add(id);
      }
      onSelectionChange(Array.from(next));
    },
    [onSelectionChange, selectedNodeIdsRef],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-foreground-muted h-5 w-5 animate-spin" />
        <span className="text-foreground-muted ml-2 text-sm">{"Loading file structure…"}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-card-border bg-card-bg rounded-lg border px-4 py-8 text-center">
        <p className="text-foreground-muted text-sm">{"Failed to load file structure"}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="text-interactive mt-2 text-sm font-medium hover:underline"
        >
          {"Try again"}
        </button>
      </div>
    );
  }

  if (!structure?.pages || structure.pages.length === 0) {
    return (
      <div className="border-card-border bg-card-bg rounded-lg border px-4 py-8 text-center">
        <p className="text-foreground-muted text-sm">{"No pages found in this design file"}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-foreground text-sm font-medium">{"File Structure"}</h3>
        {selectedNodeIds.length > 0 && (
          <span className="text-foreground-muted text-xs">
            {`${selectedNodeIds.length} frames selected`}
          </span>
        )}
      </div>
      <div className="border-card-border bg-card-bg max-h-[24rem] overflow-y-auto rounded-lg border py-1">
        {structure.pages.map((page) => (
          <TreeNode
            key={page.id}
            node={page}
            depth={0}
            selectedIds={selectedSet}
            expandedIds={expandedIds}
            thumbnails={thumbnails}
            onToggleExpand={handleToggleExpand}
            onToggleSelect={handleToggleSelect}
          />
        ))}
      </div>
    </div>
  );
}
