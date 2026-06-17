# Visual Email Builder (`components/builder/`)

Drag-and-drop email builder using the component library. Phase 24.4 property panels (24.5), bidirectional sync (24.6).

## Architecture

**Bidirectional data flow:** Palette → Canvas → HTML output (builder→code). Code editor → parser → sections (code→builder). Split view shows both simultaneously with debounced sync (500ms code→builder, 200ms builder→code, builder wins on conflict).

**Property panels:** Right sidebar (w-80) appears when a section is selected. Four tabs: Content (slot editing), Style (design token overrides), Responsive (mobile behavior), Advanced (MSO, dark mode, HTML attributes). Changes are live — no Apply button.

## Components

- `visual-builder-panel.tsx` — Top-level panel with palette, canvas, preview, and conditional property panel. Accepts `syncedSections` prop for split-mode sync and `templateShell` for structure-aware assembly.
- `component-palette.tsx` — Left sidebar with searchable/filterable component library, drag sources
- `builder-canvas.tsx` — Central drop zone with sortable sections and drop zones between them
- `section-wrapper.tsx` — Per-section selection UI, drag handle, duplicate/delete actions
- `builder-preview.tsx` — Sandboxed iframe preview of assembled email HTML
- `drag-drop-context.tsx` — @dnd-kit DndContext + SortableContext wrapper
- `zoom-controls.tsx` — Preview zoom controls (50%–125%)

### `panels/` — Property panel components (Phase 24.5)

- `property-panel.tsx` — Container: header + Radix Tabs + ScrollArea
- `content-tab.tsx` — Dynamic slot editors driven by `slotDefinitions`
- `style-tab.tsx` — Color overrides (palette picker), font/size selectors, spacing, alignment
- `responsive-tab.tsx` — Mobile behavior toggles, preview mode switch
- `advanced-tab.tsx` — CSS class, MSO conditional, dark mode overrides, HTML attributes, View Source
- `slot-editor.tsx` — Generic input renderer (maps slot_type → control)
- `palette-color-picker.tsx` — Reusable palette-restricted color picker (Popover + swatch grid)

## Sync Library (`lib/builder-sync/`) — Phase 24.6

- `ast-mapper.ts` — HTML↔section parser: Strategy 1 (annotated `data-section-id`) + Strategy 2 (structural content-root analysis with `findContentRoot` deep unwrap). ESP token preservation (Liquid/Handlebars/AMPscript/ERB). `internalizeStructuralEsp()` moves conditionals from around `<tr>` into `<td>`. `isColumnGroup()` dynamic column detection. `sectionsToHtml()` DOM-based serialization.
- `sync-engine.ts` — `BuilderSyncEngine` debounced bidirectional sync with conflict resolution. Template shell captured on successful parse only.
- `section-markers.ts` — `stripAnnotations()` removes `data-section-id`/`data-slot-name`/`data-component-id`/`data-component-name`. `hasAnnotations()` detects annotated HTML.
- `index.ts` — barrel export

## Hooks

- `use-builder.ts` — `useBuilderState()` reducer with undo/redo + `setSections()`, `useBuilderPreview()` structure-preserving HTML assembler with slot fills, 13-token CSS overrides, dark mode CSS, MSO ghost tables, scoped section CSS, `createSectionDefaults()`
- `use-builder-sync.ts` — `useBuilderSync()` React hook wrapping `BuilderSyncEngine` with status/error state, parsed sections, serialized HTML

## Types

- `types/visual-builder.ts` — BuilderSection, BuilderState, BuilderAction, PaletteItem, SlotDefinition, DefaultTokens, ResponsiveOverrides (mobileHide, mobilePaddingOverride, mobileTextAlign), AdvancedConfig, SectionNode (with precedingContent), SectionDiff, SyncStatus
- `types/design-system-config.ts` — DesignSystemConfig, extractPaletteSwatches()

## Security

- All `dangerouslySetInnerHTML` uses DOMPurify sanitization
- Preview iframe uses `sandbox=""` (no script execution)
- API calls use `authFetch`
- Color picker restricted to design system palette (no freeform hex)
- HTML attributes: `on*` blocked, `javascript:`/`data:`/`vbscript:` URIs blocked, `style` blocked
- CSS class validated against `/^[a-zA-Z_-][\w-]*$/`
- CSS values sanitized: `expression()`, `behavior:`, dangerous URI schemes blocked
- Responsive CSS: section IDs sanitized for selector injection, `mobileFontSize` sanitized
- ESP tokens treated as opaque strings — never evaluated or executed
- `stripAnnotations()` removes all builder metadata before export
