**Verdict: Request changes** (one Medium: an undocumented pattern violation). This is recorded as a comment because GitHub blocks a formal review from the PR's own author.

# PR #409 review: fix(design-sync): render social-section texts and dividers (T1)

**Head** c29122d87a8510d62e75be2a1e6bb3fddb833003 · **Base** main @ f26ee233dbda185ffbef677fba4f6c90e1a4cbb6

This is round 1, a fresh-context review. The live `origin/main` tip is `f26ee233` (observed, `git rev-parse origin/main` after `git fetch`), which equals `baseRefOid`. No earlier `pr-409-review*.md` exists, so the guarantees pass does not apply. The fix-mechanism pass was run on the pre-PR findings F1–F7 (`.claude/state/s9-t1/review-findings-pre-pr.md`), as the session asked.

## Summary

Social-classified sections used to render only their icon row. `_fills_social` now walks the section's column groups in design order and emits text and divider rows around a nested icon row, all inside the `social_links` attr slot. The template's "Follow us" label became the `social_label` slot. Icon-only sections keep it, and sections with design text empty it and collapse its row. The change is well scoped, and it uses the single existing HTML path: no new writer and no composite splice. Its tests run on the real `data/debug` corpus. All CI checks are green. One naming violation blocks, and five Low items follow.

## Issues

### Critical
None.

### High
None.

### Medium

- **R1 · Medium · `app/design_sync/component_matcher.py:2640`**
  - **Problem:** the new log event `design_sync.social.ungrouped_texts` has three parts. `.claude/references/logging-standard.md:36-39` says new events use the two-part form `domain.action_state` and that no new three-part names are added.
  - **Why it counts as a deviation:** it is not in the plan AMENDMENTS or in the report's Deviations, so it is undocumented. `app/design_sync/tests/test_social_section_content.py:189` asserts the name.
  - **Fix:** rename it to a two-part name, e.g. `design_sync.social_ungrouped_texts_skipped`, and update the test.

### Low

- **R2 · Low · `app/design_sync/component_matcher.py:2632`**
  - **Problem:** `if not groups: return None` runs before the F4 ungrouped-text log at `:2637`. A social section with no column groups and no content groups therefore still drops every text with no log line and keeps "Follow us".
  - **When it happens:** both group lists come back empty when all content sits at the section root or in a single child frame (`figma/layout_analyzer.py:1381`, `:2002-2004`).
  - **Why it is only Low:** the plan's Solution Statement step 1 chose "else nothing (today's behaviour)" for this case, so the drop itself is documented. What is missing is the log and a mention of this case in the closed entry's NARROWING note (`.agents/deferred-items.json:1243`).
  - **Fix:** log the texts in the zero-group case too, and add "sections with no column or content groups" to the note. The corpus does not reach this branch (every corpus social section has one column group; this is the report's probe, not re-run here).
- **R3 · Low · `app/design_sync/component_matcher.py:2581`, `:2654`**
  - **Problem (F3 mechanism):** on the image fallback, `icon_ids` holds every section image. The icon row anchors on the first of them in design order, so a non-icon image placed before a pre-icon label (logo → label → icons) pulls the icon row above the label.
  - **Corpus:** no corpus section has that shape. c10's logo precedes the icons with no text between them.
  - **Fix:** add this ordering symptom to `phase-53g-t1-social-non-icon-images-as-icons` (`.agents/deferred-items.json:1263`). It closes with that entry.
- **R4 · Low · `.claude/reports/t1-social-section-column-content-report.md:5`, `:19`, `:22`**
  - **Problem:** the status lines are stale. They say "Branch head: `71b9db89`", "the session-3 re-score is pending" and "`make check-full` … at `71b9db89` is running". Later sections of the same report record the re-score (at `:128`) and the `c29122d8` gate (at `:81`).
  - **Fix:** update the three lines. The report is untracked, so nothing ships wrong.
- **R5 · Low · PR body § A3; `.claude/state/s9-t1/a3/after/scores.json`**
  - **What is right:** every A3 figure in the PR body is correct. The "after" column matches `scratchpad/a3-s3/after-71b9db89/scores.json` (observed), and the "before" column matches `.claude/state/s9-t1/a3/before/scores.json` (observed).
  - **Problem:** the durable copy at `.claude/state/s9-t1/a3/after/scores.json` still holds the superseded session-2 numbers (c6 0.8058, c9 0.715), and the only file that backs the published "after" column is in a session scratch directory. The PR body also presents "`f26ee233` vs `71b9db89`" without saying that "before" is the session-2 run of `f26ee233`.
  - **Fix:** copy the session-3 `scores.json` into `.claude/state/s9-t1/a3/` and add "before = session-2 run" to the PR body.
- **R6 · Low · `.agents/deferred-items.json:1228`, `:1269`, `:1285`**
  - **Problem:** three `pending` SHA placeholders remain (`closed_commit` once, `introduced_commit` twice).
  - **Why it is only Low:** this is expected under the stamp-after-squash convention, and the PR body and report both say so.
  - **Fix:** stamp them with the squash SHA after merge (`/deferred-items`).

## Fix-mechanism pass (F1–F7): what each fix newly permits

- **F1, collapse on an explicit empty fill (`component_renderer.py:61`, `:1025-1027`): clean.**
  - The collapse runs only for `social_label` (the only member of `_COLLAPSE_ON_EMPTY_FILL`), and only after `_fill_text_slot` has emptied the cell. That means `_collapse_blanked_slot`'s solo-row regex matches, and the label `<tr>` is dropped.
  - `_cell` padding then lands on the first remaining `padding:`, which is the `social_links` container `<td>` (`padding: 0 0 24px`). Per-side longhands land on the same `<td>` through `_upsert_first_td_css_prop`. Both are intended, and c8 `data/debug/8/expected.html` shows `padding:40px 40px 40px 40px` on that cell.
  - With no `_cell` override (c6 s7), the section loses the label's 24px top padding and keeps `0 0 24px`. This is documented in the report's session-3 audit.
  - The fill-rate warning does not fire: an icon-only section fills 1 of 2 slots, 50%, and the threshold is `< 0.5` (`component_renderer.py:634`).
  - `footer-social` also maps to `_fills_social` (`component_matcher.py:591`) but has no `social_label` slot, so the collapse is a no-op there.
- **F2, `None` for every empty text fill (`tree_bridge.py:174-180`): clean.**
  - Both claims in the new comment hold. `validate_tree_against_manifest` checks only that slot keys are known, never `required` (`app/components/tree_schema.py:124-160`). TreeCompiler fills only the keys it receives (`app/components/tree_compiler.py:219`), so seed content survives a missing key.
  - Tag-only fills (`"<br> "`) also map to `None`, and a test pins that (`test_bridge_roundtrip.py`).
  - The ledger's "e.g. 'Shop Now'" (`deferred-items.json:1286`) is `derived` from the seed markup: no tree-path run on a CTA case is recorded. Only c9 has run through the tree path since F2.
- **F3, `icon_ids` anchor: one Low, R3.** On the button path, `icon_ids` holds `node_id` and `icon_node_id` only for buttons that produced a cell, so either the button or its icon image anchors the row. That is correct.
- **F4, multi-group stacking.** Side-by-side column groups become stacked rows in a single-cell slot table. This is documented in AMENDMENTS, and it is not reached on the corpus. The zero-group gap is R2.
- **F5, `content_order` schema and serialisation: clean.**
  - The field defaults to `()`, is omitted from JSON when empty and reads back as `()` when absent.
  - The schema adds it as an optional array. `additionalProperties` is not affected, and `test_content_order_passes_schema` validates it.
  - It is threaded through `from_content_group` and `to_content_group`. The only consumer is `_social_column_rows`, because `_ordered_column_elements` reads `content_order`.
- **F6 and F7: clean.** The byte-identity literal and the "Follow us" render test are present (`test_social_section_content.py:104-141`). The manifest lists `social_label` (`component_manifest.yaml:1151`).

## Numbers pass

| Figure (PR body / report) | Source | Tag / check |
|---|---|---|
| `make check-full` exit 0, 8512 passed / 0 failed / 115 skipped, vitest 780 | `.claude/last-gate.json` (head `c29122d8…`, `short_gate` false, `dirty` false) and gate log line 10616 | observed from the record; not re-run in this review |
| golden-conformance 26 passed / 9 skipped; ladder 6 passed | gate log `:10657`, `:6189-6194` | observed from the log |
| `test_social_section_content.py` 14 passed; bridge file 19 passed | this review: 33 passed (= 14 + 19) | observed |
| `make snapshot-test` 34 passed / 10 skipped / 1 xfailed | this review | observed |
| baselines c6 86, c8 59, c9 56, c10 59 lines; c5 and c7 untouched | `git diff --stat origin/main...HEAD` (c6 60+26, c8 42+17, c9 40+16, c10 39+20) | observed; sums derived |
| A3 table (6 rows) | the two `scores.json` files above; every value matches | observed; deltas derived (e.g. c6 0.8132 − 0.8203 = −0.0071) |
| "same converter code as this commit" (`71b9db89` vs `c29122d8`) | `git diff --stat 71b9db89 c29122d8` touches only the ledger, the plan and the test file | derived |
| Report line references (`:61`, `:1026`, `:2553`, `:2567`, `:2581`, `:2606`, `:2640`, `:2654`, `tree_bridge.py:175`, `layout_analyzer.py:198`, `:2028`, `email_design_document.py:978`) | read at head | all match |
| RED evidence per test | the report's session records | accepted as recorded; not re-run (it would need the fix reverted) |

## Validation

| Check | Result | Tag |
|---|---|---|
| `make check-full` at `c29122d8` | exit 0; pytest 8512 / 0 / 115; vitest 780 | observed (`.claude/last-gate.json`) |
| `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run pytest app/design_sync/tests/test_social_section_content.py app/design_sync/tests/test_bridge_roundtrip.py -q` | 33 passed | observed (this review) |
| `make snapshot-test` | 34 passed, 10 skipped, 1 xfailed | observed (this review) |
| `gh pr checks 409` at 10:56Z | all 14 checks pass (Backend, Frontend, CodeQL ×2, Semgrep ×2, Trivy, E2E, Integration, Migrations ×2, SDK drift, Commit lint, Ready) | observed |
| Code-scanning alerts, `refs/pull/409/merge`, state open | 0, read at 10:56Z after Semgrep and CodeQL completed | observed |
| Working tree after the runs | unchanged (only the untracked report) | observed |

## Deferred items touching this diff

| id | status | decision |
|---|---|---|
| `phase-53g-g11-social-section-drops-column-content` | closed by this PR | close stands; widen the NARROWING note per R2 |
| `phase-53g-t1-social-non-icon-images-as-icons` | new | add the R3 ordering symptom |
| `phase-53g-t1-tree-path-social-label-default` | new | fine as written; "Shop Now" is derived (see F2) |
| `phase-53g-g11-contentgroup-column-divider-gap` | deferred | carry forward; the social path now reads content groups but not dividers, as the plan states |
| `phase-53g-g4-tree-html-slot-row-shape` | deferred | avoid; this PR uses an attr fill, not a composite |
| `phase-53g6-card-tree-path-text-only` | deferred | unaffected; its `_fill_to_slot_value` text branch changed only for empty results |

## What is good

- It uses the single HTML path, with an attr fill inside the existing slot. There is no parallel writer and no widening of the shared splice regex. The rejection of the composite route is argued in the plan.
- The output is table-only. Each new text `<td>` carries `font-family`, `font-size`, `color`, `line-height` and `mso-line-height-rule:exactly`. The nested icon table has `role="presentation"`. Escaping goes through the existing `_column_text_row` and `html.escape` paths.
- Icon-only output is pinned byte for byte against a literal captured from `f26ee233`.
- The corpus tests use real fixtures, and the edge cases the corpus cannot reach are driven from real c6 and c8 sections rather than synthetic HTML.
- The A3 trade was re-scored after F1 and ratified. Non-targets c5 and c7 are flat on every band, and the ladder did not move.

## Recommendation

Request changes for R1: a one-line rename plus the test assertion. R2–R5 are small ledger and report edits that can ride on the same fix commit. R6 happens after merge. Next step: `piv-fix-review-findings` on this file.
