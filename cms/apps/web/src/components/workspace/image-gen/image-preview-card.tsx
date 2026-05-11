"use client";

import { Download, ImagePlus } from "../../icons";
import type { GeneratedImage } from "@/types/image-gen";

interface ImagePreviewCardProps {
  image: GeneratedImage;
  onInsert: (image: GeneratedImage) => void;
}

export function ImagePreviewCard({ image, onInsert }: ImagePreviewCardProps) {
  const createdDate = new Date(image.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  return (
    <div className="border-card-border bg-card-bg group overflow-hidden rounded-md border">
      <img
        src={image.url}
        alt={image.prompt}
        className="aspect-square w-full object-cover"
        loading="lazy"
      />
      <div className="p-2">
        <p className="text-foreground line-clamp-2 text-xs">{image.prompt}</p>
        <div className="text-foreground-muted mt-1 flex items-center justify-between text-xs">
          <span>{createdDate}</span>
          <span>{image.style}</span>
        </div>
        <div className="mt-2 flex gap-1">
          <button
            type="button"
            onClick={() => onInsert(image)}
            className="border-border text-foreground hover:bg-surface-hover flex flex-1 items-center justify-center gap-1 rounded border px-2 py-1 text-xs font-medium transition-colors"
          >
            <ImagePlus className="h-3 w-3" />
            {"Insert"}
          </button>
          <a
            href={image.url}
            download
            className="border-border text-foreground-muted hover:bg-surface-hover flex items-center justify-center rounded border px-2 py-1 text-xs transition-colors"
          >
            <Download className="h-3 w-3" />
          </a>
        </div>
      </div>
    </div>
  );
}
