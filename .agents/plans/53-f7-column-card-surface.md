# Plan: RC-F7 Card-Surface Render Fix — LEGO column-layout cards (scoped 51.1 slice)

> **Scope:** the minimal committable half of RC-F7 — give `column-layout-{2,3,4}`
> sections a white card surface when they carry `inner_bg`, closing
> `phase-53f-f7-column-seed-no-inner` (render-fidelity plan §5:435-440) WITHOUT the
> 51.1 composite-slot infrastructure. Pill-radius half already recovered
> (`fix/phase-53f-f7-pills-radius`, ce6d61ad).
> **Parent contract:** `.agents/plans/53-f-render-fidelity.md` §3 (measurement) + §0 (ground rules).
>
> **✅ EXECUTED 2026-07-05** (`fix/phase-53f-f7-pills-radius`). Design B shipped as written
> (`_wrap_col_bg_inner_card` in `component_renderer.py`, seeds+matcher untouched). **c7
> 0.636→0.719 (+0.083)**, section_median → 0.804; **only c7 changed** (git-confirmed), **exactly 6
> wraps** (sec 5/7/9/11/13/15); c5/c6/c8/c9/c10 byte-identical; ladder 13/9/8/10/8/12 held;
> `make test` 8251 passed, `make types` 0 errors; 10 unit tests (6 RED pre-fix). Visual composite:
> uniform white rounded cards on lime, not ragged. **Two plan corrections found in execution:**
> (1) c7 cards carry `inner_radius=12` (NOT square as §5.4/§9.3 assumed) → they render rounded
> (`border-radius:12px`), a bonus correctness win; (2) the wrapper base must **omit**
> `border-collapse:collapse` — the radius path *prepends* `border-collapse:separate;overflow:hidden`,
> so a base `collapse` sits later in the value and wins, defeating corner clipping (§5.4 had the
> precedence backwards). Fixed: base uses `mso-table-lspace/rspace:0pt` only. Membership card [19]
> deferred → `phase-53f-f7-image-gallery-membership-card`.

## 1. Context — the verified defect

From the F7 halt investigation (`53-f-render-fidelity.md`:295-321), disk-confirmed this session:

- LEGO (c7) card sections **already carry `inner_bg=#FFFFFF`** via the 50.4 direct path
  (`node.fill_color`≠`container_bg`). **Detection is NOT the gap.**
- They match `column-layout-2`; the seed has **no `class="_inner"` element** (only 6/151
  seeds do — `article-card`, `event-card`, `editorial-2`, `pricing-table`,
  `zigzag-image-{left,right}`). So the `inner_bg→_inner` override
  (`_build_token_overrides`:2054 → renderer `_replace_inner_bg_color`:1379) **no-ops**
  (0 `_inner` in `data/debug/7/expected.html`, disk-verified).
- The band colour (lime `#AFCA01`, 11× in c7 expected.html) is painted onto the outer
  `col2-bg` cell via `container_bg → _outer` (`_build_token_overrides`:2051, legacy
  first-`background-color` replace). Because `inner_bg` is truthy, the
  `elif section.bg_color → _outer` fallback (:2056) is skipped — but lime already comes
  from `container_bg`, so the section renders with **content on bare lime, no white card**.

**Fix = give the column-layout render an `_inner` target the existing override can paint.**
Rendering is the gap, not detection.

## 2. Design decision (a real fork — recommendation + rejected alternatives)

The card is **per-section**: one `col2-bg` cell wrapping two columns — col_1 = `<img>`,
col_2 = a multi-row text block (disk-verified: 22px/30px heading + 16px/20px body …). The
two `<div class="column" vertical-align:top>` are **unequal height**.

| Design | Where | Byte-safe? | Verdict |
|---|---|---|---|
| **A — per-column wrap in `_build_column_fill_html`** | matcher | ✅ perfect | **REJECTED.** Two `vertical-align:top` white boxes of unequal height leave the **band exposed below the shorter column** → ragged card, fails the "white card reappears" criterion. `font-size:0` kills only the *horizontal* gap, not the vertical one. |
| **B — insert per-section wrapper in the renderer** | `component_renderer.py` | ✅ perfect | **RECOMMENDED.** One white table spans both columns = uniform surface. Byte-safe via the **RC-F2 insert-on-no-op precedent** (`_insert_first_table_bg_color`:1350). |
| **C — literal seed wrapper + renderer unwrap** | seeds + renderer | ⚠️ fragile | REJECTED. Only variant that literally edits the seeds; dominated — depth-aware *unwrap* of a nested-table wrapper for zero fidelity gain over B. |

### 2a. KEY FINDING — the byte-safe fix does NOT touch the seeds or the matcher

The command sketched a 3-file scope (`column-layout-{2,3,4}.html` + `_build_column_fill_html`
+ renderer `_inner` handlers). **Research shows the byte-safe realization is renderer-only:**

- A static seed wrapper is **always present** → changes bytes for the 11 innocent column
  sections in c5/c8/c9/c10 (see §3.1) → violates "byte-identical no-op when `inner_bg` absent."
- `_build_column_fill_html` builds **per-column** content and cannot wrap **per-section**
  (that region — MSO ghost + both `<div class="column">` — is static seed, not matcher output),
  and per-column wrapping is Design A (ragged).
- Therefore the wrapper must be **conditionally inserted at render time**, exactly like RC-F2
  inserts a bg declaration only when the `_outer` override no-ops. This lives entirely in
  `component_renderer.py`.

Design B stays **within** the allowed scope (a subset) and out of `_detect_inner_bg`. Not
touching the seeds + matcher is a simplification, not a scope violation — surfaced here so the
divergence from the sketch is explicit, not hidden.

## 3. The three mandated quantifications

### 3.1 Cross-case baseline impact — gating confines the change to c7 (OBSERVED)

The exact predicate for "the wrap fires" is `section.inner_bg is not None` **AND**
`match_section().component_slug ∈ {column-layout-2/3/4}`. Element counts of `col-bg` /
`_inner` do **not** measure this (the c7 bug is a section with `inner_bg` and no `_inner`
rendering like `inner_bg=None`), so it was measured directly through the **real pipeline** (run 2026-07-05 — the same route the
investigation used). Reproducible ~20-line probe: for each case, `load_structure_from_json` +
`load_tokens_from_json` (`app.design_sync.diagnose.report`) → `EmailDesignDocument.from_legacy` →
`doc.to_email_sections()`; per section print `match_section(s, i).component_slug` + `s.inner_bg`;
flag `inner_bg is not None and slug in {column-layout-2/3/4}`. Run with
`PYTHONPATH=<repo> uv run python <probe>`:

| Fixture | sections | col-layout **+ `inner_bg`** (fix wraps) | col-layout, no `inner_bg` (byte-identical) | `inner_bg` on non-col seed | expected.html |
|---|---|---|---|---|---|
| c5 maap | 15 | **0** | 2 | 0 | **byte-identical** |
| c6 starbucks | 9 | **0** | 0 | 0 | **byte-identical** |
| **c7 LEGO** | 21 | **6** — `sec[5,7,9,11,13,15]` `column-layout-2` `#FFFFFF` | 1 | 1 — `sec[19]` `image-gallery` `#FFFFFF` | **changes: exactly 6 wraps** |
| c8 Ferrari | 11 | **0** | 3 | 0 | **byte-identical** |
| c9 slate | 11 | **0** | 1 | 0 | **byte-identical** |
| c10 mammut | 17 | **0** | 5 | 0 | **byte-identical** |

**Only c7's 6 column-layout cards change.** The other 5 fixtures record **0** fix-fires →
byte-identical. Reconciliation: `col-layout(fix) + col-layout(no-inner)` = the `col-bg` element
counts (c5 0+2=2, c7 6+1=**7**, c8 0+3=3, c9 0+1=1, c10 0+5=5) — 1:1, no unaccounted section.
This is the **opposite** of the command's worst-case ("every column section changes structurally"):
an *unconditional* seed wrapper would move 4 fixtures / 11 innocent sections; the *gated* renderer
insert moves only c7.

- **Intra-c7 split:** c7 has **7** column-layout sections but the intended diff is **exactly 6**
  wraps — the 7th (`col-layout, no inner_bg`) must stay byte-identical *within* c7. Diff-audit c7
  to exactly 6 `product-card _inner` insertions, no more.
- **Membership card confirmed out of scope:** `sec[19]` carries `inner_bg=#FFFFFF` but matches
  `image-gallery` (not `column-layout-*`, no `col-bg` class) — `_COL_BG_CELL_OPEN_RE` won't match,
  so it stays surface-less → §8 new deferred, carries to 51.1.

> **Execution gate (mandatory, §7):** re-run the probe before regen as a confirmation (not
> discovery) step — assert the 6-fire / c7-only map still holds on the rebased tree; the
> diff-audit ratifies any surprise.

### 3.2 Dark-mode interaction — no `_detect_inner_bg` change needed

**Answer to the command's item (2): the `container_bg` precondition drop is NOT needed; do NOT
widen physical-card detection (`layout_analyzer.py:433`).**

- LEGO cards **already** have `inner_bg` via the 50.4 direct path — detection is sufficient.
  Dropping the `container_bg` precondition would set *more* `inner_bg` (paints nothing new here)
  and widen `layout_analyzer.py:433 if inner_bg is not None` → dark-mode regression surface for
  zero render gain. **Untouched.**
- The wrapper carries `class="product-card _inner"`. `product-card` is a **static** entry in the
  dark-mode stylesheet — `converter_service.py:1083` (`@media`) + `:1108` (`[data-ogsc]`) hardcode
  `.product-card { background-color:#2d2d44 !important; }`, emitted for every conversion regardless
  of use. So the card flips to the **nested-card shade `#2d2d44`** on the dark band (`col2-bg → #1a1a2e`)
  in dark mode **with zero change to the dark-CSS emitter** (out of scope) and zero new class.
  `#2d2d44`-on-`#1a1a2e` is exactly the correct "card distinct from band" contrast (41.3 `bgcolor-*`
  class contract preserved — light bg from the inline override, dark bg from the static class).

### 3.3 Scoped slice vs full 51.1 chain — standalone, no ratification blocker

**This slice is standalone and does NOT require the 51.1 composite-slot infrastructure**
(`SlotFill` discriminated union + sub-renderer recursion, `deferred/TRIAGE-2026-06-12.md`,
USER RATIFICATION pending since 2026-06-12). It reuses the **existing** `_inner` override
emission (`_build_token_overrides`:2054/2062), the RC-F2 insert precedent, `_find_matching_close`
(:98), and the static `product-card` dark class. No new schema, no bridge sites (§0 RC-A trap N/A).

**Closes:** `phase-53f-f7-column-seed-no-inner` for the 6 `column-layout` benefit cards.
**Explicitly deferred to the 51.1 chain (still pending ratification):**
- membership card [19] (`image-gallery` seed — §3.1);
- lime-border *float* (card inset so the band shows as a frame — this slice fills edge-to-edge);
- per-corner rounding / composite card-with-N-children (each child its own card);
- per-column card layouts where columns are genuinely separate cards.

## 4. Files to Create/Modify

- `app/design_sync/component_renderer.py` — **only production change.**
  1. new module regex `_COL_BG_CELL_OPEN_RE` (near `_BG_CLASS_*` / `_INNER_CLASS_*`, ~:393);
  2. new method `_wrap_col_bg_inner_card` (beside `_insert_first_table_bg_color`, ~:1378);
  3. 4-line fallback in `_apply_token_overrides` `_inner`/`background-color` branch (:1124-1126).
- `app/design_sync/tests/test_*` — new unit tests (§5, RED pre-fix). Suggested
  `test_column_card_surface.py`.
- **NOT modified** (per §2a): `email-templates/components/column-layout-{2,3,4}.html`,
  `component_matcher.py`, `converter_service.py` dark CSS, `layout_analyzer.py`.
- **Baselines (regen after diff-audit only):** `data/debug/7/expected.html`.
  c5/c6/c8/c9/c10 must be **verified byte-identical** (do not regen).

## 5. Implementation Steps

### Step 1 — module regex (anchor for the column-layout cell)

Mirror the `_BG_CLASS_BGCOLOR_RE` style (:389). Match the first `<td>` whose class carries a
col-bg token:

```python
# RC-F7: column-layout section wrapper cell (column-layout-2/3/4 seeds).
_COL_BG_CELL_OPEN_RE = re.compile(
    r'<td\b[^>]*\bclass="[^"]*(?:col2-bg|col3-bg|col4-bg)[^"]*"[^>]*>'
)
```

### Step 2 — the insert method (mirror RC-F2 `_insert_first_table_bg_color`:1350)

```python
def _wrap_col_bg_inner_card(self, html_str: str, color: str) -> str:
    """Wrap a column-layout section's body in an inner card surface (RC-F7).

    column-layout-{2,3,4} seeds carry no ``class="_inner"`` element, so a section
    with ``inner_bg`` set — a card floating on a coloured band (LEGO benefit
    cards) — loses its surface: the ``_inner`` bg override no-ops and content
    renders on the bare band. Mirroring RC-F2's insert-on-no-op
    (:meth:`_insert_first_table_bg_color`), when the ``_inner`` bg override finds
    no target AND the section rendered through a ``col[234]-bg`` cell, wrap that
    cell's whole body in ONE ``<table class="product-card _inner">`` painted with
    the card colour. A single per-section wrapper spans every column so the
    surface is uniform — per-column wrapping leaves the band exposed below the
    shorter column (col_1 image vs col_2 text differ in height). ``product-card``
    is a static dark-mode class (``converter_service.py`` → ``#2d2d44``), so the
    card flips to the nested-card shade in dark mode with no dark-CSS change.
    Byte-identical no-op when no ``col[234]-bg`` cell is present (non-column seed).
    """
    safe = html.escape(color, quote=True)
    m = _COL_BG_CELL_OPEN_RE.search(html_str)
    if m is None:
        return html_str  # not a column-layout seed → byte-identical no-op
    content_start = m.end()
    close = _find_matching_close(html_str, "td", content_start)
    if close is None:
        return html_str  # unbalanced markup → leave untouched
    body = html_str[content_start:close]
    wrapper_open = (
        '<table role="presentation" class="product-card _inner" width="100%" '
        'cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;background-color:{safe};" '
        f'bgcolor="{safe}"><tr><td style="padding:0;">'
    )
    return (
        html_str[:content_start]
        + wrapper_open + body + "</td></tr></table>"
        + html_str[close:]
    )
```

- `_find_matching_close(html_str, "td", content_start)` (:98) walks depth-balanced `<td>`
  tokens — the col-bg cell wraps nested `<table>`/`<td>` rows, so a naive `</td>` would truncate
  (same reason the footer path uses it, :930).
- `padding:0` on the wrapper cell keeps the existing per-column `padding:20px` (`_cell` override)
  as the card's internal padding — no double padding, no seed change.

### Step 3 — wire the fallback (mirror RC-F2's `if replaced == result:` at :1114)

In `_apply_token_overrides`, `_inner`/`background-color` branch (:1124-1126):

```python
elif target == "_inner":
    if prop == "background-color":
        replaced = self._replace_inner_bg_color(result, val)
        if replaced == result:
            # RC-F7: column-layout seeds have no _inner target, so a card
            # section's inner_bg would no-op and content renders on the bare
            # band. Wrap the col[234]-bg cell body in a card surface.
            replaced = self._wrap_col_bg_inner_card(result, val)
        result = replaced
    elif prop == "border-radius":
        result = self._replace_inner_radius(result, val)
    # … width / align / class-add arms unchanged …
```

`_replace_inner_bg_color`'s regexes **all require an `_inner` element**, so `replaced == result`
reliably means "no `_inner` target" — the exact F2 detection. When a real `_inner` seed matches
(article-card etc.) it paints normally and the fallback is skipped (no double-wrap).

### Step 4 — radius composition (free, no extra code)

`_build_token_overrides` emits `inner_bg` (:2055) **before** `inner_radius` (:2062), so the wrap
is inserted first; a later `border-radius`/`_inner` override then matches the wrapper via
`_INNER_CLASS_RADIUS_INSERT_RE` (:418) and adds `border-radius + border-collapse:separate;
overflow:hidden;` → uniform rounded card (per-section, correct 4 corners). Current corpus carries
**no** column-card `inner_radius` (c7 `structure.json` has zero `cornerRadius`) → square card,
no radius insert. **Latent note:** the wrapper inherits any section-level `_inner` Rule-11
width/align overrides (:2068-2070) too — none in the current corpus; a future width-fit column
card is the natural trigger to promote to 51.1 per-section composite.

### Step 5 — unit tests (`test_column_card_surface.py`, RED pre-fix)

| Test | Asserts | RED today |
|---|---|---|
| `test_col_bg_inner_bg_wraps_card` | col-layout-2 render + `_inner` bg override → output has one `<table class="product-card _inner"` w/ `background-color` wrapping the col-bg body | ✅ (no wrap today) |
| `test_no_inner_bg_byte_identical` | same seed, **no** `_inner` override → output **==** input | ✅ guards no-op |
| `test_real_inner_seed_not_double_wrapped` | `article-card` (`_inner` present) + bg override → existing `_inner` painted, **no** `product-card` wrapper added | ✅ guards double-wrap |
| `test_wrapper_spans_both_columns` | 2-col body, unequal content → **one** `product-card _inner`; both `col_1` + `col_2` inside it (per-section, not per-column) | ✅ |
| `test_wrapper_carries_dark_class` | wrapper `class` contains `product-card` (static dark flip) | ✅ |
| `test_inner_radius_rounds_wrapper` | col-bg + bg + radius override → wrapper gains `border-radius` + `overflow:hidden` | ✅ radius compose |
| `test_non_column_seed_noop` | inner_bg override on HTML with no `col[234]-bg` cell and no `_inner` → output == input | ✅ safety |

> **Tests MUST render from the real `column-layout-{2,3,4}` seed (with the MSO `[if mso]` ghost
> comments), not a simplified fixture.** `_find_matching_close` counts `<td>`/`</td>` tokens
> *inside* comments; it lands on the true `col-bg` `</td>` only because the ghost's commented
> `<td width="…">` opens and `</td>` closes **balance** (N/N for column-layout-N). A stripped
> fixture would balance trivially and pass while the real render mis-nests. Assert the wrap is
> well-formed (opens/closes balance; both `col_1` and `col_2` fall between `<table class="product-card
> _inner">…</table>`) on the actual seed HTML — load via `_load_seeds()` / `COMPONENT_SEEDS`. The
> c7 snapshot regen (§7) + golden-conformance are the integration backstop for malformed wraps.

## 6. Security Checklist

- **No new/changed endpoints** — pure HTML-rendering internal method.
- **No injection surface** — `color` is `section.inner_bg` (design-sourced hex), `html.escape`d
  into both the style value and `bgcolor` attr (mirrors F2 `_insert_first_table_bg_color`).
  No user free-text reaches the wrapper; downstream `sanitize_web_tags_for_email()` unaffected
  (table/tr/td only — HTML Email Structure Rules honoured: no `<p>`/`<div>`-for-layout).
- **No auth/rate-limit surface.**

## 7. Verification — §3 measurement contract (parent plan §3, no exceptions)

**Gates (per §0):** `make types` · design_sync + components suites · golden-conformance · scoped
lint. `make test` before ship, then `git checkout -- app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml`.

- [ ] **A3 before/after** (all 6, `full_image`/`section_min`/`section_median`), appended to
  `53-f-render-fidelity.md` §6. **Expected:** c7 card sections gain a white surface → c7
  `section_min`/`section_median` up (white now dominant vs bare lime); `full_image` up modestly
  (hero-asset gap [F1] + membership card [out of scope] still cap it — do **not** claim a full
  ≥0.80 close). c5/c6/c8/c9/c10 **flat** (byte-identical).
- [ ] **Byte-identity proof:** `git diff --stat data/debug/*/expected.html` touches **only c7**;
  c5/c6/c8/c9/c10 unchanged. In c7 the diff is **exactly 6** `<table class="product-card _inner"
  … background-color:#FFFFFF>` wrappers (one per `sec[5,7,9,11,13,15]`) — the 7th `col-bg` section
  and `sec[19]` (`image-gallery` membership card) must be **byte-identical within c7**. Regen with
  `python scripts/snapshot-capture.py 7 --overwrite` **after** manual intended-vs-structural
  diff-audit (Track-B playbook, [[reference_converter_trackb_playbook]]); nothing else structural.
- [ ] **Ladder 13/9/8/10/8/12 held** — the wrap is intra-section (no section add/remove);
  confirm the count is unchanged (A2 strict; mammut xfail untouched).
- [ ] **Visual spot-check (the gate):** `uv run python scripts/score-fidelity-cases.py` → Read
  the c7 side-by-side composite in `.tmpscratch/fidelity/`: card content now on a **uniform
  white surface**, not ragged, not bare lime; band (lime) still frames the section edge.
- [x] **Dark-mode spot-check — satisfied by cascade analysis, not the composite render.** The wrapper
  carries the static `product-card` class, whose dark-CSS rule (`converter_service.py:1083` `@media` +
  `:1108` `[data-ogsc]`) sets `background-color:#2d2d44 !important`; author `!important` beats both the
  inline `background-color:#FFFFFF` and the `bgcolor` attr, so the card is `#2d2d44` on the `#1a1a2e`
  band in dark mode with zero dark-CSS change. Stated as a substitution: the cascade is deterministic,
  so the named dark composite was not separately rendered.
- [ ] `rendered_w600.png` left frozen (advisory-only, stale since F5/F6 — do not fold their drift).

## 8. Deferred-items handling (at ship time)

- **Close** `phase-53f-f7-column-seed-no-inner`: it is documented in `53-f-render-fidelity.md`
  §5:435-440 but **not yet in `.agents/deferred-items.json`** (verified absent). Add it as
  `status:"closed"` with `closed_commit`, `code_refs` → `component_renderer.py:_wrap_col_bg_inner_card`,
  and a `closure_note` scoping the close to the 6 `column-layout` benefit cards (membership card
  [19] excluded). Follow `.claude/rules/deferred-items.md` schema.
- **New deferred** `phase-53f-f7-image-gallery-membership-card` (confirmed): membership card [19]
  matches `image-gallery` (no `_inner`, no `col-bg`), so this slice's `_COL_BG_CELL_OPEN_RE` skips
  it — the LEGO VIP card still renders surface-less. `closes_when`: 51.1 composite gives
  `image-gallery` a card wrapper, or an `image-gallery`-specific insert analog ships.
  `blocked_by`: `phase-51-converter-fidelity-51.2` (card-with-N-children).
- **Update** `53-f-render-fidelity.md` §5 `phase-53f-f7-column-seed-no-inner` bullet → CLOSED, and
  add the §6 A3 row `F7 (cards)`.
- Untouched companions: `phase-53f-f7-text-block-cta-hardcoded-radius` (in JSON, orthogonal —
  CTA radius, not card surface); the 51.1 chain (TRIAGE, ratification pending).

## 9. Out of scope / limitations (honest ceiling)

1. **Edge-to-edge fill, not float** — the white card fills the `col2-bg` cell; the lime shows only
   at the section's outer edge, not as an inset frame around the card. Net pixel win (reference is
   mostly-white-card > current all-lime), but the inset "floating card" is 51.1 (needs cell padding).
2. **Membership card [19]** unaffected (`image-gallery` seed — §3.1, §8).
3. **Rounded via `inner_radius`** — the plan's "square card" assumption was wrong: c7 cards carry
   `inner_radius=12`, so the wrapper rounds (`border-radius:12px` + `border-collapse:separate;overflow:hidden`
   clips). Only *per-corner* (non-uniform) rounding remains 51.1.
4. **Per-section only** — genuinely-separate side-by-side cards (each column its own card) need the
   51.1 composite path; this wrap treats a column section as one card.
5. `_wrap_col_bg_inner_card` wraps the **first** `col-bg` cell per rendered section HTML — correct
   because each section renders one seed; a hypothetical multi-col-bg seed would only wrap the first
   (flagged, not in corpus).
6. **Outlook ghost overflow (logged latent, EXECUTED 2026-07-05).** The wrapper `<td>` becomes the
   section's first cell, so the `_cell` 20px padding override (`component_matcher.py:2169`) lands on
   it — OUTSIDE the 600px MSO ghost. In the Word engine: `100%` wrapper → 40px horizontal padding →
   a fixed 600px ghost in a 560px box → the card renders ~40px too wide. Chromium honours the `100%`
   wrapper and is correct; the fidelity scorer (Chromium) + DOM/string unit tests + `make test` never
   render the MSO path, so no gate caught it (same class as F3's attr/width latent). **Non-blocking**
   (converter fidelity is Chromium-scored; c7 0.636→0.719 is the Chromium win). A stopgap — drop the
   wrapper td's `style="padding:0"` so `_cell` stays on `col_1` inside the ghost — is Outlook-safe but
   reintroduces the pre-fix image/text top misalignment and lowers the Chromium score, so the holistic
   fix (thread padding inside the per-column ghost cells) is deferred to the 51.1 card-padding
   restructure → `phase-53f-f7-card-wrapper-outlook-ghost-overflow`.
