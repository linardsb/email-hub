# Implementation Report — T1: social-classified sections render their text and divider content

**Plan**: `.agents/plans/t1-social-section-column-content.md`   **Branch**: `fix/t1-social-section-column-content`   **Status**: COMPLETE (A3 trades ratified 2026-09-28; gate below)

Base: `origin/main` `f26ee233` (observed, `git log -1 origin/main`, 2026-09-28). PR #409 commits: `c29122d8` (the three session-2/3 `chore(wip):` commits `18598920`, `027bcfdf`, `71b9db89` folded by `piv-commit`) and `4ec80659` (review round 1: R1, R2). All figures below are from runs on this branch on 2026-09-28 unless tagged otherwise.

## Summary

A section classified `SOCIAL` used to render only its icon row: `_fills_social` never read the section's texts or in-column dividers, so footer legal copy ("Ferrari N.V. …", "Privacy Policy | Unsubscribe", "© …") and the c8 `#373737` divider were dropped. `_fills_social` now walks the section's column groups in design order and emits text and divider rows around the icon row inside the `social_links` attr slot. The icon row is nested in its own `<table role="presentation">` so each row of the slot table stays a single cell. Icon-only sections return the unchanged single `<tr>` of icon cells. Per plan amendment L1, the template's hardcoded "Follow us" label is now a `social_label` slot. When the design carries its own text, the label is filled empty and, since the session-3 review fix F1, its row collapses.

## Tasks completed

- Task 0, preflight: base recorded as `f26ee233`. The deferred-items grep ran at plan time (table in the plan). `/preflight-check` was not run as a separate step (see Deviations).
- Task 1, RED-first corpus and unit tests: `app/design_sync/tests/test_social_section_content.py` (CREATE).
- Task 2, `_fills_social` column walk: `app/design_sync/component_matcher.py` (UPDATE). The helper `_social_column_rows(section, icon_row, icon_ids)` returns `None` when there is no text or divider row. `_fills_social` then emits `SlotFill("social_label", "")` plus the column HTML.
- Task 2 / amendment L1, label slot: `email-templates/components/social-icons.html` (UPDATE; `data-slot="social_label"` on the `social-label` `<td>`). `app/design_sync/component_renderer.py` (UPDATE; `social_label` added to `_PRESERVE_UNFILLED_SLOTS`; see Deviations).
- Task 3, audited baseline regen: `data/debug/{6,8,9,10}/expected.html` (UPDATE), in session 2 and again in session 3. c5 and c7 were not overwritten.
- Task 4, ladder: no change to `data/debug/ladder_snapshot.json`.
- Task 5, full-corpus A3: scored in session 2 and re-scored in session 3 at `71b9db89` (table below; scores saved to `.claude/state/s9-t1/a3/after-s3-71b9db89/`).
- Task 6, tree-bridge check: c8 and c9 run with the tree bridge on.
- Task 7, ledger: `.agents/deferred-items.json` (UPDATE; see Ledger).
- Task 8, `piv-validate`: `make check-full` via `record-gate.sh` green at `c29122d8` and re-run at `4ec80659` (Validation results). Draft PR #409 opened; CI flipped it to ready at 10:54:54Z with all 14 checks passing (observed, PR timeline and `gh pr checks 409`).

## Tests added

`app/design_sync/tests/test_social_section_content.py`, 15 tests (observed, `pytest` 15 passed at `4ec80659`): 7 from session 2, 6 from the session-3 review fixes, `test_texts_without_any_icon_render_nothing` added at commit time, and `test_texts_without_any_group_are_logged` from review round 1. All run the real converter on the tracked `data/debug` cases through `test_snapshot_regression._run_conversion`, or drive `_fills_social` with real c6/c8/c9 sections taken from that run. Session-3 tests are listed under Review fixes.

| Test (session 2) | Asserts | AC |
|---|---|---|
| `test_c8_footer_keeps_legal_texts_and_divider_in_order` | c8 `section_10`: last icon `<img` < "automatically generated email" < `border-top:1px solid #373737` < "Ferrari N.V." | 1 |
| `test_c9_label_above_icons_legal_below` | c9 `section_9`: "FOLLOW US" before the first icon; "Privacy Policy" and "Unsubscribe" after the last icon | 2 |
| `test_c9_template_label_blanked_when_design_has_text` | c9 `section_9` has no "Follow us" | L1 |
| `test_c10_footer_keeps_legal_texts` | c10 `section_14` has "Privacy Policy" and "Mammut Sports Group" | 3 |
| `test_c6_footer_and_peeled_column_keep_texts` | c6 `section_8` has "26-6-NWSL"; `section_7` has "REWARDS" | 4 |
| `test_icon_row_is_nested_when_text_rows_present` | c8 `social_links` value opens with the nested presentation table; every top-level row is one cell | 5 |
| `TestFillsSocialIconOnly::test_icon_only_section_output_unchanged` | c8 section with texts and dividers stripped: one `social_links` fill equal to the pre-T1 literal (byte check since F6) | 5 |

Session-2 results:
- RED on unchanged code (observed, `uv run pytest app/design_sync/tests/test_social_section_content.py`): 6 failed on assertions, 1 passed (the icon-only identity test, as the plan expects).
- After the fix (observed, same command): 7 passed.
- With `app/design_sync/tests/test_component_matcher.py` (includes the existing `TestFillsSocial`) (observed): 150 passed.

## Review fixes (session 3, 2026-09-28)

The pre-PR code review at `027bcfdf` (`.claude/state/s9-t1/review-findings-pre-pr.md`) raised F1–F7 (3 Medium, 4 Low). The user triaged them through AskUserQuestion and chose to fix all seven on this branch (plan AMENDMENTS, session 3). Every fact in this table is observed this session. Line numbers are at `71b9db89`.

| # | What changed | Test(s) that pin it | RED evidence |
|---|---|---|---|
| F1 | `component_renderer.py:61` adds `_COLLAPSE_ON_EMPTY_FILL = frozenset({"social_label"})`. At `:1026`, after `_blank_unfilled_text_slots`, an explicit empty fill on those slots calls `_collapse_blanked_slot`, which drops the label row. The design `_cell` padding override now lands on the `social_links` cell. | `test_blanked_label_row_collapses_and_design_padding_moves_down` (c8 `section_10`) | RED on `027bcfdf`: `'data-slot="social_label"'` present |
| F2 | `tree_bridge.py:175` `_fill_to_slot_value` returns `None` for an empty text fill, because `TextSlot`/`HtmlSlot` need `min_length=1`. The tree path now shows the seed "Follow us" instead of the literal word "text". | `test_bridge_roundtrip.py:593` `test_empty_text_fill_is_skipped_not_placeholder`, `:605` `test_c9_tree_path_social_label_has_no_placeholder` | 2 RED on unchanged code. After: 19 passed in that file, 97 passed for `-k "tree or bridge"` |
| F3 | `_fills_social` records `icon_ids` (`component_matcher.py:2553`, `:2567`, `:2581`): the button `node_id` and `icon_node_id` that produced an icon cell, or the fallback image ids. `_social_column_rows(section, icon_row, icon_ids)` (`:2606`) anchors the icon row on the first image or button in `icon_ids` (`:2654`). Other buttons are not rendered. | `test_button_icons_anchor_the_icon_row` | RED: `assert 2443 < 204` |
| F4 | `_social_column_rows` walks every column group in order. `section.texts` outside every group are logged as `design_sync.social_texts_ungrouped` (renamed in review round 1, R1), since they carry no position data. | `test_every_column_group_is_rendered`, `test_ungrouped_texts_are_logged` | RED: `1374 < -1`; the log test RED |
| F5 | `ContentGroup.content_order` (`figma/layout_analyzer.py:198`, built at `:2028` by `_column_content_order`). Serialised on `DocumentContentGroup` (`email_design_document.py:978`) and in `$defs/content_group` of `data/schemas/email-design-document-v1.json:324`. Only the social path consumes it; `_build_column_fills_from_content_groups` is unchanged. | `TestContentGroupContentOrder` in `test_email_design_document.py` (3) and `test_layout_analyzer.py` (1); `test_content_group_follows_design_order` | The 4 new tests RED on unchanged code (TypeError/AttributeError; schema test "'content_order' was unexpected"). Order test RED: `502 < 238` |
| F6 | `test_icon_only_section_output_unchanged` now compares to the exact pre-T1 value, captured by running `f26ee233`'s `_fills_social` on the same icon-only section. New `test_icon_only_render_keeps_template_label` pins the `_PRESERVE_UNFILLED_SLOTS` addition. | both, in `TestFillsSocialIconOnly` | Render test RED-first post hoc: removing `social_label` from `_PRESERVE_UNFILLED_SLOTS` made it fail; restored |
| F7 | `app/components/data/component_manifest.yaml:1151` lists `social_label` for social-icons. The closed ledger entry gains a NARROWING note: non-icon buttons are still not rendered and the corpus does not exercise them. | `app/components/tests`: 807 passed, 43 skipped | n/a (data change) |

F5 blast radius (observed): the section cache key does not hash `child_content_groups`; there are no pinned document JSON fixtures; no cms types are generated from this schema.

Corpus probe (observed): every corpus social section has one column group, no ungrouped texts and zero buttons. c6 s7's two content groups hold one image and one text. So F2–F5 claim no corpus change. Their acceptance is partial: the mechanism is proven by unit tests on real c6/c8/c9 sections, not by a corpus case.

## Validation results

Rows marked session 2 ran at `027bcfdf` or earlier. Session-3 rows ran after the F1–F7 fixes.

| Check | Result | Tag |
|---|---|---|
| `ruff check` / `ruff format --check` on the 3 changed `.py` files (session 2) | clean | observed |
| `mypy` on the 3 changed `.py` files (session 2) | clean | observed |
| `pyright` on the 3 changed `.py` files (session 2) | 0 errors; 3 `reportPrivateUsage` warnings in the test file (imports of `_fills_social`, `_DEBUG_DIR`, `_run_conversion`) | observed |
| `uv run pytest app/design_sync/tests/ app/components/tests/ -q` with `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` (session 2) | 3046 passed, 3 failed. All 3 failures are in `test_section_cache` and are caused by the env override disabling the cache | observed |
| `uv run pytest app/design_sync/tests/test_section_cache.py` without the override (session 2) | 35 passed | observed |
| `uv run pytest app/design_sync/tests/test_bridge_roundtrip.py` | session 2: 17 passed; session 3: 19 passed | observed |
| `uv run pytest app/components/tests` (session 3) | 807 passed, 43 skipped | observed |
| `make snapshot-test` | session 2 and session 3: 34 passed, 10 skipped, 1 xfailed | observed |
| Ladder: `git diff origin/main -- data/debug/ladder_snapshot.json` | session 2 and session 3: empty | observed |
| Ladder tests (`test_converter_data_regression.py -k ladder`) | session 2 and session 3: 6 passed | observed |
| `make golden-conformance` | session 2 and session 3: 26 passed, 9 skipped | observed |
| `make lint-numeric` | session 2 and session 3: exit 0 | observed |
| Tree bridge: c8, c9 with `DESIGN_SYNC__TREE_BRIDGE_ENABLED=true` (session 2) | no error or fallback log line; c8 contains "Ferrari N.V.", c9 contains "Unsubscribe", neither contains "Follow us". Superseded by F2: c9 on the tree path now shows the seed "Follow us" (ledgered) | observed |
| `make check-full` via `record-gate.sh` at `027bcfdf` (session 2) | exit 0, pytest 8499 passed / 0 failed / 115 skipped, vitest 780, dirty false, short_gate false, 09:29:31Z→09:34:10Z | observed (.claude/last-gate.json) |
| `make check-full` via `record-gate.sh` at `4ec80659` (review round 1) | exit 0, pytest 8513 passed / 0 failed / 115 skipped, vitest 780, dirty false, short_gate false, 11:13:20Z→11:19:12Z | observed (.claude/last-gate.json) |
| `make check-full` via `record-gate.sh` at `c29122d8` (the folded commit) | exit 0, pytest 8512 passed / 0 failed / 115 skipped, vitest 780, dirty false, short_gate false, 10:39:50Z→10:44:37Z. An earlier run at `71b9db89` (exit 0, 8511 passed) was marked short because the report file was created mid-run | observed (.claude/last-gate.json) |

### Baseline regen audit, session 2 (Task 3)

Six cases captured to scratch with `scripts/snapshot-capture.py <case> --output <scratch>`, then diffed against the committed `expected.html` as an ignore-all-space numstat (observed):

| Case | +/- lines | Overwritten |
|---|---|---|
| c5 | empty | no |
| c6 | +46 / -4 | yes |
| c7 | empty | no |
| c8 | +31 / -2 | yes |
| c9 | +30 / -2 | yes |
| c10 | +25 / -2 | yes |

Every changed line traces to Task 2. The label `<td>` gains `data-slot` and loses the "Follow us" text. The icon cells move into a nested table. Text rows carry design typography. c8 gains its `#373737` `border-top` divider row. The pre-commit `trailing-whitespace` hook then stripped c8's `expected.html`. This is the known c8 whitespace churn, and the snapshot gate normalises whitespace.

### Baseline regen audit, session 3 (F1)

Same recipe, diffed against the `027bcfdf` baselines (observed):

| Case | +/- lines | Overwritten |
|---|---|---|
| c5 | empty | no |
| c6 | +1 / -9 | yes |
| c7 | empty | no |
| c8 | +1 / -5 | yes |
| c9 | +1 / -5 | yes |
| c10 | +1 / -5 | yes |

Every changed line is the label row removal plus the design padding moving to the `social_links` `<td>`. c6 s7 had no design padding, so only its label row went. The padding that moved is `padding:20px 48px 40px 48px` on c6 s8, `40px 40px 40px 40px` on c8 and c9, and `40px 32px 40px 32px` on c10. The trailing-whitespace hook stripped c8 again (known churn). The after-regen gates are in the session-3 rows of the Validation table.

### Full-corpus A3 (Task 5)

**Session 2 (`027bcfdf`), superseded.** A subagent ran `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` in a worktree, once on `f26ee233` files and once on `18598920`. Scores are from `scratchpad/a3/before/scores.json` and `after/scores.json` (observed); deltas are derived as after − before.

| Case | Role | full_image | section_min | section_median |
|---|---|---|---|---|
| c5 | non-target | 0.8662 → 0.8662 (0) | 0.6628 → 0.6628 | 0.8849 → 0.8849 |
| c6 | target | 0.8203 → 0.8058 (−0.0145) | 0.4772 → 0.4854 | 0.6984 → 0.7527 |
| c7 | non-target | 0.8397 → 0.8397 (0) | 0.5417 → 0.5417 | 0.8651 → 0.8651 |
| c8 | target | 0.8217 → 0.8663 (+0.0446) | 0.6966 → 0.8141 | 0.8404 → 0.8663 |
| c9 | target | 0.6814 → 0.7150 (+0.0336) | 0.4479 → 0.3033 | 0.7621 → 0.7676 |
| c10 | target | 0.7195 → 0.7439 (+0.0244) | 0.0000 → 0.0574 | 0.8268 → 0.8338 |

In session 2, c5 and c7 were identical on every band (observed). The target-band drops (c6 bands 0–3, c8 bands 3/4/10, c9 bands 4/6/7, c10 bands 12/14/15, derived from the two JSON files) were judged scorer jitter from the taller render shifting the fixed design-fraction bands (memory `reference_a3_scorer_section_instability`).

**Session 3 (`71b9db89`).** F1 moves the c6/c8/c9/c10 baselines, so A3 was re-scored on the whole corpus: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` in a throwaway worktree detached at `71b9db89`, with the gitignored reference PNGs and assets copied from the main checkout. `scores.json` was written at 10:33Z, after the 10:31Z start (observed). "Before" is the session-2 `f26ee233` run. The worktree reproduced session 2's `027bcfdf` scores byte-for-byte before re-scoring (observed). Deltas are derived as after − before.

| Case | Role | full_image | section_min | section_median |
|---|---|---|---|---|
| c5 | non-target | 0.8662 → 0.8662 (0) | 0.6628 → 0.6628 | 0.8849 → 0.8849 |
| c6 | target | 0.8203 → 0.8132 (−0.0071) | 0.4772 → 0.4661 | 0.6984 → 0.7573 |
| c7 | non-target | 0.8397 → 0.8397 (0) | 0.5417 → 0.5417 | 0.8651 → 0.8651 |
| c8 | target | 0.8217 → 0.8632 (+0.0415) | 0.6966 → 0.8085 | 0.8404 → 0.8645 |
| c9 | target | 0.6814 → 0.7095 (+0.0281) | 0.4479 → 0.3033 | 0.7621 → 0.7614 |
| c10 | target | 0.7195 → 0.7361 (+0.0166) | 0.0000 → 0.0635 | 0.8268 → 0.8336 |

- c5 and c7 are identical on every band (observed).
- Target bands that dropped by more than 0.005 (derived):
  - c6: bands 0–7 (0.971 → 0.899 at the top; 0.477 → 0.466 on bands 4–7).
  - c8: bands 3, 4 and 10.
  - c9: bands 4, 6 and 7 (0.448 → 0.303).
  - c10: bands 7, 12 and 15.
- In the composites (reference on the left, `score-fidelity-cases.py:78`) the c6, c8, c9 and c10 footers match the design in content and order.
- The dropped bands cover upper sections whose HTML this change does not touch. The render got taller, so these drops read as jitter.
- Against session 2, F1 halved c6's full-image drop (−0.0145 → −0.0071, derived) and trimmed the c8, c9 and c10 gains.

**Ratified by the user, 2026-09-28 (AskUserQuestion, "Ratify and ship"):** c6 full_image −0.0071 with section_min 0.4772 → 0.4661, and c9 section_min 0.4479 → 0.3033.

## Deviations from the plan

1. **`component_renderer.py` changed, although Task 2 did not name it.** `social_label` is added to `_PRESERVE_UNFILLED_SLOTS`. Without that, `_blank_unfilled_text_slots` blanks every unfilled text slot, and the L1 slot would have wiped "Follow us" on icon-only sections too, which contradicts L1. `_fills_social` blanks the label explicitly when design text is present. F1 later added `_COLLAPSE_ON_EMPTY_FILL` in the same file.
2. **Task 0 `/preflight-check` was not run as a separate step.** The deferred-items grep it performs was done at plan time; its table is the plan's "Deferred Items Touching This Plan". Base `f26ee233` was recorded.
3. **Resolved at commit time: the planned "texts but no resolvable icon → `[]`" unit test.** `test_texts_without_any_icon_render_nothing` added; it pins unchanged behaviour (the `if not cells: return []` guard), so it passes on base too.
4. **Resolved by F6: the icon-only identity test checked shape, not bytes.** It now compares to the exact pre-T1 value from `f26ee233`.
5. **Resolved by F5: the `child_content_groups` branch did not follow design order.** It now uses each group's `content_order`.
6. **Superseded by F3: the "icons after the last row" fallback when icons come only from `section.buttons`.** Icon buttons now anchor the icon row at their design position.
7. **Ledger details differ from Task 7.**
   - The new entry id is `phase-53g-t1-social-non-icon-images-as-icons`, not the planned `t1-social-section-non-icon-images-as-icons`, to follow the schema's `phase-<N>.<sub>-<slug>` prefix. Its code_ref is `component_matcher.py:2576` (the images-as-icons fallback, re-verified at commit time).
   - The closed entry's drifted code_ref `:2528` was **not** corrected to `:2530`, which the plan asked for. The deferred-items skill's close step says to leave every other field unchanged.
   - The note that non-icon buttons are unexercised by the corpus is now recorded in the entry itself (F7).
8. **F2 changes tree-path behaviour for empty CTA label fills.** On the tree path (flag off by default), empty `cta_text`, `primary_text`, `secondary_text` and `link_text` fills now show their seed label instead of the literal word "text". The default path prunes those CTAs and is unchanged. This is recorded in `phase-53g-t1-tree-path-social-label-default`. The plan amendment said the F2 test asserts no "Follow us" on the tree path; the shipped test asserts no placeholder, and the seed "Follow us" is ledgered instead.
9. **The `rm -rf` guard hook blocked an A3 command in session 3.** The command was re-run without the delete.

## Issues encountered

- Running the full design_sync suite with `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` (needed for converter runs) fails 3 `test_section_cache` tests, because those tests need the cache on. Re-run without the override: 35 passed (observed). This is an environment interaction, not a regression.
- The pre-commit `trailing-whitespace` hook rewrote c8 `expected.html` after each overwrite (known c8 churn). `make snapshot-test` gave the same result before and after (observed).
- Out of scope, ledgered: non-icon images in social sections (c6 `2833:1490`, c10 logo `2833:1274`) still render as 32px "Social icon" cells in the icon row.
- Carried forward, unchanged: `phase-53g-g11-contentgroup-column-divider-gap` (c6 s7 has no divider).

## Ledger (`.agents/deferred-items.json`)

| Entry | Change | Commit field |
|---|---|---|
| `phase-53g-g11-social-section-drops-column-content` | closed; session 3 adds a NARROWING note (texts and in-column dividers closed, icon buttons anchor the icon row, non-icon buttons still not rendered and unexercised by the corpus) | `closed_commit: pending` |
| `phase-53g-t1-social-non-icon-images-as-icons` | added, known-bug | `introduced_commit: pending` |
| `phase-53g-t1-tree-path-social-label-default` | added, known-bug (tree path flag-off; seed "Follow us" beside design text, plus the empty-CTA-label side effect) | `introduced_commit: pending` |

All three `pending` values need stamping with the squash SHA after merge.

## PR review round 1 (`.claude/code-reviews/pr-409-review.md`)

`piv-review-pr` ran in a fresh-context subagent at `c29122d8` and posted review 5337541547 as a comment. Verdict: request changes. Counts: Medium 1, Low 5 (observed). User triage (AskUserQuestion): fix R1 and R2, ledger R3.

| Code | Finding | Outcome |
|---|---|---|
| R1 Medium | the F4 log event had three dot-parts; new events must be two-part | fixed in `4ec80659`: `design_sync.social_texts_ungrouped` |
| R2 Low | texts in a section with no column/content group were dropped without a log | fixed in `4ec80659`: the log runs before the no-group return; `test_texts_without_any_group_are_logged` RED then green (observed) |
| R3 Low | image fallback: a logo above a label pulls the icon row above the label | ledgered on `phase-53g-t1-social-non-icon-images-as-icons` |
| R4 Low | stale report lines (head, re-score, gate) | fixed in this report |
| R5 Low | session-3 A3 scores only in the scratchpad | copied to `.claude/state/s9-t1/a3/after-s3-71b9db89/` |
| R6 Low | three `pending` ledger SHAs | stamp after merge |
