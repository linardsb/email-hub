"use client";

import { useEffect, useCallback, useRef } from "react";
import type { LiquidBlock, LiquidBlockType } from "@/types/liquid-builder";
import { useLiquidBuilder } from "@/hooks/use-liquid-builder";
import { serializeLiquid } from "@/lib/liquid/serializer";
import { BlockPalette } from "./block-palette";
import { BlockCanvas } from "./block-canvas";
import { LiquidPreview } from "./liquid-preview";

interface LiquidBuilderPanelProps {
  code: string;
  onCodeChange: (code: string) => void;
}

export function LiquidBuilderPanel({ code, onCodeChange }: LiquidBuilderPanelProps) {
  const { blocks, parseFromCode, updateBlock, removeBlock, addBlock, moveBlock } =
    useLiquidBuilder(code);

  const isInternalUpdate = useRef(false);

  // Sync from code when code prop changes externally
  useEffect(() => {
    if (!isInternalUpdate.current) {
      parseFromCode(code);
    }
    isInternalUpdate.current = false;
  }, [code, parseFromCode]);

  // When blocks change, serialize back to code
  const handleBlockUpdate = useCallback(
    (id: string, updates: Partial<LiquidBlock>) => {
      updateBlock(id, (block) => ({ ...block, ...updates }) as LiquidBlock);
    },
    [updateBlock],
  );

  const handleAddBlock = useCallback(
    (type: LiquidBlockType) => {
      addBlock(type);
    },
    [addBlock],
  );

  // Sync blocks → code when blocks change
  useEffect(() => {
    const serialized = serializeLiquid(blocks);
    if (serialized !== code) {
      isInternalUpdate.current = true;
      onCodeChange(serialized);
    }
  }, [blocks]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 overflow-hidden">
        {/* Palette sidebar */}
        <div className="border-default bg-surface w-36 flex-shrink-0 overflow-y-auto border-r">
          <BlockPalette onAddBlock={handleAddBlock} />
        </div>

        {/* Main canvas */}
        <div className="flex flex-1 flex-col">
          <BlockCanvas
            blocks={blocks}
            onMove={moveBlock}
            onUpdate={handleBlockUpdate}
            onRemove={removeBlock}
          />

          {/* Preview */}
          <div className="h-1/3 min-h-32 flex-shrink-0">
            <LiquidPreview code={code} />
          </div>
        </div>
      </div>
    </div>
  );
}
