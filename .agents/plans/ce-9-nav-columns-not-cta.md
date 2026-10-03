# Feature: icon + label columns stop routing as CTAs (CE-9, #427)

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay attention to the names of existing utils, types and models, and import from the right files.

Base: origin/main `1a891e70` (observed: `git fetch` + `git log -1 origin/main`, 2026-10-03). All `file:line` refs below were read at that head. Branch: `feat/ce-9-nav-columns-not-cta`, cut from `origin/main` (the main checkout sits on the merged `plan/dsl-spec`; do not branch from it).

**One-pass confidence: 10/10.** The whole change was built and measured in a throwaway spike before this plan was finalised. Every behaviour, gate result, A3 figure, screenshot, mutation outcome and test count the tasks rely on was observed on that spike (S-table). Every risk the first draft carried was either fixed in the spike and measured (R1, R2, R3) or found to predate this ticket, reproduced on base and ledgered (R4–R6). No step depends on an unmeasured assumption or on user input still outstanding.

**Reference implementation:** `.tmpscratch/ce9/spike.diff` (gitignored, main checkout; 10 files, binary-safe). Worktree `.tmpscratch/ce9-spike` (detached, WIP commit `fb3b4beb` = exactly that diff on `1a891e70`, after the review fixes in S17 and the fixture-script asset re-save in S18; its `.venv` is an untracked symlink, never commit it). Scratch artefacts in `.tmpscratch/ce9/`: `a3_before/`, `a3_after2/` (scores.json + composites), `gate_base.txt`, `gate_after.txt` (first attempt, failed), `gate_after2.txt`, `gate_after2_c6.txt`, `restamp.txt`, `cap2/<case>.html` (`cap/` holds pre-fix captures, do not use), `nav_640.png`, `nav_375.png`, `gate_crops_after.png`, `mutate.py`, `shots.py`, `overflow.py`, `tree_probe.py`, `make_test.txt`. The implementer ports the diff task by task with path filters (T2, T3, T5, T6, T8 name theirs) and re-runs every VALIDATE on the branch. Three paths in the diff are **reference only, never applied**: `data/debug/fidelity_baseline.json` (the spike's rehearsal stamp names base `1a891e70` and predates F1; T9 is the only stamp), `data/debug/6/expected.html` (T4 regenerates it; the diff copy is the comparison target), and `data/debug/6/assets/*.png` (T5 produces them with the fixture script). A main-checkout dry run `git apply --check --binary --exclude='data/debug/*' .tmpscratch/ce9/spike.diff` passes (observed on the final diff).

## Decisions ratified by the user (2026-10-03, planning chat)

| # | Decision | Effect |
|---|---|---|
| U1 | **Matcher only.** No change to `layout_analyzer.py` or `component_renderer.py` | `section_type` stays CTA/SOCIAL for the nav columns; only the matched component changes. "Classed CTA" = the matched slug |
| U2 | **SOCIAL rescue limited to peel-row members** | A standalone one-icon social link keeps `social-icons` |
| U3 | **Reuse the `td` seed** | No new seed, manifest row or conformance surface |
| U4 | **Any CE-1 drop stops for ratification before re-stamp** | Moot after the spike: the final head has no drop (S9); the re-stamp records improvements only |

## Evidence

### Planning probes (observed 2026-10-03 at `1a891e70`; dump script method: `load_structure_from_json` → `normalize_tree` → `analyze_layout` → `match_section`, as `scripts/snapshot-capture.py:50-60`)

| # | Question | Result |
|---|---|---|
| E1 | Nav band in Figma | Wrapper `2833:1453` (640×120, fill `#296042`, padding 28/28) → one `mj-section` → four `mj-column`s `2833:1455/1460/1465/1470` (154/154/154/164 × 64). Each = `mj-image-Frame` → IMAGE 42×42 + `mj-text-Frame` (h 22, padding-top 6) → TEXT "APP"/"ORDER"/"OFFERS"/"REWARDS", 14px, line-height 16, `#FFFFFF`, centred |
| E2 | Segmentation | Semantic peel (`layout_analyzer.py:715-733`, `_peelable_grandkids` `:813`; `_grandkids_are_cards` `:841-849` names "icon+label nav items" as a peel target) → four solo sections sharing `peel_row_id` `2833:1453:r0`, single column, no column groups |
| E3 | Types | idx 4–6 `CTA` (0.5) from `_classify_by_position` `:1179-1193` (22px `mj-text-Frame` with a short TEXT passes its "button child" test); idx 7 `SOCIAL` (0.5) from `:1169-1171`; reached via `_classify_mj_section` fall-through `:1017-1018`. `_extract_buttons` (`:1805`) returns `[]` for all four |
| E4 | Matching on base | idx 4–6 → `cta-button` (`_match_by_type` CTA branch `component_matcher.py:295-300`, never checks `section.buttons`); idx 7 → `social-icons` |
| E5 | Loss point | `_fills_cta` (`:2136`, else-arm `:2177-2179`) writes only `cta_text=""`/`cta_url=""`; `_prune_unfilled_ctas` (`component_renderer.py:1114`) → `_strip_empty_cta_chrome` (`:1144`) deletes the anchorless chrome. Base `expected.html:221-310`: three empty 48px cells; APP/ORDER/OFFERS and their icons absent; REWARDS at 32px via `social-icons` |
| E6 | Row composition | `ComponentRenderer.render_peel_row` (`component_renderer.py:758`) composes the four side by side (MSO ghost 157/157/157/169, inline-block `div.column`), called from `converter_service.py:893-910` |
| E7 | Mobile CSS | `@media only screen and (max-width: 599px) { .column { display:block !important; width:100% !important … } }` (`data/debug/6/expected.html:26-27`) |
| E8 | CTA-family slugs on base, all seven cases | Only c6 idx 4–6; every extracted `ButtonElement` has text |
| E9 | Sections matching the tile predicate | Only c6 idx 4–7 (cases 5–10 + reframe). Near misses: c9 s5 (label ≥ 40 chars), c9 s6 / reframe s7, s12 (have buttons), c10 s11/13/15 (two-column path) |
| E10 | "Follow us" on the default path | Absent in every case's `expected.html` (c9's hit is the design's own "FOLLOW US"); ledger `phase-53g-t1-tree-path-social-label-default` is tree-path only |
| E11 | Hand build | `Starbucks/manual_component_build.html:298-339`: `column-layout-4` of four 149px tile PNGs (icon and label baked into one image) |
| E12 | Gate render width | `fidelity_gate.py:480-481` renders at the frame width (640 for c6); `scripts/score-fidelity-cases.py` renders at 600 |
| E13 | Case-6 design geometry | Section 3 `spacing_after` 84 (includes the wrapper's top 28); section 7 `spacing_after` 28 (wrapper's bottom 28); nav column `y` 4663, `height` 64 |

### Spike (observed 2026-10-03, worktree `.tmpscratch/ce9-spike` at `1a891e70` + spike diff)

| # | What | Result |
|---|---|---|
| S1 | A3 before (base), 7 rows | full / min / median: 5 0.8660/0.6632/0.8852 · 6 0.8126/0.4661/0.7573 · 7 0.8403/0.5459/0.8679 · 8 0.8632/0.8081/0.8645 · 9 0.7089/0.3033/0.7614 · 10 0.7361/0.0639/0.8336 · reframe 0.8437/0.5505/0.8779 (`a3_before/scores.json`) |
| S2 | CE-1 gate on base | `make fidelity-gate` 1 passed (`gate_base.txt`) |
| S3 | RED (tests written, names stubbed: `_CTA_FAMILY_SLUGS` populated, `_is_icon_label_tile` → False, `_fills_icon_label_tile` → `[]`) | 10 failed on assertions, 20 passed: RED = node-tree routing, CTA/SOCIAL/HEADER tile routing, CTA-without-button, both tile-HTML tests, VLM guard, both c6 corpus invariants. Green on base as designed: checked mapping, standalone social, real CTAs, five non-tile shapes, 12 non-c6 corpus invariants. The node-tree test's precondition (some section typed CTA) held on base |
| S4 | First implementation (no label gap) | 30/30 new tests green; converter suite flagged `test_every_referenced_asset_committed[6]` (icons `2833_1457/1462/1467` rendered but untracked) and F5 `test_content_group_follows_design_order` (selected c6 `2833:1470` by `social-icons` slug). Both fixed (Task 6) |
| S5 | First gate attempt | FAILED: `2833:1465` −0.0083 (margin 0.005); `2833:1455` −0.0023, `2833:1460` −0.0045, `2833:1470` +0.0018, `2833:1475` +0.0000. Gate crops at 640 (`gate_crops_after.png`): render label ≈ 6px higher than design (the `mj-text-Frame` padding-top 6 was not applied) |
| S6 | Fix: label gap from geometry | gap = column height − icon height − Σ label line-heights = 64 − 42 − 16 = 6 (derived, E1); label row `padding:6px 0 0`; tile height 64 = design (observed, S10) |
| S7 | Baseline audit on the final spike (`snapshot-capture.py <case> --output .tmpscratch/ce9/cap2/<case>.html`, fresh dir; `diff --ignore-all-space`) | vs `origin/main` baselines: 5, 7, 8, 9, 10, reframe 0 changed lines; c6 72. vs the regenerated head baselines: all 0. c6 changes confined to `section_4`–`section_7` (the four `cta-button`/`social-icons` blocks → `td` tiles: centred 42px icon + label `font-family:Roboto,sans-serif;font-size:14px;font-weight:400;color:#FFFFFF;line-height:16px;text-align:center` with `padding:6px 0 0`); `grep -c "padding:6px 0 0"` = 4; "Follow us" 0 |
| S8 | Gates after the fix | `make snapshot-test` 38 passed, 12 skipped, 2 xfailed; ladder `-k ladder` 7 passed and `data/debug/ladder_snapshot.json` unchanged; `make golden-conformance` 26 passed; `test_content_checks.py` 56 passed (allowlist rows for c6 unchanged); `make lint-numeric` clean; `make types` 0 errors (mypy + pyright); ruff check/format clean |
| S9 | CE-1 gate after the fix (measured before F1; still holds, derived via byte identity: the post-F1 c6 capture equals the baseline this run measured, S7) | PASS (`gate_after2.txt`). c6: `2833:1455` 0.9827→0.9891 (+0.0064 improved), `2833:1460` 0.9740→0.9787 (+0.0047), `2833:1465` 0.9765→0.9781 (+0.0016), `2833:1470` 0.9629→0.9802 (+0.0173 improved), `2833:1475` +0.0000; every other section in all seven cases +0.0000 |
| S10 | Screenshots (`shots.py`, Chromium, light) | 640px: one row, four icons each above its label, row box 640×64 (`nav_640.png`). 375px: clean stack of four centred tiles, 4 × 64 = 256px (`nav_375.png`) |
| S11 | A3 after the fix, 7 rows (measured before F1; holds by the same byte identity) | c6 full 0.8126→0.8131, min 0.4661→0.4661, median 0.7573→0.7573, max per-section Δ 0.002 (section 8 0.826→0.828); cases 5, 7, 8, 9, 10, reframe: 0.0000 on every number (`a3_after2/scores.json`) |
| S12 | Re-stamp rehearsal | `make fidelity-restamp CASES="6" REASON=…` stamped case 6 (`restamp.txt`); `fidelity_baseline.json` +12/−4; `make fidelity-gate` after: 1 passed |
| S13 | Tree path (R2) | Whole-case tree compile of c6 falls back to legacy on base and on the spike ("Unsafe URL scheme in button href: '#'", unrelated, R6). Compiling the four real c6 nav-tile matches alone through `build_email_tree` + `TreeCompiler`: all four icon ids and labels present (`test_c6_nav_tiles_compile_on_the_tree_path`). With `slot_type="text"` (mutation M5) the icons are stripped |
| S14 | Mutations (`mutate.py`, each reverted, file restored byte-identical) | see Task 7 table |
| S15 | Full suite | `make test`: 8900 passed, 118 skipped, 10 xfailed, 0 failed (`make_test.txt`) |
| S17 | Fresh-agent code review of the spike (code-reviewer, 2026-10-03) | High 0, Med 2, Low 7. Fixed in the spike: F1 predicate counted placeholder/blank labels the filler drops (now `_tile_labels` filters both, every text must be a real label; 2 new param cases, mutation M8); F2 assets force-added instead of allowlisted (`.gitignore` gains three `!data/debug/6/assets/2833_14xx.png` lines, `git check-ignore` rc=1); F3 docstring states the one-line-label assumption; F4 two-label test; F7 overflow entry got `code_refs`; F9 moot after F1 (predicate guarantees every text renders). Not taken: F5 `alt=""` for tile icons (the G3-neg conformance gate forbids empty alt, closed ledger `phase-53-b5-decorative-empty-alt-vs-g3neg`); F6 stamp commit is the host HEAD at stamp time, handled by T9's ordering; F8 CTA→CONTENT applies to every button-less CTA section, intended and corpus-neutral (S7), stated in the PR body. After the fixes: 36 new tests green, `make snapshot-test` 38 passed, converter + components suite 3411 passed / 0 failed, `make types` 0 errors, `make fidelity-gate` 1 passed |
| S18 | Asset provenance (advisor) | `scripts/prepare-fidelity-fixtures.py --cases 6` prints exactly the `.gitignore` lines the spike added (3 new + 8 existing case-6 lines, observed) and re-saves the three icons with `optimize=True`: pixel-identical to the raw copies (84×84, `ImageChops.difference` empty), 891/1073/1249 bytes. The spike now commits the script's output. `reference_1x.png` unchanged by the run |
| S19 | Stamp-commit precedent | CE-3's three stamps name `98355b2f`, which is not an ancestor of `origin/main` (`git merge-base --is-ancestor`, squash merge). A stamp naming a branch commit that the squash removes is the accepted pattern |
| S20 | `make check-full` on the final spike (`check_full.txt`, `check_full_rest.txt`) | lint: no rewrites; mypy "Success: no issues found in 1392 source files"; pyright 0 errors; `make test` 8903 passed / 0 failed / 10 xfailed; `fidelity-gate` 1 passed; `check-fe` could not run (worktree has no `cms/node_modules`: `tsc: command not found`) and is not this diff's gate (no `cms/` change; DoD frontend gate applies only to `cms/`); `security-check migration-lint validate-overlays lint-numeric golden-conformance flag-audit check-env-drift` exit 0 (flag-audit PAST_REMOVAL_DATE warnings are advisory and pre-existing) |
| S16 | Pre-existing, reproduced on base | 600px viewport wraps the fourth peel-row cell (A3 composite; base wrapped REWARDS too). 375px page `scrollWidth` 463 on base and spike (`overflow.py`). Tree compile falls back on base for c5 (`hero_image` slot undefined for `hero-block`), c6 and reframe (`#` href) (`tree_probe.py`) |

## Feature Description

A row of icon + short-label columns (a nav band: app, order, offers, rewards) loses its icons and labels. The segmenter peels the columns into solo sections, a position fallback types three of them CTA although none holds a button, the matcher sends every CTA type to `cta-button`, and the CTA filler writes neither the icon nor the label. This ticket routes such columns to an icon-over-label tile that renders both at design size and design spacing, and stops both the heuristic and the VLM path from choosing a CTA component for a section with no button.

## User Story

As a marketer converting a Figma email
I want a row of icon + label links to come out as icons with their labels
So that a nav band does not render as empty green boxes

## Problem Statement

- `_match_by_type` maps any `CTA` type to `cta-button` without checking `section.buttons` (E4); the VLM fallback can do the same (`match_section_with_vlm_fallback`, `component_matcher.py:165-242`).
- No default-path component exists for a peeled column holding one small icon and a short label: `navigation-bar` is text-only (`_fills_nav` `:2689`) and its seed is `hide` on mobile (`navigation-bar.html:5`); `social-icons` rescales the icon to 32px.

## Solution Statement

Port the spike. In `component_matcher.py`: an icon-label tile route in `match_section` (`td` seed, `attr` HTML fill built from the column row builders, label gap from geometry), a CTA guard in `_match_by_type`, a VLM guard, and a checked `_CTA_FAMILY_SLUGS` set. Regenerate case 6, commit its three icon assets, re-stamp case 6 with the measured improvements, retarget one F5 test, and ledger the pre-existing defects the spike surfaced.

## Out of Scope / Non-Goals

- Not changing classification (`layout_analyzer.py`), the peel, section counts or the ladder (U1).
- Not changing `_strip_empty_cta_chrome` / `_prune_unfilled_ctas` (U1; they only delete chrome `_fills_cta` already emptied).
- Not fixing the 600–639px peel-row wrap, the 375px c6 page overflow, the tree-path compile fallbacks, or the band's 28/28 wrapper padding (all pre-existing, S16; ledgered in Task 8).
- Not wrapping tile icons/labels in links (the design carries no hyperlink on these nodes; `ImagePlaceholder` has no URL).
- Not touching the social icon-size fallback (`phase-53g-t1-social-non-icon-images-as-icons`).

## Feature Metadata

**Feature Type**: Bug Fix
**Estimated Complexity**: Low (spike-proven port)
**Primary Systems Affected**: `app/design_sync/component_matcher.py` (default render path; tree path benefits); case-6 baseline
**Dependencies**: none new

## Related Work

**Implements**: #427 (CE-9) · **Epic**: #439, slices `.agents/plans/converter-epic-slices.md:151-158`

**Back-references**: `.agents/plans/converter-epic-slices.md` (conventions inherited); `.agents/plans/ce-1-fidelity-baseline-gate.md` (gate, re-stamp); `.agents/plans/ce-3-corpus-refresh.md` (seven-case corpus, spike-plan precedent).

**Forward-references**: (none yet)

**Parallel tickets on the same file**: CE-8 #426, CE-11 #429 (`component_matcher.py`/`component_renderer.py`); no open PR at planning time (`gh pr list --search`). This diff touches `match_section`, `match_section_with_vlm_fallback`, `_match_by_type`, `_column_text_row`, `_column_image_row` and adds new symbols after `_build_column_fill_html`; rebase in merge order.

## Risks and how each is closed

| # | Risk (first draft) | Closed by | Evidence |
|---|---|---|---|
| R1 | Shorter row shifts content; CE-1 drop on `2833:1475` | Label gap from geometry makes the tile 64px = design | S5 → S6 → S9 (`2833:1475` +0.0000, all nav sections up), S10 (row 640×64) |
| R2 | Tree path strips the tile to text | `slot_type="attr"` (the `_fills_social` precedent, `component_matcher.py:2609`) → `HtmlSlot` | S13; unit `test_tree_path_keeps_the_icon`; M5 |
| R3 | VLM can still pick a CTA slug for a button-less section | Guard in `match_section_with_vlm_fallback` | `test_vlm_cta_slug_rejected_without_button`; M6 |
| R4 | 600–639px viewports wrap the last peel-row cell | Pre-existing (base wrapped REWARDS); out of U1 scope | S16; new ledger `ce-9-peel-row-fixed-width-wrap` |
| R5 | c6 page 463px wide at 375px | Pre-existing, identical on base | S16; new ledger `ce-9-c6-mobile-page-overflow` |
| R6 | Whole-case tree compile falls back (c5, c6, reframe) | Pre-existing, unrelated; tile proven on the tree path in isolation | S13, S16; new ledger `ce-9-tree-path-corpus-compile-fallback` |
| R7 | Rendered icon assets not committed (CE-1 fixture test) | Allowlist per file in `.gitignore` and commit the three PNGs | S4, S17 (F2); `test_every_referenced_asset_committed[6]` green |
| R8 | F5 social-order test borrowed c6 REWARDS by slug | Select by node id via `_all_matches` | S4; test green, still exercises `_fills_social` on the real content-group shape |

## Deferred Items Touching This Plan

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `phase-53g-t1-tree-path-social-label-default` | epic table → CE-9 | carry forward + note | Tree path only (E10); note records the default-path check |
| `phase-53g-t1-social-non-icon-images-as-icons` | epic table → CE-9; `component_matcher.py:2576` | avoid | Tile needs exactly one image; c6 s8 / c10 s14 stay on `social-icons` |
| `phase-53g6-card-tree-path-text-only` | `td` content-slot shape | carry forward + note | Note names `slot_type="attr"` as the candidate fix for `_fills_card` |
| `phase-53g-band-item-spacing-defaults-vs-wrapper-padding` | wrapper padding not threaded | carry forward + note | Peeled rows lose the 28/28 band padding too (E13); tile-internal gap fixed here |
| `phase-53g-g3-template-cta-padding-uncovered`, `ce-2-cta-button-vml-twin-unfilled` | CTA templates in `component_renderer.py` | avoid | No CTA template change |
| `phase-53f-decorative-image-flag` | `_column_image_row` | avoid | New `align` kwarg defaults to today's markup (S7 byte-identity) |
| `phase-53g-g9-img-not-rescaled-with-column` | column rescalers | avoid | 42px icon in a ≥154px cell; no rescaler involved |
| `phase-53g-g4-general-sub-template-recursion`, `phase-53f-eyebrow-partial-padding-cell-theft`, `phase-53g-g5-pill-white-on-light-latent`, `phase-53g-g11-contentgroup-column-divider-gap`, `phase-53g-g7-per-side-stroke-capture` | file-level refs on matcher/renderer | avoid | Different functions |

New entries added by this plan (Task 8): `ce-9-peel-row-fixed-width-wrap`, `ce-9-c6-mobile-page-overflow`, `ce-9-tree-path-corpus-compile-fallback`. Grep used: `python3` over `items` with `status == "deferred"` and `code_refs` containing `component_matcher`/`component_renderer`/`layout_analyzer`, plus the ids the epic names, plus keyword sweeps (overflow, mobile, peel row, href, tree path) (2026-10-03).

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/component_matcher.py:99-138` (`match_section`; column branch `:111-122` is the precedent for fills built outside `_build_slot_fills`), `:165-242` (VLM fallback), `:255-325` (`_match_by_type`; CONTENT `:286-293`, CTA `:295-300`), `:745-818` (`_column_text_row`), `:940-997` (`_ICON_MAX_WIDTH_PX`, `_column_image_row`), `:1069-1086` (`_wrap_column_table`), `:1115-1140` (`_SPEC_LABEL_MAX_CHARS`), `:2070-2133` (`_fills_card`, the `td` dispatch), `:2136-2180` (`_fills_cta`), `:2540-2615` (`_fills_social`, `attr` precedent at `:2609`).
- `app/design_sync/tree_bridge.py:170-208` (`_fill_to_slot_value`: `text` strips tags, `attr` → `HtmlSlot`); `app/components/tree_compiler.py:317-334` (`_fill_html`).
- `app/design_sync/tests/test_social_section_content.py:22-45, 200-212` (helpers; F5 test to retarget).
- `app/design_sync/tests/test_fidelity_gate.py:313-317` (`test_every_referenced_asset_committed`).
- `app/design_sync/tests/test_vlm_classifier.py:205-259` (VLM fallback test pattern).
- `email-templates/components/td.html` (`<td data-slot="content" align="center" style="padding:0;">`).
- `.claude/skills/converter-fix/SKILL.md` + `references/baselines-and-gates.md`, `references/a3-scoring.md`.

### New Files to Create

- `app/design_sync/tests/test_icon_label_columns.py` (36 tests in the spike; in `spike.diff`).

### Patterns to Follow

- Constants reused, no new numeric literals in predicates: `_ICON_MAX_WIDTH_PX` (64), `_SPEC_LABEL_MAX_CHARS` (40).
- Checked mapping: `_CTA_FAMILY_SLUGS` is asserted equal to the seed slugs `_build_slot_fills` dispatches to `_fills_cta` (spy on the module name; the dispatch dict is local to `_build_slot_fills`, do not hoist it).
- Generality rule: the routing test builds a minimal Figma node tree with generic labels and runs the real `analyze_layout`; no fixture id, colour or pixel value in source logic.
- Email HTML table-only (CLAUDE.md); `make golden-conformance`.

---

## STEP-BY-STEP TASKS

### T1 SETUP branch and base

- **IMPLEMENT**: `git fetch origin && git switch -c feat/ce-9-nav-columns-not-cta origin/main`. If `origin/main` ≠ `1a891e70`, run `git diff --stat 1a891e70 origin/main -- app/design_sync/ app/components/ data/debug/ email-templates/components/` and stop if any listed path moved (the spike numbers would no longer be base). Run `/preflight-check .agents/plans/ce-9-nav-columns-not-cta.md`.
- **GOTCHA**: the main checkout carries uncommitted `skill-versions.yaml` stamps and untracked review files; stage only this task's files at every commit.
- **VALIDATE**: `git log -1 --format=%h origin/main` → `1a891e70` (or the empty diff above).
- **SATISFIES**: AC 7.

### T2 CREATE the test file and prove RED

- **IMPLEMENT**: take `app/design_sync/tests/test_icon_label_columns.py` and the `test_social_section_content.py` hunk from `spike.diff` (`git apply --include='app/design_sync/tests/*' .tmpscratch/ce9/spike.diff`). Add stubs to `component_matcher.py` so imports resolve: `_CTA_FAMILY_SLUGS` (full set), `_is_icon_label_tile` → `False`, `_fills_icon_label_tile` → `[]`.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_icon_label_columns.py -q -p no:cacheprovider` → RED on assertions, matching S3 (plus the tests added after S3 — label-gap ×2, two-label gap, c6 tree compile — RED; the placeholder/blank-label params stay green under the stubs because the stub predicate is always False). Record the failing names in the report. No ImportError.
- **SATISFIES**: AC 1–3.

### T3 IMPLEMENT the matcher change

- **IMPLEMENT**: apply the `component_matcher.py` hunk of `spike.diff` (`git apply --include='app/design_sync/component_matcher.py' …`; the stubs from T2 are replaced by it — revert the stubs first). Contents, for review:
  - `match_section`: before `_match_by_type`, `if _is_icon_label_tile(section)` → `ComponentMatch(component_slug="td", slot_fills=_fills_icon_label_tile(section, image_urls), token_overrides=_build_token_overrides(...), spacing_after=...)`.
  - `match_section_with_vlm_fallback`: `if new_slug in _CTA_FAMILY_SLUGS and not section.buttons: return match`.
  - `_match_by_type`: before the CONTENT branch, `if st == CTA and not has_buttons: st = CONTENT`.
  - `_column_text_row(..., padding: str = "0 0 8px")`; `_column_image_row(..., align: str | None = None)` — defaults byte-identical.
  - After `_build_column_fill_html`: `_CTA_FAMILY_SLUGS`, `_is_icon_label_tile` (peel member, no button, exactly one image ≤ `_ICON_MAX_WIDTH_PX` both sides, 1–2 texts, every text a real label per `_tile_labels` — non-blank, not `_is_placeholder` — and each `< _SPEC_LABEL_MAX_CHARS`), `_fills_icon_label_tile` (centred `_column_image_row`, labels via `_column_text_row` with `padding:{gap}px 0 0` on the first and `0px 0 0` on the rest, `SlotFill("content", …, slot_type="attr")`), `_icon_label_gap` (column height − icon height − Σ label line-heights, 0 when any is unknown or negative).
- **GOTCHA**: `ruff format` reflows the `_column_image_row` call; run it before `ruff check --no-fix`. Never `ruff --fix` beyond `--select I`.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_icon_label_columns.py app/design_sync/tests/test_component_matcher.py app/design_sync/tests/test_cta_fidelity.py -q -p no:cacheprovider` all green; `uv run ruff check --no-fix app/design_sync/ && uv run ruff format --check app/design_sync/component_matcher.py app/design_sync/tests/test_icon_label_columns.py`; `make types` 0 errors.
- **SATISFIES**: AC 1–4.

### T4 REGENERATE and AUDIT the baselines

- **IMPLEMENT**: capture all seven cases to scratch (`DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/snapshot-capture.py <case> --output .tmpscratch/ce9/cap3/<case>.html` — a fresh directory: `--output` refuses an existing file and prints only an error, which once left a stale comparison in the spike), `diff --ignore-all-space` against committed `expected.html`; then `--overwrite` case 6 only. Compare the new `data/debug/6/expected.html` with the spike's (`git show fb3b4beb:data/debug/6/expected.html` inside `.tmpscratch/ce9-spike`, or the `spike.diff` hunk): identical.
- **GOTCHA**: check each capture prints "Output saved"; never `make snapshot-capture` (hardcodes `--overwrite`); a whitespace-only c8 diff is known churn, restore it.
- **VALIDATE**: non-targets 0 changed lines (S7); `make snapshot-test` green; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder -q` green and `git diff origin/main -- data/debug/ladder_snapshot.json` empty; `grep -c "padding:6px 0 0" data/debug/6/expected.html` = 4; `grep -ci "follow us" data/debug/6/expected.html` = 0; `make golden-conformance`; `uv run pytest app/design_sync/tests/test_content_checks.py -q`; `make lint-numeric`.
- **SATISFIES**: AC 4, 5, 7.

### T5 PREPARE, ALLOWLIST and COMMIT the icon assets

- **IMPLEMENT**: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/prepare-fidelity-fixtures.py --cases 6` (after T4, so it sees the tiles; it re-saves every referenced asset ≤ 600px and prints the allowlist block). Add the three new lines it prints (`!data/debug/6/assets/2833_1457.png`, `_1462`, `_1467`) to the existing case-6 block in `.gitignore` (per-file rule, `docs/fidelity-gate.md:112`; same lines as the spike's `.gitignore` hunk). `git status` must show only the three new PNGs under `data/debug/6/` (S18: `reference_1x.png` and the other assets unchanged). Then `git add` the three PNGs (no `-f`).
- **VALIDATE**: `git check-ignore data/debug/6/assets/2833_1457.png` exits 1; the three files are byte-identical to `git -C .tmpscratch/ce9-spike show fb3b4beb:data/debug/6/assets/2833_1457.png` etc. (`cmp`); `uv run pytest "app/design_sync/tests/test_fidelity_gate.py::TestCommittedFixtures" -q` green.
- **SATISFIES**: AC 6.

### T6 RETARGET the F5 social-order test

- **IMPLEMENT**: the `test_social_section_content.py` hunk (applied in T2): `_social_matches` becomes a filter over a new `_all_matches`; `test_content_group_follows_design_order` selects c6 `2833:1470` from `_all_matches("6")` with a comment saying why.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_social_section_content.py -q` green.
- **SATISFIES**: AC 7.

### T7 PROVE the tests by mutation (both halves)

- **IMPLEMENT**: run `uv run python .tmpscratch/ce9/mutate.py` from the repo root. It snapshots `app/design_sync/component_matcher.py` to `.tmpscratch/ce9/cm_good.py`, applies each mutation, runs the new test file, and restores the snapshot. Expected (S14, observed on the spike):

| Mutation | RED | Stays green (by design) |
|---|---|---|
| M1 drop the CTA guard | `test_cta_without_button_is_not_a_cta_component` | `test_cta_component_implies_a_button[6]` (the tile route catches c6 first) |
| M2 drop the peel-row requirement | `test_standalone_social_link_keeps_social_icons` | tile routing tests |
| M3 tile slug → `cta-button` | node-tree routing, CTA/SOCIAL/HEADER tile routing, both c6 corpus invariants, c6 tree compile (7) | — |
| M4 drop the icon row | tile HTML, node-tree routing, c6 output invariant, unit tree test, c6 tree compile (5) | — |
| M5 `slot_type="text"` | `test_tree_path_keeps_the_icon`, `test_c6_nav_tiles_compile_on_the_tree_path` | default-path tests (renderer inserts both alike) |
| M6 drop the VLM guard | `test_vlm_cta_slug_rejected_without_button` | — |
| M7 gap forced to 0 | `test_label_gap_from_column_geometry` | — |
| M8 predicate counts raw texts (F1 reverted) | `test_non_tile_shapes_do_not_route_to_td[placeholder-label]`, `[blank-label]` | — |

- **VALIDATE**: totals per mutation as observed on the final spike (36 tests): M1 1, M2 1, M3 7, M4 5, M5 2, M6 1, M7 1, M8 2 failed; `diff -q app/design_sync/component_matcher.py .tmpscratch/ce9/cm_good.py` after the run; the mutation table goes into the report with both columns.
- **SATISFIES**: AC 1–4 (tests are load-bearing).

### T8 UPDATE the ledger

- **IMPLEMENT**: apply the `.agents/deferred-items.json` hunk of `spike.diff` (or re-create via the `deferred-items` skill): notes on `phase-53g-t1-tree-path-social-label-default`, `phase-53g-band-item-spacing-defaults-vs-wrapper-padding`, `phase-53g6-card-tree-path-text-only`; three new entries `ce-9-peel-row-fixed-width-wrap`, `ce-9-c6-mobile-page-overflow` (code_refs: c6 `expected.html`, `render_peel_row`), `ce-9-tree-path-corpus-compile-fallback` (`introduced_commit: "pending"`, stamped after merge per the deferred-items skill). No closes.
- **VALIDATE**: `python3 -c "import json;d=open('.agents/deferred-items.json').read();assert json.dumps(json.loads(d),indent=2,ensure_ascii=False)+'\n'==d"` (byte round-trip, observed on the spike).
- **SATISFIES**: AC 9.

### T9 SCORE A3, run the CE-1 gate, re-stamp

- **IMPLEMENT**: first make a `chore(wip):` commit of T2–T8 so the stamp's `commit` field names a commit that produces the scores (the stamp records the host HEAD; review F6). `piv-commit` folds it, and the squash merge removes it from main anyway — the CE-3 precedent (S19). Do not apply the spike's `fidelity_baseline.json` hunk. A3 after with `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` (move any old `.tmpscratch/fidelity/` aside first; the hook blocks `rm -rf` on it); compare with `.tmpscratch/ce9/a3_before/scores.json`. `make fidelity-gate` (Colima running). Then `make fidelity-restamp CASES="6" REASON="CE-9 #427: nav band icon+label tiles render: 2833:1455 +0.0064, 2833:1460 +0.0047, 2833:1465 +0.0016, 2833:1470 +0.0173; other case-6 sections +0.0000"` — replace the figures with this run's if any differ, and stop for the user if any case-6 section shows a drop (U4). Re-run `make fidelity-gate`.
- **VALIDATE**: A3 matches S11 (non-targets 0.0000; c6 per-section |Δ| ≤ 0.002); gate rows match S9; gate passes after re-stamp; `git diff --stat -- data/debug/fidelity_baseline.json` ≈ +12/−4 and its new stamp's `commit` is the WIP commit, not `1a891e70`.
- **SATISFIES**: AC 6.

### T10 VISUAL check and report

- **IMPLEMENT**: run `.tmpscratch/ce9/shots.py` from the repo root (paths relative to it) for 640/375px; write `.claude/reports/ce-9-nav-columns-not-cta-report.md`: S-table figures re-derived on the branch (tagged observed with the command), RED list, mutation table, baseline audit, ladder, A3 table (7 rows), gate rows, screenshots, divergences, ledger ids.
- **VALIDATE**: 640px row box 640×64 with four icon+label tiles; 375px four stacked tiles (S10).
- **SATISFIES**: AC 4.

### T11 GATE and hand off

- **IMPLEMENT**: `piv-commit` (`fix(design-sync): route icon+label columns to a tile, not a CTA (CE-9)`), `piv-validate` (`make check-full` via `record-gate.sh` on the committed head), `piv-create-pr` (draft, base `origin/main`, body per `converter-fix` "PR body"), then watch CI.
- **VALIDATE**: `make check-full` green in the real checkout, where `check-fe` has its `node_modules` (S20 ran every other target green on the spike); PR body states F8 (button-less CTA sections of any origin now score as content); `git diff --stat origin/main...HEAD` lists exactly: `.gitignore`, `.agents/deferred-items.json`, `.agents/plans/ce-9-nav-columns-not-cta.md`, `app/design_sync/component_matcher.py`, `app/design_sync/tests/test_icon_label_columns.py`, `app/design_sync/tests/test_social_section_content.py`, three `data/debug/6/assets/*.png`, `data/debug/6/expected.html`, `data/debug/fidelity_baseline.json` (+ the report if tracked).
- **SATISFIES**: AC 7.

---

## TESTING STRATEGY

### Unit Tests

`test_icon_label_columns.py`: matcher rules (tile routing for CTA/SOCIAL/HEADER types, standalone social, CTA without button, real CTAs, five non-tile shapes), tile HTML (centred 42px icon, design typography, no `<p>/<h*>/<div>`), label gap (6px; 0 without line-height), tree-bridge `HtmlSlot`, VLM guard, checked `_CTA_FAMILY_SLUGS` mapping.

### Integration Tests

Same file: the minimal Figma node-tree test through `analyze_layout` + `match_all` (precondition asserts the CTA typing it fixes); corpus invariants over every live case through the real converter (`_run_conversion` + `match_all` spy); c6 nav tiles compiled through `build_email_tree` + `TreeCompiler`. Plus `make snapshot-test`, `make converter-data-regression`, `test_social_section_content.py`, `test_fidelity_gate.py`, `make fidelity-gate`.

### Edge Cases

| Edge case | Verified by |
|---|---|
| CTA type, no button, not a tile | `test_cta_without_button_is_not_a_cta_component` |
| Real CTA, one or two buttons | `test_real_ctas_unchanged` |
| Tile shape with a button / icon 65px / label 40 chars / two images / no label | `test_non_tile_shapes_do_not_route_to_td` (5 params) |
| Standalone one-icon social link | `test_standalone_social_link_keeps_social_icons` |
| Nav row at the top of an email (HEADER type) | `test_header_typed_peel_tile_routes_to_td` |
| Unknown label line-height | `test_label_gap_zero_without_line_height` |
| VLM picks a CTA slug for a button-less section | `test_vlm_cta_slug_rejected_without_button` |
| Tree-bridge path | `test_tree_path_keeps_the_icon`, `test_c6_nav_tiles_compile_on_the_tree_path` |
| Placeholder or blank label | Not a tile (`[placeholder-label]`, `[blank-label]` params; M8) |
| Two labels | Gap above the first only, clamped at 0 (`test_two_labels_gap_above_first_only`) |
| Label that wraps to two lines | Gap overstated by one line (F3, docstring); labels are < 40 chars in ≥ 150px columns on the corpus, so not reachable there |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync/component_matcher.py app/design_sync/tests/test_icon_label_columns.py app/design_sync/tests/test_social_section_content.py`
- `uv run ruff check --no-fix app/design_sync/`
- `make types` (mypy + pyright), `make lint-numeric`, `make golden-conformance`

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_icon_label_columns.py app/design_sync/tests/test_component_matcher.py app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_social_section_content.py -q -p no:cacheprovider`
- `uv run pytest app/design_sync/tests/ app/components/tests/ -q -p no:cacheprovider` (S17: 3411 passed, 0 failed; do not set `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` here: it fails three `test_section_cache.py` tests by design, observed)

### Level 3: Integration / gates

- `make snapshot-test`, `make converter-data-regression`, `make fidelity-gate`
- `make test` (S15: 8900 passed) — restores of `app/ai/agents/*/skill-versions.yaml` are handled by `piv-commit`
- `make check-full` via `piv-validate`. No eval gate (no diff under `app/ai/agents/`).

### Level 4: Manual Validation

1. Open `.tmpscratch/ce9/nav_640.png` and `nav_375.png` regenerated on the branch (T10): one row of four icon+label tiles at 640px (64px tall), a clean stack at 375px.
2. Side-by-side at 600px: `.tmpscratch/fidelity/case6_side_by_side.png` from T9 against `Starbucks/manual_component_build.html:298-339`. The harness's 600px viewport wraps REWARDS to a second row (pre-existing R4); judge structure and presence, not the wrap.
3. `grep -ci "follow us" data/debug/6/expected.html` → 0.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: RED-first node-tree test (row of icon + short-label columns, no button frame) routes every column to the icon-label tile, none to a CTA-family slug.
- [ ] AC 2: Invariant over every live case (5–10 + reframe): a CTA-family slug implies the section holds a button; the VLM path cannot violate it.
- [ ] AC 3: Invariant over every live case: every icon node and label in an icon-label row reaches the converter HTML; the tiles also compile on the tree path.
- [ ] AC 4: Case 6: APP, ORDER, OFFERS, REWARDS and assets `2833:1457/1462/1467/1472` present, one 64px row at 640px, clean stack at 375px, no "Follow us".
- [ ] AC 5: Non-target cases byte-identical modulo whitespace; case-6 diff confined to sections 4–7.
- [ ] AC 6: Full-corpus A3 before/after (7 rows) reported; `make fidelity-gate` passes on base and head; case 6 re-stamped with every moved section named; the three icon assets committed.
- [ ] AC 7: Ladder unchanged from base; `make check-full` green on the committed head.
- [ ] AC 8: Mutation table (T7) in the report, both columns observed.
- [ ] AC 9: Ledger notes and three new entries added; no entry closed.

---

## COMPLETION CHECKLIST

- [ ] T1–T11 done in order, each VALIDATE run and recorded
- [ ] Report at `.claude/reports/ce-9-nav-columns-not-cta-report.md`, figures tagged observed/derived/expected and re-derived on the branch (not copied from this plan)
- [ ] Draft PR open; CI watched
- [ ] Spike worktree removed after merge: `git worktree remove .tmpscratch/ce9-spike` (it holds an untracked `.venv` symlink: `--force` only after checking `git -C .tmpscratch/ce9-spike status --short` shows nothing else)

---

## OPEN QUESTIONS / ASSUMPTIONS

None open. U1–U4 answered 2026-10-03. The one judgement left to the implementer is U4's stop rule, which the spike shows will not trigger (S9).

## NOTES

- Rejected: route to `navigation-bar` (the ticket's first suggestion). `_fills_nav` drops images and the seed is `hide` on mobile, so the ticket's own wrong-if ("labels come back but icons stay missing") would fire.
- Rejected: un-peel the nav row into one `column-layout-4` (closest to the hand build). It moves the ladder (c6 rendered 9 → 6, derived: 9 − 4 + 1) and is segmentation work; the peel-row composer already gives one row at 640px (S10).
- Rejected: tighten `_classify_by_position` (U1).
- Why the first gate attempt failed and the second passed: base's empty green boxes score high against a mostly flat green reference crop, so any content placed off by a few pixels scores lower than nothing. The 6px label offset alone cost OFFERS 0.0083. Placing the label at design y turns every nav section into a gain (S5 → S9). This is why the gap is derived from geometry rather than left to CE-6.
- The ticket estimated ~300–500 lines (brief); the spike is 106 source lines plus 415 test lines (observed, `git diff --stat`), with no renderer change.

## AMENDMENTS

- 2026-10-03 — implementation (`piv-implement`): report renamed to the plan slug (`ce-9-nav-columns-not-cta-report.md`, T10 and checklist updated) and tracked in the PR. T1 preflight ran after implementation; its Step 2b found one entry the Deferred Items table omits, `phase-53-d3-mammut-below-candidate-undercount` (matched on `layout_analyzer.py`), decision **avoid** (file untouched, U1). T2 RED: 14 failed, 5 of them on `ValueError` unpacking the stub's empty fill list rather than an assertion. T9 A3 "before" re-derived on the branch (base matcher swapped in, identical to `a3_before/scores.json`); base gate cited from main CI run 37063674884. The stamp names WIP commit `e2a0b56c`, folded by `piv-commit` (S19 precedent). `docs/converter-fidelity-ceiling.md` not appended (dated Track-G snapshot; CE-1/CE-3 precedent).
- 2026-10-03 — planning chat: user ratified U1–U4.
- 2026-10-03 — advisor pass: spike baseline/expected/assets marked reference-only in the port (T9 sole stamp); T5 uses the fixture script (S18); stamp-commit precedent recorded (S19); S9/S11 tagged derived-via-byte-identity; `make check-full` run on the spike (S20). Spike `2d4fbb4b` → `fb3b4beb`.
- 2026-10-03 — fresh code-reviewer pass on the spike (S17): F1, F2, F3, F4, F7 fixed and re-measured; F5 rejected (G3-neg); F6 folded into T9; F8 into the PR body. Spike commit `b5174bed` → `2d4fbb4b`.
- 2026-10-03 — user asked for 10/10 confidence with every risk addressed. Built and measured the spike (`b5174bed`); first gate attempt failed on `2833:1465` (S5) and was fixed by deriving the label gap from geometry (S6, S9); R2 fixed with `slot_type="attr"`; R3 fixed with a VLM guard; three pre-existing defects reproduced on base and ledgered (R4–R6); two collateral test needs found and folded in (R7 assets, R8 F5 test). Plan rewritten as a port of the spike.
