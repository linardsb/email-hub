# Fix: social-classified sections render their text and divider content (T1)

The following plan should be complete, but validate codebase patterns and task sanity before implementing.
Base: `origin/main` `f26ee233` (observed, `git log -1 origin/main`). Branch `fix/t1-social-section-column-content`.
Cycle: `.claude/skills/converter-fix/SKILL.md` (RED-first, audited regen, non-target identity, ladder, full-corpus A3).

## Feature Description

A section classified `SOCIAL` renders only its icon row. `_fills_social` (`app/design_sync/component_matcher.py:2530`)
builds one `<tr>` of icon cells for the `social_links` slot and never looks at the section's texts or in-column
dividers, so footer legal text ("© 2025 Slat…", "Privacy Policy | Unsubscribe", "Ferrari N.V. …") and c8's
`#373737` divider vanish from the email. This is also handoff ticket T1, the first ticket through the new PIV loop.

## User Story

As a marketer converting a Figma design, I want the footer's legal text and dividers that sit beside the social
icons to appear in the email, so that the email carries the unsubscribe / legal copy the design has.

## Problem Statement

Observed on this head (subagent `dump_social.py`, `DESIGN_SYNC__SECTION_CACHE_ENABLED=false`, output byte-equal
to each `expected.html`): every SOCIAL section in the corpus is matched to `social-icons` and loses every design
text. Rows below are observed from that dump.

| Case | Section (node) | Design order (top → bottom) | Dropped today |
|---|---|---|---|
| c6 | s7 `2833:1470` (peeled CTA-row column) | img 1472 → text 1474 "REWARDS" | 1474 |
| c6 | s8 `2833:1475` | 4 icons → text 1488 "Ref: 26-6-NWSL…" → img 1490 | 1488 |
| c8 | s10 `2833:2348` | 5 icons → text 2363 → divider 2365 → text 2367 "Ferrari N.V. …" | 2363, 2365, 2367 |
| c9 | s9 `2833:2149` | text 2153 "FOLLOW US" → 5 icons → 2166 (©) → 2168 (Privacy…) → 2170 "Unsubscribe" | all 4 texts |
| c10 | s14 `2833:1270` | logo 1274 → 5 icons → 1287 "Privacy Policy \| Unsubscribe" → 1289 → 1291 (address) | 3 texts |

c5 and c7 have no SOCIAL section (observed). `footer-social` is never selected by the matcher (registry key only,
`component_matcher.py:591`; type→slug at `:305-306`).

## Solution Statement

User decision (2026-09-28, AskUserQuestion): fix now as T1, **render path** (not re-classification).

Route chosen: **`_fills_social` emits the whole ordered column itself** inside the `social_links` slot.
`social_links` is `slot_type="attr"`; its value replaces the inner rows of `<table data-slot="social_links">`
verbatim (`_fills_social` docstring, `component_matcher.py:2537-2542`). So:

1. Take the section's ordered content: `_ordered_column_elements(column_groups[0])` (`:1083`) when
   `column_groups` exist; else a `ColumnGroup` built from `child_content_groups` flattened in order (c6 s7,
   mirroring `_build_column_fills_from_content_groups`, `:2698`); else nothing (today's behaviour).
2. Walk it. The **first** `ImagePlaceholder` position emits the icon row (built exactly as today from
   `section.buttons` / `section.images`); later images are skipped (already inside the icon row). Each
   `TextBlock` → `_column_text_row` (`:745`), each `ColumnDivider` → `_column_divider_row` (`:993`); buttons are
   empty in all four sections (observed) and are left out.
3. When at least one text/divider row exists, the icon row is nested so every row of the slot table has one
   cell: `<tr><td align="center"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>…icon
   cells…</tr></table></td></tr>`. When no text/divider row exists, return today's `<tr>…cells…</tr>` unchanged
   (byte-identity for any icon-only section, including all `TestFillsSocial` cases).

Rejected: a composite row spliced after `social_links` (`CompositeSlot`, `:58`). `_splice_rows_after_slot`
anchors on `<td data-slot=…>` only (`app/design_sync/component_renderer.py:1328`), the social template puts the
slot on a `<table>`, widening that shared regex touches every composite; composites are dropped on the tree path
(`app/design_sync/tree_bridge.py:204-214`); and pre-icon text (c9) would need a second, before-splice anchor.

## Out of Scope / Non-Goals

- Non-icon images rendered as social icons (c6 1490 bottom image, c10 logo 1274 rendered as 32×32 "Social icon")
  → new ledger entry (Task 7), not fixed here. Rendering them from `content_order` would duplicate them.
- Buttons inside social sections: empty on the corpus (observed); not rendered by this change.
- `footer-social.html` (unselected, and its markup has an unclosed Instagram `<td>`): not touched.
- Re-segmentation / classification (`layout_analyzer.py:980`): not touched; the ladder must not move.
- Icon alt/href quality (`href="#"`, alt "Social icon"): unchanged.

## Feature Metadata

**Feature Type**: Bug Fix · **Complexity**: Medium · **Systems**: design_sync component matcher (default render
path; tree-bridge path also receives the attr value) · **Dependencies**: none new.

## Related Work

**Implements**: handoff T1 (`.claude/state/s8-handoff/HANDOFF-main-checkout.md` "Open, in order" 3); plan
`.agents/plans/ai-layer-import.md` §S9 last row. **Back-references**: G11 item 1 in-column dividers
(`_column_divider_row`), F10 `content_order`, B2 `_wrap_column_table`. **Forward-references**: none yet.

## Deferred Items Touching This Plan

Grep run 2026-09-28 on `component_matcher.py`, `component_renderer.py`, `layout_analyzer.py`, `social`,
`footer`, `legal` (subagent, observed).

| id | match | decision | why |
|----|-------|----------|-----|
| `phase-53g-g11-social-section-drops-column-content` | code_refs `component_matcher.py:2528` (_fills_social) | **close** | closes_when route (a): social section renders its column content. Buttons named in the entry are unexercised by the corpus: say so when closing; fix drifted ref `:2528` → `:2530` |
| `phase-53g-g11-contentgroup-column-divider-gap` | ContentGroup has no dividers | carry forward | c6 s7 (the only content-group social section) has no divider; unchanged |
| `phase-53g-g4-tree-html-slot-row-shape` | tree path composites | avoid | this plan uses an attr fill, not a composite |
| `phase-53-d3-mammut-below-candidate-undercount` | layout_analyzer (c10) | avoid | no segmentation change |

## CONTEXT REFERENCES

### Files to read before implementing

- `app/design_sync/component_matcher.py:2530-2589` `_fills_social`: the function to change.
- `:1233-1264` `_build_column_fill_html`: the row-walk pattern to mirror (ordered elements, placeholder skip).
- `:745` `_column_text_row`, `:993` `_column_divider_row`, `:1063` `_wrap_column_table`, `:1083`
  `_ordered_column_elements`, `:2698-2720` `_build_column_fills_from_content_groups` (ContentGroup → ColumnGroup).
- `app/design_sync/figma/layout_analyzer.py:157-178` `ColumnGroup` fields (`dividers`, `content_order`).
- `email-templates/components/social-icons.html`: slot on `<table data-slot="social_links">`; hardcoded
  `social-label` "Follow us" `<td>` (not a slot).
- `app/design_sync/tests/test_component_matcher.py:1858` `TestFillsSocial`: existing unit tests, must stay green.
- `app/design_sync/tests/test_snapshot_regression.py:211-217` `_run_conversion`: real-fixture entry point.
- `app/design_sync/tree_bridge.py:199-202`: attr fill → `HtmlSlot(html=value)` on the tree path.

### New Files to Create

- `app/design_sync/tests/test_social_section_content.py`: RED-first corpus tests (Task 1).

### Patterns to Follow

- Section chunk extraction: `<!-- section:section_{idx} -->` … `<!-- /section:section_{idx} -->`
  (`component_renderer.py:2389-2392`).
- Logging: none needed; `_fills_social` logs nothing today.
- Table-only HTML: every emitted row is `<tr><td>`; nested table carries `role="presentation"` (G1 conformance).

---

## STEP-BY-STEP TASKS

### Task 0: Preflight
- **IMPLEMENT**: `/preflight-check .agents/plans/t1-social-section-column-content.md`; record base `git rev-parse origin/main`.
- **VALIDATE**: preflight table printed; base = `f26ee233…` (expected).
- **SATISFIES**: process.

### Task 1: CREATE `app/design_sync/tests/test_social_section_content.py` (RED first)
- **IMPLEMENT**: drive `_run_conversion(case)` (import from `test_snapshot_regression` or copy its 4 calls),
  extract the section chunk, assert:
  - c8 `section_10` contains "Ferrari N.V." and "automatically generated email", and a `border-top` rule row
    between them (divider 2365; colour as emitted by `_column_divider_row`);
  - c9 `section_9` contains "Unsubscribe", "Privacy Policy", and "FOLLOW US" appears **before** the first
    `<img` of the icon row while "Unsubscribe" appears **after** the last icon `<img`;
  - c10 `section_14` contains "Privacy Policy" and "Mammut Sports Group";
  - c6 `section_8` contains "26-6-NWSL"; c6 `section_7` contains "REWARDS";
  - every row in the `social_links` table body is single-cell when text rows are present (no `<tr>` has a
    sibling `<td>` next to a text `<td>`): assert the icon cells sit inside a nested `<table role="presentation">`.
  Plus unit tests in the same file on `_fills_social` with a real-fixture section (load c8 via
  `load_structure_from_json`), asserting icon-only sections return exactly the pre-fix `<tr>…</tr>` value.
- **GOTCHA**: assertions must be impossible on old code (skill step 1). Use real fixtures only.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_social_section_content.py -q` → corpus tests FAIL on
  the assertion (not ImportError); icon-only identity test PASSES. Keep the failing output for the report.
- **SATISFIES**: AC 1–4.

### Task 2: UPDATE `_fills_social` in `app/design_sync/component_matcher.py`
- **IMPLEMENT**: per Solution Statement 1–3. Keep the icon-cell builder unchanged (extract to a local helper
  `_social_icon_cells(section, image_urls) -> list[str]` only if needed to reuse; single caller otherwise).
  Ordered source: `section.column_groups[0]` if present; elif `section.child_content_groups` → ColumnGroup per
  `:2705-2712` pattern (concatenate groups' elements in order); else `[]`. Skip `_is_placeholder` texts.
- **GOTCHA**: do NOT render `ImagePlaceholder`s from the ordered list as image rows (duplicates, see Out of
  Scope). A section with texts but zero icon cells: keep returning `[]` as today (the `if not cells` guards).
  **Label**: see Q1; implement the option ratified at the plan gate.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_social_section_content.py app/design_sync/tests/test_component_matcher.py -q`
  green; `uv run ruff check --no-fix app/design_sync/component_matcher.py`; `uv run ruff format --check …`;
  `uv run mypy app/design_sync/component_matcher.py`; `uv run pyright app/design_sync/component_matcher.py`.
- **SATISFIES**: AC 1–5.

### Task 3: Regenerate and audit baselines (skill step 3)
- **IMPLEMENT**: `references/baselines-and-gates.md` § Regen-and-audit: capture all six cases to scratch with
  `scripts/snapshot-capture.py <case> --output <tmp>`; diff vs committed `expected.html`; trace every changed
  line to Task 2; `--overwrite` only c6, c8, c9, c10.
- **GOTCHA**: never `make snapshot-capture` (hardcoded `--overwrite`); c8 whitespace churn is not a change.
- **VALIDATE**: c5 and c7 scratch diffs empty under `--ignore-all-space`; `make snapshot-test` green after overwrite.
- **SATISFIES**: AC 6.

### Task 4: Ladder
- **VALIDATE**: `git diff origin/main -- data/debug/ladder_snapshot.json` empty;
  `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder -q` green. Any move = stop.
- **SATISFIES**: AC 7.

### Task 5: Full-corpus A3 (advisory, skill step 5, `references/a3-scoring.md`)
- **IMPLEMENT**: copy gitignored reference PNGs/assets into the worktree per the reference; score before (fix
  stashed via a tagged stash or WIP commit, never bare `git stash`) and after:
  `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`.
- **GOTCHA**: six rows or it is a short run. Jitter rule: per-section drop on a target = scorer artefact until
  composites/geometry say otherwise. A non-target (c5/c7) move beyond jitter, or a per-band trade on a target,
  stops for user ratification before commit.
- **VALIDATE**: before/after table, 6 rows (observed).
- **SATISFIES**: AC 8.

### Task 6: Tree-bridge path check
- **IMPLEMENT**: run c8 with `DESIGN_SYNC__TREE_BRIDGE_ENABLED=true` through `_run_conversion`; confirm no
  `CompilationError`/fallback and the legal text is present (attr → `HtmlSlot`, `tree_bridge.py:199-202`).
  If the tree compile rejects the value, degrade on the tree path only and ledger it (skill § 7 "Tree-path deferral").
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_bridge_roundtrip.py -q` green.
- **SATISFIES**: AC 9.

### Task 7: Ledger (deferred-items skill)
- **IMPLEMENT**: close `phase-53g-g11-social-section-drops-column-content` (`closed_commit: pending`, note
  buttons unexercised, ref `:2530`); add known-bug entry `t1-social-section-non-icon-images-as-icons` (c6 1490,
  c10 1274 rendered as 32×32 social icons; code_ref `_fills_social` images fallback). Edit line by line (no
  `json.dump` re-serialise).
- **VALIDATE**: `python3 -c "import json;json.load(open('.agents/deferred-items.json'))"`; `git diff --stat` on
  the ledger shows only the touched entries.
- **SATISFIES**: AC 10.

### Task 8: Validate and hand off
- **IMPLEMENT**: `piv-validate` (`make check-full` via `record-gate.sh`) → `piv-commit` → `piv-create-pr` (draft).
- **VALIDATE**: `.claude/last-gate.json` head = commit, exit 0, short_gate false.

---

## TESTING STRATEGY

- **Unit**: `_fills_social` icon-only identity (existing `TestFillsSocial` + one new); ordered output on a real
  c8 section.
- **Corpus (real fixtures, CI-gated)**: Task 1 file runs in CI because the six cases' inputs are tracked
  (`references/baselines-and-gates.md` § What runs in CI, observed on run 29764095476). `test_snapshot_matches`
  locks the regenerated baselines.
- **Edge cases**: text before icons (c9, Task 1); divider between texts (c8, Task 1); content-group source
  (c6 s7, Task 1); icon-only section unchanged (Task 1 unit); section with texts but no resolvable icon →
  `[]` as today (Task 1 unit, synthetic `EmailSection` built from a real c8 section with images stripped).

## VALIDATION COMMANDS

1. `uv run ruff check --no-fix <files>` · `uv run ruff format --check <files>` · `make types`
2. `uv run pytest app/design_sync/tests/ app/components/tests/ -q`
3. `make snapshot-test` · `make converter-data-regression` · `make golden-conformance` · `make lint-numeric`
4. `piv-validate` → `make check-full` (final gate)

## ACCEPTANCE CRITERIA

1. c8 s10 renders texts 2363 and 2367 and divider 2365 in design order (Task 1 test).
2. c9 s9 renders all four texts; "FOLLOW US" above the icon row, the other three below (Task 1).
3. c10 s14 renders texts 1287, 1289, 1291 (Task 1).
4. c6 s8 renders text 1488; c6 s7 renders "REWARDS" (Task 1).
5. Every `social_links` row is single-cell when text rows are present; icon-only sections byte-identical to today.
6. Baselines regenerated for c6/c8/c9/c10 only, every diff line traced; c5 and c7 byte-identical (modulo ws).
7. Ladder unchanged from base.
8. A3 before/after for all six cases reported; any non-target regression or target trade ratified by the user.
9. Tree-bridge path compiles c8 without fallback.
10. Ledger: entry closed, non-icon-image entry added.
11. `make check-full` green on the commit head (`record-gate.sh`).

## OPEN QUESTIONS / ASSUMPTIONS

- **Q1 (plan gate, user decides): the template's hardcoded "Follow us" label.** It sits in a non-slot `<td>`
  above the icons. c9's design has its own "FOLLOW US" above the icons, so after this fix c9 shows both; c6/c8/c10
  designs have no such label at all.
  - **L1 (recommended)**: add `data-slot="social_label"` to the label `<td>` in `social-icons.html` and have
    `_fills_social` fill it empty when the section carries design text (the design owns its labels); icon-only
    sections keep "Follow us". Cost: a component-template edit (check seeds / golden conformance), and the empty
    label cell keeps its `24px 0 16px` padding.
  - **L2**: keep the label as is; accept "Follow us" + "FOLLOW US" on c9. No template change.
  - **L3**: render pre-icon design text only by replacing the label (needs the L1 slot plus design typography on
    that cell); post-icon text unchanged. More code, narrower gain.
- A1: the slot table's auto width (`align="center"`, no width) grows to fit long legal text, capped by the
  parent cell. Expected, confirmed at Task 3 audit and the A3 composites.
- A2: `_column_text_row` carries design typography and alignment; section backgrounds are applied by token
  overrides (observed in scratch chunks: c8 `#181818`, c9 `#2B2B2B`, c6 s7 `#296042`), so white text is visible.

## NOTES

Route comparison: attr-fill (chosen) keeps grid validity via the nested icon table, needs no renderer or
template change for the text itself, and reaches the tree path; composite would widen a shared splice regex,
skip the tree path, and need a before-anchor for c9. Non-targets are only c5 and c7, a thin guard; the unit
identity test on icon-only sections adds a second one.

## AMENDMENTS

- 2026-09-28 — Plan gate: user approved; Q1 ratified **L1** (template `social-label` cell gets `data-slot="social_label"`, filled empty when the section carries design text). Task 2 implements L1; Files to modify gains `email-templates/components/social-icons.html`.
- 2026-09-28 (session 3) — Pre-PR review triage (AskUserQuestion): user chose to **fix all of F1–F7** from `.claude/state/s9-t1/review-findings-pre-pr.md` on this branch. Scope changes:
  - **F1**: an explicit empty `social_label` fill collapses the label row like an unfilled blanked slot; the design's top padding moves to the next row. Supersedes the L1 note that the empty label cell keeps its padding. Moves c6/c8/c9/c10 baselines and A3 again; the session-2 A3 ratification figures are void and are re-scored.
  - **F2**: `tree_bridge.py` no longer turns an empty text fill into the literal `"text"`; it returns `None` (TextSlot/HtmlSlot need `min_length=1`), so the tree path keeps the seed "Follow us" (test asserts no placeholder text; the seed label is ledgered as `phase-53g-t1-tree-path-social-label-default`). Empty CTA label fills on the tree path likewise keep their seed label.
  - **F3**: a `ButtonElement` that produced an icon cell anchors the icon row. Supersedes Out-of-Scope "buttons … not rendered" only for icon buttons; other buttons in a social section stay unrendered (ledger note).
  - **F4**: `_social_column_rows` walks every column group in order (side-by-side groups become stacked rows); `section.texts` outside every group are logged, not placed (no position data).
  - **F5**: `ContentGroup` gains `content_order` (design tree order, built by `_column_content_order`), serialised on `DocumentContentGroup` and in `$defs/content_group` of `data/schemas/email-design-document-v1.json`; only the social path consumes it (`_build_column_fills_from_content_groups` unchanged).
  - **F6**: byte-identity test against the `f26ee233` icon-only literal; test that an icon-only section keeps "Follow us" (RED-first post-hoc by removing `social_label` from `_PRESERVE_UNFILLED_SLOTS`); tests for F1–F5.
  - **F7**: `app/components/data/component_manifest.yaml` social-icons lists `social_label`; closed ledger entry gains a narrowing note (non-icon buttons still dropped).
  - Files added to "modify": `app/design_sync/tree_bridge.py`, `app/design_sync/figma/layout_analyzer.py`, `app/design_sync/email_design_document.py`, `data/schemas/email-design-document-v1.json`, `app/components/data/component_manifest.yaml`, plus their tests. F3/F4/F5 are not exercised by the corpus (observed probe: every social section has one column group, no ungrouped texts, no buttons) and claim no corpus change.
- 2026-09-28 (session 3, pre-commit) — Divergences from the tasks above, as shipped (report `.claude/reports/t1-social-section-column-content-report.md` § Deviations):
  - Task 2 also changed `app/design_sync/component_renderer.py`: `social_label` in `_PRESERVE_UNFILLED_SLOTS` (icon-only sections keep "Follow us") and `_COLLAPSE_ON_EMPTY_FILL` (F1).
  - Task 0 `/preflight-check` was not run as a separate step; its deferred-items grep ran at plan time.
  - Task 7: the new entry id is `phase-53g-t1-social-non-icon-images-as-icons` (schema prefix), code_ref `component_matcher.py:2576`; the closed entry's `:2528` code_ref was left as is (the skill's close step changes no other field). A third entry, `phase-53g-t1-tree-path-social-label-default`, was added for F2.
  - A3 trades ratified by the user at `71b9db89`: c6 full_image 0.8203 → 0.8132, section_min 0.4772 → 0.4661; c9 section_min 0.4479 → 0.3033 (observed, report § A3).
