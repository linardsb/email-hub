---
name: piv-fix-review-findings
description: Triage code-review findings (manual or AI), fix the ones you choose one at a time with tests, defer/log the rest, then validate — and if the work is on a PR, commit and push so the PR reflects the fixes. Use after a review has produced a list of issues or a review file.
argument-hint: "[code-review-file-or-issues] [scope / what to fix now vs defer]"
---

# Fix Review Findings

A review produced findings — but a review is **input, not a work order.** You decide what happens to each one.

Read `$ARGUMENTS` as **prose**, not as positional slots — never split on whitespace and never bind by
position. Two things may be in there and the second is free-form, so it will contain spaces:

1. **The code review** — a file path, a PR/comment URL, or a description of the issues.
2. **Direction / scope** *(optional)* — what to fix now vs defer. An unquoted steer is still one steer.

If the review itself is missing, ask for it once, in a single message.

If the Code-review is a file, **read the entire file first** so you understand every finding before triaging.

## 0. Check the ground before you start

Two things that are cheap to check now and expensive to discover at push time.

**Is the PR still open?** Find it (`gh pr list --head "$(git branch --show-current)"`) and read its state:

- **OPEN** → normal path; the fixes land on this PR at step 4.
- **MERGED / CLOSED** → say so **now**. The fixes need their own branch and PR, or a direct commit if the
  project allows one — settle which with the human before fixing, not after pushing. `piv-review-pr` guards
  this too, but this skill runs *after* it, and a solo repo can merge in between.

**Is the worktree actually yours?** `git status --porcelain`, plus a probe for an interrupted operation:

```bash
GD=$(git rev-parse --git-dir); ls "$GD"/MERGE_HEAD "$GD"/REBASE_HEAD "$GD"/CHERRY_PICK_HEAD 2>/dev/null
```

Use `git rev-parse --git-dir` — **in a worktree `.git` is a file, not a directory**, so `ls .git/MERGE_HEAD`
gives a false negative. If another session left a half-finished merge or staged work in the index, resolve
who owns it before committing; otherwise their work lands in your commit.

## 1. Triage first (the human's call)

Sort the findings before touching code. Honor any direction in the scope argument; if it's unclear, surface the
findings grouped and **ask** rather than fixing everything by default:

- **Fix now (this PR)** — real, in-scope, belongs with this change.
- **Defer** — real but later; don't bloat this PR. A deferral goes to the open-gap ledger
  `.agents/deferred-items.json`, per `.claude/rules/deferred-items.md` (open it first — it is the schema):
  - **Critical** → cannot be deferred without the human's explicit call in this session.
  - **High / Medium** that is a real defect → append one object to the file's `items` array with every required
    field: `id` (`phase-<N>.<sub>-<short-slug>`; use the PR's phase/track, e.g. `phase-53g-g4-…`), `phase`, `title`,
    `status: "deferred"`, `severity`, `introduced` (today, `YYYY-MM-DD`), `introduced_commit` (`"pending"` — the
    user squash-merges, so a PR head SHA never lands on `main`; stamp the squash SHA after the merge),
    `summary` (name the PR and the finding code), `code_refs` (`file:line (symbol)`), `symptom_if_broken`,
    `closes_when`. Optional `fix_sketch` carries the reviewer's proposed fix.
  - **Ledger `severity` is not review severity.** Map: reproduced or read-confirmed defect → `known-bug`; plausible
    by inspection but unconfirmed → `speculative`; an acceptance criterion that needs data or a fixture that does
    not exist yet → `soft`.
  - **Low** polish / "could be cleaner" → do **not** log it; the rules file excludes subjective preferences. Note it
    in the fixes report and drop it — the review of whichever PR next touches that file re-finds it if it matters.
  - Before appending, grep the ledger for the file and symptom: an existing entry gets a `notes` line, not a
    duplicate. After appending, prove it still parses: `python3 -m json.tool .agents/deferred-items.json >/dev/null`.
  - A finding this PR closes that the ledger already carries → set `status: "closed"` and add `closed_commit` (the
    rules file's field, not `closed_at` / `closed_date`; `"pending"` until the squash SHA exists, as above).
- **Needs a human look / manual test** — anything you should inspect or test by hand before trusting it. Flag it,
  don't silently auto-fix.
- **Noise / won't-fix** — say why, then drop it.

Don't let the reviewer dictate scope — "real, but later" is a valid and common call; a clean small PR beats a
sprawling one.

## 1.5 A code-scanning round

email-hub's scanners report to GitHub code scanning: Semgrep now (`.github/workflows/semgrep.yml`), plus a
`codeql` job in `ci.yml` once it lands (expected, not yet written). Semgrep runs with `continue-on-error: true`, so
**its check is green whatever it finds — do not wait for a red check.** When there are open alerts on the PR's
merge ref, they are the findings, not a reviewer's list. Feed them in with this command (`{N}` = the PR number;
the executable step, so a broken endpoint shows in a diff):

```bash
gh api --paginate "repos/{owner}/{repo}/code-scanning/alerts?ref=refs/pull/{N}/merge&state=open&per_page=100" \
  --jq '.[] | "F\(.number) [\(.tool.name)] (\(.rule.security_severity_level // .rule.severity), \(.rule.id)) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line) — \(.most_recent_instance.message.text // .rule.description) \(.html_url)"'
```

A 403/404 means code scanning is not enabled on the repo (the SARIF upload step tolerates that): say so in the
report, and read the `semgrep-sarif` workflow artifact instead if the round needs Semgrep's findings.

Then triage as in §1, under rules that are not negotiable inside a session:

- **No suppression comments** in source — neither Semgrep's `nosem` / `nosemgrep` nor CodeQL's `lgtm` /
  `codeql[…]` forms. The `PreToolUse` hook (`.claude/hooks/pre_tool_use.py`) refuses them in shipped-source files.
- **No new `.semgrepignore` paths** — an ignore entry is a suppression by another route, and the hook fences that
  file.
- **Never dismiss an alert** through the API; the hook refuses that too. A human dismisses in the GitHub UI, with
  a reason, and the gate honours that on the next run.
- **Touch only findings inside this PR's diff** (`gh pr diff {N} --name-only`, then the changed lines): an alert
  the base already carries is the backlog and stays where it is.
- **Never remove the feature** to lower a count.
- **At most 3 push-and-rescan cycles**, then stop and hand to the human. The re-scan is CI's scan on the pushed
  commit (`semgrep.yml`, or the `codeql` job once it exists), never a local scanner.
- A finding that is genuinely wrong gets one line in the PR body under `## Notes for the reviewer`
  ("Code-scanning disputed (<tool>): `<rule>` at `<file:line>` — <why>"), not a suppression.

Name the report round `scan-<n>` (see Output).

## 2. Fix the "fix now" set — one at a time

For each:
1. Explain what was wrong.
2. Make the fix.
3. Create and run a test that proves it. Where you can, **run the new test against the unfixed
   code and watch it fail** — that is the only thing separating a regression test from a passing
   decoration. **Probe with the input or mutation the finding NAMES, verbatim, before writing a
   cleaner one.** A same-shaped substitute proves the test catches *your* mutation, not the
   reviewer's, and it can go green on code that is genuinely broken:
   - One PR's F1 — probed the ReDoS with `'https://a' + '/'.repeat(100_000)`; the review's input
     ended in a non-slash character. It **passed on the vulnerable body in 8 ms**, because a slash
     run reaching the end of the string matches on the regex engine's first attempt. With the
     review's trailing `x` the same body took **8892.7 ms** against a 250 ms bound. Two attempts,
     and the first one was a false green.
   - Another PR's L1 — the decline was published in three surfaces on a log-only helper that was
     `14 passed, 14 total` through the reviewer's exact edit.

   If you cannot reproduce the finding's own input (it needs a service, a fixture you do not have),
   say so in the fixes report and name what you probed instead. A substituted probe is a reduced
   claim, not an equivalent one.
4. For a **Critical or High**, answer in one line: **what new failure mode does this fix's
   mechanism have?** — a swallowed `catch`, a promise chain with no terminal `catch`, a flag set
   before the thing it claims, a read moved before the write it depends on — and add the test for
   *that* before moving on. The repro from step 3 proves the old failure is gone; it says nothing
   about the one the mechanism introduced. Both of one PR's round-2 Highs were round-1 fixes
   that passed their repros.

### When a fix changes a NUMBER or a GUARANTEE, chase its copies

A figure gets written once and quoted four times. Fixing the original and stopping leaves the
copies stating the old, now-false claim — and the repo rule ("a number or a guarantee in a
comment, plan or PR body is a claim, not decoration") is broken by the copies just as much.

Grep for the **value**, not the topic word. The stale copy usually does not contain the word you
fixed — correcting a "429" claim leaves a stale *viewer count* and a stale *test total*, neither
of which contains "429". Check:

- the docblocks and constants around the fix
- `.agents/plans/<feature>.md` — including its task list, ACs and manual-validation steps, not
  just the one paragraph you already found
- `.claude/reports/<feature>-report.md` — gate figures go stale the moment a test is added
- **the PR body** — no working-tree grep can reach it, and it is the first thing the next
  reviewer reads and the number they will re-run the gate against

Chase the **subject** as well as the value: a retired claim survives as a verb ("the cache this
script *measures*") long after its number is gone — grep the noun (`quantiz`, `grid`, the issue
number) too. And make the sweep **checkable**: list in `.claude/reports/pr-{N}-review-fixes.md`
the exact `grep -n` you ran per retired value/noun and its hits in the plan, the report and the
PR body, so the reviewer diffs a list instead of trusting a sentence. On one PR this rule was written in two files, was
followed for the digits, and still missed the sentence three times — because its
output was a feeling, not a list.

## 3. Validate

Run the `piv-validate` skill to finalize the fixes.

## 4. If operating on a PR — commit and push

**Before committing: run every finding's closing command NOW, against the fixed tree, before writing
its closing sentence.** "Every one is fixed; nothing was deferred" is a claim like any other — one
PR's closing line quoted a command run that predated its own fix, and the fix did not work (round 2
found it). A finding's closing line in `.claude/reports/pr-{N}-review-fixes.md` quotes the command, when it
ran, and its output — or says "not run" honestly.

If these fixes are on a PR branch, **commit them (use `piv-commit`) and push** so the PR reflects the fixes and the
review can re-run on the updated PR. `piv-commit` stages by path: name `.agents/deferred-items.json` in the staged set when §1 changed it. If
nothing was fixed (everything deferred), commit just the `.agents/deferred-items.json` change the same way and push
it — every deferred item must be filed where §1 says it goes.

## Output

A short report: what was **fixed** (with its test), what was **deferred** (with its `.agents/deferred-items.json`
`id`, or "dropped — Low"), what needs a **manual look/test** — and, if on a PR, the **pushed commit** + confirmation the PR is updated.

Write it to `.claude/reports/pr-{N}-review-fixes.md` (round number in the name when there is more
than one). `piv-review-pr` round ≥ 2 reads this file: a report that exists only in this session's
transcript cannot be cross-checked by the reviewer it is written for.
