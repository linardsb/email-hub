# Plan: 31.5 Preview Iframe Dark Mode Text Safety & Sandbox Fix

## Context

When preview iframe dark mode is enabled, it injects `body { background-color: #121212 !important; }` and triggers `@media (prefers-color-scheme: dark)` rules. Elements without corresponding dark-text overrides keep their original dark inline colors (e.g., `color:#101828` nav links), becoming invisible on the dark background.

The sandbox attribute was already relaxed to `allow-same-origin` in a prior change. This plan addresses the remaining dark mode contrast safety issue plus applies the sandbox fix to the other 5 preview iframes that still use `sandbox=""`.

## Current State

- `preview-iframe.tsx`: `sandbox="allow-same-origin"` (already done), no contrast safety
- `component-preview.tsx`: `sandbox=""`, same dark mode injection, no contrast safety
- `approval-preview.tsx`: `sandbox=""`, similar dark mode injection, no contrast safety
- `builder-preview.tsx`, `LocalePreview.tsx`, `version-compare-dialog.tsx`, `esp-template-preview-dialog.tsx`, `ReportPanel.tsx`: `sandbox=""`, no dark mode
- `color-utils.ts`: has `hexToRgb()` but no luminance/contrast utilities

## Files to Create/Modify

1. `cms/apps/web/src/lib/color-utils.ts` — add `relativeLuminance()` and `isDarkColor()` utilities
2. `cms/apps/web/src/components/workspace/preview-iframe.tsx` — add dark mode contrast safety
3. `cms/apps/web/src/components/components/component-preview.tsx` — add `allow-same-origin` to sandbox
4. `cms/apps/web/src/components/approvals/approval-preview.tsx` — add `allow-same-origin` to sandbox

## Implementation Steps

### Step 1: Add luminance utilities to `color-utils.ts`

Add two new exported functions after `colorDistance()` (after line 45):

```typescript
/**
 * WCAG 2.1 relative luminance (0 = black, 1 = white).
 * Accepts 3-digit or 6-digit hex with optional leading #.
 */
export function relativeLuminance(hex: string): number {
  const rgb = hexToRgb(normalizeHex(hex));
  if (!rgb) return 0;
  const [rs, gs, bs] = [rgb.r / 255, rgb.g / 255, rgb.b / 255].map((c) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * rs! + 0.7152 * gs! + 0.0722 * bs!;
}

/** True when the color would be hard to read on a dark (#121212) background. */
export function isDarkColor(hex: string): boolean {
  return relativeLuminance(hex) < 0.3;
}
```

Also add a helper (before `relativeLuminance`) to normalize 3-digit hex to 6-digit:

```typescript
/** Normalize 3-digit hex to 6-digit (e.g. #abc -> #aabbcc). */
function normalizeHex(hex: string): string {
  const h = hex.replace(/^#/, "");
  if (h.length === 3) {
    return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
  }
  return `#${h}`;
}
```

### Step 2: Add `ensureDarkModeContrast()` to `preview-iframe.tsx`

Add imports at top:

```typescript
import { isDarkColor } from "@/lib/color-utils";
```

Add the contrast-safety function before the component:

```typescript
const DARK_FALLBACK_TEXT = "#e5e5e5";
const DARK_FALLBACK_LINK = "#93c5fd";

/**
 * Scan inline style color values; replace dark-on-dark text with light fallbacks.
 * Only runs when dark mode preview is active. Operates on the already-sanitised
 * compiled HTML — no script injection risk.
 */
function ensureDarkModeContrast(html: string): string {
  return html.replace(
    /(<(?:td|a|span|p|h[1-6]|li|div)\b[^>]*style="[^"]*)(color:\s*#([0-9a-fA-F]{3,6}))([^"]*")/gi,
    (match, before: string, colorDecl: string, hex: string, after: string) => {
      if (!isDarkColor(hex)) return match;
      // Determine fallback: links get blue, everything else gets light gray
      const isLink = before.trimStart().startsWith("<a");
      const fallback = isLink ? DARK_FALLBACK_LINK : DARK_FALLBACK_TEXT;
      return `${before}${colorDecl}${after.replace(/"$/, `; --orig-color: #${hex}" data-dark-adjusted="1"`)}`.replace(
        colorDecl,
        `color: ${fallback} !important`,
      );
    },
  );
}
```

**Wait — the above regex replacement is getting complex.** Simpler approach that's easier to reason about:

```typescript
/**
 * When dark mode preview is active, replace dark inline text colors with
 * readable light alternatives. Only touches `color:` in style attributes
 * on text-bearing elements. Operates on sanitised compiled HTML.
 */
function ensureDarkModeContrast(html: string): string {
  // Match style attributes containing a color declaration with a hex value
  return html.replace(
    /style="([^"]*?)color:\s*#([0-9a-fA-F]{3,6})([^"]*)"/gi,
    (match, pre: string, hex: string, post: string) => {
      if (!isDarkColor(hex)) return match;
      const fallback = DARK_FALLBACK_TEXT;
      return `style="${pre}color: ${fallback} !important${post}"`;
    },
  );
}
```

This is cleaner — it finds any `style="...color:#XXYYZZ..."` and if the hex is dark (luminance < 0.3), replaces it with the light fallback. The `!important` ensures it wins over other declarations in the same style attribute.

### Step 3: Inject contrast safety in `useMemo`

Modify the existing `useMemo` in `PreviewIframe`:

```typescript
const srcdoc = useMemo(() => {
  if (!compiledHtml) return null;
  if (!darkMode) return compiledHtml;

  // Fix dark-on-dark text visibility before injecting dark mode styles
  const safeHtml = ensureDarkModeContrast(compiledHtml);

  // Inject dark mode meta + style to trigger @media (prefers-color-scheme: dark) in email HTML
  if (safeHtml.includes("</head>")) {
    return safeHtml.replace(
      "</head>",
      `${DARK_MODE_META}\n${DARK_MODE_STYLE}\n</head>`,
    );
  }
  if (safeHtml.includes("<head>")) {
    return safeHtml.replace(
      "<head>",
      `<head>\n${DARK_MODE_META}\n${DARK_MODE_STYLE}`,
    );
  }
  return `${DARK_MODE_META}\n${DARK_MODE_STYLE}\n${safeHtml}`;
}, [compiledHtml, darkMode]);
```

### Step 4: Relax sandbox on other preview iframes

In `component-preview.tsx` and `approval-preview.tsx`, change:
```
sandbox=""
```
to:
```
sandbox="allow-same-origin"
```

This enables reliable cross-origin image loading while still blocking scripts, forms, popups, and navigation. `allow-same-origin` without `allow-scripts` is safe — no script execution means same-origin cannot be exploited.

Do NOT change `builder-preview.tsx` — the builder preview renders user-edited HTML in real-time and should remain maximally sandboxed. `LocalePreview.tsx`, `version-compare-dialog.tsx`, `esp-template-preview-dialog.tsx`, and `ReportPanel.tsx` also remain `sandbox=""` since they don't need image loading from external CDNs.

### Step 5: Add tests

Add a test file `cms/apps/web/src/lib/__tests__/color-utils.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { relativeLuminance, isDarkColor, hexToRgb } from "../color-utils";

describe("relativeLuminance", () => {
  it("returns ~0 for black", () => {
    expect(relativeLuminance("#000000")).toBeCloseTo(0, 3);
  });

  it("returns ~1 for white", () => {
    expect(relativeLuminance("#ffffff")).toBeCloseTo(1, 3);
  });

  it("handles 3-digit hex", () => {
    expect(relativeLuminance("#fff")).toBeCloseTo(1, 3);
  });

  it("returns low luminance for dark gray", () => {
    expect(relativeLuminance("#101828")).toBeLessThan(0.05);
  });

  it("returns mid luminance for medium gray", () => {
    const lum = relativeLuminance("#808080");
    expect(lum).toBeGreaterThan(0.15);
    expect(lum).toBeLessThan(0.25);
  });
});

describe("isDarkColor", () => {
  it("dark colors return true", () => {
    expect(isDarkColor("#000000")).toBe(true);
    expect(isDarkColor("#101828")).toBe(true);
    expect(isDarkColor("#1a1a2e")).toBe(true);
  });

  it("light colors return false", () => {
    expect(isDarkColor("#ffffff")).toBe(false);
    expect(isDarkColor("#e5e5e5")).toBe(false);
    expect(isDarkColor("#93c5fd")).toBe(false);
  });
});
```

Add a test for the contrast function in `cms/apps/web/src/components/workspace/__tests__/preview-iframe.test.tsx`:

```typescript
import { describe, expect, it } from "vitest";

// We'll need to export ensureDarkModeContrast or test via the component
// For unit testing, extract the function to a shared utility if preferred.
// For now, test via the rendered component behavior.

describe("PreviewIframe dark mode contrast", () => {
  it("replaces dark inline colors with light fallback", () => {
    // Import the utility (after it's exported for testing)
    const { ensureDarkModeContrast } = require("../preview-iframe");
    const input = `<td style="color:#101828; font-size:14px">Nav</td>`;
    const output = ensureDarkModeContrast(input);
    expect(output).toContain("color: #e5e5e5 !important");
    expect(output).not.toContain("#101828");
  });

  it("preserves light inline colors", () => {
    const { ensureDarkModeContrast } = require("../preview-iframe");
    const input = `<td style="color:#ffffff; font-size:14px">Nav</td>`;
    const output = ensureDarkModeContrast(input);
    expect(output).toContain("#ffffff");
  });
});
```

**Note:** To make `ensureDarkModeContrast` testable, export it from `preview-iframe.tsx` with a named export (the component is the default/named export already, so adding another named export is fine). Alternatively, extract to `lib/dark-mode-contrast.ts` if preferred.

Better approach: extract `ensureDarkModeContrast` into `cms/apps/web/src/lib/dark-mode-contrast.ts` as a standalone pure function, import it into `preview-iframe.tsx`. This keeps the component slim and the function independently testable.

### Step 5b (revised): Extract to separate utility file

Create `cms/apps/web/src/lib/dark-mode-contrast.ts`:

```typescript
import { isDarkColor } from "./color-utils";

const DARK_FALLBACK_TEXT = "#e5e5e5";

/**
 * When dark mode preview is active, replace dark inline text colors with
 * readable light alternatives. Only touches color declarations in style
 * attributes. Operates on already-sanitised compiled HTML.
 */
export function ensureDarkModeContrast(html: string): string {
  return html.replace(
    /style="([^"]*?)color:\s*#([0-9a-fA-F]{3,6})([^"]*)"/gi,
    (match, pre: string, hex: string, post: string) => {
      if (!isDarkColor(hex)) return match;
      return `style="${pre}color: ${DARK_FALLBACK_TEXT} !important${post}"`;
    },
  );
}
```

Then in `preview-iframe.tsx`:
```typescript
import { ensureDarkModeContrast } from "@/lib/dark-mode-contrast";
```

And test file becomes `cms/apps/web/src/lib/__tests__/dark-mode-contrast.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { ensureDarkModeContrast } from "../dark-mode-contrast";

describe("ensureDarkModeContrast", () => {
  it("replaces dark inline colors with light fallback", () => {
    const input = `<td style="color:#101828; font-size:14px">Nav link</td>`;
    const result = ensureDarkModeContrast(input);
    expect(result).toContain("color: #e5e5e5 !important");
    expect(result).not.toContain("#101828");
  });

  it("preserves light inline colors", () => {
    const input = `<td style="color:#ffffff; font-size:14px">White text</td>`;
    const result = ensureDarkModeContrast(input);
    expect(result).toContain("#ffffff");
    expect(result).not.toContain("!important");
  });

  it("handles 3-digit hex colors", () => {
    const input = `<td style="color:#111">Dark</td>`;
    const result = ensureDarkModeContrast(input);
    expect(result).toContain("#e5e5e5 !important");
  });

  it("handles multiple color declarations", () => {
    const input = `
      <td style="color:#101828">Dark nav</td>
      <td style="color:#e5e5e5">Light text</td>
      <a style="color:#0f172a">Dark link</a>
    `;
    const result = ensureDarkModeContrast(input);
    expect(result).not.toContain("#101828");
    expect(result).not.toContain("#0f172a");
    expect(result).toContain("#e5e5e5"); // original light text preserved
  });

  it("does not modify HTML without inline color styles", () => {
    const input = `<td class="nav-link">Plain</td>`;
    const result = ensureDarkModeContrast(input);
    expect(result).toBe(input);
  });

  it("preserves other style properties", () => {
    const input = `<td style="font-size:14px; color:#101828; padding:10px">Text</td>`;
    const result = ensureDarkModeContrast(input);
    expect(result).toContain("font-size:14px");
    expect(result).toContain("padding:10px");
  });
});
```

## Security Checklist

- **No new endpoints** — this is a frontend-only change
- **Sandbox relaxation:** `allow-same-origin` without `allow-scripts` is safe per HTML spec. The iframe content cannot execute JavaScript, so same-origin access cannot be exploited for XSS or data exfiltration
- **Contrast fix regex** operates on already-XSS-sanitised compiled HTML (output of Maizzle build pipeline). No script injection vector — it only modifies inline CSS `color` values
- **No `dangerouslySetInnerHTML`** — uses `srcDoc` which is the existing pattern
- **No user input flows** into the regex replacement — input is compiled template HTML from the backend

## Verification

- [ ] `make check-fe` passes (lint + types + unit tests)
- [ ] Import email with dark nav links (`color:#101828`) + dark mode sections, toggle dark mode → nav links remain readable (light color applied)
- [ ] Toggle dark mode off → original colors restored (the replacement only runs in the `useMemo` when `darkMode` is true)
- [ ] External placeholder images (`placehold.co`, `via.placeholder.com`) load in preview iframe
- [ ] Sandbox still blocks JavaScript: `<script>alert(1)</script>` in HTML produces no alert
- [ ] Component preview and approval preview images load correctly with relaxed sandbox
- [ ] New unit tests pass: `relativeLuminance`, `isDarkColor`, `ensureDarkModeContrast`
