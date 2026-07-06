# Plan: F10 — Column content y-order: emit column rows in design tree order

> **Scope:** Track F close-out c7 item 5 (`53-f-render-fidelity.md` §6 close-out) —
> `_build_column_fill_html` emits `images → texts → buttons` category buckets,
> discarding the design's vertical order. Closes `phase-53f-column-category-order`.
> Three surgical seams: capture order at group construction (`layout_analyzer.py`),
> round-trip it through the document bridge (`email_design_document.py`, the #327
> serializer lesson), merge at emission (`component_matcher.py`).
> **`_column_cta_row`'s anchor markup is untouched** (rows just emit in a different
> sequence); **`_detect_content_hierarchy` untouched** (no corpus-wide pill
> reclassification); per-corner pill styling stays 51.1.
> **Parent contract:** `53-f-render-fidelity.md` §3 (measurement) + §0 (ground rules).
> Standalone slice per the F7-cards/F9 precedent — no ratification needed.
>
> **✅ EXECUTED 2026-07-06** (`fix/phase-53f10-column-y-order`). Shipped as written —
> see `## Result`. **Correctness win, not pixels: full_image flat on all 6; only the
> c7 baseline changed (6 card sections, pure row relocation)**; acceptance
> composite-verified (pill → heading → body → CTA; product name above the
> pieces/points icon rows); ladder 13/9/8/10/8/12 held; 6 unit tests (3 behavioral
> RED pre-fix via the public analyzer→builder path).

## 1. Context — the verified defect (fixture evidence, this session)

`_build_column_fill_html` (`component_matcher.py:889-899` pre-fix) iterates
`group.images`, then `group.texts`, then `group.buttons`. The interleave is lost one
step earlier: both group constructors (`_detect_mj_columns` :1112, `_build_column_groups`
:1148) run three independent pre-order extractors (`_extract_buttons/_texts/_images`)
over the column node, so each category list is internally ordered but the cross-category
sequence is gone. None of `TextBlock`/`ImagePlaceholder`/`ButtonElement` carries a y —
only `EmailSection` does — so order must be captured **where the `DesignNode` tree is
still in hand**, at construction.

Corpus census (pipeline-verified via `from_legacy → to_email_sections`, this session):

| Case | Mixed-order columns | Routes through the column builder? |
|---|---|---|
| c7 | 6 — tip cards sec[5]/[7] col2 (pill BTN → heading → body → CTA BTN); treats cards sec[9]/[11]/[13]/[15] (name TXT → icon IMG → pieces TXT → icon IMG → points TXT → CTA) | **YES** — `column-layout-2`, `column_groups` path |
| c5 | 1 — nav bar sec[6] (6× label TXT ↔ icon IMG pairs) | no — `layout=single`, slug `navigation-bar` |
| c6 | 1 — footer sec[8] (`Ref:` line between social icons) | no — `layout=single`, slug `social-icons` |
| c9 | 3 — sec[6] `col-icon`, sec[8] `image-grid`, sec[10] `social-icons` | no — all `layout=single` |
| c8/c10 | 0 | — |

Tree order is monotone with node y in every observed column (Figma auto-layout), so the
pre-order walk IS the y-order the ledger entry names. The single-column cases above
route through slot-shaped seed builders (order fixed by seed HTML structure, not bucket
loops) — 51.1 composite-slot territory, out of scope, deliberately no new ledger entry.

## 2. Design

1. **`ColumnGroup.content_order: tuple[str, ...] = ()`** (`layout_analyzer.py`) — node
   ids of the extracted content in one more pre-order walk of the column node
   (`_column_content_order`, ids filtered to the extracted elements' `node_id`s; a
   wrapped image's inner-img id is a descendant, so the walk finds it). Populated at
   both construction sites (`_detect_mj_columns`, `_build_column_groups`).
2. **`DocumentColumn.content_order`** (`email_design_document.py`) — mirrored through
   `to_json`/`from_json`/`from_column_group`/`to_column_group`. The #327 lesson: a
   render field is real only if it survives the document bridge; without this the fix
   works in the harness and dies app-side.
3. **`_ordered_column_elements`** (`component_matcher.py`) — stable-sort of
   `[*images, *texts, *buttons]` by `content_order` index; ids not in the tuple sort
   after all ordered ones in legacy category order. `_build_column_fill_html` dispatches
   each element to its unchanged row builder (`_column_image_row` / `_column_text_row` /
   `_column_cta_row`).
4. **Failsafe:** empty `content_order` (older persisted documents, and the
   `ContentGroup → ColumnGroup` conversion at `component_matcher.py:1925`) reproduces
   the legacy bucket order byte-for-byte.

Rejected alternatives:
- **Route pre-heading button-likes through the F6 `stacked_before` seam** — fixes only
  the pill half; `stacked_before` is a slot-splice on the text-block path and cannot
  reorder images-vs-texts inside the column's own inner table (the treats half of the
  acceptance). The y-merge subsumes F6's intent for columns without touching F6.
- **Put `y` on the three element dataclasses** — 3 dataclasses + both serializers +
  Document mirrors for the same information one tuple carries; more invasive, same
  outcome.
- **Thread order through `ContentGroup` too** — widens the blast radius past the
  ledger's c7-only contract for zero corpus effect today (content-group columns in the
  corpus aren't mixed-order); the conversion site deliberately passes `()`.

## 3. Tests (`app/design_sync/tests/test_column_y_order.py`, 6)

RED-proven pre-fix (3 behavioral assertion failures through the public
`_detect_mj_columns`/`_build_column_groups` → `_build_column_fill_html` path, 2
field-existence errors; the legacy-fallback guard green both sides, as designed):

1. `test_tip_card_pill_renders_above_heading` — synthetic mixed column mirroring c7
   sec[5] col2; pre-fix emission `heading, body, pill, CTA` (RED), post-fix
   `pill, heading, body, CTA`.
2. `test_treats_card_name_renders_above_icon_rows` — mirrors c7 sec[9] col1; asserts
   name → icon → pieces → icon → points → CTA.
3. `test_auto_layout_columns_also_capture_order` — same via `_build_column_groups`.
4. `test_detect_mj_columns_captures_pre_order_ids` — exact `content_order` tuple.
5. `test_group_without_content_order_keeps_bucket_order` — legacy fallback (old
   persisted documents) byte-stable.
6. `test_document_column_round_trips_content_order` — `from_column_group → to_json →
   from_json → to_column_group` preserves the field **and** full group equality.

## 4. Adjacent open items (surfaced, not absorbed)

- `phase-53-b8-text-block-solid-cta-text-color` (**open**, speculative) — solid-fill
  text-block CTAs hardcode white label text vs c5's extracted `#010101`. The F11-class
  neighbour on the pill/CTA fidelity story; untouched here.
- Single-column category ordering (c5 nav, c6/c9 social-icons, c9 col-icon/image-grid,
  table above): same defect class, different mechanism (seed slot structure, not bucket
  loops) → 51.1, no ledger entry (nothing load-bearing to pin to a code_ref today).

## 5. Execution checklist (standard contract)

1. BEFORE scores: c5 0.840 / c6 0.802 / c7 0.794 / c8 0.778 / c9 0.680 / c10 0.742
   (reproduced the §6 F9 row exactly — worktree fixture set restored from the primary
   checkout, 800 gitignored files).
2. Tests written; RED set proven; implement §2; all 6 GREEN.
3. Baseline regen ONLY after per-case temp-diff audit: c7 changed (84 diff lines, pure
   row relocation in exactly the 6 card sections) → `snapshot-capture.py 7 --overwrite`;
   **c8's 6-line diff = pre-existing trailing-whitespace churn (converter-emitted,
   hook-stripped in the committed baseline) → NOT regenerated (F7-radius precedent)**;
   c5/c6/c9/c10 byte-identical.
4. Ladder 13/9/8/10/8/12 held (data-regression 73 passed / 1 mammut xfail).
5. Gates: `make types` 0 errors · design_sync+components 2852 passed / 2 xfailed ·
   golden-conformance 26 · scoped ruff (incl. S-rules) clean.
6. AFTER scores + c7 composite eyeballed per §3.3 (before/after crops).
7. Ledger: close `phase-53f-column-category-order` with `closed_commit` (two-commit
   F9 pattern: code commit, then ledger-close).
8. `git restore app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` before
   staging. Never touch TODO.md. `/be-ship` then `/commit`.

## 6. Risks

- **Pill radius stays 4px** — the c7 tag pills carry no `border_radius` in the fixture;
  `_column_cta_row`'s fallback renders 4px (design: rounded chip). Per-corner pill
  styling is explicitly 51.1 (`corner_radius_spec` exists on `ButtonElement`, unused
  by this path). Out of scope.
- **Icon/label pairs stack vertically** — design places each spec icon NEXT TO its
  label; the column table is one `<td>` per row, so icon-above-label is the best
  vertical-order-faithful rendering available before 51.1's composite slots.
- **Median optics** — a within-card row reorder shifts height bands; the resize-based
  scorer has punished corrective moves before (F3/F9). Composites are the gate.

## Result (2026-07-06, `fix/phase-53f10-column-y-order`)

Shipped as planned (§2 verbatim: `_column_content_order` + `ColumnGroup.content_order`
in `layout_analyzer.py`; `DocumentColumn.content_order` through all four bridge points
in `email_design_document.py`; `_ordered_column_elements` + dispatch loop in
`component_matcher.py`; no other file touched). BEFORE scores reproduced the §6 F9 row
exactly; AFTER: **c5 0.840 / c6 0.802 / c7 0.794 / c8 0.778 / c9 0.680 / c10 0.742 —
full_image flat on all 6.**

- **Corpus effect (diff-audited):** only `data/debug/7/expected.html` changed — a pure
  row relocation in exactly the 6 card sections: 'Art prints'/'Stationery' pill anchors
  (byte-identical markup) move from below-body to above-heading; 4 product names move
  above their pieces/points icon rows, icons interleaving to icon→label positions;
  CTAs stay last. Zero style/content/attribute changes. c8's regen churn was
  trailing-whitespace-only → skipped (F7-radius precedent); c5/c6/c9/c10
  byte-identical — the ledger's c7-only prediction held exactly.
- **Acceptance (composite-eyeballed per §3.3, before/after):** tip cards render
  pill → heading → body → CTA top-to-bottom ('Art prints' above "Bundle of 6 Halloween
  posters", 'Stationery' above "Stranger Things Sketchbook" — design position); treats
  cards render the product name above the 617-Pieces/+260-Points icon rows (before:
  both brick icons stacked above the name).
- **Scores, honest read:** full_image flat everywhere (a ~30px in-card reorder is
  sub-band on a 6446px composite — the F6 precedent). c7 per-section (BEFORE
  re-derived via temporary source revert): **five card bands UP** (+0.062, +0.052,
  +0.033, +0.030, +0.007), one band −0.010 — and that 0.803 band WAS the median, so
  section_median prints 0.803→0.793 while the per-section mean is up ~+0.008
  (order-statistic optics, not a regression; section_min 0.478 flat, untouched band).
- **Gates:** `make types` 0 errors; design_sync+components **2852 passed / 2 xfailed**
  (+6 = the new tests); golden-conformance 26 + data-regression 73 / 1 mammut xfail —
  **ladder 13/9/8/10/8/12 held**; scoped ruff+S clean. 6 unit tests
  (`test_column_y_order.py`; 3 behavioral RED pre-fix via public paths, 2
  field-existence errors, 1 legacy guard green both sides).
- **Ledger:** `phase-53f-column-category-order` → closed (this branch).
  `phase-53-b8-text-block-solid-cta-text-color` **stays open** (F11 scope, §4).
- **App-side note:** `content_order` reaches app documents only for snapshots/imports
  created after this lands (older persisted documents carry no field → legacy order by
  design) — same re-sync ops caveat as #327, already in the ceiling doc §3.
