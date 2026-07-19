# Feature: Spec mini-table + multi-line + hug-row centering (Track G · G7 / 51.4 + 51.5, M4 + M6)

> Prompt 7 of the frozen Track-G sequence (`53-g-production-readiness-prompt-sequence.md`).
> Promotes TRIAGE stubs `51.4-spec-mini-table-slot` + `51.5-multi-line-text-splitter`,
> plus the M6 hug-content fix. Refs pinned to main `a660262c`; verified against the
> **live tree** (branch `fix/phase-53g6-card-composite` @ `504c6c00`) — symbols re-anchored
> below because line numbers drifted since the audit snapshot.

## Feature Description

Two design-fidelity defects, one root cause: **the converter flattens HORIZONTAL
auto-layout frames into full-width vertical stacks.**

- **M4 (c7 #10–13 product specs, c8 grids, c9 icon rows):** a spec pair
  `[icon 16–26px | 617⏎Pieces]` sits inside a product-card column. The design lays icons
  and labels side-by-side (a mini-table); the converter emits each icon and each label as
  its own full-width `<tr>`.
- **M6 (c7 #15 user-info):** the `Andy | 0 | …` row is a 4-cell **hug-width, centered**
  strip (each cell ≈60px, Σ=240 in a 600 container) with a `border-left` divider on the
  count group. The converter routes it to a `column-layout-4` seed and spreads it across
  **4 × 138px equal columns** with no divider.

## User Story

As a designer converting a Figma email with product-spec mini-tables and compact centered
info rows, I want the converter to preserve the horizontal layout, the stacked value/label
text, and the cell divider, so the exported HTML matches my design instead of exploding
each icon and label onto its own full-width line.

## Problem Statement

`_build_column_fill_html` (component_matcher.py:1046) renders every column element as its
own `<tr>` in design y-order (F10) but has **no horizontal sub-grouping** — so icon+label
runs stack. Separately, the `column-layout-*` width path (`_apply_column_width_fractions`,
component_renderer.py:2106) honors *fraction* asymmetry but always fills the container
width, so a hug-content row (Σcols ≪ container) is force-spread to equal 138px cells and
its per-cell stroke is never emitted.

## Solution Statement

Four surgical mechanisms, ordered by risk/value (all render/matcher-side; **no schema
round-trip, no `individualStrokeWeights` ingest** — see NOTES for why the prompt's ingest
premise is superseded by the data):

1. **Multi-line → `<br>` (51.5, M4·b):** normalize `\n`, ` `, `\r\n`, ` ` to
   `<br />` in the column text renderer. The design encodes `617\nPieces` / `+260 …`
   as **one TEXT node** with a separator + uniform font — so the "splitter" is a cell-text
   normalization, **not** node-splitting (confirmed: no per-line font-weight in the data;
   TRIAGE's "`\n`→`<br>` fallback may already suffice" = yes, once ` ` is included).
2. **Hug-content centering (M6·a):** in the `column-layout-*` width path, when Σ(design
   column widths) is well under the container, render at content width, `margin:0 auto`,
   each `<td>` at its design px — instead of equal-splitting the container.
3. **Spec mini-table pairing (51.4, M4·a):** in `_build_column_fill_html`, detect an
   adjacent `(icon-image ≤30px, short-text <40 chars)` run in the existing `content_order`
   interleave and emit **one** centered horizontal `<td>×N` mini-table row instead of N
   full-width rows. **Matcher-only, direct HTML** (the G4 composite seam is for section
   seed slots, not the intra-column builder — not used here).
4. **Border-left divider (M6·b, deferrable polish):** thread the source column's already-
   ingested uniform `stroke_color/stroke_weight` onto `ColumnGroup`; emit `border-left` on
   the hug cell that carries a stroke. Ledger the true per-side (`individualStrokeWeights`)
   capture as a deferred generalization gap.

## Out of Scope / Non-Goals

- **NOT fixing** c7 user-info icon width inflation (30→60px) — that is the frame-wrap
  ingest bug `phase-53f-decorative-image-flag`, explicitly deferred to **Prompt 11**. If it
  surfaces in a diff, leave it; do not lower the `c.width > 40` gate.
- **NOT** capturing `individualStrokeWeights` per-side strokes (Mechanism 4 uses the
  already-ingested uniform stroke + horizontal-row-cell position; per-side → ledgered).
- **NOT** adding a `spec-list.html` component or the 51.4-stub `SpecListSlot` schema — the
  mini-table is built inline in the column builder (stub's "sub-row of existing component,
  cheaper" fork; the standalone-component fork is dropped).
- **NOT** touching `_card_text_row`'s existing `\n`-only replace unless it lands in the
  diff (it has the same latent ` ` gap but no corpus case exercises it — note only).
- **NOT** the nested mj-divider LINE gap (`phase-53.5-nested-divider-render-gap`) — that is
  a *row* rule, distinct from Mechanism 4's *cell border-left*.

## Feature Metadata

**Feature Type:** Enhancement (fidelity) · **Complexity:** High (4 mechanisms, 2 code paths)
**Primary Systems:** `component_matcher.py` (column fill builder), `component_renderer.py`
(column-layout width path), `figma/layout_analyzer.py` (ColumnGroup stroke thread only)
**Dependencies:** none new. Builds on F6/F10 `content_order` interleave
(`phase-53f-column-category-order`, CLOSED) and the D2/A8 `column_width_fractions` path.

## Related Work

**Implements:** Track-G Prompt 7 (51.4 + 51.5 + M6). **Epic:** `.agents/plans/53-g-production-readiness-prompt-sequence.md`.

**Back-references:**
- `.agents/plans/53-g4-composite-slot-infrastructure.md` — the composite seam (deliberately
  NOT reused here; see NOTES).
- `.agents/plans/53-g6-card-composite.md` — routing-map + diff-audit discipline mirrored in
  Phase 0. The user-info row is a **standalone section**, NOT a child of the G6 card
  (verify in Phase 0 it does not route into the card renderer).
- `.agents/plans/deferred/51.4-spec-mini-table-slot.md`, `51.5-multi-line-text-splitter.md`,
  `TRIAGE-2026-06-12.md` (KEEP row 51.4/51.5).

**Forward-references:** (none yet) — Prompt 8 (51.6 footer) is next in the chain.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `app/design_sync/component_matcher.py:1046-1070` (`_build_column_fill_html`) — **Mech 3
  insertion (matcher).** Iterates `_ordered_column_elements`; each element → one `<tr>`.
- `app/design_sync/component_matcher.py:1022-1043` (`_ordered_column_elements`) — the F10
  `content_order` interleave that yields `[icon, value, icon, value]`. **Mech 1 reads this.**
- `app/design_sync/component_matcher.py:703-769` (`_column_text_row`) — **Mech 2 site.**
  Line 769 emits `_safe_text(text.content)` with **no** `\n` handling.
- `app/design_sync/component_matcher.py:920-948` (`_column_image_row`) — icon cell markup
  to mirror for the mini-table icon `<td>`; width-pin at `_STACK_NATURAL_WIDTH_MAX` (:1098).
- `app/design_sync/component_matcher.py:625-627` (`_safe_text`) — html-escape only; the
  `\n`/` ` normalization goes in the row builders, not here (keep `_safe_text` pure).
- `app/design_sync/component_matcher.py:1209-1230` (`_card_text_row`) — precedent for
  `.replace("\n","<br />")` in a cell (G6). Mirror + extend to ` `.
- `app/design_sync/component_renderer.py:623-670` (`render_section`) — calls
  `_apply_column_width_fractions` (:658); `column-layout` branch (:662). **Mech 3 render.**
- `app/design_sync/component_renderer.py:2106-2155` (`_apply_column_width_fractions`) —
  redistributes per-`<td>`/div widths by `column_width_fractions`; equal-within-tolerance
  is a no-op (:2124) → why hug rows stay 138px. **Mech 3 hooks alongside this.**
- `app/design_sync/figma/layout_analyzer.py:141-156` (`ColumnGroup`) — has `width`,
  `content_order`; **no stroke field** → Mech 4 adds `stroke_color/stroke_weight`.
- `app/design_sync/figma/layout_analyzer.py:1177-1205` (`_detect_column_layout_with_groups`)
  — Strategy-1 MJML `_detect_mj_columns`; Strategy-2 `HORIZONTAL` gated on `c.width > 40`
  (**do not lower** — spec sub-cols are 26/30/40 by design). Mech 4 populates ColumnGroup
  stroke where columns are built (`_build_column_groups` / `_detect_mj_columns`).

### Ground-truth data (c7, verified this session)

Spec `mj-table-row` (HORIZONTAL, w=260), children alternate icon/text columns:
```
column w=26 VERTICAL → IMAGE 16×22          (icon)
column w=40 VERTICAL → TEXT '617\nPieces'   (value⏎label)
column w=30 VERTICAL → IMAGE 26×26          (icon)
column w=164 VERTICAL → TEXT '+260 LEGO® Insiders Points'
```
User-info `mj-section` (HORIZONTAL, w=440), 4 × `mj-column` w=60 (Σ=240 ≪ 600):
```
mj-column w=60 → IMAGE 30×30
mj-column w=60 → TEXT 'Andy'
mj-column w=60 STROKE=#D9D9D9/1.0 → IMAGE 30×30   ← divider source (border-left)
mj-column w=60 → TEXT '0'
```
Separators in c7: **9 `\n` + 2 ` `** (the `+260` cell uses ` `). User-info renders
at `4×138px` today (expected.html:742–798).

### Patterns to Follow

- **Cell text normalization:** `_card_text_row` (:1211) `content = _safe_text(...).replace("\n","<br />")`
  → extend to a shared helper `_multiline_to_br(text)` handling `\r\n|\n| | `.
- **Icon width-pin:** sub-`_STACK_NATURAL_WIDTH_MAX` images render at native px
  (`_column_image_row`/`_stacked_image_row`) — reuse for mini-table icon cells.
- **Diff-audit discipline (every phase):** regen baselines via
  `scripts/snapshot-capture.py <case> --overwrite`, strip trailing ws
  (`sed -i '' 's/[[:space:]]*$//'`), `git diff data/debug/` line-by-line = only the
  intended rows. `git restore` `skill-versions.yaml` stamps before staging (Track-G invariant).
- **Test-first:** every mechanism gets a RED-proven unit test in
  `app/design_sync/tests/` before the fix.

---

## IMPLEMENTATION PLAN

### Phase 0: Routing map + interleave confirmation (pre-code gate) — ✅ DONE

**Independent of:** all — ran first; gated blast radius. Report:
`.claude/code-reviews/53-g7-routing-map.md` (via `scratchpad/g7_routing.py`).

**A1 CONFIRMED:** the c7 spec run arrives in **one ColumnGroup**, content_order
`[name-txt, img(26), '617\nPieces', img(30), '+260⏎…', btn]` → predicate returns **pairs=2**.
Mechanism 1 stays matcher-only in `_build_column_fill_html`. User-info (§17) is a standalone
`multi-column cols=4` (Σ=240 ≪ 600), separate from the G6 card (§19).

**Blast radius (fires ✓ / excluded ✗):**

| Case | Mech 1 spec | Mech 2 `<br>` (`_column_text_row`) | Mech 3 hug | Mech 4 divider |
|---|---|---|---|---|
| c7 | ✓ §9/11/13/15 | ✓ spec cells §9/11/13/15 | ✓ §17 (Σ=240) | ✓ §17 col[2] |
| c8 | ✗ text-only pairs, no icon | ✗ §6/§8 headings route via text-block seed (out of scope) | ✗ §9 Σ=600 | ✗ |
| c9 | ✗ img=34>30, 1 pair | ✓ §3 labels (`The Place: ⏎…`) | ✗ | ✗ |
| c10 | ✗ no pairs | ✗ (no `_column_text_row` multi-line) | ✗ Σ=536 | ✗ |

**Consequences:** Mech 1 is **c7-only** (`img≤30` separates c7's 26/30px icons from c9's
34px). Mech 2 is scoped to `_column_text_row` (column-group text) → touches **c7 + c9 only**;
c8 §6/§8 multi-line headings render via the **text-block seed** (`data-slot="heading"`), a
different path — their `\n`-collapse is a **pre-existing latent, out of G7 scope** (do not
extend Mech 2 into `_fills_text_block` here). c7 card §19 `Andy\nemail` is already handled by
G6's `_card_text_row`. Mech 3/4 are c7-§17-only.

### Phase 1: Multi-line → `<br>` (Mechanism 2 · 51.5)

**Independent of:** Phases 2–4 (pure cell-text change).

- **Tasks:**
  - ADD `_multiline_to_br(text: str) -> str` in component_matcher.py near `_safe_text`:
    `html.escape` then replace `\r\n|\n| | ` → `<br />` (single regex).
  - UPDATE `_column_text_row` (:769) to use it. UPDATE `_card_text_row` (:1211) to the
    shared helper too **iff** its baseline stays byte-identical (c7 card `Andy\nemail…`
    already emits `<br/>`; adding ` ` coverage must not churn — verify).
  - The spec mini-table cell renderer (Phase 3) uses the same helper.
- **Corpus effect:** c7 spec value cells gain a mid-cell `<br>` (`617<br>Pieces`,
  `+260<br>LEGO® Insiders Points`). Diff-audit to those lines only.

### Phase 2: Hug-content column-layout centering (Mechanism 3 · M6·a)

**Depends on:** Phase 0 (confirm user-info path). **Independent of:** Phases 1, 3.

- **Tasks:**
  - In the `column-layout-*` render path (`render_section` :658 / a new sibling to
    `_apply_column_width_fractions`), compute `col_px = [cg.width for cg in
    match.section.column_groups]`. **Hug predicate:** all widths present AND
    `sum(col_px) <= container * _HUG_MAX_FRACTION` (start `0.9`).
  - When hug: rescale the seed's per-`<td>`/div widths to the design px (60 each), set the
    outer column table to fixed content width (Σ=240) + `align="center"` /
    `margin:0 auto`, add `white-space:nowrap` on the cells. When NOT hug → **untouched**
    (normal 2-col ≈276px each ≈ container → byte-identical; guard with the predicate).
  - Reuse/extend the existing width-rewrite regex machinery in
    `_apply_column_width_fractions` rather than a parallel parser.
- **Corpus effect:** c7 user-info → centered 4×60 strip. No other case has a hug row
  (verify via Phase 0 map; c8/c10 grids are full-width by design).
- **VALIDATE:** RED test: a synthesized `column-layout-4` match with `column_groups` widths
  `[60,60,60,60]` in a 600 container → output carries `margin:0 auto` + `width:60` td, not
  `138`. Equal-but-full-width control (`[276,276]`) → unchanged.

### Phase 3: Spec mini-table pairing (Mechanism 1 · 51.4) — the core

**Depends on:** Phase 1 (`_multiline_to_br` for cell text), Phase 0 (insertion confirmed).

- **Tasks:**
  - ADD `_group_spec_pairs(elements) -> list[list[Element] | Element]` (matcher): scan the
    `_ordered_column_elements` sequence; a **spec run** = ≥2 consecutive
    `(ImagePlaceholder width≤30, TextBlock len(content.strip())<40)` pairs (51.4 stub
    predicate). Emit the run as a group; everything else passes through unchanged.
  - ADD `_spec_minitable_row(pairs) -> str`: one `<tr>` inside the column table with, per
    pair, an icon `<td valign="middle">` (native-width `<img>`, mirror `_column_image_row`)
    + a value/label `<td valign="middle" style="text-align:left">` (via `_multiline_to_br`).
    Center via `align="center"` on the row / wrapper. Icon cell width = icon px; text cell
    natural.
  - UPDATE `_build_column_fill_html` (:1058-1070): route spec-run elements through
    `_spec_minitable_row`, non-run elements through the existing per-element rows. Preserve
    F10 order (the run occupies its position in the sequence).
  - **No** `render_composite`/`_splice_rows_after_slot` — direct HTML in the builder.
- **Corpus effect (predict, then diff-audit):** c7 #10–13 spec rows collapse from N
  full-width rows → one mini-table row each. **c8 spec grids / c9 icon rows route the same
  builder** — expected to improve or hold; if the predicate misfires there, tighten it
  (size/length thresholds) rather than special-casing.
- **VALIDATE:** RED test: a ColumnGroup with content_order `[icon26, '617\nPieces',
  icon30, '+260 …']` → one `<tr>` with 4 `<td>` (2 icon, 2 text), `617<br>Pieces`,
  icons at native width; a single icon+text (1 pair) → **no** mini-table (falls back).
  Non-spec column (heading+body+cta) → byte-identical to pre-G7.

### Phase 4: Border-left divider (Mechanism 4 · M6·b) — deferrable polish

**Depends on:** Phase 2 (shares the hug/column-layout render). **Sequence last.**

- **Tasks:**
  - ADD `stroke_color: str | None`, `stroke_weight: float | None` to `ColumnGroup`
    (layout_analyzer.py:141). Populate from the source column DesignNode in the column
    builders (`_build_column_groups` / `_detect_mj_columns`). *(ColumnGroup is rebuilt from
    the tree each run — no structure.json round-trip. **Grep for any ColumnGroup
    serializer** (`email_design_document.py`, `protocol.py`) and thread the field if one
    exists — #327 lesson.)*
  - In the hug render (Phase 2), emit `border-left:{weight:.0f}px solid {stroke_color}` on
    the `<td>` whose ColumnGroup carries a stroke. **`border-left` specifically** — a full
    `border` paints a box, not a divider.
  - LEDGER a new `phase-53g-g7-per-side-stroke-capture` (deferred, speculative):
    `individualStrokeWeights` not captured; border-left inferred from the uniform stroke +
    horizontal-row-cell position; closes_when a real fixture needs a non-left per-side edge.
- **Corpus effect:** c7 user-info 3rd cell gains `border-left:1px solid #D9D9D9`.
- **Fallback:** if this destabilizes c8/c9 or the diff is noisy, **defer Phase 4** to a
  follow-up and ship 1–3 (record as an AMENDMENT). Centering (Phase 2) is the score-mover;
  the divider is polish.

---

## STEP-BY-STEP TASKS

### PHASE 0 — MAP `scripts/` + fixtures
- **IMPLEMENT:** routing dump script over c7/c8/c9/c10; content_order dump for a c7 card.
- **PATTERN:** G6 routing map (`.claude/reports/53-g4-*-report.md` method note).
- **VALIDATE:** `uv run python <dump>.py` → map + confirmed interleave.
- **SATISFIES:** blast-radius gate for AC "c8/c9 re-verified".

### ADD `_multiline_to_br` + UPDATE `_column_text_row` (Phase 1)
- **IMPLEMENT:** shared helper; regex `[\r]?\n| | ` → `<br />` post-escape.
- **PATTERN:** `_card_text_row` :1211.
- **GOTCHA:** must cover ` ` (2 nodes in c7) — `\n`-only fails the `+260` cell.
- **VALIDATE:** `uv run pytest app/design_sync/tests/test_multi_line_text.py -q` (RED first).
- **SATISFIES:** 51.5 / M4·b.

### ADD hug detection + centering (Phase 2)
- **IMPLEMENT:** `_HUG_MAX_FRACTION`; hug branch in the column-layout width path.
- **PATTERN:** `_apply_column_width_fractions` :2106 width-rewrite regex.
- **GOTCHA:** predicate must NOT fire on full-width equal splits (byte-stability).
- **VALIDATE:** `pytest …::TestHugColumnCentering` (RED first); c7 user-info diff = width/align only.
- **SATISFIES:** M6·a.

### ADD `_group_spec_pairs` + `_spec_minitable_row` + UPDATE `_build_column_fill_html` (Phase 3)
- **IMPLEMENT:** pairing predicate (img≤30, text<40, ≥2 pairs) + horizontal row builder.
- **PATTERN:** `_column_image_row` (icon cell), `_multiline_to_br` (text cell).
- **GOTCHA:** matcher-only; do NOT reuse the G4 composite seam; single-pair → no mini-table.
- **VALIDATE:** `pytest …::TestSpecMiniTable` (RED first); c7/c8/c9 diff-audit.
- **SATISFIES:** 51.4 / M4·a.

### ADD ColumnGroup stroke + border-left emit + LEDGER (Phase 4)
- **IMPLEMENT:** stroke fields + populate + `border-left` on stroked hug cell.
- **PATTERN:** `_column_cta_row` border shorthand (:962-964) for hex-safe border css.
- **GOTCHA:** `border-left` only; grep ColumnGroup serializers before adding the field.
- **VALIDATE:** `pytest …::TestUserInfoDivider` (RED first); ledger entry added.
- **SATISFIES:** M6·b.

### GATES + CLOSE-OUT (Phase 5)
- **IMPLEMENT:** `make check-full`; A3 re-score; baseline regen diff-audit; TODO.md Track G.
- **VALIDATE:** `make check-full` exit 0; A3 c7 up, c8/c9 flat-or-up.
- **SATISFIES:** Definition of Done + anti-drift close-out.

---

## TESTING STRATEGY

### Unit Tests (RED-proven, `app/design_sync/tests/`)
- `test_multi_line_text.py` — `_multiline_to_br` on `\n`, ` `, `\r\n`, ` `, plain.
- `test_spec_mini_table.py` — `_group_spec_pairs` (≥2 pairs → run; 1 pair → passthrough;
  no icons → passthrough) + `_spec_minitable_row` markup (cell count, `<br>`, native width).
- `test_hug_column_centering.py` — hug predicate boundary (`[60,60,60,60]`/600 → hug;
  `[276,276]`/600 → not hug) + rendered `margin:0 auto` / per-td px.
- `test_user_info_divider.py` — ColumnGroup stroke threads → `border-left:1px solid #D9D9D9`
  on the str'd cell only.

### Integration / snapshot
- `scripts/snapshot-capture.py {7,8,9,10} --overwrite` → `git diff data/debug/` audited to
  only the intended rows. c5/c6 expected byte-identical (no spec/hug rows) — verify.

### Edge Cases
- ` ` cell (the `+260` node) — the specific case `\n`-only would miss.
- Single icon+text pair (no mini-table). Three-line text (defer per 51.5 OQ; `<br>` handles
  it acceptably as N lines). Hug row with a missing column width → predicate declines (safe).

---

## VALIDATION COMMANDS

- **L1 Syntax/style:** `uv run ruff check --no-fix app/design_sync/` · `uv run ruff format --check app/design_sync/`
- **L2 Types:** `uv run mypy app/design_sync/` · `uv run pyright app/design_sync/`
- **L3 Unit:** `uv run pytest app/design_sync/tests/test_{multi_line_text,spec_mini_table,hug_column_centering,user_info_divider}.py -q`
- **L4 Snapshot/fidelity:** `uv run pytest app/design_sync/tests/ -k snapshot -q` ·
  `uv run python scripts/score-fidelity-cases.py` (A3 — **local-only; PNG assets gitignored,
  so this is NOT a CI gate**; the committed `structure.json`/`expected.html` byte-diff IS).
- **L5 Full gate:** `make check-full`.

---

## ACCEPTANCE CRITERIA

- [ ] c7 spec rows render as one-line `[icon | value⏎label]` pairs (mini-table), not stacked.
- [ ] c7 user-info renders compact **centered** 4×60 strip with a `border-left` divider.
- [ ] `\n` AND ` ` both become `<br>` in spec value cells (`+260` cell correct).
- [ ] c8 spec grids / c9 icon rows re-verified via Phase-0 map; any change diff-audited to
      the mechanism; **A3 c7 up, c8/c9 flat-or-up** (≤0.005 regression tolerance).
- [ ] `data/debug/` baseline diff contains only intended rows; c5/c6 byte-identical.
- [ ] RED-proven unit test per mechanism; `make check-full` exit 0.
- [ ] `phase-53f-decorative-image-flag` NOT touched (icon-inflation stays Prompt 11).
- [ ] Ledger: 51.4/51.5 promotion recorded; `phase-53g-g7-per-side-stroke-capture` added.
- [ ] Anti-drift close-out (see below) done.

---

## COMPLETION CHECKLIST

- [ ] Phases 0→4 executed in order; each validation passed before the next.
- [ ] `make check-full` GREEN; A3 table before/after recorded in the report.
- [ ] Baselines regenerated (not hand-patched) + diff-audited; ws-stripped to committed bytes.
- [ ] `git diff` isolates only G7 changes (no parallel-branch leakage; `skill-versions.yaml` restored).
- [ ] `.claude/reports/53-g7-spec-minitable-report.md` written (mirror G4/G6 report shape).
- [ ] TODO.md Track G status refreshed; later G-prompts patched where G7 invalidated refs.

---

## OPEN QUESTIONS / ASSUMPTIONS

- **A1 (load-bearing) — ✅ CONFIRMED (Phase 0):** the spec run arrives in **one
  ColumnGroup** with content_order `[name, img, value, img, value, btn]`, predicate pairs=2.
  Mechanism 1 stays matcher-only.
- **A2:** hug threshold `_HUG_MAX_FRACTION=0.9` — tune against all 6 fixtures so no
  full-width equal split flips to hug.
- **Q1 (scope):** if the Phase-3 diff on c8/c9 is large/ambiguous, **split Phase 3 into its
  own PR** (spec mini-table) from Phases 1–2+4 (multi-line + user-info). Flagged per the
  advisor; decide at diff-audit, record as AMENDMENT, don't force one PR.
- **Q2:** three-line text (`$29⏎/month⏎Save 40%`) — `<br>` renders all lines; the 51.5
  value/label-pair semantics are not needed (data has no per-line weight). Deferred unless a
  real fixture needs distinct per-line styling.

## NOTES (open canvas)

**Why the prompt's stated mechanisms are re-aimed (verified against the live tree + c7 data):**

1. *"matcher groups same-row runs by y-band + x-order like peel_row"* → **matcher-only via
   `content_order`, no x/y.** `TextBlock`/`ImagePlaceholder`/`ButtonElement`
   (layout_analyzer.py:73/95/112) carry **no x/y** — they're lost at extraction. But
   `_peel_rows` (layout_analyzer.py:742) needs `DesignNode.x/y`, which only the raw tree
   has. F6/F10 already restore vertical order via `content_order`; the spec pairs arrive
   adjacent in it. So pairing is an adjacency scan in the column builder — **no analyzer
   change, no new fields, no round-trip.** (Biggest simplification vs the prompt.)
2. *"51.5 splitter: text nodes with `\n` emit stacked value/label rows"* → **cell-text
   `<br>` normalization.** The value is **one** TEXT node (`617\nPieces`) with uniform font;
   there is no per-line weight to split on. TRIAGE's "verify `\n`→`<br>` suffices" = yes,
   **plus ` `** (the `+260` cell) which a `\n`-only replace silently drops.
3. *"ingest: capture per-side strokes (`individualStrokeWeights`)"* → **already ingested as
   uniform.** structure.json carries `stroke_color=#D9D9D9, stroke_weight=1.0` directly on
   the divider column node. Mechanism 4 is render-only (emit `border-left`); the true
   per-side capture is ledgered as a generalization gap, not built (Simplicity First). Note:
   `raw_figma.json` shows no stroke node for this band → it is partial/stale; **trust
   structure.json + the prompt's stated border-left intent, not raw_figma.**
4. *G4 composite seam* — `render_composite`/`_splice_rows_after_slot` inject rows after a
   **section seed slot**; the intra-column builder emits raw HTML directly, so the spec
   mini-table is a direct build. Forcing the composite abstraction here would be
   over-engineering.

**Deferred-items touching this plan (preflight grep):**
- `phase-53f-column-category-order` (CLOSED) — content_order interleave Mech 1 depends on. ✅
- `phase-53f-decorative-image-flag` (DEFERRED) — user-info icon 30→60 inflation. **Out of
  scope → Prompt 11.** Do not fix; leave in diff if it appears.
- `phase-53.5-nested-divider-render-gap` (DEFERRED) — mj-divider *row* rule; distinct from
  Mech 4's *cell* border-left. Not closed here.
- `phase-53g-g5-pill-white-on-light-latent` (DEFERRED) — unrelated (pill color).

**Anti-drift close-out (prompt-mandated):** after gates pass, update **TODO.md § Track G**
— refresh the intro status row if A3 scores moved, and patch any LATER G-prompt (Prompt 8
footer, 9 Outlook, 10 re-score) whose `file:line` refs / scores / mechanism claims this
change invalidated. Frozen snapshot `53-g-production-readiness-prompt-sequence.md` stays
untouched (provenance). TODO.md is gitignored → local-only edits.

## AMENDMENTS

- 2026-07-19 — **Executed.** Deviations from plan (all in the report):
  - **Mech 2 scoped to `_column_text_row`** → touches c7 + c9, NOT c8 (c8 §6/§8 multi-line headings
    render via the text-block seed `data-slot="heading"`, a different path — left as a pre-existing
    latent, out of scope). Plan blast-radius table corrected.
  - **Mech 4 (divider) hug-scoped** after a blast-radius surprise: the first cut emitted `border-left`
    on every stroked column and fired on c9 §3 (#545454 on col_1+col_2 — a left border on the first
    column is wrong). Gated on `_is_hug_row`; c9 reverted to byte-identical. Locked by a test; general
    per-column-stroke render ledgered as `phase-53g-g7-per-side-stroke-capture`.
  - **Hug render ordering:** hug widths are re-shrunk by the F9 `render_repeating_group` inset; fixed by
    gating BOTH F9 shrink sites off for hug rows (`_is_hug_row`) rather than ordering alone.
  - **A3 finding (corrected after an advisor catch — first two measurements were section-cache/CLI
    confounded):** rigorous **cache-off** (`DESIGN_SYNC__SECTION_CACHE_ENABLED=false`), stash-verified:
    c7 full_image 0.893→0.894 (+0.001) · median 0.909→0.914 (+0.005) UP · **section_min 0.778→0.708
    (−0.070)** — a per-band-REALIGNMENT trade (shorter side-by-side specs shift section heights → fixed
    bands misalign; bands moved both ways), NOT a broken feature. The mini-table renders correctly
    side-by-side (visually confirmed). Ratifiable like G2/G3/G4. c9 +0.004. **The Redis section cache
    poisons the fidelity harness** — score cache-off. Q1 (split) resolved: one PR (c8 byte-identical,
    c9 = `<br>` only).
  - **Schema (advisor catch):** `DocumentColumn.to_json` emits stroke without a v1-schema entry →
    `additionalProperties:false` rejects it on the app validation path. Added stroke_color/weight
    (+ content_order, F10's pre-existing gap) to `/$defs/column`.
  - Lint: `lint-numeric` banned `round(g.width or 0)` → switched to an `is not None` filter; ambiguous
    Unicode (`×`/U+2028) in docstrings/regex scrubbed to ASCII/escapes.
  - **Ratified 2026-07-19:** user ratified the c7 section_min −0.070 trade (design-correct-vs-coarse-scorer,
    like G2/G3/G4) → commit + PR (targeting the G6 branch; G7 stacks on unmerged G6). `make check-full` GREEN.
