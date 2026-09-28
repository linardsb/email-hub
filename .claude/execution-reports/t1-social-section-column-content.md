# Execution Report — T1: social-classified sections render their text and divider content

## Meta Information

- Plan file: `.agents/plans/t1-social-section-column-content.md` (with its AMENDMENTS, sessions 2 and 3).
- Written by: a delegated agent in a later context on 2026-09-28. It did not implement the ticket. It works from the lead's records: the plan and its AMENDMENTS, the implementation report `.claude/reports/t1-social-section-column-content-report.md`, the PR review `.claude/code-reviews/pr-409-review.md`, the pre-PR findings `.claude/state/s9-t1/review-findings-pre-pr.md`, the handoff `.claude/state/s8-handoff/HANDOFF-main-checkout.md` ("S9 session status"), the session-2 §7 draft `.claude/state/s9-t1/s7-entry-s9-session2.md`, and the session-3 process facts the lead supplied. Facts from the lead are tagged "observed (lead)". Facts from this agent's own commands are tagged "observed (this report)".
- Branch / PR: `fix/t1-social-section-column-content`, PR #409. Base `origin/main` `f26ee233`. Head `4ec80659` (observed (this report), `git log origin/main..HEAD`).
- Commits: `c29122d8` (the three session-2/3 `chore(wip):` commits `18598920`, `027bcfdf` and `71b9db89`, folded) and `4ec80659` (review round 1, R1 + R2).
- Files added (observed (this report), `git diff --name-status origin/main...HEAD`):
  - `.agents/plans/t1-social-section-column-content.md`
  - `app/design_sync/tests/test_social_section_content.py`
- Files modified (same command):
  - `app/design_sync/component_matcher.py`, `app/design_sync/component_renderer.py`, `app/design_sync/tree_bridge.py`, `app/design_sync/figma/layout_analyzer.py`, `app/design_sync/email_design_document.py`
  - `app/design_sync/tests/test_bridge_roundtrip.py`, `app/design_sync/tests/test_email_design_document.py`, `app/design_sync/tests/test_layout_analyzer.py`
  - `email-templates/components/social-icons.html`, `app/components/data/component_manifest.yaml`, `data/schemas/email-design-document-v1.json`
  - `data/debug/{6,8,9,10}/expected.html`
  - `.agents/deferred-items.json`
- Lines changed: +958 −85 across 18 files (observed (this report), `git diff --shortstat origin/main...HEAD`). Of these, +463 −4 across 12 files are outside `data/debug/` and `.agents/`, which covers code, tests, schema, manifest and template (observed (this report), same command with those paths excluded).

## Validation Results

- Syntax & Linting: ✓. `ruff check`/`ruff format --check` were clean on the changed files in session 2 (observed (lead), report § Validation). The `make check-full` lint step was green at `c29122d8` and `4ec80659` (observed (lead), `.claude/last-gate.json`, `make_errors` empty).
- Type Checking: ✓. mypy and pyright ran inside `make check-full` at both heads (observed (lead), same record). In session 2 pyright gave 3 `reportPrivateUsage` warnings in the new test file and 0 errors (observed (lead)).
- Unit Tests: ✓. Figures per head:
  - `4ec80659`: 8513 passed, 0 failed, 115 skipped; vitest 780. `exit_code` 0, `dirty` false, `short_gate` false, 11:13:20Z→11:19:12Z (observed (this report), read from `.claude/last-gate.json`).
  - `c29122d8`: 8512 / 0 / 115; vitest 780; exit 0 (observed (lead)).
  - The +1 is `test_texts_without_any_group_are_logged`, the R2 test (derived: 8513 − 8512 = 1).
  - The new test file has 15 tests, all passing at `4ec80659` (observed (lead)).
  - Converter gates at session 3 (observed (lead)): `make snapshot-test` 34 passed / 10 skipped / 1 xfailed; ladder tests 6 passed, and `ladder_snapshot.json` is unchanged from base; `make golden-conformance` 26 passed / 9 skipped; `make lint-numeric` exit 0.
- Integration Tests: not run locally, because `make check-full` does not run them. CI job "Integration tests (tenant isolation)" passed at `c29122d8` (observed (lead): all 14 checks passed, CI flipped #409 to ready at 10:54:54Z). At `4ec80659` the same job showed pass at 11:29Z (observed (this report), `gh pr checks 409`). At that read, "Backend (lint + types + security + test)" was still pending and `mergeStateStatus` was BLOCKED. CI at `4ec80659` is therefore **not yet green** at the time of writing.
- Full-corpus A3: advisory, not a gate. Session 3 at `71b9db89` against session 2's `f26ee233` run (observed (lead); deltas derived as after − before):
  - c5 and c7 (non-targets): flat on every band.
  - c8: +0.0415 full_image.
  - c9: +0.0281 full_image, but section_min 0.4479 → 0.3033 (−0.1446).
  - c10: +0.0166 full_image.
  - c6: 0.8203 → 0.8132 full_image (−0.0071); section_min 0.4772 → 0.4661 (−0.0111).
  - The user ratified the c6 and c9 trades (observed (lead), AskUserQuestion "Ratify and ship").

## What Went Well

- **The root cause was relocated with evidence before any code was written.** The S9 prep note blamed the early return at `layout_analyzer.py:980`. Session 2 showed that removing it changes nothing and that the loss is in `_fills_social` (observed (lead), s7 draft line 27). The plan was then written against the real cause.
- **The plan chose the single existing HTML path.** It argued the composite-splice route down (plan lines 56-59). The fresh PR reviewer called the choice well scoped (pr-409-review "What is good").
- **RED-first held throughout.** The evidence:
  - 6 of the 7 session-2 tests failed on assertions on unchanged code (observed (lead)).
  - Each of F1–F5 has recorded RED output.
  - F6's render test was proven RED-first post hoc, and says so.
  - The icon-only identity test compares bytes against a literal captured by running `f26ee233` code.
- **The corpus guard held.** c5 and c7 scratch diffs were empty in both regen rounds, and the ladder did not move (observed (lead), report § Baseline regen audit).
- **The review caught real defects before merge.** A pre-PR review from a fresh-context reviewer found 3 Medium defects (F1–F3) that the lead's own tree-flag check had missed. For F2, the lead's check asserted "Follow us" absent but never checked for the literal "text" (review-findings-pre-pr.md F2).
- **Partial acceptance was stated, not over-claimed.** F2–F5 claim no corpus change, because a probe showed every corpus social section has one column group, no ungrouped texts and no buttons. The unit tests on real c6/c8/c9 sections carry the proof, as `converter-fix` §7 "Partial acceptance" asks.
- **Subagent fan-out with exclusive file ownership produced no merge conflicts** (observed (lead)). The owners were:
  - F2: `tree_bridge`.
  - F5: `layout_analyzer`/`email_design_document`/schema.
  - F7: manifest and ledger.
  - Plus a research agent, an A3 worktree-prep agent, a report-draft agent and a fresh-context `piv-review-pr` agent.
  - The lead kept the matcher, the renderer and the test file.
- **The A3 re-score was trustworthy.** The throwaway worktree reproduced session 2's `027bcfdf` scores byte for byte before re-scoring, which is a built-in calibration check (observed (lead), report § A3).

## Challenges Encountered

Process friction in session 3 (all observed (lead) unless tagged otherwise):

- **(a) zsh shell semantics.**
  - `uv run ruff check $F` did not word-split `$F`, so a zsh array was needed.
  - `echo =====` fails in zsh (the `=word` expansion). The lead already knew this as a dead end.
  - No project rule or skill mentions zsh (observed (this report): a grep of `CLAUDE.md`, `.claude/rules`, `.claude/skills` and `.claude/references` for `zsh` has no hit).
- **(b) The `rm -rf` guard hook blocked a legitimate cleanup.** It blocked `rm -rf .tmpscratch/fidelity` in the A3 worktree. `.tmpscratch/` is gitignored (observed (this report), `git check-ignore`). The broad rule `rm\s+-rf\s+(/|\.|\*|\.\.)` in `.claude/hooks/block-dangerous.sh:70` matches any path that starts with a dot. The same hook also blocked a read-only `grep` by this report's agent: the grep pattern contained the string `rm -rf` and the path `.claude/`, and the protected-path check at `:59-66` matches substrings anywhere in the command (observed (this report)).
- **(c) The first gate at `71b9db89` was marked short.** The report-draft subagent created an untracked file while the gate was running. This was the lead's parallelism error: `piv-validate` already says a parallel agent editing the tree mid-run trips the tree-changed check.
- **(d) The WIP fold invalidated the gate record.**
  - `piv-commit` step 1 folds one `chore(wip):` commit with `git reset --soft HEAD~1`, but the branch had three.
  - The lead used `git reset --soft f26ee233`. The fold produced a new head, which invalidated the gate record, so the gate was re-run at `c29122d8`.
  - That re-run took 4m47s (derived: 10:39:50Z→10:44:37Z). The lead estimated about 6 min lost; a full gate on this branch took between 4m39s and 5m52s (derived from the three recorded runs).
  - The fold also changed the tree, not just the head: `71b9db89` and `c29122d8` differ in the ledger, the plan and the test file (derived, pr-409-review "Numbers pass").
- **(e) The skills give untracked PIV artefacts no safe place during a gate.**
  - An untracked report or review file makes `record-gate.sh` record `dirty`, because it samples `git status --porcelain`, which lists untracked files (`record-gate.sh:91-94`).
  - `.claude/reports/`, `.claude/code-reviews/`, `.claude/execution-reports/` and `.claude/system-reviews/` are not gitignored (observed (this report), `git check-ignore`).
  - The lead parked the files in scratch during each gate. No skill says where they should live.
- **(f) A background wrapper died while the gate kept running.** The background Bash wrapper around `record-gate.sh` was killed (exit 144). `record-gate.sh` kept running as an orphan and completed.
- **(g) An unquoted heredoc mangled the PR body.** When the validation block was inserted into the PR body, the unquoted heredoc swallowed the backticks.
- **(h) The pre-push hook rewrote the `skill-versions.yaml` dates again.** It ran the local `make check` and rewrote two dates, which the lead restored by hand. This has now happened at least three times: #408's session-1 push, #408's session-2 push (handoff lines 6 and 14) and this push. The hook's detection runs the local gate on any uncertainty (`scripts/ci-local-fallback.sh:14`) and does not restore the stamps.
- **(i) The trailing-whitespace hook stripped c8 `expected.html` again.** This is the pre-commit `trailing-whitespace` hook and the known churn. The file had to be re-added. `.pre-commit-config.yaml:13-14` has no exclusion for `data/debug/*/expected.html`.
- **Code-level challenge: the label padding.** L1 made the template label a slot. The accepted cost was "the empty label cell keeps its `24px 0 16px` padding" (plan line 244). In practice the bridged design padding landed on that empty cell and left a band of 80px or more (F1). A renderer collapse rule (`_COLLAPSE_ON_EMPTY_FILL`) was needed, and the baselines and A3 moved a second time.

## Divergences from Plan

**Renderer file changed although Task 2 did not name it**
- Planned: Task 2 edits `_fills_social` only; the files list did not include `component_renderer.py`.
- Actual: `social_label` was added to `_PRESERVE_UNFILLED_SLOTS`, and F1 later added `_COLLAPSE_ON_EMPTY_FILL`.
- Reason: without the first change, `_blank_unfilled_text_slots` would have blanked "Follow us" on icon-only sections as well, which contradicts L1.
- Type: Plan assumption wrong

**Task 0 `/preflight-check` not run as its own step**
- Planned: run `/preflight-check` on the plan (Task 0; `converter-fix` §0.2).
- Actual: the deferred-items grep ran at plan time, and its table became the plan's "Deferred Items Touching This Plan". Base `f26ee233` was recorded.
- Reason: the lead judged the plan-time grep to cover it. Preflight's other checks (friction patterns) did not run.
- Type: Other (a skipped step, not a better approach)

**Scope widened by F1–F7 after the pre-PR review**
- Planned: `_fills_social` walks `column_groups[0]`, or flattened content groups, with the first `ImagePlaceholder` anchoring the icon row. Buttons were left out. The empty label cell was expected to keep its padding. The tree path was only checked for the legal text being present.
- Actual (user triage, session 3): all seven findings were fixed.
  - F1: collapse the empty label row.
  - F2: `None` for empty tree text fills.
  - F3: icon buttons anchor the row.
  - F4: walk every group and log ungrouped texts.
  - F5: `ContentGroup.content_order` added, with schema and serialisation.
  - F6: byte-identity and label tests.
  - F7: manifest and ledger note.
- Reason: a fresh-context reviewer found defects that the plan's design produced when implemented as written (see the evolution review, `plan_defect`).
- Type: Plan assumption wrong

**Tree path shows the seed label instead of blank**
- Planned (amendment F2): the test asserts no "Follow us" on the tree path.
- Actual: the test asserts no placeholder text. The seed "Follow us" remains on the tree path and is ledgered as `phase-53g-t1-tree-path-social-label-default`. Empty CTA label fills on the tree path now also keep their seed label.
- Reason: `TextSlot`/`HtmlSlot` need `min_length=1`, so the tree path cannot carry an empty value.
- Type: Plan assumption wrong

**Ledger details differ from Task 7**
- Planned: new id `t1-social-section-non-icon-images-as-icons`; fix the closed entry's drifted `:2528` code_ref to `:2530`.
- Actual:
  - The new id is `phase-53g-t1-social-non-icon-images-as-icons`, which follows the schema prefix.
  - The drifted code_ref was left as is, because the `deferred-items` skill's close step says "Leave every other field as it is" (`deferred-items/SKILL.md:41`).
  - A third entry was added for F2.
- Reason: the plan conflicted with the ledger schema and with the skill.
- Type: Better approach found (id); Other (plan/skill conflict, code_ref)

**Log event name broke the logging standard (R1)**
- Planned: "Logging: none needed" (plan line 116).
- Actual: the F4 amendment added `design_sync.social.ungrouped_texts`, a three-part name, contrary to `.claude/references/logging-standard.md:36`. The PR review flagged it (R1 Medium), and `4ec80659` renamed it to `design_sync.social_texts_ungrouped`.
- Reason: the amendment added a log without anyone re-reading the logging standard.
- Type: Other (an undocumented pattern violation)

**Gate run with a parallel writer in the tree**
- Planned: `piv-validate` on a quiet tree.
- Actual: the gate at `71b9db89` was marked short because a subagent created an untracked file mid-run.
- Reason: lead orchestration error.
- Type: Other

## Skipped Items

- `/preflight-check` as a separate step (Task 0). Reason: covered in part by the plan-time deferred-items grep; see Divergences.
- Correcting the closed entry's drifted code_ref (Task 7). Reason: the `deferred-items` skill forbids changing other fields on close.
- Non-icon buttons in social sections are still not rendered. Reason: out of scope per the plan, and the corpus does not exercise them (NARROWING note on `phase-53g-g11-social-section-drops-column-content`).
- Ledger SHA stamping (three `pending` values). Reason: this happens after the squash merge (R6).

## Recommendations

The evolution review ranks these and expands each (`.claude/system-reviews/t1-social-section-column-content-review.md`).

- Plan skill improvements:
  - **E6.** When an AMENDMENT adds a new kind of artefact (log event, schema field, template slot, manifest slot), re-open the matching "Patterns to Follow" reference and record the check.
  - **E7.** For every input shape the plan limits to what the corpus exercises (first group only, image-only anchor, group order), either handle the general case or ledger it at plan time. A tree-path check must assert that no placeholder text is present, not only that the target text is present.
- Execute skill improvements:
  - **E1.** Order the hand-off as fold WIP commits → plan amendments → `piv-validate` → `piv-create-pr`, and fold every consecutive `chore(wip):` commit back to the merge-base.
  - **E2.** Make `record-gate.sh` ignore untracked files under the four PIV artefact directories.
  - **E3.** No subagent may write into the tree while a gate runs; route drafts to `.claude/state/` (gitignored).
  - **E10.** Update PR bodies with `gh pr edit --body-file`.
- CLAUDE.md additions:
  - **E8.** Under "Known environment issues": the shell is zsh, so use arrays for file lists and quote `'====='`.
  - **E4 / E5.** Record the pre-push `skill-versions.yaml` rewrite and the c8 trailing-whitespace churn as known issues, until the hook and pre-commit fixes land.
