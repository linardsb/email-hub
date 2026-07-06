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

## §6 — scores row (standard contract)

| | c5 | c6 | c7 | c8 | c9 | c10 |
|---|---|---|---|---|---|---|
| BEFORE (2026-07-06, post-53.3 main) | 0.840 | 0.802 | 0.794 | 0.778 | 0.680 | 0.742 |
| AFTER | 0.840 | 0.802 | 0.794 | 0.778 | **0.681** | 0.742 |

## Result (2026-07-06, `fix/phase-53.5-vector-recovery`)

Shipped both halves as planned; ran after 53.3 (`#332`, gate honoured).

- **Divider half** — zero-area stroked LINEs adopt onto their DIVIDER section
  (`_zero_area_vector_stroke` + DIVIDER-scoped lift in `analyze_layout`); matcher emits
  `TokenOverride("border-top", "_divider", "<w>px solid <hex>")` (hex-validated, weight
  defaults 1px); renderer rewrites the `divider-line` element's `border-top`
  (`_replace_divider_border`). Schema gains the 52.5-leftover `stroke_color`/`stroke_weight`
  on BOTH `image` and `section` defs (section `to_json` had been emitting them un-declared
  since 52.5); bridge-roundtrip `_full_image`/`_full_section` now pin all four.
- **Icon half** — `_walk_for_images` collects visible VECTORs ≥ 8×8 px as
  `ImagePlaceholder(export_node_id=node.id)` (the Figma render composites
  BOOLEAN_OPERATION subtrees); vectors inside already-imaged frames are skipped
  (`skip_vectors` threading — the frame export bakes them in); zero-area/sub-8px skipped.
  `_is_descriptive_alt` additionally rejects Figma auto-names ("Vector 3", "Union 12") so
  rasterized vectors fall back to the gate-clean generic alt — **found live by the new
  test**: "Vector 3" previously passed and would have leaked as alt text (G3-neg class);
  no committed baseline carries such alts, so the tightening is churn-free.
- **Corpus effect (diff-audited, per-case):** the plan predicted divider-only changes on
  5/8/9/10; reality is **case 9 only** — its two `mj-divider` sections re-render
  `border-top:1px solid #e0e0e0` → `2px solid #545454` (regen `snapshot-capture.py 9
  --overwrite`, exactly ±2 lines; snapshot gate isolates case 9 before regen, all-green
  after). Case 5's LINEs are genuinely stroke-less (raw has no strokes — nothing to
  recover); case 8's LINE is a **column child** inside a content wrapper (never a section;
  in-column divider row is a 51.x seam); case 10's divider sections DO adopt `#C7CCCF`
  (visible in the layout dump) but band grouping **absorbs** them as spacer-class
  separators before matching (`absorb_spacers`, the ratified A2 behaviour) — new ledger
  entry `phase-53.5-nested-divider-render-gap` tracks both. **No icon vectors exist in the
  corpus** — the rasterize half is synthetic-tests-only (stated in the test docstring).
- **Gates:** ladder 13/9/8/10/8/12 held (data-regression 73 passed / 1 mammut xfail;
  snapshot 34 passed post-regen); `make types` 0 errors; design_sync+components suite
  green; golden-conformance 26; scoped ruff (incl. S-rules) clean. **Scores:** §6 row —
  flat everywhere except c9 full-image +0.001 (0.680 → 0.681, the two recovered rules
  are 2px darker and match the design's own stroke values; sub-band change, composite
  eyeball adds nothing over the byte diff). A3 advisory delta recorded.
- **Honest read:** recovery reach is section-level dividers only (1 of 3 stroked fixture
  dividers rendered); nested (column-child / band-absorbed) dividers need their own seam.
  Icon rasterization exercises the existing export path — live-import PNGs join the
  gitignored-assets class (`phase-53.7-asset-reexport-prerequisite` stays open).
