---
name: system-execution-report
description: Generates a structured implementation report reflecting on a just-completed feature — what was done, divergences, challenges. Use right after finishing an implementation, as the input to a system review.
argument-hint: "[plan-file] (optional — defaults to this session's context)"
---

# Execution Report

Review and deeply analyze the implementation you just completed.

## Inputs

Read `$ARGUMENTS` as **prose**, not as positional slots — never split on whitespace and never
bind by position. The one input is a **plan path**, and it may arrive inside a sentence naming
the PR, the merge sha and the sibling artifacts. Take the `.md` path out of that sentence; take
every other artifact it names as well, and read them too.

**This guard is here because the alternative fired.** With `arguments: [plan]` declared, an
invocation beginning "PR #241 — the SMS provider switch slice…" bound `$plan` to the literal
string `PR`, and the skill rendered "**Plan file: PR**" (2026-09-21, ledger L18 — logged
2026-09-04 against this exact file and unapplied for the loops between).

**The plan path may be absent.** If it is, use the plan this session worked from.

If it is empty AND this session did not do the implementation, **say so and stop** rather than
writing a report from the diff alone: this skill reflects on *why* things diverged, and a cold
session can see what changed but not why. Ask for the plan path, or re-run in the implementing
session.

Also read, when they exist — they carry the divergences and the review's verdict, and a report
that contradicts them is worse than no report:

- `.claude/reports/<feature>-report.md` — the implementation report from `piv-implement`
- `.claude/code-reviews/pr-<N>-review.md` — any review that ran on this work

## Context

You have just finished implementing a feature. Before moving on, reflect on:

- What you implemented
- How it aligns with the plan
- What challenges you encountered
- What diverged and why

## Generate Report

Save to: `.claude/execution-reports/[feature-name].md`

### Meta Information

- Plan file: [path to plan that guided this implementation]
- Files added: [list with paths]
- Files modified: [list with paths]
- Lines changed: +X -Y

### Validation Results

- Syntax & Linting: ✓/✗ [details if failed]
- Type Checking: ✓/✗ [details if failed]
- Unit Tests: ✓/✗ [X passed, Y failed]
- Integration Tests: ✓/✗ [X passed, Y failed]

### What Went Well

List specific things that worked smoothly:

- [concrete examples]

### Challenges Encountered

List specific difficulties:

- [what was difficult and why]

### Divergences from Plan

For each divergence, document:

**[Divergence Title]**

- Planned: [what the plan specified]
- Actual: [what was implemented instead]
- Reason: [why this divergence occurred]
- Type: [Better approach found | Plan assumption wrong | Security concern | Performance issue | Other]

### Skipped Items

List anything from the plan that was not implemented:

- [what was skipped]
- Reason: [why it was skipped]

### Recommendations

Based on this implementation, what should change for next time?

- Plan skill improvements: [suggestions]
- Execute skill improvements: [suggestions]
- CLAUDE.md additions: [suggestions]
