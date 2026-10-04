# Feature: Font fallback stacks by category (CE-7, #425)

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay special attention to the names of existing utils, types and models; import from the right files.

**Base:** `origin/main` = `9a19d74c` (CE-11 #471 merged). Branch: `feat/ce-7-font-fallback-stacks` from `origin/main` (the current checkout `feat/ce-11-vml-every-button` is already squash-merged; do not stack on it).

**Execute in the main checkout `/Users/Berzins/Desktop/email-hub`, not a fresh worktree.** The spike artefacts (`.tmpscratch/ce7/`), the corpus reference PNGs and assets, and `data/debug/*/structure.json` are gitignored and exist only here.

## Decisions

| ID | Decision | Why |
|---|---|---|
| D1 | New module `app/design_sync/font_stacks.py`: `FontCategory` (`StrEnum` SANS/SERIF/MONO), `_CATEGORY_STACK: dict[FontCategory, tuple[str, ...]]`, `font_category(family) -> FontCategory`, `font_stack(family) -> str`. | Issue scope: "one stack builder … new builder module". |
| D2 | Stacks exactly as the issue: SANS `Helvetica, Arial, sans-serif`; SERIF `Georgia, 'Times New Roman', serif`; MONO `'Courier New', Courier, monospace`. Output = the design family first, then the category stack, deduped ignoring case and quotes, joined with `", "`. | Issue scope. Dedupe so `Arial` → `Arial, Helvetica, sans-serif` and `Courier New` → `'Courier New', Courier, monospace`. |
| D3 | Category is inferred from the family **name**. Figma exposes no generic family: `raw_figma.json` text styles carry only `fontFamily`, `fontPostScriptName`, `fontSize`, `fontStyle`, `fontWeight` (observed: `grep -o '"font[A-Za-z]*"' data/debug/10/raw_figma.json`, 29 each), and `structure.json` carries `font_family` only. Tokenise the lower-cased name on spaces/hyphens. Order: MONO (any token **equal to** `mono` or `code`, or **starting with** `courier`, `consol`, `menlo`, `monaco` — prefix so `Consolas` matches; whole-word `mono`/`code` since PR #472 review F1, so `Codec Pro` and `Monotype Corsiva` are not mono) → SANS (token starting with `sans`, `grotesk`, `grotesque`) → SERIF (any token equal to `serif`, `slab`, or a name in a short known-serif list — any token, so `EB Garamond` matches: Georgia, Times, Garamond, Baskerville, Bodoni, Didot, Caslon, Playfair, Merriweather, Lora, Cambria, Palatino, Cormorant, Crimson, Spectral, Domine) → default SANS. | Mono first so `Roboto Mono`/`Noto Sans Mono` stay mono; sans before serif so `Merriweather Sans` is sans. The name list is font data, not fixture data (generality rule holds: keyed on a Figma text property, never a design/node/colour). |
| D4 | Input that is already a list: sanitise each family; if the last is a CSS generic family, return the normalised list unchanged (idempotent); otherwise keep every authored family and append the first family's category stack, deduped. | Providers other than Figma (penpot, html import, tests at `test_component_matcher.py:310`, `test_vml_button.py:161`) already pass lists. Idempotence lets the renderer re-apply the builder as a guard. |
| D5 | Sanitising lives in the builder: strip `'`/`"`, keep only `\w` (Unicode, so `_` stays) plus ` .-` per family (regex `[^\w .-]` removed), collapse spaces; a family emptied by this is dropped; an empty result gives the SANS stack alone. Multi-word names are wrapped in single quotes. Call sites **do not** `html.escape` the builder's output. | `html.escape(quote=True)` turns `'` into `&#x27;`, whose `;` ends the renderer's `font-family:\s*[^;"]+` match (`component_renderer.py:440-447`, `:466-473`) and `_upsert_style_decl` (`:2051`) on a second write, leaving a junk declaration. The builder's charset contains no `"`, `<`, `>`, `&`, so it is attribute-safe without escaping. No template uses single-quoted `style='…'` attributes (observed: `grep -rln "style='" email-templates/components` → none). Exception kept: `vml_button._attr` (`vml_button.py:56-57`) still escapes the spec font into `&#x27;` in the VML `<center>`; safe because it sits inside an `<!--[if mso]>` block that no later regex rewrites, and lxml readers decode it. Families are any `\w` (Unicode letters/digits) plus ` _.-`, so non-Latin names survive; a name is quoted when it has a space or a token starting with a digit (an unquoted `3Dumb` drops the whole declaration). |
| D6 | Canonical write point = the matcher's override emission (`_text_node_overrides` `component_matcher.py:3059-3060`, `_build_token_overrides` `:3233-3239`) emits `font_stack(...)`. The renderer's three appliers call `font_stack(value)` again as a guard (no-op on a stack by D4). | Every bare value in today's output comes from this override path (observed probe, Evidence E2). The renderer guard covers any other `TokenOverride("font-family", …)` producer. |
| D7 | Inline matcher sites and the VML spec route through `font_stack` too: `_column_text_row` `:784-790`, `_cta_label_typography` `:852-856`, `_vml_button_spec` `:1063-1065`, `_spec_label_style` `:1284-1290`, `_card_text_row` `:1590-1595`, `_footer_editorial_row` `:2462-2468`. "No design font" keeps today's per-site default: `Arial` sites call `font_stack("Arial")` (`Arial, Helvetica, sans-serif`); `_cta_label_typography` still emits no `font-family` when `btn.font_family` is falsy. | They pass CE-2 today but carry the wrong category (`Geist Mono,sans-serif`, `Georgia,sans-serif`, E2). |
| D8 | RED proof is a **category invariant**, not CE-2 alone: for every `font-family` value in output, the last family equals the generic of `font_category(first family)`. Shell and template defaults already satisfy it (`Inter, Arial, Helvetica, sans-serif`; `-apple-system, …, sans-serif`). | CE-2's `font_generic` only catches bare values; the inline sites are generic-terminated but wrong (E2). |
| D9 | Out of scope: the shell font (`token_transforms._font_stack` `:42-52`, `converter_service.py:1022-1040`), the YAML `fallback_map` (`data/email_client_fonts.yaml`, shared with `app/templates/upload/font_optimizer.py`), template-default stacks, the MJML path, the tree-bridge path (flag off). | Not in the issue's Files list; the shell already passes CE-2 and D8. Q1 below. |

## Evidence

### Planning probes (observed 2026-10-04 on `9a19d74c` tree)

| # | Observation |
|---|---|
| E1 | `uv run python -m app.design_sync.tests.content_checks --empty-allowlist`: `font_generic` FAIL on all six cases — 5 `Courier New\|Helvetica`, 6 `Roboto`, 7 `Noto Sans`, 8 `Arial`, 9 `Arial`, 10 `Geist Mono\|Helvetica`; matches `data/debug/content_check_allowlist.yaml` (6 entries owned by `#425`). Mammut = case 10, Starbucks = case 6 (`data/debug/manifest.yaml`). |
| E2 | Probe (`.tmpscratch/ce7/bare.py`, regex over converted HTML): every bare value sits on a `<td>` reached by the override path — `data-slot="heading"/"body"/"subtext"/"description"` (`_replace_heading_font`/`_replace_body_font`) or slot-less `<td data-node-id>` (`_apply_text_node_style`). Generic-terminated but wrong category: c10 `Geist Mono,sans-serif` × 8 (CTA labels and columns). Per-case bare counts: c5 7, c6 3, c7 6, c8 10, c9 3, c10 11. |
| E3 | Corpus families from `structure.json`: c5 Courier New, Helvetica; c6 Roboto; c7 Noto Sans; c8 Arial; c9 Arial, Inter; c10 Geist Mono, Helvetica; reframe Helvetica. Only MONO and SANS occur; SERIF is exercised only by unit tests (a family the corpus lacks, as the issue asks). |
| E4 | Local fonts (`fc-list`): Geist Mono 0 matches, Roboto 0 matches, Noto Sans installed. So locally bare `Geist Mono`/`Roboto` cells fall to the browser default serif today; after the fix they fall to Courier New / Helvetica. The mammut side-by-side is valid locally (Geist Mono absent). |
| E5 | Superseded by S1 (the grep missed the CE-2 reader tests). |

### Spike (observed 2026-10-04, throwaway over `9a19d74c`, reverted; tree clean after)

Builder roughly per D1–D5 in `app/design_sync/font_stacks.py` plus the D6/D7 call-site swaps (5 inline sites, VML spec, 3 override emissions, 3 renderer appliers). Scripts: `.tmpscratch/ce7/bare.py`, `.tmpscratch/ce7/mask_audit.py`.

| # | Observation |
|---|---|
| S1 | `uv run pytest app/design_sync/tests/ app/components/tests/ -q`: **25 failed, 3526 passed, 120 skipped, 7 xfailed**. The 25: 7 × `test_snapshot_matches[5,6,7,8,9,10,reframe]`; `test_content_checks.py` `test_content_checks_hold_allowlist`, `test_quoted_font_is_still_bare`, `test_generic_fallback_with_important_is_accepted`, `test_bare_font_moved_into_style_block_is_read`, `…_into_mso_block_is_read`, `…_into_face_attribute_is_read` (all mutate case 10's bare `font-family:Geist Mono;`, which no longer exists); `test_cta_fidelity.py` `test_c7_square_pills_byte_identical`, `test_c5_rounded_city_pill_byte_identical`; `test_column_text_styling.py` `test_column_row_emits_all_design_properties`, `test_column_row_heading_fallbacks`, `test_column_row_escapes_font_family`, `test_build_column_fill_html_renders_design`, `test_cta_label_typography_emits_design`, `test_cta_label_typography_escapes_font_family`, `test_build_column_fill_html_styles_cta_label`; `test_card_composite.py::test_card_font_family_escaped_with_fallback`; `test_component_matcher.py::TestPerNodeTypography::test_per_node_overrides_carry_each_nodes_typography`; `test_component_renderer.py::TestTokenOverrideExpansion::test_body_font_override_description_slot`. |
| S2 | `.tmpscratch/ce7/mask_audit.py` on the spike, 7 cases: `masked_equal=True` × 7 (mask `font-family:[^;"]+` and `face="…"` after `html.unescape`, whitespace-normalised, vs committed `expected.html`); category violations 0 × 7. |
| S3 | Same audit on base (call sites reverted, builder kept for the classifier): category violations c5 7, c6 3, c7 6, c8 10, c9 3, c10 21 (incl. `Geist Mono,sans-serif`), reframe 6 — the invariant is RED on all 7 cases. |
| S4 | `python -m app.design_sync.tests.content_checks --empty-allowlist` on the spike: `font_generic` pass × 6. |
| S5 | Re-run with the final `_clean` (keeps `_`; the first spike mapped `_` to a space): same 25 failures (`.tmpscratch/ce7/pytest-spike2.txt`), masked audit and category invariant identical to S2. Output captured to `.tmpscratch/ce7/spike-after/<case>.html` × 7 for T10's `cmp`. No corpus family contains `_` (E3), so the R1/R4 runs from the first spike apply unchanged (derived). |

### Risk closure (observed 2026-10-04, second spike over `9a19d74c`; reference copy kept at `.tmpscratch/ce7/spike.patch` + `.tmpscratch/ce7/spike_font_stacks.py`)

| Risk | Probe | Result | Closed by |
|---|---|---|---|
| R1 fidelity gate | `make fidelity-gate` on the spike (`.tmpscratch/ce7/gate-spike.log`, Playwright 1.63.0 image) | **1 section fails**: c7 `2833:1942` 0.8611 → 0.8552 (−0.0059 > 0.005). Moved in margin: c7 `2833:1870` −0.0024, `2833:1882` −0.0034, `2833:1898` −0.0011; c6 `2833:1430` +0.0004; c10 `2833:1141` −0.0007, `2833:1176` +0.0001, `2833:1197` +0.0003, `2833:1227` −0.0004. Every other section of 5, 6, 8, 9, 10, reframe +0.0000. | Cause, observed with `.tmpscratch/ce7/probe_c7.py` in the pinned image: the section is one 30px Noto Sans heading ("Expect lots of treats this Halloween!"); the image has no Noto Sans, so base renders it in **Liberation Serif** (bare `"Noto Sans"`, browser default) and the fix in **Liberation Sans**. Crops: `.tmpscratch/ce7/c7-1942-{before,after,reference}.png`; the design reference is a sans (Noto Sans) and the after crop matches its shape, the before crop does not. The scorer ranks the serif render higher; the mechanism inside the scorer is not isolated (expected: per-pixel overlap, not face shape). By the jitter rule this is a target case, and the composites rank the after render closer. Ratification requested at planning (Q3); T12 re-stamps cases 6, 7, 10 with these deltas as the reason. |
| R2 escape hazard | `.tmpscratch/ce7/double_write.py` (pipeline cells, second `_text_b1` write) and `double_write_escaped.py` (same, with `html.escape` re-applied to the stack) | Spike: first write `font-family:'Courier New', Courier, monospace;`, second `font-family:'Geist Mono', 'Courier New', Courier, monospace;` — one clean declaration. Escaped variant: first write already mangled (`&#x27;x27Courier Newx27&#x27;`, because the renderer guard re-cleans an escaped value), second leaves a junk tail `…monospace;x27Courier Newx27&#x27;, Courier, monospace;`. | D5 (no escaping of builder output) + the T3 double-write test. New rule from the probe: a `TokenOverride` font value is always the raw design family or a builder stack, never pre-escaped (T4 GOTCHA). |
| R3 mammut evidence | `.tmpscratch/ce7/used_font.py` (CDP `CSS.getPlatformFontsForNode`, local Chromium, 600 px; Geist Mono not installed locally, E4) | "BUILD YOUR LAYERS" computed `"Geist Mono", "Courier New", Courier, monospace`, rendered face **Courier New** (mono) after the fix; screenshots `.tmpscratch/ce7/c10-after-{cta,full}.png`. | T13 repeats it on the branch and records the base face next to it. |
| R4 A3 (local, macOS fonts) | `.tmpscratch/ce7/a3_run.sh` → `scores-{before,after}.json`, composites `fidelity-{before,after}/` | full_image before→after: c5 0.8660→0.8672, c6 0.8131→0.8117, c7 0.8403→0.8403, c8 0.8632→0.8632, c9 0.8125→0.8125, c10 0.7361→0.7368, reframe 0.8542→0.8542. Section moves: c5 idx 3 +0.002, 7 +0.005, **8 −0.007**, 9 +0.005, 10 +0.001, 11–13 +0.007, 14 +0.008; c6 idx **1 −0.006**; c10 idx 2/4/5/8/9 +0.001, 6 +0.002, 7 −0.002, **12 +0.015**. c7, c8, c9, reframe flat (c7 flat here because Noto Sans is installed locally, E4). | Mechanisms observed with `.tmpscratch/ce7/boxes.py` (box and computed font per text leaf): **c5** only "Discover →" changed, height 43→42 px (the render is 1909→1908 px). Helvetica has no "→" glyph; the arrow's fallback moves from the system sans to Arial and the line is 1 px shorter. Everything below shifts 1 px, which is the known bidirectional scorer artifact (memory `reference_a3_scorer_section_instability`). **c6** idx 1: same height, the three bare-Roboto cells change from serif to Helvetica (diff bbox y 545–1956), the intended change. **c10**: "SHOP THE COLLECTION" and "DISCOVER EIGER EXTREME 6.0" now render mono (sans before), heights 43→42. Ratification for c5 idx 8 and c6 idx 1 is requested with R1 (Q3). |

- Ladder: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder` on the spike → 7 passed (observed).

Nothing in this plan's success path is left unmeasured: every gate, test count and score delta above was run on the spike. Execution re-runs them on the branch and compares against these figures.

## Feature Description

Every font the converter writes gets a full fallback stack chosen by the design font's category, so a client without the design font falls back to the right kind of face (mono stays mono, serif stays serif) instead of the browser default serif.

## User Story

As a marketer converting a Figma email, I want text in a font the recipient lacks to fall back to a similar face, so the email keeps its typographic character in every client.

## Problem Statement

The override path writes the bare design family (`font-family:Geist Mono`), so clients without it render Times. The inline paths append `,sans-serif` whatever the font, so a mono or serif design font falls back to sans (R5).

## Solution Statement

One builder (`font_stacks.py`) classifies the family by name and returns `family, <category stack>`. The matcher's override emission and its six inline sites call it; the renderer re-applies it idempotently and stops HTML-escaping the value. CE-2's six `font_generic` allow-list entries are deleted, and a category invariant over all seven cases guards the result.

## Out of Scope / Non-Goals

- Not included: shell/body font from tokens (`token_transforms._font_stack`, `converter_service.py:1022-1040`) — owned by `ce-3-file-wide-tokens-body-font` (Q1).
- Not included: per-role `data-role` font targets and the template CTA twin's font (CE-13 #431); per-character style runs (CE-14 #432).
- Not changing: the YAML `fallback_map` or `font_optimizer.py`; template-default stacks in `email-templates/components/`; MJML path; tree-bridge path; web-font `<link>`/`@font-face` loading.
- Not included: reading Figma font metadata beyond the family name (none exists, D3).

## Feature Metadata

**Feature Type**: Bug Fix · **Estimated Complexity**: Medium · **Primary Systems Affected**: `app/design_sync` matcher + renderer, corpus baselines, fidelity baseline · **Dependencies**: none new.

## Related Work

**Implements**: #425 (CE-7) · **Epic**: #439 (converter fidelity), conventions table inherited.

**Back-references**: `.agents/plans/ce-2-content-checks.md` (allow-list, `font_family_values`); `.agents/plans/ce-11-vml-every-button.md` (plan shape, audited regen recipe, A3/gate steps); `.agents/plans/ce-10-button-icon-not-content-image.md` (minimal-tree test shape).

**Forward-references**: CE-13 (#431) routes role-keyed font writes through this builder.

## Deferred Items Touching This Plan

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `ce-3-file-wide-tokens-body-font` | `token_transforms.py` font code_ref; font topic | avoid | Shell font is D9 out of scope; the shell already ends generic. Q1. |
| `phase-53g-g3-template-cta-padding-uncovered` | `component_renderer.py`, `component_matcher.py`, `vml_button.py` | carry forward | The template CTA HTML twin keeps the template's own font (not a converter write); its VML spec font does route through the builder (D7). CE-13 `_cta` font target owns the twin. |
| `phase-53g-g5-pill-white-on-light-latent` | `component_matcher.py`, `vml_button.py` | avoid | Colour, not font. |
| `phase-53g6-card-tree-path-text-only`, `phase-53g-t1-tree-path-social-label-default`, `ce-9-tree-path-corpus-compile-fallback` | matcher/renderer | avoid | Tree path, flag off (D9). |
| `phase-53g-band-item-spacing-defaults-vs-wrapper-padding`, `ce-9-peel-row-fixed-width-wrap`, `ce-9-c6-mobile-page-overflow` | `component_renderer.py` | avoid | Spacing/width, not font. |
| `ce-10-cta-icon-not-rendered`, `ce-10-unnamed-button-icon-not-exported` | `component_matcher.py` | avoid | Icons, not font. |

(Ledger grep: `python3` scan of `.agents/deferred-items.json` for `status: deferred` entries matching the touched files or font/typography, observed 2026-10-04. No entry has `phase` `ce-7`.)

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/component_matcher.py:766-790` (`_column_text_row`), `:841-860` (`_cta_label_typography`), `:1041-1090` (`_vml_button_spec`), `:1281-1290` (`_spec_label_style`), `:1585-1595` (`_card_text_row`), `:2451-2468` (`_footer_editorial_row`), `:3049-3060` (`_text_node_overrides`), `:3231-3239` (`_build_token_overrides` font block), `:78-84` (`TokenOverride`).
- `app/design_sync/component_renderer.py:440-447`, `:466-473` (font regexes), `:1592-1600` (dispatch), `:1666-1678` (`_replace_heading_font`, `_replace_body_font`), `:2044-2079` (`_upsert_style_decl`, `_apply_text_node_style`).
- `app/design_sync/tests/content_checks.py:142-224` (`GENERIC_FAMILIES`, `font_family_values`, `is_bare_font`, `output_bare_fonts`), `:301` (`convert_case`).
- `data/debug/content_check_allowlist.yaml` (six `font_generic` entries, owner `#425`).
- `app/design_sync/token_transforms.py:42-52` (`_font_stack`, the out-of-scope shell builder; do not touch).
- `app/design_sync/tests/test_converter_service.py:47-97` (`_make_tokens`, `_make_structure`, `_make_document`; minimal DesignNode tree → `DesignConverterService().convert_document(..., output_format="html")`).
- `app/design_sync/tests/test_column_text_styling.py:44-60` (`_styled_text`), `:198-246` (`_styled_button`, CTA typography tests).
- `.claude/skills/converter-fix/SKILL.md` and `references/baselines-and-gates.md` (regen-and-audit), `references/a3-scoring.md`.
- `docs/fidelity-gate.md` §Re-stamping (`:93-113`), margin `:29`.

### New Files to Create

- `app/design_sync/font_stacks.py` — the builder (D1–D5).
- `app/design_sync/tests/test_font_stacks.py` — builder unit tests, minimal-tree pipeline test, corpus category invariant.
- `.claude/reports/ce-7-font-fallback-stacks-report.md` — report (gitignored by default; reports are untracked).

### Relevant Documentation

- [CSS Fonts 4 §font-family](https://www.w3.org/TR/css-fonts-4/#font-family-prop) — unquoted family names are sequences of identifiers; quote names with spaces as good practice; generic families must not be quoted.
- [MDN font-family](https://developer.mozilla.org/en-US/docs/Web/CSS/font-family#syntax) — "always include at least one generic family".

### Patterns to Follow

- Enum-keyed mapping with a completeness test: `set(_CATEGORY_STACK) == set(FontCategory)` (planning skill §Figures and enum-shaped sets).
- Module shape: small pure module with `from __future__ import annotations`, module docstring, no logger needed (mirror `app/design_sync/vml_button.py:1-57`).
- Corpus tests skip when fixtures are absent: `content_checks.convert_case` returns `None` → `pytest.skip` (mirror `test_content_checks.py:53-57`).
- No `x or N` numeric defaults (`make lint-numeric`); not expected to arise here.

---

## IMPLEMENTATION PLAN

Phase 1 (builder, T1–T2) → Phase 2 (call sites, T3–T6) → Phase 3 (fallout tests, allow-list, corpus invariant, T7–T9) → Phase 4 (baselines and gates, T10–T13) → Phase 5 (ledger, report, full gate, T14–T15). Strictly sequential.

---

## STEP-BY-STEP TASKS

### T0 CAPTURE baselines

- **IMPLEMENT**: `git rev-parse origin/main` (record). Capture before-snapshots for all 7 cases: `uv run python scripts/snapshot-capture.py <case> --output .tmpscratch/ce7/before/<case>.html` for `5 6 7 8 9 10 reframe`. A3 before: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`, copy `.tmpscratch/fidelity/scores.json` → `.tmpscratch/ce7/scores-before.json` (needs the gitignored reference PNGs per `references/a3-scoring.md`; fewer than the full rows is a short run, say so).
- **VALIDATE**: 7 files in `.tmpscratch/ce7/before/`; `scores-before.json` exists.
- **SATISFIES**: AC 6, AC 7.

### T1 CREATE `app/design_sync/tests/test_font_stacks.py` — builder unit tests (RED)

- **IMPLEMENT**: tests, all importing from `app.design_sync.font_stacks`:
  - `test_category_stack_covers_enum`: `set(_CATEGORY_STACK) == set(FontCategory)`.
  - `font_category` parametrised: MONO — `Geist Mono`, `Courier New`, `Roboto Mono`, `Noto Sans Mono`, `Fira Code`, `JetBrains Mono`; SANS — `Helvetica`, `Arial`, `Roboto`, `Noto Sans`, `Inter`, `Nunito`, `Merriweather Sans`, `Space Grotesk`; SERIF — `Georgia`, `Times New Roman`, `Noto Serif`, `Lora`, `Playfair Display`, `Roboto Slab`, `EB Garamond`; unknown (`Brandname Display`) → SANS.
  - `font_stack` exact strings: `Geist Mono` → `'Geist Mono', 'Courier New', Courier, monospace`; `Courier New` → `'Courier New', Courier, monospace`; `Arial` → `Arial, Helvetica, sans-serif`; `Helvetica` → `Helvetica, Arial, sans-serif`; `Lora` → `Lora, Georgia, 'Times New Roman', serif`; `JetBrains Mono` (not in corpus) → `'JetBrains Mono', 'Courier New', Courier, monospace`.
  - Lists: `Georgia, serif` → `Georgia, serif` (unchanged); `'Helvetica Neue', Arial` → `'Helvetica Neue', Arial, Helvetica, sans-serif`; idempotence `font_stack(font_stack(x)) == font_stack(x)` over every name above.
  - Sanitising: `Arial" onmouseover="x` → result contains no `"`, `<`, `>`, `&`, `=`, `;`, `\`; `"Geist Mono"` and `'Geist Mono'` give the same result as `Geist Mono`; `""`/`"  "` → `Helvetica, Arial, sans-serif`; `3Dumb Sans` is quoted; a non-Latin name (`Noto Sans JP` in kana, e.g. `ヒラギノ角ゴ`) survives and is quoted only if it has a space; `Consolas` → MONO.
- **GOTCHA**: case-insensitive dedupe must compare unquoted names (`'Courier New'` vs `Courier New`).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_font_stacks.py -q` → collection error on the import (RED; record the output). Note: an import error is acceptable RED for a new module only; T3/T5 below are assertion-level RED.
- **SATISFIES**: AC 1.

### T2 CREATE `app/design_sync/font_stacks.py`

- **IMPLEMENT**: D1–D5. Public: `FontCategory`, `font_category(family: str) -> FontCategory`, `font_stack(family: str) -> str`. Private: `_CATEGORY_STACK`, `_GENERIC` (`sans-serif`, `serif`, `monospace`, plus `cursive`, `fantasy`, `system-ui`, `ui-serif`, `ui-sans-serif`, `ui-monospace`, `ui-rounded` — same set as `content_checks.GENERIC_FAMILIES`), `_split(value) -> list[str]` (split on `,`, strip quotes, sanitise per D5), `_render(name) -> str` (generic names lower-cased and never quoted; single-quote when the name has a space or a digit-leading token). Classifier per D3 (any token; whole-word `mono`/`code`, prefix match for the mono brand stems and the SANS keywords). The spike's ~45-line version passed S2/S4; it is a reference, not the deliverable (no docstrings, no tests).
- **IMPORTS**: `re`, `enum.StrEnum`.
- **GOTCHA**: generic family names must never be quoted (`'serif'` is a family called "serif"). Keep the module free of `html` escaping (D5).
- **VALIDATE**: T1 green; `uv run mypy app/design_sync/font_stacks.py && uv run pyright app/design_sync/font_stacks.py`; `uv run ruff check --no-fix app/design_sync/font_stacks.py app/design_sync/tests/test_font_stacks.py`.
- **SATISFIES**: AC 1.

### T3 ADD pipeline tests to `test_font_stacks.py` — matcher sites (RED)

- **IMPLEMENT**:
  - `test_minimal_tree_every_font_matches_category`: minimal Figma tree mirroring `test_converter_service.py:62-93` — a lead FRAME and a tail FRAME (Roboto body each; the first frame classifies as `email-header` and drops its text, observed at execution) around one FRAME section with a heading TEXT (`font_family="JetBrains Mono"`, `font_size=28`), a body TEXT (`font_family="Lora"`), and a second section with body TEXT `font_family="Roboto"`; tokens from `_make_tokens()` pattern. Convert with `DesignConverterService().convert_document(EmailDesignDocument.from_legacy(...), output_format="html")`. Assert: for every value from `content_checks.font_family_values(html)`, last family (unquoted, lower) == `font_category(first).generic`; and at least one value starts with `'JetBrains Mono'` and ends `monospace`, one starts `Lora` and ends `serif`.
  - Unit RED per inline site (no full pipeline): `_column_text_row(_styled_text(font_family="Georgia"), is_heading=True)` contains `font-family:Georgia, 'Times New Roman', serif`; `_cta_label_typography(_styled_button(font_family="Geist Mono"))` contains `font-family:'Geist Mono', 'Courier New', Courier, monospace`; `_vml_button_spec(...)` `.font_family` same mono stack; `_card_text_row`, `_spec_label_style`, `_footer_editorial_row` with `font_family="Lora"` end `serif`; `_text_node_overrides` and `_build_token_overrides` emit `TokenOverride("font-family", …, "'Geist Mono', 'Courier New', Courier, monospace")` for a mono TextBlock.
  - Renderer guard and double-write: build the cells through the real pipeline, not hand-written HTML — `match_section` on a CONTENT section with a heading and two body `TextBlock`s (`font_family="Courier New"` and `"Geist Mono"`, two bodies so the matcher stamps per-node `<td data-node-id>` anchors via `_per_node_body_html`), then `ComponentRenderer().render_section(match)`. Then re-apply `renderer._apply_token_overrides(html, [TokenOverride("font-family", "_text_<courier node id>", "Geist Mono")])` — the second write targets the anchor that already holds the Courier New stack, so a replace-over-stack happens. Assert that anchor's style carries exactly one `font-family:` declaration and it **equals** `'Geist Mono', 'Courier New', Courier, monospace` (RED on base, where the value is bare `Geist Mono`), with no `&#x27;` and no orphan fragment (`Courier New'`) anywhere in the cell. Confirm `text-block.html` has no `data-node-id` of its own (observed: grep finds none), so the anchors come from the matcher. GOTCHA: anchors need `column_layout == ColumnLayout.SINGLE` and ≥ 2 body texts (`_per_node_body_texts`, `component_matcher.py:1825-1839`); assert the rendered HTML contains `data-node-id=` before the font assertions so the test cannot pass vacuously.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_font_stacks.py -q` → assertion failures (RED; record which; executed as the whole file: 10 failed, 63 passed). Expected failing: every site test, the minimal-tree test, the double-write test.
- **SATISFIES**: AC 2, AC 3.

### T4 UPDATE `app/design_sync/component_matcher.py`

- **IMPLEMENT**: `from app.design_sync.font_stacks import font_stack`. Replace each `html.escape(family) + ",sans-serif"` block (D7 lines) with `font_stack(text.font_family)` / `font_stack(btn.font_family)`; the `else` defaults become `font_stack("Arial")` where the site had `Arial,sans-serif` (keep the `_cta_label_typography` no-font branch emitting nothing). `_vml_button_spec`: `family = font_stack(btn.font_family or "Arial")`. Override emission: `TokenOverride("font-family", target, font_stack(text.font_family))` at `:3060`, `:3234`, `:3239`. Update the docstrings at `:774-777`, `:846-849`, `:1588` that describe "web-safe fallback appended / escaped".
- **GOTCHA**: a `TokenOverride` font value is the raw family or a builder stack, never pre-escaped: the R2 probe showed an escaped value is mangled by the renderer guard (`&#x27;x27Courier Newx27&#x27;`). Mechanical reference for every swap: `.tmpscratch/ce7/spike.patch` (164 lines, observed green on S1–S4 after the test updates). `html` is still used elsewhere in the module; remove the import only if ruff F401 says it is unused. Do not touch `:2377-2381` (hardcoded seed CSS strings already `Arial, sans-serif`, not design writes).
- **VALIDATE**: matcher tests in T3 green; `uv run pytest app/design_sync/tests/test_component_matcher.py app/design_sync/tests/test_cta_fidelity.py -q -k "not C7 and not C5"`.
- **SATISFIES**: AC 2.

### T5 UPDATE `app/design_sync/component_renderer.py`

- **IMPLEMENT**: `_replace_heading_font` / `_replace_body_font`: `safe = font_stack(font)` instead of `html.escape(font, quote=True)`. `_apply_text_node_style`: when `prop == "font-family"`, `safe_val = font_stack(value)`; other props keep `html.escape`. Leave `_apply_image_corner_radius` unchanged (the spike patch touched it, but it only receives `border-*-radius` props).
- **GOTCHA**: the replacement string goes into `re.sub` as a template — the builder's charset has no `\` or `\g`, so no escaping needed; assert this in the T1 sanitiser test (no backslash survives).
- **VALIDATE**: T3 renderer tests green; `uv run pytest app/design_sync/tests/test_component_renderer.py -q`.
- **SATISFIES**: AC 2, AC 3.

### T6 MUTATION check (record both halves)

- **IMPLEMENT**: (a) revert T5's `_apply_text_node_style` change only → run the double-write test and the corpus invariant (T9) for case 10: both must go red. (b) revert T4's `:3060` change only (renderer guard still on) → the `_text_node_overrides` emission test goes red **and** the minimal-tree test stays green (the guard covers it). Record both results; restore.
- **VALIDATE**: commands as in T3 with `-k "double_write or minimal_tree or text_node_overrides"`.
- **SATISFIES**: AC 3.

### T7 UPDATE `data/debug/content_check_allowlist.yaml`

- **IMPLEMENT**: delete the six `font_generic` entries (owner `#425`). Keep the `default_blue` entries.
- **VALIDATE**: `uv run python -m app.design_sync.tests.content_checks` → no problems (S4); `uv run pytest app/design_sync/tests/test_content_checks.py -q -k allowlist`.
- **SATISFIES**: AC 4.

### T8 UPDATE the 16 non-snapshot, non-pill tests that fail (S1)

- **IMPLEMENT**:
  - `test_column_text_styling.py` (7): `:75,172` → `font-family:Georgia, 'Times New Roman', serif`; `:105` → `font-family:Arial, Helvetica, sans-serif`; `:218,246` → the Geist Mono mono stack; `test_column_row_escapes_font_family` and `test_cta_label_typography_escapes_font_family` → assert no `"`, no `onmouseover=` and no `&quot;` dependency (the builder strips, it no longer escapes); read each failing assertion before editing.
  - `test_card_composite.py::test_card_font_family_escaped_with_fallback` → `font-family:'Noto Sans', Helvetica, Arial, sans-serif` and the strip-not-escape assertion.
  - `test_component_matcher.py::TestPerNodeTypography::test_per_node_overrides_carry_each_nodes_typography` and `test_component_renderer.py::TestTokenOverrideExpansion::test_body_font_override_description_slot` → expected values become stacks.
  - `test_content_checks.py` reader tests (5: `test_quoted_font_is_still_bare`, `test_generic_fallback_with_important_is_accepted`, three `test_bare_font_moved_into_*`): they mutate case 10's bare `font-family:Geist Mono;`, which no longer exists. Keep the "mutate real converted output" rule: a helper (`_html_with_bare_geist`) first rewrites the first real case-10 stack (`font-family:'Geist Mono', 'Courier New', Courier, monospace;`) **outside any conditional block** back to `_GEIST` (`font-family:Geist Mono;`), then the existing mutations run unchanged. (The first occurrence sits in a CE-11 `<!--[if !mso]><!-->` twin, which the reader counts twice.) The bare-count helper at `:213` reads the rebuilt value.
- **GOTCHA**: after this task the only expected failures are the 7 snapshot tests and the 2 pill tests (fixed in T10). Anything else failing is not in S1: stop and trace it.
- **VALIDATE**: `uv run pytest app/design_sync/tests/ app/components/tests/ -q --deselect app/design_sync/tests/test_snapshot_regression.py -k "not byte_identical"` → 0 failed.
- **SATISFIES**: AC 2.

### T9 ADD corpus category invariant to `test_font_stacks.py`

- **IMPLEMENT**: `test_corpus_fonts_match_category[case]` for `5 6 7 8 9 10 reframe`: `html = content_checks.converted_html(case)` (skip on `None`); for every `font_family_values(html)` value, last family == generic of `font_category(first)`; and `"font-family:&#x27;" not in strip_mso(html)` (lxml decodes entities, so the invariant alone cannot see a re-escaped value; this line is what makes T6(a) go red on the corpus, c5 and c10). RED on base: `git stash push -- app/design_sync/component_matcher.py app/design_sync/component_renderer.py` (keep `font_stacks.py`, which the test imports), run, record, `git stash pop`.
- **GOTCHA**: `converted_html` is cached per process; run the RED check in a fresh process.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_font_stacks.py -q -k corpus` → 7 passed on the branch; 7 failed on base with violation counts 7/3/6/10/3/21/6 for 5/6/7/8/9/10/reframe (expected = S3).
- **SATISFIES**: AC 2 (invariant over every case).

### T10 REGEN snapshots (masked audit)

- **IMPLEMENT**: capture after-snapshots to `.tmpscratch/ce7/after/<case>.html` for all 7 (`scripts/snapshot-capture.py <case> --output …`). Masked audit script `.tmpscratch/ce7/mask_audit.py` (exists; written on the spike): `html.unescape` both sides first (the VML `<center>` font carries `&#x27;`, whose `;` would end the mask early), then replace every `font-family:[^;"]+` and `face="[^"]*"` with a placeholder, whitespace-normalise, compare; print `case masked_equal=<bool> font_values_changed=<n>`. All 7 must print `masked_equal=True` (expected = S2). **Then `cmp .tmpscratch/ce7/after/<case>.html .tmpscratch/ce7/spike-after/<case>.html` for all 7** (spike output, captured with the final `_clean`). Identical bytes mean every spike figure (S1–S4, R1–R4) carries over unchanged, because the gate is deterministic on one host (same-host spread 0.0000, `docs/fidelity-gate.md:32`). If any file differs, list the differing values in the report and expect T12 figures to move by those values only. Then copy after → `data/debug/<case>/expected.html`. Then update `test_cta_fidelity.py:985-997` `_C7_ART_PRINTS`/`_C5_MELBOURNE` font values to the stacks now in those files (font value only; the rest of the byte string must still match).
- **GOTCHA**: never `make snapshot-capture` (`--overwrite`). A whitespace-only c8 churn is the known hook artefact (skill §4). Any `masked_equal=False` stops the task.
- **VALIDATE**: `make snapshot-test` green; `uv run pytest app/design_sync/tests/test_cta_fidelity.py -q` (pill constants updated above).
- **SATISFIES**: AC 5.

### T11 LADDER

- **VALIDATE**: `git diff origin/main -- data/debug/ladder_snapshot.json` empty; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -q -k ladder` green (13/9/8/10/8/12 per the epic, reported as "unchanged from base").
- **SATISFIES**: AC 6.

### T12 A3 + FIDELITY GATE (planned stop point)

- **IMPLEMENT**: A3 after, same command as T0; table before/after for all rows. `make fidelity-gate` (Colima). Expected = the spike's figures (R1 and R4 rows): gate fails on c7 `2833:1942` only (−0.0059); in-margin moves on c6, c7, c10; A3 moves on c5, c6, c10.
- **DECISION RULE (fixed at planning so execution never improvises)**:
  - T10 `cmp` identical on all 7 and Q3 ratified → the gate and A3 must reproduce R1/R4 exactly; re-stamp as below. No further stop.
  - T10 `cmp` not identical → the differing values bound the change; a section the spike did not move, or a delta differing by more than 0.001, stops for the user with the table and crops.
  - Q3 not ratified → stop before the re-stamp.
- **IMPLEMENT (re-stamp)**: `make fidelity-restamp REASON="CE-7 #425 font fallback stacks: c7 2833:1942 heading renders Liberation Sans instead of Liberation Serif (Noto Sans absent from image; reference is sans), -0.0059 ratified; c6/c7/c10 in-margin moves from Roboto/Noto Sans/Geist Mono fallbacks" CASES="6 7 10"`. Append the stamp note to `docs/fidelity-gate.md` §Re-stamping with the per-section deltas of the branch run (observed).
- **VALIDATE**: `make fidelity-gate` green after the stamp; `git diff data/debug/fidelity_baseline.json` touches cases 6, 7 and 10 only.
- **SATISFIES**: AC 7.

### T13 SIDE-BY-SIDES

- **IMPLEMENT**: 600 px renders (local Playwright, where Geist Mono and Roboto are absent per E4) of c10 and c6 before/after next to `email-templates/training_HTML/for_converter_engine/{mammut,Starbucks}/manual_component_build.html`. Mammut "BUILD YOUR LAYERS" must render in a monospace face: measure it with `PYTHONPATH=. uv run python .tmpscratch/ce7/mammut_cta.py after` (writes `c10-after.html` + screenshots) then `.tmpscratch/ce7/used_font.py after "BUILD YOUR LAYERS"` (CDP rendered face; spike result `['Courier New']`, R3). Repeat with `before` on the T0 capture (`.tmpscratch/ce7/before/10.html`, byte-equal to base `expected.html`). Save PNGs under `.tmpscratch/ce7/` and name them in the report.
- **VALIDATE**: rendered face for "BUILD YOUR LAYERS" is a monospace family (Courier New locally); visual check recorded in the report; wrong-if (derived, issue) — mammut CTAs still serif → stop, it is a missing hook (CE-13 plumbing), log it.
- **SATISFIES**: AC 8.

### T14 LEDGER

- **IMPLEMENT**: no entry closes (none owned by CE-7). If T12/T13 finds a font write the builder cannot reach (e.g. template CTA twin font), add a `ce-7-*` entry via the `deferred-items` skill. Append a dated note to `phase-53g-g3-template-cta-padding-uncovered` only if the twin's font is observed wrong in T13.
- **VALIDATE**: `python3 -c "import json; json.load(open('.agents/deferred-items.json'))"`.
- **SATISFIES**: AC 9.

### T15 REPORT + full gate

- **IMPLEMENT**: report `.claude/reports/ce-7-font-fallback-stacks-report.md`: evidence tags, RED outputs (T1, T3, T9), mutation results (T6), masked-audit lines (T10), ladder, A3 table, gate deltas and re-stamp reason, side-by-sides, divergences, Q1 status. Run `piv-validate` (`make check-full`), then `git diff` again (`make lint` rewrites).
- **VALIDATE**: `make check-full` green; `git diff --stat origin/main...HEAD` lists only: this plan, `font_stacks.py`, `test_font_stacks.py`, `component_matcher.py`, `component_renderer.py`, `test_column_text_styling.py`, `test_card_composite.py`, `test_cta_fidelity.py`, `test_component_matcher.py`, `test_component_renderer.py`, `test_content_checks.py`, `content_check_allowlist.yaml`, 7 × `data/debug/*/expected.html`, `data/debug/fidelity_baseline.json`, `docs/fidelity-gate.md`, plus `.agents/deferred-items.json` only if T14 added an entry. Restore `app/ai/agents/*/skill-versions.yaml` if `make test` touched them.
- **SATISFIES**: AC 10.

---

## TESTING STRATEGY

### Unit Tests

`test_font_stacks.py`: builder (enum completeness, classifier, exact stacks, lists, idempotence, sanitising), each matcher site, override emission, renderer guard and double write. Inputs are `TextBlock`/`ButtonElement` objects and a real seed cell — no synthetic email HTML.

### Integration Tests

Minimal Figma `DesignNode` tree through `convert_document` (T3); corpus invariant over the 7 cases (T9); CE-2 content checks with the shrunk allow-list (T8); snapshot test (T10). No WebSocket surface.

### Edge Cases

| Edge case | Verified in |
|---|---|
| Mono name containing "Sans" (`Noto Sans Mono`) | T1 classifier test |
| Serif name containing "Sans" (`Merriweather Sans` → sans) | T1 |
| Family the corpus lacks (`JetBrains Mono`, `Lora`, `Fira Code`) | T1, T3 minimal tree |
| Design family equal to a stack member (`Arial`, `Courier New`) — no duplicate | T1 |
| Already-generic list passes through unchanged | T1, `test_component_renderer.py:297` |
| Quote/escape injection in the family name | T1 sanitiser, T8 escape tests |
| Second font write on the same cell | T3 double-write, T6 mutation |
| No design font (`None`) | T8: `test_cta_label_typography_falls_back_to_legacy_defaults` stays green (no `font-family`); `test_column_text_styling.py:105` updated to the Arial stack |
| Tree-bridge path compile still valid | `uv run pytest app/design_sync/tests/ -q -k tree` in T15's suite |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync` · `uv run ruff check --no-fix app/design_sync`
- `uv run mypy app/` · `uv run pyright app/`
- `make lint-numeric` · `make golden-conformance`

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_font_stacks.py app/design_sync/tests/test_column_text_styling.py app/design_sync/tests/test_card_composite.py app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_component_renderer.py app/design_sync/tests/test_component_matcher.py app/design_sync/tests/test_vml_button.py app/design_sync/tests/test_content_checks.py -q`
- `uv run pytest app/design_sync/tests/ app/components/tests/ -q`

### Level 3: Converter gates

- `make snapshot-test` · `make converter-data-regression` · `make golden-conformance` · `make fidelity-gate`
- `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` (T0/T12)
- Final: `make check-full` via `piv-validate`

### Level 4: Manual Validation

1. `uv run python .tmpscratch/ce7/mask_audit.py` → 7 lines `masked_equal=True` (T10 ships the script).
2. `uv run python -m app.design_sync.tests.content_checks` → no `font_generic` failure on any case.
3. Open `.tmpscratch/ce7/c10-after.png` beside `email-templates/training_HTML/for_converter_engine/mammut/manual_component_build.html` rendered at 600 px: "BUILD YOUR LAYERS" is monospace (T13 produces both).

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: `font_stacks.py` returns the issue's three stacks by category, per-category unit tests pass including families the corpus lacks; enum mapping checked (T1–T2).
- [ ] AC 2: every converter font write (5 inline sites, the VML spec, 3 override emissions, 3 renderer appliers) routes through the builder; category invariant green on the minimal tree and all 7 cases, RED on base (T3–T5, T8, T9).
- [ ] AC 3: a second font write on one cell leaves one well-formed declaration; mutation halves recorded (T3, T6).
- [ ] AC 4: CE-2 `font_generic` passes on every case and its six allow-list entries are deleted (T8).
- [ ] AC 5: snapshots regenerated; masked audit `masked_equal=True` on all 7 (T10).
- [ ] AC 6: ladder unchanged from base (T11).
- [ ] AC 7: A3 before/after for the full corpus reported and within ±0.001 of the spike figures (R4); fidelity gate green after a re-stamp of cases 6, 7, 10 whose reason names each moved section; Q3 ratified before the re-stamp (T12).
- [ ] AC 8: mammut "BUILD YOUR LAYERS" renders mono at 600 px side-by-side; Starbucks side-by-side recorded (T13).
- [ ] AC 9: ledger updated if T12/T13 found an unreachable write (T14).
- [ ] AC 10: `make check-full` green on the head; report written; held-out check n/a (CE-5 #423 open) (T15).

---

## COMPLETION CHECKLIST

- [ ] T0–T15 done in order, each VALIDATE run and recorded
- [ ] RED outputs recorded for T1, T3, T9; mutation results for T6
- [ ] Masked audit 7 × equal; ladder, A3 table, fidelity gate (re-stamped) green
- [ ] `make check-full` green; `git diff` re-read after lint
- [ ] Report written with every figure tagged observed / derived / expected

---

## OPEN QUESTIONS / ASSUMPTIONS

- **Q1 — ANSWERED 2026-10-04 (user): out of scope, as recommended.** Shell font. `token_transforms._font_stack` (YAML map, else `X, Arial, Helvetica, sans-serif`) still writes the `<body>`/`<style>` font. It ends generic and is category-blind (a serif token font gets a sans tail). Plan: out of scope (D9) because the issue's Files list omits it and `ce-3-file-wide-tokens-body-font` owns the shell's wrong family. If the user wants literally every write routed, add one task: replace `_font_stack`'s fallback with `font_stack` (keeps the YAML map for named fonts) and re-run T10–T12 — every case's shell bytes change.
- **Q2** Quoting. D5 keeps the issue's single-quoted multi-word names and drops `html.escape` at the font sites. Alternative: unquoted names (valid CSS) with escaping left in place. Chosen: quoted, because it matches the issue's stacks and the builder's charset is attribute-safe.
- **A1** Assumed: no template font-family value is rewritten by a regex outside the three renderer appliers after the matcher writes it. T10's masked audit would surface a stray rewrite as a non-font diff.
- **Q3 — RATIFIED 2026-10-04 (user): all three, as recommended. T12 re-stamps without stopping, provided the T10 `cmp` is identical.** Ratify three measured drops before execution, so T12 runs without stopping. Each has a different cause:
  1. Gate c7 `2833:1942` −0.0059 (margin 0.005). The 30 px Noto Sans heading moves from Liberation Serif to Liberation Sans in the pinned image. The design reference is a sans, and the after crop matches it while the before crop does not (`.tmpscratch/ce7/c7-1942-{before,after,reference}.png`, observed).
  2. A3 c6 idx 1 −0.006. The heading "PUMPKIN NOW, PEPPERMINT ON THE WAY" and its body copy were bare `Roboto`, rendered serif; now Helvetica. The reference (Roboto) is a sans, and the after crop matches its shape (`.tmpscratch/ce7/c6-heading-{before,after,reference}.png`, observed).
  3. A3 c5 idx 8 −0.007. Not a face change on that section. The "Discover →" CTA above it is 1 px shorter (43→42 px; the arrow glyph falls back to Arial instead of the system sans), so the page below shifts 1 px. Neighbouring sections idx 7/9–14 move +0.005 to +0.008 for the same reason: the known bidirectional scorer artifact.
  Recommended: ratify all three. Not ratifying 1 means CE-7 cannot merge without moving the fidelity margin; not ratifying 2 or 3 changes nothing in the code (A3 is advisory) but leaves the trade unrecorded.
- **A2** The pinned image's font set is fixed: Liberation Sans/Serif/Mono for the three stacks, no Noto Sans, Roboto or Geist Mono (observed `fc-match` and CDP in the image). A Playwright bump changes this and is its own re-stamp (`docs/fidelity-gate.md:19`).

## NOTES

- Why not extend `_font_stack` in `token_transforms.py`: it is shell-only, private, and returns a sans tail for every unmapped font; reusing it would put category logic in the token layer and change the shell (Q1). The new module is importable by matcher and renderer without a cycle (`font_stacks.py` imports nothing from design_sync).
- Why the matcher emits stacks and the renderer re-applies: the matcher is where the design family is known per text node; the renderer guard makes any other override producer (correction applicator, future CE-13 role applier) safe without a second code path. Idempotence (D4) is what makes the double call free.
- The `html.escape` → `&#x27;` hazard is why D5 is load-bearing: `_upsert_style_decl` would match `font-family:&#x27` and leave `Geist Mono&#x27;, 'Courier New'…` as a junk declaration. T3's double-write test is the guard.

## AMENDMENTS

- 2026-10-04 — Risk closure pass: a second spike measured R1 (fidelity gate: one section, c7 `2833:1942` −0.0059, cause isolated in the pinned image), R2 (double write clean; the escaped variant corrupts, proven), R3 (mammut CTA renders Courier New) and R4 (full-corpus A3, every section move traced to a glyph or face change). T12 now carries a fixed decision rule with the measured figures. Q3 asks for ratification up front. Spike reference: `.tmpscratch/ce7/spike.patch`, `spike_font_stacks.py`, probe scripts in `.tmpscratch/ce7/`. Then a third pass: probe scripts moved into `.tmpscratch/ce7/`, `_` handling fixed (S5), T10 compares bytes against the spike output, c6 crops checked, and Q3 split by cause. Confidence 10/10 once the user answers Q1 and Q3.
- 2026-10-04 — User answered Q1 (shell out of scope) and ratified Q3 (all three drops). Confidence 10/10.
- 2026-10-04 — Execution amendments (report `.claude/reports/ce-7-font-fallback-stacks-report.md` §Deviations): minimal tree gains lead/tail frames (T3); corpus test adds the non-MSO escaped-font assertion (T9, closes T6(a) on the corpus); `_apply_image_corner_radius` left unchanged (T5); `_card_text_row` uses `font_stack(text.font_family or "Arial")` (ruff SIM108, same output) (T4); content-check helper picks the first stack outside conditional blocks (T8); T13 before render from the T0 capture. All figures reproduced the spike exactly (gate table, A3 JSON, `cmp` × 7).
