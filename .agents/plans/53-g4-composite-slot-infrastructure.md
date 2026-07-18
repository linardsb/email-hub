# Feature: Composite-slot infrastructure (51.1) + own-row CTA first consumer (Track G · G4 / M8)

The following plan should be complete, but validate documentation, codebase patterns, and task
sanity before implementing. **Symbols are the anchor** — line numbers are HEAD-relative
(`origin/main` @ `9d66eae5`, post-G3 #353) and WILL drift; re-grep the symbol if a line ref
misses. Pay special attention to the TWO `SlotFill` classes (see Gotcha): the target is
`app/design_sync/component_matcher.py:29`, NOT `app/ai/agents/schemas/build_plan.py:23`.

## Feature Description

The composite chain (cards-with-pills, membership cards, spec mini-tables, composite footers —
6 stubs in `.agents/plans/deferred/TRIAGE-2026-06-12.md`) is strictly ordered behind one
foundational piece: **51.1 composite-slot infrastructure**. Today a `SlotFill` can only carry a
flat string; a slot cannot hold a *rendered sub-component*. This ticket ratifies and builds the
minimal composite seam — a `composite` variant on `SlotFill` + a depth-capped children-rendering
loop (the sub-renderer) + a splice-after-slot injection primitive — and proves it with its first
consumer: **own-row CTA emission in `_fills_text_block`**, which currently folds CTA `<a>` anchors
*into* the body `<td>` so they inherit the body cell's left padding instead of centering on their
own row.

## User Story

As a **designer handing a Figma file to the converter**
I want **a CTA below a text block to render centered on its own row like the design**
So that **the email matches the design's vertical composition instead of a left-hugging inline link — and the converter gains the composite-slot seam every later card/pill/footer fix needs**.

## Problem Statement

1. **No composite seam.** `SlotFill` (`component_matcher.py:29-47`) is `slot_id | value | slot_type
   ∈ {text,image,cta,attr} | attr_overrides | stacked_before | stacked_after`. A builder can only
   emit flat strings or hand-built raw `<tr>` HTML (the `stacked_*` escape hatch, F1/F6). There is
   no structured way for a slot to contain a *rendered sub-component*, so cards can't hold pill
   rows, footers can't hold logo+social, etc. Every stub below 51.1 is blocked on this.
2. **Text-block CTA is left-hugging inline.** `_fills_text_block` (`component_matcher.py:1433-1441`)
   concatenates rendered `<a>` anchors into the `body` slot's `value`
   (`fills[idx] = SlotFill("body", body_fill.value + "\n" + cta_html)`). The CTA then renders
   inside the body `<td class="textblock-body" style="padding:0 24px 24px">` — left-aligned, in the
   body's horizontal padding — not centered on its own row. c7's hero 'Explore now' is the
   acceptance exemplar.

## Solution Statement

Add a **render-time-only** composite variant (no schema / round-trip / cache bridge — `SlotFill` is
never serialized, verified §NOTES A):

- **`SlotFill.slot_type` gains `"composite"`** + a new `composite: CompositeSlot | None = None`
  trailing field (default `None` → every existing construction stays valid → byte-compat).
- **`CompositeSlot`** (new frozen dataclass): `children: tuple[SlotFill, ...]`, `after_slot: str`
  (the `data-slot` id whose row the composite splices after), `cell_style`, `align`.
- **`render_composite(cs, depth=1)`** (the sub-renderer, module-level in `component_matcher.py`):
  one children-rendering loop with a **depth ≤ 3** cap. A child whose `slot_type == "composite"`
  re-enters the loop at `depth+1` (recursion is *inherent*, not a separate module); a terminal
  child contributes its `value`. Wraps the joined children in one centered `<tr><td>` row.
- **Injection = splice-after-slot** (no shared-template edit): a new
  `_splice_rows_after_slot` (mirror of the existing `_splice_rows_before_slot`,
  `component_renderer.py:1229`) inserts the rendered row after the reference slot's `</tr>`.
- **First consumer:** `_fills_text_block` emits the CTA as a `composite` "cta_row" fill
  (children = the pre-built, G3-styled anchors; `after_slot="body"`) instead of folding into body.
- **Second consumer (tree path):** one new `composite` branch in `tree_bridge._fill_to_slot_value`
  → `HtmlSlot(render_composite(...))`, so the `EmailTree` builder path keeps the CTA.

Byte-compat is proven in two checkpoints: **A** = infra landed, no composite fills → corpus
byte-identical; **B** = consumer wired → only c6/c7/c10 (the text-block-CTA cases) move.

## Out of Scope / Non-Goals

- **NOT a general sub-template recursion** — no `_fill_slots(sub_template, sub_fills, sub_slug, …)`
  recursive template rendering. Own-row CTA's children are terminal pre-built anchor HTML with no
  template substitution; a general sub-template renderer would ship with **zero real consumers**
  and synthetic-only tests (the consumer-less abstraction CLAUDE.md's Simplicity First forbids).
  The depth-cap + recursion *seam* is built; the general sub-template child is deferred to **51.2**
  (card/pills — the first genuine depth≥2 consumer). Ledger scope-cut entry per AC.
- **NOT `data-slot-composite` template markup** (the 51.1 stub's anchor-injection mode). Own-row
  CTA uses splice-after-slot; the anchor mode belongs to the first *nested-container* consumer
  (51.2, card body contains a pill row). YAGNI now.
- **NOT routing the CTA through `cta.html` / `cta-pair.html`.** Those carry hardcoded padding
  (`15px 30px`, `12px 32px`) and are the template-CTA surface **G3 deferred to 51.3**. The composite
  must **preserve the current anchor markup** (G3's `_cta_padding_css`, design colors/radius/stroke).
- **NOT `display:block` CTAs** — deferred by G3 (`project_lego_p50_target_recalibrated`); own-row is
  achieved by the wrapping centered `<td>`, anchors stay `inline-block`.
- **NOT changing column CTAs** (`_column_cta_row`, `component_matcher.py:884`) — a different path;
  c5's 8 pills + c8's 2 CTAs route there and must stay byte-identical.
- **NOT the AI/scaffolder `SlotFill`** (`app/ai/agents/schemas/build_plan.py:23`) — unrelated type.

## Feature Metadata

**Feature Type**: New Capability (foundational infrastructure) + Enhancement (fidelity).
**Estimated Complexity**: Medium — the code is small, but the risk is byte-compat completeness
across two consumers (renderer + tree bridge) and the scope discipline (not over-building recursion).
**Primary Systems Affected**: `app/design_sync/` — `component_matcher.py` (SlotFill + CompositeSlot
+ render_composite + `_fills_text_block`), `component_renderer.py` (`_fill_slots` dispatch +
`_fill_composite_slot` + `_splice_rows_after_slot`), `tree_bridge.py` (one branch), and the
`data/debug/{6,7,10}` snapshot baselines.
**Dependencies**: none new. G3 (#353) is in HEAD — the anchors already carry design geometry.

## Related Work

**Implements**: 51.1 composite-slot infrastructure (stub `.agents/plans/deferred/51.1-composite-slot-infrastructure.md`) · Track G · Prompt 4 (M8). Frozen source: `.agents/plans/53-g-production-readiness-prompt-sequence.md` (§Prompt 4) — **do NOT edit that snapshot**. Living copy: TODO.md § Track G.

**Back-references** (patterns this builds on):
- `_splice_rows_before_slot` / `_splice_stacked_rows` (`component_renderer.py:1229`/`:1204`, F6/F1) —
  the row-splice pattern `_splice_rows_after_slot` mirrors.
- G3 #353 (`_cta_padding_css`, design-derived anchor styling) — the anchor markup the composite
  wraps unchanged.
- F11 #331 (`phase-53-b8-text-block-solid-cta-text-color`) — the `_fills_text_block` CTA label-color
  thread; this ticket restructures the *placement* of those same anchors, not their styling.

**Forward-references**:
- **51.2** (card-with-N-children) — first depth≥2 consumer; consumes `render_composite` recursion +
  will add the `data-slot-composite` nested-container mode.
- **51.3** (tag-pill slot) — consumes composite children for pills; owns the template-CTA padding.
- 51.4/51.6 (spec mini-table, composite footer) — later composite consumers.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `app/design_sync/component_matcher.py:29-47` — `@dataclass(frozen=True) class SlotFill`. Add
  `composite` trailing field; extend the `slot_type` comment. **`from __future__ import annotations`
  (line 3) is present** → forward-ref to `CompositeSlot` (defined below the class) is safe.
- `app/design_sync/component_matcher.py:59-70` — `ComponentMatch` (holds `slot_fills: list[SlotFill]`).
  No change; context for how fills flow to both renderer and tree bridge.
- `app/design_sync/component_matcher.py:730-751` — `_cta_label_typography`; `:754-782`
  `_cta_padding_css` (G3). Read: the anchor styling the composite must preserve.
- `app/design_sync/component_matcher.py:884-908` — `_column_cta_row` (the OTHER CTA path; already
  emits its own `<tr><td>`). Do NOT touch — context for the byte-compat boundary.
- `app/design_sync/component_matcher.py:1353-1443` — `_fills_text_block`. The CTA build loop
  (`:1402-1432`) is unchanged; the fold at **`:1433-1441`** is what this ticket replaces.
- `app/design_sync/component_matcher.py:464-544` — `_build_slot_fills` dispatch registry; the slugs
  routing to `_fills_text_block` (`text-block`, `banner`, `col-gutter`, `heading`, `paragraph`,
  `icon`, `list`, `footer-unsub`, `app-store`, `font-inline` — `:478-543`). Context: `after_slot`
  must resolve on whatever template these slugs use (hence the body→heading→fallback ladder).
- `app/design_sync/component_renderer.py:892-966` — `_fill_slots` dispatch (`:936-941`) + post-fill
  passes. Add the `composite` branch at `:940`. Post-fill passes read only `.slot_id` / `.value`
  (`:947`,`:955`) — never `slot_type` — so a composite fill (value `""`, id `"cta_row"`) is inert to
  them; verified §NOTES B.
- `app/design_sync/component_renderer.py:1097-1135` — `_fill_text_slot` (honors `stacked_before`
  only). `:1204-1246` — `_splice_stacked_rows` / `_splice_rows_before_slot`: the mirror source for
  `_splice_rows_after_slot`.
- `app/design_sync/tree_bridge.py:110-146` — `_convert_slot_fills`. **`:142` positional rebuild
  fires ONLY for image-alt fills** (`fill.slot_type == "image"` guard at `:140`), so a `composite`
  fill passes through untouched — NO change needed at `:142` (verified). `:170-212`
  `_fill_to_slot_value`: add the `composite` branch **before** the unknown-slot_type fallback at
  `:204` (else composite→`None`→CTA dropped in tree path). `HtmlSlot` imported at `:10`.
- `email-templates/components/text-block.html` — the seed: two rows only, `<td data-slot="heading">`
  (`:7`) + `<td data-slot="body" class="textblock-body" style="padding:0 24px 24px">` (`:12`). No CTA
  row/slot. **Do NOT edit** (shared by ~10 slugs; splice-after-slot avoids touching it).
- `data/debug/{6,7,10}/expected.html` — the three baselines that move (regen). `data/debug/{5,8,9}`
  — must stay byte-identical.

### New Files to Create

- `app/design_sync/tests/test_composite_slot.py` — unit tests for `render_composite` (depth 1, depth
  cap, terminal children, recursion) + `_splice_rows_after_slot`. (Or extend `test_cta_fidelity.py` /
  `test_component_renderer.py` — see Testing Strategy; a dedicated file matches the 51.1 stub.)

### Relevant Documentation

- `.agents/plans/deferred/51.1-composite-slot-infrastructure.md` — the stub scope + open questions
  (this plan resolves: Rep = `list[SlotFill]`-under-loop, depth cap 3, no `HtmlSlot`-as-canonical).
- `.agents/plans/deferred/TRIAGE-2026-06-12.md` §"KEEP — composite-slot family" — the 6 ordered
  stubs; mark 51.1 **promoted** at close-out.
- `docs/architecture/opus-figma-to-html-process.md` Part 4 §3 (per the stub) — "single biggest
  leverage point — Gaps 2,3,4 collapse to 'add a composite slot'."

### Patterns to Follow

**Trailing default field for byte-compat.** Add `composite: CompositeSlot | None = None` LAST on the
frozen dataclass (mirror `stacked_before`/`stacked_after` at `:46-47`). Frozen-dataclass `__eq__`
compares the defaulted field equal on both sides, so every existing `SlotFill(...)` construction and
test stays valid.

**Render-time-only — no bridge.** Unlike DocumentButton (G3), `SlotFill` has NO `to_json`/schema/
round-trip (verified §NOTES A). Do NOT add schema props or round-trip methods.

**Splice-after mirrors splice-before.** `_splice_rows_after_slot` takes `_splice_rows_before_slot`'s
row-open anchor (last `<tr>` before the slot, `:1229`) and finds THAT row's matching `</tr>` via the
depth-counting `_find_matching_close` (`:216`, used by `_fill_text_slot` at `:1127`) — NOT a forward
`find("</tr>")`, which breaks on nested-table body cells (c10). Same defensive no-op contract.

**Extend, don't rewrite the CTA build.** `_fills_text_block:1402-1432` (anchor build) is unchanged;
only the fold at `:1433-1441` changes. Mirror F11's minimal-diff discipline.

---

## IMPLEMENTATION PLAN

Phases run top-to-bottom. **Phase 1** (types + sub-renderer) and **Phase 2** (renderer + tree
plumbing) are the *infrastructure* — landing them with NO consumer must leave the corpus
byte-identical (Checkpoint A). **Phase 3** (wire `_fills_text_block`) is the consumer (Checkpoint B).
Phase 4 = tests; Phase 5 = regen + audit + close-out.

### Phase 0: Baseline (no code change)
- Confirm HEAD = `9d66eae5` (G3 in tree); clean tree. Capture current A3 + ladder as the honest
  before (G1/G2/G3 already moved scores off any frozen-prompt numbers).

### Phase 1: Types + sub-renderer (Foundation)
- `CompositeSlot` dataclass + `composite` field on `SlotFill` + `render_composite` in
  `component_matcher.py`. Pure, importable by both consumers, no circular import.

### Phase 2: Renderer + tree plumbing (infra, still zero-consumer)
**Depends on:** Phase 1.
- `_fill_slots` composite branch + `_fill_composite_slot` + `_splice_rows_after_slot`
  (`component_renderer.py`). `composite` branch in `tree_bridge._fill_to_slot_value`.
- **Checkpoint A:** run the corpus → byte-identical (no builder emits composite yet).

### Phase 3: First consumer (own-row CTA)
**Depends on:** Phases 1–2.
- Replace `_fills_text_block:1433-1441` fold with a composite "cta_row" fill.

### Phase 4: Tests (RED-proven)
**Depends on:** Phases 1–3.
- `render_composite` (depth/recursion/cap), `_splice_rows_after_slot`, builder emission, renderer
  splice, tree_bridge composite→HtmlSlot, byte-compat (A and B).

### Phase 5: Regen + audit + close-out
**Depends on:** Phases 1–4 green.
- Regen c6/c7/c10; confirm c5/c8/c9 byte-identical; re-score A3; ledger + TRIAGE + TODO.md.

---

## STEP-BY-STEP TASKS

Execute in order. Each is atomic and independently testable.

### 0. BASELINE current corpus
- **IMPLEMENT**: Record pre-change A3 + ladder for cases 5–10.
- **VALIDATE**: `uv run python scripts/score-fidelity-cases.py` → save the table verbatim.
- **GOTCHA**: This baseline (post-G3), not any prompt number, is the no-regression reference.
- **SATISFIES**: AC "A3 flat-or-up" (establishes the reference).

### 0.5 VERIFY coverage map (no code change) — DO BEFORE REGEN
- **IMPLEMENT**: Per case, count `<a display:inline-block>` inside a `textblock-body` `<td>`.
- **EXPECTED (verified 2026-07-18)**: text-block CTAs = **c6:1 ('Order your fall favorite'),
  c7:1 ('Explore now'), c10:2 ('SHOP THE COLLECTION','DISCOVER EIGER EXTREME 6.0')**; c5:0
  (8 column pills), c8:0 (2 column CTAs), c9:0. So **only c6/c7/c10 move**; c5/c8/c9 byte-identical.
- **VALIDATE**: the counts reproduce (script in §NOTES C).
- **SATISFIES**: bounds the byte-compat claim (the Checkpoint-B discriminator).

### 1. ADD `CompositeSlot` + `composite` field (`component_matcher.py`)
- **IMPLEMENT**: After `SlotFill` (`:47`), add:
  ```python
  @dataclass(frozen=True)
  class CompositeSlot:
      """A rendered sub-component spliced as its own row (51.1 composite-slot infra)."""
      children: tuple[SlotFill, ...]
      after_slot: str          # data-slot id whose <tr> the composite splices after
      cell_style: str = ""     # inline style for the wrapping <td>
      align: str = "center"
      child_separator: str = ""  # joins rendered children (own-row CTA uses "\n")
  ```
  Add to `SlotFill` (last field, after `stacked_after:47`):
  `composite: CompositeSlot | None = None  # set only when slot_type == "composite"`
  Extend the `slot_type` comment (`:35`) → `"text" | "image" | "cta" | "attr" | "composite"`.
- **PATTERN**: trailing-default field; `from __future__ import annotations` (`:3`) makes the
  forward ref to `CompositeSlot` safe despite definition order.
- **GOTCHA**: keep `composite` LAST so the positional `SlotFill(id, val, type, attrs)` rebuild at
  `tree_bridge.py:142` (image-alt only) is unaffected.
- **VALIDATE**: `uv run python -c "from app.design_sync.component_matcher import SlotFill, CompositeSlot; SlotFill('a','b'); CompositeSlot((), 'body')"`
- **SATISFIES**: AC composite-union.

### 2. ADD `render_composite` (`component_matcher.py`)
- **IMPLEMENT**: module-level, near `_column_cta_row`:
  ```python
  _MAX_COMPOSITE_DEPTH = 3

  def render_composite(cs: CompositeSlot, depth: int = 1) -> str:
      """Render a composite slot's children into one centered <tr> row.

      Recursion is inherent: a child with slot_type == "composite" re-enters at
      depth+1, capped at _MAX_COMPOSITE_DEPTH. Own-row CTA (51.1's first consumer)
      exercises depth 1 only — children are terminal text fills carrying pre-built
      <a> anchor HTML. General sub-template child rendering is deferred to 51.2.
      """
      if depth > _MAX_COMPOSITE_DEPTH:
          logger.warning("design_sync.composite.max_depth", depth=depth)
          return ""
      parts: list[str] = []
      for child in cs.children:
          if child.slot_type == "composite" and child.composite is not None:
              parts.append(render_composite(child.composite, depth + 1))
          else:
              parts.append(child.value)
      return (
          f'<tr><td align="{cs.align}" style="{cs.cell_style}">'
          f"{cs.child_separator.join(parts)}</td></tr>"
      )
  ```
- **PATTERN**: `logger` already bound (`component_matcher.py:26`). `child_separator` preserves the
  old fold's `"\n".join(cta_parts)` (`:1434`) inter-anchor whitespace so c10's 2 buttons keep their
  gap — only row *placement* changes, not button spacing.
- **GOTCHA**: depth guard uses `> _MAX_COMPOSITE_DEPTH` (a depth-3 child renders; a depth-4 re-entry
  returns `""`). Recursion guarded on `child.composite is not None` so a mislabeled composite child
  with no payload degrades to `child.value`, not a crash.
- **VALIDATE**: Task 8 unit tests.
- **SATISFIES**: AC sub-renderer + depth-cap.

### 3. ADD `_splice_rows_after_slot` (`component_renderer.py`)
- **IMPLEMENT**: near `_splice_rows_before_slot` (`:1228`). A naive "first `</tr>` after the td" is
  WRONG — a body cell can wrap a nested table (`_per_node_body_html`, multi-paragraph bodies), so the
  first `</tr>` is the *nested row's* close and the CTA would splice INSIDE the body cell. Anchor on
  the row OPEN and use the depth-counting `_find_matching_close` (the same helper `_fill_text_slot`
  uses at `:1127`) to reach the OUTER row's close:
  ```python
  @staticmethod
  def _splice_rows_after_slot(html_str: str, slot_id: str, after: str) -> str:
      """Inject <tr> rows after the <tr> enclosing a text slot's <td> (51.1).

      Anchors on the row-open <tr...> nearest before the <td data-slot=...>, then
      finds THAT row's matching </tr> via _find_matching_close (counting nested
      <tr> depth) so a body cell wrapping a _per_node_body_html <table> (c10) is
      not truncated at the inner row. Defensive no-op if the slot / its row open /
      its matching close isn't found — a composite whose after_slot isn't in the
      template keeps pre-51.1 output rather than dropping a row mid-table.
      """
      m = re.search(rf'<td\b[^>]*\bdata-slot="{re.escape(slot_id)}"', html_str)
      if not m:
          return html_str
      opens = list(re.finditer(r"<tr\b[^>]*>", html_str[: m.start()]))
      if not opens:
          return html_str
      close_start = _find_matching_close(html_str, "tr", opens[-1].end())
      if close_start is None:
          return html_str
      tr_end = close_start + len("</tr>")
      return html_str[:tr_end] + after + html_str[tr_end:]
  ```
- **PATTERN**: `_splice_rows_before_slot` (`:1229-1246`) for the row-open anchor; `_find_matching_close`
  (module-level, used at `:1127`) for the depth-counted close. Confirm `_find_matching_close` returns
  the `</tr>` START (as `_fill_text_slot` relies on at `:1130`).
- **GOTCHA**: **VERIFIED 2026-07-18** — c10's `textblock-body` cells nest a `<table><tr>…` (cells #1/#2
  `nested_table=True`); c6/c7 don't. The depth-counted close is REQUIRED for c10, not optional. Do NOT
  use a forward `find("</tr>")`.
- **VALIDATE**: Task 8 (incl. the nested-table case).
- **SATISFIES**: AC injection primitive.

### 4. ADD `_fill_composite_slot` + dispatch branch (`component_renderer.py`)
- **IMPLEMENT**: extend the import `from app.design_sync.component_matcher import … SlotFill …` to add
  `CompositeSlot, render_composite`. Add a branch in `_fill_slots` at `:940` (before the `else`):
  ```python
  elif fill.slot_type == "composite":
      result = self._fill_composite_slot(result, fill)
  ```
  and the method:
  ```python
  def _fill_composite_slot(self, html_str: str, fill: SlotFill) -> str:
      """Splice a composite slot's rendered row after its reference slot (51.1)."""
      if fill.composite is None:
          return html_str
      row = render_composite(fill.composite)
      return self._splice_rows_after_slot(html_str, fill.composite.after_slot, row)
  ```
- **PATTERN**: the `if image / elif cta / else text` chain at `:936-941`.
- **GOTCHA**: the branch MUST precede `else → _fill_text_slot` — otherwise a composite falls to
  `_fill_text_slot`, finds no `data-slot="cta_row"`, no-ops, and the CTA is LOST.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_composite_slot.py -q` (Task 8); Checkpoint A.
- **SATISFIES**: AC renderer-dispatch.

### 5. ADD `composite` branch to `tree_bridge._fill_to_slot_value` (`tree_bridge.py`)
- **IMPLEMENT**: extend the import (`:18`) to add `render_composite`. Before the unknown-slot_type
  fallback (`:204`) add:
  ```python
  if fill.slot_type == "composite":
      if fill.composite is not None:
          return HtmlSlot(html=render_composite(fill.composite))
      return None
  ```
- **PATTERN**: the `attr → HtmlSlot` branch (`:199-202`); `HtmlSlot` already imported (`:10`).
- **GOTCHA**: without this, a composite fill hits `:204-212` → logs `tree_bridge.unknown_slot_type`
  every render AND returns `None` for the empty-`value` composite → CTA dropped in the EmailTree
  path. `:142` needs NO change (image-alt only). **OPEN**: verify a bare `<tr>` inside `HtmlSlot`
  renders in the `TreeCompiler`; if it needs a fragment without the `<tr>` wrapper, emit
  `render_composite`'s inner instead (Task 10 asserts the shape; §OQ 3).
- **VALIDATE**: Task 10.
- **SATISFIES**: AC tree-path parity (CTA not dropped).

### 6. VERIFY Checkpoint A — infra byte-identical (no code change)
- **IMPLEMENT**: With Tasks 1–5 landed and `_fills_text_block` UNCHANGED, run the corpus.
- **VALIDATE**: `make snapshot-test` (or regen dry-run) → `git diff data/debug/` EMPTY;
  `uv run python scripts/score-fidelity-cases.py` unchanged vs Task 0.
- **GOTCHA**: any diff here means the infra alone changed output (a leak) — stop and investigate
  before wiring the consumer.
- **SATISFIES**: AC "corpus byte-identical with zero composite consumers".

### 7. WIRE the consumer — own-row CTA in `_fills_text_block` (`component_matcher.py`)
- **IMPLEMENT**: replace the fold at `:1433-1441` with:
  ```python
  if cta_parts:
      anchor_slot = (
          "body" if any(f.slot_id == "body" for f in fills)
          else "heading" if any(f.slot_id == "heading" for f in fills)
          else None
      )
      if anchor_slot is not None:
          fills.append(SlotFill(
              "cta_row", "", slot_type="composite",
              composite=CompositeSlot(
                  children=tuple(SlotFill("cta_anchor", a) for a in cta_parts),
                  after_slot=anchor_slot,
                  cell_style="padding:8px 24px 24px;",  # TUNE vs A3 (Task 11)
                  child_separator="\n",  # preserve the old fold's inter-anchor gap
              ),
          ))
      else:
          # Fallback (no text anchor slot — not hit by the corpus): keep pre-51.1
          # inline behaviour so a CTA is never dropped.
          fills.append(SlotFill("body", "\n".join(cta_parts)))
  ```
  Import `CompositeSlot` (same module — no import change). Body fill now stays PURE (body text only).
- **PATTERN**: F11's minimal edit; the anchor build (`:1402-1432`) is untouched.
- **GOTCHA**: `cell_style` sets the own-row spacing; `align="center"` (CompositeSlot default) is what
  centers 'Explore now'. Start from body's horizontal `24px` + a small top gap; **tune in Task 11
  against A3** (the exact value moves the c6/c7/c10 diff). Do NOT reintroduce `display:block` on the
  anchor.
- **VALIDATE**: Task 9 render test; Task 11 regen.
- **SATISFIES**: AC own-row CTA (closes M8).

### 8. ADD sub-renderer + splice unit tests (`test_composite_slot.py`)
- **IMPLEMENT**: (a) `render_composite(CompositeSlot((SlotFill("x","A"),SlotFill("y","B")),"body"))`
  → `<tr><td align="center" …>AB</td></tr>`. (b) recursion: a child `slot_type="composite"` renders
  nested (depth 2). (c) depth cap: a chain 4-deep → the depth-4 re-entry returns `""` (assert the
  logged warning path / truncation). (d) `_splice_rows_after_slot`: given a 2-row table, splice after
  `data-slot="body"` → new row lands between body `</tr>` and the next content; no-op when the slot
  is absent. **(e) nested-table body (REGRESSION GUARD): a `<td data-slot="body">` wrapping a
  `<table><tr><td>…</td></tr></table>` (the c10 `_per_node_body_html` shape) → the spliced row lands
  AFTER the outer body `</tr>`, NOT inside the nested table.** A simple 2-row table (8d) passes even
  with the naive-`find` bug — this case is what catches it.
- **PATTERN**: `test_component_renderer.py` splice tests; `test_cta_fidelity.py` anchor asserts.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_composite_slot.py -q` (RED before Tasks 2–4).
- **SATISFIES**: AC RED-proven sub-renderer + cap + splice.

### 9. ADD builder + renderer render test (`test_cta_fidelity.py`)
- **IMPLEMENT**: (a) `_fills_text_block` on a section with body + one button → assert the returned
  fills contain a `SlotFill(slot_id="cta_row", slot_type="composite")` whose `composite.after_slot ==
  "body"` and children carry the anchor HTML — and that the `body` fill's value has NO `<a>`
  (no longer folded). (b) full render of a text-block match with that composite → the `<a>` sits in a
  `<td align="center">` row AFTER the `textblock-body` row (not inside it). (c) multi-button (c10-like
  2 buttons) → both anchors in the one centered row.
- **PATTERN**: `test_cta_fidelity.py:299-323` (SlotFill/ButtonElement fixtures).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_cta_fidelity.py -q` (RED before Task 7).
- **SATISFIES**: AC RED-proven own-row + no-inline-fold.

### 10. ADD tree_bridge composite test (`test_tree_bridge.py`)
- **IMPLEMENT**: a fills list with a `composite` "cta_row" fill → `_convert_slot_fills` /
  `build_email_tree` yields an `HtmlSlot` carrying the CTA anchor HTML for that slot (NOT `None`, NOT
  a dropped CTA); assert no `tree_bridge.unknown_slot_type` warning. Assert the `body` slot is a plain
  `TextSlot` without the anchor (moved to the composite).
- **PATTERN**: `test_tree_bridge.py:140-256` construction patterns.
- **GOTCHA**: if the `TreeCompiler` rejects a bare `<tr>` in `HtmlSlot`, this test tells you to emit
  the inner fragment instead (§OQ 3) — adjust Task 5 accordingly, don't paper over it.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_tree_bridge.py -q`.
- **SATISFIES**: AC tree-path parity.

### 11. REGEN + diff-audit baselines (Checkpoint B)
- **IMPLEMENT**: `python scripts/snapshot-capture.py <case> --overwrite` for **6, 7, 10** only.
  `git diff data/debug/<case>/expected.html` per-case:
  - **c6** — 'Order your fall favorite' moves from inside `textblock-body` to a centered `<tr><td
    align="center">` row below it.
  - **c7** — 'Explore now' centers on its own row below the hero body (**acceptance exemplar**).
  - **c10** — both CTAs move to one centered row below the body.
  Regen c5/c8/c9 too and **confirm ZERO diff** (a non-empty diff = column-path leak → stop).
- **GOTCHA**: only the CTA `<a>`/`<tr>` lines should move; if body typography or padding shifts,
  the `cell_style` or the pure-body change leaked — investigate. Tune `cell_style` (Task 7) until
  c6/c7/c10 A3 is flat-or-up.
- **VALIDATE**: `git diff --stat data/debug/`; visual spot-check c7 'Explore now' centered.
- **SATISFIES**: AC c7 own-row; c5/c8/c9 byte-identical.

### 12. RE-SCORE + full gate
- **IMPLEMENT**: re-run A3; compare to Task 0.
- **VALIDATE**: `uv run python scripts/score-fidelity-cases.py` (c7 flat-or-up, no case regresses;
  ladder unchanged) then `make check-full`.
- **SATISFIES**: AC A3 flat-or-up + `make check-full`.

### 13. LEDGER + TRIAGE + TODO.md close-out (anti-drift)
- **IMPLEMENT**:
  (a) `.agents/deferred-items.json` — add + close `phase-53g-g4-composite-slot-infra` (severity
      `soft`→closed; code_refs = `render_composite`, `_fill_composite_slot`, `_splice_rows_after_slot`,
      `_fills_text_block:1433`; closes_when = "composite variant + sub-renderer + own-row CTA shipped,
      corpus regenerated"). Add a **deferred** `phase-53g-g4-general-sub-template-recursion` (severity
      `speculative`; symptom = a composite child needing template substitution has no renderer;
      closes_when = 51.2 card/pills lands the depth≥2 sub-template path). Add a **deferred**
      `phase-53g-g4-tree-html-slot-row-shape` if Task 10 surfaced the `<tr>`-in-`HtmlSlot` question.
  (b) `.agents/plans/deferred/TRIAGE-2026-06-12.md` — mark `51.1-composite-slot-infrastructure.md`
      **promoted** (note the depth-cap/splice-after decisions; the 5 siblings stay ordered behind it).
  (c) TODO.md § Track G — refresh the intro status row if scores moved; patch any LATER G-prompt
      whose file:line refs / mechanism claims this change invalidated (e.g. a prompt asserting
      "text-block CTA folds into body"). **Do NOT edit the frozen snapshot
      `.agents/plans/53-g-production-readiness-prompt-sequence.md`.**
- **VALIDATE**: `git diff` review; confirm frozen snapshot untouched; stub marked promoted.
- **SATISFIES**: AC ledger + TRIAGE + close-out discipline.

---

## TESTING STRATEGY

### Unit Tests
- **Sub-renderer** (`test_composite_slot.py`): `render_composite` depth 1 (terminal children concat +
  centered wrap), depth 2 (composite child recursion), depth cap (4-deep → truncated `""`);
  `_splice_rows_after_slot` (splices after the row; no-op when slot absent).
- **Builder** (`test_cta_fidelity.py`): `_fills_text_block` emits a `composite` "cta_row" fill with
  `after_slot="body"`; body fill no longer carries the anchor; multi-button → one row.
- **Renderer** (`test_cta_fidelity.py` / `test_component_renderer.py`): composite fill splices a
  centered `<td>` row after `textblock-body`; the non-composite path is unchanged.
- **Tree bridge** (`test_tree_bridge.py`): composite → `HtmlSlot` (not `None`), no unknown-type warn.

### Integration / Snapshot
- **Checkpoint A**: infra-only → `git diff data/debug/` empty (Task 6).
- **Checkpoint B**: consumer wired → only `data/debug/{6,7,10}` move; `{5,8,9}` byte-identical.
- `make snapshot-test`; A3 scorer is the fidelity oracle.

### Edge Cases
- Text-block with buttons but no body AND no heading → fallback inline-append (no CTA drop).
- CTA-only text-block (body blanked by `_blank_unfilled_text_slots` post-splice) → CTA row survives
  as a sibling (splice ran during the dispatch loop, before the post-fill blank pass).
- Composite child mislabeled `composite` with `composite=None` → degrades to `child.value`.
- Depth-4 nesting → truncated, warning logged (no infinite recursion).

---

## VALIDATION COMMANDS

### Level 1 — Syntax & Style
- `uv run ruff check app/design_sync/ --no-fix` (never `--fix` with TCH — CLAUDE.md)
- `uv run ruff format --check app/design_sync/`

### Level 2 — Unit Tests
- `uv run pytest app/design_sync/tests/test_composite_slot.py app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_tree_bridge.py app/design_sync/tests/test_component_renderer.py -q`

### Level 3 — Types + Snapshot + Fidelity
- `uv run mypy app/design_sync/` · `uv run pyright app/design_sync/`
- Checkpoint A: infra-only `git diff data/debug/` EMPTY.
- `uv run python scripts/score-fidelity-cases.py` (compare to Task 0).
- Checkpoint B: `git diff data/debug/` shows only c6/c7/c10 CTA-row moves.

### Level 4 — Manual
- Open `data/debug/7/expected.html`: 'Explore now' renders in a `<td align="center">` row BELOW the
  hero body cell (not inside it). c6/c10 likewise.

### Level 5 — Full gate
- `make check-full` (lint + types + tests + security + golden + flag audit + migration lint).

---

## ACCEPTANCE CRITERIA

- [ ] `SlotFill` carries `slot_type="composite"` + a `composite: CompositeSlot | None` field;
      `CompositeSlot` + `render_composite` (depth-≤3 loop) land in `component_matcher.py`.
- [ ] `_fill_slots` dispatches composite → `_fill_composite_slot` → `_splice_rows_after_slot`;
      `tree_bridge._fill_to_slot_value` has a composite branch (CTA not dropped in the tree path).
- [ ] **Checkpoint A**: infra landed, no consumer → corpus byte-identical (`git diff data/debug/`
      empty); A3 unchanged.
- [ ] **Checkpoint B**: `_fills_text_block` emits the CTA as a composite row; **c7 'Explore now'
      centers on its own row**; c6 + c10 likewise; **c5/c8/c9 byte-identical**.
- [ ] A3 flat-or-up vs Task-0 baseline; ladder unchanged; c7 flat-or-up.
- [ ] RED-proven unit tests: sub-renderer (+ depth cap), splice, builder emission, renderer splice,
      tree_bridge composite; `make check-full` green.
- [ ] Baselines regenerated (NOT hand-patched); `git diff` shows only CTA-row moves.
- [ ] Ledger entries added (infra closed + sub-template-recursion deferred); TRIAGE 51.1 marked
      promoted; TODO.md Track G updated; frozen snapshot untouched.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order; each validation passed immediately.
- [ ] Checkpoint A (infra byte-identical) verified BEFORE wiring the consumer.
- [ ] Full suite green (unit + snapshot); zero lint/type errors.
- [ ] Manual spot-check: c7 'Explore now' centered on its own row.
- [ ] A3 flat-or-up vs Task-0; ladder unchanged.
- [ ] Ledger + TRIAGE + TODO.md updated; frozen snapshot untouched; `git diff` isolated to this ticket.

---

## OPEN QUESTIONS / ASSUMPTIONS

1. **Recursion scope (RATIFIED here — the ticket's "ratify" call).** Build the composite as ONE
   children-rendering loop with a depth-≤3 cap that own-row CTA exercises at depth 1 (children =
   pre-built G3-styled anchor HTML, no template substitution). **Do NOT build a general recursive
   sub-template renderer now** — it would ship with zero real consumers + synthetic-only tests
   (Simplicity First) and could only reach own-row CTA by regressing G3's `_cta_padding_css` or
   pulling in the `cta.html` surface 51.3 owns. 51.2 (card/pills) is the first genuine depth≥2
   consumer and will add the sub-template child + `data-slot-composite` anchor mode. Recorded as a
   ledger scope-cut (Task 13a). *If the reviewer wants the general renderer now, flag before
   implementing — it changes the plan materially.*
2. **`cell_style` value.** Own-row spacing is tuned against A3 (Task 11), starting from body's
   horizontal `24px` + a small top gap. If a reviewer wants the exact design gap, it's a one-line
   change but moves the c6/c7/c10 diff.
3. **`HtmlSlot(html="<tr>…")` shape.** Task 5 emits the full `<tr>` row into `HtmlSlot`; Task 10
   asserts the `TreeCompiler` accepts it. If it needs a fragment without the `<tr>` wrapper, emit
   `render_composite`'s inner instead (the anchors) — decided empirically at Task 10, ledgered if it
   forces a shape change.
4. **Branch/PR strategy.** Assumed continuation on `investigate/converter-v2-deep-audit` (now reset
   onto `origin/main` @ `9d66eae5`). NOTE: that reset set the branch to **track `origin/main`** —
   repoint the upstream (new branch or force-push `origin/investigate/converter-v2-deep-audit`)
   before pushing so it does not target `main`. Doesn't change the code.
5. **Multi-button own-row layout.** Both anchors go in ONE centered `<td>` (inline-block, side by
   side, wrapping if they don't fit) — c10's pair. If the design stacks them vertically, that's a
   `display:block`-per-anchor decision deferred with the rest of the block work.

## NOTES (open canvas)

### (A) Evidence: `SlotFill` is never serialized — no bridge needed (verified 2026-07-18)
Full-surface survey: no `asdict` / `to_json` / `from_json` / pickle / cache touches `SlotFill` or its
container `ComponentMatch`. `data/schemas/email-design-document-v1.json` has ZERO `SlotFill` /
`slot_type` / `composite` references. The only `asdict` sites in design_sync operate on
`style_runs` / `ExtractedTokens` — never matches. `section_cache.py` serializes `SectionCacheEntry`
+ a key dict, never `slot_fills`. So a new field needs NO schema / round-trip / cache change — the
opposite of DocumentButton (G3). Lifecycle: built by `_fills_*` → consumed by `_fill_slots` +
`tree_bridge` → discarded.

### (B) Why a composite fill is inert to the post-fill passes
`_fill_slots`' post-fill passes read only: `_blank_unfilled_text_slots` ← `{f.slot_id}` (`:947`);
`_prune_unfilled_ctas` ← `{f.slot_id for f if f.value.strip()}` (`:955`); placeholder warn scans the
rendered HTML, not `fills`. NONE switch on `slot_type`. A composite fill (`slot_id="cta_row"`,
`value=""`) adds `"cta_row"` to `filled_ids` (no `data-slot="cta_row"` in any template → no effect)
and is absent from `nonempty_filled` (empty value; and `"cta_row"` ∉ `_CTA_TEXT_SLOTS`). Inert.

### (C) Coverage-map script (Task 0.5, reproduce)
```python
import re
for n in (5,6,7,8,9,10):
    h=open(f"data/debug/{n}/expected.html",encoding="utf-8").read()
    cells=re.findall(r'<td\b[^>]*class="[^"]*textblock-body[^"]*"[^>]*>(.*?)</td>',h,re.DOTALL)
    print(n, sum(c.count("display:inline-block") for c in cells), "text-block CTA anchors")
# 2026-07-18: 5→0, 6→1, 7→1, 8→0, 9→0, 10→2  (labels: c6 'Order your fall favorite',
# c7 'Explore now', c10 'SHOP THE COLLECTION' + 'DISCOVER EIGER EXTREME 6.0')
```
Nested-body check (drives Task 3's depth-counted splice): **c10's `textblock-body` cells nest a
`<table><tr>…` (cells #1/#2), c6/c7 do NOT.** `_per_node_body_html` (`:1324-1328`) emits that nested
table for multi-paragraph bodies, so a forward `find("</tr>")` after `data-slot="body"` would land the
CTA row INSIDE c10's body cell. `_find_matching_close(html, "tr", row_open)` is mandatory, not
belt-and-suspenders.

### (D) Two-checkpoint byte-compat rationale
The AC's "corpus byte-identical with zero composite consumers" is provable ONLY by staging: land
Phases 1–2 (types + renderer + tree branch) with `_fills_text_block` untouched, run the corpus →
must be empty diff (Checkpoint A). THEN wire Phase 3 → exactly c6/c7/c10 move (Checkpoint B). This
separates "did the infra leak?" from "did the consumer behave?" — a single combined run can't.

## AMENDMENTS

- (none — created 2026-07-18)
