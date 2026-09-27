---
name: system-evolution-review
description: Performs a meta-level review of how well an implementation followed its plan, classifying divergences and recommending AI-Layer improvements. Use after an execution report exists to find bugs in the process, not the code.
argument-hint: "[plan-file] [execution-report-file] — or a free-form scope for a project-wide review"
arguments: [plan, report]
---

# System Review

Perform a meta-level analysis of how well the implementation followed the plan and identify process improvements.

## Purpose

**System review is NOT code review.** You're not looking for bugs in the code - you're looking for bugs in the process.

**Your job:**

- Analyze plan adherence and divergence patterns
- Identify which divergences were justified vs problematic
- Surface process improvements that prevent future issues
- Suggest updates to AI-Layer assets (CLAUDE.md, plan templates, skills)

**Philosophy:**

- Good divergence reveals plan limitations → improve planning
- Bad divergence reveals unclear requirements → improve communication
- Repeated issues reveal missing automation → create skills

## Context & Inputs

**Check both arguments before you read anything.** They are POSITIONAL — plan first, execution
report second — and getting one argument instead of two is the common failure: `$plan` silently
receives the report and `$report` resolves to empty. If either is missing, or if `$plan` points
into `.claude/execution-reports/` (which means they were passed in one slot or reversed), say
which you got and ask — do not guess. Correct form:

```
/system-evolution-review .agents/plans/<feature>.md .claude/execution-reports/<feature>.md
```

**A first argument that is present but does not end in `.md` is a word-split sentence, not a plan
path** — an empty first argument is the missing-argument case above, so ask. — a project-wide run
of this skill in the project it came from got `$plan`="the", `$report`="whole". Test that suffix
before reading anything; if it fails, do not ask — run project-wide: scope from the sentence you were
invoked with, `.claude/system-reviews/*.md` plus `.claude/execution-reports/*.md` read in place of the
pair, and every later `$plan`/`$report` naming those two sets.

**Remedy ledger — read FIRST, before the four artifacts:**
`.claude/system-reviews/REMEDY-LEDGER.md` — one table row per remedy (`Date | Symptom | Root cause |
Remedy (file) | PR`). A row whose `PR` cell is `open` is recommended but not yet applied; table order among
open rows is the rank. Two things to do with it: (1) check whether any open row's *class* (its Root cause)
recurred in the loop you are reviewing — a recurrence of a logged item is a finding in itself, at higher
severity than a new one (in the project this skill came from, one loop logged an item and the next paid for
it); (2) the topmost open rows are the default candidates for this review's 1–2 apply slots, ahead of
anything newly discovered of equal weight — the queue exists because "first candidate for the next loop's
apply slot" once sat unapplied for seven loops.

You will analyze four key artifacts:

**Plan Skill:**
Read this to understand the planning process and what instructions guide plan creation.
`.claude/skills/piv-plan-implementation/SKILL.md`

**Generated Plan:**
Read this to understand what the agent was SUPPOSED to do.
Plan file: $plan

**Execute Skill:**
Read this to understand the execution process and what instructions guide implementation.
`.claude/skills/piv-implement/SKILL.md`

**Execution Report:**
Read this to understand what the agent ACTUALLY did and why.
Execution report: $report

## Analysis Workflow

### Step 1: Understand the Planned Approach

Read the generated plan ($plan) and extract:

- What features were planned?
- What architecture was specified?
- What validation steps were defined?
- What patterns were referenced?

### Step 2: Understand the Actual Implementation

Read the execution report ($report) and extract:

- What was implemented?
- What diverged from the plan?
- What challenges were encountered?
- What was skipped and why?

### Step 3: Classify Each Divergence

For each divergence identified in the execution report, classify as:

**Good Divergence** (Justified):

- Plan assumed something that didn't exist in the codebase
- Better pattern discovered during implementation
- Performance optimization needed
- Security issue discovered that required different approach

**Bad Divergence** (Problematic):

- Ignored explicit constraints in plan
- Created new architecture instead of following existing patterns
- Took shortcuts that introduce tech debt
- Misunderstood requirements

### Step 4: Trace Root Causes

For each problematic divergence, identify the root cause:

- Was the plan unclear, where, why?
- Was context missing, where, why?
- Was validation missing, where, why?
- Was manual step repeated, where, why?

### Step 5: Generate Process Improvements

Based on patterns across divergences, suggest:

- **CLAUDE.md updates:** Universal patterns or anti-patterns to document
- **Plan skill updates:** Instructions that need clarification or missing steps
- **New skills:** Manual processes that should be automated
- **Validation additions:** Checks that would catch issues earlier

## Output Format

Save your analysis to: `.claude/system-reviews/[feature-name]-review.md`

### Report Structure:

#### Meta Information

- Plan reviewed: [path to $plan]
- Execution report: [path to $report]
- Date: [current date]

#### Overall Alignment Score: \_\_/10

Scoring guide:

- 10: Perfect adherence, all divergences justified
- 7-9: Minor justified divergences
- 4-6: Mix of justified and problematic divergences
- 1-3: Major problematic divergences

**The adherence score is blind to plan-inherited defects** — a false claim born in the plan and copied
forward faithfully scores as adherence, not as a defect. In the project this skill came from, two loops
both scored 9/10 and produced the only two defects that ever reached `main`.
When a defect originated in the plan and was reproduced faithfully, add a **second score** —
`Plan correctness: __/10 — [the defect, and the plan line it entered at]` — and list it under Divergence
Analysis as `plan_defect:` with `entered_at:` and `reproduced_at:`. Not as a `bad` divergence: faithful
reproduction is not a divergence, and a caveat beside a 9/10 does not change the 9/10. One of those
reviews wrote one voluntarily and still scored 9.

#### Divergence Analysis

For each divergence from the execution report:

```yaml
divergence: [what changed]
planned: [what plan specified]
actual: [what was implemented]
reason: [agent's stated reason from report]
classification: good | bad
justified: yes/no
root_cause: [unclear plan | missing context | etc]
```

#### Pattern Compliance

Assess adherence to documented patterns:

- [ ] Followed codebase architecture
- [ ] Used documented patterns (from CLAUDE.md)
- [ ] Applied testing patterns correctly
- [ ] Met validation requirements

#### System Improvement Actions

Based on analysis, recommend specific actions:

**Update CLAUDE.md:**

- [ ] Document [pattern X] discovered during implementation
- [ ] Add anti-pattern warning for [Y]
- [ ] Clarify [technology constraint Z]

**Update Plan Skill ($plan):**

- [ ] Add instruction for [missing step]
- [ ] Clarify [ambiguous instruction]
- [ ] Add validation requirement for [X]

**Create New Skill:**

- [ ] A new skill for [manual process repeated 3+ times]

**Update Execute Skill:**

- [ ] Add [validation step] to execution checklist

#### Key Learnings

**What worked well:**

- [specific things that went smoothly]

**What needs improvement:**

- [specific process gaps identified]

**For next implementation:**

- [concrete improvements to try]

**Rule for this section: a learning phrased as a recurring mechanism is not allowed to rest here.**
It either becomes an action item (applied now, or a ranked row in the ledger) or is explicitly marked
**"accepted risk — not worth a control, because …"**. One review's sharpest insight ("a plan's numbers
are inherited, not audited") went into Key Learnings with no action item, and the next loop reproduced it
verbatim.
A learning without an action item is a prediction, not a control.

#### Update the ledger (mandatory last step)

Before finishing, update `.claude/system-reviews/REMEDY-LEDGER.md`:

- **Append** every "recommended, not applied" item from this review as a row with `PR` = `open`, placed
  among the open rows by rank; `Symptom` names this review file as its origin.
- **Close** each item this review applied — set its `PR` cell to the PR that carries it, and put the grep
  that verifies the remedy exists at HEAD in its `Remedy (file)` cell. An "acted on" checkbox in the report
  body is not the record; the ledger row is.
- **Record a recurrence** on any open row whose class fired again in this loop: append
  `(recurred <YYYY-MM-DD>, <this review>)` to its `Symptom` cell and move it up the open rows.

A remedy with no ledger row and no repo reference can be deleted silently and stay "applied" in an old
report forever — that is how two gate scripts in the project this skill came from were deleted with no
review noticing. The same risk applies here to `.claude/skills/piv-create-pr/scripts/record-gate.sh` (the
gate-evidence writer behind `.claude/last-gate.json`): give it a ledger row when a review recommends it.

## Important

- **Be specific:** Don't say "plan was unclear" - say "plan didn't specify which auth pattern to use"
- **Focus on patterns:** One-off issues aren't actionable. Look for repeated problems.
- **Action-oriented:** Every finding should have a concrete asset update suggestion
- **Suggest improvements:** Don't just analyze - actually suggest the text to add to CLAUDE.md or skills
