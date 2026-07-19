# Feature: Card-with-N-children composite render (51.2 / Rule 1 + Rule 11) — Track G · G6 / M5

The plan below is complete, but **validate before implementing**. **Symbols are the anchor** —
line numbers are HEAD-relative (`origin/main` @ `1a4fee05`, post-G5 #356) and WILL drift; re-grep
the symbol if a ref misses. This plan was written after a 3-agent evidence sweep + two live probes
(`match_section` instrumentation + a `content_order`/width probe on the real c7 fixture); its facts
are empirical, not inferred. Read §NOTES → Evidence and the routing map before writing any code.

## Feature Description

The LEGO Insiders **membership card** (raw frame `2833:2057`: `fills[0]=#ffffff`, `cornerRadius=18`,
4 children — logo img 440×114, name/email TEXT, barcode img 440×90, bottom-shape img 440×44) must
render as **ONE white `border-radius:18px` table, `width="440" align="center"`, with its four
children stacked as rows** (Rule 1: card-with-N-children collapses to one container; Rule 11: card
width = dominant child-image native width, not 100%). Today it routes to the **image-gallery** seed,
which lays the 3 images out as 192px 3-across tiles and **silently drops the name/email TEXT** — the
single worst-scoring band in c7 (`section_min 0.351`). This is Track G Prompt 6 / TRIAGE stub 51.2,
building on the G4 (51.1) composite seam and closing ledger `phase-53f-f7-image-gallery-membership-card`.

## User Story

As a **designer handing a Figma file with a physical membership card to the converter**
I want **the card to render as one rounded white 440px card with its logo, identity text, barcode,
and shape stacked in design order**
So that **the email matches the design instead of a 3-across tile gallery with the identity text
missing — and the converter gains a reusable card/table composite the later card-shaped fixes need.**

## Problem Statement

Four defects, each **empirically verified** on the real c7 fixture (probe output in §NOTES A):

1. **Wrong seed.** Section §14 (`is_physical_card_surface=True`, `inner_bg=#FFFFFF`, `inner_radius=18.0`,
   `img=3, text=1, col_layout=SINGLE`) matches `image-gallery @ 0.88`
   (`component_matcher.py:_score_candidates`, predicate `img_count >= 3 and text_count <= 1`). It is the
   **only** section in the whole corpus routing to image-gallery (probe: all 6 fixtures).
2. **TEXT dropped.** `_fills_image_gallery` (`component_matcher.py`, ~:1744) iterates `section.images[:6]`
   only and never reads `.texts`; the "Andy\nemail@brand.emaillove.com" node (`2833:2062`) is **present in
   `section.texts`** but discarded → no data recovery needed, only routing/fill.
3. **No white r18 shell / wrong width.** `inner_bg`/`inner_radius` are threaded but their token overrides
   target only an `_inner` element the image-gallery seed lacks (`component_matcher.py:_build_token_overrides`
   → `_inner`; seed has none) → card renders surface-less on the `#F4F4F4` band, images at 192px.
4. **Rule 9 latent.** `is_physical_card_surface` is detected + threaded 1:1 but **never read by any render
   code** (the "reads it to skip the flip" comment at `layout_analyzer.py` is stale). Not a live bug today
   (image-gallery emits no dark class), but any card surface class G6 adds could re-introduce it.

## Solution Statement

Route the card-shell to a dedicated **card fill** that renders the design's card table, hosted by the
existing `cell` seed — a minimal single-cell wrapper (no new seed, no manifest/golden-conformance churn):

- **Detect (A1):** in `_score_candidates`, add a card-shell candidate that beats image-gallery for exactly
  this section — predicate `is_physical_card_surface AND inner_bg AND images AND texts AND
  column_layout == SINGLE` (probe: fires on **c7 §14 alone** across all 6 fixtures). Route to a new
  `"card"` slug hosted by the `cell` seed.
- **Build (A2):** new `_fills_card` builder — order children by `section.column_groups[0].content_order`
  (probe: `('2833:2060','2833:2062','2833:2064','2833:2066')` == design y-order), map each node-id to its
  `ImagePlaceholder`/`TextBlock`, emit one `<tr>` per child (image rows reuse the `_stacked_image_row`
  img construction — Rule-11 width pin, `_derive_image_alt` gate-safe alt, `data-node-id`; text row =
  a `<td>` with full inline font props + `mso-line-height-rule:exactly`, `\n`→`<br>`). Wrap in a new
  `render_card_table(rows, *, width, bg, radius)` helper → `<table width="{440}" align="center"
  bgcolor="{#FFFFFF}" class="wf" style="background-color:{#FFFFFF};border-radius:{18}px;
  border-collapse:separate;overflow:hidden;">{rows}</table>`. Return a single **text fill of the `cell`
  `content` slot** (fill-a-cell, NOT a splice). Width = `max(im.width for im in section.images)` (Rule 11;
  `inner_card_fixed_width` is `None` here — see §NOTES A). Radius = `section.inner_radius`; bg = `section.inner_bg`.
- **Rule 9 by construction (A3):** the card table carries **no** dark-mode class → its white surface never
  flips; no `is_physical` read at render. (`_invert_text_colors` no-ops on the light bg.)
- **Close-out (A4):** regen c7 `expected.html` (diff-audited: only §14 changes; c5/c6/c8/c9/c10 byte-identical);
  score locally (c7 `section_min` up); rewrite ledger `phase-53f-f7-image-gallery-membership-card` (its
  `closes_when` under-describes the real fix — see §Related), unblock G7; `make check-full`; TODO.md Track G.

## Out of Scope / Non-Goals

- **NOT closing `phase-53g-g4-general-sub-template-recursion`.** That item is *sub-template substitution*
  (a composite child rendered through its own seed — the pills-in-card case). This card's children are
  **terminal leaves** (image/text rows); it never exercises recursion. Keep that entry deferred; frame
  what ships as a bounded "rows-in-a-table" render, not general recursion. (Advisor call.)
- **NOT extending `render_composite`.** Own-row CTA (G4) is byte-sensitive; a NEW sibling
  `render_card_table` helper isolates the CTA path (zero regression risk) and is what G7/G8 reuse.
  Alternative (extend `render_composite` with a wrapper mode) recorded in Open Questions.
- **NOT a new seed template.** Reuse the registered `cell` seed. Adding `card.html` would incur
  `component_manifest.yaml` + golden-conformance + tree-manifest churn for zero gain.
- **NOT a tree-path (`tree_bridge`) card render.** The default renderer path drives `expected.html`; the
  tree path is non-default and force-falls-back to the renderer (which renders the card correctly). If the
  `cell` text-fill needs an `HtmlSlot` shape there, mirror G4's graceful skip + ledger — do not error.
- **NOT touching the 6 benefit cards** (`column-layout-2`, already white via `_wrap_col_bg_inner_card`),
  nor c5 §10 (physical but col-layout-4, no images/texts) — the predicate excludes both (probe-confirmed).
- **NOT re-extracting `structure.json`** (schema-drift trap). No ingest fields change; everything needed
  (`content_order`, `inner_bg`, `inner_radius`, `is_physical_card_surface`, image widths) is already present.

## Feature Metadata

**Feature Type**: Enhancement (fidelity) + small New Capability (card render primitive).
**Estimated Complexity**: Medium — small code, but risk is (a) baseline diff isolation to §14 and (b)
routing a new slug through the existing seed/manifest without gate churn.
**Primary Systems Affected**: `app/design_sync/component_matcher.py` (detection candidate + `_fills_card`
+ `render_card_table`), possibly `component_renderer.py` (only if `cell`/`card` slug needs wiring),
`app/components/data/component_manifest.yaml` + `app/components/data/seeds` (register `card` → `cell`
template, if a distinct slug is chosen), the `data/debug/7` snapshot baseline.
**Dependencies**: G4 (#354, composite infra — reused conceptually), G3 (#353, captured geometry). Both on main.

## Related Work

**Implements**: TRIAGE stub `51.2-rule-1-card-with-n-children.md` · Track G · Prompt 6 (M5). Frozen source:
`.agents/plans/53-g-production-readiness-prompt-sequence.md` §Prompt 6 — **do NOT edit that snapshot**.
Living copy: TODO.md § Track G (patch on close-out).

**Back-references**:
- G4 #354 (`.agents/plans/53-g4-composite-slot-infrastructure.md`) — `SlotFill`/`CompositeSlot`/`render_composite`
  seam + `_stacked_image_row`/`_splice` patterns this mirrors (fill-a-cell instead of splice-after).
- F7 #97bfb77c (`.agents/plans/53-f7-column-card-surface.md`) — `_wrap_col_bg_inner_card` rounded-white card
  precedent (the col-layout half; this is the image-gallery half F7 scoped out).
- G3 #353 — `ImagePlaceholder.width` / captured geometry the row widths read.

**Forward-references**:
- **G7** (`53-g7-spec-minitable.md`, `[blocked by G6]`) — reuses `render_card_table` for the centered
  spec/user-info tables. Unblock at close-out.
- **G8** (composite footer) — later `render_card_table` / row-composite consumer.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `app/design_sync/component_matcher.py` — `_score_candidates` (`~:323`, image-gallery predicate `~:351`,
  sort `~:401`); `_match_by_type` (`~:239`, CONTENT dispatch `~:268`); `match_section` (`~:97`, column
  override `~:108` protects benefit cards); `_build_slot_fills` builders dict (`~:496`, `"image-gallery"`
  `~:508`); `_fills_image_gallery` (`~:1744`, the drop); `_stacked_image_row` (`~:1103`, returns a full
  `<tr><td><img>`, Rule-11 width pin at `_STACK_NATURAL_WIDTH_MAX=540` `~:1080`/`~:1115`, `_derive_image_alt`,
  `data-node-id`); `_resolve_image_url` (`~:?`); `SlotFill` (`~:29`, `slot_type` incl. `"composite"`),
  `CompositeSlot`/`render_composite` (`~:55`/`~:959` — reference only, NOT extended); `_build_token_overrides`
  (`~:2256`, `_inner` overrides that no-op on this card).
- `app/design_sync/figma/layout_analyzer.py` — `EmailSection` (`~:175`: `is_physical_card_surface:237`,
  `inner_bg`, `inner_radius`, `images:191`, `texts:190`, `column_layout:188`, `column_groups:201`);
  `ColumnGroup.content_order` (`~:152-156`, the F10 interleave restorer = the y-order source);
  `TextBlock` (`~:73`) / `ImagePlaceholder` (`~:95`, `.width:100`) — **no absolute-y field** (use `content_order`).
- `app/design_sync/figma/physical_card_detector.py` — `detect_physical_card_surface` (`~:59`) +
  `find_physical_card_in_subtree` (`~:102`); why `is_physical=True` here (barcode_child + distinct_corner_radius).
- `app/design_sync/component_renderer.py` — `_fill_slots` dispatch (`~:897`, text branch); `_fill_text_slot`
  (inserts fill value **raw**, HTML preserved — confirm before relying on it); `_invert_text_colors`
  (`bgcolor_propagator.py:~422`, light-bg no-op `~:429`); `_wrap_col_bg_inner_card` (`~:1670`) +
  `_replace_inner_radius` (`~:1736`, the `border-collapse:separate;overflow:hidden` radius-clip precedent).
- `app/core/config/design_sync.py:126` — `physical_card_detection_enabled` (default **True**; the predicate
  inherits it).
- `email-templates/components/cell.html` — the host seed (single `data-slot="content"` cell, `width=100%`,
  `align`). `app/components/data/component_manifest.yaml:620` (`slug: cell`) — registered + golden-conformant.
- `data/debug/7/expected.html` — the baseline to regen (currently renders the buggy gallery, §14 ~L823-877).
  `data/debug/{5,6,8,9,10}/expected.html` — must stay byte-identical.
- `email-templates/training_HTML/for_converter_engine/Lego/manual_component_build.html` #16 (L1195-1276) —
  the P50 design truth (exact card table + 4 rows; see §NOTES B).

### New Files to Create

- `app/design_sync/tests/test_card_composite.py` — unit tests for `_fills_card` (fill shape, y-order,
  text restored, Rule-11 width, r18) + `render_card_table` (wrapper attrs) + a detection test (predicate
  fires only for the card-shell). RED before A1/A2.

### Relevant Documentation

- `.agents/plans/deferred/51.2-rule-1-card-with-n-children.md` — stub scope (Rule 1 pre-pass intent; note the
  TRIAGE re-scope: band-grouping already ships the wrapper-level half — G6 is the rounded-card **render**).
- `.agents/plans/53-g-production-readiness-prompt-sequence.md` §Prompt 6 (frozen) + M5 (L36 mistake row).
- `docs/architecture/opus-figma-to-html-process.md` §8.3 Rule 1 / Rule 11 (per the stub).

### Patterns to Follow

- **Fill-a-cell, not splice** (advisor): the card IS the section body → a self-contained `<table>` filling
  the `cell` `content` slot via a text/html fill; **not** `_splice_rows_after_slot` (that inserts a row and
  would leave an empty anchor row above the card). A RED test asserts the card table is the cell content.
- **Reuse the row builder** — `_stacked_image_row` returns `<tr><td style="padding:0;text-align:center;
  font-size:0;line-height:0;"><img …></td></tr>` with `_derive_image_alt` (never empty → gate-safe) and the
  width pin. For the design's per-row padding (`20px 0 0 0` / `30px 0 20px 0` / `0`), build the row inline
  mirroring `_stacked_image_row`'s img construction rather than post-editing its `padding:0`.
- **No `alt=""`** on the decorative bottom-shape — let `_derive_image_alt` produce a multi-word alt
  (hardcoding `alt=""` trips golden-conformance G3-neg; ledger `phase-53f-...alt` documents "no live safe case").
- **Radius clip** — the r18 needs `border-collapse:separate;overflow:hidden` on the card `<table>` to bite
  (mirror `_replace_inner_radius:1744`); design confirms both.
- **Text `<td>` full props** — `font-family`, `font-size`, `color`, `line-height`, `mso-line-height-rule:exactly`
  (CLAUDE.md HTML-email rule; design #16 row 2). No `<p>`/`<h*>`.

---

## IMPLEMENTATION PLAN

Phases run top-to-bottom. **Phase 0** verifies (empirical, fixtures are local); **Phase 1** = builder +
helper + detection; **Phase 2** = routing/host wiring; **Phase 3** = tests; **Phase 4** = regen + score +
close-out.

### Phase 0: Baseline + before-coding verifies (no code change)
- Confirm branch off `origin/main` @ `1a4fee05` (post-G5), clean tree. Capture current c7 A3
  (`section_min ~0.351`) + ladder `13/9/8/10/8/12` as the honest before.
- **VERIFY-1 (host):** confirm `card`/`cell` routing. Is `cell` in `COMPONENT_SEEDS`
  (`app/components/data/seeds`) and does `_load_seeds()` resolve it? Decide slug: reuse `cell` directly, or
  register a thin `card` slug whose `template` == `cell.html`. Pick the path with the least manifest churn.
- **VERIFY-2 (fill insert):** confirm `_fill_text_slot` inserts a fill's value **raw** (HTML preserved, not
  escaped) into `data-slot="content"`. If it escapes, use the `stacked_after`/raw-HTML path or an `HtmlSlot`.
- **VERIFY-3 (tree path):** confirm the `cell` text-fill either renders in `tree_bridge` or force-falls-back
  cleanly (no `CompilationError` that isn't caught). Ledger if it drops (mirror G4).

### Phase 1: Card builder + render helper + detection (Foundation)
**Depends on:** Phase 0.
- `render_card_table(rows, *, width, bg, radius, align="center")` (module-level, near `render_composite`).
- `_fills_card(section, cw, *, image_urls=None, **kw) -> list[SlotFill]` — y-order via `content_order`,
  image/text rows, wrap, return one `content` text fill.
- Card-shell candidate in `_score_candidates` (score `> 0.88`, e.g. `0.95`).

### Phase 2: Route + host wiring
**Depends on:** Phase 1.
- Register `"card": _fills_card` in the builders dict; ensure the `card`/`cell` slug resolves to the
  `cell` seed. Confirm the section renders end-to-end (renderer path).

### Phase 3: Tests (RED-proven)
**Depends on:** Phases 1–2.
- `_fills_card` shape/order/text/width/radius; `render_card_table` attrs; detection predicate isolation;
  Rule-9 (no dark class on the card table).

### Phase 4: Regen + score + close-out
**Depends on:** Phases 1–3 green.
- Regen c7; diff-audit (§14 only); confirm c5/c6/c8/c9/c10 byte-identical; score c7; white-on-white grep;
  ledger + TODO.md + G7 unblock; `make check-full`.

---

## STEP-BY-STEP TASKS

Execute in order. Each is atomic and independently testable.

### 0. BASELINE + VERIFY-1/2/3
- **IMPLEMENT**: record c7 A3 + ladder; resolve VERIFY-1/2/3 (host slug, raw insert, tree path). Extend the
  scratch probe (`scratchpad/yorder_probe.py`) if needed.
- **VALIDATE**: `uv run python scripts/score-fidelity-cases.py --cases 7` (save table); print `COMPONENT_SEEDS`
  keys for `cell`; grep `_fill_text_slot` for escaping.
- **GOTCHA**: this local baseline (post-G5), not any frozen-prompt number, is the no-regression reference.
- **SATISFIES**: AC "A3 up vs baseline" reference; host/insert decisions.

### 1. ADD `render_card_table` (`component_matcher.py`)
- **IMPLEMENT**: near `render_composite`. Signature `render_card_table(rows: list[str], *, width: int,
  bg: str, radius: int, align: str = "center") -> str`. Emit:
  `<table role="presentation" width="{width}" align="{align}" cellpadding="0" cellspacing="0" border="0"
  bgcolor="{bg}" class="wf" style="background-color:{bg};border-radius:{radius}px;border-collapse:separate;
  overflow:hidden;">{"".join(rows)}</table>`. `rows` are full `<tr>…</tr>` strings.
- **PATTERN**: manual #16 wrapper (§NOTES B); `_replace_inner_radius:1744` radius-clip; `wf` class = the
  design's width-fix class (also emitted for `_inner` at `_build_token_overrides:2317`).
- **GOTCHA**: values come pre-validated from the section (`inner_bg`, `inner_radius`, dominant img width) —
  coerce to `int`/hex-safe; do not interpolate raw user strings.
- **VALIDATE**: Task 6 unit test asserts the wrapper attrs/style.
- **SATISFIES**: AC card-table shell (white/r18/440/center).

### 2. ADD `_fills_card` (`component_matcher.py`)
- **IMPLEMENT**: order children by `section.column_groups[0].content_order` when present (fallback: images
  then texts in stored order — flag if `content_order` empty). Build a `{node_id: element}` map from
  `section.images` + `section.texts`. For each node-id in order:
  - image → an image row: mirror `_stacked_image_row`'s img tag (url via `_resolve_image_url`, `_derive_image_alt`,
    width pin, `data-node-id`) inside `<tr><td style="padding:{per-row};text-align:center;font-size:0;line-height:0;">`.
    Per-row padding from §NOTES B (logo `20px 0 0 0`, barcode `30px 0 20px 0`, shape `0`); default `0` for
    unmapped rows.
  - text → `<tr><td align="center" style="background-color:{bg};padding:10px 24px 0 24px;font-family:{ff};
    font-size:{fs}px;line-height:{lh}px;font-weight:{fw};color:{tc};mso-line-height-rule:exactly;">{content
    with \n→<br>}</td></tr>` (font from the `TextBlock`; fall back to design #16: Noto Sans / 14 / 19 / 600 / #000000).
  - `width = max((int(im.width) for im in section.images if im.width), default=600)` (Rule 11 = 440 here).
  - `return [SlotFill("content", render_card_table(rows, width=width, bg=section.inner_bg or "#FFFFFF",
    radius=int(section.inner_radius or 0)), slot_type="text")]`.
- **PATTERN**: `_fills_image_gallery` shape (builder signature); `_stacked_image_row` img construction.
- **GOTCHA**: `inner_card_fixed_width is None` here (rule_11 needs *direct* image children; these are nested)
  → **use `max(img.width)`, not `inner_card_fixed_width`** (probe-verified). Emit NO dark-mode class (Rule 9).
- **VALIDATE**: Task 6/7 tests.
- **SATISFIES**: AC text restored, stacked y-order, width 440, r18, Rule 9.

### 3. ADD card-shell candidate to `_score_candidates` (`component_matcher.py`)
- **IMPLEMENT**: before/among the existing candidates, add:
  ```python
  if (section.is_physical_card_surface and section.inner_bg
          and section.images and section.texts
          and section.column_layout == ColumnLayout.SINGLE):
      candidates.append(("card", 0.95))   # beats image-gallery 0.88
  ```
- **PATTERN**: the candidate-append list `_score_candidates:~:340-360`; highest-score sort `~:401`.
- **GOTCHA**: 0.95 must exceed image-gallery's 0.88 AND any other candidate this section could raise
  (probe: none higher fire). Predicate probe-proven unique to c7 §14 across all 6 fixtures.
- **VALIDATE**: Task 8 detection test; Task 9 routing map (all 6 unchanged except c7 §14).
- **SATISFIES**: AC routing (card wins), isolation (no other case moves).

### 4. REGISTER the `card` slug → `cell` seed (`component_matcher.py` builders + manifest/seeds)
- **IMPLEMENT**: add `"card": _fills_card` to the `_build_slot_fills` builders dict (`~:496`). Ensure the
  `card` slug resolves to the `cell.html` template (per VERIFY-1: either alias `card`→`cell` template in
  `component_manifest.yaml` + `COMPONENT_SEEDS`, or route directly to the `cell` slug if simpler).
- **PATTERN**: existing builder registrations (`:508` image-gallery); seed load `_load_seeds()`.
- **GOTCHA**: a slug with no seed = KeyError at render. Keep the seed minimal (the `content` cell); do NOT
  add data-slots that would trip golden-conformance.
- **VALIDATE**: end-to-end render of case 7 produces the card table in §14.
- **SATISFIES**: AC card renders in the corpus path.

### 5. WIRE Rule 9 guard (only if a surface class is emitted anywhere)
- **IMPLEMENT**: by construction the card table has no dark class → nothing to do. If, and only if, the host
  path adds `product-card`/`dark-bg`/`bgcolor-{HEX}` to the card, gate it on `not section.is_physical_card_surface`
  (the first render-time reader of the flag).
- **VALIDATE**: white-on-white grep (Task 11) + dark-mode render spot-check.
- **SATISFIES**: AC Rule 9 (physical card not dark-flipped).

### 6. ADD `render_card_table` + `_fills_card` unit tests (`test_card_composite.py`)
- **IMPLEMENT**: (a) `render_card_table(["<tr>…</tr>"], width=440, bg="#FFFFFF", radius=18)` →
  asserts `width="440"`, `border-radius:18px`, `background-color:#FFFFFF`, `border-collapse:separate;overflow:hidden`,
  `align="center"`. (b) `_fills_card` on a synthetic section (3 imgs + 1 text + `content_order`) → one
  `SlotFill("content", …, slot_type="text")` whose value contains the text ("Andy"), 4 `<tr>` rows in
  content_order, `width="440"`, r18, and NO dark-mode class.
- **PATTERN**: `test_cta_fidelity.py` fixtures; `test_composite_slot.py`.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_card_composite.py -q` (RED before Tasks 1–2).
- **SATISFIES**: AC RED-proven builder + helper.

### 7. ADD y-order / text-restore render test
- **IMPLEMENT**: assert the rendered card row order == `content_order` (logo, text, barcode, shape) and the
  identity text is present (regression against the drop). Assert a physical card with NO `content_order`
  falls back to images-then-texts without crashing.
- **VALIDATE**: same test file.
- **SATISFIES**: AC y-order + text restored.

### 8. ADD detection isolation test
- **IMPLEMENT**: the predicate returns `card` for a card-shell section and NOT for (a) a plain 3-image
  gallery (`is_physical=False`), (b) a physical col-layout-4 section (c5 §10 shape), (c) an image-only
  physical card (no texts). Mirror the probe's discriminators.
- **VALIDATE**: same test file.
- **SATISFIES**: AC isolation (no other case perturbed).

### 9. VERIFY routing map (no code change) — DO BEFORE REGEN
- **IMPLEMENT**: re-run the `match_section` probe (`scratchpad/route_probe.py`) over all 6 fixtures; assert
  **only c7 §14** routes to `card`; every other section's slug is **unchanged** vs the Phase-0 capture.
- **VALIDATE**: diff the pre/post routing dumps → exactly one changed row.
- **GOTCHA**: any second changed row = predicate too broad → tighten before regen.
- **SATISFIES**: AC "no other case changes unless it carries a card-shell".

### 10. REGEN + diff-audit c7 baseline
- **IMPLEMENT**: `make snapshot-capture CASE=7` (→ `scripts/snapshot-capture.py 7 --overwrite`). Regen
  c5/c6/c8/c9/c10 and confirm **zero diff**. `git diff data/debug/7/expected.html`: §14 changes from the
  image-gallery block (3 tiles) to the card `<table width="440" … border-radius:18px>` with 4 rows incl.
  the restored "Andy / email…". Ladder unchanged (still 8 sections in c7 — count invariant).
- **VALIDATE**: `git diff --stat data/debug/`; visual spot-check c7 card centered/white/r18; `python -m
  app.design_sync.tests.ladder_harness --write` shows `13/9/8/10/8/12` unchanged.
- **GOTCHA**: only §14 lines should move. Any change elsewhere = leak → stop.
- **SATISFIES**: AC c7 card renders; others byte-identical; ladder held.

### 11. WHITE-ON-WHITE + SCORE
- **IMPLEMENT**: grep regenerated c7 for `background-color:#FFFFFF;color:#ffffff` (any case) → zero (guards
  `_invert_text_colors` sampling the band bg). Re-score c7.
- **VALIDATE**: `uv run python scripts/score-fidelity-cases.py --cases 7` → c7 `section_min` up from ~0.351,
  `full_image`/`section_median` up; no c7 metric regresses. (Local-only; needs Playwright + gitignored assets.)
- **SATISFIES**: AC "c7 A3 up"; no white-on-white.

### 12. FULL GATE
- **IMPLEMENT**: `make check-full`.
- **VALIDATE**: lint + types + tests + security + golden + flag audit + migration lint all green.
- **GOTCHA**: `make check-full` does NOT compute fidelity (Task 11 does, locally). Keep them distinct.
- **SATISFIES**: AC `make check-full`.

### 13. LEDGER + TODO.md close-out (anti-drift)
- **IMPLEMENT**:
  (a) `.agents/deferred-items.json` — **CLOSE** `phase-53f-f7-image-gallery-membership-card` (add
      `closed_commit`; `closure_note`: routed to `card`/`cell` via `_fills_card`+`render_card_table`; note its
      `closes_when` under-described the fix — the real change restores the dropped text + stacks rows + adds
      the white r18 shell, a substantial §14 diff, NOT "1 added wrapper"; ladder held `13/9/8/10/8/12`).
      Keep `phase-53g-g4-general-sub-template-recursion` **DEFERRED** (pills-in-card, not this card).
      Add a **deferred** tree-path card entry if VERIFY-3 surfaced a drop.
  (b) TODO.md § Track G — refresh the intro status row if scores moved (c7 `section_min`); flip G7's header
      `[blocked by G6]` → `[ready]`; patch any LATER G-prompt (G7/G8) whose file:line refs / mechanism claims
      this change invalidated (e.g. G8 "depends 51.1+51.2" now satisfied). **Do NOT edit the frozen snapshot
      `.agents/plans/53-g-production-readiness-prompt-sequence.md`.**
  (c) `git restore` the `skill-versions.yaml` stamps before staging (per-prompt invariant).
- **VALIDATE**: `git diff` review; frozen snapshot untouched; ledger entry closed; G7 unblocked.
- **SATISFIES**: AC ledger closed + close-out discipline.

---

## TESTING STRATEGY

### Unit Tests (`test_card_composite.py`)
- `render_card_table`: wrapper attrs/style (width/radius/bg/clip/align).
- `_fills_card`: single `content` text fill; 4 `<tr>` in `content_order`; text restored; width 440; r18;
  no dark class; `content_order`-empty fallback.
- Detection: predicate returns `card` only for the card-shell (3 negative shapes).

### Integration / Snapshot
- Routing map (Task 9): only c7 §14 → `card`.
- Regen (Task 10): only `data/debug/7` moves; `{5,6,8,9,10}` byte-identical; ladder `13/9/8/10/8/12`.
- `make snapshot-test`; A3 scorer (local) is the fidelity oracle.

### Edge Cases
- `content_order` empty/absent → images-then-texts fallback (no crash, flagged).
- A physical card with images but no text → predicate does NOT fire (stays image-gallery) — out of scope.
- Image width missing → width default 600 (does not stretch beyond band).
- Decorative image → `_derive_image_alt` multi-word alt (no `alt=""`, G3-neg safe).

---

## VALIDATION COMMANDS

### Level 1 — Syntax & Style
- `uv run ruff check app/design_sync/ --no-fix` (never `--fix` with TCH — CLAUDE.md)
- `uv run ruff format --check app/design_sync/`

### Level 2 — Unit Tests
- `uv run pytest app/design_sync/tests/test_card_composite.py app/design_sync/tests/test_cta_fidelity.py -q`

### Level 3 — Types + Snapshot + Routing
- `uv run mypy app/design_sync/` · `uv run pyright app/design_sync/`
- Routing map (Task 9): only c7 §14 → `card`.
- Regen: `git diff data/debug/` shows only c7 §14; `{5,6,8,9,10}` empty.

### Level 4 — Fidelity (LOCAL-ONLY — needs Playwright + gitignored assets)
- `uv run python scripts/score-fidelity-cases.py --cases 7` → c7 `section_min` up (~0.351 → higher),
  no c7 metric down. White-on-white grep = zero. (Separate from `make check-full`.)

### Level 5 — Full gate
- `make check-full` (lint + types + tests + security + golden + flag audit + migration lint).

---

## ACCEPTANCE CRITERIA

- [ ] c7 membership band renders a **white `border-radius:18px`, `width="440" align="center"` card** with
      logo, "Andy / email@brand.emaillove.com" text, barcode, and bottom shape **stacked in design order**.
- [ ] The dropped identity TEXT is restored; images at native 440 width (Rule 11), not 192px tiles.
- [ ] Detection predicate routes **only c7 §14** to `card` (routing map: all other sections/cases unchanged).
- [ ] Rule 9: the card carries no dark-mode class (white surface never flips); no white-on-white.
- [ ] c7 `expected.html` regenerated (NOT hand-edited); `git diff` isolated to §14; c5/c6/c8/c9/c10
      byte-identical; ladder `13/9/8/10/8/12` unchanged.
- [ ] c7 A3 up (local): `section_min` rises from ~0.351; no c7 metric regresses.
- [ ] RED-proven unit tests (builder, helper, detection, y-order); `make check-full` green.
- [ ] Ledger `phase-53f-f7-image-gallery-membership-card` CLOSED; `phase-53g-g4-general-sub-template-recursion`
      stays deferred; TODO.md Track G updated + G7 unblocked; frozen snapshot untouched.

---

## COMPLETION CHECKLIST

- [ ] All tasks in order; each validation passed immediately.
- [ ] Routing map verified BEFORE regen (only c7 §14 moves).
- [ ] Full suite green (unit + snapshot); zero lint/type errors.
- [ ] Manual spot-check: c7 card white/r18/centered/440, text present, 4 rows in order.
- [ ] c7 A3 up (local) vs Phase-0; ladder held; no white-on-white.
- [ ] Ledger + TODO.md updated; frozen snapshot untouched; `git diff` isolated to this ticket
      (`skill-versions.yaml` stamps restored).

---

## OPEN QUESTIONS / ASSUMPTIONS

1. **Render helper vs extend `render_composite` (RECOMMENDED: new `render_card_table`).** A dedicated helper
   isolates the byte-sensitive own-row CTA path and is the primitive G7/G8 reuse. The prompt says "composite
   fill (51.1 seam)"; this honors it in spirit (a card composite is emitted, reusing the seam's row-building
   idiom) without mutating `render_composite`. *If the reviewer wants `render_composite` extended with a
   wrapper mode instead, flag before implementing — it changes Task 1 and adds CTA byte-compat proof.*
2. **Host slug (RECOMMENDED: reuse `cell`).** `cell` is registered + golden-conformant. If a distinct `card`
   slug is preferred for clarity, alias its template to `cell.html` — but that adds a manifest/seeds entry.
   Resolve in VERIFY-1.
3. **Per-row padding fidelity.** The design paddings (§NOTES B) are used verbatim. If they over-fit and move
   neighbouring bands, fall back to a uniform inset; A3 (Task 11) is the arbiter.
4. **Tree path.** Assumed non-blocking (force-fallback renders correctly). If the `cell` text-fill errors in
   `tree_bridge`, ledger the drop (mirror G4's `phase-53g-g4-tree-html-slot-row-shape`); do not force it into
   scope.
5. **Branch base.** Execute on a fresh branch off `origin/main` @ `1a4fee05` (post-G5 #356); local
   `a6838b5f` was squash-merged.

## NOTES (open canvas)

### (A) Evidence — live probe on the real c7 fixture (2026-07-19)
`match_section` instrumentation + `content_order`/width probe (`scratchpad/route_probe.py`,
`scratchpad/yorder_probe.py`):
- CARD = section idx **14**, `node=2833:2057`, `slug=image-gallery`, `col_layout=single`, `col_groups=1`,
  `child_groups=0`, `is_physical_card_surface=True` (signals `barcode_child`, `distinct_corner_radius`),
  `inner_bg=#FFFFFF`, `inner_radius=18.0`, **`inner_card_fixed_width=None`**.
- images (stored order): `2833:2060 (440×114)`, `2833:2064 (440×120)`, `2833:2066 (440×44)`; texts:
  `2833:2062 "Andy\nemail@brand.emaillove…"` (**present**, dropped by the fill only).
- **`column_groups[0].content_order = ('2833:2060','2833:2062','2833:2064','2833:2066')`** = design y-order
  (logo, text, barcode, shape) → the interleave source. `TextBlock`/`ImagePlaceholder` carry no absolute-y.
- Rule 11 (`rule_11_card_width_from_dominant_image`) returns `None` here because it counts **direct** image
  children of the card frame, but the images sit 2 levels down (`2833:2057 → mj-column 2833:2058 → wrapper
  frames → image`). ⇒ width from `max(img.width)` = 440, not `inner_card_fixed_width`.

**Routing map (probe, all 6 fixtures):**

| Case | → `image-gallery` today | Card-shell (predicate fires)? | Post-G6 |
|------|-------------------------|-------------------------------|---------|
| 5 maap | none | No (§10 physical but col-layout-4, img=0/txt=0) | unchanged |
| 6 starbucks | none | No inner_bg | unchanged |
| **7 LEGO** | **§14 @0.88** | **YES — §14 only** | **§14 → `card`** |
| 8 ferrari | none | No inner_bg | unchanged |
| 9 slate | none | No inner_bg | unchanged |
| 10 mammut | none | No inner_bg | unchanged |

### (B) Design truth — manual_component_build.html #16 (L1195-1276)
Wrapper: `<table role="presentation" width="440" align="center" cellpadding="0" cellspacing="0" border="0"
bgcolor="#ffffff" class="wf" style="background-color:#ffffff;border-radius:18px;border-collapse:separate;
overflow:hidden;">`. Rows:
- logo: `<td style="padding:20px 0 0 0;line-height:0;font-size:0;"><img … width="440" max-width:440px>`
- name/email: `<td align="center" style="background-color:#ffffff;padding:10px 24px 0 24px;font-family:'Noto
  Sans',Arial,sans-serif;font-size:14px;line-height:19px;font-weight:600;color:#000000;mso-line-height-rule:
  exactly;"><span style="font-size:16px;line-height:22px;">Andy</span><br /> email@brand.emaillove.com</td>`
- barcode: `<td style="padding:30px 0 20px 0;line-height:0;font-size:0;"><img … width="440" max-width:440px>`
- bottom-shape: `<td style="padding:0;line-height:0;font-size:0;"><img … width="440" max-width:440px alt="" role="presentation">`
Asset-name trap (Rule 5): `footer-card.png`=logo, `footer-social.png`=barcode, `footer-logo.png`=shape.
(The design's decorative-shape `alt=""` is NOT reproduced verbatim — use `_derive_image_alt` to stay G3-neg-safe.)

### (C) Baseline prediction
- c7 `expected.html` §14: image-gallery block (3 `<div class="column">` tiles, ~L823-877) → one `cell`-hosted
  card `<table width="440" … border-radius:18px>` with 4 rows incl. restored text. Substantial single-section diff.
- c5/c6/c8/c9/c10: byte-identical (routing unchanged — probe). Ladder `13/9/8/10/8/12` invariant (card is
  still one section). A3: c7 `section_min ~0.351` → up; `full_image`/`section_median` up; others flat.

### (D) Why fill-a-cell, not the composite splice
`render_composite`/`_splice_rows_after_slot` (G4) INSERT a row after a reference slot — correct for own-row
CTA, wrong for a whole-section card (would leave an empty anchor row above the card). The card is a
self-contained table filling one cell → a text/html fill of `cell`'s `content` slot. This also sidesteps the
`tree_bridge` composite-skip (`phase-53g-g4-tree-html-slot-row-shape`): a text fill is handled by the normal
slot path.

## AMENDMENTS

- 2026-07-19 — created.
- 2026-07-19 (execution) — **Host seed `cell` → `td`.** VERIFY-1 found `cell.html` uses unresolved
  seed-default mustache (`{{ align || 'center' }}` …) that the converter doesn't resolve → literal
  `{{ }}` leaked into the card td. Switched to the registered `td` ("Table Cell") seed — clean single
  `content` slot, no mustache. Nothing else routes to `td`; it is in `COMPONENT_SEEDS`.
- 2026-07-19 (execution) — **Two render-integration traps fixed inside the card fill** (found via live
  render probes, not in the plan): (a) the section container-bg override's `_replace_first_css_prop`
  clobbers the first inline `background-color` in the component, so the card's white now rides on the
  `bgcolor` ATTR only (no inline bg) → the override correctly falls through to paint the `td` outer band;
  (b) `data-node-id` omitted from card `<img>`s so the Rule-10 `_apply_image_corner_radius` override can't
  stamp per-corner radii (the card clips via `overflow:hidden`).
- 2026-07-19 (execution) — **Rule 11 width source confirmed:** `inner_card_fixed_width` is `None` for this
  card (images nested below the frame → `rule_11` doesn't fire); width reads `max(img.width)` = 440.
- 2026-07-19 (execution) — **VERIFY-3 result:** the tree path (non-default) HTML-strips the card text fill
  → card degrades to plain identity text. Renderer path (default, drives expected.html) is correct.
  Ledgered `phase-53g6-card-tree-path-text-only` (mirrors the G4 tree-path deferral); not fixed in G6.
- 2026-07-19 (execution) — **lint-numeric:** the project forbids `or <number>` in design_sync; the two
  `or 600`/`or 0` defaults were rewritten to explicit `is not None` (satisfies both lint-numeric and ruff
  FURB110). `make check-full` GREEN. **Result:** c7 full_image 0.771→0.893, section_min 0.351→0.778,
  section_median 0.804→0.909; zero trade; ledger `phase-53f-f7-image-gallery-membership-card` CLOSED.
