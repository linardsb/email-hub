# Feature: VML rounded button on every button path (CE-11, #429)

The following plan should be complete, but validate documentation and codebase patterns and task sanity before you start implementing. Pay special attention to naming of existing utils, types and models.

Branch: `feat/ce-11-vml-every-button`, cut from `origin/main` `c63874d8` (CE-10 #470 merged). Work in the main checkout, where the gitignored A3 inputs live (`.claude/skills/converter-fix/references/a3-scoring.md`).

**Spike (gitignored, main checkout, `.tmpscratch/ce11/`).** The whole design below was prototyped on 2026-10-04 and reverted. `spike.patch` (304 lines, `component_matcher.py` + `component_renderer.py`) and `spike_vml_button.py` are a working reference, not the implementation: they lack tests and docstrings, carry two `x or N` defaults that `make lint-numeric` rejects (S11), use a function-local import and a lambda, and omit the follow-through tasks. Scripts, all run with `PYTHONPATH=. uv run python <script>`:

| script | what it prints |
|---|---|
| `corpus_check.py [--save DIR]` | per case: VML count, paired count, CTA anchors, href/label mismatches, MSO validity, MSO-stripped equality vs `before/`, "Shop Now" centres |
| `census_all.py` | every loaded seed with a CTA `data-slot` (42): VML count vs CTA anchors, pairing, new imbalance and browser-view equality vs the VML step disabled |
| `template_census.py [slug]` | every CTA-bearing slug rendered with 2 design buttons: VML count, pairing, chrome kind (`table`/`a`); with a slug, the twin it wrapped |
| `census_balance.py [--naive]` | tag balance of the Outlook and browser views per slug; `--naive` swaps in the defective chrome finder (mutation check) |
| `balance_check.py DIR` | the same balance check over a directory of full outputs |
| `views.py` | `outlook_view`, `browser_view`, `balanced` helpers (port into the test module, T3) |

`before/` holds the 7 `expected.html` from `c63874d8`; `a3-before.txt`/`a3-after.txt` and `scores-before.json`/`scores-after.json` hold the A3 runs.

## Decisions

The user asked on 2026-10-04 to raise confidence and close every risk. Q1 and Q2 of the first draft are resolved to their recommended options; the user can still overturn either before execution.

| # | Decision | Why |
|---|---|---|
| D1 | One builder module `app/design_sync/vml_button.py`: frozen `VmlButton` + `arcsize_pct` + `render_vml_button(spec, twin_html) -> str`. It never imports `ButtonElement` | CE-19 (#437) wraps MJML `mj-button` with it (`docs/architecture/dsl-compiler.md:171`, `:204` M6) |
| D2 | One adapter `_vml_button_spec(btn, *, fill, text_color, stroke_color, stroke_weight_px, max_width)` in `component_matcher.py` | Matcher and template paths share size, radius, font and label logic |
| D3 | Colour rule: **fill** = design `fill_color` (hex), else `fill="f"` (transparent), never a fallback colour. **Label colour** = the colour the HTML twin uses. **Stroke** = design stroke, else (template path only) the twin's `border:Npx solid #hex`, else none | Three corpus buttons have no design fill (S5). Their twin paints `#0066cc`/`#e84e0f` fallbacks, and the blue one is CE-20's allowlisted default-blue bug. Copying it into VML would spread that bug. The label must stay visible, so it follows the twin |
| D4 | Templates stay untouched. `ComponentRenderer.load()` strips the seed `<v:roundrect>` (cta-button only) and unwraps its `!mso` twin | Templates also feed the component library (`app/components/data/file_loader.py:59`, `seeds.py:180`). Removes the CE-13 (#431) same-file conflict. Template-library VML, if wanted, is a separate ticket (was Q2) |
| D5 | Template path: new renderer step after token overrides wraps every surviving CTA anchor (`data-slot` in `cta_url`, `primary_url`, `secondary_url`, `primary_cta_url`, `secondary_cta_url`) with a non-empty label, on every slug | Done check is "every CTA in the corpus"; the census covers all 42 seeds with a CTA slot (S6 for the 24 matcher literals, S12 for all 42) |
| D6 | Chrome (what gets hidden from Outlook): the innermost `<table>` that **truly encloses** the anchor (tag-stack scan, then `_find_matching_close`), contains no nested `<table>`, no `<img>`, exactly one `<a>`, and whose visible text equals the label. Otherwise the anchor alone. Outlook-only `<!--[if …mso…]>…<![endif]-->` blocks inside the chosen twin are removed | A naive backward search for `<table` swallowed the enclosing `</td></tr></table>` on `article-card` and `hero-block` (S7). Conditional comments do not nest, and the `button` seed carries `<!--[if mso]>&nbsp;<![endif]-->` inside its anchor |
| D7 | Arcsize = `floor(radius / min(width, height) * 100)`, clamped 0–50 | jsx-email pattern named by the DSL doc (`dsl-compiler.md:177`); reproduces the 3 golden variants (E5); matches a **measured classic Outlook render**: a 536×268 shape at `arcsize="19%"` draws a 50 px corner (50/268 = 18.7%), where the ECMA/MS reading predicts 25 px (E7) |
| D8 | VML `width`/`height` = the design box, stroke or not | The golden variant 2 uses `strokeweight="2px"` with no size change, and jsx-email passes width/height through. Whether Word grows the shape by the stroke (E8 hints it does) is a stroke-geometry leg owed by #422 (AC 9) |
| D9 | Per-corner radius uses the largest corner (was Q1) | VML has one radius. reframe "Register now" (0/12/12/0) still reads as rounded, not square. Corpus impact: 1 button, `arcsize` 25 (D7 at 48 px height) |
| D10 | No feature flag | Browser output is unchanged (S2, S4: A3 `scores.json` byte-identical). CE-9/CE-10 precedent |
| D11 | Template path: VML `href` and label come from the rendered twin anchor; colours, size, radius and font from the design button | `survey-scale` has a bare seed label with no fill slot, and the video placeholders hold two `cta_url` anchors of which `_fill_cta_slot` fills only the first (`component_renderer.py:1359-1369`, `count=1`). Taking them from the design button broke pairing on 3 seeds (S12). The twin is what non-Outlook clients link to and show, so Outlook must match it |

## Evidence

### Planning probes (observed 2026-10-03, `c63874d8`)

| id | Probe | Result |
|---|---|---|
| E1 | `grep -c v:roundrect data/debug/*/expected.html` | 0 for cases 5–10; reframe 4 (2 buttons × open + close) |
| E2 | CTA anchors per case (CE-2 predicate `content_checks.py:239-247` plus `data-slot` CTA anchors) | 8/2/9/2/2/2, reframe 3. Total 28; 2 with VML |
| E3 | CTA sources | Text-block composite (`component_matcher.py:1910-1915`) and column anchors (`:1040-1060`) for most; templates: c6 `event-card`, c9 seed `SHOP NOW`, reframe 2 × `cta-button` |
| E4 | reframe "Register now" | per-corner 0/12/12/0, 576×48 |
| E5 | golden `vml-rounded-button-variants.html` | 48h/5r → 10%, 44h/22r → 50%, 36h/3r → 8%; floor(r/min·100) gives 10/50/8 (derived) |
| E6 | jsx-email `button.tsx` | `Math.floor((borderRadius / height) * 100)`; `strokeweight` or `stroke="false"`; `fillcolor` or `fill="false"`; `<w:anchorlock/>` + `<center>` |
| E7 | MS VML doc vs dextinity PR #6296 | Spec: "% of half the smaller dimension". PR: classic Outlook draws 50 px for 19% on 536×268; it switched to radius ÷ full shorter side, capped at 50%, with before/after classic-Outlook screenshots |
| E8 | hteumeuleu/email-bugs #86 | Changing `strokeweight` means adding 2× the border weight to the VML width/height to keep the inner size; it does not say the box must shrink |
| E9 | `_strip_mso_blocks` (`test_converter_data_regression.py:66-70`) on a wrapped anchor | Returns `<td></td>`: wrong order. `content_checks.strip_mso` (`:231-236`) is right |
| E10 | `quality_contracts.py:171` | Counts open + close tags; `max(anchors, 2n)` hides missing buttons |
| E11 | `_repoint` (`unsubscribe_links.py:121-149`) | Skips comment contents, so VML hrefs are never repointed |
| E12 | `_cta` override VML passes (`component_renderer.py:1491-1507`, `:1975-1985`, `:1166-1173`) | Global over every roundrect/centre in a section: would repaint or delete matcher-path VML |
| E13 | `gh pr list --state open` | No open PR touches the matcher or renderer |

### Spike results (observed 2026-10-04, spike over `c63874d8`, reverted)

| id | Result |
|---|---|
| S1 | `corpus_check.py`: VML 8/2/9/2/2/2/3 = CTA anchors; every VML paired with its anchor (same href + label); 0 mismatches; `validate_mso_conditionals` valid on all 7; 0 "Shop Now" centres |
| S2 | MSO-stripped, whitespace-normalised output equals `before/` on all 7 cases |
| S3 | `balance_check.py`: Outlook view and browser view tag-balanced on all 7, before and after |
| S4 | A3 before (spike stashed) vs after: `scores-before.json` and `scores-after.json` byte-identical (`cmp`); full-image 0.866/0.813/0.840/0.863/0.812/0.736/0.854 |
| S5 | Design buttons with no fill: c5 "Discover →" (stroke #000000 1), c6 "Peek at what's coming" (stroke #F7F0E4 1), c9 "SHOP NOW" (stroke #FE5219 2). The other 25 have a hex fill. Width and height present on all 28 |
| S6 | `template_census.py`: all 24 CTA-bearing slugs emit one VML per filled CTA, paired; cta-pair and hero-2cta emit 2 with per-button colours. Chrome `table` for button/button-filled/button-ghost/button-responsive/cta/cta-button/cta-pair/editorial-1..5/article-2..4/article-reverse/event-card-minimal/hero-2cta; `a` for article-card, event-card(-banner), hero-block, hero-text, product-card |
| S7 | `census_balance.py --naive` (backward `rfind("<table")` finder): Outlook view unbalanced on `article-card`, `hero-block`. With D6: only `editorial-5`, which is unbalanced in its **seed** already (`balanced(outlook_view(seed))` false). The test asserts "no new imbalance" |
| S8 | The pipeline's formatter puts newlines/indent between `<![endif]-->` and `<!--[if !mso]>`; pairing regexes must allow `\s*` |
| S9 | Full `app/design_sync/tests` + `app/components/tests` on the spike: 12 failed, 3441 passed. The 12: 7 × `test_snapshot_matches[*]`; `test_cta_fidelity.py` `test_cta_bg_color_applied`, `test_cta_border_radius_applied`, `test_different_cta_colors_per_section` (seed VML via overrides, no design button), `test_render_places_cta_in_centered_row_after_body` (regex expects `<a>` right after `<td>`); `test_content_checks.py::test_non_mso_wrapped_cta_still_counts` (re-wraps an already wrapped anchor) |
| S11 | `make lint-numeric` on the spike: fails on `int(column_width or 600)` and `round(btn.stroke_weight or 1)` (falsy-numeric rule, `Makefile:526-528`). Implementation uses `x if x is not None else N` |
| S12 | `census_all.py`: 42 loaded seeds carry a CTA `data-slot`, and that equals every template file with one, so none is unreachable. With design href/label: pairing fails on `survey-scale`, `video-placeholder-inline`, `video-placeholder-overlay`. With D11: 0 problems on all 42 (VML count = filled CTAs, paired, no new imbalance, browser view equal). Corpus re-run after D11: S1/S2 unchanged |
| S13 | `make golden-conformance` on the spike: 26 passed, 9 skipped |
| S14 | `make fidelity-gate` (pinned Playwright 1.63.0 image) on the spike: `test_fidelity_gate_holds_baseline` PASSED, no re-stamp |
| S10 | c9 "SHOP NOW" (template path): VML shows the design stroke 2px #FE5219 at 16 px; the HTML twin shows template 14 px and no border (ledger g3 family: the template twin ignores the design box). VML follows the design by intent |

## Feature Description

Classic Outlook (Word engine) ignores `border-radius`, so an `<a>` button turns into a square box. The standard fix is a VML `<v:roundrect>` inside `<!--[if mso]>`, with the HTML button hidden from Outlook by `<!--[if !mso]><!-->…<!--<![endif]-->`. Only the `cta-button` seed has one today, and it keeps the seed label and URL. This ticket gives every converter CTA a design-driven VML twin from one builder.

## User Story

As an email developer converting a Figma design
I want every button to keep its radius, fill, stroke and size in classic Outlook
So that the Outlook render matches the design instead of falling back to square boxes.

## Problem Statement

R10: 26 of 28 corpus CTAs have no VML (E1, E2); the other 2 read "Shop Now" (ledger `ce-2-cta-button-vml-twin-unfilled`). The existing VML gets colour and radius from global regex passes and a 48 px height guess (`component_renderer.py:2110-2120`), which cannot handle two buttons in one section or matcher-built buttons.

## Solution Statement

Builder (D1) → matcher paths wrap their anchors (T4) → template path strips seed VML and wraps each surviving CTA with D6 chrome (T6) → dead global VML passes removed (T6) → unsubscribe, regression helper and quality contract follow through (T8–T10).

## Out of Scope / Non-Goals

- MJML path (`convert_document_mjml`): CE-19 (#437) wraps `mj-button` with this builder.
- Tree-bridge path (flag off; ledger `phase-53g-g4-tree-html-slot-row-shape`).
- `email-templates/components/*.html` (D4); template twin padding/font (ledger g3); button icon (`ce-10-cta-icon-not-rendered`); light-pill label colour (g5); the twin's `#0066cc` no-fill fallback (CE-20 allowlist).
- `text-link` and `navbar-link` anchors (links, not buttons). VML backgrounds.
- `editorial-5`'s pre-existing Outlook-view imbalance (S7): log in the report.
- Outlook visual check: owed by CE-4 (#422).

## Feature Metadata

**Feature Type**: Enhancement · **Complexity**: Medium · **Systems**: `app/design_sync` matcher, renderer, unsubscribe pass, quality contracts, regression harness · **Dependencies**: none new

## Related Work

**Implements**: #429 (CE-11, T6) · **Epic**: #439; slices `.agents/plans/converter-epic-slices.md:169-176`; DSL spec `docs/architecture/dsl-compiler.md` (M6)

**Back-references**: `.agents/plans/ce-10-button-icon-not-content-image.md` (plan shape, A3/gate recipe); `.agents/plans/ce-2-content-checks.md` (`strip_mso`, CTA counts); `.agents/plans/49.7-cta-fidelity.md` (`_cta` overrides).

**Forward-references**: CE-19 (#437) consumes `render_vml_button`; CE-13 (#431) no longer conflicts on button templates.

## Deferred Items Touching This Plan

| id | match | decision | why |
|----|-------|----------|-----|
| `ce-2-cta-button-vml-twin-unfilled` | `component_renderer.py:1359`, `cta-button.html:6` | **close** (T8, T14) | Seed VML gone; label/href from design; T8 adds the VML-href unsubscribe test its `closes_when` names |
| `phase-53g-g3-template-cta-padding-uncovered` | template CTAs, `_replace_cta_*` | carry forward | Twin keeps template padding/font (S10); add a note that VML now carries the design box |
| `phase-53g-g5-pill-white-on-light-latent` | `_column_cta_row`, `_fills_text_block` | carry forward | VML label follows the twin (D3), same fallback |
| `ce-10-cta-icon-not-rendered` | `_fills_cta` | carry forward | Icon absent on both surfaces |
| `phase-53g-g4-tree-html-slot-row-shape`, `phase-53g6-card-tree-path-text-only`, `ce-9-tree-path-corpus-compile-fallback` | tree path | avoid | Flag off |
| `phase-53g-g4-general-sub-template-recursion` | `render_composite` | avoid | VML rides inside terminal child values |
| `phase-53g-t1-*`, `ce-10-unnamed-button-icon-not-exported`, `ce-10-large-styled-icon-wrapper-exports-bare-glyph` | matcher refs | avoid | Unrelated paths |

Re-run before T1: `grep -n 'component_renderer\|component_matcher\|unsubscribe_links\|quality_contracts\|roundrect' .agents/deferred-items.json`.

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `.tmpscratch/ce11/spike.patch`, `spike_vml_button.py` - working reference for T2/T4/T6
- `email-templates/components/golden-references/vml-rounded-button-variants.html` - target markup
- `app/design_sync/component_matcher.py:840-905` (`_cta_label_typography`, `_cta_padding_css`, `_cta_radius_css`; radius fallback 4 px at `:905`), `:1040-1060` (`_column_cta_row`), `:1278-1293` (caller; `group.width`), `:1882-1945` (`_fills_text_block` CTA loop), `:540-600` (`_build_slot_fills` dispatch, `container_width` → `_cw`)
- `app/design_sync/component_matcher.py:668`, `:723`, `:743-760` - `_safe_text`, `_HEX_COLOR_RE`, `_safe_color`, `_safe_url`
- `app/design_sync/figma/layout_analyzer.py:112-138` (`ButtonElement`), `:1961-1965` (width/height)
- `app/design_sync/component_renderer.py:236-257` (`_find_matching_close`: pass the index **after** the open tag), `:647-656` (`load`), `:658-750` (`render_section`), `:1114-1174` (prune + `_strip_empty_cta_chrome`), `:1491-1513`, `:1971-2053`, `:2108-2120`
- `app/design_sync/unsubscribe_links.py:86-149`; `app/design_sync/quality_contracts.py:159-173`
- `app/design_sync/tests/test_converter_data_regression.py:57-70`; `content_checks.py:160-161`, `:231-247`; `test_content_checks.py:299-308`
- `app/qa_engine/mso_parser.py:345` (`validate_mso_conditionals`; needs the document's `xmlns:v` for its namespace check, so wrap fragments as `<html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">`)
- `app/design_sync/tests/test_cta_fidelity.py:42-111` (`_button`, `_make_section`, `_make_match`), `:301-341`, `:343-380`, `:517-530`
- `app/design_sync/tests/test_button_icon_exclusion.py:41-160` - Figma node-tree helpers (`_text`, `_btn`, `_column`, `_mj_section`, `_page`, `_analyze_one`)
- `app/design_sync/tests/test_unsubscribe_links.py`, `test_quality_contracts.py`, `test_content_groups.py:363` (`caplog` pattern)
- `.claude/skills/converter-fix/SKILL.md` + `references/baselines-and-gates.md`

### New Files to Create

- `app/design_sync/vml_button.py`
- `app/design_sync/tests/test_vml_button.py` (builder units)
- `app/design_sync/tests/test_vml_button_paths.py` (Figma-tree paths, template census, corpus invariant, view helpers)
- `.claude/reports/ce-11-vml-every-button-report.md`

### Relevant Documentation

- [MS VML arcsize](https://learn.microsoft.com/en-us/windows/win32/vml/msdn-online-vml-arcsize-attribute) - spec reading (not what Outlook does)
- [dextinity PR #6296](https://github.com/vivid-planet/dextinity/pull/6296) - classic Outlook arcsize measurement (D7)
- [jsx-email Button](https://github.com/shellscape/jsx-email/blob/main/packages/jsx-email/src/components/button.tsx) - pattern named by the DSL doc
- [email-bugs #86](https://github.com/hteumeuleu/email-bugs/issues/86) - strokeweight resizes the button (D8)

### Patterns to Follow

- Builders return strings and never raise on design data (`_column_divider_row`, `component_matcher.py:1021-1037`).
- Colours through `_HEX_COLOR_RE`; text `html.escape(…, quote=False)`; attribute values `quote=True` (`component_renderer.py:2042`).
- Logging `logger.warning("design_sync.<area>.<event>", …)` (`component_renderer.py:665-668`); names per `.claude/references/logging-standard.md`.
- Frozen dataclasses (`layout_analyzer.py:111`). No lambda assigned to a name (ruff E731; the spike used one with `noqa`: replace it with a helper).
- Lint: `pyproject.toml:126`; strict mypy/pyright: annotate `float | None`, `re.Match[str]`.

---

## IMPLEMENTATION PLAN

- Phase 1 Builder (T1–T2)
- Phase 2 Matcher paths (T3–T4). **Depends on:** Phase 1
- Phase 3 Template path + dead passes (T5–T7). **Depends on:** Phase 1 and T4 (shares the adapter)
- Phase 4 Follow-through (T8–T10). **Depends on:** Phase 3 for T8's test
- Phase 5 Corpus evidence, gates, report (T11–T15)

---

## STEP-BY-STEP TASKS

### T0 CAPTURE baselines

- **IMPLEMENT**: `.tmpscratch/ce11/before/` already holds the 7 `expected.html` from `c63874d8`; confirm `git diff c63874d8 -- data/debug` is empty, else re-copy. A3 before is `.tmpscratch/ce11/a3-before.txt` + `scores-before.json` (S4); re-run only if `origin/main` moved under `app/design_sync/`.
- **VALIDATE**: `ls .tmpscratch/ce11/before | wc -l` → 7.
- **SATISFIES**: AC 7

### T1 CREATE `app/design_sync/tests/test_vml_button.py` (RED)

- **IMPLEMENT**:
  1. Golden parity: the 3 golden variants → `arcsize` 10/50/8, `style="height:Hpx;v-text-anchor:middle;width:Wpx;"`, `fillcolor`, `strokecolor`, `<w:anchorlock/>`, `<center …>label</center>`.
  2. Shape: `<!--[if mso]><v:roundrect …>…</v:roundrect><![endif]--><!--[if !mso]><!-->{twin}<!--<![endif]-->`, exactly one opening `<v:roundrect `, twin verbatim, no whitespace added.
  3. Fill: `fill=None` → `fill="f"` and no `fillcolor`.
  4. Stroke: none → `stroke="f"`; with stroke → `strokecolor` + `strokeweight="Npx"`.
  5. Arcsize (`arcsize_pct`): clamp 50 (r40/h44); 0 → 0; `min(w,h)` (30w×48h r15 → 50); floor of the dextinity point (r50, 536×268 → 18; they measured 19% rounded).
  6. Escaping: label `Shop & <Save>`; href with `"`; font `'Helvetica Neue', Arial`.
  7. `xmlns:v` and `xmlns:w` on the roundrect.
  8. `validate_mso_conditionals` (namespaced wrapper, see refs) valid.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_vml_button.py -q` → import error (RED, record).
- **SATISFIES**: AC 1

### T2 CREATE `app/design_sync/vml_button.py`

- **IMPLEMENT**: from `.tmpscratch/ce11/spike_vml_button.py`: `VmlButton(href, label, width_px, height_px, radius_px, fill: str | None, text_color, stroke_color: str | None, stroke_weight_px: int | None, font_family, font_size_px, font_weight)`; `arcsize_pct`; `render_vml_button`. Replace the spike's lambda with a module helper `_attr(v) -> str`. Docstring cites the golden file, jsx-email, the dextinity measurement and the MS spec conflict (E7).
- **IMPORTS**: `html`, `math`, `dataclasses.dataclass` only (D1).
- **VALIDATE**: T1 green; `uv run mypy app/design_sync/vml_button.py && uv run pyright app/design_sync/vml_button.py`.
- **SATISFIES**: AC 1

### T3 CREATE `app/design_sync/tests/test_vml_button_paths.py`, matcher paths (RED)

- **IMPLEMENT**: helpers first: `PAIR_RE` (allow `\s*` between blocks, S8); `assert_paired(html)` (each VML's href and `<center>` text equal its twin anchor's); `outlook_view`/`browser_view`/`balanced` ported from `.tmpscratch/ce11/views.py`. Figma-tree tests via the `test_button_icon_exclusion.py` helpers → `analyze_layout` → `match_section` → `ComponentRenderer().render_section`:
  1. Text-block (heading + body + 1 filled button, radius) → 1 VML, paired, `fillcolor` = design fill, `arcsize` per D7.
  2. Text-block with 2 buttons, one outlined with **no fill** → 2 paired VML; the outlined one has `fill="f"`, `strokecolor`, `strokeweight`; its `<center>` colour equals the anchor's `color:`; no `#0066cc` inside any `<v:roundrect`.
  3. Two-column section with a button → wrapped; VML width ≤ column width.
  4. FILL button wider than its column → VML width clamped.
  5. Stroke keeps the design box (D8): 2px stroke, 185×56 → `width:185px`, `height:56px`.
  6. Per-corner 0/12/12/0, 576×48 → `arcsize="25%"` (D9).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_vml_button_paths.py -q -k matcher` → fails (RED, record).
- **SATISFIES**: AC 2

### T4 UPDATE `app/design_sync/component_matcher.py`

- **IMPLEMENT** (spike patch, matcher hunks):
  - `_vml_button_spec`: href `_safe_url`; label `btn.text`; radius = `max(per_corner)` (D9) else `border_radius` else 4.0 (`:905` parity); font family/size/weight with the `_cta_label_typography` fallbacks (`:849-861`); width = `round(btn.width)` else `len(label)·size·0.6 + pl + pr` (expected heuristic; unused on the corpus, S5); height = `round(btn.height)` else `size·1.2 + pt + pb`; no stroke adjustment (D8); width clamped to `max_width`; both ≥ 1.
  - `_column_cta_row(btn, *, column_width: float | None = None)`: wrap the anchor; `fill=_safe_color(btn.fill_color, "") or None` (D3), `text_color=txt_color`, stroke only when `border_css` is set; caller `:1292` passes `column_width=group.width`.
  - `_fills_text_block`: build `anchor` exactly as today, then `cta_parts.append(render_vml_button(spec, anchor))`; stroke only when `border` is set; `max_width=_cw`.
- **GOTCHA**: anchor bytes unchanged (S2 depends on it). `_column_cta_row` has one caller (`:1292`). No `x or N` numeric defaults (`make lint-numeric`, S11): write `int(column_width) if column_width is not None else 600`, and likewise for stroke weight and the width/height fallbacks (`btn.width is not None and btn.width > 0`).
- **VALIDATE (extra)**: `make lint-numeric`.
- **VALIDATE**: T3 green; `uv run pytest app/design_sync/tests/test_cta_fidelity.py -q -k "not Renderer and not Multiple and not centered_row"`.
- **SATISFIES**: AC 2

### T5 ADD template-path tests (RED)

- **IMPLEMENT** in `test_vml_button_paths.py`:
  1. Census, parametrised over every loaded seed whose template has a CTA `data-slot` (42 today; compute the list from `ComponentRenderer()._templates`, never hard-code it; port `.tmpscratch/ce11/census_all.py`), 2 design buttons, CTA slots filled: VML count = filled CTAs, all paired, no "Shop Now", no new Outlook- or browser-view imbalance and an equal browser view vs the same render with the VML step disabled (monkeypatch `_apply_vml_buttons` to identity). `survey-scale` and `video-placeholder-*` must pass (D11).
  2. Chrome kind per S6: `table` for `cta-button`, `button`, `button-filled`, `cta`, `cta-pair`, `hero-2cta`; `a` for `event-card`, `hero-block`, `article-card`, `product-card`.
  3. cta-pair: first VML uses `buttons[0]`, second `buttons[1]` (fill, stroke); no bleed.
  4. `button` slug: the twin holds no `<!--[if` (D6 nested-MSO strip).
  5. Pruned: `_make_match("cta-button")` → no VML (`test_component_renderer.py:843` stays green).
  6. No design button but a filled slot → no VML, `design_sync.vml_button.no_design_button` warning (`caplog`).
  7. Text-block with a `_cta` `color` override → matcher VML `<center>` colour unchanged (E12 guard).
  8. One Figma-tree test that routes to `cta-button` through `match_section` (generality rule).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_vml_button_paths.py -q -k template` → fails (RED).
- **SATISFIES**: AC 3

### T6 UPDATE `app/design_sync/component_renderer.py`

- **IMPLEMENT** (spike patch, renderer hunks):
  - `_strip_seed_vml` applied in `load()`: `<!--[if mso]>\s*<v:roundrect\b.*?</v:roundrect>\s*<!\[endif\]-->\s*<!--[if !mso]><!-->(.*?)<!--<![endif]-->` → `\1`.
  - `_chrome_span` per D6: tag-stack over `<(/?)table\b[^>]*>` before the anchor, innermost open table, `_find_matching_close(html, "table", open.end())`, then the four content checks.
  - `_apply_vml_buttons(html_str, match)` after step 2 (`:686`): anchors outside comments with a non-empty label; `secondary*` → `buttons[1]`, else `buttons[0]`, missing → warning + skip; chrome per D6; strip nested MSO blocks from the chrome; colours per D3 (twin fallbacks: anchor `color:`, `border:Npx solid #hex`); `href` and label from the twin anchor (D11; `html.unescape` the href, the builder re-escapes); `max_width=self._container_width`; replace right-to-left.
  - Import `_safe_color`, `_vml_button_spec` at module top from `component_matcher` (it already imports from there, `:11-16`; the spike's function-local import is not needed).
  - REMOVE `_replace_cta_fillcolor`, `_replace_cta_strokecolor`, `_update_vml_arcsize`, `_CTA_FILLCOLOR_RE`, `_CTA_STROKECOLOR_RE`, `_VML_ARCSIZE_RE` and their calls (`:1495`, `:1500-1502`, `:1505`), the `<center>` regex in `_replace_cta_text_color` (`:1979-1984`) and the roundrect sub in `_strip_empty_cta_chrome` (`:1166-1172`); fix both docstrings (`:1114-1126`, `:1145-1153`).
- **GOTCHA**: runs after `_prune_unfilled_ctas`. `grep -rn "<name>" app/` before deleting each helper.
- **VALIDATE**: T5 green; `uv run python .tmpscratch/ce11/census_balance.py` → only `editorial-5` (pre-existing); mutation: monkeypatch `_chrome_span` with the `--naive` finder → T5.1 red on `article-card`/`hero-block` (run once, record).
- **SATISFIES**: AC 3, AC 5

### T7 UPDATE the 5 non-snapshot tests that fail (S9)

- **IMPLEMENT**:
  - `test_cta_fidelity.py` `test_cta_bg_color_applied`, `test_cta_border_radius_applied`, `test_different_cta_colors_per_section`: pass `section=_make_section(buttons=[_button(fill_color=…, border_radius=…)])`; assert builder output (`fillcolor`, `arcsize` per D7 for 220×48). Keep the twin assertions.
  - `test_render_places_cta_in_centered_row_after_body`: allow the MSO block + `<!--[if !mso]><!-->` between `<td align="center">` and `<a>`.
  - `test_content_checks.py::test_non_mso_wrapped_cta_still_counts`: invert the mutation. Case 5 CTAs are now wrapped, so remove every `!mso` wrapper and MSO block from the real output and assert `output_cta_count(unwrapped) == output_cta_count(html)` (= 8).
- **GOTCHA**: each rewritten test must fail when `_apply_vml_buttons` returns its input unchanged (run once, record).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_content_checks.py -q`.
- **SATISFIES**: AC 5

### T8 UPDATE `app/design_sync/unsubscribe_links.py`

- **IMPLEMENT**: in `_repoint`, after the anchor pass, rewrite `href` on `<v:roundrect\b[^>]*>(.*?)</v:roundrect>` whose stripped text `has_unsubscribe_phrase` and whose href does not start `{{`; add to `count`. Test in `test_unsubscribe_links.py`: `cta-button` match with an "Unsubscribe" design button → `render_section` → `link_unsubscribe_text`: the `<a>` and `<v:roundrect>` hrefs are both `{{unsubscribeUrl}}`; a "Shop now" VML keeps its href.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_unsubscribe_links.py -q`.
- **SATISFIES**: AC 6

### T9 FIX `_strip_mso_blocks` order

- **IMPLEMENT**: unwrap `_NON_MSO_WRAPPER_RE` first, then `_MSO_BLOCK_RE` (`test_converter_data_regression.py:66-70`); unit test with the E9 string (anchor survives).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -q -k "strip or html_structure or layout_divs"`.
- **SATISFIES**: AC 4

### T10 FIX `quality_contracts.py:171`

- **IMPLEMENT**: count `<v:roundrect\b`. Test: 2 input buttons, 1 VML-wrapped anchor → warning fires (today it does not).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_quality_contracts.py -q`.
- **SATISFIES**: AC 4

### T11 ADD corpus invariant

- **IMPLEMENT** in `test_vml_button_paths.py`, parametrised over `discover_cases(data/debug)` via `run_case_conversion` (skips without `structure.json`, like the regression module): port `.tmpscratch/ce11/corpus_check.py`. Assert: VML count = CTA anchors; all paired; MSO valid; no "Shop Now" centre unless a design button says it; Outlook and browser views balanced; no `#0066cc` inside a `<v:roundrect` tag.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_vml_button_paths.py -q -k corpus` → 7 passed; counts 8/2/9/2/2/2/3 (expected, = S1).
- **SATISFIES**: AC 2, 3, 4

### T12 REGEN snapshots (audited)

- **IMPLEMENT**: `uv run python scripts/snapshot-capture.py <case> --output .tmpscratch/ce11/after/<case>.html` × 7; `uv run python .tmpscratch/ce11/corpus_check.py` must print `stripped_equal=True` × 7 (replaces the skill's non-target byte identity, which cannot hold); then copy into `data/debug/<case>/expected.html`.
- **GOTCHA**: never `make snapshot-capture` (`--overwrite`). Any `stripped_equal=False` stops the task: the browser markup changed.
- **VALIDATE**: `make snapshot-test` green.
- **SATISFIES**: AC 7

### T13 GATES

- **IMPLEMENT**: ladder `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder` (13/9/8/10/8/12); A3 after (move `.tmpscratch/fidelity/` aside; `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`), then `cmp .tmpscratch/fidelity/scores.json .tmpscratch/ce11/scores-before.json` → identical (expected, = S4); `make fidelity-gate` (Colima) → pass without re-stamp (derived from identical A3 scores, same renderer family); `make golden-conformance`; `uv run pytest app/components/tests -q`.
- **GOTCHA**: a non-identical score file contradicts S2/S4; investigate before anything else. Any non-target drop beyond jitter stops for the user.
- **VALIDATE**: all green; A3 table in the report.
- **SATISFIES**: AC 7

### T14 LEDGER

- **IMPLEMENT**: close `ce-2-cta-button-vml-twin-unfilled` (`closed_commit: "pending"`, Close step of `.claude/skills/deferred-items/SKILL.md`); refresh moved renderer line numbers in the g3/g5 `code_refs`; add a g3 note (S10).
- **VALIDATE**: `python -c "import json;json.load(open('.agents/deferred-items.json'))"`.
- **SATISFIES**: AC 6

### T15 REPORT + full gate

- **IMPLEMENT**: 600 px side-by-side of c6, c9, c10, reframe against `email-templates/training_HTML/for_converter_engine/{Starbucks,slate,mammut,reframe_2025}/manual_component_build.html` (unchanged from before, per S2/S4). Report `.claude/reports/ce-11-vml-every-button-report.md`: evidence tags, per-case VML counts, mutation results (T6, T7), A3 table, gates, the D4 divergence from the issue's "Files: button templates", the `editorial-5` seed note, owed AC 9. Run `piv-validate` (`make check-full`), then `git diff` again.
- **VALIDATE**: `make check-full` green; `git diff --stat origin/main...HEAD` lists only: plan, report, `.agents/deferred-items.json`, `vml_button.py`, `component_matcher.py`, `component_renderer.py`, `unsubscribe_links.py`, `quality_contracts.py`, `test_vml_button.py`, `test_vml_button_paths.py`, `test_cta_fidelity.py`, `test_content_checks.py`, `test_converter_data_regression.py`, `test_quality_contracts.py`, `test_unsubscribe_links.py`, 7 × `data/debug/*/expected.html`. Restore `app/ai/agents/*/skill-versions.yaml` if `make test` touched them.
- **SATISFIES**: AC 8

---

## TESTING STRATEGY

### Unit Tests
Builder (T1); matcher paths via Figma trees (T3); template census + pairing (T5); unsubscribe (T8); helper order (T9); contract count (T10). RED first for T1, T3, T5.

### Integration Tests
Corpus invariant over the 7 real cases (T11; local only, `structure.json` gitignored). No WebSocket surface.

### Edge Cases

| Edge case | Verified in |
|---|---|
| No design fill → transparent VML | T1.3, T3.2, T11 (c5/c6/c9) |
| No stroke / stroke keeps design box | T1.4, T3.5 |
| Arcsize clamp, min side, Outlook point | T1.5 |
| Per-corner radius | T3.6 |
| FILL button wider than column | T3.4 |
| Two buttons in one template | T5.3 |
| Two stacked buttons in one cell | T3.2 |
| Anchor-only vs table chrome; closed sibling table before the anchor | T5.1, T5.2, T6 mutation |
| Outlook-only spacer inside the twin | T5.4 |
| Pruned CTA; no design button | T5.5, T5.6 |
| `_cta` override cannot repaint VML | T5.7 |
| Unsubscribe button | T8 |
| Escaping | T1.6 |
| Pre-existing seed imbalance (`editorial-5`) | T5.1 compares before/after |
| Bare seed label / second unfilled `cta_url` anchor | T5.1 (`survey-scale`, `video-placeholder-*`, D11) |
| Falsy numeric defaults | `make lint-numeric` (T4) |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
- `uv run ruff format --check app/design_sync` · `uv run ruff check --no-fix app/design_sync`
- `uv run mypy app/` · `uv run pyright app/`

### Level 2: Unit Tests
- `uv run pytest app/design_sync/tests/test_vml_button.py app/design_sync/tests/test_vml_button_paths.py app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_content_checks.py app/design_sync/tests/test_component_renderer.py app/design_sync/tests/test_quality_contracts.py app/design_sync/tests/test_unsubscribe_links.py -q`
- `uv run pytest app/design_sync/tests/ app/components/tests/ -q` (spike: 3441 passed and 12 failed before the T7/T12 fixes, S9)

### Level 3: Converter gates
- `make snapshot-test` · `make converter-data-regression` · `make golden-conformance` · `make fidelity-gate`
- `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` + `cmp` (T13)
- Final: `make check-full` via `piv-validate`

### Level 4: Manual Validation
1. `uv run python .tmpscratch/ce11/corpus_check.py` → 7 lines with `mismatched=[] mso_valid=True stripped_equal=True shop_now_center=0`.
2. `grep -o '<center[^>]*>[^<]*' data/debug/reframe/expected.html` → Register now, Grab your spot, Register for livestream.
3. `grep -c '<v:roundrect' data/debug/*/expected.html` → 8/2/9/2/2/2/3.
4. Open `data/debug/9/expected.html` in a browser: unchanged from before.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: Builder tests (golden parity, fill/stroke, arcsize incl. the measured Outlook point, escaping, namespaces) RED then green (T1–T2).
- [ ] AC 2: Matcher-built CTAs carry a paired VML from design fill, stroke, radius and size, with width clamp (T3–T4, T11).
- [ ] AC 3: Every seed with a CTA `data-slot` (42): each filled CTA gets a paired VML from its own `ButtonElement`, the correct chrome, and no new Outlook-view imbalance; pruned CTAs get none (T5–T6).
- [ ] AC 4: Over every corpus case: each CTA anchor sits in an MSO conditional paired with one `v:roundrect`, counts equal, MSO valid, both views balanced; the regression helper and quality contract count correctly (T9–T11).
- [ ] AC 5: One VML source in the converter: no seed VML at render time, no global VML passes (T6–T7; `grep -n "roundrect" app/design_sync/component_renderer.py` shows only `_strip_seed_vml` and docstrings).
- [ ] AC 6: Unsubscribe repoints VML hrefs; `ce-2-cta-button-vml-twin-unfilled` closed (T8, T14).
- [ ] AC 7: MSO-stripped output equal on all 7; ladder unchanged; A3 `scores.json` identical; fidelity gate passes without re-stamp; held-out check n/a (CE-5 #423 open) (T12–T13).
- [ ] AC 8: `make check-full` green on the head; report written (T15).
- [ ] AC 9 (**owed by #422**): Outlook renders show design radius, fill, stroke and size, including whether the stroke grows the box (D8). No local oracle draws Word VML: `validate_mso_conditionals`/`outlook_analyzer` check markup only, and Chromium drops MSO. The formula risk is bounded by an external classic-Outlook measurement (E7), not by a render here.

---

## COMPLETION CHECKLIST

- [ ] T0–T15 in order, each VALIDATE recorded
- [ ] RED recorded (T1, T3, T5); mutations recorded (T6 naive finder, T7 identity step)
- [ ] Snapshot audit 7 × equal; ladder, A3 `cmp`, fidelity gate, golden conformance green
- [ ] `make check-full` green, `git diff` re-read after lint
- [ ] Ledger updated; report at the named path

---

## RISK REGISTER (each with how this plan closes it)

| # | Risk | Closed by |
|---|---|---|
| R1 | Wrapper changes browser rendering | S2 (stripped equal) + S4 (A3 byte-identical), re-checked in T12/T13 |
| R2 | Chrome finder hides layout tags from Outlook | D6 balanced finder; S7 mutation proves the oracle; T5.1 + T11 balance checks |
| R3 | Nested conditional comments | D6 nested-MSO strip; T5.4 |
| R4 | Global `_cta` passes repaint or delete new VML | T6 removal; T5.7 guard |
| R5 | VML copies the default-blue fallback | D3; T3.2/T11 "no `#0066cc` in a roundrect" |
| R6 | Arcsize formula wrong for Outlook | D7: golden, jsx-email and a measured classic-Outlook render agree; one function if CE-4 disagrees |
| R7 | Stroke grows the button in Word | Not closable here: D8 follows the golden reference; residual owed by #422 (AC 9) |
| R8 | Test churn surprises | S9 lists all 12; T7/T12 handle each |
| R9 | Pairing regex misses formatted output | S8; `\s*` in `PAIR_RE` |
| R10 | Template CTAs without a design button | T5.6: skip + warning; the corpus has none (S1) |
| R11 | Unsubscribe VML keeps the old URL | T8 |
| R12 | Contract/helper blind to wrapped CTAs | T9, T10 |
| R14 | Spike-only defaults trip `make lint-numeric` | S11; T4 GOTCHA + VALIDATE |
| R15 | Seeds outside the matcher's literal list misbehave | S12 census over all 42; T5.1 computes the list |
| R16 | Fidelity gate / golden conformance regress | S13, S14 observed on the spike; re-run in T13 |
| R13 | Outlook visual result | Not closable on this machine: AC 9, owed by #422 |

## OPEN QUESTIONS / ASSUMPTIONS

- None blocking. Q1 (per-corner) → D9; Q2 (template library) → D4; both can be overturned before T1.
- A1 (stacked buttons): Word lays inline VML out like inline text, the same flow as the inline-block anchors. Worst case: side by side where the browser stacks them; folded into AC 9.
- A2: VML width follows the design box, so on template paths it can differ from the twin's padding-driven width (S10, ledger g3). Outlook shows the design size.

## NOTES (open canvas)

- Confidence 10/10 is for one-pass implementation of this plan: every code path, test change and gate in `make check-full` that this diff can move was exercised on the spike (S1–S14). `make check-full` as a whole was not run on the spike (lint/types/frontend/security parts are untouched by this design or depend on the final code). It is not a claim about Outlook's drawn result. It is not a claim about Outlook's drawn result, which AC 9 owns.
- Rejected: static VML twins in each template synced by more regex (the current cta-button approach). It needs size overrides, breaks with two buttons per section and gives CE-19 nothing.
- Rejected: VML colours parsed only from the twin. That would copy `#0066cc` (R5) and lose the design box size.
- `sanitize_web_tags_for_email` stashes `[if …]` blocks untouched (`sanitizers.py:79`); the twin anchor is not sanitised there, same as today's cta-button.

## AMENDMENTS

- 2026-10-04 — Spike-validated revision at the user's request ("increase confidence to 10 and address all risks"). Added S1–S10 and the risk register. Changes from the first draft: no-invented-fill rule (D3); balanced chrome finder + nested-MSO strip (D6), after the naive finder broke `article-card`/`hero-block`; stroke inset (D8); arcsize confirmed against a classic-Outlook measurement (D7); Q1/Q2 resolved to the recommendations (D9, D4); exact T7 test list; A3 identity observed.
- 2026-10-04 — Advisor review: D8 stroke inset dropped (it contradicted the golden reference, jsx-email and its own citation); VML keeps the design box and stroke geometry goes to AC 9. Added D11 (twin href/label) after the all-seed census (S12); lint-numeric, golden-conformance and fidelity-gate run on the spike (S11, S13, S14); census widened from 24 matcher literals to all 42 CTA seeds.
- 2026-10-04 — Implementation divergences (report `.claude/reports/ce-11-vml-every-button-report.md`, Deviations 1–11), superseding the lines named:
  - D3 / T6 label colour on the template path: design `text_color` first, twin colour as fallback (spike rule). Corpus output is byte-identical under either rule; twin-first ignored the design on override-free template renders.
  - T5.3: cta-pair primary VML takes the twin's `border:Npx solid #hex` as stroke when the design has none (D3 as written), not `stroke="f"`.
  - T5.1: no per-slug minimum CTA count; `hero-video` and `video-placeholder` CTA anchors wrap a play image with no label, so 0 VML is correct.
  - T3.3/T3.4/T3.6: column cases build a `ColumnGroup` and call `_build_column_fill_html`, because `analyze_layout` peels two-column mj sections into single sections.
  - T5.6: `capsys`, not `caplog` (structlog writes to stdout).
  - T6 mutation: the naive finder also turns `pricing-table` and `pricing-table-highlight` red. T7 mutation: the two matcher-path tests are checked with an identity `render_vml_button` in the matcher.
  - T15 visual check: byte-compared the A3 rendered PNGs (c6/c9/c10/reframe identical to the `c63874d8` run) instead of eyeballed side-by-sides. Added a VML geometry table: 28/28 match the design box and fill, none wider than its container.
  - E4/D9 corpus impact: 3 reframe buttons carry 0/12/12/0 corners, not 1; all get `arcsize="25%"`.
  - T15 diff list: 21 files; the report stays untracked (`.claude/reports` convention).
