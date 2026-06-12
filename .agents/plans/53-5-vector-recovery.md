# 53.5 — Decorative vector recovery

> Standalone VECTOR/LINE nodes fall through extraction and vanish from output (icons,
> dividers, vector logomarks). Fork (a) scoped; zero document-model change needed.

## Current facts (verified 2026-06-12)

- Fall-through: `_walk_for_images` (`layout_analyzer.py:1223-1278`) handles IMAGE,
  FRAME+image_ref, FRAME-wrapping-single-IMAGE; every other type hits the bare-recurse
  `else` (`:1276-1278`). All of RECTANGLE/ELLIPSE/LINE/VECTOR/BOOLEAN_OPERATION/STAR map to
  `DesignNodeType.VECTOR` (`service.py:67-83`) and ARE preserved on the parsed tree with
  fill/stroke/bbox/opacity (`protocol.py:110-159`; `_parse_node` keeps all children).
- Export path renders ANY node: `export_images` (`service.py:1685-1765`, `/v1/images`,
  batches of 100) — precedent for non-IMAGE-as-image already exists (frame-wrapping-image
  `export_node_id`, `layout_analyzer.py:1254-1275`; button icon detection accepts VECTOR
  `:1365-1378`).
- `DocumentImage` needs **zero new fields** (reuse `node_id/export_node_id/width/height`).
  Known pre-existing schema gap: `stroke_color`/`stroke_weight` exist on `DocumentImage` but
  not in `email-design-document-v1.json` (strict `additionalProperties:false`) — 52.5
  leftover, fix alongside (same family as `phase-53.7-typography-maxitems-cap`).
- **Fixture reality:** cases 5-10 contain exactly 9 standalone vectors — ALL zero-height
  `mj-divider` LINEs (5:2, 8:1, 9:2, 10:2; cases 6/7 none). No icon/logomark vectors exist
  in the corpus, so the regression suite can only see the divider half.

## Implementation

### 1. Split by area — two different recoveries

In `_walk_for_images` (or a sibling `_walk_for_vectors` feeding the same results), dispatch
`node.type == DesignNodeType.VECTOR`:

- **Zero-area lines (height or width ≈ 0, the `mj-divider` shape):** do NOT rasterize a
  0-px PNG. Recovery = make the parent divider section render a real rule: verify the
  divider seed emits a visible line (`border-top` on a `<td>`) and thread the LINE node's
  `stroke_color`/`stroke_weight` (already parsed, 52.5) into a `_divider` token override
  (color + thickness). If baselines already show a visible divider, this half reduces to
  color/weight fidelity.
- **Non-zero-area vectors (icons, logomarks):** emit
  `ImagePlaceholder(node_id=node.id, export_node_id=node.id, width, height)` — the Figma
  image API rasterizes the vector; everything downstream (asset export, `_resolve_image_url`,
  alt derivation via `_derive_image_alt`) already works. Guard: skip vectors that are
  children of an already-imaged FRAME (avoid double capture); skip < 8×8 px artifacts.

### 2. Size/role guards

- Icon-sized vectors (≤ 64×64, matching the button-icon precedent `:1365-1378`) keep their
  natural size; larger vector art is capped by the existing asset resize path
  (`assets.py:134`).
- Decorative default: `alt=""` is forbidden by G3-neg — route through `_derive_image_alt`
  (multi-word fallback), consistent with B5. TIER-2 semantic-alt stays the separate RC-E
  item (`phase-53-b5-decorative-empty-alt-vs-g3neg` history).

### 3. Tests

- Unit fixtures (synthetic `DesignNode` trees) for: icon-sized vector → ImagePlaceholder
  with `export_node_id`; zero-height LINE → no ImagePlaceholder + divider override emitted;
  vector inside imaged frame → skipped. **This is the only coverage for the icon half** —
  the corpus has none (state this in the test docstring, don't pretend otherwise).
- Divider half: cases 5/8/9/10 baselines — regen + diff audit; expect divider color/weight
  changes only.

## Out of scope

- Inline SVG output (email clients strip it — ceiling doc §2 already documents
  rasterize-only).
- Vector subtree composition (BOOLEAN_OPERATION groups render fine via the node export —
  the API composites them).

## Verify

Ladder counts unchanged; baseline diff audit divider-only; new unit tests green; A3 advisory
delta recorded; `make types` + design_sync suite + golden-conformance green.

## Deferred-items touching this plan

- `phase-53.7-asset-reexport-prerequisite` — vector PNGs join the gitignored-assets class;
  fixture regen requires `scripts/export-case-assets.py` + `FIGMA_TOKEN`.
- Schema strictness gap (`stroke_*` on DocumentImage) — fix here or as its own ledger entry;
  do not leave `to_json` emitting fields the schema forbids.
