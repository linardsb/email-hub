# System Review — T1: social-classified sections render their text and divider content

## Meta Information

- Plan reviewed: `.agents/plans/t1-social-section-column-content.md`
- Execution report: `.claude/execution-reports/t1-social-section-column-content.md`
- Date: 2026-09-28
- Also read:
  - `.claude/system-reviews/REMEDY-LEDGER.md` (read first; it has no rows, so there are no open items and no recurrences of logged items).
  - `.claude/skills/piv-plan-implementation/SKILL.md` and `.claude/skills/piv-implement/SKILL.md`.
  - The skills this loop used: `converter-fix`, `piv-validate`, `piv-commit`, `piv-create-pr`, `piv-review-pr` and `deferred-items`.
  - The implementation report, `pr-409-review.md`, `review-findings-pre-pr.md` and the S9 handoff block.
- Scope: this was the first ticket through the imported PIV loop (handoff T1). It is a process review, not a code review.

## Overall Alignment Score: 7/10

The tasks were executed in order and in substance. The divergences that affected the code were justified, and each is documented in the report and in the plan's AMENDMENTS. Three process divergences were problematic:

- `/preflight-check` was skipped.
- The gate ran while a subagent was writing into the tree, and `piv-validate` already forbids that.
- The new log event broke the logging standard and was not declared (R1).

**Plan correctness: 5/10.** Five of the seven pre-PR findings (F1–F5), plus the R1 root cause, entered at plan lines and were then reproduced faithfully. The implementation followed the plan, so they do not count as adherence failures. Each one cost a fix round, and together they sent the baselines and A3 through a second full cycle. The entries are listed below as `plan_defect`.

## Divergence Analysis

```yaml
divergence: component_renderer.py changed (_PRESERVE_UNFILLED_SLOTS, later _COLLAPSE_ON_EMPTY_FILL)
planned: Task 2 edits _fills_social only; renderer not in files list
actual: social_label preserved when unfilled; F1 collapse-on-empty-fill added
reason: without it the L1 slot blanks "Follow us" on icon-only sections, contradicting L1
classification: good
justified: yes
root_cause: plan did not trace the new slot through the renderer's unfilled-slot handling (missing context)
```

```yaml
divergence: Task 0 /preflight-check not run as a step
planned: /preflight-check <plan> (Task 0; converter-fix §0.2)
actual: plan-time deferred-items grep reused; friction-pattern scan not run
reason: lead judged the plan-time grep sufficient
classification: bad
justified: no
root_cause: converter-fix §0.2 does not say whether a same-day, same-base plan-time grep satisfies it; nothing checks that the step ran
```

```yaml
divergence: F1–F7 scope widening after pre-PR review
planned: column_groups[0] only; flattened content groups; first ImagePlaceholder anchors icons; buttons out; label cell keeps padding
actual: all seven fixed on the branch (user triage)
reason: fresh-context review found plan-born defects
classification: good
justified: yes
root_cause: plan defects (see plan_defect entries); the divergence itself is the correct response
```

```yaml
divergence: tree path keeps seed "Follow us" rather than blank
planned: amendment F2 test asserts no "Follow us" on the tree path
actual: asserts no placeholder; seed label ledgered (phase-53g-t1-tree-path-social-label-default)
reason: TextSlot/HtmlSlot min_length=1 cannot carry an empty value
classification: good
justified: yes
root_cause: plan assumption wrong (tree schema constraint not read at amendment time)
```

```yaml
divergence: ledger id prefix and code_ref left drifted
planned: id t1-social-section-non-icon-images-as-icons; fix :2528 -> :2530 on close
actual: id phase-53g-t1-…; code_ref unchanged
reason: schema id prefix; deferred-items/SKILL.md:41 "Leave every other field as it is"
classification: good
justified: yes
root_cause: plan instruction conflicts with the deferred-items skill (the plan skill does not tell the planner the close step's constraints)
```

```yaml
divergence: log event design_sync.social.ungrouped_texts (three-part)
planned: "Logging: none needed" (plan line 116)
actual: F4 amendment added a log; name violated logging-standard.md:36; fixed in 4ec80659 (R1)
reason: not stated in report (undocumented)
classification: bad
justified: no
root_cause: amendments add work without re-checking the plan's Patterns to Follow; the plan said no logging, so logging-standard.md was never opened
```

```yaml
divergence: gate at 71b9db89 run with a parallel writer
planned: piv-validate on a quiet tree
actual: report-draft subagent created an untracked file mid-run; record marked short
reason: lead orchestration error
classification: bad
justified: no
root_cause: piv-validate forbids tree edits during a run, but the rule is phrased for "a parallel agent editing the tree" and says nothing about new untracked PIV artefacts; the lead's fan-out rules give subagents no write location outside the tree
```

```yaml
divergence: WIP fold with git reset --soft f26ee233 instead of HEAD~1
planned: piv-commit step 1 folds one chore(wip) commit
actual: three WIP commits; manual reset to base; new head invalidated the gate record; gate re-run at c29122d8 (4m47s, derived)
reason: skill handles exactly one WIP commit
classification: good
justified: yes
root_cause: piv-commit assumes one WIP commit; the hand-off order (validate → commit) guarantees a head change after the gate
```

```yaml
plan_defect: F1 empty social_label cell keeps its bridged padding (80px+ band)
entered_at: plan line 244-245 (Q1 L1 "the empty label cell keeps its 24px 0 16px padding" accepted as a cost)
reproduced_at: session-2 commit 18598920 / baselines 027bcfdf; caught by pre-PR review F1
```

```yaml
plan_defect: F2 tree path renders empty text fill as literal "text"
entered_at: plan line 183-184 (Task 6 checks "legal text is present", never that no placeholder is emitted)
reproduced_at: session-2 tree-flag run (checked "Follow us" absent only); caught by pre-PR review F2
```

```yaml
plan_defect: F3 button-sourced icons appended after all text
entered_at: plan line 47-50 (first ImagePlaceholder anchors the icon row; buttons "left out")
reproduced_at: 18598920; caught by pre-PR review F3
```

```yaml
plan_defect: F4 texts in second+ column groups or outside groups dropped silently
entered_at: plan line 44 (column_groups[0] only)
reproduced_at: 18598920; caught by pre-PR review F4; zero-group case survived to PR review (R2)
```

```yaml
plan_defect: F5 content-group branch not in design order
entered_at: plan line 45-46 (flattened in order, "mirroring _build_column_fills_from_content_groups")
reproduced_at: 18598920; caught by pre-PR review F5
```

```yaml
plan_defect: R1 root: logging pattern declared unnecessary and never revisited
entered_at: plan line 116 ("Logging: none needed")
reproduced_at: session-3 F4 amendment (line 267) added a log without a pattern check; caught by PR review R1
```

**The pattern behind F3–F5.** The plan limited handling to the shapes the corpus exercises: one column group, image icons, a single content group. It did not ledger the general cases. The corpus could not catch this, because every social section in it has one group, no buttons and no ungrouped texts. The fresh-context reviewer caught it by reading the mechanism. `converter-fix` §7 "Partial acceptance" covers this only after the fact. Nothing at plan time asks "which input shapes does this code path accept, and which of them does the corpus exercise?"

## Pattern Compliance

- [x] Followed codebase architecture. The change uses the single HTML path through an attr fill. It adds no parallel writer and no splice-regex widening (pr-409-review "What is good").
- [ ] Used documented patterns (from CLAUDE.md). There is one miss: the logging standard's two-part event rule (R1). Table-only HTML, escaping and real fixtures all held.
- [x] Applied testing patterns correctly. Tests were RED-first, with post-hoc RED stated where it applied. They use real `data/debug` fixtures, including the byte-identity literal from `f26ee233`.
- [x] Met validation requirements, with the gaps below. `make check-full` ran green via `record-gate.sh` at `c29122d8` and `4ec80659` (observed (lead), `.claude/last-gate.json`). The full-corpus A3 has six rows, and its trades were ratified. The ladder is unchanged from base. The gaps:
  - One short gate was caused by the lead's own parallel writer.
  - Preflight was skipped.
  - CI at `4ec80659` was still pending when this review was written. At 11:29Z (observed (this review), `gh pr checks 409`): Backend pending, 11 checks passing, `mergeStateStatus` BLOCKED.

## System Improvement Actions

Ranked. Recurring and structural items come first. Every item is **recommended, not applied**: the caller limited this run to creating the two report files.

**Update Execute Skills (piv-commit, piv-implement, converter-fix, piv-validate, piv-create-pr):**

- [ ] **E1: fix the hand-off order and the multi-WIP fold (structural).**
  - The problem: `converter-fix` §8 and `piv-implement` "Next" both say `piv-validate` → `piv-commit` → `piv-create-pr`. But `piv-commit` changes the tree after the gate: it folds WIP commits and writes plan amendments (step 2). `piv-create-pr` Phase 2.5 then refuses a record whose `head` is not `HEAD`. So a green gate taken before the commit cannot survive to the PR on any ticket with a WIP commit or a plan amendment, and the fold here also changed the tree (`71b9db89`..`c29122d8` differ in ledger, plan and test file). Keying the record on the tree hash would not help.
  - Text for `converter-fix` §8 and `piv-implement` "Next": "`piv-commit` (fold WIP, amend the plan) → `piv-validate` on the committed head → `piv-create-pr`."
  - Text for `piv-commit` step 1: "If one or more consecutive top commits start with `chore(wip):`, run `git reset --soft <first non-wip ancestor>` (for a branch whose every commit is WIP, `git merge-base HEAD origin/main`)."
- [ ] **E2: make `record-gate.sh` ignore untracked PIV artefacts (structural; this review's own files trigger it).**
  - The problem: `record-gate.sh:91-94` samples `git status --porcelain`, which lists untracked files. The four artefact directories `.claude/{reports,code-reviews,execution-reports,system-reviews}/` are not gitignored, and they are sometimes committed (as the G4 report and review were, in #355). So any untracked report makes the gate `dirty`. The lead had to park files in scratch for each gate. This review's two new files will make the next gate on this branch dirty too.
  - Remedy: filter `?? .claude/(reports|code-reviews|execution-reports|system-reviews)/` out of both samples.
  - Text for `piv-validate` §2: "Untracked files under the four PIV artefact directories do not mark the record dirty; every other new file does."
  - This also closes friction (e), where the skills never say where PIV artefacts should live during a gate.
- [ ] **E3: no in-tree writes during a gate.** Text for `piv-validate` §2, after "Do not start a second gate": "While a gate runs, no subagent writes inside the worktree, not even a new untracked file. Send drafts to `.claude/state/<ticket>/` (gitignored) or the session scratchpad, and move them in after the gate finishes." This root cause is at the orchestration level: when the lead fanned out work (friction (c)), it gave subagents file ownership but no write location.
- [ ] **E9: stop the `rm -rf` guard from firing on non-deletions and gitignored scratch** (`.claude/hooks/block-dangerous.sh`).
  - The problem, in two parts:
    - The protected-path check (`:59-66`) matches `rm -rf` and a protected path anywhere in the command string. It blocked this review's read-only `grep` (observed (this review)).
    - The broad rule (`:70`) blocks every relative dotted path, including gitignored `.tmpscratch/` (friction (b)).
  - Remedy:
    - Anchor the match to the command position (`(^|[;&|]\s*)rm\s+-…`).
    - Allow paths that `git check-ignore` reports as ignored and that sit under `.tmpscratch/` or the scratchpad.
- [ ] **E10: publish PR bodies from a file.** Text for `piv-create-pr` Phase 3: "When updating an existing PR body, write it to a file and run `gh pr edit {N} --body-file <file>`; never interpolate through an unquoted heredoc (it runs command substitution on backticks)." The skill's own `gh pr create` example already uses `<<'EOF'`. The failure happened on the edit path, which the skill does not describe.
- [ ] **E11: run the gate so its record survives the wrapper.** Text for `piv-validate` §2: "Run `record-gate.sh` itself with `run_in_background`, not inside another wrapper. If the wrapper dies (for example exit 144), check `.claude/last-gate.json` `finished` and whether `record-gate.sh` is still running (`pgrep -f record-gate`) before starting another run." (friction (f)). This is low-ranked: it happened once, but a second concurrent gate is exactly what §2 forbids.

**Update Plan Skill (`.claude/skills/piv-plan-implementation/SKILL.md`):**

- [ ] **E6: amendments re-check the patterns (R1 root).** Add to the AMENDMENTS template (`:564-568`): "An amendment that adds a new kind of artefact (log event, schema field, template or manifest slot, public function) re-opens the matching Patterns to Follow reference (`.claude/references/logging-standard.md`, `data/schemas/…`, the component manifest) and records the check in the entry."
- [ ] **E7: shape coverage at plan time (F3–F5 root; F2 variant).**
  - Add a Quality Criteria item: "For each input the changed code path accepts (list, group, element kinds), the plan states which shapes it handles and which the corpus exercises. An unhandled general shape is either handled or ledgered in the plan, not left to review."
  - Add to `converter-fix` §0.4: "A tree-path check asserts both that the target text is present **and** that no placeholder/seed text is emitted."
- [ ] **E12: resolve the plan/skill conflict on drifted code_refs.** Either `deferred-items` §close allows a drifted `code_refs` line to be corrected, with a note, or the plan skill tells planners not to ask for it. Recommended: allow the correction. A drifted ref on a closed entry misleads the next grep.

**Update CLAUDE.md:**

- [ ] **E8: zsh line under "Known environment issues"** (friction (a); no zsh guidance exists in CLAUDE.md, `.claude/rules`, `.claude/skills` or `.claude/references`, observed (this review) by grep). Text: "The shell is zsh: an unquoted `$VAR` holding several paths is one argument (use an array, `files=(a b); cmd \"${files[@]}\"`), and a word starting with `=` is expanded as a command path (quote it: `echo '====='`)."
- [ ] **E4: pre-push hook rewrites `skill-versions.yaml` (recurring, 3 or more times: #408 sessions 1 and 2, and this push).**
  - Cause: `scripts/ci-local-fallback.sh` runs `make check` whenever it cannot confirm Actions is healthy (`:14`), and `make test` stamps dates. Unlike `record-gate.sh`, the hook does not restore clean-before stamps.
  - Remedy: restore them in the hook after `make check`, using the same rule as `record-gate.sh`.
  - Until the remedy lands, add to CLAUDE.md "Known environment issues": "After a push, `git status`: the pre-push fallback may re-stamp `app/ai/agents/*/skill-versions.yaml`; restore them."
- [ ] **E5: c8 `expected.html` trailing-whitespace churn (recurring since Track F; again this loop, friction (i)).** `.pre-commit-config.yaml:13-14` does not exclude converter baselines. Remedy: add `exclude: ^data/debug/\d+/expected\.html$` to `trailing-whitespace`, since the snapshot gate already normalises whitespace. Until then, note it in `converter-fix` §4.1.

**Update converter-fix §0.2 (preflight):**

- [ ] **E13.** State whether a plan-time deferred-items table dated the same day on the same base satisfies §0.2. Recommended: no. Run `/preflight-check` and paste its table, because its friction-pattern scan is the part the plan-time grep does not do.

**Create New Skill:**

- None. No manual process repeated three or more times that a skill would absorb better than E1–E5.

## Key Learnings

**What worked well:**

- The fresh-context pre-PR review found three Medium defects that the implementing context had missed. On F2, the implementer's own check was too narrow to see the defect. Running `piv-review-pr` in a clean subagent paid for itself on the first real ticket.
- Fanning subagents out with exclusive file ownership across F2, F5 and F7 produced no conflicts. Keeping the matcher, the renderer and the tests with the lead kept the RED/green loop in one context.
- The byte-identity literal captured from the base code, and the A3 worktree reproducing prior scores before re-scoring, are strong self-checks. Both are worth reusing.
- `converter-fix` §7 "Partial acceptance" worked as written. F2–F5 claim no corpus change and are proven on real sections.

**What needs improvement:**

- The skill chain's order (validate → commit → PR) conflicts with its own `head == HEAD` check (E1).
- The gate recorder treats the loop's own artefacts as dirt (E2).
- Plans narrowed to corpus shapes let generality defects through to review (E7).
- Amendments bypass pattern references (E6).
- Two environment issues recurred, again with no control (E4, E5).

**For next implementation:**

- Commit, then gate, then open the PR.
- Keep subagent drafts in `.claude/state/<ticket>/` while a gate runs.
- At plan time, list the accepted input shapes against the corpus shapes.

Disposition of each learning:

- "Plans narrowed to the corpus let generality defects through": becomes action E7.
- "Amendments skip pattern checks": becomes action E6.
- "The skill order invalidates the gate": becomes action E1.
- "Untracked artefacts dirty the gate": becomes action E2.
- "Parallel writers during a gate": becomes action E3.
- "The background wrapper died": becomes action E11 (low rank).
- "Unquoted heredoc": becomes action E10.
- The user's A3 trade ratification (c6 −0.0071 full_image; c9 section_min 0.4479 → 0.3033, observed (lead)) is **accepted risk, not worth a control**. The jitter rule and the ratification step already handle it, and they worked here.

## Ledger rows to append (not applied: caller constraint)

This run was limited to creating this file and the execution report. `REMEDY-LEDGER.md` was **not edited**, so the skill's mandatory last step is outstanding. Append these rows in this order, with `PR` = `open`. No rows are closed, because nothing was applied. There are no recurrences to record, because the ledger had no rows.

| Date | Symptom | Root cause | Remedy (file) | PR |
|---|---|---|---|---|
| 2026-09-28 | Green gate invalidated by the WIP fold; gate re-run at `c29122d8` (t1-social-section-column-content-review.md, E1) | Hand-off order validate→commit, and `piv-commit` folds only one WIP commit, while `piv-create-pr` requires record `head == HEAD` | `.claude/skills/converter-fix/SKILL.md` §8, `.claude/skills/piv-implement/SKILL.md` "Next", `.claude/skills/piv-commit/SKILL.md` step 1 | open |
| 2026-09-28 | Untracked report/review made gates `dirty`; lead parked files in scratch each gate (t1-…-review.md, E2) | `record-gate.sh:91-94` counts untracked files; the PIV artefact directories are not gitignored | `.claude/skills/piv-create-pr/scripts/record-gate.sh` (gate-evidence writer), `.claude/skills/piv-validate/SKILL.md` §2 | open |
| 2026-09-28 | Gate at `71b9db89` short: subagent created a file mid-run (t1-…-review.md, E3) | No write location for subagents during a gate | `.claude/skills/piv-validate/SKILL.md` §2 | open |
| 2026-09-28 | F3–F5 plan-born generality defects found only at review (t1-…-review.md, E7) | Plan limits handling to corpus shapes without ledgering the general case; tree check asserts presence only | `.claude/skills/piv-plan-implementation/SKILL.md` Quality Criteria, `.claude/skills/converter-fix/SKILL.md` §0.4 | open |
| 2026-09-28 | R1 three-part log event added by an amendment (t1-…-review.md, E6) | Amendments do not re-open Patterns to Follow references | `.claude/skills/piv-plan-implementation/SKILL.md` AMENDMENTS template | open |
| 2026-09-28 | Pre-push hook re-stamps `skill-versions.yaml` (3 or more times: #408 s1, s2, #409) (t1-…-review.md, E4) | `scripts/ci-local-fallback.sh` runs `make check` without restoring clean-before stamps | `scripts/ci-local-fallback.sh`, `CLAUDE.md` Known environment issues | open |
| 2026-09-28 | c8 `expected.html` stripped by trailing-whitespace again (t1-…-review.md, E5) | No exclusion for converter baselines | `.pre-commit-config.yaml` `trailing-whitespace` | open |
| 2026-09-28 | Guard hook blocked `rm -rf .tmpscratch/…` and a read-only grep (t1-…-review.md, E9) | Substring match on the whole command; broad rule blocks any dotted relative path | `.claude/hooks/block-dangerous.sh:59-70` | open |
| 2026-09-28 | zsh word-split and `=word` failures (t1-…-review.md, E8) | No zsh guidance in the AI layer | `CLAUDE.md` Known environment issues | open |
| 2026-09-28 | Preflight skipped on a converter ticket (t1-…-review.md, E13) | `converter-fix` §0.2 does not say whether a plan-time grep satisfies it | `.claude/skills/converter-fix/SKILL.md` §0.2 | open |
| 2026-09-28 | Drifted code_ref left on a closed entry (t1-…-review.md, E12) | Plan instruction conflicts with `deferred-items` close step | `.claude/skills/deferred-items/SKILL.md` close step | open |
| 2026-09-28 | Unquoted heredoc swallowed backticks in the PR body (t1-…-review.md, E10) | `piv-create-pr` documents create, not edit | `.claude/skills/piv-create-pr/SKILL.md` Phase 3 | open |
| 2026-09-28 | Background wrapper killed (exit 144) while `record-gate.sh` ran on as an orphan (t1-…-review.md, E11) | `piv-validate` does not say how to run or recover a background gate | `.claude/skills/piv-validate/SKILL.md` §2 | open |

Default apply-slot candidates for the next loop are the top two open rows, E1 and E2. Both are structural and cost this loop a gate re-run and a scratch-parking workaround on every gate.
