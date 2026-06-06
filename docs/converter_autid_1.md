# Figma→Email Converter Engine — Fidelity Audit

**Status:** Decision-ready engineering audit (READ-ONLY investigation — no repo code changed)
**Branch:** `tech-debt/phase-52-converter-foundation`
**Date:** 2026-06-01
**Audience:** Senior engineer + project owner choosing the Phase-53 engine fork
**Scope:** 6 real debug fixtures (`data/debug/{5,6,7,8,9,10}/`), empirical render-vs-reference, code attribution at `file:line`, adversarial verification.
**Method:** Orchestrator rendered all 6 fixtures' current converter output (Playwright, width=600, dsf=1) and visually compared each to its design reference, establishing the structural-delta spine; a 24-agent read-only workflow then attributed each defect to code and adversarially refuted each finding. The five load-bearing claims (mode-B orphan `<tr>`, footer-regex truncation, alt leaks, blind metric, the 5-string metric regex) were **independently re-verified by the orchestrator** against the live HTML this session (see §10).

> **One-line bottom line:** There are **two** structural layers. (1) **Segmentation** — *how many* sections the design is cut into — is **wrong on 5 of 6 fixtures** (LEGO: 17 vs ~8), a defect *upstream* of the renderer in `layout_analyzer.analyze_layout`; this is the **dominant *structural*** gap (note: the per-section render bugs below are the more *visually salient* ones to a human viewer). (2) **Per-section rendering** — slot-fill leaks, column collapse (a single function, `_build_column_fill_html`), alt, overflow — are in-engine bugs, all individually fixable. Plus a fidelity metric that scores the broken output 1.0. **Honest sequence: repair the metric (52.1) → fix the cheap per-section render bugs in place → address segmentation, which is where the engine-fork choice actually bites — a parallel audit *reports* (not verified here) that fork (b)'s recursive renderer produces correct band grouping natively, whereas fork (a) can only patch the asymmetric wrapper pass.**

> ### ⚠ Reconciliation correction (added 2026-06-01, post-synthesis)
> This audit's *original* headline — "section selection + ordering are mostly correct; structure is not the problem" — was **overconfident and is partly refuted.** It was measured against each fixture's `manifest.yaml` `count`, which is the converter's **own** output count (calibrated so the regression passes) — the same self-referential trap as `expected.html == actual.html`. Comparing instead against the design's true band structure (the manifest *descriptions* and the reference PNGs) shows the converter emits the **wrong number of sections on 5/6 fixtures** (over-segments LEGO 17-vs-8 and slate 10-vs-8; under-segments maap 11-vs-13, Starbucks 5-vs-9, mammut 14-vs-18; only case 8 on-target). **Two parallel-session audits — `docs/converter_audit_2.md` (17-agent) and `docs/converter_audit_3.md` (34-agent) — independently reached this segmentation finding as their headline, and this audit now confirms it in code** (see §4.0). What stands unchanged: the per-section render-defect attributions (§5.1–5.4), all independently re-verified at `file:line` — these *converge* with the parallel audits. What is corrected: the *ranking* — segmentation is the dominant *structural* defect, and the §6 fork recommendation is rebalanced (fork (b) is a stronger candidate than the original framing credited, because audit_2 **reports** that a live spike of the recursive renderer produced the correct **8 LEGO bands** — imported from the parallel audit and **not independently verified in this audit**; it also runs against a documented prior that the recursive renderer was "never pixel-faithful," so treat it as a lead to confirm at the 53.1 spike, not settled fact).

---

## 1. Executive Summary

**The real problem in one paragraph.** The converter's section *ordering* is mostly correct — what it emits appears in roughly the right top-to-bottom flow — but the **number** of sections (the segmentation / band grouping) is **wrong on 5 of 6 fixtures** (see §4.0, the dominant structural defect, confirmed against the design band counts and by two parallel audits). *On top of that*, the per-section HTML carries a cluster of **specific, tractable rendering defects** in the slot-fill and column-injection code, plus a **narrow fork-gated structural ceiling** (the fixed-seed renderer cannot express archetypes/proportions no seed encodes). The render defects are individually small bugs — a content-gated filler that never blanks an unfilled slot, a non-greedy regex that truncates a footer at the first nested `</td>`, a column builder that concatenates `<tr>` rows into a single cell with no enclosing `<table>` — but they dominate the *visible per-section* failure because they leak placeholder text, scatter navigation rows, and mis-place CTAs on every applicable fixture. Compounding all of it, the only fidelity metric that runs is **blind**: `report.json` self-scores cases 6/8/10 at `slot_fill_rate: 1.0` and `overall_score: 0.975–1.0` *on malformed output*, and scores `section_count_accuracy: 1.0` on LEGO's 17-vs-8 over-segmentation (verified) because it compares to the self-referential manifest. So the system ships these defects and reports them as perfect.

**The key reframe (scoped to the per-section render layer).** Within the per-section rendering, the scariest-*looking* mode is not architectural: **grid/column collapse into a vertical stack (mode B) is NOT the RC-C ceiling — it is a single-function slot-injection bug.** `_build_column_fill_html` emits bare `<img>` + `<tr><td>…</td></tr>` rows + bare `<a>` joined and stuffed into one `<td data-slot="col_N">` with no inner `<table>` (confirmed: `data/debug/8/actual.html:167-187` — orphan `<tr>` directly inside `col_1`). Browsers and Outlook foster-parent those orphan rows out of the cell, producing the scatter. This is fixable **in-place, in the current engine**, in a single function.

**Dominant failure modes, ranked by impact:**

| Rank | Mode | What it looks like | Cause class | Fixable in-engine? |
|------|------|--------------------|-------------|-------------------|
| **0** | **SEG — wrong section count / band grouping** | design's ~8 bands become 17 (LEGO) or design's 13 become 11 (maap); too many / too few sections before any seed is chosen | **segmentation** — asymmetric wrapper-unwrap in `layout_analyzer.analyze_layout` (`figma/layout_analyzer.py:272`, `_is_container_wrapper:579-584`); `match_all` is strict 1:1 so the count is frozen upstream | **Hard** — a one-way splitter regresses LEGO; fork (b) fixes natively |
| 1 | **B — grid/column collapse** | nav rows scatter, CTAs float to top of cell, multi-child columns vertical-stack | slot-injection bug (`_build_column_fill_html`) | **Yes** |
| 2 | **A — slot-fill placeholder leak** | "Section Heading"/"Article Heading"/"Headline 1/2"/"123 Business Street" render as live copy | content-gated fillers never blank unfilled slots + 1 regex truncation | **Yes** |
| 3 | **E-alt — Figma layer name in alt** | `alt="mj-image"` gray boxes; alt is raw Figma node name | image fillers never write `alt` | **Yes (alt slice)** |
| 4 | **D — horizontal overflow** | a 640px seed table exceeds the 600px frame | seed width + MSO-width clamp misses `max-width`/640 | **Yes** |
| 5 | **RC-C — archetype/proportion ceiling** | vertical bold nav-menu matched to horizontal NavigationBar; 70/30 splits unrepresentable; composite nesting drop | no seed of that shape exists | **No — fork-gated** |
| 6 | **RC-F — metric blindness** | self-score 0.99/1.0 on broken output | metric default-regex recognizes only 5 strings | Yes, but **separate** (52.1) |

Test artifacts (case-5 hero over-tall, image gray boxes, mode-C proportion boxes) are **confirmed asset-resolution artifacts, not converter bugs** — see §7.

---

## 2. Scope & Method

- **Fixtures:** 6 real debug cases under `data/debug/{5,6,7,8,9,10}/`, each carrying `actual.html` (shipped converter output) + a reference design. These are real Figma imports (MAAP, Starbucks, etc.), not synthetic HTML.
- **Render basis:** rendered/compared at the email frame **width = 600, device-scale-factor = 1**. The metric path renders Gmail-class only (`fidelity_service.py` hardcodes `gmail_web` per the plan).
- **Code attribution:** every defect traced to `file:line` in `app/design_sync/component_matcher.py`, `component_renderer.py`, and the committed seed HTML under `email-templates/components/*.html`.
- **Adversarial verification:** each diagnosis was cross-checked with a *discriminating* grep that would have refuted it if wrong (e.g. the footer-truncation claim was tested by `grep "Company Name|All rights reserved"` returning **0** while the address survives — proving consumption, not "outside the slot").
- **READ-ONLY:** no repo file was modified. All claims below are confirmed by `grep`/`git`/file reads, not inference. Counts in §4 were re-derived directly from the rendered HTML, not taken on faith from the catalog.
- **Segmentation ground truth (§4.0):** section *count* is judged against the design's true band structure (manifest `description` band intent + reference PNGs), **not** the self-referential `manifest.count` (the converter's own output). This is the one place the original synthesis erred; it is reconciled here and cross-validated against two same-day parallel-session audits (`docs/converter_audit_2.md`, `docs/converter_audit_3.md`) that reached the segmentation finding independently.

---

## 3. What Phase 52 Already Fixed (do not re-chase)

The Phase-52 token-override plumbing is **visibly live in the shipped HTML** — confirm before re-attacking:

- **Real design hex colors reach the output.** Case 6 carries `#006241`, `#AA1733`, `#296042` (Starbucks greens/reds), not seed defaults — confirmed in `data/debug/6/actual.html`. The Euclidean brand-sweep is correctly *off* this path.
- **Design typography reaches the output.** Roboto family, letter-spacing, pill `border-radius`, and CTA border (`1px solid #F7F0E4`) are emitted from design tokens (52.4 / 52.4b "style CTA labels from design typography," commit `144aba27`).
- **Multi-column text styling (col_N gap) landed** (52.4d, commits `4fdfc514` / `23d03a20`).
- **Fidelity metric made color-aware + min-aggregated** (52.1 partial, commit `3099ca82`) — but still does not *run by default* and the slot-fill-rate sub-metric stays blind (see §5 RC-F).

**Do not re-chase:** color/typography token emission, CTA label styling, col_N text styling. These work. The residual color defect (case-6 section_2 ghost-CTA fill defaulting to `#0066cc`) is a **narrow per-instance miss**, not a plumbing failure — the border and radius were captured; only the fill defaulted.

---

## 4. Empirical Findings

### 4.0 Section count / segmentation — the dominant structural defect (reconciled)

The converter cuts the design into the **wrong number of sections** on 5 of 6 fixtures. This is *upstream* of seed-matching and the per-section render bugs below — it is the single biggest structural gap, and it is the finding this audit originally under-weighted (it trusted the self-referential `manifest.count`). Verified by comparing the manifest **description** (the human band intent) and the reference PNGs against the converter's emitted section count:

| Case | Design bands (description) | Converter count | Direction |
|------|----------------------------|-----------------|-----------|
| 5 (maap) | 13 | 11 | **under** |
| 6 (Starbucks) | 9 | 5 | **under** |
| 7 (LEGO) | **8** | **17** | **over (+9)** |
| 8 (performance) | 10 | 10 | on-target |
| 9 (slate) | 8 | 10 | over (medium-confidence) |
| 10 (mammut) | 18 | 14 | **under** |

**Mechanism (attributed; confirmed in code).** Segmentation happens in `analyze_layout` (`app/design_sync/figma/layout_analyzer.py:272`), *before* `component_matcher.match_all` (`component_matcher.py:96`, a strict 1:1 map that cannot change the count). The single mechanism producing **both** directions is the wrapper-unwrap pass (`_get_section_candidates:520` + `_expand_container_wrappers:540`) behaving asymmetrically: `_is_container_wrapper` (`figma/layout_analyzer.py:579-584`) requires a non-default fill **AND ≥2 section children**, so single-child wrappers stay **merged** (under-count) while multi-child card wrappers **explode** each child to a top-level section (over-count). A naive one-way "splitter" — the only fix prior plans floated — would make LEGO/slate *worse*. Nuance: LEGO's target is **8 visual bands, not 8 flat sections** (the hand-authored reference is itself ~17 finer blocks grouped *within* 8 bands), so the real fix is band-**grouping**, not raw splitting.

**Cross-validation.** This converges with two parallel-session audits done the same day: `docs/converter_audit_2.md` (17-agent forensic, ran the live pipeline) and `docs/converter_audit_3.md` (34-agent, produced the full per-stage count ladder). Both pin the defect to the same stage. **audit_2 *reports* that a live spike of the deleted recursive renderer (fork b) produced the correct 8 LEGO bands** — this audit did **not** independently re-run that spike, and it runs against the documented prior that the recursive renderer was "never pixel-faithful," so treat it as a lead, not settled fact. Per audit_2/audit_3, the recursive renderer walks the Figma tree directly rather than calling `analyze_layout`, which (if accurate) is why it would bypass the broken segmentation. Either way, the engine-fork choice (§6) is really *about segmentation*, not about the cheap per-section render bugs.

### 4.1 Per-case summary

> **Note on the "Structure correct?" column:** "Yes" here means *ordering/flow* is broadly right — it does **not** mean the section **count** is right. Per §4.0, the count is wrong on 5/6 cases. The original catalog's "structure_correct: true" was measured against the self-referential `manifest.count` and is corrected by §4.0.

| Case | Structure correct? | Dominant observed defects | Notes |
|------|--------------------|--------------------------|-------|
| **5** (MAAP) | Yes — 11/11 sections | A: "Section Heading" leak (×1) + footer "123 Business Street" (×1); B-adjacent: city-pill group split into mismatched 3-col/4-col grids; RC-C: vertical nav-menu matched to horizontal NavigationBar; E-alt: non-descriptive alt (×6) | Hero "over-tall" = **test artifact** (node 2833:1628 is genuinely 600×800; converter emits correct `width=600 height=800`). |
| **6** (Starbucks) | Yes — 5 wrappers 1:1 | B: orphan `<tr>` in every multi-child column → nav scatter + "Peek at what's coming" CTA floats top-right; color: section_2 ghost-CTA fill `#0066cc` vs cream-outline; A: footer legal-text block dropped; E-alt: non-descriptive alt (×7) | `report.json`: `slot_fill_rate 1.0 / overall 1.0` on malformed output — **direct RC-F evidence.** |
| **7** | Yes | A: "Section Heading" leak (×2) + footer "123 Business Street" (×1); E-alt (×11) | Probe: `case7[0]` text-block has body `'View online \| My Account'` but no heading → `fills=['body']`, heading unfilled → seed default survives at `actual.html:97`. |
| **8** | Yes | **B: orphan `<tr>` directly inside `col_1`/`col_2` with no inner table** (V8/ENGINE — `actual.html:167-187`, verified); E-alt (×4) | `report.json`: `slot_fill_rate 1.0 / overall 0.975`. The cleanest single proof of mode B. |
| **9** | Yes | A: "Section Heading" (×1) + **invented "Headline 1/2" grid (×8)** from `col-icon` mis-match; D: 640px table overflow (`actual.html:84-90`, verified); E-alt (×13, incl. `mj-image, (mjml:mj-image)` variant ×7, "Grid image 1/2" ×2, literal `image_alt` ×2) | `col-icon` (2-col component) matched to single-icon+body sections → cardinality mismatch; 4 leaks visible in Playwright (non-slotted mobile copies), 8 total in grep. |
| **10** | Yes | A: "Article Heading" leak (×1); E-alt (×12, incl. "Article image" ×1) | `actual.html:185`: `src` rewritten to real asset but `alt="Article image"` survives — proving `_fill_image_slot` ignores alt. `report.json`: `slot_fill_rate 1.0 / overall 1.0`. |

### 4.2 Cross-fixture taxonomy (failure mode × case)

Counts are **re-verified directly from the rendered HTML this session**. The E-alt counts are non-descriptive placeholder alts (Figma layer-name leaks + generic placeholders): the verified composition is `alt="mj-image"` (exact: 5/6/8/0/0/8 for c5–c10), the longer `alt="mj-image, (mjml:mj-image)[, (type: logo)]"` variant (c9 = 7), `alt="Full width image"` (1/1/3/4/2/3), `alt="Grid image 1/2"` (c9 = 2), `alt="Article image"` (c10 = 1), and the literal slot id `alt="image_alt"` (c9 = 2). All are confirmed real leaks: `data-component-name="mj-image"` = **0** in all 6 cases, so none are component-name false hits. (Some images correctly emit `alt=""` — e.g. c9 has 8 — so the handling is *inconsistent*, not uniformly broken.)

| Failure mode | Cat | Sev | c5 | c6 | c7 | c8 | c9 | c10 | Freq | Fixable in-engine |
|--------------|-----|-----|----|----|----|----|----|-----|------|-------------------|
| **B** orphan `<tr>` in `col_N` (no inner table) | grid_collapse | critical | – | ✔ | – | ✔ | – | – | 2/6 | **Yes** |
| **A1** heading slot leak ("Section/Article Heading") | slot_fill_leak | major | 1 | – | 2 | – | 1 | 1 | 4/6 | **Yes** |
| **A1** "Headline 1/2" leak (col-icon) | slot_fill_leak | major | – | – | – | – | 8 | – | 1/6 | **Yes** |
| **A2** footer "123 Business Street" (regex truncation) | slot_fill_leak | major | 1 | – | 1 | – | – | – | 2/6 | **Yes** |
| **A**/drop footer legal-text block dropped | slot_fill_leak | major | – | ✔ | – | – | – | – | 1/6 | Partly (composite-gated) |
| **E-alt** non-descriptive alt (layer-name + generic placeholders) | asset_resolution | minor | 6 | 7 | 11 | 4 | 13 | 12 | 6/6 | **Yes** |
| **E-alt** "Grid image 1/2" / "Article image" survives | asset_resolution | minor | – | – | – | – | 2 | 1 | 2/6 | **Yes** (alt) |
| **Color** ghost-CTA fill defaults `#0066cc` | color | major | – | ✔ | – | – | – | – | 1/6 | **Yes** |
| **Alignment** mismatched-column-count grids | alignment | major | ✔ | ✔ | – | – | – | – | 2/6 | Partly (composite-gated) |
| **RC-C** wrong archetype (vertical nav → horizontal) | typography | major | ✔ | – | – | – | – | – | 1/6 | **No — fork** |
| **D** 640px overflow vs 600 frame | overflow | minor | – | – | – | – | ✔ | – | 1/6 | **Yes** |
| **RC-F** metric blind (`slot_fill_rate 1.0` on leaks) | metric | systemic | – | ✔ | – | ✔ | – | ✔ | 3/6+ | Yes (separate) |
| *Test artifact* — hero over-tall / gray boxes | asset_resolution | n/a | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | 6/6 | **Not a bug** |

**Reading the table:** modes A, B, E-alt, D, and the section-2 color miss are **all in-engine fixable** and account for the majority of *visible* defects. The genuinely fork-gated residue is narrow: RC-C archetype/proportion/composite-nesting (the case-5 vertical nav, the mismatched-grid alignment, the case-6 footer-block drop).

---

## 5. Root-Cause Attribution

### 5.1 Mode A — slot-fill placeholder leak (fixable in-engine)

**Mechanism (A1, primary).** `render_section` → `_fill_slots` (`component_renderer.py:384, 538`) iterates **only** over `match.slot_fills` and writes content for each. Slots present in the seed HTML but absent from `slot_fills` are never touched — their baked-in default text survives. `_fill_slots` ends with a *warn-only* loop (`component_renderer.py:18` default regex; warn loop logs but does not strip). The `slot_fills` under-cover because the per-slug fillers are **content-gated**: `_fills_text_block` (`component_matcher.py:963`) appends a `heading` `SlotFill` only when `_first_heading(section.texts)` (`component_matcher.py:611`) is truthy. When a section has body text but **no heading**, no heading fill is created and the seed default survives. Same gate in `_fills_article_card` (`component_matcher.py:1023`).

Seed defaults live between the slot tags: `email-templates/components/text-block.html:7-8` (`'Section Heading'`), `article-card.html:32-33` (`'Article Heading'`), `col-icon.html:19-20,40-41` (slotted `'Headline 1/2'`).

**The mitigation that was never generalized.** Exactly one filler, `_fills_event_card` (`component_matcher.py:1231`), deliberately emits **empty-string** fills so the renderer blanks the placeholder default. That designed pattern was never applied to `text-block`/`article-card`/`footer`.

**Mechanism (A2, footer regex truncation — distinct bug).** `_fill_text_slot` (`component_renderer.py:601`) replaces slot content with a **non-greedy `.*?` + `count=1`** regex. The `email-footer` seed nests an inner `<table>` of `<td>` cells inside the `footer_content` `<td>`. Because `.*?` is non-greedy, the fill terminates at the **first nested `</td>`** (the copyright cell), not the slot-closing `</td>`. The address row (`email-footer.html:16`) and links row are left dangling as malformed siblings. So `123 Business Street` is **not** "unfilled default outside the slot" — it is the un-consumed tail of a truncated match.

**Verification verdict — CONFIRMED (adversarial).** `grep -nE "Company Name|All rights reserved" data/debug/{5,7}/actual.html` → **0 hits** (copyright cell consumed), while `123 Business Street` survives (×1 each). The asymmetry refutes any "address is outside the slot" explanation and proves truncation. Re-verified this run.

**Mechanism (A4, non-slotted seed literals — structurally unfillable).** `col-icon.html:73,106` carry literal `'Headline 1/2'` with **no `data-slot`** inside the `!mso` web block. No matcher fix can fill them; only a seed edit removes them. (The slotted copies at `:19-20,40-41` are A1; the non-slotted at `:73,106` are the Playwright-visible leaks.)

**Verdict:** **Fixable in current fixed-seed engine — none fork-gated.** Single robust fix: a post-fill blank pass in `render_section` that subtracts filled-slot ids from template-slot ids and **blanks the inner text of leftover TEXT slots while keeping the `<td data-slot>` element** (the element is the editor/ESP hook — removing it regresses builder-sync). Plus delete ~3 non-slotted seed literals and fix the footer truncation regex (tag-balanced match, or have `_fills_footer` emit the whole inner table).

### 5.2 Mode B — grid/column collapse (fixable in-engine; NOT the RC-C ceiling)

**Mechanism.** `_build_column_fill_html` (`component_matcher.py:784`) builds a column's content by **concatenating** bare `<img …/>`, `_column_text_row(...)` (`component_matcher.py:693`, which emits `<tr><td>…</td></tr>`), and bare `<a …>`, then `"\n".join(parts)`. That blob is injected into a single `<td data-slot="col_N">` (e.g. `column-layout-2.html`). The result is orphan `<tr>` rows **directly inside a `<td>` with no enclosing `<table>`**.

**Verification verdict — CONFIRMED (live HTML).** `data/debug/8/actual.html:167-187` shows literally:
```
<td data-slot="col_1" ...>
  <tr><td ...>V8</td></tr>
  <tr><td ...>ENGINE</td></tr>
</td>
```
Browsers/Outlook foster-parent these orphan rows out of the cell → the V8/ENGINE label drops below the row, nav scatters, and the CTA (emitted as a sibling `<a>` after the orphan rows) reflows to the top of the cell. The seed *wrappers* (`column-layout-2/3/4`) DO render side-by-side via MSO ghost + inline-block `div`; the breakage is purely the cell content.

**Verdict:** **Fixable in current engine — single function.** Wrap all three child types as rows inside one inner `<table>` in `_build_column_fill_html`. Touches shared `_column_text_row` callers + `test_column_text_styling.py` / `test_cta_fidelity.py` assertions. This is the highest-impact single fix in the audit and it is **decisively not** the RC-C structural ceiling — that reframe changes the fork math.

### 5.3 Mode E-alt — image proportion/sizing + asset resolution (alt fixable; gray boxes are test artifact)

**Mechanism (alt leak).** Two independent failures leave seed/Figma alt intact: (1) `image_alt` is emitted as a *text-type* `SlotFill` (`component_matcher.py:1043,1093,1303`) carrying `img.node_name` — the raw Figma layer name (`'mj-image'`) — and routed to `_fill_text_slot`, which searches for `data-slot="image_alt"` (an element) but the seed marks alt with `data-slot-ALT="image_alt"` (a **dead attribute convention nothing reads**), so the fill no-ops. (2) `image_url` routes to `_fill_image_slot` (`component_renderer.py:636`), which rewrites `src` and `attr_overrides` but **never touches `alt`**.

**Verification verdict — CONFIRMED.** `data/debug/10/actual.html:185`: `src` rewritten to the real asset (`/api/v1/design-sync/assets/2833:1172.png`) but `alt="Article image"` survives — proving `_fill_image_slot` ignores alt and the text fill no-oped. `data-component-name="mj-image"` = 0 in all cases → the non-descriptive-alt counts (6/7/11/4/13/12 for c5–c10) are 100% real alt leaks, not component-name false hits. Exact `alt="mj-image"` = 5/6/8/0/0/8; the remainder are the `mj-image, (mjml:mj-image)` variant, "Full width image", "Grid image 1/2", "Article image", and the literal slot id `alt="image_alt"`.

**Mechanism (proportion / gray boxes = TEST ARTIFACT).** The converter already emits a derived `height` plus `width:100%;height:auto`. In production (resolved PNG) `height:auto` wins → natural aspect. The visible gray "588px" box is the **unresolved-asset artifact under Playwright** (the asset endpoint is not served in the test harness). This is mode F (asset resolution), not a converter proportion bug.

**Verdict:** **alt slice fixable in-engine** (route `alt` through `_fill_image_slot`; source real accessibility text or emit `alt=""` for decorative — never the Figma layer name; have `_fills_image_grid` emit alt fills; retire the dead `data-slot-alt`). Proportion/gray-boxes: **not a converter defect** — see §7 and §9.

### 5.4 Mode D — width / overflow (fixable in-engine)

**Mechanism.** `data/debug/9/actual.html:86` — a single seed table declares `max-width:640px` + MSO `width=640`, exceeding the 600 frame. `_update_mso_widths` (`component_renderer.py:1172`) rewrites `width=600` inside MSO blocks but **misses 640 and `max-width`**.

**Verdict:** **Fixable in-engine.** Correct the seed OR generalize the width clamp to catch `max-width` and non-600 MSO widths. Small.

### 5.5 RC-C — the fixed-seed structural ceiling (fork-gated)

**Mechanism.** The engine matches design content to a **seed that already exists** and injects content; it cannot synthesize a new layout shape. Three irreducible residues survive any in-place fix:
- **Arbitrary column proportions** — seeds bake fixed ratios (`column-layout-2` = 300/300; `article-card` ≈ 280/320). Only an `_inner` width override exists (`component_renderer.py:973`), not per-column ratio control. A 70/30 split cannot be matched faithfully.
- **No-matching-archetype** — case 5's large bold **vertical** nav-menu was matched to a **horizontal** NavigationBar because no vertical-link-menu seed exists. The honest cost of fixed-seed.
- **Heterogeneous composite nesting (Phase-51 composite-slot gap)** — a card holding tag-pills + spec-list + CTA *together* is inexpressible; slots take flat strings. Root of the case-5 city-pill group split and the case-6 footer-legal-block drop.

**Verdict:** **Fork-gated.** No in-place fix raises this ceiling; only authoring/parametrizing seeds (fork b/middle) or a recursive layout engine (fork b-restore / c) does.

### 5.6 RC-E ingest losses + RC-F metric blindness (context)

**RC-E (ingest, upstream of the renderer).** Effects/shadow, blendMode, scaleMode/imageTransform (image crop), rotation, AUTO/% line-height, z-order/overlap, and non-button strokes are **never parsed** (`figma/service.py`, `protocol.py`). Per the Phase-52 plan (`52.5`), translucent layers are also composited against a hardcoded `#FFFFFF` rather than the real backdrop — a *wrong-value before conversion* bug. These are **upstream of any renderer fork**; they need ingest+protocol work regardless of which engine is chosen.

**RC-F (metric blindness — why none of this was caught).** `compute_slot_fill_rate` (`app/design_sync/tests/regression_runner.py:67-69`) divides (total data-slot attrs − default-matched) by total, where "default" matches **only 5 strings**: `Image caption | Editorial heading | Section Heading | Lorem ipsum | https://example.com`. It is blind to `Headline`, `Article Heading`, `Grid image`, `mj-image`, and `123 Business Street`. Verified consequence: cases 6/8/10 report `slot_fill_rate: 1.0` and `overall_score: 0.975–1.0` **with leaks present**. The reported fidelity number is currently unfalsifiable.

> **Honesty note on the fidelity ladder.** Do not cite the historical 85→93→98% progression as evidence of progress. That ladder is computed by the blind/off-by-default metric this audit (RC-F) invalidates; citing it would launder the metric. Express outcomes by **defect-class closure**, not a percentage, until 52.1's color-aware, multi-client, min-aggregated metric is wired and actually runs.

---

## 6. Engine Decision (Phase 53 Fork)

Three forks, evaluated against the **observed** defects above. The Phase-52 plan (`.agents/plans/52-converter-foundation.md:151-156`) defines these exact three at the 53.1 decision gate. **Numbers for fork (a) are evidenced (from the verified catalog); numbers for (b)/(c) are projected (from the plan + existing infra).** Decision-ready ≠ falsely precise.

### Fork (a) — Keep fixed-seed engine + fix-in-place (incremental) — *EVIDENCED*
Keep `component_matcher → component_renderer` architecture unchanged; close defects with surgical fixes: post-fill blank pass (A), inner-table column builder (B), seed-literal cleanup + footer-regex fix (A2/A4), width clamp (D), alt derivation (E-alt). No recursive renderer, no composite-slot infra.

### Fork (b) — Restore the recursive renderer — *PROJECTED*
Recover the deleted recursive converter (`git show d9132c7c^:app/design_sync/converter.py`, ≈1625 LOC per plan line 154) **or** build forward on the existing tree bridge (`app/design_sync/tree_bridge.py`, `app/components/tree_compiler.py`, `app/components/tree_schema.py` — these files exist today). Re-plumb ingest to persist the `DesignNode`/`EmailTree` tree; render Figma Auto-Layout → nested tables. Buys typography/Auto-Layout/proportion/composite fidelity — **NOT** effects/geometry/pixel. This is the **middle fidelity tier** (per plan correction #1, line 33).

### Fork (c) — Per-frame rasterization for high-loss subtrees — *PROJECTED*
Rasterize high-loss subtrees (effects/gradients/overlap/vector) to PNG. Buys pixel fidelity for those subtrees; **destroys editable structure + ESP token/personalisation hooks** per rasterized frame (mutually exclusive with editability — plan line 155).

### Comparison (against the OBSERVED defects)

| Criterion | (a) Fix-in-place | (b) Recursive renderer | (c) Per-frame raster |
|-----------|------------------|------------------------|----------------------|
| Closes **B** (column collapse) | ✔ single function | ✔ (renders correct nesting natively) | ✔ (but as image) |
| Closes **A** (slot leaks) | ✔ blank pass + regex | ✔ (no seed defaults exist) | ✔ (no slots) |
| Closes **E-alt** | ✔ | ✔ | n/a (image) |
| Closes **D** (overflow) | ✔ | ✔ | ✔ |
| Closes **SEG** (wrong section count — §4.0, dominant *structural*) | ✗→partial (risky band-group pass on the asymmetric wrapper; one-way splitter regresses LEGO) | ✔ likely (audit_2 *reports* a live spike → 8 LEGO bands — **not verified here**; walks tree, skips `analyze_layout`) | ✔ (whole frame as image) |
| Closes **RC-C** archetype/proportion | ✗ residue stays | ✔ (the point of the fork) | ✔ (pixel-exact) |
| Closes RC-C composite nesting | ✗ | ✔ | ✔ |
| Effort | **Small–medium**, no arch change | **High** — recover/rebuild + re-plumb ingest | **Medium–high** + infra |
| Ceiling | defect-classes A/B/D/E-alt closed; RC-C residue remains | middle tier — no effects/geometry/pixel | pixel for rastered subtrees only |
| **Editability** | **Preserved/improved** (valid nesting parses cleanly in `ast-mapper.ts`) | Preserved if tree→table keeps `data-slot` hooks | **Destroyed per frame** (no slots/tokens) |
| Risk | Low–medium (regex/column rewrite; baselines regenerate) | Medium–high (1625 LOC recovery; ingest re-plumb; was deleted for a reason) | High (loses ESP/personalisation; image weight; CLS) |

### Recommendation (the choice is the owner's)

**Recommend: do the fork-independent work first (metric + cheap per-section render fixes via Fork-(a) techniques), then make the fork decision *as a decision about segmentation* — where Fork (b) is the leading candidate. Explicitly NOT Fork (c) as a default.** Reasoning:

1. **The per-section render defects (A, B, D, E-alt) are fork-independent and cheap.** Mode B (column collapse) is a single-function bug, not the architecture; modes A/D/E-alt are likewise small. Apply these in place under the current engine regardless of the fork — they close the dominant *visible per-section* failures at small–medium effort with no rewrite, and they keep `data-slot`/ESP hooks intact (the mode-B fix even *improves* `ast-mapper.ts` parsing).
2. **The fork decision is really about segmentation (§4.0), the dominant *structural* defect — and it is NOT a narrow residue.** Wrong section count affects **5/6 fixtures**. Fork (a) can only *patch* it (a band-grouping pass on the asymmetric wrapper — risky; a one-way splitter regresses LEGO/slate). **Fork (b) would fix it natively** — and a parallel audit (audit_2) *reports* a live spike of the recursive renderer producing the correct 8 LEGO bands (because, per that audit, it walks the Figma tree and never calls the broken `analyze_layout`). **This audit did not independently verify that spike, and it runs against a documented prior ("recursive renderer never pixel-faithful") — so it is a lead to confirm at the 53.1 spike, not proof.** With that caveat, the honest framing is *not* "(a) is enough, (b) is for a narrow residue" — it is "(a) clears the cheap render layer; (b) is the leading *candidate* for the dominant segmentation layer + the RC-C archetype/proportion residue."
3. **Sequence:** (i) repair the metric (52.1) — fork-independent precondition; (ii) ship the fork-(a) per-section render fixes — fork-independent, immediate visible wins; (iii) **then** run the 53.1 fork spike *with the metric live and segmentation as the explicit success criterion* — fork (b) carries the (imported, unverified) live-spike lead — **re-run that spike yourself first** as part of the gate; weigh its re-plumb cost (1625 LOC recovery **or** building on the existing `tree_bridge.py`/`tree_compiler.py`) against the band-grouping patch in (a).
4. **(c) is reserved for genuinely unreproducible subtrees only** (gradients/effects/overlap — §7), as a *fallback per subtree*, never the primary engine — it sacrifices the editability and ESP hooks the product depends on.

**Caveat the owner must weight:** the per-section fixes do **not** fix the blind metric (RC-F) *or* segmentation. If they ship without 52.1, the reported number won't move even as A/B/D close, and will keep scoring LEGO's 17-vs-8 over-segmentation as `section_count_accuracy: 1.0`. **52.1 (metric repair) must precede or accompany any fork** — it is fork-independent and is the precondition for trusting *any* of these choices. **The fork choice is the owner's** (53.1 decision gate); this audit makes it decision-ready and identifies (b) as the evidence-leading option for the dominant defect.

---

## 7. The Honest Ceiling (physically impossible in email — not bugs)

Do **not** conflate these with the defects above. No engine fork reproduces them in the email box model:

- **Gradient fills** (linear/radial) — no email-portable equivalent; flatten to solid or slice to image.
- **Drop/inner shadows, layer blur** (Figma effects) — never ingested AND not reproducible in mail-client CSS.
- **Layer rotation / arbitrary transforms** — table-cell layout cannot rotate content.
- **Blend modes** (multiply/overlay/screen) — no cross-client `mix-blend` support.
- **Inline/vector SVG** — stripped by most clients; only rasterized PNG survives.
- **Sub-pixel / overlapping / absolutely-positioned z-stacked layouts** — table grid cannot express z-overlap or fractional positioning.
- **True opacity over non-white** — dies at ingest (composited against `#FFFFFF`); even fixed, alpha-over-color is approximate.
- **Outlook/Word floor** — table+VML tops out around **~95%** on Outlook regardless of engine.

**Confirmed test artifacts (NOT ceiling, NOT bugs):** case-5 hero "over-tall" (node 2833:1628 is genuinely 600×800; converter emits correct dimensions); image gray boxes (asset endpoint unresolved under Playwright); mode-C proportion boxes (`height:auto` wins in prod). These vanish when assets resolve in production — see §9.

---

## 8. Recommended Fix Plan (sequenced backlog — NO code changes now)

Prioritized by **impact-on-observed-defects × tractability**. Fork-independence marked explicitly. Maps to existing Phase-52 subtasks where applicable. **Every fix changes the regression baseline** (`expected.html == actual.html`), so each item ends with *regenerate-and-review baselines*, not assert-unchanged.

| # | Item | Closes | Effort | Fork-gated? | Maps to |
|---|------|--------|--------|-------------|---------|
| **1** | **Repair + activate the fidelity metric** — color-aware, min-aggregated, multi-client incl. Outlook, run by default; extend `regression_runner.py` default-regex beyond the 5 strings | RC-F (unblinds A/B/D detection) | 3–4d | **Independent** | 52.1 |
| **2** | **Inner-table column builder** — wrap img/text/CTA as rows in one `<table>` in `_build_column_fill_html` | **B** (highest visible impact) | S–M | **Independent of (b)/(c)** | new (in (a)) |
| **3** | **Post-fill blank pass** in `render_section` — subtract filled from template slot ids, blank leftover TEXT slots (keep `<td data-slot>` element) | **A1** (Section/Article/Headline) | S | Independent | new (in (a)) |
| **4** | **Footer regex fix** — tag-balanced match OR have `_fills_footer` emit whole inner table | **A2** (123 Business Street) | S–M | Independent | new (in (a)) |
| **5** | **Seed-literal cleanup** — replace/remove non-slotted `Headline 1/2` (`col-icon.html:73,106`), `Grid image 1/2` | **A4** | S | Independent | new (in (a)) |
| **6** | **Alt derivation** — route `alt` through `_fill_image_slot`; never emit Figma layer name; `alt=""` for decorative; retire `data-slot-alt` | **E-alt** | S | Independent | new (in (a)) |
| **7** | **Width clamp** — generalize `_update_mso_widths` to catch `max-width`/640; or fix the seed | **D** | S | Independent | new (in (a)) |
| **8** | **Cardinality guard** — stop `col-icon` (2-col) matching single-icon+body sections | **A** (case-9 invented grid) | S–M | Independent | matcher |
| **9** | **Section-2 ghost-CTA fill** — emit captured fill/transparent instead of `#0066cc` default | color | S | Independent | 52.4 follow-up |
| **10** | **Serializer-bridge + override widening** (RC-A/RC-B/RC-D) — un-inert Phase-49/50 fields (text_color, text_align, url, radius, typography trio) | upstream fidelity | 0.5–3d each | Independent | 52.2 / 52.3 / 52.4 |
| **11** | **Ingest correctness** (RC-E) — composite alpha vs real bg, gradient `node_id`, non-button strokes, AUTO/% line-height | ingest loss | 2–3d | Independent (upstream) | 52.5 |
| **12** | **`_fix_text_contrast` mis-scoping** — depth-tracked close-tag scan | silent corruption | 0.5–1d | Independent | 52.6 |
| **SEG** | **Segmentation / band-grouping** (§4.0, *dominant* structural defect) — the *requirement* (group the design's nodes into the right number of visual bands) is fork-independent; the *implementation* is fork-dependent: in fork (a) a band-grouping pass over `analyze_layout`'s asymmetric wrapper-unwrap (risky — must not regress under-segmenting cases); in fork (b) it is *reported* to fall out natively (audit_2 live spike — unverified here; confirm at #13). **Do NOT ship a one-way splitter** (regresses LEGO/slate). | wrong section count (5/6) | M (a) / native (b) | **Decided at #13** | 53.1/53.2 |
| **13** | **FORK DECISION + spike** — with metric live, spike (a)/(b)/(c) on a committed fixture; **make segmentation (§4.0) the explicit success criterion**; choose by measured ΔE × effort | — | gate | **The gate** | 53.1 |
| **14** | **Fork (b) for RC-C residue** (if chosen) — recursive/tree renderer for vertical-nav archetype, arbitrary proportions, composite nesting | RC-C residue | High | **Gated on #13** | 53.2 |
| **15** | **Never-parsed ingest render** (effects/gradient reattach/crop/rotation → flat or `frame_export` fallback) | physical-ceiling fallbacks | — | Gated on fork | 53.3 |

**Sequence:** **#1 first** (fork-independent precondition — without it, #2–#9 close defects the metric still reports as 1.0). Then **#2–#9** (the in-engine fork-(a) defect closure, ordered by visible impact). **#10–#12** (fork-independent upstream/ingest correctness) can run in parallel. **#13** (decision gate) only after #1 makes the spike measurable. **#14–#15** gated on the fork choice.

**Items independent of the fork:** #1–#12 (all of fork (a), plus ingest/bridge/metric). **Items gated on the fork:** #13 (the decision), #14–#15 (the RC-C-residue engine and never-parsed render).

---

## 9. Open Questions / Things to Confirm

1. **Production asset resolution.** The gray boxes and case-5 hero "over-tall" are attributed to the Playwright harness not serving `/api/v1/design-sync/assets/*`. **Confirm** that in production the resolved PNGs fill these boxes at natural aspect (`height:auto` winning). If assets do **not** resolve in prod, mode C/F escalate from artifact to real defect.
2. **Grid detection vs grid rendering.** For the case-5 city-pill split (3-col then 4-col) and case-6 nav — is the failure in *detecting* the grouping (the matcher chose wrong column counts) or in *rendering* a correctly-detected group? The mode-B fix addresses rendering; if the column-count mismatch persists after #2, the defect is in detection (matcher), needing a separate fix.
3. **Does the deleted recursive renderer (`d9132c7c^`) still apply?** It was deleted for a reason (plan correction #1). Confirm whether fork (b) should recover it or build forward on the live `tree_bridge.py`/`tree_compiler.py` infra — the latter may be the lower-risk path.
4. **RC-F gate threshold.** After #1 lands as advisory, what ΔE/min-section threshold should gate CI? Must be set from a baseline scoring run, not guessed (plan risk note).
5. **Footer composite drop (case 6).** Is the legal-text-block drop the same A2 truncation, or the separate composite-nesting (RC-C) gap? If composite, it is fork-gated, not closed by #4.
6. **Is the segmentation fix cleanly fork-independent?** The two parallel audits diverge on this: audit_3 frames the band-grouping pass as "ship now, fork-independent"; audit_2 argues it is *not* cleanly fork-independent because fork (b) would do band-grouping natively, making a fixed-seed `analyze_layout` patch potentially throwaway. Honest reconciliation: the band-grouping *requirement* is fork-independent, but the *implementation* (patching flat-section segmentation) is not. Resolve before committing engineering time to a fork-(a) segmentation patch (item SEG) — it may be wasted if fork (b) wins at #13.
7. **Slate (case 9) target count is medium-confidence** — its "8 bands / over-segments to 10" rests on the manifest authors' judgment, not a direct band-count of its PNG in this pass. Re-count before treating slate's *direction* as settled.

---

## 10. Appendix

### File / line index (verified this audit)

| File | Lines | Role |
|------|-------|------|
| `app/design_sync/component_renderer.py` | `384` render_section; `419` `_strip_placeholder_urls`; `538` `_fill_slots`; `601` `_fill_text_slot` (truncation); `636` `_fill_image_slot` (ignores alt); `1172` `_update_mso_widths`; `18` default-string regex | Slot-fill + render |
| `app/design_sync/component_matcher.py` | `611` `_first_heading`; `693` `_column_text_row`; `784` `_build_column_fill_html` (mode B); `963` `_fills_text_block`; `1023` `_fills_article_card`; `1195` `_fills_footer`; `1231` `_fills_event_card` (the empty-fill mitigation) | Matching + fill emission |
| `app/design_sync/tests/regression_runner.py` | `67-69` default-string regex (5 strings — RC-F) | Blind metric |
| `email-templates/components/text-block.html` | `7-8` `'Section Heading'` default | Seed leak |
| `email-templates/components/article-card.html` | `18` `data-slot-alt`; `32-33` `'Article Heading'` | Seed leak |
| `email-templates/components/col-icon.html` | `19-20,40-41` slotted Headline; `73,106` non-slotted Headline | Seed leak |
| `email-templates/components/email-footer.html` | `7-29` nested-table slot (truncation target) | Seed leak |
| `email-templates/components/image-grid.html` | `16,30` `'Grid image 1/2'` | Seed leak |
| `data/debug/8/actual.html` | `167-187` orphan `<tr>` in `col_1`/`col_2` (mode B proof) | Live evidence |
| `data/debug/10/actual.html` | `185` `src` rewritten, `alt` survives (E-alt proof) | Live evidence |
| `data/debug/9/actual.html` | `86` 640px overflow (mode D) | Live evidence |
| `data/debug/{5,6,8,10}/report.json` | `slot_fill_rate 1.0`, `overall 0.975–1.0` on broken output (RC-F) | Live evidence |
| `app/design_sync/figma/layout_analyzer.py` | `272` `analyze_layout` (segmentation); `520` `_get_section_candidates`; `540` `_expand_container_wrappers`; `579-584` `_is_container_wrapper` (asymmetric ≥2-child predicate — SEG) | Segmentation stage |
| `app/design_sync/component_matcher.py` | `96` `match_all` (strict 1:1 — count frozen upstream) | Seed-match |
| `app/components/tree_schema.py`, `tree_compiler.py`, `app/design_sync/tree_bridge.py` | exist today | Fork-(b) anchor |

### Render method
Render/compare at **width = 600, dsf = 1**; metric path renders Gmail-class (`gmail_web`) only. Asset endpoint `/api/v1/design-sync/assets/*` is **not served under Playwright** → gray boxes are harness artifacts, not converter defects.

### Adversarial verifications performed
- Footer truncation: `grep "Company Name|All rights reserved"` = **0** (consumed) vs `123 Business Street` survives → truncation confirmed, "outside the slot" refuted.
- Alt leaks real: `data-component-name="mj-image"` = **0** in all 6 cases → the non-descriptive-alt counts (6/7/11/4/13/12 for c5–c10; exact `alt="mj-image"` = 5/6/8/0/0/8) are real alt leaks, not component-name false hits.
- Mode D overflow: `width="640"` + `max-width:640px` confirmed at `data/debug/9/actual.html:84-90`.
- Metric regex: `regression_runner.py:68-69` matches exactly 5 default strings (`Image caption|Editorial heading|Section Heading|Lorem ipsum|https://example.com`) — blind to `Headline`, `Article Heading`, `Grid image`, `mj-image`, `123 Business Street`.
- RC-F scores on broken output (verified `report.json`): c6/c8/c10 = `slot_fill_rate 1.0`, `overall 1.0/0.975/1.0`; c5/c7/c9 = `slot_fill_rate 0.95/0.94/0.96`, `overall 0.99` — all near-perfect despite confirmed leaks.
- Mode B structural: orphan `<tr>` directly inside `<td data-slot="col_1">` with no inner `<table>` confirmed in live HTML.

### Deferred-items / plan cross-refs
- **Plan:** `.agents/plans/52-converter-foundation.md` (Phase 52 foundation + Phase 53 engine fork; RC-A…RC-G map at lines 21-29; fork (a/b/c) at lines 151-156; honest ceiling at line 169).
- **Superseded numbering:** `.agents/plans/50-converter-fidelity-master.md` (50–53 labels marked stale per 52.7; do not cite its 85→99% ladder).
- **Deferred entries:** `phase-50.7-ac-4` / `phase-50.8-nested-physical-cards` (physical-card detection → old "Rule 9", now Phase 53). No deferred entry blocks the fork-(a) in-engine fixes (#2–#9).
- **Parallel-session audits (same day — this audit converges with both; reconciled in §4.0):** `docs/converter_audit_2.md` (17-agent forensic, live pipeline; *reports* a fork-b live spike → 8 LEGO bands — not independently verified in this audit), `docs/converter_audit_3.md` (34-agent, full per-stage count ladder). Both reach the segmentation defect as their headline. Where this audit adds value: the per-section render-defect attributions (§5) and the verified mode-B single-function reframe; where it was corrected: the segmentation ranking (§4.0 reconciliation).
- **Memory:** `project_converter_fidelity_phase52_53.md` (inert serializer-bridge RC-A/RC-B context + audit-2/3 reconciliation); `reference_local_converter_tests_red.md` (converter tests skip in CI, run locally — fixtures gitignored).

---

*This audit modified no repo files. Every code claim is cited at `file:line` and, where load-bearing, confirmed by grep/git/file evidence this session.*