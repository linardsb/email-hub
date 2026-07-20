# Feature: G11 — Residual ingest classes sweep (Track G · closes 3 ledger items)

Validate every file:line and symbol against current `main` before editing — line numbers below are
hints pinned to symbols (the anchor), not addresses. `main` = `5e14429` (G10 / #364 merged 2026-07-20;
G10 changed only `docs/converter-fidelity-ceiling.md`, so all code refs equal the working tree).

## Feature Description

Three independent converter (Figma→email HTML) fidelity gaps, each an open deferred-items entry that
fires on real-world designs but is corpus-latent-or-small today. G11 closes all three in one PR
(three per-item commits). This is the last render/ingest-correctness prompt before G12's generalization gate.

## User Story

As an email designer importing a Figma file, I want horizontal rules inside columns/bands to render,
decorative icons to keep their designed size, and AUTO/% line-heights to survive fixture reload — so the
converted email matches the design instead of dropping rules, ballooning icons, or mis-attributing a
line-height regression to the wrong layer.

## Problem Statement

- **(1) `phase-53.5-nested-divider-render-gap`** — 53.5 recovers a divider stroke only when the
  `mj-divider` frame **is** a section (case 9, working). Two nested placements lose the rule:
  - **case 8 (Ferrari, column-child):** LINE at `mj-wrapper > mj-section > mj-column > mj-divider-Frame`.
    Column extraction captures only texts/images/buttons — the zero-area LINE is dropped at ingest,
    so no rule renders.
  - **case 10 (mammut, band-absorbed):** two DIVIDER sections DO adopt the stroke (53.5 lift), but
    `group_by_wrapper`'s `absorb_spacers` drops DIVIDER/SPACER pseudo-sections (A2-ratified) before the
    band renders, and the band renderer emits no rule.
- **(2) `phase-53f-decorative-image-flag` (53.3d)** — the frame-wrapping-single-image branch emits the
  **FRAME** width for the image. A small decoration wrapped in a column-width frame inflates
  (case 10 nav arrows 28→268px; case 7 LEGO user-info icons 30→60px). The downstream F3 width-pin
  (`_column_image_row`/`_image_fills_column`) reads the already-wrong width and stretches.
- **(3) `phase-53.3-line-height-relative-loader-gap`** — `report.py:_node_from_dict` (the
  `load_structure_from_json` loader feeding the ENTIRE corpus harness) omits the 52.5
  `line_height_relative` field. Latent today (all 6 committed `structure.json` predate 52.5); becomes
  load-bearing the moment G12 regens fixtures against live Figma.

## Solution Statement

- **(1a) case 8:** capture in-column divider LINE strokes at column extraction; add a divider element
  category to the column-fill pipeline (`ColumnGroup` → `DocumentColumn` → `_ordered_column_elements` →
  `_column_divider_row`), and **thread the divider node-id into `content_order`** so the rule lands at
  its design y-position, not the column bottom.
- **(1b) case 10:** capture each absorbed DIVIDER's (position-among-surviving-members, stroke) onto a new
  `RepeatingGroup.internal_rules` field during `group_by_wrapper`; `render_repeating_group` re-injects a
  `<tr><td border-top>` rule row after the matching member. Absorption (member count) is UNCHANGED.
- **(2)** in the frame-wrap branch, make **emitted width and export target move together** (advisor
  correction — see NOTES): when the inner image is much smaller than the wrapper AND the wrapper carries
  no own bg-fill / corner-radius / effects, export the **child** at **child** dims (decoration); else keep
  today's frame-export + frame-dims (styled wrapper). This replaces the size-heuristic stopgap.
- **(3)** add one kwarg to `report.py:_node_from_dict` + a full-field-parity round-trip test over
  `dataclasses.fields(DesignNode)` through `report.py`'s serializer (the #327 pattern, different serializer).

## Out of Scope / Non-Goals

- **Not** z-order / semantic-role capture at ingest (the "real fix" half of `phase-53f-decorative-image-flag`
  for *large* decorative photos) — G11 closes only the frame-wrap-width half named in the prompt. Large
  decorative photos indistinguishable from content stay a known gap (leave that clause of the ledger note).
- **Not** changing `absorb_spacers` membership/count semantics (A2-ratified) — only re-inject a rule row.
- **Not** touching `_serialization.py` (`cached_dict_to_node` already round-trips `line_height_relative`)
  or the app cache path — item 3 is the diagnose/report loader only.
- **Not** the mammut 12-vs-18 undercount, new fixtures, or the semantic-split spike — those are G12.
- **Not** editing the frozen snapshot `.agents/plans/53-g-production-readiness-prompt-sequence.md`.

## Feature Metadata

**Feature Type**: Bug Fix (3 residual-class closures)
**Estimated Complexity**: Medium (item 1 is the meat — 2 sub-cases spanning ingest→document→render;
item 2 surgical ingest; item 3 trivial + test)
**Primary Systems Affected**: `app/design_sync/` — `figma/layout_analyzer.py`, `component_matcher.py`,
`component_renderer.py`, `sibling_detector.py`, `email_design_document.py`, `diagnose/report.py`
**Dependencies**: none new. Corpus scoring needs Playwright + local assets (advisory only).

## Related Work

**Implements**: Track G · G11 (TODO.md `#### G11`, the living copy — line ~433). **Epic**: Track G (G1–G12),
audit source `.agents/plans/53-g-production-readiness-prompt-sequence.md` (frozen — do not edit).

**Back-references**:
- 53.5 (#333 `2fa74e55`) — the working case-9 divider path this extends (`component_matcher.py:2861`).
- F3 image-width discipline (`_column_image_row`, `_image_fills_column`) — item 2 makes its pin work.
- #327 (`test_serialization_roundtrip.py`, `91d8752a`) — the dataclass-parity test pattern item 3 mirrors.
- G7 (#359) — `ColumnGroup.stroke_color` (the column's OWN border-left; NOT the in-column divider).

**Forward-references**: G12 (blocked by G11) — item 3 directly protects G12's live-Figma fixture regen.

---

## CONTEXT REFERENCES

### Corpus map (READ FIRST — the prompt's "cN" = case N, NOT c1..c10)

6 fixtures under `data/debug/<N>/` numbered **5–10**: **5=maap · 6=starbucks · 7=LEGO · 8=Ferrari · 9=slate
· 10=mammut** (`scripts/score-fidelity-cases.py:33-40`, `data/debug/manifest.yaml`). `structure.json` +
`tokens.json` + `expected.html` are committed for 5–10; other assets are local-only (tests `pytest.skip`
without them).

**Expected corpus movement (EMPIRICALLY MEASURED, not estimated — see VERIFICATION LOG in NOTES):**
- **Item 1** (dividers): **case 8** (column-child divider `2833:2365` #373737) + **case 10** (2 band-absorbed
  dividers `2833:1251`/`2833:1262` #C7CCCF). Both RED-confirmed absent in current HTML.
- **Item 2** (≤64 decoration width, per user-ratified scope): **cases 6, 7, 8, 9, 10 all move**; **case 5
  flat** (0 fires). Named wins: c7 icons 60→30, c10 arrows 268→28. Incidental (all genuinely-small ≤64px
  decorations → native size): c6 42px images + 26px social, c8 64px icon + 24px social, c9 24px icons + 42px
  social, small social icons in c6/c8/c9/c10. Diff-audit ALL FIVE; A3 must hold-or-improve per case.
- **Item 3**: zero corpus movement — `grep -rl line_height_relative data/debug/*/structure.json` is EMPTY
  (verified); baselines byte-identical.

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `app/design_sync/figma/layout_analyzer.py`
  - `_zero_area_vector_stroke` (:1458) — the recoverable divider-stroke signal (reuse for case 8).
  - `_walk_for_images` frame-wrap branch (:1544-1565) — **item 2 edit site** (`width=node.width`,
    `export_node_id=node.id`); `_crop_export_id` is the child-export helper.
  - `class ColumnGroup` (:142) — add divider category here (`content_order` :156; `stroke_*` :159 is the
    column's own border, not this).
  - column construction `_extract_mjml_columns` (~:1258) + `_build_column_groups` (:1304) — where each
    column's children become texts/images/buttons; `_column_content_order(child, texts, images, buttons)`
    (:1296/:1321) is where the divider id must be threaded.
- `app/design_sync/component_matcher.py`
  - working case-9 divider override (:2861-2876) — mirror this `border-top`/`_divider` shape.
  - `_ordered_column_elements` (:1063) — union-widen to include divider element; sorts by `content_order`.
  - `_group_spec_pairs` (:1110) — divider must pass through unchanged.
  - `_build_column_fill_html` (:1205-1233) — route divider element to a new `_column_divider_row`.
  - `_column_image_row` (:961) — mirror its `<tr><td>` shape for `_column_divider_row`.
  - `_fills_divider` (:2560) — the divider seed's slot filler (returns `[]`; rule comes from the override).
- `app/design_sync/sibling_detector.py`
  - `class RepeatingGroup` (:37) — add `internal_rules` field.
  - `group_by_wrapper` (:135, absorb at :182) + `_SKIP_TYPES` (:16, DIVIDER/SPACER) — capture absorbed
    DIVIDER position+stroke while filtering.
- `app/design_sync/component_renderer.py`
  - `render_repeating_group` (:812) — member loop :847-873 builds `rows`; inject rule rows keyed off
    member index. **Verify `matches` is 1:1 in-order with `group.sections`** before keying (advisor).
- `app/design_sync/email_design_document.py`
  - `class DocumentColumn` (:859) — mirror the new divider field in `to_json`/`from_json`/
    `from_column_group`/`to_column_group` (:878-942). Separate serializer from item 3 (see gotcha).
- `app/design_sync/diagnose/report.py`
  - `_node_from_dict` (:88-140) — **item 3 edit site** (`line_height_px` at :121, missing
    `line_height_relative`); `_dataclass_to_dict` (:65) dumps all fields; `load_structure_from_json` (:43)
    → `_dict_to_structure` (:143) is the harness loader.
- `app/design_sync/protocol.py:138` — `DesignNode.line_height_relative`.

### New Files to Create

- `app/design_sync/tests/test_diagnose_roundtrip.py` — item 3 full-field-parity test (report.py serializer).
- (item 1 tests may extend existing files — see Testing Strategy.)

### Patterns to Follow

- **Divider rule:** `f"{max(1, round(weight))}px solid {stroke_color}"`, floor sub-pixel to 1px, gate on
  `_HEX_COLOR_RE.match` — copy `component_matcher.py:2864-2876` verbatim in shape.
- **Column row:** `<tr><td style="...font-size:0;line-height:0;">…</td></tr>` (mirror `_column_image_row`
  :961 / `_stacked_image_row` :1307). Divider row: `border-top` on the td.
- **Dataclass round-trip parity:** `for f in dataclasses.fields(DesignNode): if f.name=="children": continue;
  assert getattr(got,f.name)==getattr(node,f.name), f.name` — `test_serialization_roundtrip.py:112-125`.
- **RED image-width assertion:** `assert 'width="28"' in tag` / `'width:100%' not in tag` with a comment
  naming the killed defect — `test_image_width_fidelity.py:92-104`.
- **Logging:** `get_logger`, `domain.action_state`. **No `<p>`/`<h*>`/layout-div** in emitted HTML.

---

## IMPLEMENTATION PLAN

Phases 1–3 are the three items. **Independent of each other** (different code paths) — could parallelize,
but ship as ONE PR with three ordered commits so each item's baseline diff-audit is isolated (case 10 is hit
by both item 1 and item 2 — per-commit regen keeps the two mechanisms from confounding its audit).
Recommended order: **item 3 (trivial, de-risks the harness loader) → item 2 (surgical) → item 1 (the meat)**.

### Phase A — Item 3: line_height_relative loader parity  `[independent]`

**Tasks:** add the missing kwarg; add a full-field-parity test through the report.py serializer.

### Phase B — Item 2: decorative image frame-wrap width  `[independent]`

**Tasks:** make width + export-target move together in the frame-wrap branch; RED test at ingest; regen
case 7 + case 10 snapshot baselines and diff-audit to the icon/arrow shrink.

### Phase C — Item 1: nested divider render (case 8 + case 10)  `[independent; largest surface]`

**Tasks:** case 8 column-divider category (capture → ColumnGroup → DocumentColumn → order → render); case 10
band-internal rule row (RepeatingGroup field → capture in group_by_wrapper → re-inject in renderer); RED
tests for both; regen case 8 + case 10 baselines and diff-audit to the recovered rules.

### Phase D — Close-out (all items green)

Ledger close ×3, TODO.md intro-row refresh + G12 anti-drift check, gates, PR.

---

## STEP-BY-STEP TASKS

Execute top to bottom. `VALIDATE` runs after each. **Write the RED test FIRST** for each item and confirm it
fails for the stated reason before the fix.

### Phase A — Item 3

#### CREATE `app/design_sync/tests/test_diagnose_roundtrip.py`
- **IMPLEMENT**: build a `DesignNode` with a distinct sentinel on EVERY field (esp. `line_height_relative=1.4`),
  round-trip via `_dict_to_structure(_structure_to_dict(DesignFileStructure(...)))` OR
  `_node_from_dict(_dataclass_to_dict(node))`; assert per-field equality over `dataclasses.fields(DesignNode)`
  (skip `children`, assert separately). Add a focused `test_line_height_relative_survives_reload`.
- **PATTERN**: `test_serialization_roundtrip.py:112-125` (`test_full_field_parity_with_protocol`).
- **IMPORTS**: `dataclasses`; `from app.design_sync.protocol import DesignNode, DesignFileStructure`;
  `from app.design_sync.diagnose.report import _node_from_dict, _dataclass_to_dict` (or the structure pair).
- **GOTCHA**: this is a DIFFERENT serializer than #327 (`report.py`, not `_serialization.py`). Confirm it
  fails RED on `line_height_relative` (and surfaces ANY other dropped field — add those to the fix too).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_diagnose_roundtrip.py -x` → RED on `line_height_relative`.
- **SATISFIES**: AC #3.

#### UPDATE `app/design_sync/diagnose/report.py` (`_node_from_dict`, ~:139)
- **IMPLEMENT**: add `line_height_relative=data.get("line_height_relative"),` (place near `line_height_px`
  / after `effects_summary`). Add any other field the parity test flagged.
- **GOTCHA**: `_dataclass_to_dict` already dumps it — only the loader was asymmetric. No fixture regen (latent).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_diagnose_roundtrip.py -x` → GREEN;
  `make snapshot-test` → byte-identical (no corpus movement).
- **SATISFIES**: AC #3.

### Phase B — Item 2

#### CREATE/EXTEND RED test in `app/design_sync/tests/test_image_width_fidelity.py`
- **IMPLEMENT**: build a frame (width 268, no fill/image_ref/effects) wrapping a 28px IMAGE child; run
  `_walk_for_images`; assert the emitted `ImagePlaceholder.width == 28` (child) AND
  `export_node_id == <child id>` (advisor: width + export move together). Add THREE controls: (a) a 30px
  image in a 60px frame with `corner_radii=[6,0,0,6]` → STILL child-exports at 30, and `corner_radius_spec`
  is preserved (c7 shape — radius must NOT block); (b) a 65px image in a 600px frame → NOT child-exported
  (>64 cap); (c) a 600px image in a 600px frame → NOT child-exported (`img==frame`, FILL).
- **PATTERN**: `test_image_width_fidelity.py:92-104`.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_image_width_fidelity.py -x` → RED (emits 268).
- **SATISFIES**: AC #2.

#### UPDATE `app/design_sync/figma/layout_analyzer.py` (`_walk_for_images` frame-wrap branch, :1544-1565)
- **IMPLEMENT**: binary branch. Compute `is_small_decoration = (img.width is not None and img.width <= 64
  and node.width is not None and img.width < node.width and node.image_ref is None and node.fill_color is
  None and node.effects_summary is None)`. IF `is_small_decoration` → emit `width=img.width,
  height=img.height, export_node_id=_crop_export_id(img)` (CHILD export). ELSE keep today's
  `width=node.width, height=node.height, export_node_id=node.id`. **Leave `node_id=img.id` and
  `corner_radius_spec=_corner_spec_or_none(rule_10_image_corner_radii(node))` UNCHANGED in both branches** —
  the current code already uses the child id as `node_id`, and radius stays sourced from the frame (applied
  to the child `<img>` via CSS by Rule 10), so rounding survives child-export.
- **PATTERN**: existing branch; `_crop_export_id` is the per-image export helper used at :1519.
- **GATE RATIONALE (user-ratified `img≤64` cap — NOT `img<frame` alone)**: `img<frame` alone fires on 5 cases
  incl. mid-size content (c6/c9 218px) — ambiguous correctness, risks "A3 no regression elsewhere". The ≤64
  absolute cap restricts to genuinely-small decorations/icons where native size is unambiguously right; c5
  stays flat, mid-size content stays on today's path. `corner_radii` does NOT block child-export (radius is
  preserved via CSS); only BAKED styling (`fill_color`/`image_ref`/`effects_summary`) blocks it — **verified:
  c7's 30-in-60 icon frame has ONLY `corner_radii=[6,0,0,6]`, no fill/image/effects, so it correctly child-exports.**
- **GOTCHA (advisor, critical — coupling)**: exporting the 268px FRAME into a 28px `<img>` scales the whole
  PNG down → arrow renders ~3px. Child-export MUST pair with child-width; they move together. Frame-export
  survives only for FILL-sized (`img==frame`) or baked-styled wrappers.
- **GOTCHA (verified)**: c10 arrow `img.width=28` and c7 icon `img.width=30` are INTRINSIC child widths in
  `structure.json` (not stretched), and neither frame carries fill/image_ref/effects — the gate is corpus-correct.
- **GOTCHA (asset key)**: flipping `export_node_id` frame→child changes the export key; `_resolve_image_url`
  resolves by `img.node_id` (already the child) so likely fine, but VERIFY the child asset resolves to a real
  PNG (not the 404 placeholder) at diff-audit — corpus asset-key handling is finicky (cf. G10 scorer artifact).
- **VALIDATE**: item-2 test GREEN.
- **SATISFIES**: AC #2.

#### REGEN + diff-audit item-2 baselines (FIVE cases: 6, 7, 8, 9, 10 — c5 flat)
- **IMPLEMENT/AUDIT**: `make snapshot-test`. Every moved case's diff should be decorations shrinking to native
  size. **Audit and ratify each; do NOT hand-revert. Watch for two consequent structural changes:**
  1. **c7 spec-fold (advisor, likely):** LEGO user-info icons shrink 60→30, and `_is_spec_icon` gates on
     `el.width <= 30` INCLUSIVE (`component_matcher.py:1092`). Post-shrink `30 <= 30` is TRUE, so ≥2 adjacent
     (icon, short-label) pairs in that column fold into a G7 spec-mini-table (`_group_spec_pairs` :1110):
     stacked rows → one horizontal mini-table. Decide consciously whether the fold is design-correct (likely
     desirable) or must be suppressed; ratify in the commit.
  2. **Primary-image flip:** `_select_primary_image` (:1264) picks the largest image by AREA. A shrunk
     decoration's smaller area can flip the hero in a section with a decoration + a real image. If a diff
     touches hero/section structure, this or the spec-fold is the cause — not a bug to revert.
  3. **Social-element movers (c6/c8/c9/c10):** confirm whether social-section logos actually flow through the
     frame-wrap branch to the emitted width, or are sized by the social render path (then inert). If inert,
     those "fires" produce no HTML diff — expected.
  Adopt via `cp data/debug/<N>/actual.html data/debug/<N>/expected.html` once each diff traces to a mechanism.
- **VALIDATE**: `make converter-data-regression` (all cases); A2 ladder counts UNCHANGED (a spec-fold is
  within-section restructuring, not a new section — if the ladder drifts, STOP and investigate). Non-target
  movers (c6/c9) must A3 hold-or-improve — if any drops, the ≤64 gate over-reached; narrow and re-audit.
- **SATISFIES**: AC #2, #5, #6.

### Phase C — Item 1

#### case 8 — RED test (extend `app/design_sync/tests/` divider/column test)
- **IMPLEMENT**: build `mj-column` with children [text, zero-area LINE(stroke #C7CCCF/1px), text]; run the
  column pipeline; assert rendered column HTML contains `border-top:1px solid #C7CCCF` at the LINE's
  y-position (between the two texts, NOT at column bottom).
- **VALIDATE**: RED (no divider rule emitted).
- **SATISFIES**: AC #1.

#### UPDATE `layout_analyzer.py` — capture in-column divider + ColumnGroup category
- **VERIFIED TARGET (case 8):** divider VECTOR `2833:2365` (`#373737`/1.0, w520 h0) is the 3rd of 4 children
  `[mj-social, mj-text-Frame, mj-divider-Frame, mj-text-Frame]` in mj-column `2833:2350` — and that column
  SURVIVES in `analyze_layout` (its id is in the analyzed column set), so the capture reaches it. The rule
  must render BETWEEN the two texts.
- **IMPLEMENT**: in column construction (`_extract_mjml_columns` ~:1258 / `_build_column_groups` :1304), scan
  each column child for divider LINEs via `_zero_area_vector_stroke`; collect `(node_id, stroke_color,
  stroke_weight)`. Add a `dividers: list[ColumnDivider]` field to `ColumnGroup` (:142) — small frozen
  dataclass with `node_id`/`stroke_color`/`stroke_weight`. **Extend `_column_content_order` to accept the
  dividers and add their node_ids to its `wanted` set** (the pre-order walk then places each divider id at its
  true y-position; without this the divider id stays out of `content_order` → renders at column bottom — advisor).
- **GOTCHA**: `_walk_for_images` deliberately drops zero-area LINEs (not rasterizable) — the divider signal
  must come from a separate `_zero_area_vector_stroke` scan, not the image walk. `_column_content_order`
  currently builds `wanted` from ONLY text/image/button ids (:~1092) — the divider id must be added there.
- **GOTCHA**: a divider-only column would survive as an empty-content ColumnGroup (the `has_content`/`is_spacer`
  skip at :1276-1284 keys on names starting `mj-spacer`, NOT `mj-divider-Frame`) — but case 8's column has
  real content, so this is moot here; noted for robustness.
- **VALIDATE**: `uv run pyright app/design_sync/figma/layout_analyzer.py`.
- **SATISFIES**: AC #1.

#### UPDATE `email_design_document.py` (`DocumentColumn`, :859-942) — persistence parity
- **IMPLEMENT**: mirror `dividers` in `to_json`/`from_json`/`from_column_group`/`to_column_group`.
- **GOTCHA (advisor)**: this is a SEPARATE serializer from item 3's `report.py` — item 3's test will NOT
  catch a dropped DocumentColumn divider field. Add a `DocumentColumn` round-trip assertion (see Testing).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_bridge_roundtrip.py -x`.
- **SATISFIES**: AC #1.

#### UPDATE `component_matcher.py` — render the column divider
- **IMPLEMENT**: widen `_ordered_column_elements` (:1063) union to include the divider element (pull from
  `group.dividers`, position via `content_order`); pass divider through `_group_spec_pairs` (:1110)
  unchanged; add `_column_divider_row(divider) -> str` (mirror `_column_image_row` :961) emitting
  `<tr><td style="padding:...;border-top:{w}px solid {color};font-size:0;line-height:0;"></td></tr>`;
  route it in `_build_column_fill_html` (:1220-1232).
- **GOTCHA (advisor — the ~10-link chain; any missing link = SILENT no-render)**: case 8 threads through
  `ColumnDivider` dataclass → `ColumnGroup.dividers` → capture at **BOTH** `_extract_mjml_columns` AND
  `_build_column_groups` → `_column_content_order` `wanted` set → `DocumentColumn.dividers` + **all 4**
  serialization methods → `_ordered_column_elements` union → `_group_spec_pairs` pass-through →
  `_column_divider_row` → `_build_column_fill_html` route. Miss any link (esp. the `DocumentColumn` bridge or
  one capture site) and the divider is dropped with NO error. **Build in dependency order; the case-8
  RED→GREEN flip is the end-to-end integration gate that proves every link is wired** — it is the only
  assertion that exercises the whole chain.
- **GOTCHA (advisor — third construction path, latent re-drop)**: `_build_column_fills_from_content_groups`
  (:2674) builds a `ColumnGroup` from a `ContentGroup` (`layout_analyzer.py:164`), which has NO dividers
  field. c8 flows through `column_groups` (verified `cols=2` populated) so the corpus is safe, but a
  divider-bearing column taking the content-group fallback would re-drop. **Either add `dividers` to
  `ContentGroup` + carry it in the `ColumnGroup(...)` at :2674, OR add a deferred-items entry** so G12
  ("must hold on any design") isn't surprised — do not leave it silent.
- **VALIDATE**: case-8 RED test → GREEN (the chain's integration gate).
- **SATISFIES**: AC #1.

#### case 10 — RED test (extend band/repeating-group test)
- **IMPLEMENT**: build a wrapper band [card, DIVIDER(stroke), card]; run `group_by_wrapper` +
  `render_repeating_group`; assert the band HTML contains a `border-top` rule row between the two cards AND
  that member count is still 2 (absorption preserved).
- **VALIDATE**: RED (no rule row).
- **SATISFIES**: AC #1.

#### UPDATE `sibling_detector.py` — capture absorbed divider onto RepeatingGroup
- **VERIFIED TARGET (case 10):** run for wrapper `2833:1240` is [content `2833:1247`, divider `2833:1248`
  #C7CCCF, content, divider `2833:1259` #C7CCCF, content] → `group_by_wrapper` absorbs the 2 dividers,
  members=[content,content,content]. Rules go **after member 0** (divider before member index 1) and **after
  member 1**. Confirmed by pipeline run (`absorbed=2 section_count=3`).
- **IMPLEMENT**: add `internal_rules: tuple[BandRule, ...] = ()` to `RepeatingGroup` (:37) — `BandRule` =
  frozen `(after_member_index: int, stroke_color: str, stroke_weight: float | None)`. In `group_by_wrapper`
  (:182), while filtering `run`→`members`, for each absorbed **DIVIDER** (not SPACER) with a valid
  `stroke_color`, record `after_member_index` = (count of surviving members seen so far in the run) − 1, +
  stroke; attach to the emitted `RepeatingGroup`. (For case 10: 1st divider after 1 member → index 0; 2nd
  after 2 → index 1.)
- **GOTCHA**: member count / band grouping UNCHANGED (A2-ratified). Only DIVIDER-with-stroke produces a rule;
  SPACER stays pure padding. A leading/trailing divider (index −1 or == last) is possible in other designs —
  clamp/skip out-of-range indices defensively.
- **VALIDATE**: `uv run pyright app/design_sync/sibling_detector.py`.
- **SATISFIES**: AC #1.

#### UPDATE `component_renderer.py` (`render_repeating_group`, :812) — re-inject rule rows
- **VERIFIED (matches↔sections):** the caller builds `group_matches` at `converter_service.py:861-865` by
  iterating `match.matches` in order and selecting those mapped to this group → 1:1 in-order with
  `group.sections` whenever every member matched (band members are rendering `content` sections, so they do).
- **IMPLEMENT**: **guard `if len(matches) == len(group.sections)` before keying** (advisor); when unequal,
  skip injection + `log()` (a missing rule beats a misplaced one). In the member loop (:847-873), after
  emitting `rendered_items[i]`, for each `group.internal_rules` with `after_member_index == i`, append a
  `<tr><td style="padding:0 {item_spacing.horizontal}px;"><table role="presentation" width="100%"
  cellpadding="0" cellspacing="0" border="0"><tr><td style="border-top:{w}px solid {color};font-size:0;
  line-height:0;"></td></tr></table></td></tr>` rule row.
- **VALIDATE**: case-10 RED test → GREEN.
- **SATISFIES**: AC #1.

#### REGEN + diff-audit item-1 baselines
- **VALIDATE**: `make snapshot-test` → case 8/10 diffs show ONLY the recovered rules; audit each; adopt via
  `cp data/debug/<N>/actual.html data/debug/<N>/expected.html`. `make converter-data-regression CASE=8`/`CASE=10`;
  A2 ladder counts UNCHANGED (rules/rows add no sections).
- **SATISFIES**: AC #1, #6.

### Phase D — Close-out

#### CLOSE ledger entries (`.agents/deferred-items.json`)
- **IMPLEMENT**: set `status: "closed"` + `closed_commit` on `phase-53.5-nested-divider-render-gap`,
  `phase-53f-decorative-image-flag`, `phase-53.3-line-height-relative-loader-gap`. For
  `phase-53f-decorative-image-flag`, note the LARGE-decorative-photo half stays open (only the frame-wrap
  width half closed) — adjust the note rather than deleting it if the z-order half is still uncovered.
- **VALIDATE**: `python3 -c "import json,sys; d=json.load(open('.agents/deferred-items.json'))"` parses.

#### UPDATE `TODO.md` Track G (anti-drift; NEVER committed per Track-G invariant)
- **IMPLEMENT**: flip the G11 header to DONE with the PR#; refresh the intro **Status (2026-07-20)** row
  (line ~35) IF A3 scores moved (advisory — record new case 7/8/10 numbers); patch G12 only if any of its
  file:line/score/mechanism claims are invalidated (checked: G12 references `score-fidelity-cases.py CASES`
  + A2 ladder + mammut ledger — no G11 symbols; "every class fixed in G1–G11 must hold" — leave as-is).
  Do NOT edit `.agents/plans/53-g-production-readiness-prompt-sequence.md` (frozen).

#### FINAL gates
- **VALIDATE**: `make check-full`; `git restore` any `skill-versions.yaml` stamp before staging (Track-G
  invariant); `git diff` to confirm only G11 files staged (Parallel Work Awareness).

---

## TESTING STRATEGY

### Unit / component (RED-then-GREEN, assert exact HTML substrings with a defect-naming comment)
- **Item 3:** `test_diagnose_roundtrip.py` — full-field parity over `dataclasses.fields(DesignNode)` through
  `report.py` (RED on `line_height_relative`). Pattern: `test_serialization_roundtrip.py:112-125`.
- **Item 2:** ingest test — `_walk_for_images` emits child width + child export for the decoration case,
  frame width + frame export for the styled-wrapper control. Pattern: `test_image_width_fidelity.py:92-104`.
- **Item 1 case 8:** column pipeline emits `border-top:...` divider row at the LINE's y-position.
- **Item 1 case 10:** band emits a `border-top` rule row between members; member count preserved.
- **DocumentColumn parity (case 8):** extend `test_bridge_roundtrip.py`-style coverage so the new divider
  field survives `to_json`/`from_json` (SEPARATE serializer from item 3).

### Integration / corpus (the diff-audit)
- `make snapshot-test` — golden `expected.html` unified-diff per case (writes `actual.html`); the primary
  mechanism-level diff-audit. Adopt with `cp actual.html expected.html` ONLY after auditing the diff to the
  intended mechanism (rule recovered / icon shrunk) and nothing else.
- `make converter-data-regression [CASE=N]` — A2 section-count ladder (HARD gate) + per-case manifest.
- `make converter-regression` — trace-metric baseline (tolerance 0.05); if it flags a benign warning-rate
  shift, `python -m app.design_sync.converter_regression --update-baseline` and note in commit.

### Edge cases
- Divider stroke sub-pixel → floors to 1px (never `0px solid`). Divider without a hex stroke → no rule.
- Column with divider but empty `content_order` → falls back to legacy order (divider last is acceptable
  degradation, matches image/text fallback).
- Frame-wrap where inner ≈ frame (genuine full-bleed in a padding frame) → keeps frame export/width.
- Band with SPACER (not DIVIDER) → no rule row (pure padding preserved).

---

## VALIDATION COMMANDS

### Level 1 — Syntax & types
`uv run ruff check app/design_sync/ --no-fix` · `uv run pyright app/design_sync/` (never `ruff --fix` w/ TCH).

### Level 2 — Unit
`uv run pytest app/design_sync/tests/test_diagnose_roundtrip.py app/design_sync/tests/test_image_width_fidelity.py app/design_sync/tests/test_bridge_roundtrip.py -x`

### Level 3 — Corpus / integration
`make snapshot-test` · `make converter-data-regression` · `make converter-regression`

### Level 4 — A3 pixel fidelity (advisory, local, Playwright+assets)
`uv run python scripts/score-fidelity-cases.py --cases 7 8 10` → compare full_image to
`docs/converter-fidelity-ceiling.md` §3 table; eyeball `.tmpscratch/fidelity/case*_side_by_side.png`.
A3 is NEVER a ship gate — "no regression elsewhere" means cases 5/6/9 unchanged within noise.

### Level 5 — Full gate
`make check-full` (lint + types + tests + security + golden-conformance + flag-audit + migration-lint).

---

## ACCEPTANCE CRITERIA

- [ ] **AC #1** — Item 1: column-child divider (case 8) and band-absorbed dividers (case 10) render their
      stroke as a rule at the correct position; RED tests for both flip GREEN; case 8/10 baselines regenerated
      and diff-audited to ONLY the recovered rules; ledger `phase-53.5-nested-divider-render-gap` CLOSED.
- [ ] **AC #2** — Item 2: frame-wrapped decorations ≤64px emit child width + child export (c7 icons 30px,
      c10 arrows 28px; mid-size content + FILL-sized wrappers unchanged; radius preserved); RED test + 3
      controls flip GREEN; **all five moved baselines (c6/c7/c8/c9/c10) diff-audited** to native-size shrink
      plus any consequent spec-fold / primary-image change, each traced and ratified in the commit; ledger
      `phase-53f-decorative-image-flag` frame-wrap half CLOSED (large-decorative-photo half stays open).
- [ ] **AC #3** — Item 3: `report.py:_node_from_dict` round-trips `line_height_relative`; full-field-parity
      test passes; corpus baselines byte-identical (latent); ledger
      `phase-53.3-line-height-relative-loader-gap` CLOSED.
- [ ] **AC #4** — A2 ladder counts UNCHANGED for all cases (no item adds sections); `test_rendered_matches_target`
      case-10 xfail still xfails (not accidentally fixed/broken).
- [ ] **AC #5** — A3 "no regression elsewhere": c5 full_image unchanged (0 fires); moved non-targets c6/c9
      hold-or-improve (the ≤64 cap targets native-size decorations — a DROP means the cap over-reached; narrow
      + re-audit) (advisory metric).
- [ ] **AC #6** — `make check-full` green; TODO.md Track G intro row + G11 header updated (uncommitted);
      frozen plan snapshot untouched; `skill-versions.yaml` stamps restored before staging.

---

## COMPLETION CHECKLIST

- [ ] Three RED tests written and confirmed failing before their fix.
- [ ] Three items committed as three ordered commits (item 3 → 2 → 1) in one PR; per-commit baseline regen.
- [ ] `make snapshot-test` diffs audited line-by-line to the mechanism; `actual.html`→`expected.html` adopted.
- [ ] `make check-full` green; A2 ladder + trace-metric within tolerance.
- [ ] 3 ledger entries closed with `closed_commit`; DocumentColumn parity covered separately from item 3.
- [ ] `ContentGroup` third column-path decision made (handled OR ledgered — not left silent).
- [ ] Case-8 chain built in dependency order; RED→GREEN flip confirms every link wired (integration gate).
- [ ] TODO.md refreshed (uncommitted); G12 anti-drift checked; frozen snapshot untouched.

---

## OPEN QUESTIONS / ASSUMPTIONS

**Resolved by verification (see VERIFICATION LOG in NOTES) — no longer open:** the two-path split (c8
column-child, c10 band-absorbed), the exact divider node ids/strokes, c8's column survives, both RED-confirmed,
the item-2 gate (≤64, radius allowed), the exact 5-case blast radius, matches↔sections 1:1, item-3 latency.

**Residual (require rendering/eyeball at execution — self-correcting via the A3 gate):**
- **c6/c9 A3 direction:** the ≤64 movers (c6 42px, c9 24px, social icons) are almost certainly native-size
  improvements, but A3 is a pixel metric requiring Playwright + local assets to confirm holds-or-improve. If a
  non-target A3 DROPS, the ≤64 cap over-reached that case → narrow (e.g. exclude the specific element) + re-audit.
- **Social-element inertness:** whether social-section logos actually flow through the frame-wrap branch to
  the emitted width (→ real diff) or are sized by the social render path (→ inert). Determined at diff-audit.
- **Assumption (high-confidence):** no item changes section COUNT → `data/debug/ladder_snapshot.json` needs
  NO regen. A2 ladder drift = the change leaked into segmentation → STOP and investigate, don't blind-regen.
- **Planning-policy note:** Track G marks G11 "the prompt is the plan" (runs directly). This plan file is the
  formal /piv-plan-implementation artifact requested by the user; it does not change the run-directly policy.

## NOTES (open canvas)

**Advisor's decisive correction (item 2) — width and export target are coupled.** The naive read ("emit
child width, keep exporting the frame") is incoherent: the Figma image API rasterizes the *export node*, so
exporting a 268px frame yields a 268px PNG (arrow small, inside lots of empty space); dropping that into
`<img width="28">` scales the *whole* PNG to 28px → the arrow renders ~3px. The only coherent decoration
path is `export_node_id = child` + `width = child`. Frame-export survives only as the styled-wrapper
exception (wrapper has its own bg-fill / corner-radius / effects worth baking — the original Rule-10 reason
the frame-wrap branch exists). So the branch is binary on (inner ≪ frame) ∧ (wrapper unstyled).

**Two serializers, kept straight.** `_serialization.py` (`serialize_node`/`cached_dict_to_node`, the app
cache path) ALREADY round-trips `line_height_relative` (:203) and is covered by #327. The bug is only in
`report.py:_node_from_dict` — the `load_structure_from_json` loader that feeds `snapshot-test`,
`regression_runner` (A2 ladder), `service.py`, and `test_physical_card_detector`. That blast radius (the
whole corpus harness) is why the ledger flagged it despite being latent. Item 3's new test targets
report.py's serializer; item 1's DocumentColumn field targets `email_design_document.py`'s
`to_json`/`from_json` — a THIRD serializer. None of the three tests substitutes for the others.

**Why case 9 works and 8/10 don't (the reach map).** 53.5 lifts a zero-area LINE stroke onto its parent
DIVIDER *section*, and `component_matcher.py:2864` emits the rule when the SECTION is DIVIDER-typed. Case 8's
LINE never becomes a section (it's a column grandchild); case 10's LINE *does* become a DIVIDER section but
`absorb_spacers` deletes it before render. Both fixes re-establish reach to the SAME already-captured stroke
signal — no new ingest capture of the stroke value itself, just new render categories (in-column row;
band-internal row) plus, for case 8, capturing the in-column LINE that the image-walk drops.

**c10 double-hit.** mammut takes both the absorbed-rule (item 1) and the arrow-shrink (item 2). Per-commit
baseline regen (not one regen at the end) keeps its snapshot diff attributable to one mechanism at a time.

## VERIFICATION LOG (evidence behind the claims above — run 2026-07-20 against main `5e14429`)

Every mechanism claim in this plan was checked against the committed fixtures + pipeline, not inferred:

1. **Corpus mapping** — `scripts/score-fidelity-cases.py:33-40`: 5=maap, 6=starbucks, 7=LEGO, 8=Ferrari,
   9=slate, 10=mammut. There is no c1–c4.
2. **Item 1 two-path split (ran `analyze_layout` + `group_by_wrapper` on c8/c10):**
   - **c8 column-child:** divider VECTOR `2833:2365` (#373737, w520 h0) is child 3 of 4 in mj-column
     `2833:2350` (`[mj-social, text, divider, text]`); that column id IS in the analyzed column set (survives);
     no divider SECTION appears. → capture into the ColumnGroup, render between the texts.
   - **c10 band-absorbed:** dividers `2833:1248`/`2833:1259` become `type=divider` SECTIONS (#C7CCCF, 53.5
     lift); `group_by_wrapper` logs `absorbed=2 section_count=3` for wrapper `2833:1240`; band renders
     `[content, content, content]`. → rules after members 0 and 1 via `RepeatingGroup.internal_rules`.
   - **Both RED-confirmed:** current converted HTML has `border-top+#373737` count 0 (c8) and
     `border-top+#C7CCCF` count 0 (c10).
3. **Item 2 gate + blast radius (walked all 6 trees with the chosen `img≤64 ∧ img<frame ∧ no baked` gate):**
   c5 = 0 fires (FLAT); c6 = 8, c7 = 10, c8 = 6, c9 = 10, c10 = 8. c7's 30-in-60 icon frame carries ONLY
   `corner_radii=[6,0,0,6]` (no fill/image_ref/effects) → child-exports correctly. c10 arrows are 28-in-268,
   intrinsic. Product/hero images are `img==frame` (FILL) → never fire.
4. **matches↔sections** — `converter_service.py:861-865` builds `group_matches` in `match.matches` order
   filtered to the group → 1:1 with members when all match (band content members do). Guard added anyway.
5. **`_column_content_order`** — builds order from `wanted={text/img/btn ids}` via a pre-order walk
   (`layout_analyzer.py` ~:1092); ids not in `wanted` are omitted → a captured divider MUST be added to
   `wanted` or it renders at column bottom.
6. **Item 3 latency** — `grep -rl line_height_relative data/debug/*/structure.json` → EMPTY. Confirmed the
   sole gap is `report.py:_node_from_dict` (`_serialization.py:cached_dict_to_node:203` already handles it).

**Confidence: 9.5/10** (design-unknowns fully closed; execution-surface risk remains). Every unknown that
capped the first draft at 7 — which path each divider takes, whether c8's column survives, the item-2 gate
correctness for c7's radius-only frame, the true blast radius, matches ordering, item-3 latency — is
empirically closed. The **one remaining watch-item** is item-1 case 8's ~10-link wiring chain (see its render
task): mechanical but unforgiving, since a missing link drops silently — the case-8 RED→GREEN flip is its
integration gate. Residuals that need a local render (unreachable here) are self-correcting via the gates:
(a) c6/c9 A3 direction → the "narrow the ≤64 cap" fallback; (b) social-element inertness → a diff-audit
observation, not a correctness risk. Item 3 is one kwarg + a mirror of an existing parity test.

## AMENDMENTS

- 2026-07-20 — created.
- 2026-07-20 — verification pass (raise confidence 7→9.5): ran `analyze_layout`/`group_by_wrapper` and walked
  all 6 fixtures. Confirmed c8=column-child / c10=band-absorbed with exact node ids, both RED. Changed item-2
  gate from advisor's strict `img<frame` to the **user-ratified `img≤64` small-decoration cap** (radius
  allowed; only baked fill/image_ref/effects block) after measuring that `img<frame` alone moves 5 cases incl.
  mid-size content. Recorded the measured 5-case blast radius, the `_column_content_order` `wanted`-set
  threading, and the matches↔sections guard. Added VERIFICATION LOG.
