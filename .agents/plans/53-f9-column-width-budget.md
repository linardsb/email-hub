# Plan: F9 — Column width budget: rescale column seeds into the effective content box

> **Scope:** the highest-leverage remaining render defect from Track F close-out
> (`53-f-render-fidelity.md` §6 close-out, c7 item 1 — the diagnosis of record).
> Renderer-side ONLY: rescale column-seed widths (MSO ghost `td width` + inline-block
> div `max-width`, together) so their sum fits the content box that the renderer's own
> horizontal insets leave available. Closes `phase-53f-column-width-budget`.
> **Detection and seeds are CORRECT — neither is touched** (§4 row 4 finding: the
> "column-detection widening" lever is wrong; sections already match `column-layout-*`).
> **Parent contract:** `.agents/plans/53-f-render-fidelity.md` §3 (measurement) + §0
> (ground rules). Standalone slice per the F7-cards precedent
> (`53-f7-column-card-surface.md`) — no ratification needed.
>
> **✅ EXECUTED 2026-07-06** (`fix/phase-53f9-column-width-budget`). Shipped as written —
> see `## Result` at the end of this file. **c7 0.771→0.794 (+0.023), c10 0.678→0.742
> (+0.064)**; all acceptance criteria composite-verified; ladder 13/9/8/10/8/12 held;
> 21 unit tests (5 RED pre-fix via public render paths). One design nuance found in
> execution: c9 is a 640px-container design whose ghost table said 640 while cells
> summed 600 — the rescale re-bases the table attr to the cell total, and
> `total − inset` (not `table − inset`) is deliberate: sizing to the 640-box would
> re-wrap at the 600px scoring/client viewport (§Result, c9 note).

## 1. Context — the verified defect (disk evidence, this session)

`column-layout-{2,3,4}` seeds hardcode per-column pixel widths sized for a full 600px
context (`email-templates/components/column-layout-2.html:6-20`): MSO ghost
`<td width="300" valign="top">` + `<div class="column" … max-width: 300px>` (col3: 200,
col4: 150). Two renderer-applied horizontal insets shrink the live content box below the
seed total, so the `display:inline-block` column divs wrap and multi-column sections
render **stacked**:

1. **Repeating-group band inset** — `render_repeating_group` wraps every member in
   `<td style="padding:{top}px {horizontal}px 0">` (`component_renderer.py:680-682`;
   `horizontal` from `_resolve_item_spacing`, `:158`, corpus value 24). Content box:
   600 − 48 = **552px**.
2. **F7 card wrapper inset** — `_wrap_col_bg_inner_card` (`component_renderer.py:1392`)
   inserts `<table class="product-card _inner"><tr><td style="padding:0">`, and the
   section's `_cell` padding override (`component_matcher.py:~2163-2176`, applied after
   `inner_bg` → deterministic) relocates onto that wrapper cell (c7: `padding:20px 20px
   20px 20px`). Content box inside a banded card: 600 − 48 − 40 = **512px**.

Corpus census (from `data/debug/*/expected.html`, verified 2026-07-06):

| Case | Sections (marker idx) | Inset | Live box | Seed total | Today |
|---|---|---|---|---|---|
| c7 | 6 benefit cards (col2, carded + banded 24px) | 48+40 | 512 | 600 | STACKED (app export 4470px vs 3223px design) |
| c7 | sec[13] "Andy \| 0" user-info (col4, banded 24px) | 48 | 552 | 600 | 4th cell wraps |
| c8 | sec[3]/[4] spec grids (col2, banded 24px) | 48 | 552 | 600 | single-column (2×2 breaks) |
| c8 | sec[9] (col4, **un-grouped, un-inset**) | 0 | 600 | 600 | renders 4-across — the no-op control |
| c10 | sec[5]/[6]/[11]/[12]/[13] product grids (col2, banded 24px) | 48 | 552 | 600 | single-column |

`_apply_column_width_fractions` (A8, `component_renderer.py:1828`) redistributes the seed
total by measured design fractions but never **rescales** the total to the effective box.
Mobile CSS (`.column { max-width:100% !important }`) stacks columns below 600px by design
— unaffected by inline max-width values.

## 2. Design — where the rescale lives (and rejected alternatives)

The prompt's constraint: compute the effective content box as *600 minus accumulated
horizontal insets the renderer itself applies/knows*. Both inset sources are
renderer-owned, but they become known at **different times**:

- The **card inset** exists inside the section HTML by `render_section` step 2
  (`_apply_token_overrides`).
- The **band inset** is applied by `render_repeating_group` AFTER `render_section`
  returns (the row-cell padding wraps the member's finished HTML).

So the rescale is **one core helper with two call sites**, each subtracting the inset it
owns from the *current* ghost total (idempotent layering: 600 →(card 40)→ 560 →(band
48)→ 512):

| Alternative | Verdict |
|---|---|
| **Rescale in the matcher builders** | REJECTED — builders have no group-spacing context (band inset unknowable at build time), and the card wrapper doesn't exist yet (renderer inserts it at override time). |
| **Edit the seeds to %-widths** | REJECTED — changes bytes for every un-inset section (violates the byte-identical control), breaks Outlook (ghost cells need px), off-limits per "do not touch seeds". |
| **Single call site in `render_section` with band inset passed in** | REJECTED — threads group context through `render_section`'s signature for all callers; the group already post-processes member HTML (row wrap), so shrinking there is the surgical, layer-local change. |
| **One helper, two call sites (render_section: card inset; render_repeating_group: band inset)** | **CHOSEN.** Each layer knows exactly the inset it applies; subtracting from the current total composes correctly. |

### 2a. Invariants preserved (A8 contract)

- **All-or-nothing:** ghost `td width` matches, div `max-width` matches, and the ghost
  `<table width="NNN">` open must be consistent (`len(td) == len(div) > 0`, exactly one
  ghost table) or the whole rewrite is a no-op — the two surfaces never diverge
  (mirrors `_apply_column_width_fractions:1849-1852`).
- **Fractions preserved:** new widths come from `_distribute_widths(target, current
  fractions)` (`component_renderer.py:91`) — the last column absorbs rounding, exactly
  as A8 does. An A8-redistributed asymmetric split (e.g. 200/400) rescales to the same
  fractions (552 → 184/368).
- **Un-inset ⇒ byte-identical:** `inset_px <= 0` or `target == total` returns the input
  unchanged.
- **Slug-gated:** both call sites fire only for `component_slug.startswith
  ("column-layout")` — same gate as A8 (`:1842`). `peel-row` ghosts (same `<td width=…
  valign="top">` shape, `render_peel_row:561`) and `col-icon` are out of reach.

### 2b. Adjacent deferred item — surfaced, NOT absorbed

`phase-53f-f7-card-wrapper-outlook-ghost-overflow` (deferred, known-bug): the F7 wrapper
relocates `_cell` padding OUTSIDE the 600px MSO ghost, so Outlook's Word engine overflows
the 600px column (~640px). F9's rescale shrinks the ghost totals (600→512 inside a banded
card), which makes the Outlook arithmetic fit (512 + 88 = 600) — an **incidental
improvement to NOTE in §6, not claim**: that entry closes only with Outlook verification
(its `closes_when` requires the 51.1 padding restructure + Outlook-verified c7). Both
items live in how widths thread the MSO ghost; this plan does not close it.

## 3. Implementation

**File: `app/design_sync/component_renderer.py`** (only file; no seed, matcher,
analyzer, or bridge changes — no new `EmailSection` fields ⇒ RC-A bridge trap n/a).

### 3.1 Module constants (near `_COLUMN_TD_WIDTH_RE`, `:84`)

```
_COLUMN_GHOST_TABLE_WIDTH_RE — (<table\b[^>]*\bwidth=")(\d+)("[^>]*>\s*<tr>\s*<td width="\d+" valign="top")
```
Matches ONLY a fixed-width ghost table whose first cell is a column cell (the outer
section table and the card wrapper are `width="100%"` — no digit match).

### 3.2 Helper: `_style_horizontal_padding_px(style: str) -> int`

Parse a style-attribute body; return left+right padding in px. CSS order semantics
(later declaration wins per side): `padding:` shorthand (1/2/3/4-value forms) sets both
sides; `padding-left:`/`padding-right:` longhands override their side (the RC-D-prime
partial-padding path emits longhands via `_upsert_first_td_css_prop:1607`). Non-px
values contribute 0. Module-level function beside `_distribute_widths`.

### 3.3 Helper: `_card_wrapper_inset(html_str) -> int`

Find the F7 wrapper open `<table … class="product-card _inner" …><tr><td style="…">`
(regex anchored on the class, mirroring `_wrap_col_bg_inner_card`'s emitted shape);
return `_style_horizontal_padding_px` of that first cell's style. 0 when no wrapper.

### 3.4 Core: `_shrink_column_ghost_widths(html_str, inset_px) -> str`

1. `inset_px <= 0` → return unchanged.
2. Collect `_COLUMN_TD_WIDTH_RE` + `_COLUMN_DIV_MAXWIDTH_RE` + `_COLUMN_GHOST_TABLE_WIDTH_RE`
   matches; require `len(td) == len(div) > 0` and exactly 1 ghost table, else no-op.
3. `total = sum(td widths)`; `target = total - inset_px`; `target < len(td)` → no-op
   (degenerate box); `target == total` → no-op.
4. `widths = _distribute_widths(target, tuple(w / total for w in current))`.
5. Rewrite td widths and div max-widths positionally (A8's `_rewrite` iterator pattern)
   + the ghost table width attr → `target`.

### 3.5 Call site 1 — `render_section` step 3c (after A8, `:526`)

```python
# 3c. F9: rescale column widths into the card-narrowed content box
if match.component_slug.startswith("column-layout"):
    result_html = self._shrink_column_ghost_widths(
        result_html, self._card_wrapper_inset(result_html)
    )
```

### 3.6 Call site 2 — `render_repeating_group` rows loop (`:678-683`)

In the rows loop, before embedding each member in the padded row cell:

```python
item_html = rendered.html
if rendered.component_slug.startswith("column-layout"):
    item_html = self._shrink_column_ghost_widths(item_html, 2 * item_spacing.horizontal)
rows.append(f'<tr>\n  <td style="padding:{padding}">\n    {item_html}\n  </td>\n</tr>')
```

(`item_spacing` is already resolved at `:671`, before the rows loop — no reorder
needed. Single-member groups return `render_section` directly at `:662` — no band, no
inset, consistent.)

## 4. Unit tests — `app/design_sync/tests/test_column_width_budget.py`

Real seeds with MSO ghosts (F7 `test_column_card_surface.py` precedent). RED pre-fix
where marked:

| # | Test | Expectation | RED pre-fix? |
|---|---|---|---|
| 1 | col2 member in a `horizontal=24` group | ghost `td width="276"` ×2, `max-width: 276px` ×2, ghost table `width="552"` | **RED** |
| 2 | col4 member in a `horizontal=24` group (user-info shape) | 4 × `width="138"`, table `width="552"` — 4 cells fit one 552px line | **RED** |
| 3 | carded col2 (`_inner` bg + `_cell` `padding:20px 20px 20px 20px`) via `render_section` | `td width="280"` ×2, divs 280, table `width="560"` | **RED** |
| 4 | carded col2 member in a `horizontal=24` group (c7 benefit-card shape) | 256/256, table `width="512"` | **RED** |
| 5 | un-inset col2 via `render_section` (no card) | **byte-identical** output | guard (green both sides — no bytes can move pre-fix) |
| 6 | col2 member in a `horizontal=0` group | member html byte-identical inside the row | guard |
| 7 | A8-asymmetric fractions (≈1/3, 2/3) + band inset | 552 → 184/368 — fractions preserved, last absorbs rounding | **RED** |
| 8 | surface-count mismatch (synthetic: 2 ghost tds, 1 div) | whole rewrite no-ops — surfaces never diverge | guard |
| 9 | `_style_horizontal_padding_px`: shorthand 1/2/3/4-value, longhand override, mixed | correct left+right sums | new-helper unit |

## 5. Acceptance (HTML + composite, §3.3 eyes-are-the-gate)

- c7 benefit cards: image LEFT / text RIGHT **side-by-side**; render height approaches
  the 3223px design (was ~4470 in the app export).
- c7 sec[13] "Andy | 0": **no 4th-cell wrap** (4 cells, one line).
- c8 spec grid: **2×2** (sec[3]/[4] each 2-across).
- c10 product grid: **2-up**.
- c8 sec[9] (un-inset col4) byte-identical inside c8's diff.
- Note (don't claim) the incidental Outlook-ghost arithmetic improvement (§2b).

## 6. Execution checklist (standard contract)

1. BEFORE scores recorded: c5 0.845 / c6 0.802 / c7 0.771 / c8 0.782 / c9 0.680 /
   c10 0.678 (matches §6 app-parity row — done, this session).
2. Tests 1-9 written; RED set proven RED pre-fix; implement §3; all GREEN.
3. Regen baselines: `python scripts/snapshot-capture.py <case> --overwrite` for c7/c8/c10
   (+ any case whose bytes shift — c5/c6/c9 expected byte-identical, verify) ONLY after
   a manual intended-vs-structural diff audit per case (Track-B playbook).
4. Ladder 13/9/8/10/8/12 held (A2 strict; mammut xfail untouched).
5. Gates: `make types` · design_sync + components suites · golden-conformance · scoped
   lint (`uv run ruff check app/design_sync/ --select=S --ignore=S311 --no-fix` +
   format/fix on changed files only).
6. AFTER scores: `uv run python scripts/score-fidelity-cases.py`; composites eyeballed
   for c7/c8/c10 (+shifted); §6 row appended to `53-f-render-fidelity.md`; Result
   section appended here.
7. Ledger: close `phase-53f-column-width-budget` (`closed_commit`); note the §2b
   adjacency on `phase-53f-f7-card-wrapper-outlook-ghost-overflow` — stays open.
8. `git restore app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` before
   staging. Never touch TODO.md. `/be-ship` then `/commit`.

## 7. Risks

- **Exact-fit wrapping:** rescaled totals fill the live box exactly (256+256=512), same
  contract as the seed's 300+300=600 in an unpadded 600 box — proven working by c8
  sec[9] (600-box exact fit renders 4-across today). `font-size:0` on the col-bg cell
  kills inter-div whitespace.
- **Score direction:** collapsing stacked columns roughly halves those sections' render
  height; the height-band scorer has punished *corrective* height shifts before (F3).
  Composites are the gate (§3.3); full_image on c7 expected UP (the stacking is the
  dominant distortion), c8/c10 direction to be measured and explained honestly.
- **Filled-content regex collisions:** a fill containing `<td width="N" valign="top">`
  would inflate the td surface count ⇒ count mismatch ⇒ designed no-op (fail-safe,
  not fail-wrong).

## Result (2026-07-06, `fix/phase-53f9-column-width-budget`)

Shipped as planned (§3 verbatim: `_style_horizontal_padding_px` + `_card_wrapper_inset`
+ `_shrink_column_ghost_widths` + `_COLUMN_GHOST_TABLE_WIDTH_RE`/`_CARD_WRAPPER_CELL_RE`
in `component_renderer.py`; call sites `render_section` 3c + `render_repeating_group`
rows loop; no other file touched). BEFORE scores reproduced the §6 app-parity row
exactly; AFTER: **c5 0.840 / c6 0.802 / c7 0.794 / c8 0.778 / c9 0.680 / c10 0.742**.

- **Corpus effect (diff-audited per case, width-only, 162 lines):** 15 sections
  rescaled — c7: 6 carded benefit cards 600→**512** (256/256) + the "Andy|0" col4
  600→552 (138×4); c8: 2 spec grids →552 (276/276); c10: 5 product grids →552; c5:
  2 A8-asymmetric col3 pill rows →552 with fractions preserved (152/157/291→139/144/269;
  148/156/296→136/143/273); c9: 1 col2 icon row →552. **c6 byte-identical**;
  **c8 sec[9] (un-inset col4) untouched** — the no-op control held in real corpus.
- **Acceptance (composite-eyeballed per §3.3):** c7 cards image-LEFT/text-RIGHT
  side-by-side; c7 render **3144px vs the 3223px design** (app export was ~4470);
  "Andy|0" 4 cells on one line; c8 spec grid **2×2**; c10 product grid **2-up**;
  c5 city pills 3-per-line.
- **Scores, honest read:** c7 **+0.023** (section_min 0.351→**0.478**), c10 **+0.064**
  (median 0.777→**0.821**). c5 −0.005 / c8 −0.004 are the F3-class height-band
  artifact — un-stacking shortens the renders toward design height, shifting the
  height-normalized bands (c8 median is UP 0.788→0.791; c5's min sits on the
  pre-existing blank KASK product-image band, untouched by F9's width-only diff).
  c9 flat to 3dp: its col2 now renders side-by-side, but the row is ~60px on a
  4242px height-normalized canvas.
- **c9 nuance (found in execution):** c9 is a **640px-container** design;
  `_update_mso_widths` had stretched the ghost table to 640 while cells stayed
  300+300=600 (pre-existing mismatch). The rescale re-bases the table attr to the
  cell total (552), healing it on inset sections. `total − inset` over
  `table − inset` is deliberate: a 592 target would re-wrap at the 600px
  scoring/client viewport.
- **c8 heading trailing-whitespace** in the fresh output is the pre-existing
  converter text-join drift (F6/F8-noted), normalized by the pre-commit hook —
  not an F9 change.
- **Gates:** `make types` 0 errors (pyright on the file: 0, == preflight baseline);
  design_sync + components **2846 passed / 2 xfailed**; data-regression 73 passed /
  1 xfail (mammut) — **ladder 13/9/8/10/8/12 held**; golden-conformance 26 passed;
  scoped S-lint + format clean. 21 unit tests in `test_column_width_budget.py`
  (18 RED pre-fix, of which 5 behavior tests RED via the public render paths; 3
  no-op guards green both sides, as designed).
- **Ledger:** `phase-53f-column-width-budget` → closed.
  `phase-53f-f7-card-wrapper-outlook-ghost-overflow` **stays open** — F9's rescale
  makes the padded Word-box arithmetic fit (512+88=600), an incidental improvement
  noted, not claimed: that entry closes only with the 51.1 restructure + Outlook
  verification.
